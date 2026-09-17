from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.ingestion import locate_data_package, parse_dashboard_metrics, parse_guide_chunks, parse_structured_attractions
from server.retrieval import local_answer, retrieve
from server.vector_backends import write_optional_vector_index


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = locate_data_package()
        self.docx_files = sorted(self.package.glob("*.docx"))
        self.xlsx_file = next(self.package.glob("*.xlsx"))
        self.structured = next(path for path in self.docx_files if "结构化" in path.name)
        self.guide = next(path for path in self.docx_files if "指南" in path.name)

    def test_structured_docx_extracts_scenic_spots(self) -> None:
        attractions = parse_structured_attractions(self.structured)
        names = {item["name"] for item in attractions}
        self.assertEqual(len(attractions), 22)
        self.assertIn("九龙灌浴", names)
        self.assertIn("拈花广场", names)

    def test_guide_docx_extracts_ticket_and_route_chunks(self) -> None:
        chunks = parse_guide_chunks(self.guide)
        joined = "\n".join(chunk["content"] for chunk in chunks)
        titles = "\n".join(chunk["title"] for chunk in chunks)
        self.assertIn("成人票", joined)
        self.assertIn("亲子家庭路线", titles)
        self.assertGreaterEqual(len(chunks), 30)

    def test_dashboard_metrics_are_from_uploaded_excel(self) -> None:
        metrics = parse_dashboard_metrics(self.xlsx_file)
        self.assertEqual(metrics["total_rows"], 140447)
        self.assertEqual(metrics["matching_lingshan_rows"], 777)
        self.assertGreater(metrics["matching_wuxi_rows"], 0)
        self.assertGreater(metrics["unique_tourists"], 0)
        self.assertIn("data_scope_note", metrics)

    def test_local_answer_keeps_source_boundary(self) -> None:
        chunks = [
            {
                "title": "九龙灌浴",
                "source_file": "灵山胜境 景点结构化数据集.docx",
                "content": "平日演出时间为10:00、11:30、13:30、15:00。",
                "score": 0.9,
            }
        ]
        answer = local_answer("九龙灌浴表演时间是什么？", chunks)
        self.assertIn("10:00", answer)
        self.assertIn("未补编", answer)

    def test_local_answer_does_not_dump_structured_fields(self) -> None:
        chunks = [
            {
                "title": "灵山大照壁（LS-001）",
                "source_file": "灵山胜境 景点结构化数据集.docx",
                "content": "景区：灵山胜境\n景点ID：LS-001\n景点名称：灵山大照壁\n具体位置：景区入口处，面朝太湖。\n核心功能：景区标志性门户、文化序章。\n游玩亮点：打卡合影，拍摄湖光壁影同框美景。\n演艺/开放信息：全天开放，无时间限制。",
                "score": 0.9,
            }
        ]

        answer = local_answer("灵山大照壁有什么看点？", chunks, "拍照推荐")

        self.assertIn("灵山大照壁", answer)
        self.assertIn("打卡合影", answer)
        self.assertNotIn("景点ID", answer)
        self.assertNotIn("具体位置：", answer)

    def test_retrieve_prefers_exact_spot_for_time_question(self) -> None:
        results = retrieve("九龙灌浴表演时间是什么？", limit=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("九龙灌浴", results[0]["title"])
        self.assertIn("10:00", results[0]["content"])

    def test_optional_vector_backend_reports_status(self) -> None:
        result = write_optional_vector_index([
            {
                "title": "测试片段",
                "content": "这是一个测试片段。",
                "source_file": "test.docx",
                "source_type": "test",
                "metadata": {},
            }
        ])
        self.assertIn(result["status"], {"ok", "fallback"})
        self.assertIn(result["backend"], {"chroma", "faiss", "sqlite"})


if __name__ == "__main__":
    unittest.main()
