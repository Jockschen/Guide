from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .db import connect, json_load
from .text_utils import cosine, hash_embedding, keyword_score


def _rows_to_chunks(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for row in rows:
        chunks.append(
            {
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "source_file": row["source_file"],
                "source_type": row["source_type"],
                "metadata": json_load(row["metadata_json"], {}),
                "score": 0.0,
            }
        )
    return chunks


def retrieve(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query_embedding = hash_embedding(query)
    conn = connect()
    try:
        keyword_rows: list[sqlite3.Row] = []
        try:
            keyword_rows = conn.execute(
                """
                SELECT kc.*
                FROM knowledge_fts fts
                JOIN knowledge_chunks kc ON kc.id = fts.chunk_id
                WHERE knowledge_fts MATCH ?
                LIMIT 20
                """,
                (query,),
            ).fetchall()
        except sqlite3.OperationalError:
            keyword_rows = []

        all_rows = conn.execute(
            "SELECT id,source_file,source_type,title,content,metadata_json,embedding_json FROM knowledge_chunks"
        ).fetchall()
    finally:
        conn.close()

    scored: dict[int, dict[str, Any]] = {}
    keyword_ids = {row["id"] for row in keyword_rows}
    for row in all_rows:
        embedding = json.loads(row["embedding_json"] or "[]")
        content = f'{row["title"]}\n{row["content"]}'
        score = cosine(query_embedding, embedding) * 0.72 + keyword_score(query, content) * 0.28
        if row["id"] in keyword_ids:
            score += 0.18
        title_name = row["title"].split("（", 1)[0]
        if title_name and title_name in query:
            score += 0.26
            if row["source_type"] == "attraction":
                score += 0.18
        if any(term in query for term in ["表演", "演出", "开放", "时间"]) and "演艺/开放信息" in row["content"]:
            score += 0.08
        scored[row["id"]] = {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "source_file": row["source_file"],
            "source_type": row["source_type"],
            "metadata": json_load(row["metadata_json"], {}),
            "score": round(score, 4),
        }

    return sorted(scored.values(), key=lambda item: item["score"], reverse=True)[:limit]


STYLE_OPENINGS = {
    "自然讲解": "可以，我来给你讲得清楚一点。",
    "文化深度": "可以，这里适合放慢脚步看文化线索。",
    "简洁提示": "可以，先给你抓重点。",
    "亲子陪伴": "可以，这一站很适合边看边给孩子讲故事。",
    "拍照推荐": "可以，这里可以按“先看整体、再找细节”的方式拍。",
}


def _field(content: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}[：:]\s*(.*?)(?=\n\S+?[：:]|$)", content, flags=re.S)
    if not match:
        return ""
    return _tidy(match.group(1))


def _tidy(value: str, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", value).strip(" ；;。")
    if len(clean) <= limit:
        return clean
    sentence = re.match(r"^(.{20,}?[。！？；;])", clean)
    if sentence and len(sentence.group(1)) <= limit + 20:
        return sentence.group(1).rstrip("。；;")
    return clean[:limit].rstrip("，、；;。") + "。"


def _spot_name(chunk: dict[str, Any]) -> str:
    return _field(chunk["content"], "景点名称") or str(chunk["title"]).split("（", 1)[0]


def local_answer(question: str, chunks: list[dict[str, Any]], guide_style: str = "自然讲解") -> str:
    if not chunks or chunks[0]["score"] < 0.08:
        return "资料包中没有找到足够依据回答这个问题。你可以换一种问法，或在后台上传补充资料后重建知识库。"
    lead = chunks[0]
    supporting = chunks[1:3]
    content = lead["content"]
    name = _spot_name(lead)
    location = _field(content, "具体位置")
    highlights = _field(content, "游玩亮点") or _field(content, "核心功能") or _field(content, "详细介绍")
    culture = _field(content, "文化内涵")
    opening = _field(content, "演艺/开放信息") or _field(content, "开放信息")
    opening = opening or _tidy(content, 120)

    if guide_style == "简洁提示":
        bullets = [("开放安排", opening), ("推荐看点", highlights), ("怎么到达", location)]
    elif guide_style == "文化深度":
        bullets = [("文化线索", culture), ("推荐看点", highlights), ("开放安排", opening)]
    elif guide_style == "亲子陪伴":
        bullets = [("孩子看点", highlights), ("开放安排", opening), ("轻松走法", location)]
    elif guide_style == "拍照推荐":
        bullets = [("拍照重点", highlights), ("站位方向", location), ("开放安排", opening)]
    else:
        bullets = [("什么时候去", opening), ("看什么", highlights), ("顺路了解", culture or location)]
    bullets = [(label, value) for label, value in bullets if value][:3]

    opening_text = STYLE_OPENINGS.get(guide_style, STYLE_OPENINGS["自然讲解"])
    answer_parts = [f"{opening_text} **{name}** 这一站可以这样看："]
    if bullets:
        answer_parts.append("\n".join(f"- **{label}**：{value}" for label, value in bullets))
    if supporting:
        related = "、".join(_spot_name(item) for item in supporting if _spot_name(item))
        if related:
            answer_parts.append(f"你还可以顺路问我：{related}。")
    answer_parts.append(f"> 资料依据：{lead['title']}（{lead['source_file']}）。以上内容仅来自本地资料包，未补编资料包未提供的景区事实。")
    return "\n\n".join(answer_parts)


def list_faqs(limit: int = 24) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id,question,answer,source_title,source_file,tags_json FROM faqs ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "source_title": row["source_title"],
            "source_file": row["source_file"],
            "tags": json_load(row["tags_json"], []),
        }
        for row in rows
    ]


def _normalize_faq_text(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).casefold()


FAQ_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "位置": ("在哪", "哪里", "位置", "怎么走", "如何到达"),
    "开放信息": ("开放", "演出", "演艺", "表演", "几点", "时间", "时段", "什么时候", "营业", "免费讲解"),
    "文化": ("文化", "历史", "寓意", "象征", "由来", "代表", "复刻", "原型", "仿照", "取自"),
    "游玩亮点": ("怎么玩", "亮点", "看什么", "拍照", "值得看"),
    "功能": ("核心功能", "功能", "作用", "用途"),
}


def _faq_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "source_title": row["source_title"],
        "source_file": row["source_file"],
        "tags": json_load(row["tags_json"], []),
    }


def _faq_entity(source_title: str) -> str:
    return re.split(r"[（(]", source_title, maxsplit=1)[0].strip()


def match_faq(question: str) -> dict[str, Any] | None:
    """Return a FAQ only when the visitor question can be matched safely."""

    normalized = _normalize_faq_text(question)
    if not normalized:
        return None
    if re.search(r"(?:哪个|哪些).{0,12}(?:景点|体验点|节点|地方)", normalized):
        return None
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id,question,answer,source_title,source_file,tags_json FROM faqs ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        if _normalize_faq_text(row["question"]) == normalized:
            return _faq_row(row)

    entities = {
        entity
        for row in rows
        if (entity := _faq_entity(row["source_title"]))
        and _normalize_faq_text(entity) in normalized
    }
    intent_text = normalized
    for entity in entities:
        intent_text = intent_text.replace(_normalize_faq_text(entity), "", 1)
    intents = {
        intent
        for intent, keywords in FAQ_INTENT_KEYWORDS.items()
        if any(_normalize_faq_text(keyword) in intent_text for keyword in keywords)
    }
    if len(entities) != 1 or len(intents) != 1:
        return None
    entity = next(iter(entities))
    intent = next(iter(intents))
    candidates = [
        row
        for row in rows
        if _faq_entity(row["source_title"]) == entity
        and intent in json_load(row["tags_json"], [])
    ]
    return _faq_row(candidates[0]) if len(candidates) == 1 else None
