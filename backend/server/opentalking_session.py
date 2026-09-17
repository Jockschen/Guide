from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
import json
import re
from typing import Any, AsyncIterator, Callable, Mapping, Protocol, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import uuid


def _first_text(source: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


@dataclass(frozen=True, slots=True)
class ActiveProfilePayload:
    """Published product profile translated to OpenTalking's session schema."""

    avatar_id: str
    model: str = "quicktalk"
    persona_id: str | None = None
    stt_provider: str = "funasr"
    tts_provider: str = "edge"
    published_tts_provider: str | None = None
    tts_voice: str | None = None
    tts_model: str | None = None
    llm_system_prompt: str | None = None

    def __post_init__(self) -> None:
        if not self.avatar_id.strip():
            raise ValueError("active profile must provide an OpenTalking avatar id")

    @classmethod
    def from_mapping(
        cls,
        profile: Mapping[str, Any],
        *,
        session_stt_provider: str | None = None,
        session_tts_provider: str | None = None,
    ) -> "ActiveProfilePayload":
        avatar_id = _first_text(profile, "opentalking_avatar_id", "avatar_id")
        if not avatar_id:
            raise ValueError("active profile must provide an OpenTalking avatar id")
        return cls(
            avatar_id=avatar_id,
            model=_first_text(profile, "opentalking_model", "model") or "quicktalk",
            persona_id=_first_text(profile, "opentalking_persona_id", "persona_id"),
            stt_provider=(
                (session_stt_provider or "").strip()
                or _first_text(profile, "opentalking_session_stt_provider", "session_stt_provider")
                or "funasr"
            ),
            tts_provider=(
                (session_tts_provider or "").strip()
                or _first_text(profile, "opentalking_session_tts_provider", "session_tts_provider")
                or "edge"
            ),
            published_tts_provider=_first_text(profile, "tts_provider"),
            tts_voice=_first_text(profile, "tts_voice", "voice", "voice_id"),
            tts_model=_first_text(profile, "tts_model"),
            llm_system_prompt=_first_text(profile, "llm_system_prompt", "persona"),
        )

    def to_session_payload(self, *, user_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "avatar_id": self.avatar_id,
            "model": self.model,
        }
        optional = {
            "persona_id": self.persona_id,
            "user_id": user_id.strip() if user_id and user_id.strip() else None,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        payload.update(
            {
                "stt_provider": self.stt_provider,
                "tts_provider": self.tts_provider,
                "agent_enabled": False,
                "memory_enabled": False,
                "knowledge_enabled": False,
            }
        )
        return payload

    def app_defaults(self) -> dict[str, str | None]:
        """Published voice/persona retained for the product TTS/Qwen layer."""

        return {
            "tts_provider": self.published_tts_provider,
            "voice": self.tts_voice,
            "tts_model": self.tts_model,
            "persona": self.llm_system_prompt,
        }


@dataclass(frozen=True, slots=True)
class UploadPart:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class AsyncStreamResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    async def read(self) -> bytes: ...

    def iter_bytes(self) -> AsyncIterator[bytes]: ...


class AsyncHTTPTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, UploadPart] | None = None,
    ) -> HTTPResponse: ...

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> AbstractAsyncContextManager[AsyncStreamResponse]: ...


def _response_headers(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except AttributeError:
        return {}


def _multipart_body(files: Mapping[str, UploadPart]) -> tuple[bytes, str]:
    boundary = f"----lingjing-{uuid.uuid4().hex}"
    pieces: list[bytes] = []
    for field_name, part in files.items():
        safe_field = field_name.replace('"', "").replace("\r", "").replace("\n", "")
        safe_filename = part.filename.replace('"', "").replace("\r", "").replace("\n", "")
        pieces.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                (
                    f'Content-Disposition: form-data; name="{safe_field}"; '
                    f'filename="{safe_filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {part.content_type}\r\n\r\n".encode("ascii"),
                part.content,
                b"\r\n",
            ]
        )
    pieces.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


class _UrllibStreamResponse:
    def __init__(self, response: Any, *, chunk_size: int = 64 * 1024) -> None:
        self._response = response
        self._chunk_size = chunk_size
        self.status_code = int(getattr(response, "status", getattr(response, "code", 200)))
        self.headers = _response_headers(response)

    async def read(self) -> bytes:
        return await asyncio.to_thread(self._response.read)

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        while True:
            chunk = await asyncio.to_thread(self._response.read, self._chunk_size)
            if not chunk:
                break
            yield bytes(chunk)

    async def close(self) -> None:
        await asyncio.to_thread(self._response.close)


class _UrllibStreamContext(AbstractAsyncContextManager[_UrllibStreamResponse]):
    def __init__(
        self,
        opener: Callable[..., Any],
        request: urllib_request.Request,
        timeout: float,
    ) -> None:
        self._opener = opener
        self._request = request
        self._timeout = timeout
        self._stream: _UrllibStreamResponse | None = None

    async def __aenter__(self) -> _UrllibStreamResponse:
        try:
            response = await asyncio.to_thread(self._opener, self._request, timeout=self._timeout)
        except urllib_error.HTTPError as exc:
            response = exc
        self._stream = _UrllibStreamResponse(response)
        return self._stream

    async def __aexit__(self, *args: object) -> None:
        if self._stream is not None:
            await self._stream.close()


class UrllibAsyncTransport:
    """Small stdlib async adapter; callers can inject another transport in tests."""

    def __init__(self, *, opener: Callable[..., Any] = urllib_request.urlopen) -> None:
        self._opener = opener

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, UploadPart] | None = None,
    ) -> HTTPResponse:
        request_headers = dict(headers)
        body: bytes | None = None
        if json_body is not None and files is not None:
            raise ValueError("a request cannot contain both JSON and files")
        if json_body is not None:
            body = json.dumps(dict(json_body), ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif files is not None:
            body, content_type = _multipart_body(files)
            request_headers.setdefault("Content-Type", content_type)
        request = urllib_request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )

        def perform() -> HTTPResponse:
            try:
                with self._opener(request, timeout=timeout) as response:
                    return HTTPResponse(
                        status_code=int(getattr(response, "status", 200)),
                        headers=_response_headers(response),
                        body=response.read(),
                    )
            except urllib_error.HTTPError as exc:
                try:
                    response_body = exc.read()
                finally:
                    exc.close()
                return HTTPResponse(
                    status_code=int(exc.code),
                    headers=_response_headers(exc),
                    body=response_body,
                )

        return await asyncio.to_thread(perform)

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> AbstractAsyncContextManager[AsyncStreamResponse]:
        request = urllib_request.Request(url, headers=dict(headers), method=method.upper())
        return _UrllibStreamContext(self._opener, request, timeout)


@dataclass(frozen=True, slots=True)
class SessionResult:
    session_id: str
    status: str


@dataclass(frozen=True, slots=True)
class WebRTCAnswer:
    sdp: str
    type: str


@dataclass(frozen=True, slots=True)
class OpenTalkingHealth:
    status: str
    default_model: str | None
    quicktalk_backend: str | None
    quicktalk_device: str | None
    raw: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True, slots=True)
class SessionCapability:
    available: bool
    model: str | None
    avatar_id: str | None
    reason: str | None = None
    provider: str = "session"
    preferred: bool = True
    transport: str = "webrtc"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "available": self.available,
            "preferred": self.preferred,
            "transport": self.transport,
            "model": self.model,
            "avatar_id": self.avatar_id,
            "reason": self.reason,
        }


class OpenTalkingClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.retryable = retryable


_SENSITIVE_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret|token)"
)


class OpenTalkingSessionClient:
    """Typed async client for the vendored OpenTalking official session API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        event_timeout: float = 45.0,
        headers: Mapping[str, str] | None = None,
        secret_values: Sequence[str] = (),
        transport: AsyncHTTPTransport | None = None,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        parsed = urllib_parse.urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("OpenTalking base URL must be an absolute HTTP(S) URL")
        if timeout <= 0 or event_timeout <= 0:
            raise ValueError("OpenTalking timeouts must be positive")
        self._base_url = normalized
        self._timeout = float(timeout)
        self._event_timeout = float(event_timeout)
        self._headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self._transport = transport or UrllibAsyncTransport()
        self._secret_values = self._collect_secrets(parsed, secret_values)

    def _collect_secrets(
        self,
        parsed_url: urllib_parse.SplitResult,
        provided: Sequence[str],
    ) -> tuple[str, ...]:
        values = {str(value) for value in provided if str(value)}
        if parsed_url.password:
            values.add(parsed_url.password)
        for key, value in urllib_parse.parse_qsl(parsed_url.query, keep_blank_values=True):
            if value and _SENSITIVE_KEY.search(key):
                values.add(value)
        for key, value in self._headers.items():
            if value and _SENSITIVE_KEY.search(key):
                values.add(value)
                if value.lower().startswith("bearer "):
                    values.add(value[7:].strip())
        return tuple(sorted(values, key=len, reverse=True))

    def _redact(self, value: object) -> str:
        text = str(value)
        for secret in self._secret_values:
            text = text.replace(secret, "[redacted]")
        text = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+", r"\1[redacted]", text)
        text = re.sub(
            r"(?i)([?&](?:api[_-]?key|access[_-]?token|password|secret|token)=)[^&#\s]+",
            r"\1[redacted]",
            text,
        )
        text = re.sub(r"(https?://)[^/@\s:]+:[^/@\s]+@", r"\1[redacted]@", text)
        text = re.sub(
            r'(?i)(["\'](?:api[_-]?key|access[_-]?token|authorization|password|secret|token)["\']\s*:\s*["\'])[^"\']+',
            r"\1[redacted]",
            text,
        )
        return text

    def _url(self, path: str) -> str:
        parsed = urllib_parse.urlsplit(self._base_url)
        combined_path = f"{parsed.path.rstrip('/')}/{path.lstrip('/')}"
        return urllib_parse.urlunsplit(
            (parsed.scheme, parsed.netloc, combined_path, parsed.query, "")
        )

    @staticmethod
    def _session_path(session_id: str) -> str:
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be empty")
        return urllib_parse.quote(normalized, safe="")

    def _error_detail(self, response: HTTPResponse) -> str:
        body_text = response.body.decode("utf-8", errors="replace")[:1000]
        try:
            payload = json.loads(body_text)
        except (json.JSONDecodeError, TypeError):
            detail = body_text.strip() or "upstream request failed"
        else:
            if isinstance(payload, Mapping):
                detail = payload.get("detail") or payload.get("message") or payload
            else:
                detail = payload
            if not isinstance(detail, str):
                detail = json.dumps(detail, ensure_ascii=False)
        return self._redact(detail)

    def _http_error(self, operation: str, response: HTTPResponse) -> OpenTalkingClientError:
        detail = self._error_detail(response)
        return OpenTalkingClientError(
            f"OpenTalking {operation} failed (HTTP {response.status_code}): {detail}",
            operation=operation,
            status_code=response.status_code,
            retryable=response.status_code == 429 or response.status_code >= 500,
        )

    async def _request_object(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, UploadPart] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._transport.request(
                method,
                self._url(path),
                headers=self._headers,
                timeout=self._timeout,
                json_body=json_body,
                files=files,
            )
        except OpenTalkingClientError:
            raise
        except Exception as exc:
            detail = self._redact(exc) or type(exc).__name__
            raise OpenTalkingClientError(
                f"OpenTalking {operation} failed: {detail}",
                operation=operation,
                retryable=True,
            ) from exc
        if not 200 <= response.status_code < 300:
            raise self._http_error(operation, response)
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenTalkingClientError(
                f"OpenTalking {operation} returned invalid JSON",
                operation=operation,
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise OpenTalkingClientError(
                f"OpenTalking {operation} returned a non-object response",
                operation=operation,
                status_code=response.status_code,
            )
        return payload

    @staticmethod
    def _session_result(payload: Mapping[str, Any], operation: str) -> SessionResult:
        session_id = str(payload.get("session_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not session_id or not status:
            raise OpenTalkingClientError(
                f"OpenTalking {operation} response is missing session_id or status",
                operation=operation,
            )
        return SessionResult(session_id=session_id, status=status)

    async def health(self) -> OpenTalkingHealth:
        payload = await self._request_object("health", "GET", "/health")
        return OpenTalkingHealth(
            status=str(payload.get("status") or "unknown"),
            default_model=_first_text(payload, "default_model"),
            quicktalk_backend=_first_text(payload, "quicktalk_backend"),
            quicktalk_device=_first_text(payload, "quicktalk_device"),
            raw=payload,
        )

    async def capability(
        self,
        profile: ActiveProfilePayload | None = None,
    ) -> SessionCapability:
        try:
            health = await self.health()
        except OpenTalkingClientError as exc:
            return SessionCapability(
                available=False,
                model=profile.model if profile else None,
                avatar_id=profile.avatar_id if profile else None,
                reason=str(exc),
            )
        available = health.status.lower() == "ok"
        return SessionCapability(
            available=available,
            model=profile.model if profile else health.default_model,
            avatar_id=profile.avatar_id if profile else None,
            reason=None if available else f"OpenTalking health status is {health.status}",
        )

    async def create_session(
        self,
        profile: ActiveProfilePayload,
        *,
        user_id: str | None = None,
    ) -> SessionResult:
        payload = await self._request_object(
            "create_session",
            "POST",
            "/sessions",
            json_body=profile.to_session_payload(user_id=user_id),
        )
        return self._session_result(payload, "create_session")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        sid = self._session_path(session_id)
        return await self._request_object("get_session", "GET", f"/sessions/{sid}")

    async def delete_session(self, session_id: str) -> SessionResult:
        sid = self._session_path(session_id)
        payload = await self._request_object("delete_session", "DELETE", f"/sessions/{sid}")
        return self._session_result(payload, "delete_session")

    async def upload_audio(
        self,
        session_id: str,
        audio: bytes,
        *,
        filename: str = "speech.wav",
        content_type: str = "audio/wav",
    ) -> SessionResult:
        if not audio:
            raise ValueError("audio must not be empty")
        sid = self._session_path(session_id)
        payload = await self._request_object(
            "upload_audio",
            "POST",
            f"/sessions/{sid}/speak_flashtalk_audio",
            files={
                "file": UploadPart(
                    filename=filename,
                    content=bytes(audio),
                    content_type=content_type,
                )
            },
        )
        return self._session_result(payload, "upload_audio")

    async def offer(
        self,
        session_id: str,
        *,
        sdp: str,
        offer_type: str = "offer",
    ) -> WebRTCAnswer:
        sid = self._session_path(session_id)
        payload = await self._request_object(
            "webrtc_offer",
            "POST",
            f"/sessions/{sid}/webrtc/offer",
            json_body={"sdp": sdp, "type": offer_type},
        )
        answer_sdp = str(payload.get("sdp") or "")
        answer_type = str(payload.get("type") or "")
        if not answer_sdp or not answer_type:
            raise OpenTalkingClientError(
                "OpenTalking webrtc_offer response is missing sdp or type",
                operation="webrtc_offer",
            )
        return WebRTCAnswer(sdp=answer_sdp, type=answer_type)

    async def interrupt(self, session_id: str) -> SessionResult:
        sid = self._session_path(session_id)
        payload = await self._request_object(
            "interrupt",
            "POST",
            f"/sessions/{sid}/interrupt",
        )
        return self._session_result(payload, "interrupt")

    async def stream_events(self, session_id: str) -> AsyncIterator[bytes]:
        sid = self._session_path(session_id)
        headers = {**self._headers, "Accept": "text/event-stream"}
        try:
            async with self._transport.stream(
                "GET",
                self._url(f"/sessions/{sid}/events"),
                headers=headers,
                timeout=self._event_timeout,
            ) as response:
                if not 200 <= response.status_code < 300:
                    body = await response.read()
                    raise self._http_error(
                        "stream_events",
                        HTTPResponse(
                            status_code=response.status_code,
                            headers=response.headers,
                            body=body,
                        ),
                    )
                async for chunk in response.iter_bytes():
                    yield chunk
        except OpenTalkingClientError:
            raise
        except Exception as exc:
            detail = self._redact(exc) or type(exc).__name__
            raise OpenTalkingClientError(
                f"OpenTalking stream_events failed: {detail}",
                operation="stream_events",
                retryable=True,
            ) from exc
