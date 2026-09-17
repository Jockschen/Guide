from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.qwen_client import call_qwen, iter_qwen_deltas, sanitize_markdown_answer
from server import qwen_client


class QwenMarkdownTests(unittest.TestCase):
    def test_feedback_sentiment_classifier_returns_strict_json_result(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "sentiment": "negative",
                                    "confidence": 0.92,
                                    "reason": "游客明确抱怨排队。",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False
        classifier = getattr(qwen_client, "classify_feedback_sentiment", None)
        self.assertTrue(callable(classifier), "Qwen 情绪分类器尚未实现")

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ) as urlopen:
            result = classifier("排队太久，我很失望")

        self.assertEqual(
            result,
            {
                "sentiment": "negative",
                "confidence": 0.92,
                "reason": "游客明确抱怨排队。",
            },
        )
        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_body["temperature"], 0.0)
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertLessEqual(urlopen.call_args.kwargs["timeout"], 3)

    def test_feedback_sentiment_classifier_fails_fast_without_key(self) -> None:
        classifier = getattr(qwen_client, "classify_feedback_sentiment", None)
        self.assertTrue(callable(classifier), "Qwen 情绪分类器尚未实现")
        with patch("server.qwen_client.qwen_available", return_value=False), patch(
            "server.qwen_client.urllib.request.urlopen"
        ) as urlopen, self.assertRaises(RuntimeError):
            classifier("这次讲解不错")
        urlopen.assert_not_called()

    def test_feedback_sentiment_classifier_rejects_invalid_structure(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"sentiment":"happy","confidence":2}'}}]}
        ).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False
        classifier = getattr(qwen_client, "classify_feedback_sentiment", None)
        self.assertTrue(callable(classifier), "Qwen 情绪分类器尚未实现")

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ), self.assertRaises(RuntimeError):
            classifier("这次体验还可以")

    def test_streaming_request_yields_openai_compatible_content_deltas(self) -> None:
        response = MagicMock()
        response.__iter__.return_value = iter(
            [
                b'data: {"choices":[{"delta":{"content":"\xe4\xb9\x9d\xe9\xbe\x99\xe7\x81\x8c\xe6\xb5\xb4"}}]}\n',
                b'data: {"choices":[{"delta":{}}]}\n',
                b'data: {"choices":[{"delta":{"content":"\xe5\xb9\xb3\xe6\x97\xa5\xe5\x8d\x81\xe7\x82\xb9\xe5\xbc\x80\xe5\xa7\x8b\xe3\x80\x82"}}]}\n',
                b"data: [DONE]\n",
            ]
        )
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ) as urlopen:
            deltas = list(
                iter_qwen_deltas(
                    "九龙灌浴几点开始？",
                    [{"title": "九龙灌浴", "source_file": "资料.docx", "content": "平日10:00开始"}],
                )
            )

        self.assertEqual(deltas, ["九龙灌浴", "平日十点开始。"])
        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertTrue(request_body["stream"])
        self.assertEqual(request_body["temperature"], 0.0)

    def test_prompt_requires_complete_numeric_facts_to_remain_verbatim(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "开放时间为 09:30-19:00。"}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ) as urlopen:
            call_qwen(
                "拈花堂的开放时间是什么？",
                [{"title": "拈花堂", "source_file": "资料.docx", "content": "开放时间：09:30-19:00"}],
            )

        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        system_prompt = request_body["messages"][0]["content"]
        self.assertIn("完整时间范围", system_prompt)
        self.assertIn("09:30-19:00", system_prompt)
        self.assertIn("开始或结束时间", system_prompt)
        self.assertEqual(request_body["temperature"], 0.0)

    def test_prompt_requires_named_entities_to_remain_explicit(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "资料中的专有名词保持完整。"}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ) as urlopen:
            call_qwen(
                "这个文化景观有什么特点？",
                [{"title": "文化景观", "source_file": "资料.docx", "content": "人物：资料中的完整专名"}],
            )

        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        system_prompt = request_body["messages"][0]["content"]
        self.assertIn("人物、地点、建筑等专有名词", system_prompt)
        self.assertIn("泛称", system_prompt)

    def test_sanitize_markdown_answer_removes_html_details(self) -> None:
        text = r"\#\#\# 路线说明<details><summary>资料依据</summary>- **位置**：入口</details>"

        cleaned = sanitize_markdown_answer(text)

        self.assertIn("### 路线说明", cleaned)
        self.assertIn("**资料依据**", cleaned)
        self.assertIn("- **位置**：入口", cleaned)
        self.assertNotIn("<details>", cleaned)
        self.assertNotIn("<summary>", cleaned)

    def test_published_persona_is_injected_into_the_system_prompt(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "欢迎来到灵山胜境。"}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        with patch("server.qwen_client.qwen_available", return_value=True), patch(
            "server.qwen_client.urllib.request.urlopen", return_value=context
        ) as urlopen:
            call_qwen(
                "介绍一下灵山大佛",
                [{"title": "灵山大佛", "source_file": "资料.docx", "content": "大佛资料"}],
                persona="你是温和、准确的灵山文化导游。",
            )

        request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertIn("你是温和、准确的灵山文化导游", request_body["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
