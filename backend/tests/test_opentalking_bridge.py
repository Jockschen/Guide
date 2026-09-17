from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server import opentalking_bridge


class OpenTalkingBridgeTests(unittest.TestCase):
    def test_relative_output_dir_resolves_under_project_root(self) -> None:
        output_dir = opentalking_bridge._resolve_output_dir("backend/storage/opentalking-output")

        self.assertTrue(output_dir.is_absolute())
        self.assertEqual(output_dir, (ROOT / "backend/storage/opentalking-output").resolve())

    def test_bridge_defaults_to_quicktalk_and_supports_avatar_placeholder(self) -> None:
        payload = opentalking_bridge.LipsyncPayload()
        source = (ROOT / "backend" / "server" / "opentalking_bridge.py").read_text(encoding="utf-8")

        self.assertEqual(payload.model, "quicktalk")
        self.assertIn("{avatar}", source)
        self.assertIn("avatar=avatar_dir", source)

    def test_lipsync_cache_path_is_stable_for_same_audio_and_model(self) -> None:
        audio = ROOT / "tmp" / "opentalking-cache-test.wav"
        audio.parent.mkdir(exist_ok=True)
        audio.write_bytes(b"lingjing-audio")
        payload = opentalking_bridge.LipsyncPayload(avatar_id="lingjing-guide", model="quicktalk")

        first = opentalking_bridge._cached_output_path(payload, str(audio), "avatar-dir", "render {audio}")
        second = opentalking_bridge._cached_output_path(payload, str(audio), "avatar-dir", "render {audio}")

        self.assertEqual(first, second)
        self.assertTrue(first.name.startswith("lingjing-guide-quicktalk-"))

    def test_lipsync_cache_changes_when_avatar_template_changes(self) -> None:
        temp_root = ROOT / "tmp" / "opentalking-cache-avatar"
        audio = temp_root / "speech.wav"
        avatar = temp_root / "avatar"
        quicktalk = avatar / "quicktalk"
        image = avatar / "reference.png"
        quicktalk.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"same-audio")
        image.write_bytes(b"avatar-image")
        (avatar / "manifest.json").write_text(
            '{"metadata":{"quicktalk":{"template_video":"quicktalk/template_720x720.mp4"}}}',
            encoding="utf-8",
        )
        template = quicktalk / "template_720x720.mp4"
        payload = opentalking_bridge.LipsyncPayload(avatar_id="lingjing-guide", model="quicktalk")

        template.write_bytes(b"template-one")
        first = opentalking_bridge._cached_output_path(payload, str(audio), str(avatar), "render {audio}", str(image))
        template.write_bytes(b"template-two")
        second = opentalking_bridge._cached_output_path(payload, str(audio), str(avatar), "render {audio}", str(image))

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
