from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.profile_runtime import public_profile_data, resolve_tts_voice
from server.schemas import TTSRequest


class ActiveProfileRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {
            "id": 7,
            "name": "灵境导游·山岚",
            "persona": "温和、准确的灵山文化导游",
            "voice": "yige",
            "avatar_asset_url": "/static/avatar-v7.png",
            "clothing_version": "spring-2026",
            "source_video_kind": "real_source_video",
            "source_video_url": "/static/avatar-v7.mp4",
            "opentalking_avatar_id": "guide-v7",
            "driver_provider": "opentalking",
            "status": "published",
        }

    def test_published_voice_is_the_default_but_explicit_override_is_preserved(self) -> None:
        self.assertEqual(TTSRequest(text="欢迎").voice, "published")
        self.assertEqual(resolve_tts_voice("published", self.profile), "yige")
        self.assertEqual(resolve_tts_voice("", self.profile), "yige")
        self.assertEqual(resolve_tts_voice("calm", self.profile), "calm")

    def test_public_profile_exposes_runtime_assets_without_admin_only_fields(self) -> None:
        data = public_profile_data(self.profile)

        self.assertEqual(data["name"], "灵境导游·山岚")
        self.assertEqual(data["voice"], "yige")
        self.assertEqual(data["avatar_asset_url"], "/static/avatar-v7.png")
        self.assertTrue(data["real_neutral_motion_source"])
        self.assertEqual(data["opentalking_avatar_id"], "guide-v7")
        self.assertNotIn("management_note", data)


if __name__ == "__main__":
    unittest.main()
