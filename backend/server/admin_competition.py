from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, status

from .config import settings
from .db import connect, json_dump, json_load, row_to_dict
from .quality_evaluation import quality_run_payload, run_frozen_evaluation
from .qwen_client import classify_feedback_sentiment
from .schemas import (
    DigitalHumanPreviewRequest,
    DigitalHumanProfileCreate,
    DigitalHumanProfileVersionCreate,
    FeedbackManagementUpdate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    QualityRunCreate,
    TextFeedbackCreate,
    VoicePreviewRequest,
)


ADMIN_PREFIX = "/api/admin/competition"
DEFAULT_E2E_LATENCY_REPORT = (
    Path(__file__).resolve().parents[2]
    / "reports"
    / "quality"
    / "e2e-latency-latest.json"
)
PROFILE_FIELDS = (
    "name",
    "persona",
    "driver_provider",
    "avatar_asset_url",
    "clothing_asset_url",
    "clothing_version",
    "voice",
    "source_video_url",
    "source_video_kind",
    "opentalking_avatar_id",
    "prewarm_status",
)
DRIVER_PROVIDERS = {
    "opentalking",
    "flashtalk",
    "flashhead",
    "legacy_mp4",
    "audio_only",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _profile_from_row(row: Any, active_id: int | None = None) -> dict[str, Any]:
    data = row_to_dict(row)
    data["is_active"] = active_id is not None and data["id"] == active_id
    return data


def _session_enabled() -> bool:
    return os.getenv("OPENTALKING_SESSION_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _session_avatar_id() -> str:
    return (
        os.getenv("OPENTALKING_SESSION_AVATAR_ID", "").strip()
        or settings.opentalking_avatar_id
    )


def _legacy_profile(row: Any | None) -> dict[str, Any]:
    if row:
        legacy = row_to_dict(row)
        configured_mode = str(legacy.get("avatar_mode") or "")
        if _session_enabled():
            driver_provider = "opentalking"
        elif configured_mode in DRIVER_PROVIDERS:
            driver_provider = configured_mode
        else:
            driver_provider = "audio_only"
        return {
            "id": None,
            "profile_key": "legacy-config",
            "version": 0,
            "name": legacy.get("name") or "灵境导游",
            "persona": legacy.get("persona") or "温和、准确的景区数字人导游",
            "driver_provider": driver_provider,
            "avatar_asset_url": "",
            "clothing_asset_url": "",
            "clothing_version": "legacy",
            "voice": legacy.get("voice") or settings.vivo_tts_voice,
            "source_video_url": "",
            "source_video_kind": "still_image_fallback",
            "opentalking_avatar_id": _session_avatar_id(),
            "prewarm_status": "unavailable",
            "status": "legacy",
            "previewed_at": None,
            "published_at": None,
            "created_at": legacy.get("updated_at"),
            "updated_at": legacy.get("updated_at"),
            "is_active": True,
            "resolution_source": "legacy_config",
        }
    return {
        "id": None,
        "profile_key": "runtime-default",
        "version": 0,
        "name": "灵境导游",
        "persona": "温和、准确、只依据景区资料回答的数字人导游",
        "driver_provider": (
            "opentalking"
            if _session_enabled() or settings.opentalking_base_url
            else "audio_only"
        ),
        "avatar_asset_url": "",
        "clothing_asset_url": "",
        "clothing_version": "default",
        "voice": settings.vivo_tts_voice,
        "source_video_url": "",
        "source_video_kind": "still_image_fallback",
        "opentalking_avatar_id": _session_avatar_id(),
        "prewarm_status": "pending" if settings.opentalking_base_url else "unavailable",
        "status": "default",
        "previewed_at": None,
        "published_at": None,
        "created_at": None,
        "updated_at": None,
        "is_active": True,
        "resolution_source": "runtime_defaults",
    }


def get_active_digital_human_profile(db_path: Path | None = None) -> dict[str, Any]:
    """Resolve the published profile, falling back to the legacy singleton config.

    The returned mapping is intentionally stable for the TTS, visitor-introduction,
    and OpenTalking session layers. Passing ``db_path`` is supported for isolated
    tests; production callers should use the no-argument form after ``init_db``.
    """

    conn = connect(db_path)
    try:
        active = conn.execute(
            """
            SELECT p.*
            FROM digital_human_active a
            JOIN digital_human_profiles p ON p.id=a.profile_id
            WHERE a.id=1
            """
        ).fetchone()
        if active:
            data = _profile_from_row(active, int(active["id"]))
            data["resolution_source"] = "published_profile"
            return data
        legacy = conn.execute("SELECT * FROM digital_human_config WHERE id=1").fetchone()
        return _legacy_profile(legacy)
    finally:
        conn.close()


def _get_profile(conn: Any, profile_id: int) -> Any:
    row = conn.execute("SELECT * FROM digital_human_profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="数字人版本不存在。")
    return row


def _active_profile_id(conn: Any) -> int | None:
    row = conn.execute("SELECT profile_id FROM digital_human_active WHERE id=1").fetchone()
    return int(row["profile_id"]) if row else None


def _get_document(conn: Any, document_id: int, *, allow_deleted: bool = False) -> Any:
    row = conn.execute("SELECT * FROM knowledge_documents WHERE id=?", (document_id,)).fetchone()
    if not row or (row["status"] == "deleted" and not allow_deleted):
        raise HTTPException(status_code=404, detail="知识文档不存在。")
    return row


def _document_from_row(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["document_kind"] = "managed_document"
    data["editable"] = True
    return data


def _source_document_from_row(row: Any) -> dict[str, Any]:
    """Expose the immutable local scenic package beside managed documents."""

    chunk_count = int(row["chunk_count"] or 0)
    records_count = int(row["records_count"] or 0)
    is_loaded = chunk_count > 0 or records_count > 0
    imported_at = str(row["imported_at"] or "")
    content_label = (
        f"本地资料包 · {row['file_type']} · {records_count} 条运营数据"
        if records_count
        else f"本地资料包 · {row['file_type']} · {chunk_count} 个检索分片"
    )
    return {
        # Negative ids keep the existing numeric UI contract while preventing
        # accidental writes to the managed knowledge_documents table.
        "id": -int(row["id"]),
        "source_file_id": int(row["id"]),
        "title": row["name"],
        "content": content_label,
        "source_name": "示范景区公开资料包",
        "status": "active",
        "content_version": 1,
        "index_version": 1 if is_loaded else 0,
        "index_status": "indexed" if is_loaded else "pending",
        "created_at": imported_at,
        "updated_at": imported_at,
        "indexed_at": imported_at if is_loaded else None,
        "deleted_at": None,
        "document_kind": "source_file",
        "editable": False,
        "file_type": row["file_type"],
        "records_count": records_count,
        "chunk_count": chunk_count,
    }


def _remove_document_chunks(conn: Any, document_id: int) -> None:
    chunk_ids = [
        int(row["id"])
        for row in conn.execute(
            "SELECT id FROM knowledge_chunks WHERE knowledge_document_id=?", (document_id,)
        ).fetchall()
    ]
    for chunk_id in chunk_ids:
        conn.execute("DELETE FROM knowledge_fts WHERE chunk_id=?", (chunk_id,))
    conn.execute("DELETE FROM knowledge_chunks WHERE knowledge_document_id=?", (document_id,))


def _feedback_from_row(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["topics"] = json_load(data.pop("topics_json"), [])
    return data


def _infer_sentiment(text: str, rating: int | None) -> str:
    if rating is not None:
        if rating <= 2:
            return "negative"
        if rating >= 4:
            return "positive"
    negative_words = ("太久", "拥挤", "不清楚", "错误", "不好", "失望", "卡顿", "听不清")
    positive_words = ("很好", "清楚", "喜欢", "方便", "满意", "有帮助", "很棒")
    if any(word in text for word in negative_words):
        return "negative"
    if any(word in text for word in positive_words):
        return "positive"
    return "neutral"


def _classify_feedback(
    text: str, rating: int | None, explicit_sentiment: str | None
) -> tuple[str, str, float]:
    if explicit_sentiment is not None:
        return explicit_sentiment, "manual", 1.0
    try:
        classified = classify_feedback_sentiment(text)
        return (
            str(classified["sentiment"]),
            "qwen",
            float(classified["confidence"]),
        )
    except Exception:
        source = "rating" if rating is not None else "rules"
        confidence = 1.0 if rating is not None else 0.6
        return _infer_sentiment(text, rating), source, confidence


TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("crowding", ("排队", "拥挤", "人多", "等候", "太久")),
    ("navigation", ("路线", "指引", "地图", "迷路", "怎么走", "位置")),
    ("content", ("讲解", "回答", "知识", "不清楚", "错误", "介绍")),
    ("digital_human", ("数字人", "口型", "声音", "语音", "画面", "卡顿")),
    ("service", ("服务", "工作人员", "客服")),
    ("accessibility", ("老人", "儿童", "轮椅", "无障碍")),
)


def _infer_topics(text: str) -> list[str]:
    topics = [topic for topic, keywords in TOPIC_KEYWORDS if any(word in text for word in keywords)]
    return topics or ["other"]


def _default_recommendation(topics: list[str]) -> str:
    suggestions = {
        "crowding": "结合高峰客流增加分流与等候时间提示。",
        "navigation": "复核游线地图、当前位置和现场导视的一致性。",
        "content": "复核讲解内容、引用来源和表达清晰度。",
        "digital_human": "检查语音、口型与流媒体降级链路。",
        "service": "转交游客服务团队跟进。",
        "accessibility": "补充老人、儿童和无障碍游览提示。",
        "other": "由运营人员阅读原始反馈后补充处理建议。",
    }
    return " ".join(suggestions[topic] for topic in topics if topic in suggestions)


def _feedback_feeling(rating: int | None, sentiment: str) -> str:
    if rating is not None:
        if rating >= 5:
            return "满意"
        if rating == 4:
            return "有帮助"
        if rating == 3:
            return "一般"
        return "待改进"
    if sentiment == "positive":
        return "满意"
    if sentiment == "negative":
        return "待改进"
    return "一般"


def _sync_qa_log_feedback(
    conn: Any,
    log_id: int | None,
    rating: int | None,
    sentiment: str,
    text: str,
) -> None:
    if log_id is None:
        return
    row = conn.execute("SELECT rating FROM qa_logs WHERE id=?", (log_id,)).fetchone()
    if not row:
        return
    effective_rating = rating if rating is not None else row["rating"]
    conn.execute(
        "UPDATE qa_logs SET rating=?,feeling=?,note=? WHERE id=?",
        (
            effective_rating,
            _feedback_feeling(effective_rating, sentiment),
            text,
            log_id,
        ),
    )


def _backfill_legacy_feedback(conn: Any) -> None:
    rows = conn.execute(
        """
        SELECT q.id,q.rating,q.note,q.created_at
        FROM qa_logs q
        WHERE q.rating IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.log_id=q.id)
        ORDER BY q.id
        """
    ).fetchall()
    now = _now()
    for row in rows:
        text = str(row["note"] or "").strip() or "仅提交星级评价"
        rating = int(row["rating"])
        sentiment = _infer_sentiment(text, rating)
        topics = _infer_topics(text)
        conn.execute(
            """
            INSERT INTO feedback(
              log_id,rating,text,sentiment,sentiment_source,sentiment_confidence,
              topics_json,status,recommendation,
              management_note,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,'pending',?,'',?,?)
            """,
            (
                int(row["id"]),
                rating,
                text,
                sentiment,
                "rating",
                1.0,
                json_dump(topics),
                _default_recommendation(topics),
                row["created_at"],
                now,
            ),
        )


def _quality_from_row(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["sample_details"] = json_load(data.pop("sample_details_json"), [])
    data["latency_ms"] = json_load(data.pop("latency_ms_json"), {})
    data["environment"] = json_load(data.pop("environment_json"), {})
    data["official_evaluation"] = bool(data["official_evaluation"])
    data["scope_label"] = "带凭证的官方评测数据" if data["official_evaluation"] else "本地自测数据"
    data["acceptance_note"] = (
        "已记录官方评测凭证，仍以比赛组织方最终结果为准。"
        if data["official_evaluation"]
        else "本地冻结数据集结果，不代表比赛官方评测。"
    )
    return data


def create_admin_competition_router(
    db_path: Path | None = None,
    quality_evaluator: Callable[[], dict[str, Any]] | None = None,
    e2e_latency_report_path: Path | None = None,
) -> APIRouter:
    router = APIRouter(tags=["admin-competition"])

    @router.get(f"{ADMIN_PREFIX}/digital-human/profiles")
    def list_profiles() -> dict[str, Any]:
        conn = connect(db_path)
        try:
            active_id = _active_profile_id(conn)
            rows = conn.execute(
                "SELECT * FROM digital_human_profiles ORDER BY profile_key, version DESC, id DESC"
            ).fetchall()
            return {"ok": True, "data": [_profile_from_row(row, active_id) for row in rows]}
        finally:
            conn.close()

    @router.post(
        f"{ADMIN_PREFIX}/digital-human/profiles", status_code=status.HTTP_201_CREATED
    )
    def create_profile(payload: DigitalHumanProfileCreate) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            latest = conn.execute(
                "SELECT COALESCE(MAX(version),0) FROM digital_human_profiles WHERE profile_key=?",
                (payload.profile_key,),
            ).fetchone()[0]
            values = payload.model_dump()
            cursor = conn.execute(
                """
                INSERT INTO digital_human_profiles(
                  profile_key,version,name,persona,driver_provider,avatar_asset_url,
                  clothing_asset_url,clothing_version,voice,source_video_url,
                  source_video_kind,opentalking_avatar_id,prewarm_status,status,
                  created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)
                """,
                (
                    values["profile_key"],
                    int(latest) + 1,
                    *(values[field] for field in PROFILE_FIELDS),
                    now,
                    now,
                ),
            )
            profile_id = int(cursor.lastrowid)
            conn.commit()
            row = _get_profile(conn, profile_id)
            return {"ok": True, "data": _profile_from_row(row, _active_profile_id(conn))}
        finally:
            conn.close()

    @router.post(
        f"{ADMIN_PREFIX}/digital-human/profiles/{{profile_id}}/versions",
        status_code=status.HTTP_201_CREATED,
    )
    def create_profile_version(
        profile_id: int, payload: DigitalHumanProfileVersionCreate
    ) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            base = row_to_dict(_get_profile(conn, profile_id))
            overrides = payload.model_dump(exclude_unset=True)
            snapshot = {field: overrides.get(field, base[field]) for field in PROFILE_FIELDS}
            if snapshot["source_video_kind"] == "real_source_video" and not str(
                snapshot["source_video_url"]
            ).strip():
                raise HTTPException(
                    status_code=422,
                    detail="source_video_url is required for real_source_video",
                )
            latest = conn.execute(
                "SELECT COALESCE(MAX(version),0) FROM digital_human_profiles WHERE profile_key=?",
                (base["profile_key"],),
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO digital_human_profiles(
                  profile_key,version,name,persona,driver_provider,avatar_asset_url,
                  clothing_asset_url,clothing_version,voice,source_video_url,
                  source_video_kind,opentalking_avatar_id,prewarm_status,status,
                  created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)
                """,
                (
                    base["profile_key"],
                    int(latest) + 1,
                    *(snapshot[field] for field in PROFILE_FIELDS),
                    now,
                    now,
                ),
            )
            new_id = int(cursor.lastrowid)
            conn.commit()
            return {
                "ok": True,
                "data": _profile_from_row(
                    _get_profile(conn, new_id), _active_profile_id(conn)
                ),
            }
        finally:
            conn.close()

    @router.post(f"{ADMIN_PREFIX}/digital-human/profiles/{{profile_id}}/preview")
    def preview_profile(
        profile_id: int, payload: DigitalHumanPreviewRequest
    ) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            row = _get_profile(conn, profile_id)
            conn.execute(
                "UPDATE digital_human_profiles SET previewed_at=?,updated_at=? WHERE id=?",
                (now, now, profile_id),
            )
            conn.commit()
            profile = _profile_from_row(_get_profile(conn, profile_id), _active_profile_id(conn))
            real_source = profile["source_video_kind"] == "real_source_video"
            return {
                "ok": True,
                "data": {
                    "profile": profile,
                    "preview": {
                        "status": "configuration_ready",
                        "rendered": False,
                        "sample_text": payload.sample_text,
                        "voice": row["voice"],
                        "driver_provider": row["driver_provider"],
                        "real_neutral_motion_source": real_source,
                        "asset_label": "授权源视频形象" if real_source else "静态形象兼容兜底",
                        "message": "配置已就绪；实际音视频预览由 TTS 与数字人会话链路生成。",
                    },
                },
            }
        finally:
            conn.close()

    @router.post(f"{ADMIN_PREFIX}/digital-human/profiles/{{profile_id}}/voice-preview")
    def preview_voice(profile_id: int, payload: VoicePreviewRequest) -> dict[str, Any]:
        conn = connect(db_path)
        try:
            row = _get_profile(conn, profile_id)
            return {
                "ok": True,
                "data": {
                    "profile_id": profile_id,
                    "status": "ready_for_synthesis",
                    "synthesis_request": {"text": payload.text, "voice": row["voice"]},
                    "message": "调用现有 TTS 接口生成试听音频。",
                },
            }
        finally:
            conn.close()

    @router.post(f"{ADMIN_PREFIX}/digital-human/profiles/{{profile_id}}/publish")
    def publish_profile(profile_id: int) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            _get_profile(conn, profile_id)
            conn.execute(
                """
                UPDATE digital_human_profiles
                SET status='published',published_at=COALESCE(published_at,?),updated_at=?
                WHERE id=?
                """,
                (now, now, profile_id),
            )
            conn.execute(
                """
                INSERT INTO digital_human_active(id,profile_id,activated_at)
                VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  profile_id=excluded.profile_id,
                  activated_at=excluded.activated_at
                """,
                (profile_id, now),
            )
            conn.commit()
            return {
                "ok": True,
                "data": _profile_from_row(_get_profile(conn, profile_id), profile_id),
                "message": "数字人版本已发布并设为当前生效版本。",
            }
        finally:
            conn.close()

    @router.get(f"{ADMIN_PREFIX}/digital-human/active")
    def active_profile() -> dict[str, Any]:
        return {"ok": True, "data": get_active_digital_human_profile(db_path)}

    @router.get(f"{ADMIN_PREFIX}/knowledge/documents")
    def list_documents(include_deleted: bool = False) -> dict[str, Any]:
        conn = connect(db_path)
        try:
            where = "" if include_deleted else "WHERE status<>'deleted'"
            rows = conn.execute(
                f"SELECT * FROM knowledge_documents {where} ORDER BY updated_at DESC,id DESC"
            ).fetchall()
            source_rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.source_file=s.name) AS chunk_count
                FROM source_files s
                ORDER BY s.imported_at DESC,s.id DESC
                """
            ).fetchall()
            data = [_source_document_from_row(row) for row in source_rows]
            data.extend(_document_from_row(row) for row in rows)
            data.sort(key=lambda item: (str(item.get("updated_at") or ""), int(item["id"])), reverse=True)
            return {"ok": True, "data": data}
        finally:
            conn.close()

    @router.post(
        f"{ADMIN_PREFIX}/knowledge/documents", status_code=status.HTTP_201_CREATED
    )
    def create_document(payload: KnowledgeDocumentCreate) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO knowledge_documents(
                  title,content,source_name,status,content_version,index_version,
                  index_status,created_at,updated_at
                ) VALUES(?,?,?,'active',1,0,'pending',?,?)
                """,
                (payload.title, payload.content, payload.source_name, now, now),
            )
            document_id = int(cursor.lastrowid)
            conn.commit()
            return {
                "ok": True,
                "data": _document_from_row(_get_document(conn, document_id)),
            }
        finally:
            conn.close()

    @router.put(f"{ADMIN_PREFIX}/knowledge/documents/{{document_id}}")
    def update_document(
        document_id: int, payload: KnowledgeDocumentUpdate
    ) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            current = row_to_dict(_get_document(conn, document_id))
            updates = payload.model_dump(exclude_unset=True)
            next_values = {
                "title": updates.get("title", current["title"]),
                "content": updates.get("content", current["content"]),
                "source_name": updates.get("source_name", current["source_name"]),
            }
            conn.execute(
                """
                UPDATE knowledge_documents
                SET title=?,content=?,source_name=?,content_version=content_version+1,
                    index_status='pending',updated_at=?
                WHERE id=?
                """,
                (
                    next_values["title"],
                    next_values["content"],
                    next_values["source_name"],
                    now,
                    document_id,
                ),
            )
            conn.commit()
            return {
                "ok": True,
                "data": _document_from_row(_get_document(conn, document_id)),
            }
        finally:
            conn.close()

    @router.post(f"{ADMIN_PREFIX}/knowledge/documents/{{document_id}}/reindex")
    def reindex_document(document_id: int) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            document = row_to_dict(_get_document(conn, document_id))
            conn.execute(
                "UPDATE knowledge_documents SET index_status='indexing',updated_at=? WHERE id=?",
                (now, document_id),
            )
            _remove_document_chunks(conn, document_id)
            metadata = {
                "knowledge_document_id": document_id,
                "content_version": document["content_version"],
                "managed_by": "competition_admin",
            }
            cursor = conn.execute(
                """
                INSERT INTO knowledge_chunks(
                  source_file,source_type,title,content,metadata_json,embedding_json,
                  knowledge_document_id
                ) VALUES(?,?,?,?,?,NULL,?)
                """,
                (
                    document["source_name"],
                    "admin_knowledge",
                    document["title"],
                    document["content"],
                    json_dump(metadata),
                    document_id,
                ),
            )
            chunk_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO knowledge_fts(title,content,chunk_id) VALUES(?,?,?)",
                (document["title"], document["content"], chunk_id),
            )
            conn.execute(
                """
                UPDATE knowledge_documents
                SET index_version=content_version,index_status='indexed',indexed_at=?,updated_at=?
                WHERE id=?
                """,
                (now, now, document_id),
            )
            conn.commit()
            return {
                "ok": True,
                "data": _document_from_row(_get_document(conn, document_id)),
                "message": "知识文档已重新索引。",
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @router.delete(f"{ADMIN_PREFIX}/knowledge/documents/{{document_id}}")
    def delete_document(document_id: int) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            _get_document(conn, document_id)
            _remove_document_chunks(conn, document_id)
            conn.execute(
                """
                UPDATE knowledge_documents
                SET status='deleted',index_status='deleted',deleted_at=?,updated_at=?
                WHERE id=?
                """,
                (now, now, document_id),
            )
            conn.commit()
            row = _get_document(conn, document_id, allow_deleted=True)
            return {
                "ok": True,
                "data": _document_from_row(row),
                "message": "知识文档及其索引已删除。",
            }
        finally:
            conn.close()

    @router.post("/api/feedback/text", status_code=status.HTTP_201_CREATED)
    def create_text_feedback(payload: TextFeedbackCreate) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            qa_log = None
            if payload.log_id is not None:
                qa_log = conn.execute(
                    "SELECT id,rating FROM qa_logs WHERE id=?", (payload.log_id,)
                ).fetchone()
                if not qa_log:
                    raise HTTPException(status_code=404, detail="问答记录不存在。")
            existing = None
            if payload.log_id is not None:
                existing = conn.execute(
                    """
                    SELECT * FROM feedback
                    WHERE log_id=? AND status<>'resolved'
                    ORDER BY created_at DESC,id DESC LIMIT 1
                    """,
                    (payload.log_id,),
                ).fetchone()
            effective_rating = payload.rating
            if effective_rating is None and qa_log is not None:
                effective_rating = qa_log["rating"]
            if effective_rating is None and existing is not None:
                effective_rating = existing["rating"]
            topics = list(dict.fromkeys(payload.topics or _infer_topics(payload.text)))
            sentiment, sentiment_source, sentiment_confidence = _classify_feedback(
                payload.text, effective_rating, payload.sentiment
            )
            recommendation = _default_recommendation(topics)
            if existing:
                conn.execute(
                    """
                    UPDATE feedback
                    SET rating=?,text=?,sentiment=?,sentiment_source=?,sentiment_confidence=?,
                        topics_json=?,recommendation=?,
                        updated_at=?
                    WHERE id=?
                    """,
                    (
                        effective_rating,
                        payload.text,
                        sentiment,
                        sentiment_source,
                        sentiment_confidence,
                        json_dump(topics),
                        recommendation,
                        now,
                        int(existing["id"]),
                    ),
                )
                _sync_qa_log_feedback(
                    conn, payload.log_id, effective_rating, sentiment, payload.text
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM feedback WHERE id=?", (int(existing["id"]),)
                ).fetchone()
                return {
                    "ok": True,
                    "data": _feedback_from_row(row),
                    "message": "已更新该次问答的游客反馈。",
                }
            cursor = conn.execute(
                """
                INSERT INTO feedback(
                  log_id,rating,text,sentiment,sentiment_source,sentiment_confidence,
                  topics_json,status,recommendation,
                  management_note,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'pending',?,'',?,?)
                """,
                (
                    payload.log_id,
                    effective_rating,
                    payload.text,
                    sentiment,
                    sentiment_source,
                    sentiment_confidence,
                    json_dump(topics),
                    recommendation,
                    now,
                    now,
                ),
            )
            _sync_qa_log_feedback(
                conn, payload.log_id, effective_rating, sentiment, payload.text
            )
            feedback_id = int(cursor.lastrowid)
            conn.commit()
            row = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
            return {"ok": True, "data": _feedback_from_row(row)}
        finally:
            conn.close()

    @router.get(f"{ADMIN_PREFIX}/feedback")
    def list_feedback(
        handling_status: str = Query(default="", alias="status"), sentiment: str = ""
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if handling_status:
            clauses.append("status=?")
            params.append(handling_status)
        if sentiment:
            clauses.append("sentiment=?")
            params.append(sentiment)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = connect(db_path)
        try:
            _backfill_legacy_feedback(conn)
            conn.commit()
            rows = conn.execute(
                f"SELECT * FROM feedback {where} ORDER BY created_at DESC,id DESC", params
            ).fetchall()
            return {"ok": True, "data": [_feedback_from_row(row) for row in rows]}
        finally:
            conn.close()

    @router.patch(f"{ADMIN_PREFIX}/feedback/{{feedback_id}}")
    def update_feedback(
        feedback_id: int, payload: FeedbackManagementUpdate
    ) -> dict[str, Any]:
        updates = payload.model_dump(exclude_unset=True)
        now = _now()
        conn = connect(db_path)
        try:
            row = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="游客反馈不存在。")
            current = row_to_dict(row)
            next_status = updates.get("status", current["status"])
            recommendation = updates.get("recommendation", current["recommendation"])
            management_note = updates.get("management_note", current["management_note"])
            resolved_at = now if next_status == "resolved" else None
            conn.execute(
                """
                UPDATE feedback
                SET status=?,recommendation=?,management_note=?,updated_at=?,resolved_at=?
                WHERE id=?
                """,
                (
                    next_status,
                    recommendation,
                    management_note,
                    now,
                    resolved_at,
                    feedback_id,
                ),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
            return {"ok": True, "data": _feedback_from_row(updated)}
        finally:
            conn.close()

    @router.get(f"{ADMIN_PREFIX}/quality-runs/latest")
    def latest_quality_run() -> dict[str, Any]:
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT * FROM quality_runs ORDER BY created_at DESC,id DESC LIMIT 1"
            ).fetchone()
            return {
                "ok": True,
                "data": _quality_from_row(row) if row else None,
                "message": "" if row else "尚无质量自测记录。",
            }
        finally:
            conn.close()

    @router.get(f"{ADMIN_PREFIX}/quality-runs")
    def list_quality_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        conn = connect(db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM quality_runs ORDER BY created_at DESC,id DESC LIMIT ?", (limit,)
            ).fetchall()
            return {"ok": True, "data": [_quality_from_row(row) for row in rows]}
        finally:
            conn.close()

    @router.get(f"{ADMIN_PREFIX}/quality-runs/e2e-latency/latest")
    def latest_end_to_end_latency_report() -> dict[str, Any]:
        report_path = e2e_latency_report_path or DEFAULT_E2E_LATENCY_REPORT
        if not report_path.is_file():
            return {
                "ok": True,
                "data": None,
                "message": "尚无完整的本地端到端延迟报告。",
            }
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"无法读取端到端延迟报告：{exc}",
            ) from exc
        if not isinstance(report, dict) or report.get("kind") != "end_to_end_latency":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="端到端延迟报告格式不正确。",
            )
        return {"ok": True, "data": report}

    @router.post(f"{ADMIN_PREFIX}/quality-runs", status_code=status.HTTP_201_CREATED)
    def create_quality_run(payload: QualityRunCreate) -> dict[str, Any]:
        now = _now()
        conn = connect(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO quality_runs(
                  dataset_version,accuracy,sample_count,passed_count,sample_details_json,
                  latency_ms_json,environment_json,official_evaluation,
                  official_evidence_reference,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.dataset_version,
                    payload.accuracy,
                    payload.sample_count,
                    payload.passed_count,
                    json_dump(payload.sample_details),
                    json_dump(payload.latency_ms),
                    json_dump(payload.environment),
                    int(payload.official_evaluation),
                    payload.official_evidence_reference,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
            conn.commit()
            row = conn.execute("SELECT * FROM quality_runs WHERE id=?", (run_id,)).fetchone()
            return {"ok": True, "data": _quality_from_row(row)}
        finally:
            conn.close()

    @router.post(
        f"{ADMIN_PREFIX}/quality-runs/run",
        status_code=status.HTTP_201_CREATED,
    )
    def run_quality_evaluation() -> dict[str, Any]:
        """Execute the frozen local QA set and persist this newly measured run."""

        evaluator = quality_evaluator or run_frozen_evaluation
        try:
            report = evaluator()
            payload = QualityRunCreate.model_validate(quality_run_payload(report))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"无法运行冻结问答集自测：{exc}",
            ) from exc
        result = create_quality_run(payload)
        result["report"] = {
            "kind": report.get("kind"),
            "target_percent": report.get("target_percent"),
            "target_reached": report.get("target_reached"),
            "generated_at": report.get("generated_at"),
        }
        result["message"] = "冻结问答集已按当前问答链路重新执行并保存。"
        return result

    @router.get(f"{ADMIN_PREFIX}/overview")
    def overview() -> dict[str, Any]:
        conn = connect(db_path)
        try:
            active = get_active_digital_human_profile(db_path)
            profile_versions = conn.execute(
                "SELECT COUNT(*) FROM digital_human_profiles"
            ).fetchone()[0]
            document_counts = conn.execute(
                """
                SELECT
                  SUM(CASE WHEN status<>'deleted' THEN 1 ELSE 0 END) AS documents,
                  SUM(CASE WHEN status<>'deleted' AND index_status='pending' THEN 1 ELSE 0 END) AS pending,
                  SUM(CASE WHEN status<>'deleted' AND index_status='indexed' THEN 1 ELSE 0 END) AS indexed
                FROM knowledge_documents
                """
            ).fetchone()
            source_counts = conn.execute(
                """
                SELECT COUNT(*) AS documents,
                       SUM(CASE WHEN records_count>0 OR EXISTS(
                         SELECT 1 FROM knowledge_chunks c WHERE c.source_file=s.name
                       ) THEN 1 ELSE 0 END) AS indexed
                FROM source_files s
                """
            ).fetchone()
            feedback_counts = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                       SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved
                FROM feedback
                """
            ).fetchone()
            quality_count = conn.execute("SELECT COUNT(*) FROM quality_runs").fetchone()[0]
            latest = conn.execute(
                "SELECT * FROM quality_runs ORDER BY created_at DESC,id DESC LIMIT 1"
            ).fetchone()
            return {
                "ok": True,
                "data": {
                    "digital_human": {
                        "profile_versions": int(profile_versions),
                        "active_profile": active,
                    },
                    "knowledge": {
                        "documents": int(document_counts["documents"] or 0)
                        + int(source_counts["documents"] or 0),
                        "pending": int(document_counts["pending"] or 0),
                        "indexed": int(document_counts["indexed"] or 0)
                        + int(source_counts["indexed"] or 0),
                        "local_sources": int(source_counts["documents"] or 0),
                        "managed_documents": int(document_counts["documents"] or 0),
                    },
                    "feedback": {
                        "total": int(feedback_counts["total"] or 0),
                        "pending": int(feedback_counts["pending"] or 0),
                        "resolved": int(feedback_counts["resolved"] or 0),
                    },
                    "quality": {
                        "runs": int(quality_count),
                        "latest": _quality_from_row(latest) if latest else None,
                    },
                    "provenance": {
                        "operations": "实时交互数据",
                        "scenic": "示例景区数据",
                        "quality": "本地自测数据或带凭证的官方评测数据",
                    },
                },
            }
        finally:
            conn.close()

    return router


router = create_admin_competition_router()
