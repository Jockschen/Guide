from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from typing import Any, Protocol

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from .opentalking_session import (
    ActiveProfilePayload,
    OpenTalkingClientError,
    OpenTalkingSessionClient,
)


MAX_AUDIO_BYTES = 15 * 1024 * 1024


class SessionClient(Protocol):
    async def capability(self, profile: ActiveProfilePayload): ...
    async def create_session(self, profile: ActiveProfilePayload, *, user_id: str | None = None): ...
    async def get_session(self, session_id: str): ...
    async def upload_audio(
        self,
        session_id: str,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
    ): ...
    async def offer(self, session_id: str, *, sdp: str, offer_type: str = "offer"): ...
    async def interrupt(self, session_id: str): ...
    async def delete_session(self, session_id: str): ...
    def stream_events(self, session_id: str): ...


ProfileLoader = Callable[[], Mapping[str, Any]]
ClientFactory = Callable[[], SessionClient]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_profile() -> Mapping[str, Any]:
    try:
        from .admin_competition import get_active_digital_human_profile

        profile = get_active_digital_human_profile()
        if profile:
            return profile
    except (ImportError, LookupError, RuntimeError, ValueError):
        pass
    return {
        "opentalking_avatar_id": os.environ.get(
            "OPENTALKING_SESSION_AVATAR_ID",
            "lingjing-guide-quicktalk",
        ),
        "opentalking_model": os.environ.get("OPENTALKING_SESSION_MODEL", "quicktalk"),
    }


def _default_client() -> SessionClient:
    base_url = os.environ.get("OPENTALKING_SESSION_BASE_URL", "http://127.0.0.1:8210")
    timeout = float(os.environ.get("OPENTALKING_SESSION_TIMEOUT_SECONDS", "45"))
    token = os.environ.get("OPENTALKING_API_TOKEN", "").strip()
    return OpenTalkingSessionClient(
        base_url,
        timeout=timeout,
        event_timeout=max(timeout, 60.0),
        headers={"Authorization": f"Bearer {token}"} if token else None,
        secret_values=[token] if token else [],
    )


def _upstream_error(exc: OpenTalkingClientError) -> HTTPException:
    status_code = exc.status_code if exc.status_code and 400 <= exc.status_code < 500 else 503
    return HTTPException(
        status_code=status_code,
        detail={
            "code": "avatar_session_unavailable",
            "operation": exc.operation,
            "retryable": exc.retryable,
            "message": str(exc),
        },
    )


def create_avatar_session_router(
    *,
    profile_loader: ProfileLoader | None = None,
    client_factory: ClientFactory | None = None,
    enabled: bool | None = None,
    session_stt_provider: str | None = None,
    session_tts_provider: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/avatar", tags=["avatar-session"])
    load_profile = profile_loader or _default_profile
    make_client = client_factory or _default_client
    session_enabled = _env_bool("OPENTALKING_SESSION_ENABLED", True) if enabled is None else enabled
    stt_provider = session_stt_provider or os.environ.get("OPENTALKING_SESSION_STT_PROVIDER", "funasr")
    tts_provider = session_tts_provider or os.environ.get("OPENTALKING_SESSION_TTS_PROVIDER", "edge")

    def profile() -> ActiveProfilePayload:
        try:
            return ActiveProfilePayload.from_mapping(
                load_profile(),
                session_stt_provider=stt_provider,
                session_tts_provider=tts_provider,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "avatar_profile_invalid",
                    "message": str(exc),
                },
            ) from exc

    def require_enabled() -> None:
        if not session_enabled:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "avatar_session_disabled",
                    "message": "实时数字人暂不可用，讲解与文字问答仍可继续。",
                },
            )

    @router.get("/session-capability")
    async def session_capability() -> dict[str, Any]:
        selected = profile()
        if not session_enabled:
            data = {
                "provider": "session",
                "available": False,
                "preferred": True,
                "transport": "webrtc",
                "model": selected.model,
                "avatar_id": selected.avatar_id,
                "reason": "disabled",
            }
        else:
            try:
                data = (await make_client().capability(selected)).to_dict()
            except OpenTalkingClientError as exc:
                data = {
                    "provider": "session",
                    "available": False,
                    "preferred": True,
                    "transport": "webrtc",
                    "model": selected.model,
                    "avatar_id": selected.avatar_id,
                    "reason": str(exc),
                }
        data["fallback_order"] = ["session", "remote", "legacy_mp4", "audio_only"]
        return {"ok": True, "data": data}

    @router.post("/sessions")
    async def create_session(
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        require_enabled()
        selected = profile()
        client_id = str(body.get("client_id") or request.headers.get("x-visitor-id") or "").strip()
        try:
            result = await make_client().create_session(selected, user_id=client_id or None)
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {
            "ok": True,
            "data": {
                "session_id": result.session_id,
                "status": result.status,
                "transport": "webrtc",
                "model": selected.model,
                "avatar_id": selected.avatar_id,
                "app_defaults": selected.app_defaults(),
            },
        }

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        require_enabled()
        try:
            data = await make_client().get_session(session_id)
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {"ok": True, "data": data}

    @router.post("/sessions/{session_id}/audio")
    async def upload_audio(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        require_enabled()
        audio = await file.read(MAX_AUDIO_BYTES + 1)
        if not audio:
            raise HTTPException(status_code=400, detail="音频内容为空。")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="单段讲解音频不能超过 15MB。")
        try:
            result = await make_client().upload_audio(
                session_id,
                audio,
                filename=file.filename or "speech.wav",
                content_type=file.content_type or "application/octet-stream",
            )
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {"ok": True, "data": {"session_id": result.session_id, "status": result.status}}

    @router.post("/sessions/{session_id}/webrtc/offer")
    async def webrtc_offer(session_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        require_enabled()
        sdp = str(body.get("sdp") or "")
        offer_type = str(body.get("type") or "offer")
        if not sdp:
            raise HTTPException(status_code=422, detail="WebRTC offer 缺少 SDP。")
        try:
            answer = await make_client().offer(session_id, sdp=sdp, offer_type=offer_type)
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {"ok": True, "data": {"sdp": answer.sdp, "type": answer.type}}

    @router.post("/sessions/{session_id}/interrupt")
    async def interrupt(session_id: str) -> dict[str, Any]:
        require_enabled()
        try:
            result = await make_client().interrupt(session_id)
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {"ok": True, "data": {"session_id": result.session_id, "status": result.status}}

    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, Any]:
        require_enabled()
        try:
            result = await make_client().delete_session(session_id)
        except OpenTalkingClientError as exc:
            raise _upstream_error(exc) from exc
        return {"ok": True, "data": {"session_id": result.session_id, "status": result.status}}

    @router.get("/sessions/{session_id}/events")
    async def events(session_id: str) -> StreamingResponse:
        require_enabled()
        client = make_client()

        async def stream():
            try:
                async for chunk in client.stream_events(session_id):
                    yield chunk
            except OpenTalkingClientError as exc:
                message = str(exc).replace("\n", " ")
                payload = json.dumps({"message": message}, ensure_ascii=False)
                yield f"event: session.error\ndata: {payload}\n\n".encode("utf-8")

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return router
