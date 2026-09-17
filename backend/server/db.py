from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .config import settings


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS source_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  path TEXT NOT NULL,
  file_type TEXT NOT NULL,
  checksum TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  records_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attractions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scenic_area TEXT NOT NULL,
  spot_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  location TEXT,
  parameters TEXT,
  core_function TEXT,
  culture TEXT,
  description TEXT,
  highlights TEXT,
  opening TEXT,
  notes TEXT,
  source_file TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_file TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  embedding_json TEXT,
  knowledge_document_id INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
USING fts5(title, content, chunk_id UNINDEXED, tokenize='unicode61');

CREATE TABLE IF NOT EXISTS faqs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  source_title TEXT NOT NULL,
  source_file TEXT NOT NULL,
  tags_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dashboard_metrics (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  metrics_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  provider TEXT NOT NULL,
  created_at TEXT NOT NULL,
  visitor_id TEXT,
  user_agent TEXT,
  spot_name TEXT,
  rating INTEGER,
  feeling TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS digital_human_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT NOT NULL,
  voice TEXT NOT NULL,
  persona TEXT NOT NULL,
  avatar_mode TEXT NOT NULL,
  rtx_enabled INTEGER NOT NULL,
  opentalking_base_url TEXT,
  audio2face_base_url TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digital_human_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  name TEXT NOT NULL,
  persona TEXT NOT NULL,
  driver_provider TEXT NOT NULL,
  avatar_asset_url TEXT NOT NULL DEFAULT '',
  clothing_asset_url TEXT NOT NULL DEFAULT '',
  clothing_version TEXT NOT NULL DEFAULT '',
  voice TEXT NOT NULL,
  source_video_url TEXT NOT NULL DEFAULT '',
  source_video_kind TEXT NOT NULL DEFAULT 'still_image_fallback',
  opentalking_avatar_id TEXT NOT NULL DEFAULT '',
  prewarm_status TEXT NOT NULL DEFAULT 'pending',
  status TEXT NOT NULL DEFAULT 'draft',
  previewed_at TEXT,
  published_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(profile_key, version)
);

CREATE INDEX IF NOT EXISTS idx_digital_human_profiles_key_version
ON digital_human_profiles(profile_key, version DESC);

CREATE TABLE IF NOT EXISTS digital_human_active (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  profile_id INTEGER NOT NULL,
  activated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_name TEXT NOT NULL DEFAULT '运营维护',
  status TEXT NOT NULL DEFAULT 'active',
  content_version INTEGER NOT NULL DEFAULT 1,
  index_version INTEGER NOT NULL DEFAULT 0,
  index_status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  indexed_at TEXT,
  deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status_updated
ON knowledge_documents(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  log_id INTEGER,
  rating INTEGER,
  text TEXT NOT NULL,
  sentiment TEXT NOT NULL,
  sentiment_source TEXT NOT NULL DEFAULT 'rules',
  sentiment_confidence REAL NOT NULL DEFAULT 0.0,
  topics_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  recommendation TEXT NOT NULL DEFAULT '',
  management_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_status_created
ON feedback(status, created_at DESC);

CREATE TABLE IF NOT EXISTS quality_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_version TEXT NOT NULL,
  accuracy REAL NOT NULL,
  sample_count INTEGER NOT NULL,
  passed_count INTEGER NOT NULL,
  sample_details_json TEXT NOT NULL,
  latency_ms_json TEXT NOT NULL,
  environment_json TEXT NOT NULL,
  official_evaluation INTEGER NOT NULL DEFAULT 0,
  official_evidence_reference TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_runs_created
ON quality_runs(created_at DESC, id DESC);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    owned = conn is None
    conn = conn or connect()
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    if owned:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(digital_human_config)").fetchall()}
    if "opentalking_base_url" not in columns:
        conn.execute("ALTER TABLE digital_human_config ADD COLUMN opentalking_base_url TEXT")
    log_columns = {row[1] for row in conn.execute("PRAGMA table_info(qa_logs)").fetchall()}
    if "visitor_id" not in log_columns:
        conn.execute("ALTER TABLE qa_logs ADD COLUMN visitor_id TEXT")
    if "user_agent" not in log_columns:
        conn.execute("ALTER TABLE qa_logs ADD COLUMN user_agent TEXT")
    if "spot_name" not in log_columns:
        conn.execute("ALTER TABLE qa_logs ADD COLUMN spot_name TEXT")
    chunk_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()}
    if "knowledge_document_id" not in chunk_columns:
        conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN knowledge_document_id INTEGER")
    feedback_columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
    if "sentiment_source" not in feedback_columns:
        conn.execute("ALTER TABLE feedback ADD COLUMN sentiment_source TEXT NOT NULL DEFAULT 'rules'")
    if "sentiment_confidence" not in feedback_columns:
        conn.execute("ALTER TABLE feedback ADD COLUMN sentiment_confidence REAL NOT NULL DEFAULT 0.0")


def reset_content(conn: sqlite3.Connection) -> None:
    for table in [
        "source_files",
        "attractions",
        "knowledge_chunks",
        "knowledge_fts",
        "faqs",
        "dashboard_metrics",
    ]:
        conn.execute(f"DELETE FROM {table}")
    conn.execute(
        """
        UPDATE knowledge_documents
        SET index_version=0,index_status='pending',indexed_at=NULL
        WHERE status<>'deleted'
        """
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def executemany(conn: sqlite3.Connection, sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn.executemany(sql, rows)
    conn.commit()
