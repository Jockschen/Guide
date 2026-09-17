from __future__ import annotations

import base64
from datetime import datetime
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
import uuid

from .config import ROOT, settings
from .voice import estimate_visemes


def _avatar_video_dir() -> Path:
    path = settings.storage_dir / "avatar-video"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _audio_path_from_url(audio_url: str | None) -> str:
    if not audio_url or not audio_url.startswith("/static/audio/"):
        return ""
    filename = Path(audio_url).name
    path = settings.storage_dir / "audio" / filename
    return str(path) if path.exists() else ""


def _public_url(path: Path) -> str:
    return f"/static/avatar-video/{path.name}"


def _path_public_url(path: Path) -> str:
    resolved = path.resolve()
    for root, prefix in [(settings.storage_dir.resolve(), "/static"), ((ROOT / "public").resolve(), "")]:
        try:
            relative = resolved.relative_to(root)
            return f"{prefix}/{relative.as_posix()}".replace("//", "/")
        except ValueError:
            continue
    return ""


def _configured_demo_video() -> tuple[str, str]:
    raw_value = os.getenv("OPENTALKING_DEMO_VIDEO", "").strip()
    label = os.getenv("OPENTALKING_DEMO_LABEL", "预生成真实口型片段").strip() or "预生成真实口型片段"
    if not raw_value:
        return "", label
    if raw_value.startswith(("http://", "https://", "/static/", "/assets/")):
        return raw_value, label
    path = Path(raw_value)
    if not path.is_absolute():
        path = ROOT / path
    return (_path_public_url(path) if path.exists() and path.is_file() else ""), label


def demo_video_status() -> dict[str, Any]:
    video_url, label = _configured_demo_video()
    return {
        "demo_video_configured": bool(os.getenv("OPENTALKING_DEMO_VIDEO", "").strip()),
        "demo_video_ready": bool(video_url),
        "demo_video_url": video_url,
        "demo_video_label": label,
    }


def build_driver_metadata(provider: str, status: str, video_url: str = "", message: str = "") -> dict[str, Any]:
    provider_value = provider or "2d-fallback"
    status_value = status or "fallback"
    has_video = bool(video_url)
    if provider_value == "opentalking-demo":
        mode = "demo_video"
        label = "演示片段"
        claim = "demo_lipsync_clip"
        acceptance = "demo_video_marked"
        requires_external_service = False
    elif provider_value == "opentalking":
        mode = "real_video"
        label = "实时口型"
        claim = "real_lipsync_video" if has_video else "real_lipsync_ready"
        acceptance = "opentalking_video_ready" if has_video else "opentalking_service_ready"
        requires_external_service = True
    else:
        mode = "audio_2d"
        label = "音频驱动"
        claim = "audio_driven_stage"
        acceptance = "fallback_viseme_timeline"
        requires_external_service = False
    return {
        "mode": mode,
        "label": label,
        "claim": claim,
        "status": status_value,
        "provider": provider_value,
        "video_playable": has_video,
        "claim_real_lipsync": provider_value == "opentalking" and has_video,
        "requires_external_service": requires_external_service,
        "acceptance": acceptance,
        "message": message,
    }


def _demo_video_result(text: str, message: str) -> dict[str, Any]:
    video_url, label = _configured_demo_video()
    return {
        "provider": "opentalking-demo",
        "status": "demo-video",
        "message": message,
        "video_url": video_url,
        "task_id": "",
        "visemes": estimate_visemes(text),
        "driver": build_driver_metadata("opentalking-demo", "demo-video", video_url, message),
        "raw": {"demo_video_label": label},
    }


def _opentalking_error_result(text: str, message: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "provider": "opentalking",
        "status": "error",
        "message": message,
        "video_url": None,
        "task_id": "",
        "visemes": estimate_visemes(text),
        "driver": build_driver_metadata("opentalking", "error", "", message),
        "raw": raw or {},
    }


def _describe_opentalking_exception(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace")
        detail = body
        try:
            payload = json.loads(body)
            raw_detail = payload.get("detail") or payload.get("message") or payload
            detail = json.dumps(raw_detail, ensure_ascii=False) if isinstance(raw_detail, dict) else str(raw_detail)
        except (json.JSONDecodeError, AttributeError):
            detail = body
        return f"HTTP {exc.code}: {detail[-1200:]}"
    return str(exc)


def _demo_fallback_allowed(allow_demo: bool) -> bool:
    env_value = os.getenv("OPENTALKING_DEMO_FALLBACK", "").strip().lower()
    return allow_demo or env_value in {"1", "true", "yes", "on"}


def _save_video_base64(video_base64: str) -> str:
    encoded = video_base64.split(",", 1)[1] if "," in video_base64[:80] else video_base64
    output = _avatar_video_dir() / f"opentalking-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}.mp4"
    output.write_bytes(base64.b64decode(encoded))
    return _public_url(output)


def _copy_video_path(video_path: str) -> str:
    source = Path(video_path)
    if not source.is_absolute():
        source = ROOT / source
    if not source.exists():
        return ""
    output = _avatar_video_dir() / f"opentalking-{datetime.now().strftime('%Y%m%d%H%M%S')}-{source.name}"
    shutil.copy2(source, output)
    return _public_url(output)


def _absolute_or_remote_url(value: str, base_url: str) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("/static/"):
        return value
    if value.startswith("/"):
        return f"{base_url}{value}"
    return value


def _extract_nested(data: dict[str, Any]) -> dict[str, Any]:
    current = data
    for key in ["data", "result", "output"]:
        nested = current.get(key)
        if isinstance(nested, dict):
            current = nested
    return current


def _normalize_opentalking_result(data: dict[str, Any], base_url: str) -> dict[str, Any]:
    nested = _extract_nested(data)
    export_video = nested.get("export_video") or data.get("export_video")
    export_url = ""
    if isinstance(export_video, dict):
        export_url = str(export_video.get("download_url") or export_video.get("url") or "")
    video_url = (
        nested.get("video_url")
        or nested.get("result_url")
        or nested.get("url")
        or nested.get("video")
        or export_url
        or data.get("video_url")
    )
    video_path = nested.get("video_path") or nested.get("path") or data.get("video_path")
    video_base64 = nested.get("video_base64") or nested.get("video_b64") or data.get("video_base64")

    normalized_url = ""
    if video_base64:
        normalized_url = _save_video_base64(str(video_base64))
    elif video_path:
        normalized_url = _copy_video_path(str(video_path))
    elif video_url:
        normalized_url = _absolute_or_remote_url(str(video_url), base_url)

    task_id = nested.get("task_id") or nested.get("job_id") or nested.get("id") or data.get("task_id")
    status = str(nested.get("status") or data.get("status") or ("ok" if normalized_url else "pending")).lower()
    return {
        "video_url": normalized_url,
        "task_id": str(task_id) if task_id else "",
        "status": status,
        "raw": data,
    }


def _request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload is None:
        request = urllib.request.Request(url, method="GET")
    else:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    timeout_seconds = settings.opentalking_timeout_seconds
    if payload is not None and settings.opentalking_lipsync_path.rstrip("/") == "/api/lipsync":
        try:
            timeout_seconds = max(timeout_seconds, int(os.getenv("OPENTALKING_INFER_TIMEOUT", "0")) + 20)
        except ValueError:
            pass
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _health_endpoint(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url.rstrip('/')}{normalized_path}"


def _read_health(endpoint: str, *, timeout: float = 1.5) -> dict[str, Any]:
    request = urllib.request.Request(endpoint, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw) if raw else {}
    if not isinstance(data, dict):
        raise ValueError("OpenTalking health response must be an object")
    return data


def opentalking_runtime_status() -> dict[str, Any]:
    session_enabled = os.getenv("OPENTALKING_SESSION_ENABLED", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    session_base_url = os.getenv(
        "OPENTALKING_SESSION_BASE_URL",
        "http://127.0.0.1:8210",
    ).strip().rstrip("/")
    session_configured = session_enabled and bool(session_base_url)
    bridge_configured = bool(settings.opentalking_base_url)
    configured = session_configured or bridge_configured
    status = {
        "opentalking_configured": configured,
        "opentalking_ready": False,
        "opentalking_status": "not_configured" if not configured else "unreachable",
        "opentalking_model": settings.opentalking_model,
        "opentalking_provider": "session" if session_configured else "legacy_bridge",
        "opentalking_transport": "webrtc" if session_configured else "mp4",
        "opentalking_session_configured": session_configured,
        "opentalking_session_ready": False,
        **demo_video_status(),
    }
    if not configured:
        return status

    if session_configured:
        session_health_path = (
            os.getenv("OPENTALKING_SESSION_HEALTH_PATH", "/health").strip() or "/health"
        )
        session_endpoint = _health_endpoint(session_base_url, session_health_path)
        try:
            session_health = _read_health(session_endpoint)
            session_state = str(session_health.get("status") or "").strip().lower()
            session_ready = session_state == "ok" or bool(session_health.get("ok"))
            if session_ready:
                return {
                    **status,
                    "opentalking_ready": True,
                    "opentalking_status": "ready",
                    "opentalking_provider": "session",
                    "opentalking_transport": "webrtc",
                    "opentalking_session_ready": True,
                    "opentalking_health": session_health,
                    "opentalking_session_health": session_health,
                }
            status = {
                **status,
                "opentalking_session_health": session_health,
                "opentalking_session_error": (
                    f"OpenTalking session health status is {session_state or 'unknown'}"
                ),
            }
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as exc:
            status = {
                **status,
                "opentalking_session_error": str(exc),
            }

    if not bridge_configured:
        return {
            **status,
            "opentalking_error": status.get("opentalking_session_error", "OpenTalking session unavailable"),
        }

    health_path = os.getenv("OPENTALKING_HEALTH_PATH", "/api/health").strip() or "/api/health"
    endpoint = _health_endpoint(settings.opentalking_base_url, health_path)
    try:
        data = _read_health(endpoint)
        command_configured = data.get("command_configured")
        bridge_mode = settings.opentalking_lipsync_path.rstrip("/") == "/api/lipsync"
        ready = bool(data.get("ok", True)) and (not bridge_mode or command_configured is not False)
        return {
            **status,
            "opentalking_ready": ready,
            "opentalking_status": "ready" if ready else "command_missing",
            "opentalking_provider": "legacy_bridge",
            "opentalking_transport": "mp4",
            "opentalking_health": data,
        }
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        errors = [str(status.get("opentalking_session_error") or "").strip(), str(exc)]
        return {
            **status,
            "opentalking_error": "; ".join(error for error in errors if error),
        }


def _request_multipart(url: str, fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> dict[str, Any]:
    boundary = f"----lingjing{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=settings.opentalking_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _poll_task(base_url: str, task_id: str) -> dict[str, Any]:
    deadline = time.time() + settings.opentalking_timeout_seconds
    result_path = settings.opentalking_result_path.replace("{task_id}", urllib.parse.quote(task_id))
    result_url = f"{base_url}{result_path if result_path.startswith('/') else '/' + result_path}"
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _request_json(result_url)
        normalized = _normalize_opentalking_result(last, base_url)
        if normalized["video_url"] or normalized["status"] in {"ok", "done", "success", "completed", "failed", "error"}:
            return normalized
        time.sleep(settings.opentalking_poll_seconds)
    return _normalize_opentalking_result(last, base_url)


def _request_video_creation_job(base_url: str, endpoint_path: str, payload: dict[str, Any], audio_path: str) -> dict[str, Any]:
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError("OpenTalking 官方视频生成接口需要可读取的音频文件")
    endpoint = f"{base_url}{endpoint_path}"
    fields = {
        "model": str(payload.get("model") or "quicktalk"),
        "avatar_id": str(payload.get("avatar_id") or "lingjing-guide"),
        "audio_source": "upload",
        "title": "灵境导游讲解",
    }
    audio_file = Path(audio_path)
    data = _request_multipart(
        endpoint,
        fields,
        {
            "audio_file": (
                audio_file.name,
                audio_file.read_bytes(),
                "audio/wav" if audio_file.suffix.lower() == ".wav" else "application/octet-stream",
            )
        },
    )
    return _normalize_opentalking_result(data, base_url)


def request_lipsync(text: str, audio_url: str | None = None, allow_demo: bool = False) -> dict[str, Any]:
    demo_allowed = _demo_fallback_allowed(allow_demo)
    demo_ready = demo_video_status()["demo_video_ready"]
    if demo_allowed and demo_ready and not opentalking_runtime_status().get("opentalking_ready"):
        return _demo_video_result(text, "OpenTalking 服务未就绪，已使用预生成真实口型演示片段。")

    audio_path = _audio_path_from_url(audio_url)
    avatar_image = settings.opentalking_avatar_image
    payload = {
        "text": text,
        "audio_url": audio_url,
        "audio_path": audio_path,
        "avatar_id": settings.opentalking_avatar_id,
        "avatar_image": str(avatar_image) if avatar_image.exists() else "",
        "model": settings.opentalking_model,
        "return_video": True,
    }
    if settings.opentalking_base_url:
        base_url = settings.opentalking_base_url
        endpoint_path = settings.opentalking_lipsync_path if settings.opentalking_lipsync_path.startswith("/") else f"/{settings.opentalking_lipsync_path}"
        try:
            if endpoint_path.rstrip("/") == "/video-creation/jobs":
                normalized = _request_video_creation_job(base_url, endpoint_path, payload, audio_path)
            else:
                data = _request_json(f"{base_url}{endpoint_path}", payload)
                normalized = _normalize_opentalking_result(data, base_url)
            if normalized["task_id"] and not normalized["video_url"]:
                normalized = _poll_task(base_url, normalized["task_id"])
            if normalized["video_url"]:
                message = "OpenTalking 真实视频口型已生成"
                return {
                    "provider": "opentalking",
                    "status": "video-ready",
                    "message": message,
                    "video_url": normalized["video_url"],
                    "task_id": normalized["task_id"],
                    "visemes": estimate_visemes(text),
                    "driver": build_driver_metadata("opentalking", "video-ready", normalized["video_url"], message),
                    "raw": normalized["raw"],
                }
            message = "OpenTalking 已接收任务，暂未返回可播放视频"
            return {
                "provider": "opentalking",
                "status": "pending",
                "message": message,
                "task_id": normalized["task_id"],
                "visemes": estimate_visemes(text),
                "driver": build_driver_metadata("opentalking", "pending", "", message),
                "raw": normalized["raw"],
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            if demo_allowed and demo_ready:
                return _demo_video_result(text, f"OpenTalking 服务暂不可用，已使用预生成真实口型演示片段: {exc}")
            detail = _describe_opentalking_exception(exc)
            message = f"OpenTalking 真实口型生成失败，没有使用假的 2D 口型回退: {detail}"
            return _opentalking_error_result(text, message)

    if demo_allowed and demo_ready:
        return _demo_video_result(text, "OpenTalking 服务未配置，已使用预生成真实口型演示片段。")

    message = "外部数字人口型服务未配置，使用标准口型驱动。"
    return {
        "provider": "2d-fallback",
        "status": "fallback",
        "message": message,
        "visemes": estimate_visemes(text),
        "driver": build_driver_metadata("2d-fallback", "fallback", "", message),
    }
