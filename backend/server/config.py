from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_package_dir: Path
    database_path: Path
    storage_dir: Path
    vector_backend: str
    qwen_api_key: str
    qwen_base_url: str
    qwen_model: str
    asr_provider: str
    tts_provider: str
    funasr_base_url: str
    funasr_asr_path: str
    funasr_model_dir: str
    sherpa_onnx_asr_base_url: str
    sherpa_onnx_asr_path: str
    sherpa_onnx_asr_exe: str
    sherpa_onnx_asr_model_dir: str
    sherpa_onnx_asr_command: str
    sherpa_onnx_asr_extra_args: str
    cosyvoice_base_url: str
    cosyvoice_tts_path: str
    cosyvoice_model_dir: str
    piper_exe: str
    piper_model: str
    piper_config: str
    sherpa_onnx_tts_base_url: str
    sherpa_onnx_tts_path: str
    sherpa_onnx_tts_exe: str
    sherpa_onnx_tts_model_dir: str
    sherpa_onnx_tts_command: str
    sherpa_onnx_tts_extra_args: str
    mock_asr_text: str
    vivo_app_id: str
    vivo_app_key: str
    vivo_asr_url: str
    vivo_asr_engine_id: str
    vivo_tts_url: str
    vivo_tts_engine_id: str
    vivo_tts_voice: str
    opentalking_base_url: str
    opentalking_lipsync_path: str
    opentalking_result_path: str
    opentalking_avatar_id: str
    opentalking_avatar_image: Path
    opentalking_model: str
    opentalking_timeout_seconds: int
    opentalking_poll_seconds: float


def _path_from_env(name: str, default: str) -> Path:
    value = os.getenv(name, default)
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def get_settings() -> Settings:
    load_env()
    storage_dir = _path_from_env("STORAGE_DIR", "backend/storage")
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        data_package_dir=_path_from_env("DATA_PACKAGE_DIR", "示范景区公开资料包"),
        database_path=_path_from_env("DATABASE_PATH", "backend/storage/lingjing.db"),
        storage_dir=storage_dir,
        vector_backend=os.getenv("VECTOR_BACKEND", "chroma").lower(),
        qwen_api_key=os.getenv("QWEN_API_KEY", ""),
        qwen_base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/"),
        qwen_model=os.getenv("QWEN_MODEL", "qwen3.5-omni-plus-2026-03-15"),
        asr_provider=os.getenv("ASR_PROVIDER", "funasr"),
        tts_provider=os.getenv("TTS_PROVIDER", "cosyvoice"),
        funasr_base_url=os.getenv("FUNASR_BASE_URL", "").rstrip("/"),
        funasr_asr_path=os.getenv("FUNASR_ASR_PATH", "/api/asr"),
        funasr_model_dir=os.getenv("FUNASR_MODEL_DIR", ""),
        sherpa_onnx_asr_base_url=os.getenv("SHERPA_ONNX_ASR_BASE_URL", "").rstrip("/"),
        sherpa_onnx_asr_path=os.getenv("SHERPA_ONNX_ASR_PATH", "/api/asr"),
        sherpa_onnx_asr_exe=os.getenv("SHERPA_ONNX_ASR_EXE", ""),
        sherpa_onnx_asr_model_dir=os.getenv("SHERPA_ONNX_ASR_MODEL_DIR", ""),
        sherpa_onnx_asr_command=os.getenv("SHERPA_ONNX_ASR_COMMAND", ""),
        sherpa_onnx_asr_extra_args=os.getenv("SHERPA_ONNX_ASR_EXTRA_ARGS", ""),
        cosyvoice_base_url=os.getenv("COSYVOICE_BASE_URL", "").rstrip("/"),
        cosyvoice_tts_path=os.getenv("COSYVOICE_TTS_PATH", "/api/tts"),
        cosyvoice_model_dir=os.getenv("COSYVOICE_MODEL_DIR", ""),
        piper_exe=os.getenv("PIPER_EXE", ""),
        piper_model=os.getenv("PIPER_MODEL", ""),
        piper_config=os.getenv("PIPER_CONFIG", ""),
        sherpa_onnx_tts_base_url=os.getenv("SHERPA_ONNX_TTS_BASE_URL", "").rstrip("/"),
        sherpa_onnx_tts_path=os.getenv("SHERPA_ONNX_TTS_PATH", "/api/tts"),
        sherpa_onnx_tts_exe=os.getenv("SHERPA_ONNX_TTS_EXE", ""),
        sherpa_onnx_tts_model_dir=os.getenv("SHERPA_ONNX_TTS_MODEL_DIR", ""),
        sherpa_onnx_tts_command=os.getenv("SHERPA_ONNX_TTS_COMMAND", ""),
        sherpa_onnx_tts_extra_args=os.getenv("SHERPA_ONNX_TTS_EXTRA_ARGS", ""),
        mock_asr_text=os.getenv("MOCK_ASR_TEXT", "九龙灌浴表演时间是什么？"),
        vivo_app_id=os.getenv("VIVO_APP_ID", ""),
        vivo_app_key=os.getenv("VIVO_APP_KEY", ""),
        vivo_asr_url=os.getenv("VIVO_ASR_URL", "ws://api-ai.vivo.com.cn/asr/v2"),
        vivo_asr_engine_id=os.getenv("VIVO_ASR_ENGINE_ID", "shortasrinput"),
        vivo_tts_url=os.getenv("VIVO_TTS_URL", "wss://api-ai.vivo.com.cn/tts"),
        vivo_tts_engine_id=os.getenv("VIVO_TTS_ENGINE_ID", "short_audio_synthesis_jovi"),
        vivo_tts_voice=os.getenv("VIVO_TTS_VOICE", "yige"),
        opentalking_base_url=os.getenv("OPENTALKING_BASE_URL", "").rstrip("/"),
        opentalking_lipsync_path=os.getenv("OPENTALKING_LIPSYNC_PATH", "/api/lipsync"),
        opentalking_result_path=os.getenv("OPENTALKING_RESULT_PATH", "/api/lipsync/{task_id}"),
        opentalking_avatar_id=os.getenv("OPENTALKING_AVATAR_ID", "lingjing-guide"),
        opentalking_avatar_image=_path_from_env("OPENTALKING_AVATAR_IMAGE", "public/assets/generated/avatar-guide-v2.png"),
        opentalking_model=os.getenv("OPENTALKING_MODEL", "quicktalk"),
        opentalking_timeout_seconds=int(os.getenv("OPENTALKING_TIMEOUT_SECONDS", "45")),
        opentalking_poll_seconds=float(os.getenv("OPENTALKING_POLL_SECONDS", "1.2")),
    )


settings = get_settings()
