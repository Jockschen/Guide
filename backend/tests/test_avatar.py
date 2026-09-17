from __future__ import annotations

import base64
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server import avatar


class OpenTalkingAdapterTests(unittest.TestCase):
    def test_runtime_status_prefers_official_session_health(self) -> None:
        original_settings = avatar.settings
        avatar.settings = replace(original_settings, opentalking_base_url="http://127.0.0.1:8011")

        class Response:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args):  # type: ignore[no-untyped-def]
                return False

            def read(self) -> bytes:
                return b'{"status":"ok","default_model":"quicktalk"}'

        try:
            with patch.dict(
                os.environ,
                {
                    "OPENTALKING_SESSION_ENABLED": "1",
                    "OPENTALKING_SESSION_BASE_URL": "http://127.0.0.1:8210",
                },
            ), patch("server.avatar.urllib.request.urlopen", return_value=Response()) as urlopen:
                status = avatar.opentalking_runtime_status()
        finally:
            avatar.settings = original_settings

        self.assertTrue(status["opentalking_ready"])
        self.assertTrue(status["opentalking_session_ready"])
        self.assertEqual(status["opentalking_provider"], "session")
        self.assertEqual(status["opentalking_transport"], "webrtc")
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].full_url, "http://127.0.0.1:8210/health")

    def test_runtime_status_can_fall_back_to_legacy_bridge(self) -> None:
        original_settings = avatar.settings
        avatar.settings = replace(original_settings, opentalking_base_url="http://127.0.0.1:8011")

        class Response:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args):  # type: ignore[no-untyped-def]
                return False

            def read(self) -> bytes:
                return b'{"ok":true,"command_configured":true}'

        def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
            if request.full_url.endswith(":8210/health"):
                raise urllib.error.URLError("session unavailable")
            return Response()

        try:
            with patch.dict(
                os.environ,
                {
                    "OPENTALKING_SESSION_ENABLED": "1",
                    "OPENTALKING_SESSION_BASE_URL": "http://127.0.0.1:8210",
                },
            ), patch("server.avatar.urllib.request.urlopen", side_effect=fake_urlopen):
                status = avatar.opentalking_runtime_status()
        finally:
            avatar.settings = original_settings

        self.assertTrue(status["opentalking_ready"])
        self.assertFalse(status["opentalking_session_ready"])
        self.assertEqual(status["opentalking_provider"], "legacy_bridge")
        self.assertIn("session unavailable", status["opentalking_session_error"])

    def test_opentalking_video_base64_becomes_static_video(self) -> None:
        original_settings = avatar.settings
        original_request_json = avatar._request_json
        avatar.settings = replace(original_settings, opentalking_base_url="http://127.0.0.1:8010")

        def fake_request_json(url: str, payload=None):  # type: ignore[no-untyped-def]
            self.assertIn("/api/lipsync", url)
            return {"status": "completed", "video_base64": base64.b64encode(b"video").decode("ascii")}

        avatar._request_json = fake_request_json  # type: ignore[assignment]
        try:
            result = avatar.request_lipsync("欢迎来到灵山胜境", "/static/audio/test.wav")
        finally:
            avatar._request_json = original_request_json  # type: ignore[assignment]
            avatar.settings = original_settings

        self.assertEqual(result["provider"], "opentalking")
        self.assertEqual(result["status"], "video-ready")
        self.assertTrue(str(result["video_url"]).startswith("/static/avatar-video/opentalking-"))
        self.assertEqual(result["driver"]["mode"], "real_video")
        self.assertEqual(result["driver"]["claim"], "real_lipsync_video")
        self.assertTrue(result["driver"]["video_playable"])
        self.assertTrue(result["driver"]["claim_real_lipsync"])

    def test_opentalking_task_result_is_polled(self) -> None:
        original_settings = avatar.settings
        original_request_json = avatar._request_json
        calls = {"count": 0}
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as output:
            output.write(b"video")
            output_path = Path(output.name)
        avatar.settings = replace(
            original_settings,
            opentalking_base_url="http://127.0.0.1:8010",
            opentalking_timeout_seconds=3,
            opentalking_poll_seconds=0.01,
        )

        def fake_request_json(url: str, payload=None):  # type: ignore[no-untyped-def]
            calls["count"] += 1
            if payload is not None:
                return {"status": "pending", "task_id": "task-1"}
            return {"status": "completed", "video_path": str(output_path)}

        avatar._request_json = fake_request_json  # type: ignore[assignment]
        try:
            result = avatar.request_lipsync("欢迎来到灵山胜境", "/static/audio/test.wav")
        finally:
            avatar._request_json = original_request_json  # type: ignore[assignment]
            avatar.settings = original_settings
            output_path.unlink(missing_ok=True)

        self.assertGreaterEqual(calls["count"], 2)
        self.assertEqual(result["provider"], "opentalking")
        self.assertTrue(str(result["video_url"]).startswith("/static/avatar-video/opentalking-"))

    def test_official_video_creation_download_url_is_supported(self) -> None:
        original_settings = avatar.settings
        original_request_multipart = avatar._request_multipart
        audio_dir = avatar.settings.storage_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / "official-test.wav"
        audio_path.write_bytes(b"RIFF0000WAVE")
        avatar.settings = replace(
            original_settings,
            opentalking_base_url="http://127.0.0.1:8011",
            opentalking_lipsync_path="/video-creation/jobs",
            opentalking_avatar_id="lingjing-guide",
            opentalking_model="wav2lip",
        )

        def fake_request_multipart(url, fields, files):  # type: ignore[no-untyped-def]
            self.assertIn("/video-creation/jobs", url)
            self.assertEqual(fields["model"], "wav2lip")
            self.assertEqual(fields["avatar_id"], "lingjing-guide")
            self.assertIn("audio_file", files)
            return {"export_video": {"download_url": "/exports/videos/job-1/download"}}

        avatar._request_multipart = fake_request_multipart  # type: ignore[assignment]
        try:
            result = avatar.request_lipsync("欢迎来到灵山胜境", "/static/audio/official-test.wav")
        finally:
            avatar._request_multipart = original_request_multipart  # type: ignore[assignment]
            avatar.settings = original_settings
            audio_path.unlink(missing_ok=True)

        self.assertEqual(result["provider"], "opentalking")
        self.assertEqual(result["status"], "video-ready")
        self.assertEqual(result["video_url"], "http://127.0.0.1:8011/exports/videos/job-1/download")
        self.assertEqual(result["driver"]["mode"], "real_video")
        self.assertEqual(result["driver"]["label"], "实时口型")

    def test_demo_video_status_maps_storage_file_to_static_url(self) -> None:
        original_value = os.environ.get("OPENTALKING_DEMO_VIDEO")
        original_label = os.environ.get("OPENTALKING_DEMO_LABEL")
        demo_dir = avatar.settings.storage_dir / "avatar-demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        demo_path = demo_dir / "opentalking-demo.mp4"
        demo_path.write_bytes(b"video")
        os.environ["OPENTALKING_DEMO_VIDEO"] = str(demo_path)
        os.environ["OPENTALKING_DEMO_LABEL"] = "现场演示片段"
        try:
            status = avatar.demo_video_status()
        finally:
            if original_value is None:
                os.environ.pop("OPENTALKING_DEMO_VIDEO", None)
            else:
                os.environ["OPENTALKING_DEMO_VIDEO"] = original_value
            if original_label is None:
                os.environ.pop("OPENTALKING_DEMO_LABEL", None)
            else:
                os.environ["OPENTALKING_DEMO_LABEL"] = original_label
            demo_path.unlink(missing_ok=True)

        self.assertTrue(status["demo_video_ready"])
        self.assertEqual(status["demo_video_label"], "现场演示片段")
        self.assertTrue(str(status["demo_video_url"]).startswith("/static/avatar-demo/"))

    def test_demo_video_is_explicit_fallback_only(self) -> None:
        original_settings = avatar.settings
        original_video = os.environ.get("OPENTALKING_DEMO_VIDEO")
        original_fallback = os.environ.get("OPENTALKING_DEMO_FALLBACK")
        demo_dir = avatar.settings.storage_dir / "avatar-demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        demo_path = demo_dir / "explicit-demo.mp4"
        demo_path.write_bytes(b"video")
        os.environ["OPENTALKING_DEMO_VIDEO"] = str(demo_path)
        os.environ.pop("OPENTALKING_DEMO_FALLBACK", None)
        avatar.settings = replace(original_settings, opentalking_base_url="")
        try:
            regular = avatar.request_lipsync("欢迎来到灵山胜境")
            demo = avatar.request_lipsync("欢迎来到灵山胜境", allow_demo=True)
        finally:
            avatar.settings = original_settings
            if original_video is None:
                os.environ.pop("OPENTALKING_DEMO_VIDEO", None)
            else:
                os.environ["OPENTALKING_DEMO_VIDEO"] = original_video
            if original_fallback is None:
                os.environ.pop("OPENTALKING_DEMO_FALLBACK", None)
            else:
                os.environ["OPENTALKING_DEMO_FALLBACK"] = original_fallback
            demo_path.unlink(missing_ok=True)

        self.assertEqual(regular["provider"], "2d-fallback")
        self.assertEqual(regular["driver"]["mode"], "audio_2d")
        self.assertEqual(regular["driver"]["claim"], "audio_driven_stage")
        self.assertFalse(regular["driver"]["video_playable"])
        self.assertFalse(regular["driver"]["claim_real_lipsync"])
        self.assertEqual(demo["provider"], "opentalking-demo")
        self.assertEqual(demo["status"], "demo-video")
        self.assertTrue(str(demo["video_url"]).startswith("/static/avatar-demo/"))
        self.assertEqual(demo["driver"]["mode"], "demo_video")
        self.assertEqual(demo["driver"]["claim"], "demo_lipsync_clip")
        self.assertTrue(demo["driver"]["video_playable"])
        self.assertFalse(demo["driver"]["claim_real_lipsync"])

    def test_configured_opentalking_failure_is_not_silent_2d_fallback(self) -> None:
        original_settings = avatar.settings
        original_request_json = avatar._request_json
        avatar.settings = replace(original_settings, opentalking_base_url="http://127.0.0.1:8010")

        def fake_request_json(url: str, payload=None):  # type: ignore[no-untyped-def]
            raise urllib.error.URLError("timed out")

        avatar._request_json = fake_request_json  # type: ignore[assignment]
        try:
            result = avatar.request_lipsync("欢迎来到灵山胜境", "/static/audio/test.wav", allow_demo=False)
        finally:
            avatar._request_json = original_request_json  # type: ignore[assignment]
            avatar.settings = original_settings

        self.assertEqual(result["provider"], "opentalking")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["driver"]["mode"], "real_video")
        self.assertFalse(result["driver"]["video_playable"])
        self.assertFalse(result["driver"]["claim_real_lipsync"])
        self.assertIn("没有使用假的 2D", result["message"])


if __name__ == "__main__":
    unittest.main()
