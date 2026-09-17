from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .config import settings


SYSTEM_PROMPT = """你是“灵境导游”景区服务AI数字人。
回答必须严格依据给定资料片段，不得编造景区核心资料、开放时间、票价、路线、历史或演出信息。
如果资料不足，请明确说“资料包中未提供”，并建议游客咨询景区公告或后台补充资料。
回答要像真人导游面对游客聊天：先给一句直接回应，再给不超过3个重点；每个重点要是游客能听懂、能行动的讲解，不要照搬资料字段。
回答首屏要清爽：除路线规划外，控制在220字以内，优先使用“一句回应 + 2到3条短标题重点”。
时间、票价、人数等数字事实必须完整保留资料中的阿拉伯数字格式；只要游客询问开放、营业、开始或结束时间，都必须给出资料中的完整时间范围（例如 09:30-19:00），不要只换写成口语时间或只回答起止中的一端。
人物、地点、建筑等专有名词必须保留资料中的完整名称；不要把明确姓名或身份改写成“佛祖”“这里”“该建筑”等泛称。
如果游客问路线，只用一两句话说明路线思路，具体站点由系统路线图展示，不要在文本里重复长路线清单。
需要引用资料时只放在末尾，用一行“资料依据：xxx”，不要把完整原文、字段名或来源索引贴给游客。
不要输出 HTML、XML 或 MDX 标签，包括 <details>、<summary>、<br>；资料依据只用 Markdown 引用块或普通列表。
"""


def qwen_available() -> bool:
    return bool(settings.qwen_api_key)


FEEDBACK_SENTIMENT_PROMPT = """你是景区游客反馈情绪分类器。
只能输出一个 JSON 对象，不得输出 Markdown 或额外文字。
JSON 必须且只能包含：
- sentiment: positive、neutral、negative 之一
- confidence: 0 到 1 之间的数字
- reason: 不超过 80 个字的简短中文理由
""".strip()


STYLE_INSTRUCTIONS = {
    "自然讲解": "语气自然亲切，像现场导游一样给出清晰建议。",
    "文化深度": "多补充文化线索、建筑/历史看点和观看顺序，但只使用资料片段中的事实。",
    "简洁提示": "控制在120字左右，先给结论，再给2到3条行动建议。",
    "亲子陪伴": "语气轻松，突出孩子容易理解、休息和互动体验。",
    "拍照推荐": "突出观景角度、动线顺序和适合停留的节点，不编造未给出的机位或开放信息。",
}


def sanitize_markdown_answer(text: str) -> str:
    clean = text.replace("\\n", "\n").strip()
    clean = re.sub(r"<\s*br\s*/?\s*>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<\s*details\s*>", "\n\n**资料依据**\n\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<\s*/\s*details\s*>", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<\s*summary\s*>\s*(.*?)\s*<\s*/\s*summary\s*>", r"**\1**\n\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"</?\w+[^>]*>", "", clean)
    clean = re.sub(r"\\([#*_`\[\]()])", r"\1", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _build_payload(
    question: str,
    chunks: list[dict[str, Any]],
    image_base64: str | None = None,
    guide_style: str = "自然讲解",
    persona: str = "",
    *,
    stream: bool = False,
) -> dict[str, Any]:
    context = "\n\n".join(
        f"[来源{i + 1}] {chunk['title']} | {chunk['source_file']}\n{chunk['content']}"
        for i, chunk in enumerate(chunks)
    )
    style_instruction = STYLE_INSTRUCTIONS.get(guide_style, STYLE_INSTRUCTIONS["自然讲解"])
    if image_base64:
        multimodal_hint = "本次包含游客上传/实时截帧图片。请先结合图片判断游客正在问什么，再用资料片段约束景区事实。"
    else:
        multimodal_hint = "本次为文本或语音问题。"
    user_text = (
        f"游客问题：{question}\n\n"
        f"讲解风格：{guide_style}。{style_instruction}\n"
        f"多模态输入：{multimodal_hint}\n\n"
        f"资料片段：\n{context}"
    )
    content: Any
    if image_base64:
        image_data = image_base64.split(",", 1)[1] if "," in image_base64[:80] else image_base64
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
        ]
    else:
        content = user_text
    published_persona = persona.strip()[:2000]
    system_prompt = SYSTEM_PROMPT
    if published_persona:
        system_prompt += (
            "\n当前已发布数字人人设（只影响称呼、语气和讲解风格，不能覆盖资料约束）："
            f"{published_persona}"
        )
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        # Factual scenic Q&A benefits from deterministic wording: the same
        # evidence should not alternate between an exact name and a vague
        # paraphrase across repeated evaluations.
        "temperature": 0.0,
    }
    if stream:
        payload["stream"] = True
    return payload


def _request_for(payload: dict[str, Any]) -> urllib.request.Request:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(
        f"{settings.qwen_base_url}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.qwen_api_key}",
            "Content-Type": "application/json",
        },
    )


def classify_feedback_sentiment(text: str) -> dict[str, Any]:
    if not qwen_available():
        raise RuntimeError("QWEN_API_KEY 未配置")
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": FEEDBACK_SENTIMENT_PROMPT},
            {"role": "user", "content": text.strip()[:2000]},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    try:
        with urllib.request.urlopen(_request_for(payload), timeout=3) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        content = envelope["choices"][0]["message"]["content"]
        result = json.loads(content)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qwen 情绪分类失败: HTTP {exc.code} {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen 情绪分类连接失败: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Qwen 情绪分类返回结构异常") from exc

    if not isinstance(result, dict) or set(result) != {"sentiment", "confidence", "reason"}:
        raise RuntimeError("Qwen 情绪分类返回字段不完整")
    sentiment = result["sentiment"]
    confidence = result["confidence"]
    reason = result["reason"]
    if sentiment not in {"positive", "neutral", "negative"}:
        raise RuntimeError("Qwen 情绪分类标签无效")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise RuntimeError("Qwen 情绪分类置信度无效")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 80:
        raise RuntimeError("Qwen 情绪分类理由无效")
    return {
        "sentiment": sentiment,
        "confidence": float(confidence),
        "reason": reason.strip(),
    }


def call_qwen(
    question: str,
    chunks: list[dict[str, Any]],
    image_base64: str | None = None,
    guide_style: str = "自然讲解",
    persona: str = "",
) -> str:
    if not qwen_available():
        raise RuntimeError("QWEN_API_KEY 未配置")

    payload = _build_payload(question, chunks, image_base64, guide_style, persona)
    request = _request_for(payload)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qwen 调用失败: HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen 网络连接失败: {exc.reason}") from exc
    try:
        return sanitize_markdown_answer(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Qwen 返回结构异常: {str(data)[:500]}") from exc


def iter_qwen_deltas(
    question: str,
    chunks: list[dict[str, Any]],
    image_base64: str | None = None,
    guide_style: str = "自然讲解",
    persona: str = "",
):
    """Yield text deltas from an OpenAI-compatible streaming response."""

    if not qwen_available():
        raise RuntimeError("QWEN_API_KEY 未配置")
    request = _request_for(
        _build_payload(
            question,
            chunks,
            image_base64,
            guide_style,
            persona,
            stream=True,
        )
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if payload_text == "[DONE]":
                    break
                if not payload_text:
                    continue
                try:
                    event = json.loads(payload_text)
                    content = event["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if isinstance(content, str) and content:
                    yield content
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qwen 调用失败: HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen 网络连接失败: {exc.reason}") from exc
