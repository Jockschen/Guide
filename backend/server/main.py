from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
from itertools import chain
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .avatar import build_driver_metadata, opentalking_runtime_status, request_lipsync
from .avatar_session_api import create_avatar_session_router
from .admin_competition import router as admin_competition_router
from .admin_asset_api import router as admin_asset_router
from .config import settings
from .db import connect, init_db, json_dump, json_load, row_to_dict
from .ingestion import locate_data_package, rebuild_knowledge
from .qwen_client import call_qwen, iter_qwen_deltas, qwen_available, sanitize_markdown_answer
from .profile_runtime import active_profile, public_profile_data, resolve_tts_voice
from .retrieval import list_faqs, local_answer, match_faq, retrieve
from .schemas import ChatRequest, DigitalHumanConfigUpdate, FeedbackRequest, LipsyncRequest, RoutePlanRequest, TTSRequest
from .voice import estimate_visemes, speech_runtime_status, synthesize_tts, transcribe_asr


app = FastAPI(title="灵境导游 AI 数字人服务", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.storage_dir), name="static")
app.include_router(create_avatar_session_router())
app.include_router(admin_competition_router)
app.include_router(admin_asset_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


def _counts() -> dict[str, int]:
    conn = connect()
    try:
        return {
            "sources": conn.execute("SELECT COUNT(*) FROM source_files").fetchone()[0],
            "attractions": conn.execute("SELECT COUNT(*) FROM attractions").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],
            "faqs": conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0],
            "logs": conn.execute("SELECT COUNT(*) FROM qa_logs").fetchone()[0],
        }
    finally:
        conn.close()


def _known_attractions() -> list[dict[str, str]]:
    conn = connect()
    try:
        rows = conn.execute("SELECT name,spot_id,source_file FROM attractions ORDER BY id").fetchall()
    finally:
        conn.close()
    return [row_to_dict(row) for row in rows]


def _visitor_id_from_request(request: Request) -> tuple[str, str]:
    user_agent = (request.headers.get("user-agent") or "unknown").strip()[:500]
    digest = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()[:18]
    return digest, user_agent


def _infer_spot_name(question: str, answer: str = "", sources: list[dict[str, Any]] | None = None) -> str:
    text = f"{question}\n{answer}\n" + "\n".join(
        f"{source.get('title', '')} {source.get('source_file', '')} {source.get('preview', '')}"
        for source in (sources or [])
    )
    attractions = _known_attractions()
    for spot in attractions:
        name = spot.get("name") or ""
        if name and name in text:
            return name
    for source in sources or []:
        title = str(source.get("title") or "").strip()
        if title:
            return title.split("：", 1)[0].split("·", 1)[-1].strip()[:24]
    return "综合咨询"


STOPWORDS = {
    "什么",
    "怎么",
    "哪里",
    "这个",
    "那个",
    "一下",
    "可以",
    "帮我",
    "请问",
    "资料",
    "路线",
    "规划",
    "景点",
    "讲解",
    "适合",
    "游客",
    "导游",
    "灵山",
    "大照壁",
}


def _extract_terms(text: str, attractions: list[dict[str, str]]) -> list[str]:
    terms: list[str] = []
    for spot in attractions:
        name = spot.get("name") or ""
        if name and name in text:
            terms.append(name)
    for match in re.findall(r"[\u4e00-\u9fa5]{2,10}", text):
        value = match.strip("？?，。！!；;：:、 ")
        if value in STOPWORDS or len(value) < 2:
            continue
        if any(stop in value for stop in ["资料包中", "未提供", "资料依据"]):
            continue
        terms.append(value[:10])
    return terms


def _log_rows(
    limit: int = 80,
    start_date: str = "",
    end_date: str = "",
    spot: str = "",
    keyword: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if start_date:
        clauses.append("date(created_at) >= date(?)")
        params.append(start_date)
    if end_date:
        clauses.append("date(created_at) <= date(?)")
        params.append(end_date)
    if spot:
        clauses.append("(spot_name LIKE ? OR question LIKE ? OR answer LIKE ?)")
        like = f"%{spot}%"
        params.extend([like, like, like])
    if keyword:
        clauses.append("(question LIKE ? OR answer LIKE ? OR spot_name LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM qa_logs {where} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    finally:
        conn.close()
    logs = []
    for row in rows:
        item = row_to_dict(row)
        item["sources"] = json_load(item.pop("sources_json"), [])
        logs.append(item)
    return logs


def _build_log_summary(logs: list[dict[str, Any]]) -> dict[str, Any]:
    attractions = _known_attractions()
    dates: dict[str, int] = {}
    spots: dict[str, int] = {}
    feelings: dict[str, int] = {}
    terms: dict[str, int] = {}
    groups: dict[str, dict[str, Any]] = {}
    visitors = {log.get("visitor_id") for log in logs if log.get("visitor_id")}
    rated = [log for log in logs if log.get("rating") is not None]
    for log in logs:
        date = str(log.get("created_at") or "")[:10] or "未记录"
        dates[date] = dates.get(date, 0) + 1
        spot = log.get("spot_name") or _infer_spot_name(log.get("question", ""), log.get("answer", ""), log.get("sources", []))
        spots[spot] = spots.get(spot, 0) + 1
        feeling = log.get("feeling") or "未反馈"
        feelings[feeling] = feelings.get(feeling, 0) + 1
        question = str(log.get("question") or "")
        for term in _extract_terms(question, attractions):
            terms[term] = terms.get(term, 0) + 1
        group_key = next(iter(_extract_terms(question, attractions)), spot)
        group = groups.setdefault(group_key, {"keyword": group_key, "count": 0, "log_ids": [], "questions": []})
        group["count"] += 1
        group["log_ids"].append(log.get("id"))
        if question and question not in group["questions"]:
            group["questions"].append(question)
    avg_rating = round(sum(int(log["rating"]) for log in rated) / len(rated), 2) if rated else None
    return {
        "total_questions": len(logs),
        "unique_visitors": len(visitors),
        "rated_questions": len(rated),
        "average_rating": avg_rating,
        "date_distribution": sorted(dates.items()),
        "spot_distribution": sorted(spots.items(), key=lambda item: item[1], reverse=True)[:12],
        "feeling_distribution": sorted(feelings.items(), key=lambda item: item[1], reverse=True),
        "keyword_summary": sorted(terms.items(), key=lambda item: item[1], reverse=True)[:16],
        "question_groups": sorted(groups.values(), key=lambda item: item["count"], reverse=True)[:12],
    }


def _build_live_dashboard_metrics(
    logs: list[dict[str, Any]],
    *,
    today: date,
) -> dict[str, Any]:
    today_label = today.isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    today_visitors: set[str] = set()
    week_visitors: set[str] = set()
    today_questions = 0
    week_questions = 0
    question_counts: dict[str, int] = {}

    for log in logs:
        created_on = str(log.get("created_at") or "")[:10]
        visitor_id = str(log.get("visitor_id") or "").strip()
        question = str(log.get("question") or "").strip()
        if question:
            question_counts[question] = question_counts.get(question, 0) + 1
        if created_on == today_label:
            today_questions += 1
            if visitor_id:
                today_visitors.add(visitor_id)
        if week_start <= created_on <= today_label:
            week_questions += 1
            if visitor_id:
                week_visitors.add(visitor_id)

    hot_questions = sorted(
        (
            [question, count]
            for question, count in question_counts.items()
            if count > 1
        ),
        key=lambda item: (-int(item[1]), str(item[0])),
    )[:12]
    return {
        "today_questions": today_questions,
        "today_visitors": len(today_visitors),
        "week_questions": week_questions,
        "week_visitors": len(week_visitors),
        "live_hot_questions": hot_questions,
    }


ROUTE_PRESETS = {
    "family": {
        "title": "亲子家庭路线",
        "mood": "先看动态表演，再安排亲子互动和艺术空间。",
        "ids": ["LS-006", "LS-009", "LS-013", "LS-014"],
    },
    "culture": {
        "title": "历史文化路线",
        "mood": "从入口文化序章走向古刹、造像、艺术殿堂和坛城。",
        "ids": ["LS-001", "LS-010", "LS-011", "LS-013", "LS-014"],
    },
    "nature": {
        "title": "自然风光路线",
        "mood": "按指南中的自然风光方向，串联步道、表演、登高和园林景观。",
        "ids": ["LS-003", "LS-006", "LS-005", "LS-011", "LS-015"],
    },
    "classic": {
        "title": "经典半日线",
        "mood": "按资料包景点顺序串联核心节点，适合第一次到访。",
        "ids": ["LS-001", "LS-005", "LS-006", "LS-010", "LS-013"],
    },
}


def _route_kind(interest: str) -> str:
    text = interest.lower()
    if any(keyword in text for keyword in ["亲子", "孩子", "家庭", "轻松", "老人"]):
        return "family"
    if any(keyword in text for keyword in ["历史", "文化", "佛教", "建筑", "艺术", "深度"]):
        return "culture"
    if any(keyword in text for keyword in ["自然", "风光", "花", "湖", "拍照", "慢游"]):
        return "nature"
    return "classic"


def _is_route_request(text: str) -> bool:
    if any(source_word in text for source_word in ("指南", "资料")) and any(
        question_word in text
        for question_word in ("几小时", "多久", "多少", "哪个", "哪些", "是什么")
    ):
        return False
    direct_keywords = [
        "路线",
        "规划",
        "半日",
        "一日",
        "行程",
        "怎么走",
        "游览安排",
        "亲子",
        "带孩子",
        "家庭路线",
        "历史文化路线",
        "自然风光路线",
        "拍照路线",
        "慢游",
    ]
    if any(keyword in text for keyword in direct_keywords):
        return True
    return any(keyword in text for keyword in ["我喜欢", "感兴趣", "偏好"]) and any(
        keyword in text for keyword in ["历史", "文化", "自然", "风光", "佛教", "建筑", "拍照"]
    )


def _short_text(*values: str | None, fallback: str = "资料包景点条目") -> str:
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        for separator in ["；", "。", ";", "."]:
            if separator in text:
                text = text.split(separator, 1)[0]
                break
        return text[:54]
    return fallback


def _load_route_steps(spot_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    map_points = [
        {"map_x": 18, "map_y": 88},
        {"map_x": 34, "map_y": 75},
        {"map_x": 50, "map_y": 61},
        {"map_x": 65, "map_y": 44},
        {"map_x": 76, "map_y": 22},
    ]
    placeholders = ",".join("?" for _ in spot_ids)
    conn = connect()
    try:
        rows = conn.execute(
            f"""
            SELECT spot_id,name,location,core_function,culture,highlights,opening,source_file
            FROM attractions
            WHERE spot_id IN ({placeholders})
            """,
            spot_ids,
        ).fetchall()
    finally:
        conn.close()
    by_id = {row["spot_id"]: row_to_dict(row) for row in rows}
    steps: list[dict[str, Any]] = []
    source_files: list[str] = []
    for index, spot_id in enumerate(spot_ids, start=1):
        row = by_id.get(spot_id)
        if not row:
            continue
        source_file = row.get("source_file") or ""
        if source_file and source_file not in source_files:
            source_files.append(source_file)
        steps.append(
            {
                "index": index,
                "spot_id": row["spot_id"],
                "name": row["name"],
                "reason": _short_text(row.get("highlights"), row.get("core_function"), row.get("culture")),
                "location": _short_text(row.get("location"), fallback="见资料包景点位置"),
                "opening": _short_text(row.get("opening"), fallback="开放信息以景区公告为准"),
                "source_file": source_file,
                **map_points[min(index - 1, len(map_points) - 1)],
            }
        )
    return steps, source_files


def _load_guide_route(kind: str) -> dict[str, str] | None:
    title_like = {
        "family": "%亲子家庭路线%",
        "culture": "%历史文化爱好者路线%",
        "nature": "%自然风光爱好者路线%",
        "classic": "%路线规划%",
    }.get(kind, "%路线规划%")
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT title,content,source_file
            FROM knowledge_chunks
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY id
            LIMIT 1
            """,
            (title_like, title_like),
        ).fetchone()
    finally:
        conn.close()
    return row_to_dict(row) if row else None


def _make_route_plan(interest: str) -> dict[str, Any]:
    kind = _route_kind(interest)
    preset = ROUTE_PRESETS[kind]
    steps, source_files = _load_route_steps(preset["ids"])
    guide_route = _load_guide_route(kind)
    if guide_route and guide_route["source_file"] not in source_files:
        source_files.append(guide_route["source_file"])
    return {
        "title": preset["title"],
        "mood": preset["mood"],
        "interest": interest,
        "image_url": "/assets/generated/route-map-lingshan-v2.png",
        "steps": steps,
        "source_files": source_files,
        "guide_title": guide_route["title"] if guide_route else "",
        "note": "路线节点来自本地资料包，演出与开放信息以景区现场公告为准。",
    }


def _route_answer(route: dict[str, Any], guide_style: str = "自然讲解") -> str:
    if guide_style == "简洁提示":
        opening = f"可以，按“{route['title']}”走最省心：{route['mood']}"
    elif guide_style == "文化深度":
        opening = f"可以。我会把这条线按文化线索串起来：{route['mood']}"
    else:
        opening = f"可以，我给你画一条好走的“{route['title']}”：{route['mood']}"
    names = [step["name"] for step in route["steps"][:5]]
    first_stop = names[0] if names else "入口"
    lines = [
        opening,
        "",
        f"我已经把站点放到右侧路线图了。你可以先从 **{first_stop}** 开始，点任意站点查看讲解重点，也可以让我继续讲某一站。",
        "",
        "> 资料依据：路线节点来自本地资料包，演出与开放信息以景区现场公告为准。",
    ]
    return "\n".join(lines)


@app.post("/api/route-plan")
def route_plan(payload: RoutePlanRequest) -> dict[str, Any]:
    return {"ok": True, "data": _make_route_plan(payload.interest)}



@app.get("/api/health")
def health() -> dict[str, Any]:
    counts = _counts()
    speech_status = speech_runtime_status()
    return {
        "ok": True,
        "env": settings.app_env,
        "qwen_configured": qwen_available(),
        "vivo_configured": bool(settings.vivo_app_key),
        "vivo_app_id_configured": bool(settings.vivo_app_id),
        **speech_status,
        **opentalking_runtime_status(),
        "vector_backend": settings.vector_backend,
        "counts": counts,
    }


@app.get("/api/avatar/profile")
def avatar_profile() -> dict[str, Any]:
    return {"ok": True, "data": public_profile_data(active_profile())}


@app.post("/api/admin/rebuild")
def admin_rebuild() -> dict[str, Any]:
    result = rebuild_knowledge()
    return {"ok": True, "data": result}


@app.get("/api/admin/pipeline-check")
def pipeline_check(question: str = "九龙灌浴表演时间是什么？") -> dict[str, Any]:
    chunks = retrieve(question, limit=3)
    answer = local_answer(question, chunks, "自然讲解") if chunks else "资料包中未提供相关内容，请咨询景区公告或后台补充资料。"
    tts_result = synthesize_tts(answer, voice="gentle", style="自然讲解", speed=1.0, volume=0.86)
    avatar_status = opentalking_runtime_status()
    if avatar_status.get("opentalking_ready"):
        message = "OpenTalking 服务可用，游客播报时再生成真实口型视频。"
        lipsync_result = {
            "provider": "opentalking",
            "status": "ready",
            "message": message,
            "visemes": tts_result.get("visemes") or estimate_visemes(answer),
            "driver": build_driver_metadata("opentalking", "ready", "", message),
        }
    else:
        lipsync_result = request_lipsync(answer, tts_result.get("audio_url"), allow_demo=True)
    visemes = lipsync_result.get("visemes") or tts_result.get("visemes") or []
    avatar_driver = lipsync_result.get("driver") or build_driver_metadata(
        str(lipsync_result.get("provider") or "2d-fallback"),
        str(lipsync_result.get("status") or "fallback"),
        str(lipsync_result.get("video_url") or ""),
        str(lipsync_result.get("message") or ""),
    )
    speech_status = speech_runtime_status()
    return {
        "ok": True,
        "data": {
            "question": question,
            "knowledge_ready": len(chunks) > 0,
            "retrieved_chunks": len(chunks),
            "answer_preview": answer[:180],
            "sources": [
                {
                    "title": chunk["title"],
                    "source_file": chunk["source_file"],
                    "score": chunk["score"],
                }
                for chunk in chunks
            ],
            "tts_provider": tts_result.get("provider"),
            "tts_effective_provider": speech_status["tts_effective_provider"],
            "tts_audio_ready": bool(tts_result.get("audio_url")),
            "avatar_provider": lipsync_result.get("provider"),
            "avatar_driver": avatar_driver,
            "visemes_count": len(visemes),
        },
    }


@app.get("/api/admin/demo-readiness")
def demo_readiness() -> dict[str, Any]:
    counts = _counts()
    speech_status = speech_runtime_status()
    avatar_status = opentalking_runtime_status()
    knowledge_ready = counts["chunks"] > 0 and counts["attractions"] > 0
    if avatar_status.get("opentalking_ready"):
        digital_human_plan = "OpenTalking 实时生成真实口型视频"
        digital_human_driver_mode = "real_video"
    elif avatar_status.get("demo_video_ready"):
        digital_human_plan = "预生成真实口型片段用于演示，游客问答使用 2D 舞台兜底"
        digital_human_driver_mode = "demo_video"
    else:
        digital_human_plan = "2D 舞台兜底，待配置 OpenTalking 权重与推理命令"
        digital_human_driver_mode = "audio_2d"
    blockers = []
    if not knowledge_ready:
        blockers.append("资料库尚未完成同步")
    if not qwen_available():
        blockers.append("Qwen API Key 未配置，问答将使用资料增强模式")
    if speech_status["asr_effective_provider"] == "mock":
        blockers.append("语音识别处于本地兜底模式")
    if speech_status["tts_effective_provider"] == "mock":
        blockers.append("语音合成处于本地兜底模式")
    if not avatar_status.get("opentalking_ready") and not avatar_status.get("demo_video_ready"):
        blockers.append("真实口型服务或演示片段未就绪")
    return {
        "ok": True,
        "data": {
            "knowledge_ready": knowledge_ready,
            "counts": counts,
            "qwen_configured": qwen_available(),
            **speech_status,
            **avatar_status,
            "digital_human_plan": digital_human_plan,
            "digital_human_driver_mode": digital_human_driver_mode,
            "competition_ready": knowledge_ready and len(blockers) == 0,
            "blockers": blockers,
        },
    }


@app.get("/api/admin/sources")
def admin_sources() -> dict[str, Any]:
    conn = connect()
    try:
        sources = [row_to_dict(row) for row in conn.execute("SELECT * FROM source_files ORDER BY id").fetchall()]
        attractions = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT spot_id,name,scenic_area,opening,source_file FROM attractions ORDER BY spot_id"
            ).fetchall()
        ]
    finally:
        conn.close()
    return {"ok": True, "data": {"sources": sources, "attractions": attractions, "counts": _counts()}}


@app.post("/api/admin/sources/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".docx", ".xlsx"}:
        raise HTTPException(status_code=400, detail="仅支持上传 Word 或 Excel 资料文件。")
    data_dir = locate_data_package()
    data_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or f"资料文件{suffix}").name
    target = data_dir / safe_name
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    result = rebuild_knowledge()
    return {
        "ok": True,
        "data": {"file": safe_name, **result},
        "message": "资料已上传并同步到知识库。",
    }


@app.get("/api/admin/sources/{source_id}")
def source_detail(source_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        source = conn.execute("SELECT * FROM source_files WHERE id=?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="资料文件不存在。")
        source_dict = row_to_dict(source)
        attractions = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT spot_id,name,location,core_function,highlights,opening FROM attractions WHERE source_file=? ORDER BY spot_id",
                (source_dict["name"],),
            ).fetchall()
        ]
        chunks = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT id,title,source_type,substr(content,1,240) AS preview FROM knowledge_chunks WHERE source_file=? ORDER BY id LIMIT 30",
                (source_dict["name"],),
            ).fetchall()
        ]
        faqs = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT question,answer,source_title FROM faqs WHERE source_file=? ORDER BY id LIMIT 20",
                (source_dict["name"],),
            ).fetchall()
        ]
    finally:
        conn.close()
    return {
        "ok": True,
        "data": {
            "source": source_dict,
            "attractions": attractions,
            "chunks": chunks,
            "faqs": faqs,
        },
    }


@app.get("/api/faqs")
def faqs(limit: int = 24) -> dict[str, Any]:
    return {"ok": True, "data": list_faqs(limit=limit)}


def _faq_sources(faq: dict[str, Any]) -> list[dict[str, Any]]:
    answer = str(faq["answer"])
    return [
        {
            "title": faq["source_title"],
            "source_file": faq["source_file"],
            "source_type": "faq",
            "score": 1.0,
            "preview": answer[:220],
        }
    ]


def _chunk_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "score": chunk["score"],
            "preview": chunk["content"][:220],
        }
        for chunk in chunks
    ]


def _store_chat_log(
    payload: ChatRequest,
    request: Request,
    answer: str,
    sources: list[dict[str, Any]],
    provider: str,
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    visitor_id, user_agent = _visitor_id_from_request(request)
    spot_name = _infer_spot_name(payload.question, answer, sources)
    conn = connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO qa_logs(question,answer,sources_json,provider,created_at,visitor_id,user_agent,spot_name)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (payload.question, answer, json_dump(sources), provider, now, visitor_id, user_agent, spot_name),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def _ndjson_event(event_type: str, **values: Any) -> str:
    return json.dumps({"type": event_type, **values}, ensure_ascii=False) + "\n"


def _narration_chunks(text: str, max_chars: int = 46) -> list[str]:
    chunks: list[str] = []
    for sentence in re.findall(r"[^。！？]+[。！？]?", text):
        clean = sentence.strip()
        if not clean:
            continue
        chunks.extend(clean[start : start + max_chars] for start in range(0, len(clean), max_chars))
    return chunks


def _stream_faq_answer(
    payload: ChatRequest,
    request: Request,
    faq: dict[str, Any],
) -> Iterator[str]:
    answer = str(faq["answer"])
    provider = "faq-fast-path"
    sources = _faq_sources(faq)
    yield _ndjson_event("meta", provider=provider)
    yield _ndjson_event("delta", text=answer)
    for index, text in enumerate(_narration_chunks(answer)):
        yield _ndjson_event("narration", index=index, text=text)
    log_id = _store_chat_log(payload, request, answer, sources, provider)
    yield _ndjson_event(
        "done",
        data={"answer": answer, "sources": sources, "provider": provider, "log_id": log_id},
    )


def _stream_local_answer(
    payload: ChatRequest,
    request: Request,
    chunks: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> Iterator[str]:
    answer = local_answer(payload.question, chunks, payload.guide_style)
    provider = "local-retrieval"
    yield _ndjson_event("meta", provider=provider)
    yield _ndjson_event("delta", text=answer)
    for index, text in enumerate(_narration_chunks(answer)):
        yield _ndjson_event("narration", index=index, text=text)
    log_id = _store_chat_log(payload, request, answer, sources, provider)
    yield _ndjson_event(
        "done",
        data={"answer": answer, "sources": sources, "provider": provider, "log_id": log_id},
    )


def _stream_qwen_answer(payload: ChatRequest, request: Request) -> Iterator[str]:
    chunks = retrieve(payload.question, limit=5)
    sources = _chunk_sources(chunks)
    try:
        profile = active_profile()
        delta_iterator = iter(
            iter_qwen_deltas(
                payload.question,
                chunks,
                payload.image_base64,
                payload.guide_style,
                persona=str(profile.get("persona") or ""),
            )
        )
        first_delta = next(delta_iterator)
        if not first_delta:
            raise StopIteration
    except (Exception, StopIteration):
        yield from _stream_local_answer(payload, request, chunks, sources)
        return
    provider = "qwen-stream"
    yield _ndjson_event("meta", provider=provider)
    answer_parts: list[str] = []
    narration_buffer = ""
    narration_index = 0
    for delta in chain((first_delta,), delta_iterator):
        answer_parts.append(delta)
        narration_buffer += delta
        yield _ndjson_event("delta", text=delta)
        while match := re.match(r"^(.*?[。！？])", narration_buffer, flags=re.DOTALL):
            complete_sentence = match.group(1)
            narration_buffer = narration_buffer[len(complete_sentence) :]
            for text in _narration_chunks(sanitize_markdown_answer(complete_sentence)):
                yield _ndjson_event("narration", index=narration_index, text=text)
                narration_index += 1
        while len(narration_buffer) >= 46:
            complete_chunk = narration_buffer[:46]
            narration_buffer = narration_buffer[46:]
            text = sanitize_markdown_answer(complete_chunk)
            if text:
                yield _ndjson_event("narration", index=narration_index, text=text)
                narration_index += 1
    if narration_buffer.strip():
        for text in _narration_chunks(sanitize_markdown_answer(narration_buffer)):
            yield _ndjson_event("narration", index=narration_index, text=text)
            narration_index += 1
    answer = sanitize_markdown_answer("".join(answer_parts))
    log_id = _store_chat_log(payload, request, answer, sources, provider)
    yield _ndjson_event(
        "done",
        data={"answer": answer, "sources": sources, "provider": provider, "log_id": log_id},
    )


def _safe_chat_stream(iterator: Iterator[str]) -> Iterator[str]:
    try:
        yield from iterator
    except Exception:
        yield _ndjson_event("error", message="导览服务正在连接，请稍后重试。")


@app.post("/api/chat")
def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    if _is_route_request(payload.question):
        route = _make_route_plan(payload.question)
        answer = _route_answer(route, payload.guide_style)
        provider = "route-plan"
        sources = [
            {
                "title": step["name"],
                "source_file": step["source_file"],
                "source_type": "路线规划",
                "score": 1,
                "preview": step["reason"],
            }
            for step in route["steps"]
        ]
    else:
        faq = None if payload.image_base64 else match_faq(payload.question)
        if faq:
            answer = str(faq["answer"])
            provider = "faq-fast-path"
            sources = _faq_sources(faq)
        else:
            chunks = retrieve(payload.question, limit=5)
            provider = "local-retrieval"
            profile = active_profile()
            try:
                answer = call_qwen(
                    payload.question,
                    chunks,
                    payload.image_base64,
                    payload.guide_style,
                    persona=str(profile.get("persona") or ""),
                )
                provider = "qwen"
            except Exception as exc:
                answer = local_answer(payload.question, chunks, payload.guide_style)
                provider = f"local-retrieval ({exc})" if qwen_available() else "local-retrieval"
            sources = _chunk_sources(chunks)
    log_id = _store_chat_log(payload, request, answer, sources, provider)
    return {"ok": True, "data": {"answer": answer, "sources": sources, "provider": provider, "log_id": log_id}}


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    faq = None if payload.image_base64 else match_faq(payload.question)
    if faq:
        iterator = _stream_faq_answer(payload, request, faq)
    else:
        iterator = _stream_qwen_answer(payload, request)
    return StreamingResponse(
        _safe_chat_stream(iterator),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/admin/logs")
def admin_logs(
    limit: int = Query(default=80, ge=1, le=500),
    start_date: str = "",
    end_date: str = "",
    spot: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    return {"ok": True, "data": _log_rows(limit=limit, start_date=start_date, end_date=end_date, spot=spot, keyword=keyword)}


@app.get("/api/admin/log-summary")
def admin_log_summary(
    limit: int = Query(default=500, ge=1, le=2000),
    start_date: str = "",
    end_date: str = "",
    spot: str = "",
    keyword: str = "",
) -> dict[str, Any]:
    logs = _log_rows(limit=limit, start_date=start_date, end_date=end_date, spot=spot, keyword=keyword)
    return {"ok": True, "data": _build_log_summary(logs)}


@app.delete("/api/admin/logs/{log_id}")
def delete_log(log_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        cursor = conn.execute("DELETE FROM qa_logs WHERE id=?", (log_id,))
        conn.commit()
    finally:
        conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="问答记录不存在。")
    return {"ok": True, "message": "问答记录已删除"}


@app.post("/api/feedback")
def feedback(payload: FeedbackRequest) -> dict[str, Any]:
    conn = connect()
    try:
        conn.execute(
            "UPDATE qa_logs SET rating=?, feeling=?, note=? WHERE id=?",
            (payload.rating, payload.feeling, payload.note, payload.log_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "message": "反馈已记录"}


@app.get("/api/admin/reports/feelings")
def feelings_report() -> dict[str, Any]:
    rows = _log_rows(limit=1000)
    total = len(rows)
    rated = [row for row in rows if row.get("rating") is not None]
    avg_rating = round(sum(int(row["rating"]) for row in rated) / len(rated), 2) if rated else None
    feelings: dict[str, int] = {}
    low_rating_notes: list[dict[str, Any]] = []
    hot_questions = _build_log_summary(rows)["question_groups"]
    for row in rows:
        feeling = row.get("feeling") or "未反馈"
        feelings[feeling] = feelings.get(feeling, 0) + 1
        if row.get("rating") is not None and int(row["rating"]) <= 3:
            low_rating_notes.append({"question": row["question"], "rating": row["rating"], "note": row.get("note")})
    return {
        "ok": True,
        "data": {
            "total_questions": total,
            "rated_questions": len(rated),
            "average_rating": avg_rating,
            "feeling_distribution": sorted(feelings.items(), key=lambda item: item[1], reverse=True),
            "low_rating_notes": low_rating_notes[:8],
            "hot_questions": [(item["keyword"], item["count"]) for item in hot_questions[:8]],
        },
    }


@app.get("/api/admin/dashboard")
def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT metrics_json,updated_at FROM dashboard_metrics WHERE id=1").fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": True, "data": None, "message": "尚未重建知识库"}
    data = json.loads(row["metrics_json"])
    data["updated_at"] = row["updated_at"]
    logs = _log_rows(limit=1000)
    log_summary = _build_log_summary(logs)
    data["live_questions"] = log_summary["total_questions"]
    data["live_visitors"] = log_summary["unique_visitors"]
    data.update(_build_live_dashboard_metrics(logs, today=datetime.now().date()))
    data["live_spot_distribution"] = log_summary["spot_distribution"]
    data["live_keyword_summary"] = log_summary["keyword_summary"]
    data["live_question_groups"] = log_summary["question_groups"]
    data["live_date_distribution"] = log_summary["date_distribution"]
    data["live_feeling_distribution"] = log_summary["feeling_distribution"]
    data["live_average_rating"] = log_summary["average_rating"]
    return {"ok": True, "data": data}


@app.get("/api/admin/digital-human")
def get_digital_human() -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM digital_human_config WHERE id=1").fetchone()
    finally:
        conn.close()
    data = row_to_dict(row) if row else None
    if data:
        data.pop("rtx_enabled", None)
        data.pop("audio2face_base_url", None)
    return {"ok": True, "data": data}


@app.put("/api/admin/digital-human")
def update_digital_human(payload: DigitalHumanConfigUpdate) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO digital_human_config(
              id,name,voice,persona,avatar_mode,rtx_enabled,opentalking_base_url,audio2face_base_url,updated_at
            ) VALUES(1,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              voice=excluded.voice,
              persona=excluded.persona,
              avatar_mode=excluded.avatar_mode,
              rtx_enabled=excluded.rtx_enabled,
              opentalking_base_url=excluded.opentalking_base_url,
              audio2face_base_url=excluded.audio2face_base_url,
              updated_at=excluded.updated_at
            """,
            (
                payload.name,
                payload.voice,
                payload.persona,
                payload.avatar_mode,
                0,
                payload.opentalking_base_url,
                "",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "message": "数字人配置已保存"}


@app.post("/api/tts/synthesize")
def tts(payload: TTSRequest) -> dict[str, Any]:
    profile = active_profile()
    return {
        "ok": True,
        "data": synthesize_tts(
            payload.text,
            voice=resolve_tts_voice(payload.voice, profile),
            style=payload.style,
            speed=payload.speed,
            volume=payload.volume,
        ),
    }


@app.post("/api/asr/transcribe")
async def asr(file: UploadFile = File(...)) -> dict[str, Any]:
    audio_data = await file.read()
    return {
        "ok": True,
        "data": transcribe_asr(
            audio_data,
            filename=file.filename or "",
            content_type=file.content_type or "",
        ),
    }


@app.post("/api/avatar/lipsync")
def lipsync(payload: LipsyncRequest) -> dict[str, Any]:
    return {"ok": True, "data": request_lipsync(payload.text, payload.audio_url, allow_demo=payload.allow_demo)}


@app.exception_handler(Exception)
async def all_exception_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "message": str(exc)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)
