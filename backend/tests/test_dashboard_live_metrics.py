from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.main import _build_live_dashboard_metrics


class LiveDashboardMetricTests(unittest.TestCase):
    def test_today_week_and_repeated_raw_questions_are_derived_from_live_logs(self) -> None:
        logs = [
            {"created_at": "2026-07-16T09:00:00", "visitor_id": "visitor-a", "question": "九龙灌浴几点开始？"},
            {"created_at": "2026-07-16T09:05:00", "visitor_id": "visitor-b", "question": "灵山大佛在哪里？"},
            {"created_at": "2026-07-15T10:00:00", "visitor_id": "visitor-a", "question": "九龙灌浴几点开始？"},
            {"created_at": "2026-07-14T11:00:00", "visitor_id": "visitor-c", "question": "九龙灌浴几点开始？"},
            {"created_at": "2026-07-13T12:00:00", "visitor_id": "visitor-d", "question": "灵山大佛在哪里？"},
            {"created_at": "2026-07-12T12:00:00", "visitor_id": "visitor-old", "question": "上周问题"},
            {"created_at": "2026-07-17T12:00:00", "visitor_id": "visitor-future", "question": "未来问题"},
            {"created_at": "2026-07-16T14:00:00", "visitor_id": "", "question": "没有访客标识"},
        ]

        metrics = _build_live_dashboard_metrics(logs, today=date(2026, 7, 16))

        self.assertEqual(metrics["today_visitors"], 2)
        self.assertEqual(metrics["week_visitors"], 4)
        self.assertEqual(metrics["week_questions"], 6)
        self.assertEqual(
            metrics["live_hot_questions"],
            [["九龙灌浴几点开始？", 3], ["灵山大佛在哪里？", 2]],
        )


if __name__ == "__main__":
    unittest.main()
