from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest
import wave

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.validate_opentalking_webrtc import (  # noqa: E402
    _audio_metadata,
    _frame_motion_metrics,
    _motion_passes,
    _observed_fps,
    _select_audio_path,
)


class OpenTalkingWebRTCValidationTests(unittest.TestCase):
    def test_motion_metrics_detect_a_changed_mouth_region(self) -> None:
        idle = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(4)]
        speaking = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(4)]
        speaking[1][43:57, 41:59] = 40
        speaking[2][43:57, 41:59] = 100
        speaking[3][43:57, 41:59] = 10

        metrics = _frame_motion_metrics(idle, speaking)

        self.assertEqual(metrics["speaking_frame_count"], 4)
        self.assertEqual(metrics["speaking_unique_frames"], 4)
        self.assertGreater(metrics["speaking_mouth_delta_max"], 1.0)
        self.assertGreater(metrics["speaking_mouth_delta_p95"], metrics["idle_mouth_delta_p95"])

    def test_motion_pass_requires_video_state_frames_and_visible_change(self) -> None:
        metrics = {
            "speaking_frame_count": 60,
            "speaking_unique_frames": 50,
            "speaking_mouth_delta_max": 5.0,
            "speaking_mouth_delta_p95": 2.0,
            "idle_mouth_delta_p95": 0.4,
        }

        ok, checks = _motion_passes(
            metrics,
            video_track_received=True,
            peer_connected=True,
            speaking_state_seen=True,
        )

        self.assertTrue(ok)
        self.assertTrue(all(checks.values()))

    def test_select_audio_path_prefers_latest_nonempty_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            older = directory / "older.wav"
            newer = directory / "newer.wav"
            invalid = directory / "empty.wav"
            older.write_bytes(b"RIFF" + b"0" * 100)
            newer.write_bytes(b"RIFF" + b"1" * 120)
            invalid.write_bytes(b"")
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))
            os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

            selected = _select_audio_path(None, directory)

            self.assertEqual(selected, newer)

    def test_audio_metadata_records_provider_format_and_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "edge-proof.wav"
            with wave.open(str(audio_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16_000)
                output.writeframes(b"\0\0" * 1_600)

            metadata = _audio_metadata(audio_path, provider="")

        self.assertEqual(metadata["provider"], "edge")
        self.assertEqual(metadata["sample_rate_hz"], 16_000)
        self.assertEqual(metadata["channels"], 1)
        self.assertEqual(metadata["sample_width_bits"], 16)
        self.assertEqual(metadata["duration_seconds"], 0.1)

    def test_observed_fps_uses_full_capture_span(self) -> None:
        self.assertEqual(_observed_fps([10.0, 10.04, 10.08]), 25.0)


if __name__ == "__main__":
    unittest.main()
