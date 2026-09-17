from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .admin_competition import get_active_digital_human_profile
from .config import settings


PUBLISHED_VOICE_TOKENS = {"", "published", "default", "active"}


def active_profile() -> dict[str, Any]:
    return dict(get_active_digital_human_profile())


def resolve_tts_voice(requested_voice: str | None, profile: Mapping[str, Any]) -> str:
    requested = str(requested_voice or "").strip()
    if requested.casefold() not in PUBLISHED_VOICE_TOKENS:
        return requested
    return str(profile.get("voice") or settings.vivo_tts_voice or "gentle").strip()


def public_profile_data(profile: Mapping[str, Any]) -> dict[str, Any]:
    source_kind = str(profile.get("source_video_kind") or "still_image_fallback")
    return {
        "id": profile.get("id"),
        "name": profile.get("name") or "灵境导游",
        "persona": profile.get("persona") or "温和、准确的景区数字人导游",
        "voice": profile.get("voice") or settings.vivo_tts_voice,
        "driver_provider": profile.get("driver_provider") or "audio_only",
        "avatar_asset_url": profile.get("avatar_asset_url") or "/assets/generated/avatar-guide-v2.png",
        "clothing_asset_url": profile.get("clothing_asset_url") or "",
        "clothing_version": profile.get("clothing_version") or "default",
        "source_video_url": profile.get("source_video_url") or "",
        "source_video_kind": source_kind,
        "real_neutral_motion_source": source_kind == "real_source_video",
        "opentalking_avatar_id": profile.get("opentalking_avatar_id") or "",
        "prewarm_status": profile.get("prewarm_status") or "unavailable",
        "version": profile.get("version") or 0,
        "status": profile.get("status") or "default",
        "resolution_source": profile.get("resolution_source") or "runtime_defaults",
    }
