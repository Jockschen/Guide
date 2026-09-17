from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ROOT, load_env


load_env()


class LipsyncPayload(BaseModel):
    text: str = ""
    audio_path: str = ""
    audio_url: str | None = None
    avatar_image: str = ""
    avatar_id: str = "lingjing-guide"
    model: str = "quicktalk"


app = FastAPI(title="Lingjing OpenTalking Bridge")


def _resolve_output_dir(raw_value: str | None = None) -> Path:
    value = raw_value or os.getenv(
        "OPENTALKING_OUTPUT_DIR",
        str(ROOT / "backend" / "storage" / "opentalking-output"),
    )
    output_dir = Path(value)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return output_dir.resolve()


OUTPUT_DIR = _resolve_output_dir()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = ROOT / "backend" / "storage" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

_QUICKTALK_LOCK = threading.Lock()
_QUICKTALK_ADAPTER: Any | None = None
_QUICKTALK_AVATAR_STATE: Any | None = None
_QUICKTALK_RENDERER_KEY: tuple[str, str, str, str] | None = None
_QUICKTALK_WARMING = False
_QUICKTALK_WARMED = False
_QUICKTALK_WARMUP_ERROR = ""

# OPENTALKING_INFER_COMMAND supports {audio}, {image}, {avatar}, {text}, {output},
# {model}, {python}, and {pythonq}. Use {pythonq} when the Python path may contain spaces.


def _resolve_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


def _tail(value: str, limit: int = 1200) -> str:
    text = value.strip()
    return text[-limit:] if len(text) > limit else text


def _safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
    return cleaned.strip("-")[:48] or "lingjing-guide"


def _file_digest(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_existing_file(path: str | Path | None) -> str:
    if not path:
        return ""
    try:
        candidate = Path(path)
        if candidate.is_file():
            return _file_digest(str(candidate))
    except OSError:
        return ""
    return ""


def _avatar_bundle_digest(avatar_dir: str, avatar_image: str = "") -> str:
    digest = hashlib.sha256()
    image_digest = _digest_existing_file(avatar_image)
    if image_digest:
        digest.update(f"image:{image_digest}|".encode("utf-8"))

    bundle = Path(avatar_dir) if avatar_dir else None
    if bundle and bundle.is_dir():
        manifest_path = bundle / "manifest.json"
        manifest_digest = _digest_existing_file(manifest_path)
        if manifest_digest:
            digest.update(f"manifest:{manifest_digest}|".encode("utf-8"))
        template_paths: list[Path] = []
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
                quicktalk = metadata.get("quicktalk") if isinstance(metadata, dict) else {}
                raw_template = quicktalk.get("template_video") if isinstance(quicktalk, dict) else ""
                if raw_template:
                    template_paths.append((bundle / str(raw_template)).resolve())
            except (json.JSONDecodeError, OSError):
                pass
        quicktalk_dir = bundle / "quicktalk"
        if quicktalk_dir.is_dir():
            template_paths.extend(sorted(quicktalk_dir.glob("template_*.mp4")))
        seen: set[str] = set()
        for template in template_paths:
            key = str(template)
            if key in seen:
                continue
            seen.add(key)
            template_digest = _digest_existing_file(template)
            if template_digest:
                digest.update(f"template:{template.name}:{template_digest}|".encode("utf-8"))

    value = digest.hexdigest()
    return value if value != hashlib.sha256().hexdigest() else ""


def _cached_output_path(
    payload: LipsyncPayload,
    audio_path: str,
    avatar_dir: str,
    command_template: str,
    avatar_image: str = "",
) -> Path:
    cache_input = "|".join(
        [
            payload.model,
            payload.avatar_id,
            avatar_dir,
            command_template,
            _avatar_bundle_digest(avatar_dir, avatar_image),
            _file_digest(audio_path),
        ]
    )
    cache_key = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()[:22]
    return OUTPUT_DIR / f"{_safe_stem(payload.avatar_id)}-{_safe_stem(payload.model)}-{cache_key}.mp4"


def _write_render_log(stem: str, command: str, cwd: str, timeout: int, stdout: str, stderr: str) -> dict[str, str]:
    command_log = LOG_DIR / f"{stem}.command.txt"
    stdout_log = LOG_DIR / f"{stem}.stdout.log"
    stderr_log = LOG_DIR / f"{stem}.stderr.log"
    command_log.write_text(
        f"cwd={cwd}\ntimeout={timeout}\ncommand={command}\n",
        encoding="utf-8",
    )
    stdout_log.write_text(stdout or "", encoding="utf-8")
    stderr_log.write_text(stderr or "", encoding="utf-8")
    return {
        "command_log": str(command_log),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }


def _write_json_log(stem: str, payload: dict[str, Any]) -> dict[str, str]:
    log_path = LOG_DIR / f"{stem}.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json_log": str(log_path)}


def _quicktalk_device() -> str:
    return os.getenv("OPENTALKING_QUICKTALK_DEVICE", "").strip() or os.getenv("OPENTALKING_TORCH_DEVICE", "").strip() or "cuda:0"


def _normalize_quicktalk_asset_root_for_bridge() -> None:
    raw = os.getenv("OPENTALKING_QUICKTALK_ASSET_ROOT", "").strip()
    if not raw:
        return
    path = Path(raw)
    if path.is_absolute():
        return
    workdir = Path(_resolve_path(os.getenv("OPENTALKING_WORKDIR", str(ROOT / "third_party" / "opentalking"))))
    candidates = [
        (workdir / raw).resolve(),
        (ROOT / raw).resolve(),
    ]
    for candidate in candidates:
        if (candidate / "checkpoints").is_dir():
            os.environ["OPENTALKING_QUICKTALK_ASSET_ROOT"] = str(candidate)
            return


def _quicktalk_persistent_enabled(payload: LipsyncPayload, command_template: str) -> bool:
    mode = os.getenv("OPENTALKING_BRIDGE_RENDER_MODE", "persistent").strip().lower()
    if mode in {"subprocess", "process", "command"}:
        return False
    if payload.model.strip().lower() != "quicktalk":
        return False
    marker = "opentalking_quicktalk_gpu_render.py"
    return marker in command_template.replace("\\", "/")


def _ensure_quicktalk_renderer(avatar_dir: str, avatar_image: str) -> tuple[Any, Any, dict[str, Any]]:
    global _QUICKTALK_ADAPTER, _QUICKTALK_AVATAR_STATE, _QUICKTALK_RENDERER_KEY

    _normalize_quicktalk_asset_root_for_bridge()
    device = _quicktalk_device()
    avatar_digest = _avatar_bundle_digest(avatar_dir, avatar_image)
    key = (avatar_dir, avatar_image, avatar_digest, device)
    if _QUICKTALK_ADAPTER is not None and _QUICKTALK_AVATAR_STATE is not None and _QUICKTALK_RENDERER_KEY == key:
        return _QUICKTALK_ADAPTER, _QUICKTALK_AVATAR_STATE, {"renderer_cached": True, "device": device}

    from opentalking.models.quicktalk.adapter import QuickTalkAdapter

    started = time.perf_counter()
    adapter = QuickTalkAdapter()
    adapter.load_model(device)
    avatar_state = adapter.load_avatar(avatar_dir)
    _QUICKTALK_ADAPTER = adapter
    _QUICKTALK_AVATAR_STATE = avatar_state
    _QUICKTALK_RENDERER_KEY = key
    return adapter, avatar_state, {
        "renderer_cached": False,
        "device": device,
        "load_seconds": round(time.perf_counter() - started, 3),
    }


def _render_quicktalk_persistent(audio_path: str, avatar_dir: str, avatar_image: str, output_path: Path) -> dict[str, Any]:
    from scripts.opentalking_quicktalk_gpu_render import _read_wav_i16, _video_stats, _write_video

    started = time.perf_counter()
    with _QUICKTALK_LOCK:
        adapter, avatar_state, load_info = _ensure_quicktalk_renderer(avatar_dir, avatar_image)
        avatar_state.frame_index = 0
        if hasattr(avatar_state, "worker") and hasattr(avatar_state.worker, "make_state"):
            avatar_state.session_state = avatar_state.worker.make_state()

        max_seconds = float(os.getenv("OPENTALKING_QUICKTALK_MAX_SECONDS", "0") or "0")
        audio_chunk = _read_wav_i16(Path(audio_path), max_seconds=max_seconds)
        feature_started = time.perf_counter()
        features = adapter.extract_features_for_stream(audio_chunk, avatar_state)
        infer_started = time.perf_counter()
        predictions = adapter.infer(features, avatar_state)
        frames = [
            adapter.compose_frame(avatar_state, index, prediction).data
            for index, prediction in enumerate(predictions)
        ]
        fps = float(max(1, int(avatar_state.fps)))
        _write_video(frames, fps, Path(audio_path), output_path)
        stats = _video_stats(output_path)

    if not stats["opened"] or not stats["first_frame"] or int(stats["frames"]) <= 0:
        raise RuntimeError(f"Generated video is not playable: {output_path}")

    return {
        "render_mode": "persistent-quicktalk",
        **load_info,
        "feature_seconds": round(infer_started - feature_started, 3),
        "render_seconds": round(time.perf_counter() - infer_started, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "prediction_frames": len(frames),
        "fps": fps,
        **stats,
    }


def _warm_quicktalk_renderer() -> None:
    global _QUICKTALK_WARMING, _QUICKTALK_WARMED, _QUICKTALK_WARMUP_ERROR
    if os.getenv("OPENTALKING_WARMUP", "1").strip().lower() in {"0", "false", "no"}:
        return
    command_template = os.getenv("OPENTALKING_INFER_COMMAND", "").strip()
    payload = LipsyncPayload(model=os.getenv("OPENTALKING_MODEL", "quicktalk"))
    if not _quicktalk_persistent_enabled(payload, command_template):
        return
    avatar_dir = _resolve_path(os.getenv("OPENTALKING_AVATAR_DIR", ""))
    avatar_image = _resolve_path(os.getenv("OPENTALKING_AVATAR_IMAGE", ""))
    if not avatar_dir or not Path(avatar_dir).exists() or not avatar_image or not Path(avatar_image).exists():
        return
    _QUICKTALK_WARMING = True
    _QUICKTALK_WARMUP_ERROR = ""
    try:
        with _QUICKTALK_LOCK:
            _ensure_quicktalk_renderer(avatar_dir, avatar_image)
        _QUICKTALK_WARMED = True
    except Exception as exc:  # noqa: BLE001
        _QUICKTALK_WARMUP_ERROR = str(exc)
    finally:
        _QUICKTALK_WARMING = False


@app.on_event("startup")
def _start_quicktalk_warmup() -> None:
    thread = threading.Thread(target=_warm_quicktalk_renderer, name="quicktalk-warmup", daemon=True)
    thread.start()


def _kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return
    subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)


def _run_render_command(command: str, cwd: str, env: dict[str, str], timeout: int, stem: str) -> subprocess.CompletedProcess[str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        logs = _write_render_log(stem, command, cwd, timeout, stdout or "", stderr or "")
        raise HTTPException(
            status_code=504,
            detail={
                "message": f"OpenTalking 推理超时 {timeout} 秒，已终止渲染子进程。",
                "logs": logs,
                "stdout_tail": _tail(stdout or ""),
                "stderr_tail": _tail(stderr or ""),
            },
        ) from None
    logs = _write_render_log(stem, command, cwd, timeout, stdout or "", stderr or "")
    completed = subprocess.CompletedProcess(command, proc.returncode or 0, stdout or "", stderr or "")
    completed.logs = logs  # type: ignore[attr-defined]
    return completed


@app.get("/api/health")
def health() -> dict[str, Any]:
    command = os.getenv("OPENTALKING_INFER_COMMAND", "").strip()
    model = os.getenv("OPENTALKING_MODEL", "quicktalk").strip() or "quicktalk"
    persistent_enabled = _quicktalk_persistent_enabled(LipsyncPayload(model=model), command)
    return {
        "ok": True,
        "command_configured": bool(command),
        "command": command,
        "render_mode": "persistent-quicktalk" if persistent_enabled else "subprocess-command",
        "persistent_quicktalk_warming": _QUICKTALK_WARMING,
        "persistent_quicktalk_warmed": _QUICKTALK_WARMED,
        "persistent_quicktalk_loaded": _QUICKTALK_ADAPTER is not None and _QUICKTALK_AVATAR_STATE is not None,
        "persistent_quicktalk_error": _QUICKTALK_WARMUP_ERROR,
        "avatar_dir": _resolve_path(os.getenv("OPENTALKING_AVATAR_DIR", "")),
        "workdir": os.getenv("OPENTALKING_WORKDIR", str(ROOT / "third_party" / "opentalking")),
        "output_dir": str(OUTPUT_DIR),
        "render_log_dir": str(LOG_DIR),
    }


@app.post("/api/lipsync")
def lipsync(payload: LipsyncPayload) -> dict[str, Any]:
    command_template = os.getenv("OPENTALKING_INFER_COMMAND", "").strip()
    if not command_template:
        raise HTTPException(
            status_code=503,
            detail="OPENTALKING_INFER_COMMAND 未配置，请先配置 QuickTalk/Wav2Lip/FlashTalk 推理命令。",
        )

    audio_path = _resolve_path(payload.audio_path)
    avatar_image = _resolve_path(payload.avatar_image)
    avatar_dir = _resolve_path(os.getenv("OPENTALKING_AVATAR_DIR", ""))
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(status_code=400, detail="未收到可读取的音频文件路径。")
    if not avatar_image or not Path(avatar_image).exists():
        raise HTTPException(status_code=400, detail="未收到可读取的授权数字人形象图片。")

    output_path = _cached_output_path(payload, audio_path, avatar_dir, command_template, avatar_image)
    if output_path.exists() and output_path.stat().st_size > 0:
        return {
            "ok": True,
            "status": "completed",
            "video_url": f"/outputs/{output_path.name}",
            "video_path": str(output_path),
            "model": payload.model,
            "cached": True,
        }

    if _quicktalk_persistent_enabled(payload, command_template):
        log_stem = f"opentalking-persistent-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{output_path.stem}"
        try:
            stats = _render_quicktalk_persistent(audio_path, avatar_dir, avatar_image, output_path)
        except Exception as exc:  # noqa: BLE001
            logs = _write_json_log(
                log_stem,
                {
                    "message": "Persistent QuickTalk render failed.",
                    "error": str(exc),
                    "audio_path": audio_path,
                    "avatar_dir": avatar_dir,
                    "avatar_image": avatar_image,
                    "output_path": str(output_path),
                },
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "OpenTalking QuickTalk 持久渲染失败。",
                    "logs": logs,
                    "error": str(exc),
                },
            ) from exc
        logs = _write_json_log(log_stem, stats)
        return {
            "ok": True,
            "status": "completed",
            "video_url": f"/outputs/{output_path.name}",
            "video_path": str(output_path),
            "model": payload.model,
            "cached": False,
            "render_mode": "persistent-quicktalk",
            "render_stats": stats,
            "logs": logs,
        }

    command = command_template.format(
        audio=audio_path,
        image=avatar_image,
        avatar=avatar_dir,
        text=payload.text.replace('"', '\\"'),
        output=str(output_path),
        model=payload.model,
        python=sys.executable,
        pythonq=f'"{sys.executable}"',
    )
    env = os.environ.copy()
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    timeout = int(os.getenv("OPENTALKING_INFER_TIMEOUT", "180"))
    cwd = os.getenv("OPENTALKING_WORKDIR", str(ROOT / "third_party" / "opentalking"))
    log_stem = f"opentalking-render-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{output_path.stem}"
    result = _run_render_command(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        stem=log_stem,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "OpenTalking 推理命令执行失败。",
                "logs": getattr(result, "logs", {}),
                "stdout_tail": _tail(result.stdout),
                "stderr_tail": _tail(result.stderr),
            },
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="OpenTalking 推理命令已结束，但没有生成视频文件。")
    return {
        "ok": True,
        "status": "completed",
        "video_url": f"/outputs/{output_path.name}",
        "video_path": str(output_path),
        "model": payload.model,
        "cached": False,
    }
