from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import request as urllib_request
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from .config import settings


AssetKind = Literal["avatar_image", "clothing_image", "neutral_source_video"]
AvatarPreparer = Callable[..., Awaitable[dict[str, Any]]]

IMAGE_MAX_BYTES = 12 * 1024 * 1024
VIDEO_MAX_BYTES = 200 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", value.strip()).strip("-_")
    return clean[:48] or "lingjing-avatar"


def _looks_like_image(data: bytes, suffix: str) -> bool:
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8")
    if suffix == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _looks_like_video(data: bytes, suffix: str) -> bool:
    if suffix in {".mp4", ".mov"}:
        return b"ftyp" in data[:64]
    if suffix == ".webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    return False


def _multipart(
    fields: dict[str, str],
    *,
    field_name: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> tuple[bytes, str]:
    boundary = f"----lingjing-avatar-{uuid.uuid4().hex}"
    body: list[bytes] = []
    for key, value in fields.items():
        body.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    body.extend(
        [
            f"--{boundary}\r\n".encode("ascii"),
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
    )
    return b"".join(body), f"multipart/form-data; boundary={boundary}"


def _request_json(req: urllib_request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"OpenTalking avatar request failed (HTTP {exc.code}): {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"OpenTalking avatar service is unavailable: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OpenTalking avatar service returned an invalid response")
    return payload


async def prepare_opentalking_avatar(
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    field_name: str,
    display_name: str,
    base_avatar_id: str,
    model: str,
) -> dict[str, Any]:
    base_url = os.environ.get("OPENTALKING_SESSION_BASE_URL", "http://127.0.0.1:8210").rstrip("/")
    token = os.environ.get("OPENTALKING_API_TOKEN", "").strip()
    body, multipart_type = _multipart(
        {
            "base_avatar_id": base_avatar_id,
            "name": display_name,
            "model": model,
            "remove_background": "false",
        },
        field_name=field_name,
        filename=filename,
        content_type=content_type,
        content=file_bytes,
    )
    headers = {"Content-Type": multipart_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    create_req = urllib_request.Request(
        f"{base_url}/avatars/custom",
        data=body,
        method="POST",
        headers=headers,
    )
    created = await asyncio.to_thread(_request_json, create_req, 240.0)
    avatar_id = str(created.get("id") or "").strip()
    if not avatar_id:
        raise RuntimeError("OpenTalking did not return the new avatar id")

    prewarm_req = urllib_request.Request(
        f"{base_url}/avatars/{avatar_id}/prewarm",
        data=json.dumps({"model": model, "overwrite": False}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    prewarm = await asyncio.to_thread(_request_json, prewarm_req, 600.0)
    return {
        "avatar_id": avatar_id,
        "status": str(prewarm.get("status") or "ready"),
        "runtime_status": str(prewarm.get("runtime_status") or prewarm.get("status") or "ready"),
        "avatar": created,
        "prewarm": prewarm,
    }


def create_admin_asset_router(
    *,
    storage_dir: Path | None = None,
    avatar_preparer: AvatarPreparer | None = None,
) -> APIRouter:
    router = APIRouter(tags=["admin-assets"])
    root = storage_dir or settings.storage_dir
    prepare_avatar = avatar_preparer or prepare_opentalking_avatar

    @router.post(
        "/api/admin/competition/assets",
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_asset(
        asset_kind: AssetKind = Form(...),
        file: UploadFile = File(...),
        prepare_avatar_asset: bool = Form(default=False, alias="prepare_avatar"),
        display_name: str = Form(default="灵境导游形象"),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        is_video = asset_kind == "neutral_source_video"
        supported = VIDEO_SUFFIXES if is_video else IMAGE_SUFFIXES
        max_bytes = VIDEO_MAX_BYTES if is_video else IMAGE_MAX_BYTES
        if suffix not in supported:
            raise HTTPException(status_code=415, detail="不支持的形象素材格式。")
        content = await file.read(max_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="形象素材为空。")
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail="视频不能超过 200MB。" if is_video else "图片不能超过 12MB。",
            )
        valid = _looks_like_video(content, suffix) if is_video else _looks_like_image(content, suffix)
        if not valid:
            raise HTTPException(status_code=400, detail="形象素材内容与文件格式不匹配。")

        digest = hashlib.sha256(content).hexdigest()
        relative = Path("admin-assets") / asset_kind / f"{digest[:20]}{suffix}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(content)

        source_kind = "real_source_video" if is_video else "still_image_fallback"
        data: dict[str, Any] = {
            "asset_kind": asset_kind,
            "url": f"/static/{relative.as_posix()}",
            "media_type": file.content_type or "application/octet-stream",
            "bytes": len(content),
            "sha256": digest,
            "source_video_kind": source_kind,
            "opentalking_avatar_id": "",
            "prewarm_status": "pending" if prepare_avatar_asset else "unavailable",
        }

        if prepare_avatar_asset:
            if asset_kind == "clothing_image":
                raise HTTPException(status_code=422, detail="服装图不能单独生成数字人形象。")
            field_name = "video" if is_video else "image"
            try:
                prepared = await prepare_avatar(
                    file_bytes=content,
                    filename=file.filename or f"asset{suffix}",
                    content_type=file.content_type or "application/octet-stream",
                    field_name=field_name,
                    display_name=_safe_name(display_name),
                    base_avatar_id=os.environ.get(
                        "OPENTALKING_SESSION_AVATAR_ID",
                        "lingjing-guide-quicktalk",
                    ),
                    model=os.environ.get("OPENTALKING_SESSION_MODEL", "quicktalk"),
                )
            except Exception as exc:
                data["prewarm_status"] = "failed"
                data["prewarm_message"] = str(exc)[:1000]
            else:
                data["opentalking_avatar_id"] = prepared["avatar_id"]
                data["prewarm_status"] = (
                    "ready" if prepared.get("runtime_status") == "ready" else "failed"
                )
                data["prewarm"] = prepared

        return {"ok": True, "data": data}

    return router


router = create_admin_asset_router()

