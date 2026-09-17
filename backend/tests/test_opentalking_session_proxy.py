from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
import sys
from typing import Any, AsyncIterator, Mapping
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.opentalking_session import (
    ActiveProfilePayload,
    HTTPResponse,
    OpenTalkingClientError,
    OpenTalkingSessionClient,
    SessionCapability,
    SessionResult,
    UploadPart,
)
from scripts.prewarm_opentalking import build_parser, prewarm_session


class FakeStreamResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/event-stream"}
        self._chunks = chunks

    async def read(self) -> bytes:
        return b"".join(self._chunks)

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class FakeStreamContext(AbstractAsyncContextManager[FakeStreamResponse]):
    def __init__(self, response: FakeStreamResponse | Exception) -> None:
        self.response = response

    async def __aenter__(self) -> FakeStreamResponse:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeTransport:
    def __init__(
        self,
        responses: list[HTTPResponse | Exception] | None = None,
        streams: list[FakeStreamResponse | Exception] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.streams = list(streams or [])
        self.requests: list[dict[str, Any]] = []
        self.stream_requests: list[dict[str, Any]] = []

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
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "timeout": timeout,
                "json_body": dict(json_body) if json_body is not None else None,
                "files": dict(files) if files is not None else None,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> FakeStreamContext:
        self.stream_requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        return FakeStreamContext(self.streams.pop(0))


def json_response(status_code: int, payload: str) -> HTTPResponse:
    return HTTPResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        body=payload.encode("utf-8"),
    )


class ActiveProfilePayloadTests(unittest.TestCase):
    def test_published_profile_maps_to_official_session_fields(self) -> None:
        profile = ActiveProfilePayload.from_mapping(
            {
                "opentalking_avatar_id": "guide-v2",
                "opentalking_model": "quicktalk",
                "voice": "yige",
                "persona": "你是灵山胜境的导游。",
                "tts_provider": "vivo",
                "tts_model": "short_audio_synthesis_jovi",
            }
        )

        self.assertEqual(
            profile.to_session_payload(user_id="visitor-7"),
            {
                "avatar_id": "guide-v2",
                "model": "quicktalk",
                "tts_provider": "edge",
                "stt_provider": "funasr",
                "user_id": "visitor-7",
                "agent_enabled": False,
                "memory_enabled": False,
                "knowledge_enabled": False,
            },
        )
        self.assertEqual(
            profile.app_defaults(),
            {
                "tts_provider": "vivo",
                "voice": "yige",
                "tts_model": "short_audio_synthesis_jovi",
                "persona": "你是灵山胜境的导游。",
            },
        )

    def test_external_audio_session_providers_are_configurable(self) -> None:
        profile = ActiveProfilePayload(
            avatar_id="guide-v2",
            model="quicktalk",
            stt_provider="sensevoice",
            tts_provider="mock",
        )

        payload = profile.to_session_payload()

        self.assertEqual(payload["stt_provider"], "sensevoice")
        self.assertEqual(payload["tts_provider"], "mock")

    def test_profile_requires_an_official_avatar_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "avatar"):
            ActiveProfilePayload.from_mapping({"model": "quicktalk"})

        with self.assertRaisesRegex(ValueError, "avatar"):
            ActiveProfilePayload(avatar_id="   ")


class OpenTalkingSessionClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.profile = ActiveProfilePayload(avatar_id="guide-v2", model="quicktalk")

    async def test_create_session_uses_official_sessions_route(self) -> None:
        transport = FakeTransport([json_response(200, '{"session_id":"s-1","status":"initializing"}')])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        result = await client.create_session(self.profile, user_id="visitor-7")

        self.assertEqual(result.session_id, "s-1")
        self.assertEqual(result.status, "initializing")
        request = transport.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "http://127.0.0.1:8010/sessions")
        self.assertEqual(request["json_body"]["avatar_id"], "guide-v2")
        self.assertEqual(request["json_body"]["user_id"], "visitor-7")
        self.assertEqual(request["json_body"]["stt_provider"], "funasr")
        self.assertEqual(request["json_body"]["tts_provider"], "edge")

    async def test_get_and_delete_session_use_official_session_resource(self) -> None:
        transport = FakeTransport(
            [
                json_response(200, '{"session_id":"s-1","state":"ready","model":"quicktalk"}'),
                json_response(200, '{"session_id":"s-1","status":"closed"}'),
            ]
        )
        client = OpenTalkingSessionClient("http://127.0.0.1:8010/", transport=transport)

        state = await client.get_session("s-1")
        result = await client.delete_session("s-1")

        self.assertEqual(state["state"], "ready")
        self.assertEqual(result.status, "closed")
        self.assertEqual(
            [(request["method"], request["url"]) for request in transport.requests],
            [
                ("GET", "http://127.0.0.1:8010/sessions/s-1"),
                ("DELETE", "http://127.0.0.1:8010/sessions/s-1"),
            ],
        )

    async def test_upload_audio_uses_official_flashtalk_file_field(self) -> None:
        transport = FakeTransport([json_response(200, '{"session_id":"s-1","status":"queued"}')])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        result = await client.upload_audio(
            "s-1",
            b"RIFF-wave",
            filename="answer.wav",
            content_type="audio/wav",
        )

        self.assertEqual(result.status, "queued")
        request = transport.requests[0]
        self.assertEqual(request["url"], "http://127.0.0.1:8010/sessions/s-1/speak_flashtalk_audio")
        self.assertEqual(
            request["files"],
            {
                "file": UploadPart(
                    filename="answer.wav",
                    content=b"RIFF-wave",
                    content_type="audio/wav",
                )
            },
        )

    async def test_webrtc_offer_returns_typed_answer(self) -> None:
        transport = FakeTransport([json_response(200, '{"sdp":"answer-sdp","type":"answer"}')])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        answer = await client.offer("s-1", sdp="offer-sdp", offer_type="offer")

        self.assertEqual(answer.sdp, "answer-sdp")
        self.assertEqual(answer.type, "answer")
        self.assertEqual(
            transport.requests[0]["url"],
            "http://127.0.0.1:8010/sessions/s-1/webrtc/offer",
        )
        self.assertEqual(transport.requests[0]["json_body"], {"sdp": "offer-sdp", "type": "offer"})

    async def test_interrupt_uses_official_interrupt_route(self) -> None:
        transport = FakeTransport([json_response(200, '{"session_id":"s-1","status":"interrupted"}')])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        result = await client.interrupt("s-1")

        self.assertEqual(result.status, "interrupted")
        self.assertEqual(
            transport.requests[0]["url"],
            "http://127.0.0.1:8010/sessions/s-1/interrupt",
        )

    async def test_health_and_capability_report_session_webrtc(self) -> None:
        health_payload = (
            '{"status":"ok","default_model":"quicktalk","quicktalk_backend":"local",'
            '"quicktalk_device":"cuda:0"}'
        )
        transport = FakeTransport([json_response(200, health_payload), json_response(200, health_payload)])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        health = await client.health()
        capability = await client.capability(self.profile)

        self.assertEqual(health.status, "ok")
        self.assertEqual(health.default_model, "quicktalk")
        self.assertEqual(
            capability.to_dict(),
            {
                "provider": "session",
                "available": True,
                "preferred": True,
                "transport": "webrtc",
                "model": "quicktalk",
                "avatar_id": "guide-v2",
                "reason": None,
            },
        )
        self.assertEqual([request["url"] for request in transport.requests], [
            "http://127.0.0.1:8010/health",
            "http://127.0.0.1:8010/health",
        ])

    async def test_capability_is_unavailable_instead_of_raising_on_probe_failure(self) -> None:
        transport = FakeTransport([OSError("connection refused")])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        capability = await client.capability(self.profile)

        self.assertFalse(capability.available)
        self.assertIn("connection refused", capability.reason or "")

    async def test_event_stream_passes_official_sse_bytes_through(self) -> None:
        chunks = [b"event: session.ready\n", b"data: {\"state\":\"ready\"}\n\n"]
        transport = FakeTransport(streams=[FakeStreamResponse(chunks)])
        client = OpenTalkingSessionClient("http://127.0.0.1:8010", transport=transport)

        received = [chunk async for chunk in client.stream_events("s-1")]

        self.assertEqual(received, chunks)
        request = transport.stream_requests[0]
        self.assertEqual(request["url"], "http://127.0.0.1:8010/sessions/s-1/events")
        self.assertEqual(request["headers"]["Accept"], "text/event-stream")

    async def test_upstream_errors_redact_configured_secrets(self) -> None:
        secret = "upstream-secret-token"
        transport = FakeTransport(
            [json_response(503, '{"detail":"redis auth failed for upstream-secret-token"}')]
        )
        client = OpenTalkingSessionClient(
            "http://127.0.0.1:8010",
            transport=transport,
            headers={"Authorization": f"Bearer {secret}"},
            secret_values=[secret],
        )

        with self.assertRaises(OpenTalkingClientError) as raised:
            await client.create_session(self.profile)

        message = str(raised.exception)
        self.assertIn("HTTP 503", message)
        self.assertNotIn(secret, message)
        self.assertIn("[redacted]", message)

    async def test_network_errors_redact_credentials_and_sensitive_query_values(self) -> None:
        secret = "url-secret"
        transport = FakeTransport(
            [OSError(f"failed https://demo:{secret}@host.invalid?api_key={secret}")]
        )
        client = OpenTalkingSessionClient(
            f"https://demo:{secret}@host.invalid?api_key={secret}",
            transport=transport,
            secret_values=[secret],
        )

        with self.assertRaises(OpenTalkingClientError) as raised:
            await client.health()

        self.assertNotIn(secret, str(raised.exception))


class FakePrewarmClient:
    def __init__(
        self,
        *,
        capability: SessionCapability,
        states: list[str] | None = None,
        create_error: OpenTalkingClientError | None = None,
    ) -> None:
        self.capability_result = capability
        self.states = list(states or [])
        self.create_error = create_error
        self.created = False
        self.deleted: list[str] = []

    async def capability(self, profile: ActiveProfilePayload) -> SessionCapability:
        return self.capability_result

    async def create_session(
        self,
        profile: ActiveProfilePayload,
        *,
        user_id: str | None = None,
    ) -> SessionResult:
        self.created = True
        if self.create_error is not None:
            raise self.create_error
        return SessionResult(session_id="prewarm-1", status="initializing")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "state": self.states.pop(0)}

    async def delete_session(self, session_id: str) -> SessionResult:
        self.deleted.append(session_id)
        return SessionResult(session_id=session_id, status="closed")


async def no_wait(_: float) -> None:
    return None


class OpenTalkingPrewarmTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.profile = ActiveProfilePayload(avatar_id="guide-v2", model="quicktalk")
        self.available = SessionCapability(
            available=True,
            model="quicktalk",
            avatar_id="guide-v2",
        )

    async def test_prewarm_cli_accepts_external_audio_provider_overrides(self) -> None:
        args = build_parser().parse_args(
            ["--stt-provider", "sensevoice", "--tts-provider", "mock"]
        )

        self.assertEqual(args.stt_provider, "sensevoice")
        self.assertEqual(args.tts_provider, "mock")

    async def test_prewarm_waits_for_ready_and_closes_temporary_session(self) -> None:
        client = FakePrewarmClient(capability=self.available, states=["created", "worker_ready", "ready"])

        result = await prewarm_session(
            client,
            self.profile,
            wait_timeout=5.0,
            poll_interval=0.01,
            sleep=no_wait,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["profile"], {"avatar_id": "guide-v2", "model": "quicktalk"})
        self.assertEqual(client.deleted, ["prewarm-1"])

    async def test_prewarm_reports_actionable_health_failure_without_creating_session(self) -> None:
        client = FakePrewarmClient(
            capability=SessionCapability(
                available=False,
                model="quicktalk",
                avatar_id="guide-v2",
                reason="connection refused",
            )
        )

        result = await prewarm_session(client, self.profile, sleep=no_wait)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "health")
        self.assertIn("/health", result["action"])
        self.assertFalse(client.created)

    async def test_prewarm_turns_session_store_failure_into_actionable_json(self) -> None:
        error = OpenTalkingClientError(
            "OpenTalking create_session failed (HTTP 503): [redacted]",
            operation="create_session",
            status_code=503,
            retryable=True,
        )
        client = FakePrewarmClient(capability=self.available, create_error=error)

        result = await prewarm_session(client, self.profile, sleep=no_wait)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "session_create")
        self.assertIn("Redis", result["action"])
        self.assertEqual(result["reason"], str(error))

    async def test_prewarm_timeout_still_closes_the_temporary_session(self) -> None:
        client = FakePrewarmClient(capability=self.available, states=["created"] * 10)

        result = await prewarm_session(
            client,
            self.profile,
            wait_timeout=0.0,
            poll_interval=0.01,
            sleep=no_wait,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "session_ready")
        self.assertEqual(client.deleted, ["prewarm-1"])


if __name__ == "__main__":
    unittest.main()
