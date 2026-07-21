"""Structured data models for agent I/O and the final content package."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class VisualType(str, Enum):
    STOCK = "stock"
    AI = "ai"


class SchemaError(ValueError):
    """Raised when agent JSON does not match the expected schema."""


def _require_key(data: dict[str, Any], key: str, context: str) -> Any:
    if key not in data:
        raise SchemaError(f"Missing required field '{key}' in {context}")
    return data[key]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


@dataclass
class TopicSelection:
    topic: str
    angle: str
    target_audience: str
    estimated_interest: int
    search_keywords: list[str]
    why_now: str
    risk_level: str
    risk_note: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopicSelection:
        keywords = _require_key(data, "search_keywords", "TopicSelection")
        if not isinstance(keywords, list) or len(keywords) < 1:
            raise SchemaError("TopicSelection.search_keywords must be a non-empty list")
        interest = int(_require_key(data, "estimated_interest", "TopicSelection"))
        if not 1 <= interest <= 10:
            raise SchemaError("TopicSelection.estimated_interest must be between 1 and 10")
        return cls(
            topic=str(_require_key(data, "topic", "TopicSelection")),
            angle=str(_require_key(data, "angle", "TopicSelection")),
            target_audience=str(_require_key(data, "target_audience", "TopicSelection")),
            estimated_interest=interest,
            search_keywords=[str(k) for k in keywords],
            why_now=str(_require_key(data, "why_now", "TopicSelection")),
            risk_level=str(_require_key(data, "risk_level", "TopicSelection")),
            risk_note=_optional_str(data.get("risk_note")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Scene:
    id: int
    start_sec: int
    end_sec: int
    narration: str
    visual_type: VisualType
    stock_keyword: str | None
    visual_prompt: str | None
    on_screen_text: str | None = None
    asset_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        visual_raw = str(_require_key(data, "visual_type", "Scene")).lower()
        try:
            visual_type = VisualType(visual_raw)
        except ValueError as exc:
            raise SchemaError(f"Scene.visual_type must be 'stock' or 'ai', got '{visual_raw}'") from exc

        stock_keyword = _optional_str(data.get("stock_keyword"))
        visual_prompt = _optional_str(data.get("visual_prompt"))

        if visual_type == VisualType.STOCK and not stock_keyword:
            raise SchemaError(f"Scene {data.get('id')}: stock scenes require stock_keyword")
        if visual_type == VisualType.AI and not visual_prompt:
            raise SchemaError(f"Scene {data.get('id')}: ai scenes require visual_prompt")

        return cls(
            id=int(_require_key(data, "id", "Scene")),
            start_sec=int(_require_key(data, "start_sec", "Scene")),
            end_sec=int(_require_key(data, "end_sec", "Scene")),
            narration=str(_require_key(data, "narration", "Scene")),
            visual_type=visual_type,
            stock_keyword=stock_keyword,
            visual_prompt=visual_prompt,
            on_screen_text=_optional_str(data.get("on_screen_text")),
            asset_path=_optional_str(data.get("asset_path")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["visual_type"] = self.visual_type.value
        return payload


@dataclass
class ThumbnailPlan:
    concept: str
    prompt: str
    overlay_text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThumbnailPlan:
        return cls(
            concept=str(_require_key(data, "concept", "ThumbnailPlan")),
            prompt=str(_require_key(data, "prompt", "ThumbnailPlan")),
            overlay_text=str(_require_key(data, "overlay_text", "ThumbnailPlan")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeoPackage:
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    category: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeoPackage:
        tags = _require_key(data, "tags", "SeoPackage")
        hashtags = _require_key(data, "hashtags", "SeoPackage")
        if not isinstance(tags, list) or not isinstance(hashtags, list):
            raise SchemaError("SeoPackage tags and hashtags must be lists")
        title = str(_require_key(data, "title", "SeoPackage"))
        if len(title) > 100:
            raise SchemaError("SeoPackage.title exceeds 100 characters")
        return cls(
            title=title,
            description=str(_require_key(data, "description", "SeoPackage")),
            tags=[str(t) for t in tags],
            hashtags=[str(h) for h in hashtags],
            category=str(_require_key(data, "category", "SeoPackage")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceInfo:
    altered_content_label: bool
    risk_notes: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComplianceInfo:
        return cls(
            altered_content_label=bool(_require_key(data, "altered_content_label", "ComplianceInfo")),
            risk_notes=str(_require_key(data, "risk_notes", "ComplianceInfo")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentPlan:
    """Master Content Agent output — approved script and storyboard."""

    topic: str
    format: str
    aspect_ratio: str
    target_duration_sec: int
    quality_score: int
    hook: str
    full_narration: str
    scenes: list[Scene]
    cta: str
    music_mood: str
    thumbnail: ThumbnailPlan
    seo: SeoPackage
    compliance: ComplianceInfo

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentPlan:
        scenes_raw = _require_key(data, "scenes", "ContentPlan")
        if not isinstance(scenes_raw, list) or len(scenes_raw) < 1:
            raise SchemaError("ContentPlan.scenes must be a non-empty list")
        score = int(_require_key(data, "quality_score", "ContentPlan"))
        if not 1 <= score <= 10:
            raise SchemaError("ContentPlan.quality_score must be between 1 and 10")
        return cls(
            topic=str(_require_key(data, "topic", "ContentPlan")),
            format=str(_require_key(data, "format", "ContentPlan")),
            aspect_ratio=str(_require_key(data, "aspect_ratio", "ContentPlan")),
            target_duration_sec=int(_require_key(data, "target_duration_sec", "ContentPlan")),
            quality_score=score,
            hook=str(_require_key(data, "hook", "ContentPlan")),
            full_narration=str(_require_key(data, "full_narration", "ContentPlan")),
            scenes=[Scene.from_dict(s) for s in scenes_raw],
            cta=str(_require_key(data, "cta", "ContentPlan")),
            music_mood=str(_require_key(data, "music_mood", "ContentPlan")),
            thumbnail=ThumbnailPlan.from_dict(_require_key(data, "thumbnail", "ContentPlan")),
            seo=SeoPackage.from_dict(_require_key(data, "seo", "ContentPlan")),
            compliance=ComplianceInfo.from_dict(_require_key(data, "compliance", "ContentPlan")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "format": self.format,
            "aspect_ratio": self.aspect_ratio,
            "target_duration_sec": self.target_duration_sec,
            "quality_score": self.quality_score,
            "hook": self.hook,
            "full_narration": self.full_narration,
            "scenes": [s.to_dict() for s in self.scenes],
            "cta": self.cta,
            "music_mood": self.music_mood,
            "thumbnail": self.thumbnail.to_dict(),
            "seo": self.seo.to_dict(),
            "compliance": self.compliance.to_dict(),
        }


@dataclass
class ReviewScores:
    originality: int
    hook_strength: int
    factual_safety: int
    retention: int
    policy_risk: int
    pacing: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewScores:
        fields = ["originality", "hook_strength", "factual_safety", "retention", "policy_risk", "pacing"]
        values: dict[str, int] = {}
        for name in fields:
            value = int(_require_key(data, name, "ReviewScores"))
            if not 1 <= value <= 10:
                raise SchemaError(f"ReviewScores.{name} must be between 1 and 10")
            values[name] = value
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    decision: ReviewDecision
    scores: ReviewScores
    overall: float
    issues: list[str]
    fix_instructions: list[str]
    summary: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewResult:
        decision_raw = str(_require_key(data, "decision", "ReviewResult")).upper()
        try:
            decision = ReviewDecision(decision_raw)
        except ValueError as exc:
            raise SchemaError(f"ReviewResult.decision must be APPROVE or REJECT, got '{decision_raw}'") from exc

        issues = _require_key(data, "issues", "ReviewResult")
        fixes = _require_key(data, "fix_instructions", "ReviewResult")
        if not isinstance(issues, list) or not isinstance(fixes, list):
            raise SchemaError("ReviewResult issues and fix_instructions must be lists")

        if decision == ReviewDecision.APPROVE and fixes:
            raise SchemaError("ReviewResult.fix_instructions must be empty when decision is APPROVE")
        if decision == ReviewDecision.REJECT and not fixes:
            raise SchemaError("ReviewResult.fix_instructions required when decision is REJECT")

        return cls(
            decision=decision,
            scores=ReviewScores.from_dict(_require_key(data, "scores", "ReviewResult")),
            overall=float(_require_key(data, "overall", "ReviewResult")),
            issues=[str(i) for i in issues],
            fix_instructions=[str(f) for f in fixes],
            summary=str(_require_key(data, "summary", "ReviewResult")),
        )

    def is_approved(self) -> bool:
        return self.decision == ReviewDecision.APPROVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "scores": self.scores.to_dict(),
            "overall": self.overall,
            "issues": self.issues,
            "fix_instructions": self.fix_instructions,
            "summary": self.summary,
        }


@dataclass
class PlatformOverrides:
    youtube: dict[str, Any] = field(default_factory=dict)
    tiktok: dict[str, Any] = field(default_factory=dict)
    instagram: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "youtube": self.youtube,
            "tiktok": self.tiktok,
            "instagram": self.instagram,
        }


@dataclass
class ProductionAssets:
    video_path: str | None = None
    thumbnail_path: str | None = None
    voice_path: str | None = None
    scene_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentPackage:
    """
    Final artifact written to output/<package_id>/content_package.json after a successful run.
    Bridges production (core) and publishing (publishers).
    """

    package_id: str
    created_at: str
    channel_niche: str
    channel_niche_label: str
    channel_name: str
    topic: TopicSelection
    content_plan: ContentPlan
    review: ReviewResult
    assets: ProductionAssets
    platform_overrides: PlatformOverrides
    status: str = "ready"  # ready | published | failed

    @classmethod
    def create(
        cls,
        *,
        channel_niche: str,
        channel_niche_label: str,
        channel_name: str,
        topic: TopicSelection,
        content_plan: ContentPlan,
        review: ReviewResult,
        package_id: str | None = None,
    ) -> ContentPackage:
        if not review.is_approved():
            raise SchemaError("ContentPackage requires an APPROVED review result")
        return cls(
            package_id=package_id or str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            channel_niche=channel_niche,
            channel_niche_label=channel_niche_label,
            channel_name=channel_name,
            topic=topic,
            content_plan=content_plan,
            review=review,
            assets=ProductionAssets(),
            platform_overrides=PlatformOverrides(
                youtube={
                    "title": content_plan.seo.title,
                    "description": content_plan.seo.description,
                    "tags": content_plan.seo.tags,
                    "category": content_plan.seo.category,
                },
                tiktok={
                    "caption": f"{content_plan.seo.title}\n\n{' '.join(content_plan.seo.hashtags)}",
                },
                instagram={
                    "caption": f"{content_plan.seo.title}\n\n{' '.join(content_plan.seo.hashtags)}",
                },
            ),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentPackage:
        assets_raw = data.get("assets") or {}
        overrides_raw = data.get("platform_overrides") or {}
        return cls(
            package_id=str(_require_key(data, "package_id", "ContentPackage")),
            created_at=str(_require_key(data, "created_at", "ContentPackage")),
            channel_niche=str(_require_key(data, "channel_niche", "ContentPackage")),
            channel_niche_label=str(_require_key(data, "channel_niche_label", "ContentPackage")),
            channel_name=str(_require_key(data, "channel_name", "ContentPackage")),
            topic=TopicSelection.from_dict(_require_key(data, "topic", "ContentPackage")),
            content_plan=ContentPlan.from_dict(_require_key(data, "content_plan", "ContentPackage")),
            review=ReviewResult.from_dict(_require_key(data, "review", "ContentPackage")),
            assets=ProductionAssets(
                video_path=_optional_str(assets_raw.get("video_path")),
                thumbnail_path=_optional_str(assets_raw.get("thumbnail_path")),
                voice_path=_optional_str(assets_raw.get("voice_path")),
                scene_paths=list(assets_raw.get("scene_paths") or []),
            ),
            platform_overrides=PlatformOverrides(
                youtube=dict(overrides_raw.get("youtube") or {}),
                tiktok=dict(overrides_raw.get("tiktok") or {}),
                instagram=dict(overrides_raw.get("instagram") or {}),
            ),
            status=str(data.get("status", "ready")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "created_at": self.created_at,
            "channel_niche": self.channel_niche,
            "channel_niche_label": self.channel_niche_label,
            "channel_name": self.channel_name,
            "topic": self.topic.to_dict(),
            "content_plan": self.content_plan.to_dict(),
            "review": self.review.to_dict(),
            "assets": self.assets.to_dict(),
            "platform_overrides": self.platform_overrides.to_dict(),
            "status": self.status,
        }
