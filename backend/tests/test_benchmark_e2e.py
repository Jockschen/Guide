from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load_benchmark():
    path = ROOT / "scripts" / "benchmark_e2e.py"
    spec = importlib.util.spec_from_file_location("benchmark_e2e", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkE2ETests(unittest.TestCase):
    def test_cli_collects_thirty_samples_by_default(self) -> None:
        module = load_benchmark()

        args = module.build_parser().parse_args([])

        self.assertEqual(args.samples, 30)

    def test_missing_asr_or_visible_mouth_keeps_sample_incomplete(self) -> None:
        module = load_benchmark()

        sample = module.summarize_sample(
            {
                "chat_ms": 1200.0,
                "tts_ms": 700.0,
                "session_enqueue_ms": 100.0,
                "first_frame_ms": 500.0,
            },
            sample_id="api-001",
            run_kind="cold",
            threshold_ms=5000.0,
        )

        self.assertFalse(sample["measurement_complete"])
        self.assertFalse(sample["within_target"])
        self.assertIn("asr_ms", sample["missing_stages"])
        self.assertIn("first_valid_audio_ms", sample["missing_stages"])
        self.assertIn("first_visible_mouth_ms", sample["missing_stages"])
        self.assertNotIn("first_frame_ms", sample["timings_ms"])

    def test_summary_reports_percentiles_success_rate_and_cold_hot_groups(self) -> None:
        module = load_benchmark()
        samples = [
            module.summarize_sample(
                {
                    "asr_ms": 100.0,
                    "chat_ms": 900.0 + index * 100.0,
                    "tts_ms": 500.0,
                    "session_enqueue_ms": 100.0,
                    "first_valid_audio_ms": 250.0,
                    "first_visible_mouth_ms": 400.0,
                    "end_to_end_ms": 2000.0 + index * 100.0,
                    "asr_provider": "vivo",
                    "tts_provider": "edge",
                    "driver": "session_stream",
                },
                sample_id=f"sample-{index + 1:03d}",
                run_kind="cold" if index == 0 else "hot",
                threshold_ms=5000.0,
            )
            for index in range(4)
        ]

        report = module.summarize_samples(samples, threshold_ms=5000.0, requested_samples=4)

        self.assertTrue(report["measurement_complete"])
        self.assertTrue(report["within_target"])
        self.assertEqual(report["sample_count"], 4)
        self.assertEqual(report["success_rate_percent"], 100.0)
        self.assertEqual(report["latency_ms"]["p50"], 2150.0)
        self.assertEqual(report["latency_ms"]["p95"], 2285.0)
        self.assertEqual(report["groups"]["cold"]["sample_count"], 1)
        self.assertEqual(report["groups"]["hot"]["sample_count"], 3)
        self.assertIn("asr_ms", report["stage_statistics_ms"])
        self.assertEqual(len(report["samples"]), 4)

    def test_imported_browser_samples_can_complete_strict_report(self) -> None:
        module = load_benchmark()
        payload = {
            "samples": [
                {
                    "sample_id": "browser-001",
                    "run_kind": "cold",
                    "timings_ms": {
                        "asr_ms": 320.0,
                        "chat_ms": 1100.0,
                        "tts_ms": 650.0,
                        "session_enqueue_ms": 80.0,
                        "first_valid_audio_ms": 120.0,
                        "first_visible_mouth_ms": 900.0,
                    },
                    "end_to_end_ms": 3050.0,
                    "asr_provider": "vivo",
                    "tts_provider": "edge",
                    "driver": "session_stream",
                },
                {
                    "sample_id": "browser-002",
                    "run_kind": "hot",
                    "timings_ms": {
                        "asr_ms": 280.0,
                        "chat_ms": 900.0,
                        "tts_ms": 520.0,
                        "session_enqueue_ms": 60.0,
                        "first_valid_audio_ms": 100.0,
                        "first_visible_mouth_ms": 720.0,
                    },
                    "end_to_end_ms": 2480.0,
                    "asr_provider": "vivo",
                    "tts_provider": "edge",
                    "driver": "session_stream",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "browser-samples.json"
            sample_path.write_text(json.dumps(payload), encoding="utf-8")

            samples = module.load_sample_file(sample_path, threshold_ms=5000.0)
            report = module.summarize_samples(samples, threshold_ms=5000.0, requested_samples=2)

        self.assertTrue(report["measurement_complete"])
        self.assertTrue(report["within_target"])
        self.assertEqual(report["success_rate_percent"], 100.0)
        self.assertEqual(report["samples"][0]["source"], "browser-session")

    def test_imported_legacy_webrtc_first_frame_does_not_complete_report(self) -> None:
        module = load_benchmark()
        payload = [
            {
                "sample_id": "legacy-001",
                "asr_ms": 300.0,
                "chat_ms": 1000.0,
                "tts_ms": 500.0,
                "session_enqueue_ms": 100.0,
                "first_frame_ms": 600.0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "legacy-samples.json"
            sample_path.write_text(json.dumps(payload), encoding="utf-8")

            samples = module.load_sample_file(sample_path, threshold_ms=5000.0)
            report = module.summarize_samples(samples, threshold_ms=5000.0, requested_samples=1)

        self.assertFalse(report["measurement_complete"])
        self.assertFalse(report["within_target"])
        self.assertIn("first_visible_mouth_ms", report["samples"][0]["missing_stages"])

    def test_authoritative_total_does_not_sum_overlapping_stage_diagnostics(self) -> None:
        module = load_benchmark()

        sample = module.summarize_sample(
            {
                "asr_ms": 600.0,
                "chat_ms": 3200.0,
                "tts_ms": 900.0,
                "session_enqueue_ms": 700.0,
                "first_valid_audio_ms": 300.0,
                "first_visible_mouth_ms": 1800.0,
                "end_to_end_ms": 4200.0,
                "asr_provider": "vivo",
                "tts_provider": "edge",
                "driver": "session_stream",
            },
            sample_id="browser-overlap",
            run_kind="hot",
            threshold_ms=5000.0,
        )

        self.assertTrue(sample["measurement_complete"])
        self.assertEqual(sample["measured_total_ms"], 4200.0)
        self.assertEqual(sample["stage_sum_ms"], 7500.0)
        self.assertTrue(sample["within_target"])

    def test_missing_authoritative_end_to_end_keeps_sample_incomplete(self) -> None:
        module = load_benchmark()

        sample = module.summarize_sample(
            {
                "asr_ms": 400.0,
                "chat_ms": 1000.0,
                "tts_ms": 500.0,
                "session_enqueue_ms": 100.0,
                "first_valid_audio_ms": 120.0,
                "first_visible_mouth_ms": 800.0,
                "asr_provider": "vivo",
                "tts_provider": "edge",
                "driver": "session_stream",
            },
            sample_id="browser-no-total",
            run_kind="cold",
            threshold_ms=5000.0,
        )

        self.assertFalse(sample["measurement_complete"])
        self.assertIn("end_to_end_ms", sample["missing_stages"])

    def test_mock_or_missing_runtime_providers_cannot_complete_a_browser_sample(self) -> None:
        module = load_benchmark()

        sample = module.summarize_sample(
            {
                "asr_ms": 300.0,
                "chat_ms": 900.0,
                "tts_ms": 500.0,
                "session_enqueue_ms": 80.0,
                "first_valid_audio_ms": 120.0,
                "first_visible_mouth_ms": 700.0,
                "end_to_end_ms": 2600.0,
                "asr_provider": "mock",
                "tts_provider": "edge",
                "driver": "session_stream",
            },
            sample_id="browser-mock-asr",
            run_kind="hot",
            threshold_ms=5000.0,
        )

        self.assertFalse(sample["success"])
        self.assertFalse(sample["measurement_complete"])
        self.assertIn("real_asr_provider", sample["missing_stages"])


if __name__ == "__main__":
    unittest.main()
