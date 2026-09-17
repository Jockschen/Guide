from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    image_base64: str | None = None
    guide_style: str = Field(default="自然讲解", max_length=40)
    voice_preset: str = Field(default="gentle", max_length=40)


class RoutePlanRequest(BaseModel):
    interest: str = Field(default="经典半日路线", max_length=300)


class FeedbackRequest(BaseModel):
    log_id: int
    rating: int = Field(ge=1, le=5)
    feeling: str = Field(default="neutral", max_length=40)
    note: str = Field(default="", max_length=500)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="published", max_length=120)
    style: str = Field(default="自然讲解", max_length=40)
    speed: float = Field(default=1.0, ge=0.6, le=1.4)
    volume: float = Field(default=0.86, ge=0.0, le=1.0)


class LipsyncRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    audio_url: str | None = None
    allow_demo: bool = False


class DigitalHumanConfigUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    voice: str = Field(min_length=1, max_length=60)
    persona: str = Field(min_length=1, max_length=500)
    avatar_mode: str = Field(default="2d-fallback", max_length=40)
    opentalking_base_url: str = ""


DigitalHumanProvider = Literal["opentalking", "flashtalk", "flashhead", "legacy_mp4", "audio_only"]
SourceVideoKind = Literal["real_source_video", "still_image_fallback"]
PrewarmStatus = Literal["pending", "ready", "failed", "unavailable"]


class DigitalHumanProfileCreate(BaseModel):
    profile_key: str = Field(default="lingjing-guide", min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    persona: str = Field(min_length=1, max_length=2000)
    driver_provider: DigitalHumanProvider = "opentalking"
    avatar_asset_url: str = Field(default="", max_length=1000)
    clothing_asset_url: str = Field(default="", max_length=1000)
    clothing_version: str = Field(default="", max_length=120)
    voice: str = Field(min_length=1, max_length=120)
    source_video_url: str = Field(default="", max_length=1000)
    source_video_kind: SourceVideoKind = "still_image_fallback"
    opentalking_avatar_id: str = Field(default="", max_length=200)
    prewarm_status: PrewarmStatus = "pending"

    @model_validator(mode="after")
    def real_source_video_requires_an_asset(self) -> "DigitalHumanProfileCreate":
        if self.source_video_kind == "real_source_video" and not self.source_video_url.strip():
            raise ValueError("source_video_url is required for real_source_video")
        return self


class DigitalHumanProfileVersionCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    persona: str | None = Field(default=None, min_length=1, max_length=2000)
    driver_provider: DigitalHumanProvider | None = None
    avatar_asset_url: str | None = Field(default=None, max_length=1000)
    clothing_asset_url: str | None = Field(default=None, max_length=1000)
    clothing_version: str | None = Field(default=None, max_length=120)
    voice: str | None = Field(default=None, min_length=1, max_length=120)
    source_video_url: str | None = Field(default=None, max_length=1000)
    source_video_kind: SourceVideoKind | None = None
    opentalking_avatar_id: str | None = Field(default=None, max_length=200)
    prewarm_status: PrewarmStatus | None = None

    @model_validator(mode="after")
    def has_an_override(self) -> "DigitalHumanProfileVersionCreate":
        if not self.model_fields_set:
            raise ValueError("at least one profile field is required")
        return self


class DigitalHumanPreviewRequest(BaseModel):
    sample_text: str = Field(default="欢迎来到灵山胜境", min_length=1, max_length=500)


class VoicePreviewRequest(BaseModel):
    text: str = Field(default="欢迎来到灵山胜境", min_length=1, max_length=1000)


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)
    source_name: str = Field(default="运营维护", min_length=1, max_length=300)


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    source_name: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def has_an_update(self) -> "KnowledgeDocumentUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one knowledge field is required")
        return self


class TextFeedbackCreate(BaseModel):
    log_id: int | None = Field(default=None, ge=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)
    sentiment: Literal["positive", "neutral", "negative"] | None = None
    topics: list[str] = Field(default_factory=list, max_length=12)


class FeedbackManagementUpdate(BaseModel):
    status: Literal["pending", "acknowledged", "resolved"] | None = None
    recommendation: str | None = Field(default=None, max_length=2000)
    management_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def has_an_update(self) -> "FeedbackManagementUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one feedback field is required")
        return self


class QualityRunCreate(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=200)
    accuracy: float = Field(ge=0.0, le=1.0)
    sample_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    sample_details: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    official_evaluation: bool = False
    official_evidence_reference: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validates_evidence_and_counts(self) -> "QualityRunCreate":
        if self.passed_count > self.sample_count:
            raise ValueError("passed_count cannot exceed sample_count")
        if self.official_evaluation and not self.official_evidence_reference.strip():
            raise ValueError(
                "official_evidence_reference is required when official_evaluation is true"
            )
        return self


class ApiResponse(BaseModel):
    ok: bool
    data: Any = None
    message: str = ""
