from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, AsyncIterator
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.avatar_session_api import create_avatar_session_router
from server.opentalking_session import (
    ActiveProfilePayload,
    SessionCapability,
    SessionResult,
    WebRTCAnswer,
)


class FakeSessionClient:
    def __init__(self) -> None:
        self.profile: ActiveProfilePayload | None = None
        self.user_id: str | None = None
        self.audio: bytes | None = None
        self.offer_payload: tuple[str, str, str] | None = None
        self.interrupted: str | None = None
        self.deleted: str | None = None

    async def capability(self, profile: ActiveProfilePayload) -> SessionCapability:
        self.profile = profile
        return SessionCapability(True, profile.model, profile.avatar_id)

    async def create_session(
        self,
        profile: ActiveProfilePayload,
        *,
        user_id: str | None = None,
    ) -> SessionResult:
        self.profile = profile
        self.user_id = user_id
        return SessionResult("session-1", "initializing")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "state": "ready"}

    async def upload_audio(
        self,
        session_id: str,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> SessionResult:
        self.audio = audio
        return SessionResult(session_id, "queued")

    async def offer(self, session_id: str, *, sdp: str, offer_type: str) -> WebRTCAnswer:
        self.offer_payload = (session_id, sdp, offer_type)
        return WebRTCAnswer("answer-sdp", "answer")

    async def interrupt(self, session_id: str) -> SessionResult:
        self.interrupted = session_id
        return SessionResult(session_id, "interrupted")

    async def delete_session(self, session_id: str) -> SessionResult:
        self.deleted = session_id
        return SessionResult(session_id, "closed")

    async def stream_events(self, session_id: str) -> AsyncIterator[bytes]:
        yield b"event: session.ready\ndata: {}\n\n"


class AvatarSessionAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeSessionClient()
        app = FastAPI()
        app.include_router(
            create_avatar_session_router(
                profile_loader=lambda: {
                    "opentalking_avatar_id": "published-guide-v2",
                    "opentalking_model": "quicktalk",
                    "voice": "yige",
                    "persona": "灵山文化导游",
                },
                client_factory=lambda: self.fake,
                enabled=True,
                session_stt_provider="funasr",
                session_tts_provider="edge",
            )
        )
        self.client = TestClient(app)

    def test_create_uses_published_profile_and_external_audio_bootstrap(self) -> None:
        response = self.client.post(
            "/api/avatar/sessions",
            json={"client_id": "visitor-9", "purpose": "external-audio"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["session_id"], "session-1")
        self.assertEqual(response.json()["data"]["transport"], "webrtc")
        self.assertEqual(self.fake.user_id, "visitor-9")
        self.assertEqual(self.fake.profile.avatar_id, "published-guide-v2")
        payload = self.fake.profile.to_session_payload(user_id="visitor-9")
        self.assertEqual(payload["stt_provider"], "funasr")
        self.assertEqual(payload["tts_provider"], "edge")
        self.assertNotEqual(payload.get("tts_provider"), "vivo")

    def test_audio_offer_interrupt_and_close_proxy_official_contract(self) -> None:
        audio_response = self.client.post(
            "/api/avatar/sessions/session-1/audio",
            files={"file": ("answer.wav", b"RIFF-wave", "audio/wav")},
        )
        offer_response = self.client.post(
            "/api/avatar/sessions/session-1/webrtc/offer",
            json={"sdp": "offer-sdp", "type": "offer"},
        )
        interrupt_response = self.client.post("/api/avatar/sessions/session-1/interrupt")
        delete_response = self.client.delete("/api/avatar/sessions/session-1")

        self.assertEqual(audio_response.json()["data"]["status"], "queued")
        self.assertEqual(self.fake.audio, b"RIFF-wave")
        self.assertEqual(offer_response.json()["data"], {"sdp": "answer-sdp", "type": "answer"})
        self.assertEqual(self.fake.offer_payload, ("session-1", "offer-sdp", "offer"))
        self.assertEqual(interrupt_response.json()["data"]["status"], "interrupted")
        self.assertEqual(delete_response.json()["data"]["status"], "closed")

    def test_capability_and_events_are_same_origin_endpoints(self) -> None:
        capability = self.client.get("/api/avatar/session-capability")
        events = self.client.get("/api/avatar/sessions/session-1/events")

        self.assertEqual(capability.status_code, 200)
        self.assertTrue(capability.json()["data"]["available"])
        self.assertEqual(capability.json()["data"]["transport"], "webrtc")
        self.assertIn("session.ready", events.text)
        self.assertEqual(events.headers["content-type"].split(";")[0], "text/event-stream")


if __name__ == "__main__":
    unittest.main()
