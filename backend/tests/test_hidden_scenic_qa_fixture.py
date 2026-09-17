from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
HIDDEN_FIXTURE = FIXTURES / "hidden_scenic_qa_v1.json"
FROZEN_FIXTURE = FIXTURES / "frozen_scenic_qa.json"


def normalized(value: object) -> str:
    return re.sub(r"[\s，。；：、,.!?！？:;()（）\-—_]+", "", str(value or "")).casefold()


class HiddenScenicQAFixtureTests(unittest.TestCase):
    def load_hidden(self) -> dict[str, object]:
        return json.loads(HIDDEN_FIXTURE.read_text(encoding="utf-8"))

    def test_hidden_fixture_has_independent_unique_coverage(self) -> None:
        hidden = self.load_hidden()
        frozen = json.loads(FROZEN_FIXTURE.read_text(encoding="utf-8"))
        cases = list(hidden.get("cases") or [])
        frozen_questions = {normalized(case["question"]) for case in frozen["cases"]}
        ids = [str(case.get("id") or "") for case in cases]
        questions = [normalized(case.get("question")) for case in cases]

        self.assertEqual(hidden.get("report_slug"), "hidden-qa")
        self.assertGreaterEqual(len(cases), 30)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(questions), len(set(questions)))
        self.assertFalse(frozen_questions.intersection(questions))
        self.assertTrue(all(case.get("required_fact_groups") for case in cases))
        self.assertTrue(all(case.get("source_file") and case.get("source_title") for case in cases))
        self.assertTrue(
            {"历史", "文化", "景点", "票务", "演出", "游览建议"}.issubset(
                {str(case.get("category") or "") for case in cases}
            )
        )

    def test_every_expected_fact_is_traceable_to_the_local_source(self) -> None:
        hidden = self.load_hidden()
        conn = sqlite3.connect(ROOT / "backend" / "storage" / "lingjing.db")
        conn.row_factory = sqlite3.Row
        try:
            local_sources = {row[0] for row in conn.execute("SELECT name FROM source_files")}
            for case in hidden["cases"]:
                self.assertIn(case["source_file"], local_sources, case["id"])
                rows = conn.execute(
                    "SELECT answer FROM faqs WHERE source_file=? AND source_title=?",
                    (case["source_file"], case["source_title"]),
                ).fetchall()
                self.assertTrue(rows, case["id"])
                source_text = normalized(
                    f"{case['source_title']} " + " ".join(str(row["answer"]) for row in rows)
                )
                for group in case["required_fact_groups"]:
                    self.assertTrue(
                        any(normalized(term) in source_text for term in group),
                        f"{case['id']} is not traceable: {group}",
                    )
        finally:
            conn.close()

    def test_answer_service_does_not_read_the_hidden_fixture(self) -> None:
        for path in (ROOT / "backend" / "server").glob("*.py"):
            self.assertNotIn("hidden_scenic_qa_v1.json", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
