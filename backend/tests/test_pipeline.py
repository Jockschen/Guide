from __future__ import annotations

from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.main import app
from server import main


class PipelineTests(unittest.TestCase):
    def test_pipeline_check_covers_knowledge_tts_and_lipsync(self) -> None:
        original_tts = main.synthesize_tts
        original_lipsync = main.request_lipsync
        original_opentalking_status = main.opentalking_runtime_status
        original_speech_status = main.speech_runtime_status

        def fake_tts(text: str, voice: str, style: str, speed: float, volume: float) -> dict[str, object]:
            return {
                "provider": "edge",
                "audio_url": "/static/audio/edge-test.wav",
                "visemes": [{"time": 0, "mouth": 0.4}],
            }

        def fake_lipsync(text: str, audio_url: str | None = None, allow_demo: bool = False) -> dict[str, object]:
            return {
                "provider": "2d-fallback",
                "visemes": [{"time": 0, "mouth": 0.4}],
                "driver": {
                    "mode": "audio_2d",
                    "label": "音频驱动",
                    "claim": "audio_driven_stage",
                    "video_playable": False,
                    "claim_real_lipsync": False,
                    "acceptance": "fallback_viseme_timeline",
                },
            }

        main.synthesize_tts = fake_tts  # type: ignore[assignment]
        main.request_lipsync = fake_lipsync  # type: ignore[assignment]
        main.opentalking_runtime_status = lambda: {  # type: ignore[assignment]
            "opentalking_ready": True,
            "opentalking_status": "ready",
        }
        main.speech_runtime_status = lambda: {  # type: ignore[assignment]
            "tts_effective_provider": "edge",
        }
        client = TestClient(app)
        try:
            response = client.get("/api/admin/pipeline-check")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
        finally:
            main.synthesize_tts = original_tts  # type: ignore[assignment]
            main.request_lipsync = original_lipsync  # type: ignore[assignment]
            main.opentalking_runtime_status = original_opentalking_status  # type: ignore[assignment]
            main.speech_runtime_status = original_speech_status  # type: ignore[assignment]
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertTrue(data["knowledge_ready"])
        self.assertGreater(data["retrieved_chunks"], 0)
        self.assertGreater(data["visemes_count"], 0)
        self.assertEqual(data["avatar_driver"]["mode"], "real_video")
        self.assertEqual(data["avatar_driver"]["acceptance"], "opentalking_service_ready")
        self.assertEqual(data["tts_provider"], "edge")
        self.assertEqual(data["tts_effective_provider"], "edge")
        self.assertTrue(data["tts_audio_ready"])

    def test_demo_readiness_exposes_competition_blockers(self) -> None:
        original_speech_status = main.speech_runtime_status
        original_opentalking_status = main.opentalking_runtime_status

        def fake_speech_status() -> dict[str, object]:
            return {
                "asr_provider": "vivo",
                "tts_provider": "vivo",
                "asr_effective_provider": "vivo",
                "tts_effective_provider": "vivo",
            }

        def fake_opentalking_status() -> dict[str, object]:
            return {
                "opentalking_configured": True,
                "opentalking_ready": True,
                "opentalking_status": "ready",
                "demo_video_ready": False,
                "demo_video_url": "",
            }

        main.speech_runtime_status = fake_speech_status  # type: ignore[assignment]
        main.opentalking_runtime_status = fake_opentalking_status  # type: ignore[assignment]
        client = TestClient(app)
        try:
            response = client.get("/api/admin/demo-readiness")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
        finally:
            main.speech_runtime_status = original_speech_status  # type: ignore[assignment]
            main.opentalking_runtime_status = original_opentalking_status  # type: ignore[assignment]

        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertTrue(data["knowledge_ready"])
        self.assertEqual(data["digital_human_plan"], "OpenTalking 实时生成真实口型视频")
        self.assertEqual(data["digital_human_driver_mode"], "real_video")
        self.assertIn("blockers", data)


if __name__ == "__main__":
    unittest.main()
