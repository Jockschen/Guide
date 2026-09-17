from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.db import connect, init_db, json_dump


class QualityRunTriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "competition.db"
        self.fixture_path = self.root / "frozen.json"
        self.fixture_path.write_text(
            json.dumps(
                {
                    "dataset_version": "trigger-fixture-v1",
                    "cases": [
                        {
                            "id": "case-1",
                            "question": "开放到几点？",
                            "required_fact_groups": [["21:30"]],
                            "source_file": "景区资料.docx",
                        },
                        {
                            "id": "case-2",
                            "question": "成人票多少钱？",
                            "required_fact_groups": [["210"]],
                            "source_file": "景区资料.docx",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        conn = connect(self.db_path)
        try:
            init_db(conn)
            conn.execute(
                """
                INSERT INTO quality_runs(
                  dataset_version,accuracy,sample_count,passed_count,sample_details_json,
                  latency_ms_json,environment_json,official_evaluation,
                  official_evidence_reference,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "stale-manual-row",
                    0.0,
                    99,
                    0,
                    json_dump([]),
                    json_dump({}),
                    json_dump({"mode": "manual"}),
                    0,
                    "",
                    "2026-07-11T08:00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def answerer(question: str) -> dict[str, object]:
        answer = "开放到21:30。" if "开放" in question else "成人票为210元。"
        return {
            "answer": answer,
            "sources": [{"source_file": "景区资料.docx", "title": "景区资料"}],
            "provider": "test-local-chain",
        }

    def test_in_process_evaluator_executes_every_frozen_case(self) -> None:
        from server.quality_evaluation import run_frozen_evaluation

        report = run_frozen_evaluation(
            fixture_path=self.fixture_path,
            answerer=self.answerer,
        )

        self.assertEqual(report["dataset_version"], "trigger-fixture-v1")
        self.assertEqual(report["passed"], 2)
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["accuracy_percent"], 100.0)
        self.assertFalse(report["official_evaluation"])
        self.assertEqual(
            [item["provider"] for item in report["results"]],
            ["test-local-chain", "test-local-chain"],
        )
        self.assertTrue(all(item["latency_ms"] >= 0 for item in report["results"]))

    def test_run_endpoint_computes_and_persists_a_new_evaluation(self) -> None:
        from server.admin_competition import create_admin_competition_router
        from server.quality_evaluation import run_frozen_evaluation

        def evaluator() -> dict[str, object]:
            return run_frozen_evaluation(
                fixture_path=self.fixture_path,
                answerer=self.answerer,
            )

        app = FastAPI()
        app.include_router(
            create_admin_competition_router(
                self.db_path,
                quality_evaluator=evaluator,
            )
        )

        with TestClient(app) as client:
            response = client.post("/api/admin/competition/quality-runs/run")
            listed = client.get("/api/admin/competition/quality-runs")

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        run = payload["data"]
        self.assertEqual(run["dataset_version"], "trigger-fixture-v1")
        self.assertEqual(run["sample_count"], 2)
        self.assertEqual(run["passed_count"], 2)
        self.assertEqual(run["accuracy"], 1.0)
        self.assertFalse(run["official_evaluation"])
        self.assertEqual(run["environment"]["mode"], "local-in-process")
        self.assertEqual(run["sample_details"][0]["question"], "开放到几点？")
        self.assertEqual(len(listed.json()["data"]), 2)
        self.assertEqual(listed.json()["data"][0]["id"], run["id"])
        self.assertEqual(listed.json()["data"][1]["dataset_version"], "stale-manual-row")

    def test_latest_end_to_end_latency_report_is_exposed_separately(self) -> None:
        from server.admin_competition import create_admin_competition_router

        report_path = self.root / "e2e-latency-latest.json"
        report = {
            "kind": "end_to_end_latency",
            "scope_label": "本地端到端延迟自测（非比赛官方评测）",
            "official_evaluation": False,
            "timings_ms": {
                "chat_ms": 1200.0,
                "tts_ms": 420.0,
                "session_enqueue_ms": 95.0,
                "first_frame_ms": 610.0,
            },
            "measured_total_ms": 2325.0,
            "target_ms": 5000.0,
            "measurement_complete": True,
            "within_target": True,
            "generated_at": "2026-07-12T10:00:00+08:00",
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        app = FastAPI()
        app.include_router(
            create_admin_competition_router(
                self.db_path,
                e2e_latency_report_path=report_path,
            )
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/admin/competition/quality-runs/e2e-latency/latest"
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], report)

    def test_missing_end_to_end_latency_report_returns_an_explicit_empty_state(self) -> None:
        from server.admin_competition import create_admin_competition_router

        app = FastAPI()
        app.include_router(
            create_admin_competition_router(
                self.db_path,
                e2e_latency_report_path=self.root / "missing-report.json",
            )
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/admin/competition/quality-runs/e2e-latency/latest"
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["data"])
        self.assertIn("尚无", response.json()["message"])


if __name__ == "__main__":
    unittest.main()
