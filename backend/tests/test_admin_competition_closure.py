from __future__ import annotations

from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.db import connect, init_db, reset_content


class AdminCompetitionClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "competition.db"
        conn = connect(self.db_path)
        try:
            init_db(conn)
        finally:
            conn.close()
        self.sentiment_classifier_patch = patch(
            "server.admin_competition.classify_feedback_sentiment",
            side_effect=RuntimeError("Qwen disabled for isolated admin tests"),
        )
        self.sentiment_classifier_patch.start()

    def tearDown(self) -> None:
        self.sentiment_classifier_patch.stop()
        self.temp_dir.cleanup()

    def client(self) -> TestClient:
        try:
            from server.admin_competition import create_admin_competition_router
        except ModuleNotFoundError:
            self.fail("server.admin_competition is required for the competition admin closure")
        app = FastAPI()
        app.include_router(create_admin_competition_router(self.db_path))
        return TestClient(app)

    def profile_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "profile_key": "lingjing-guide",
            "name": "灵境导游",
            "persona": "温和、准确、只依据景区资料回答",
            "driver_provider": "opentalking",
            "avatar_asset_url": "/assets/guide-v1.png",
            "clothing_asset_url": "/assets/clothing-summer-v1.png",
            "clothing_version": "summer-2026",
            "voice": "yige",
            "source_video_url": "/uploads/neutral-source-v1.mp4",
            "source_video_kind": "real_source_video",
            "opentalking_avatar_id": "lingjing-guide-v1",
            "prewarm_status": "pending",
        }
        payload.update(overrides)
        return payload

    def test_init_db_adds_backward_compatible_competition_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                ).fetchall()
            }
            chunk_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()
            }
        finally:
            conn.close()

        self.assertTrue(
            {
                "digital_human_profiles",
                "digital_human_active",
                "knowledge_documents",
                "feedback",
                "quality_runs",
            }.issubset(tables)
        )
        self.assertIn("knowledge_document_id", chunk_columns)

    def test_init_db_migrates_feedback_sentiment_trace_columns(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy-feedback.db"
        conn = sqlite3.connect(legacy_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE feedback(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  log_id INTEGER,rating INTEGER,text TEXT NOT NULL,
                  sentiment TEXT NOT NULL,topics_json TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  recommendation TEXT NOT NULL DEFAULT '',
                  management_note TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,updated_at TEXT NOT NULL,resolved_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO feedback(
                  log_id,rating,text,sentiment,topics_json,status,recommendation,
                  management_note,created_at,updated_at
                ) VALUES(NULL,NULL,'旧反馈','neutral','[]','pending','','','2026-07-12','2026-07-12')
                """
            )
            init_db(conn)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
            row = conn.execute("SELECT * FROM feedback WHERE id=1").fetchone()
        finally:
            conn.close()

        self.assertIn("sentiment_source", columns)
        self.assertIn("sentiment_confidence", columns)
        self.assertEqual(row["sentiment_source"], "rules")
        self.assertEqual(row["sentiment_confidence"], 0.0)

    def test_profile_versions_preview_publish_and_rollback_active_resolution(self) -> None:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO digital_human_config(
                  id,name,voice,persona,avatar_mode,rtx_enabled,
                  opentalking_base_url,audio2face_base_url,updated_at
                ) VALUES(1,?,?,?,?,?,?,?,?)
                """,
                (
                    "旧版灵境导游",
                    "legacy-voice",
                    "旧版人设仍可读取",
                    "2d-fallback",
                    0,
                    "",
                    "",
                    "2026-07-11T08:00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            legacy = client.get("/api/admin/competition/digital-human/active")
            self.assertEqual(legacy.status_code, 200)
            self.assertEqual(legacy.json()["data"]["resolution_source"], "legacy_config")
            self.assertEqual(legacy.json()["data"]["voice"], "legacy-voice")

            created = client.post(
                "/api/admin/competition/digital-human/profiles",
                json=self.profile_payload(),
            )
            self.assertEqual(created.status_code, 201, created.text)
            version_one = created.json()["data"]
            self.assertEqual(version_one["version"], 1)
            self.assertEqual(version_one["status"], "draft")
            self.assertFalse(version_one["is_active"])

            preview = client.post(
                f"/api/admin/competition/digital-human/profiles/{version_one['id']}/preview",
                json={"sample_text": "欢迎来到灵山胜境"},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()["data"]["preview"]["status"], "configuration_ready")
            self.assertTrue(preview.json()["data"]["preview"]["real_neutral_motion_source"])

            voice_preview = client.post(
                f"/api/admin/competition/digital-human/profiles/{version_one['id']}/voice-preview",
                json={"text": "欢迎来到灵山胜境"},
            )
            self.assertEqual(voice_preview.status_code, 200, voice_preview.text)
            self.assertEqual(
                voice_preview.json()["data"]["synthesis_request"],
                {"text": "欢迎来到灵山胜境", "voice": "yige"},
            )
            self.assertEqual(voice_preview.json()["data"]["status"], "ready_for_synthesis")

            revised = client.post(
                f"/api/admin/competition/digital-human/profiles/{version_one['id']}/versions",
                json={
                    "voice": "xiaoyan",
                    "clothing_asset_url": "/assets/clothing-autumn-v2.png",
                    "clothing_version": "autumn-2026",
                },
            )
            self.assertEqual(revised.status_code, 201, revised.text)
            version_two = revised.json()["data"]
            self.assertEqual(version_two["version"], 2)
            self.assertEqual(version_two["voice"], "xiaoyan")
            self.assertEqual(version_two["persona"], version_one["persona"])

            published = client.post(
                f"/api/admin/competition/digital-human/profiles/{version_two['id']}/publish"
            )
            self.assertEqual(published.status_code, 200, published.text)
            self.assertTrue(published.json()["data"]["is_active"])

            active = client.get("/api/admin/competition/digital-human/active")
            self.assertEqual(active.status_code, 200)
            self.assertEqual(active.json()["data"]["resolution_source"], "published_profile")
            self.assertEqual(active.json()["data"]["version"], 2)
            self.assertEqual(active.json()["data"]["voice"], "xiaoyan")

            rollback = client.post(
                f"/api/admin/competition/digital-human/profiles/{version_one['id']}/publish"
            )
            self.assertEqual(rollback.status_code, 200, rollback.text)
            active_after_rollback = client.get("/api/admin/competition/digital-human/active")
            self.assertEqual(active_after_rollback.json()["data"]["version"], 1)
            self.assertEqual(active_after_rollback.json()["data"]["voice"], "yige")

            versions = client.get("/api/admin/competition/digital-human/profiles")
            self.assertEqual(versions.status_code, 200)
            self.assertEqual(len(versions.json()["data"]), 2)

    def test_legacy_resolution_prefers_official_session_avatar_and_provider(self) -> None:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO digital_human_config(
                  id,name,voice,persona,avatar_mode,rtx_enabled,
                  opentalking_base_url,audio2face_base_url,updated_at
                ) VALUES(1,?,?,?,?,?,?,?,?)
                """,
                (
                    "旧版灵境导游",
                    "legacy-voice",
                    "旧版配置",
                    "2d-fallback",
                    0,
                    "",
                    "",
                    "2026-07-11T08:00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with patch.dict(
            os.environ,
            {
                "OPENTALKING_SESSION_ENABLED": "true",
                "OPENTALKING_SESSION_AVATAR_ID": "lingjing-guide-quicktalk",
            },
            clear=False,
        ):
            with self.client() as client:
                response = client.get("/api/admin/competition/digital-human/active")

        self.assertEqual(response.status_code, 200, response.text)
        active = response.json()["data"]
        self.assertEqual(active["driver_provider"], "opentalking")
        self.assertEqual(active["opentalking_avatar_id"], "lingjing-guide-quicktalk")

    def test_still_image_preview_is_explicitly_labeled_as_fallback(self) -> None:
        with self.client() as client:
            created = client.post(
                "/api/admin/competition/digital-human/profiles",
                json=self.profile_payload(
                    source_video_url="",
                    source_video_kind="still_image_fallback",
                ),
            )
            self.assertEqual(created.status_code, 201, created.text)
            profile_id = created.json()["data"]["id"]
            preview = client.post(
                f"/api/admin/competition/digital-human/profiles/{profile_id}/preview",
                json={},
            )

        self.assertEqual(preview.status_code, 200, preview.text)
        preview_data = preview.json()["data"]["preview"]
        self.assertFalse(preview_data["real_neutral_motion_source"])
        self.assertEqual(preview_data["asset_label"], "静态形象兼容兜底")

    def test_knowledge_edit_reindex_and_delete_updates_real_retrieval_rows(self) -> None:
        with self.client() as client:
            created = client.post(
                "/api/admin/competition/knowledge/documents",
                json={
                    "title": "九龙灌浴临时公告",
                    "content": "今日演出时间为十点。",
                    "source_name": "运营维护",
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            document = created.json()["data"]
            self.assertEqual(document["content_version"], 1)
            self.assertEqual(document["index_version"], 0)
            self.assertEqual(document["index_status"], "pending")

            indexed = client.post(
                f"/api/admin/competition/knowledge/documents/{document['id']}/reindex"
            )
            self.assertEqual(indexed.status_code, 200, indexed.text)
            self.assertEqual(indexed.json()["data"]["index_version"], 1)
            self.assertEqual(indexed.json()["data"]["index_status"], "indexed")

            updated = client.put(
                f"/api/admin/competition/knowledge/documents/{document['id']}",
                json={"content": "今日演出时间调整为十一点三十分。"},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["data"]["content_version"], 2)
            self.assertEqual(updated.json()["data"]["index_version"], 1)
            self.assertEqual(updated.json()["data"]["index_status"], "pending")

            reindexed = client.post(
                f"/api/admin/competition/knowledge/documents/{document['id']}/reindex"
            )
            self.assertEqual(reindexed.status_code, 200, reindexed.text)
            self.assertEqual(reindexed.json()["data"]["index_version"], 2)

            conn = connect(self.db_path)
            try:
                chunks = conn.execute(
                    "SELECT id,content FROM knowledge_chunks WHERE knowledge_document_id=?",
                    (document["id"],),
                ).fetchall()
                fts_rows = conn.execute(
                    "SELECT content FROM knowledge_fts WHERE chunk_id=?", (chunks[0]["id"],)
                ).fetchall()
            finally:
                conn.close()
            self.assertEqual(len(chunks), 1)
            self.assertIn("十一点三十分", chunks[0]["content"])
            self.assertEqual(len(fts_rows), 1)

            deleted = client.delete(
                f"/api/admin/competition/knowledge/documents/{document['id']}"
            )
            self.assertEqual(deleted.status_code, 200, deleted.text)
            self.assertEqual(deleted.json()["data"]["status"], "deleted")
            self.assertEqual(deleted.json()["data"]["index_status"], "deleted")
            visible = client.get("/api/admin/competition/knowledge/documents")
            self.assertEqual(visible.json()["data"], [])

        conn = connect(self.db_path)
        try:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunks WHERE knowledge_document_id=?",
                (document["id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(remaining, 0)

    def test_local_package_sources_are_visible_in_knowledge_management(self) -> None:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO source_files(name,path,file_type,checksum,imported_at,records_count)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    "灵山胜境 景点结构化数据集.docx",
                    "示范景区公开资料包/灵山胜境 景点结构化数据集.docx",
                    "docx",
                    "checksum-1",
                    "2026-07-11T08:00:00",
                    22,
                ),
            )
            conn.execute(
                """
                INSERT INTO knowledge_chunks(source_file,source_type,title,content,metadata_json)
                VALUES(?,?,?,?,?)
                """,
                (
                    "灵山胜境 景点结构化数据集.docx",
                    "document",
                    "九龙灌浴",
                    "九龙灌浴资料",
                    "{}",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            documents = client.get("/api/admin/competition/knowledge/documents")
            overview = client.get("/api/admin/competition/overview")

        self.assertEqual(documents.status_code, 200, documents.text)
        source = documents.json()["data"][0]
        self.assertEqual(source["title"], "灵山胜境 景点结构化数据集.docx")
        self.assertEqual(source["document_kind"], "source_file")
        self.assertFalse(source["editable"])
        self.assertEqual(source["index_status"], "indexed")
        self.assertEqual(source["chunk_count"], 1)
        self.assertEqual(overview.json()["data"]["knowledge"]["documents"], 1)
        self.assertEqual(overview.json()["data"]["knowledge"]["indexed"], 1)

    def test_dashboard_spreadsheet_is_reported_as_loaded_source_data(self) -> None:
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO source_files(name,path,file_type,checksum,imported_at,records_count)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    "景区旅游数据行为分析数据.xlsx",
                    "示范景区公开资料包/景区旅游数据行为分析数据.xlsx",
                    "xlsx",
                    "checksum-dashboard",
                    "2026-07-11T08:00:00",
                    140447,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            documents = client.get("/api/admin/competition/knowledge/documents")
            overview = client.get("/api/admin/competition/overview")

        self.assertEqual(documents.status_code, 200, documents.text)
        source = documents.json()["data"][0]
        self.assertEqual(source["file_type"], "xlsx")
        self.assertEqual(source["records_count"], 140447)
        self.assertEqual(source["chunk_count"], 0)
        self.assertEqual(source["index_status"], "indexed")
        self.assertIn("140447", source["content"])
        self.assertEqual(overview.json()["data"]["knowledge"]["indexed"], 1)

    def test_full_knowledge_reset_marks_managed_documents_pending(self) -> None:
        with self.client() as client:
            created = client.post(
                "/api/admin/competition/knowledge/documents",
                json={"title": "运营公告", "content": "需要保留的运营知识。"},
            ).json()["data"]
            indexed = client.post(
                f"/api/admin/competition/knowledge/documents/{created['id']}/reindex"
            )
            self.assertEqual(indexed.status_code, 200, indexed.text)

        conn = connect(self.db_path)
        try:
            reset_content(conn)
            document = conn.execute(
                "SELECT * FROM knowledge_documents WHERE id=?", (created["id"],)
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(document["status"], "active")
        self.assertEqual(document["content_version"], 1)
        self.assertEqual(document["index_version"], 0)
        self.assertEqual(document["index_status"], "pending")

    def test_text_feedback_infers_topics_and_supports_management_closure(self) -> None:
        with self.client() as client:
            created = client.post(
                "/api/feedback/text",
                json={"rating": 2, "text": "排队太久，路线指引也不清楚"},
            )
            self.assertEqual(created.status_code, 201, created.text)
            feedback = created.json()["data"]
            self.assertEqual(feedback["sentiment"], "negative")
            self.assertIn("crowding", feedback["topics"])
            self.assertIn("navigation", feedback["topics"])
            self.assertEqual(feedback["status"], "pending")

            listed = client.get(
                "/api/admin/competition/feedback", params={"status": "pending"}
            )
            self.assertEqual(listed.status_code, 200)
            self.assertEqual([item["id"] for item in listed.json()["data"]], [feedback["id"]])

            closed = client.patch(
                f"/api/admin/competition/feedback/{feedback['id']}",
                json={
                    "status": "resolved",
                    "recommendation": "高峰时段增加分流提示",
                    "management_note": "已同步现场运营组",
                },
            )
            self.assertEqual(closed.status_code, 200, closed.text)
            closed_data = closed.json()["data"]
            self.assertEqual(closed_data["status"], "resolved")
            self.assertEqual(closed_data["recommendation"], "高峰时段增加分流提示")
            self.assertEqual(closed_data["management_note"], "已同步现场运营组")

    def test_text_feedback_uses_qwen_sentiment_with_trace_metadata(self) -> None:
        with patch(
            "server.admin_competition.classify_feedback_sentiment",
            return_value={
                "sentiment": "negative",
                "confidence": 0.91,
                "reason": "游客对等候时间不满。",
            },
            create=True,
        ) as classifier, self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={"text": "排队等得有点久"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.assertEqual(data["sentiment"], "negative")
        self.assertEqual(data.get("sentiment_source"), "qwen")
        self.assertEqual(data.get("sentiment_confidence"), 0.91)
        classifier.assert_called_once_with("排队等得有点久")

    def test_text_feedback_falls_back_when_qwen_sentiment_fails(self) -> None:
        with patch(
            "server.admin_competition.classify_feedback_sentiment",
            side_effect=TimeoutError("timeout"),
            create=True,
        ), self.client() as client:
            rated = client.post(
                "/api/feedback/text", json={"rating": 2, "text": "体验需要改进"}
            )
            ruled = client.post(
                "/api/feedback/text", json={"text": "路线指引不清楚"}
            )

        self.assertEqual(rated.status_code, 201, rated.text)
        self.assertEqual(rated.json()["data"]["sentiment"], "negative")
        self.assertEqual(rated.json()["data"].get("sentiment_source"), "rating")
        self.assertEqual(rated.json()["data"].get("sentiment_confidence"), 1.0)
        self.assertEqual(ruled.status_code, 201, ruled.text)
        self.assertEqual(ruled.json()["data"]["sentiment"], "negative")
        self.assertEqual(ruled.json()["data"].get("sentiment_source"), "rules")
        self.assertGreater(ruled.json()["data"].get("sentiment_confidence", 0), 0)

    def test_explicit_sentiment_skips_qwen_classifier(self) -> None:
        with patch(
            "server.admin_competition.classify_feedback_sentiment", create=True
        ) as classifier, self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={"text": "我想补充一条建议", "sentiment": "neutral"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.assertEqual(data["sentiment"], "neutral")
        self.assertEqual(data.get("sentiment_source"), "manual")
        self.assertEqual(data.get("sentiment_confidence"), 1.0)
        classifier.assert_not_called()

    def test_repeat_feedback_for_same_question_updates_instead_of_duplicating(self) -> None:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO qa_logs(question,answer,sources_json,provider,created_at)
                VALUES(?,?,?,?,?)
                """,
                ("路线怎么走？", "回答", "[]", "test", "2026-07-12T10:00:00"),
            )
            log_id = int(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()
        with self.client() as client:
            first = client.post(
                "/api/feedback/text",
                json={
                    "log_id": log_id,
                    "rating": 4,
                    "text": "仅提交星级评价",
                    "sentiment": "positive",
                },
            )
            second = client.post(
                "/api/feedback/text",
                json={
                    "log_id": log_id,
                    "rating": 2,
                    "text": "排队时间太长",
                    "sentiment": "negative",
                },
            )
            listed = client.get("/api/admin/competition/feedback")

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(len(listed.json()["data"]), 1)
        self.assertEqual(listed.json()["data"][0]["text"], "排队时间太长")
        self.assertEqual(listed.json()["data"][0]["sentiment"], "negative")

    def test_text_feedback_keeps_realtime_dashboard_rating_in_sync(self) -> None:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO qa_logs(question,answer,sources_json,provider,created_at)
                VALUES(?,?,?,?,?)
                """,
                ("路线怎么走？", "回答", "[]", "test", "2026-07-12T10:00:00"),
            )
            log_id = int(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={
                    "log_id": log_id,
                    "rating": 2,
                    "text": "路线指引不清楚",
                    "sentiment": "negative",
                },
            )

        self.assertEqual(response.status_code, 201, response.text)
        conn = connect(self.db_path)
        try:
            log = conn.execute("SELECT * FROM qa_logs WHERE id=?", (log_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(log["rating"], 2)
        self.assertEqual(log["feeling"], "待改进")
        self.assertEqual(log["note"], "路线指引不清楚")

        with self.client() as client:
            repeated = client.post(
                "/api/feedback/text",
                json={
                    "log_id": log_id,
                    "rating": 5,
                    "text": "现在很清楚",
                    "sentiment": "positive",
                },
            )

        self.assertEqual(repeated.status_code, 201, repeated.text)
        conn = connect(self.db_path)
        try:
            updated_log = conn.execute("SELECT * FROM qa_logs WHERE id=?", (log_id,)).fetchone()
            feedback_count = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE log_id=?", (log_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(updated_log["rating"], 5)
        self.assertEqual(updated_log["feeling"], "满意")
        self.assertEqual(updated_log["note"], "现在很清楚")
        self.assertEqual(feedback_count, 1)

    def test_text_feedback_without_rating_preserves_existing_log_rating(self) -> None:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO qa_logs(
                  question,answer,sources_json,provider,created_at,rating,feeling,note
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    "路线怎么走？",
                    "回答",
                    "[]",
                    "test",
                    "2026-07-12T10:00:00",
                    4,
                    "有帮助",
                    "原评价",
                ),
            )
            log_id = int(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={"log_id": log_id, "text": "希望补充无障碍路线提示"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        conn = connect(self.db_path)
        try:
            log = conn.execute("SELECT * FROM qa_logs WHERE id=?", (log_id,)).fetchone()
            feedback = conn.execute(
                "SELECT * FROM feedback WHERE log_id=?", (log_id,)
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(log["rating"], 4)
        self.assertEqual(log["feeling"], "有帮助")
        self.assertEqual(log["note"], "希望补充无障碍路线提示")
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["rating"], 4)

    def test_text_feedback_rejects_unknown_log_id_without_orphan(self) -> None:
        with self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={"log_id": 999999, "rating": 2, "text": "路线指引不清楚"},
            )

        self.assertGreaterEqual(response.status_code, 400, response.text)
        self.assertLess(response.status_code, 500, response.text)
        conn = connect(self.db_path)
        try:
            feedback_count = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(feedback_count, 0)

    def test_legacy_ratings_are_backfilled_once_into_management_feedback(self) -> None:
        conn = connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO qa_logs(
                  question,answer,sources_json,provider,created_at,rating,feeling,note
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    "九龙灌浴几点开始？",
                    "回答",
                    "[]",
                    "test",
                    "2026-07-11T09:30:00",
                    2,
                    "待改进",
                    "排队时间太长",
                ),
            )
            log_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO qa_logs(question,answer,sources_json,provider,created_at)
                VALUES(?,?,?,?,?)
                """,
                ("没有评分的问答", "回答", "[]", "test", "2026-07-11T09:31:00"),
            )
            conn.commit()
        finally:
            conn.close()

        with self.client() as client:
            first = client.get("/api/admin/competition/feedback")
            second = client.get("/api/admin/competition/feedback")

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(first.json()["data"]), 1)
        self.assertEqual(first.json()["data"][0]["log_id"], log_id)
        self.assertEqual(first.json()["data"][0]["sentiment"], "negative")
        self.assertEqual(first.json()["data"][0].get("sentiment_source"), "rating")
        self.assertEqual(first.json()["data"][0].get("sentiment_confidence"), 1.0)
        self.assertEqual(first.json()["data"][0]["text"], "排队时间太长")
        self.assertEqual(len(second.json()["data"]), 1)
        conn = connect(self.db_path)
        try:
            feedback_count = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(feedback_count, 1)

    def test_text_only_negative_feedback_is_not_cancelled_by_a_positive_substring(self) -> None:
        with self.client() as client:
            response = client.post(
                "/api/feedback/text",
                json={"text": "讲解不清楚"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["data"]["sentiment"], "negative")

    def test_quality_runs_persist_list_latest_and_guard_official_claims(self) -> None:
        payload = {
            "dataset_version": "scenic-qa-2026-07-11",
            "accuracy": 0.91,
            "sample_count": 11,
            "passed_count": 10,
            "sample_details": [{"question": "示例问题", "passed": True}],
            "latency_ms": {"asr": 180.0, "retrieval_llm": 620.0, "tts": 310.0},
            "environment": {"scope": "local", "gpu": "RTX 4060 8GB"},
        }
        with self.client() as client:
            created = client.post(
                "/api/admin/competition/quality-runs", json=payload
            )
            self.assertEqual(created.status_code, 201, created.text)
            run = created.json()["data"]
            self.assertFalse(run["official_evaluation"])
            self.assertEqual(run["scope_label"], "本地自测数据")

            latest = client.get("/api/admin/competition/quality-runs/latest")
            self.assertEqual(latest.status_code, 200)
            self.assertEqual(latest.json()["data"]["id"], run["id"])

            listed = client.get("/api/admin/competition/quality-runs")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual([item["id"] for item in listed.json()["data"]], [run["id"]])

            unsupported_claim = client.post(
                "/api/admin/competition/quality-runs",
                json={**payload, "official_evaluation": True},
            )
            self.assertEqual(unsupported_claim.status_code, 422, unsupported_claim.text)
            self.assertIn("official_evidence_reference", unsupported_claim.text)

    def test_overview_reports_operational_counts_and_data_provenance(self) -> None:
        with self.client() as client:
            profile = client.post(
                "/api/admin/competition/digital-human/profiles",
                json=self.profile_payload(),
            ).json()["data"]
            client.post(
                f"/api/admin/competition/digital-human/profiles/{profile['id']}/publish"
            )
            client.post(
                "/api/admin/competition/knowledge/documents",
                json={"title": "运营公告", "content": "景区公告内容。"},
            )
            client.post(
                "/api/feedback/text",
                json={"rating": 5, "text": "讲解很清楚"},
            )
            client.post(
                "/api/admin/competition/quality-runs",
                json={
                    "dataset_version": "local-v1",
                    "accuracy": 1.0,
                    "sample_count": 1,
                    "passed_count": 1,
                    "sample_details": [],
                    "latency_ms": {},
                    "environment": {"scope": "local"},
                },
            )

            response = client.get("/api/admin/competition/overview")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["digital_human"]["profile_versions"], 1)
        self.assertEqual(data["digital_human"]["active_profile"]["id"], profile["id"])
        self.assertEqual(data["knowledge"]["documents"], 1)
        self.assertEqual(data["feedback"]["total"], 1)
        self.assertEqual(data["quality"]["runs"], 1)
        self.assertEqual(data["quality"]["latest"]["scope_label"], "本地自测数据")
        self.assertEqual(
            data["provenance"],
            {
                "operations": "实时交互数据",
                "scenic": "示例景区数据",
                "quality": "本地自测数据或带凭证的官方评测数据",
            },
        )


if __name__ == "__main__":
    unittest.main()
