from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server import main
from server.retrieval import match_faq


class FAQMatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "faqs.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE faqs (
              id INTEGER PRIMARY KEY,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              source_title TEXT NOT NULL,
              source_file TEXT NOT NULL,
              tags_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO faqs(id,question,answer,source_title,source_file,tags_json)
            VALUES(1,?,?,?,?,?)
            """,
            (
                "九龙灌浴的开放或演艺信息是什么？",
                "平日演出时间为10:00、11:30、13:30、15:00。",
                "九龙灌浴（LS-006）",
                "灵山胜境 景点结构化数据集.docx",
                '["开放信息","灵山胜境"]',
            ),
        )
        conn.execute(
            """
            INSERT INTO faqs(id,question,answer,source_title,source_file,tags_json)
            VALUES(2,?,?,?,?,?)
            """,
            (
                "九龙灌浴在哪里？",
                "位于菩提大道北端。",
                "九龙灌浴（LS-006）",
                "灵山胜境 景点结构化数据集.docx",
                '["位置","灵山胜境"]',
            ),
        )
        conn.execute(
            """
            CREATE TABLE qa_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              sources_json TEXT NOT NULL,
              provider TEXT NOT NULL,
              created_at TEXT NOT NULL,
              visitor_id TEXT,
              user_agent TEXT,
              spot_name TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO faqs(id,question,answer,source_title,source_file,tags_json)
            VALUES(3,?,?,?,?,?)
            """,
            (
                "灵山大佛在哪里？",
                "位于祥符禅寺后的秦履峰南坡。",
                "灵山大佛（LS-011）",
                "灵山胜境 景点结构化数据集.docx",
                '["位置","灵山胜境"]',
            ),
        )
        conn.execute(
            """
            INSERT INTO faqs(id,question,answer,source_title,source_file,tags_json)
            VALUES(4,?,?,?,?,?)
            """,
            (
                "佛教文化博览馆有什么文化内涵？",
                "展示佛教文化发展脉络。",
                "佛教文化博览馆（LS-012）",
                "灵山胜境 景点结构化数据集.docx",
                '["文化","灵山胜境"]',
            ),
        )
        conn.execute(
            """
            INSERT INTO faqs(id,question,answer,source_title,source_file,tags_json)
            VALUES(5,?,?,?,?,?)
            """,
            (
                "佛教文化博览馆的开放或演艺信息是什么？",
                "免费讲解时段为9:30、11:00、14:30、16:00。",
                "佛教文化博览馆（LS-012）",
                "灵山胜境 景点结构化数据集.docx",
                '["开放信息","灵山胜境"]',
            ),
        )
        conn.execute(
            """
            CREATE TABLE attractions (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              spot_id TEXT NOT NULL,
              source_file TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_exact_question_returns_grounded_faq(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("九龙灌浴的开放或演艺信息是什么？")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["answer"], "平日演出时间为10:00、11:30、13:30、15:00。")
        self.assertEqual(result["source_title"], "九龙灌浴（LS-006）")

    def test_unique_entity_and_intent_match_a_paraphrase(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("九龙灌浴今天有哪些演出时间？")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["id"], 1)

    def test_multiple_entities_do_not_match_a_faq(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("九龙灌浴和灵山大佛分别在哪里？")

        self.assertIsNone(result)

    def test_pronoun_only_question_does_not_match_a_faq(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("它今天有哪些演出时间？")

        self.assertIsNone(result)

    def test_entity_name_does_not_leak_culture_into_the_question_intent(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("佛教文化博览馆的免费讲解有哪些时段？")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["id"], 5)

    def test_question_asking_for_another_attraction_bypasses_the_fast_path(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("佛教文化博览馆和哪个藏传文化景点在同一行程里？")

        self.assertIsNone(result)

    def test_origin_question_does_not_take_the_location_fast_path(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect):
            result = match_faq("九龙灌浴复刻自哪里的什么典故？")

        self.assertIsNone(result)

    def test_factual_question_about_a_documented_itinerary_is_not_replanned(self) -> None:
        self.assertFalse(
            main._is_route_request(
                "指南给自然风光爱好者安排的全景行程是几小时，并列出的两个园林节点是什么？"
            )
        )
        self.assertTrue(main._is_route_request("我喜欢自然风光，帮我规划半日游路线"))

    def test_chat_uses_the_faq_fast_path_without_calling_qwen(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.connect", side_effect=self.connect
        ), patch("server.main.call_qwen", return_value="external answer") as call_qwen:
            response = self.client.post(
                "/api/chat",
                json={"question": "九龙灌浴今天有哪些演出时间？"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["provider"], "faq-fast-path")
        self.assertEqual(data["sources"][0]["source_type"], "faq")
        self.assertGreater(data["log_id"], 0)
        call_qwen.assert_not_called()

    def test_image_question_bypasses_the_faq_fast_path(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日10:00开始",
            }
        ]
        with patch("server.main.connect", side_effect=self.connect), patch(
            "server.main.retrieve", return_value=chunks
        ), patch("server.main.active_profile", return_value={}), patch(
            "server.main.call_qwen", return_value="这是多模态回答。"
        ) as call_qwen:
            response = self.client.post(
                "/api/chat",
                json={
                    "question": "九龙灌浴的开放或演艺信息是什么？",
                    "image_base64": "aW1hZ2U=",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["provider"], "qwen")
        self.assertEqual(call_qwen.call_args.args[2], "aW1hZ2U=")

    def test_faq_stream_emits_narration_before_the_completed_logged_answer(self) -> None:
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.connect", side_effect=self.connect
        ), patch("server.main.call_qwen", return_value="external answer") as call_qwen:
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "九龙灌浴今天有哪些演出时间？"},
                headers={"Accept": "application/x-ndjson"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "application/x-ndjson")
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual([event["type"] for event in events], ["meta", "delta", "narration", "done"])
        self.assertEqual(events[2]["text"], "平日演出时间为10:00、11:30、13:30、15:00。")
        self.assertEqual(events[-1]["data"]["provider"], "faq-fast-path")
        self.assertGreater(events[-1]["data"]["log_id"], 0)
        call_qwen.assert_not_called()

    def test_qwen_stream_emits_complete_sentences_before_done(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日十点开始",
            }
        ]
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.connect", side_effect=self.connect
        ), patch("server.main.retrieve", return_value=chunks), patch(
            "server.main.active_profile", return_value={}
        ), patch(
            "server.main.iter_qwen_deltas",
            return_value=iter(["九龙灌浴", "平日十点开始。", "请提前到场。"]),
        ):
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "请根据资料说明九龙灌浴的常规安排"},
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "meta")
        self.assertIn("narration", event_types[:-1])
        self.assertEqual(event_types[-1], "done")
        self.assertEqual(events[-1]["data"]["answer"], "九龙灌浴平日十点开始。请提前到场。")
        self.assertEqual(events[-1]["data"]["provider"], "qwen-stream")
        self.assertGreater(events[-1]["data"]["log_id"], 0)

    def test_failure_before_the_first_qwen_delta_streams_a_logged_local_fallback(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日10:00开始",
            }
        ]
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.retrieve", return_value=chunks
        ), patch("server.main.active_profile", return_value={}), patch(
            "server.main.iter_qwen_deltas", side_effect=RuntimeError("secret upstream detail")
        ):
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "请根据资料讲解九龙灌浴"},
            )

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual(events[0], {"type": "meta", "provider": "local-retrieval"})
        self.assertEqual(events[1]["type"], "delta")
        self.assertIn("narration", [event["type"] for event in events])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["data"]["provider"], "local-retrieval")
        self.assertGreater(events[-1]["data"]["log_id"], 0)
        self.assertNotIn("error", [event["type"] for event in events])

    def test_empty_qwen_stream_uses_the_logged_local_fallback(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日10:00开始",
            }
        ]
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.connect", side_effect=self.connect
        ), patch("server.main.retrieve", return_value=chunks), patch(
            "server.main.active_profile", return_value={}
        ), patch("server.main.iter_qwen_deltas", return_value=iter(())):
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "请根据资料讲解九龙灌浴"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual(events[0], {"type": "meta", "provider": "local-retrieval"})
        self.assertEqual(events[-1]["type"], "done")
        self.assertNotIn("error", [event["type"] for event in events])

    def test_failure_after_a_qwen_delta_ends_with_error_without_local_splicing(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日10:00开始",
            }
        ]

        def interrupted_stream():
            yield "九龙灌浴"
            raise RuntimeError("secret after first delta")

        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.retrieve", return_value=chunks
        ), patch("server.main.active_profile", return_value={}), patch(
            "server.main.iter_qwen_deltas", return_value=interrupted_stream()
        ):
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "请根据资料讲解九龙灌浴"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual(events[0], {"type": "meta", "provider": "qwen-stream"})
        self.assertEqual(events[1], {"type": "delta", "text": "九龙灌浴"})
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("done", [event["type"] for event in events])
        self.assertNotIn("secret after first delta", events[-1]["message"])

    def test_long_unpunctuated_qwen_text_emits_narration_before_later_deltas(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "资料.docx",
                "source_type": "attraction",
                "score": 0.9,
                "content": "平日10:00开始",
            }
        ]
        first = "甲" * 30
        second = "乙" * 20
        later = "丙" * 5
        with patch("server.retrieval.connect", side_effect=self.connect), patch(
            "server.main.connect", side_effect=self.connect
        ), patch("server.main.retrieve", return_value=chunks), patch(
            "server.main.active_profile", return_value={}
        ), patch(
            "server.main.iter_qwen_deltas", return_value=iter([first, second, later, "。"])
        ):
            response = self.client.post(
                "/api/chat/stream",
                json={"question": "请根据资料讲解九龙灌浴"},
            )

        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        narration_index = next(index for index, event in enumerate(events) if event["type"] == "narration")
        later_delta_index = next(
            index
            for index, event in enumerate(events)
            if event["type"] == "delta" and event["text"] == later
        )
        self.assertLess(narration_index, later_delta_index)
        self.assertEqual(len(events[narration_index]["text"]), 46)


if __name__ == "__main__":
    unittest.main()
