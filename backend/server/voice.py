from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import hmac
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time
import os
from typing import Any
from urllib.parse import urlencode, urlsplit
import urllib.error
import urllib.request
import uuid
import wave

from .config import settings


ASR_PROVIDERS = {"funasr", "sherpa_onnx", "vivo", "mock"}
TTS_PROVIDERS = {"edge", "cosyvoice", "piper", "sherpa_onnx", "vivo", "mock"}

EDGE_VOICES = {
    "gentle": "zh-CN-XiaoxiaoNeural",
    "calm": "zh-CN-YunyangNeural",
    "bright": "zh-CN-XiaoyiNeural",
    "story": "zh-CN-XiaoxiaoNeural",
    "child": "zh-CN-XiaoyiNeural",
    "broadcast": "zh-CN-YunyangNeural",
}

VIVO_PRESET_VOICES = {
    "gentle": "xiaofu",
    "calm": "x2_yunye_news",
    "bright": "yige",
    "story": "F245_natural",
    "child": "yige_child",
    "broadcast": "GAME_GIR_LTY",
}


def _require_websocket() -> Any:
    try:
        from websocket import ABNF, create_connection
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("websocket-client 未安装，无法调用 Vivo 语音接口") from exc
    return ABNF, create_connection


def _audio_dir() -> Path:
    audio_dir = settings.storage_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def _new_audio_path(prefix: str = "tts", suffix: str = ".wav") -> Path:
    file_name = f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}{suffix}"
    return _audio_dir() / file_name


def _audio_url(path: Path) -> str:
    return f"/static/audio/{path.name}"


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return output.getvalue()


def _configured_asr_provider() -> str:
    provider = settings.asr_provider.lower().replace("-", "_")
    return provider if provider in ASR_PROVIDERS else "funasr"


def _configured_tts_provider() -> str:
    provider = settings.tts_provider.lower().replace("-", "_")
    return provider if provider in TTS_PROVIDERS else "cosyvoice"


def _provider_voice(value: str) -> str:
    if value in VIVO_PRESET_VOICES:
        return os.getenv(f"VIVO_TTS_VOICE_{value.upper()}", "").strip() or VIVO_PRESET_VOICES[value]
    return value or settings.vivo_tts_voice or "yige"


def _provider_voice_config(value: str) -> dict[str, str]:
    voice = _provider_voice(value)
    preset_key = value.upper() if value in VIVO_PRESET_VOICES else ""
    engine = (
        os.getenv(f"VIVO_TTS_ENGINE_{preset_key}", "").strip()
        if preset_key
        else ""
    ) or settings.vivo_tts_engine_id
    return {"voice": voice, "engineid": engine}


def _split_tts_chunks(text: str, max_bytes: int = 1800) -> list[str]:
    source = text.strip()
    if not source:
        return [""]
    parts = re.split(r"(?<=[。！？；;!?])\s*", source)
    chunks: list[str] = []
    current = ""
    for part in [item for item in parts if item]:
        candidate = f"{current}{part}" if current else part
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = ""
        buffer = ""
        for char in part:
            candidate_char = f"{buffer}{char}"
            if len(candidate_char.encode("utf-8")) > max_bytes and buffer:
                chunks.append(buffer)
                buffer = char
            else:
                buffer = candidate_char
        current = buffer
    if current:
        chunks.append(current)
    return chunks or [source]


def _path_exists(value: str) -> bool:
    return bool(value) and Path(value).expanduser().exists()


def _edge_runtime() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[2]
    configured = os.getenv("EDGE_TTS_PYTHON", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        root / "third_party" / "opentalking" / ".venv" / "Scripts" / "python.exe",
        root / "third_party" / "opentalking" / ".venv" / "bin" / "python",
    ]
    python_path = next((path for path in candidates if path and path.exists()), Path())
    return python_path, root / "scripts" / "synthesize_edge_tts.py"


def _split_args(value: str) -> list[str]:
    return shlex.split(value, posix=True) if value.strip() else []


def _number_to_chinese(value: int) -> str:
    digits = "零一二三四五六七八九"
    number = max(0, min(99, int(value)))
    if number < 10:
        return digits[number]
    if number == 10:
        return "十"
    if number < 20:
        return f"十{digits[number % 10]}"
    tens, ones = divmod(number, 10)
    return f"{digits[tens]}十{digits[ones] if ones else ''}"


def _format_clock_time(hour_text: str, minute_text: str) -> str:
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return f"{hour_text}点{minute_text}分"
    hour_label = f"{_number_to_chinese(hour)}点"
    if minute == 0:
        return hour_label
    minute_label = f"零{_number_to_chinese(minute)}" if minute < 10 and minute_text.startswith("0") else _number_to_chinese(minute)
    return f"{hour_label}{minute_label}分"


def normalize_spoken_text(text: str) -> str:
    """Convert display-oriented answer text into text that Chinese TTS reads naturally."""
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    clean = re.sub(r"\|?\s*-{2,}\s*\|?", "，", clean)
    clean = re.sub(r"[|*_`>#]", "，", clean)
    clean = re.sub(r"^\s*\d+\.\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(
        r"(\d{1,2})[:：](\d{2})\s*(?:-|~|—|–|到|至)\s*(\d{1,2})[:：](\d{2})",
        lambda match: f"{_format_clock_time(match.group(1), match.group(2))}到{_format_clock_time(match.group(3), match.group(4))}",
        clean,
    )
    clean = re.sub(
        r"(\d{1,2})[:：](\d{2})",
        lambda match: _format_clock_time(match.group(1), match.group(2)),
        clean,
    )
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"\s+([，。！？；：])", r"\1", clean)
    return clean.strip()


def speech_runtime_status() -> dict[str, Any]:
    asr = _configured_asr_provider()
    tts = _configured_tts_provider()
    return {
        "asr_provider": asr,
        "tts_provider": tts,
        "asr_ready": _asr_available(asr),
        "tts_ready": _tts_available(tts),
        "asr_effective_provider": asr if _asr_available(asr) else "mock",
        "tts_effective_provider": tts if _tts_available(tts) else "mock",
    }


def _asr_available(provider: str) -> bool:
    if provider == "mock":
        return True
    if provider == "vivo":
        return bool(settings.vivo_app_key)
    if provider == "funasr":
        return bool(settings.funasr_base_url) or _path_exists(settings.funasr_model_dir)
    if provider == "sherpa_onnx":
        return bool(settings.sherpa_onnx_asr_base_url) or bool(settings.sherpa_onnx_asr_command) or (
            _path_exists(settings.sherpa_onnx_asr_exe) and bool(settings.sherpa_onnx_asr_extra_args)
        )
    return False


def _tts_available(provider: str) -> bool:
    if provider == "mock":
        return True
    if provider == "edge":
        python_path, helper_path = _edge_runtime()
        return python_path.is_file() and helper_path.is_file()
    if provider == "vivo":
        return bool(settings.vivo_app_id and settings.vivo_app_key)
    if provider == "cosyvoice":
        return bool(settings.cosyvoice_base_url) or _path_exists(settings.cosyvoice_model_dir)
    if provider == "piper":
        return _path_exists(settings.piper_exe) and _path_exists(settings.piper_model)
    if provider == "sherpa_onnx":
        return bool(settings.sherpa_onnx_tts_base_url) or bool(settings.sherpa_onnx_tts_command) or (
            _path_exists(settings.sherpa_onnx_tts_exe) and bool(settings.sherpa_onnx_tts_extra_args)
        )
    return False


def _mock_tts(text: str, reason: str = "") -> dict[str, Any]:
    return {
        "provider": "mock",
        "audio_url": None,
        "message": reason or "语音服务处于本地保底模式，前端将使用浏览器播报。",
        "visemes": estimate_visemes(text),
    }


def _mock_asr(reason: str = "") -> dict[str, Any]:
    return {
        "provider": "mock",
        "text": settings.mock_asr_text.strip(),
        "message": reason or "语音输入处于本地保底模式，请继续使用文本输入。",
    }


def _post_json(url: str, payload: dict[str, Any], timeout: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _unwrap_payload(data: dict[str, Any]) -> dict[str, Any]:
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


def _save_base64_audio(audio_base64: str, prefix: str = "tts") -> str:
    encoded = audio_base64.split(",", 1)[1] if "," in audio_base64[:80] else audio_base64
    path = _new_audio_path(prefix=prefix, suffix=".wav")
    path.write_bytes(base64.b64decode(encoded))
    return _audio_url(path)


def _http_tts(base_url: str, path: str, text: str, voice: str, style: str, speed: float, volume: float, provider: str) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/{path.strip('/')}"
    data = _unwrap_payload(
        _post_json(
            endpoint,
            {
                "text": text,
                "voice": voice,
                "style": style,
                "speed": speed,
                "volume": volume,
            },
        )
    )
    audio_url = data.get("audio_url")
    audio_base64 = data.get("audio_base64") or data.get("audio")
    if audio_base64:
        audio_url = _save_base64_audio(str(audio_base64), provider)
    if not audio_url:
        raise RuntimeError(f"{provider} 未返回可播放音频")
    return {
        "provider": provider,
        "audio_url": audio_url,
        "message": f"{provider} 合成成功",
        "visemes": data.get("visemes") or estimate_visemes(text),
    }


def _http_asr(base_url: str, path: str, audio_data: bytes, filename: str, content_type: str, provider: str) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/{path.strip('/')}"
    data = _unwrap_payload(
        _post_json(
            endpoint,
            {
                "audio_base64": base64.b64encode(audio_data).decode("utf-8"),
                "filename": filename,
                "content_type": content_type,
            },
        )
    )
    return {
        "provider": provider,
        "text": str(data.get("text") or data.get("result") or "").strip(),
        "message": f"{provider} 识别完成",
    }


def _funasr_local(audio_data: bytes, filename: str, content_type: str) -> dict[str, Any]:
    try:
        from funasr import AutoModel  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("FunASR 未安装") from exc
    suffix = Path(filename).suffix or (".wav" if "wav" in content_type else ".webm")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as audio_file:
        audio_file.write(audio_data)
        audio_path = audio_file.name
    try:
        model = AutoModel(model=settings.funasr_model_dir)
        result = model.generate(input=audio_path)
    finally:
        Path(audio_path).unlink(missing_ok=True)
    text = ""
    if isinstance(result, list) and result:
        text = str(result[0].get("text", "") if isinstance(result[0], dict) else result[0])
    return {"provider": "funasr", "text": text.strip(), "message": "FunASR 识别完成"}


def _piper_tts(text: str, voice: str, style: str, speed: float, volume: float) -> dict[str, Any]:
    path = _new_audio_path(prefix="piper", suffix=".wav")
    command = [
        str(Path(settings.piper_exe).expanduser()),
        "--model",
        str(Path(settings.piper_model).expanduser()),
        "--output_file",
        str(path),
    ]
    if settings.piper_config and _path_exists(settings.piper_config):
        command.extend(["--config", str(Path(settings.piper_config).expanduser())])
    subprocess.run(command, input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=True)
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Piper 未生成音频文件")
    return {
        "provider": "piper",
        "audio_url": _audio_url(path),
        "message": "Piper 离线语音合成完成",
        "visemes": estimate_visemes(text),
    }


def _edge_voice(value: str) -> str:
    return EDGE_VOICES.get(value, value if value.startswith("zh-") else EDGE_VOICES["gentle"])


def _edge_percent(value: float, *, neutral: float = 1.0) -> str:
    percent = round((value - neutral) * 100)
    return f"{percent:+d}%"


def _edge_tts(text: str, voice: str, style: str, speed: float, volume: float) -> dict[str, Any]:
    del style
    python_path, helper_path = _edge_runtime()
    if not python_path.is_file() or not helper_path.is_file():
        raise RuntimeError("Edge 中文语音运行环境未就绪")
    output_path = _new_audio_path(prefix="edge", suffix=".wav")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as text_file:
        text_file.write(text)
        text_path = Path(text_file.name)
    command = [
        str(python_path),
        str(helper_path),
        "--text-file",
        str(text_path),
        "--output",
        str(output_path),
        "--voice",
        _edge_voice(voice),
        f"--rate={_edge_percent(speed)}",
        f"--volume={_edge_percent(volume)}",
    ]
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=True)
    finally:
        text_path.unlink(missing_ok=True)
    if not output_path.exists() or output_path.stat().st_size < 44:
        raise RuntimeError("Edge 中文语音未生成可播放音频")
    return {
        "provider": "edge",
        "audio_url": _audio_url(output_path),
        "message": "中文导游语音合成完成",
        "visemes": estimate_visemes(text),
    }


def _format_command_template(template: str, values: dict[str, str]) -> list[str]:
    formatted = template
    for key, value in values.items():
        formatted = formatted.replace("{" + key + "}", value)
    return _split_args(formatted)


def _sherpa_onnx_asr_local(audio_data: bytes, filename: str, content_type: str) -> dict[str, Any]:
    suffix = Path(filename).suffix or (".wav" if "wav" in content_type else ".webm")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as audio_file:
        audio_file.write(audio_data)
        audio_path = Path(audio_file.name)
    try:
        if settings.sherpa_onnx_asr_command:
            command = _format_command_template(settings.sherpa_onnx_asr_command, {"input": str(audio_path)})
        else:
            command = [
                str(Path(settings.sherpa_onnx_asr_exe).expanduser()),
                *_split_args(settings.sherpa_onnx_asr_extra_args),
                str(audio_path),
            ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=True)
    finally:
        audio_path.unlink(missing_ok=True)
    output = result.stdout.decode("utf-8", errors="ignore").strip()
    text = _extract_text_from_cli_output(output)
    if not text:
        raise RuntimeError("sherpa-onnx ASR 未返回识别文本")
    return {"provider": "sherpa_onnx", "text": text, "message": "sherpa-onnx 离线识别完成"}


def _extract_text_from_cli_output(output: str) -> str:
    if not output:
        return ""
    try:
        data = json.loads(output)
        if isinstance(data, dict):
            return str(data.get("text") or data.get("result") or "").strip()
    except json.JSONDecodeError:
        pass
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    for line in reversed(lines):
        if ":" in line:
            candidate = line.rsplit(":", 1)[-1].strip()
            if candidate:
                return candidate
    return lines[-1]


def _sherpa_onnx_tts_local(text: str, voice: str, style: str, speed: float, volume: float) -> dict[str, Any]:
    output_path = _new_audio_path(prefix="sherpa-onnx", suffix=".wav")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as text_file:
        text_file.write(text)
        text_path = Path(text_file.name)
    try:
        values = {
            "text": text,
            "text_file": str(text_path),
            "output": str(output_path),
            "voice": voice,
            "style": style,
            "speed": str(speed),
            "volume": str(volume),
        }
        if settings.sherpa_onnx_tts_command:
            command = _format_command_template(settings.sherpa_onnx_tts_command, values)
            input_data = None
        else:
            command = [
                str(Path(settings.sherpa_onnx_tts_exe).expanduser()),
                *_split_args(settings.sherpa_onnx_tts_extra_args),
                "--output-filename",
                str(output_path),
            ]
            input_data = text.encode("utf-8")
        subprocess.run(command, input=input_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=True)
    finally:
        text_path.unlink(missing_ok=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("sherpa-onnx TTS 未生成音频文件")
    return {
        "provider": "sherpa_onnx",
        "audio_url": _audio_url(output_path),
        "message": "sherpa-onnx 离线语音合成完成",
        "visemes": estimate_visemes(text),
    }


def synthesize_tts(
    text: str,
    voice: str = "",
    style: str = "",
    speed: float = 1.0,
    volume: float = 0.86,
) -> dict[str, Any]:
    provider = _configured_tts_provider()
    spoken_text = normalize_spoken_text(text)
    voice = voice or settings.vivo_tts_voice or "gentle"
    style = style or "自然讲解"
    if not _tts_available(provider):
        return _mock_tts(spoken_text, f"{provider} 语音资源未就绪，已进入本地保底模式。")
    try:
        if provider == "mock":
            return _mock_tts(spoken_text)
        if provider == "edge":
            return _edge_tts(spoken_text, voice, style, speed, volume)
        if provider == "vivo":
            vivo_config = _provider_voice_config(voice)
            return synthesize_vivo_tts(
                spoken_text,
                voice=vivo_config["voice"],
                speed=speed,
                volume=volume,
                engineid=vivo_config["engineid"],
            )
        if provider == "cosyvoice":
            if settings.cosyvoice_base_url:
                return _http_tts(settings.cosyvoice_base_url, settings.cosyvoice_tts_path, spoken_text, voice, style, speed, volume, "cosyvoice")
            return _mock_tts(spoken_text, "CosyVoice 本地模型路径已配置，但当前轻量运行时未加载本地推理服务。")
        if provider == "piper":
            return _piper_tts(spoken_text, voice, style, speed, volume)
        if provider == "sherpa_onnx":
            if settings.sherpa_onnx_tts_base_url:
                return _http_tts(
                    settings.sherpa_onnx_tts_base_url,
                    settings.sherpa_onnx_tts_path,
                    spoken_text,
                    voice,
                    style,
                    speed,
                    volume,
                    "sherpa_onnx",
                )
            return _sherpa_onnx_tts_local(spoken_text, voice, style, speed, volume)
    except Exception as exc:
        return _mock_tts(spoken_text, f"{provider} 语音合成暂不可用，已进入本地保底模式：{exc}")
    return _mock_tts(spoken_text)


def transcribe_asr(audio_data: bytes, filename: str = "", content_type: str = "") -> dict[str, Any]:
    provider = _configured_asr_provider()
    if not audio_data:
        return _mock_asr("没有收到音频内容。")
    if not _asr_available(provider):
        return _mock_asr(f"{provider} 语音识别资源未就绪，已进入本地保底模式。")
    try:
        if provider == "mock":
            return _mock_asr()
        if provider == "vivo":
            is_pcm = "pcm" in content_type.lower() or filename.lower().endswith(".pcm")
            if not is_pcm:
                return _mock_asr("Vivo 实时识别需要 16k/16bit 单声道 PCM，本次录音格式已交给文本输入保底。")
            return transcribe_vivo_asr(audio_data)
        if provider == "funasr":
            if settings.funasr_base_url:
                return _http_asr(settings.funasr_base_url, settings.funasr_asr_path, audio_data, filename, content_type, "funasr")
            return _funasr_local(audio_data, filename, content_type)
        if provider == "sherpa_onnx":
            if settings.sherpa_onnx_asr_base_url:
                return _http_asr(
                    settings.sherpa_onnx_asr_base_url,
                    settings.sherpa_onnx_asr_path,
                    audio_data,
                    filename,
                    content_type,
                    "sherpa_onnx",
                )
            return _sherpa_onnx_asr_local(audio_data, filename, content_type)
    except Exception as exc:
        return _mock_asr(f"{provider} 语音识别暂不可用，已进入本地保底模式：{exc}")
    return _mock_asr()


def _vivo_gateway_headers(
    *,
    method: str,
    path: str,
    canonical_query: str,
    app_id: str,
    app_key: str,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build Vivo AI Gateway headers without exposing the application key."""

    request_timestamp = timestamp or str(int(time.time()))
    request_nonce = nonce or uuid.uuid4().hex[:8]
    signed_headers = "x-ai-gateway-app-id;x-ai-gateway-timestamp;x-ai-gateway-nonce"
    signed_header_values = (
        f"x-ai-gateway-app-id:{app_id}\n"
        f"x-ai-gateway-timestamp:{request_timestamp}\n"
        f"x-ai-gateway-nonce:{request_nonce}"
    )
    signing_string = (
        f"{method.upper()}\n{path}\n{canonical_query}\n{app_id}\n"
        f"{request_timestamp}\n{signed_header_values}"
    )
    signature = base64.b64encode(
        hmac.new(app_key.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    return {
        "X-AI-GATEWAY-APP-ID": app_id,
        "X-AI-GATEWAY-TIMESTAMP": request_timestamp,
        "X-AI-GATEWAY-NONCE": request_nonce,
        "X-AI-GATEWAY-SIGNED-HEADERS": signed_headers,
        "X-AI-GATEWAY-SIGNATURE": signature,
    }


def _vivo_tts_payload(data: bytes | str) -> dict[str, Any]:
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Vivo TTS 返回了无法解析的响应") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Vivo TTS 返回格式无效")
    error_code = payload.get("error_code", 0)
    if error_code not in (0, "0", None):
        error_message = str(payload.get("error_msg") or "服务调用失败")
        raise RuntimeError(f"Vivo TTS 错误 {error_code}: {error_message}")
    return payload


def synthesize_vivo_tts(text: str, voice: str = "", speed: float = 1.0, volume: float = 0.86, engineid: str = "") -> dict[str, Any]:
    if not settings.vivo_app_id or not settings.vivo_app_key:
        return _mock_tts(text, "Vivo App ID 或 Key 未配置，已进入本地保底模式。")
    ABNF, create_connection = _require_websocket()
    params = {
        "engineid": engineid or settings.vivo_tts_engine_id,
        "system_time": str(int(time.time())),
        "user_id": "lingjinglocaluser0000000000000001",
        "model": "unknown",
        "product": "unknown",
        "package": "lingjing.guide",
        "client_version": "1.0.0",
        "system_version": "unknown",
        "sdk_version": "unknown",
        "android_version": "unknown",
        "requestId": str(uuid.uuid4()),
    }
    canonical_query = urlencode(sorted(params.items()))
    parsed_url = urlsplit(settings.vivo_tts_url)
    request_path = parsed_url.path or "/"
    url = f"{settings.vivo_tts_url}?{canonical_query}"
    gateway_headers = _vivo_gateway_headers(
        method="GET",
        path=request_path,
        canonical_query=canonical_query,
        app_id=settings.vivo_app_id,
        app_key=settings.vivo_app_key,
    )
    headers = [f"{name}: {value}" for name, value in gateway_headers.items()]
    websocket = create_connection(url, header=headers, timeout=8)
    websocket.settimeout(8)
    try:
        initial_opcode, initial_data = websocket.recv_data(True)
        if initial_opcode == ABNF.OPCODE_CLOSE:
            raise RuntimeError("Vivo TTS 连接在初始化阶段关闭")
        if initial_opcode == ABNF.OPCODE_TEXT:
            _vivo_tts_payload(initial_data)
        pcm_buffer = bytearray()
        for chunk in _split_tts_chunks(text):
            request = {
                "aue": 0,
                "auf": "audio/L16;rate=24000",
                "vcn": voice or settings.vivo_tts_voice,
                "speed": max(0, min(100, round(speed * 50))),
                "volume": max(1, min(100, round(volume * 100))),
                "text": base64.b64encode(chunk.encode("utf-8")).decode("utf-8"),
                "encoding": "utf8",
                "reqId": int(round(time.time() * 1000)),
            }
            websocket.send(json.dumps(request, ensure_ascii=False))
            chunk_audio_bytes = 0
            while True:
                opcode, data = websocket.recv_data(True)
                if opcode == ABNF.OPCODE_CLOSE:
                    raise RuntimeError("Vivo TTS 在音频完成前关闭连接")
                if opcode == getattr(ABNF, "OPCODE_BINARY", 2):
                    binary_audio = bytes(data)
                    pcm_buffer.extend(binary_audio)
                    chunk_audio_bytes += len(binary_audio)
                    continue
                if opcode != ABNF.OPCODE_TEXT:
                    continue
                payload = _vivo_tts_payload(data)
                response_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                audio = response_data.get("audio")
                if audio:
                    try:
                        decoded_audio = base64.b64decode(str(audio), validate=True)
                    except (ValueError, base64.binascii.Error) as exc:
                        raise RuntimeError("Vivo TTS 返回的音频编码无效") from exc
                    pcm_buffer.extend(decoded_audio)
                    chunk_audio_bytes += len(decoded_audio)
                if response_data.get("status") == 2:
                    if chunk_audio_bytes == 0:
                        raise RuntimeError("Vivo TTS 返回完成状态但音频为空，请检查语音合成能力或调用额度")
                    break
    finally:
        websocket.close()
    if not pcm_buffer:
        raise RuntimeError("Vivo TTS 未返回音频数据")
    path = _new_audio_path(prefix="vivo", suffix=".wav")
    path.write_bytes(pcm_to_wav(bytes(pcm_buffer)))
    return {
        "provider": "vivo",
        "audio_url": _audio_url(path),
        "message": "Vivo TTS 合成成功",
        "visemes": estimate_visemes(text),
    }


def transcribe_vivo_asr(pcm_data: bytes) -> dict[str, Any]:
    if not settings.vivo_app_key:
        return _mock_asr("Vivo Key 未配置，已进入本地保底模式。")
    ABNF, create_connection = _require_websocket()
    request_id = uuid.uuid4().hex
    params = {
        "client_version": "unknown",
        "package": "lingjing.guide",
        "sdk_version": "unknown",
        "user_id": "lingjinglocaluser0000000000000001",
        "android_version": "unknown",
        "system_time": str(int(time.time() * 1000)),
        "net_type": "1",
        "engineid": settings.vivo_asr_engine_id,
        "requestId": str(uuid.uuid4()),
        "model": "unknown",
        "system_version": "unknown",
    }
    url = f"{settings.vivo_asr_url}?{urlencode(params)}"
    websocket = create_connection(url, header=[f"Authorization: Bearer {settings.vivo_app_key}"], timeout=8)
    websocket.settimeout(8)
    final_text = ""
    try:
        start_payload = {
            "type": "started",
            "request_id": request_id,
            "asr_info": {
                "end_vad_time": 1000,
                "audio_type": "pcm",
                "chinese2digital": 1,
                "punctuation": 1,
            },
            "business_info": "lingjing-guide",
        }
        websocket.send(json.dumps(start_payload, ensure_ascii=False))
        frame_bytes = 1280
        for offset in range(0, len(pcm_data), frame_bytes):
            websocket.send_binary(pcm_data[offset : offset + frame_bytes])
        websocket.send_binary(b"--end--")
        while True:
            opcode, data = websocket.recv_data(True)
            if opcode == ABNF.OPCODE_CLOSE:
                break
            if opcode != ABNF.OPCODE_TEXT:
                continue
            payload = json.loads(data)
            if payload.get("action") == "error" or payload.get("code") not in (None, 0):
                raise RuntimeError(f"Vivo ASR 错误: {payload}")
            if payload.get("action") == "result":
                text = payload.get("data", {}).get("text", "")
                if text:
                    final_text = text
                if payload.get("data", {}).get("is_last") or payload.get("is_finish"):
                    break
    finally:
        websocket.close()
    return {"provider": "vivo", "text": final_text, "message": "Vivo ASR 识别完成"}


def estimate_visemes(text: str) -> list[dict[str, Any]]:
    chars = [char for char in text if char.strip()]
    frames: list[dict[str, Any]] = []
    for index, char in enumerate(chars[:240]):
        openness = 0.25 + (ord(char) % 7) / 10
        frames.append({"time": round(index * 0.075, 2), "mouth": min(0.95, openness), "char": char})
    if not frames:
        frames.append({"time": 0, "mouth": 0.1, "char": ""})
    return frames
