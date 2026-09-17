from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityEvidenceScriptTests(unittest.TestCase):
    def test_hidden_fixture_uses_its_report_slug_without_overwriting_frozen_reports(self) -> None:
        module = load_script("evaluate_frozen_qa.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_path = root / "hidden.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "dataset_version": "hidden-v1",
                        "report_slug": "hidden-qa",
                        "cases": [
                            {
                                "id": "hidden-1",
                                "question": "这是隐藏题吗？",
                                "required_fact_groups": [["关键事实"]],
                                "source_file": "本地资料.docx",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            frozen_latest = root / "frozen-qa-latest.json"
            frozen_latest.write_text("frozen sentinel", encoding="utf-8")
            response = {
                "data": {
                    "answer": "关键事实",
                    "sources": [{"source_file": "本地资料.docx"}],
                    "provider": "local-retrieval",
                }
            }
            args = SimpleNamespace(
                fixture=str(fixture_path),
                limit=0,
                base_url="http://127.0.0.1:8000",
                timeout=1.0,
                persist=False,
                output_dir=str(root),
            )

            with patch.object(module, "_post_json", return_value=response):
                report = module.run(args)

            self.assertTrue((root / "hidden-qa-latest.json").exists())
            self.assertTrue((root / "hidden-qa-latest.md").exists())
            self.assertEqual(frozen_latest.read_text(encoding="utf-8"), "frozen sentinel")
            self.assertEqual(report["report_slug"], "hidden-qa")
            self.assertEqual(report["success_rate_percent"], 100.0)
            self.assertFalse(report["official_evaluation"])

    def test_legacy_fixture_without_report_slug_keeps_frozen_report_name(self) -> None:
        module = load_script("evaluate_frozen_qa.py")
        self.assertEqual(module._report_slug({"dataset_version": "legacy"}), "frozen-qa")

    def test_frozen_answer_requires_facts_and_source(self) -> None:
        module = load_script("evaluate_frozen_qa.py")
        case = {
            "required_fact_groups": [["10:00"], ["11:30"], ["13:30"], ["15:00"]],
            "source_file": "灵山胜境 景点结构化数据集.docx",
        }
        sources = [{"source_file": "灵山胜境 景点结构化数据集.docx"}]

        result = module.evaluate_answer(
            case,
            "平日演出时间为10:00、11:30、13:30、15:00。",
            sources,
        )

        self.assertTrue(result["passed"])
        self.assertTrue(result["facts_passed"])
        self.assertTrue(result["source_passed"])

    def test_frozen_answer_treats_hour_colon_and_chinese_hour_as_equivalent(self) -> None:
        module = load_script("evaluate_frozen_qa.py")
        case = {
            "required_fact_groups": [["9点前"]],
            "source_file": "游览指南.docx",
        }

        result = module.evaluate_answer(
            case,
            "建议上午9:00前入园。",
            [{"source_file": "游览指南.docx"}],
        )

        self.assertTrue(result["passed"])

    def test_frozen_report_never_claims_official_certification(self) -> None:
        module = load_script("evaluate_frozen_qa.py")
        report = module.summarize_results(
            dataset_version="lingjing-frozen-v1",
            results=[{"passed": True, "latency_ms": 800.0}],
            runtime={"mode": "local-live-api"},
        )

        self.assertEqual(report["accuracy_percent"], 100.0)
        self.assertFalse(report["official_evaluation"])
        self.assertIn("本地冻结问答集", report["scope_label"])
        payload = module.quality_run_payload(report)
        self.assertEqual(payload["accuracy"], 1.0)
        self.assertEqual(payload["sample_count"], 1)
        self.assertFalse(payload["official_evaluation"])

    def test_latency_summary_tracks_each_stage_and_threshold(self) -> None:
        module = load_script("benchmark_e2e.py")
        summary = module.summarize_timings(
            {
                "chat_ms": 1200.0,
                "tts_ms": 700.0,
                "session_enqueue_ms": 400.0,
                "first_frame_ms": 900.0,
            },
            threshold_ms=5000.0,
        )

        self.assertEqual(summary["measured_total_ms"], 3200.0)
        self.assertTrue(summary["within_target"])
        self.assertFalse(summary["official_evaluation"])


if __name__ == "__main__":
    unittest.main()
