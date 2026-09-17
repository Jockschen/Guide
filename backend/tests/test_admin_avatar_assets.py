from __future__ import annotations

import base64
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from server.admin_asset_api import create_admin_asset_router


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakePreparer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "avatar_id": "custom-lingjing-neutral-v2",
            "status": "ready",
            "runtime_status": "ready",
        }


class AdminAvatarAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.preparer = FakePreparer()
        app = FastAPI()
        app.include_router(
            create_admin_asset_router(
                storage_dir=Path(self.temp.name),
                avatar_preparer=self.preparer,
            )
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_avatar_image_is_saved_as_a_managed_asset(self) -> None:
        response = self.client.post(
            "/api/admin/competition/assets",
            data={"asset_kind": "avatar_image"},
            files={"file": ("guide.png", PNG_1X1, "image/png")},
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["asset_kind"], "avatar_image")
        self.assertTrue(data["url"].startswith("/static/admin-assets/avatar_image/"))
        self.assertEqual(len(data["sha256"]), 64)
        stored = Path(self.temp.name) / data["url"].removeprefix("/static/")
        self.assertTrue(stored.is_file())
        self.assertEqual(self.preparer.calls, [])

    def test_neutral_source_video_can_create_and_prewarm_official_avatar(self) -> None:
        mp4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 128
        response = self.client.post(
            "/api/admin/competition/assets",
            data={
                "asset_kind": "neutral_source_video",
                "prepare_avatar": "true",
                "display_name": "灵境导游中性微动作 v2",
            },
            files={"file": ("neutral.mp4", mp4, "video/mp4")},
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["source_video_kind"], "real_source_video")
        self.assertEqual(data["opentalking_avatar_id"], "custom-lingjing-neutral-v2")
        self.assertEqual(data["prewarm_status"], "ready")
        self.assertEqual(self.preparer.calls[0]["field_name"], "video")

    def test_unsupported_asset_kind_is_rejected(self) -> None:
        response = self.client.post(
            "/api/admin/competition/assets",
            data={"asset_kind": "unknown"},
            files={"file": ("guide.png", PNG_1X1, "image/png")},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
