"""Abstract publisher interface for platform upload adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from core.schemas import ContentPackage


class PublisherError(RuntimeError):
    """Raised when upload or authentication fails."""


@dataclass
class PublishResult:
    platform: str
    remote_id: str
    url: str
    title: str
    privacy_status: str
    thumbnail_applied: bool = True
    thumbnail_warning: str | None = None


class BasePublisher(ABC):
    """Upload adapter — one implementation per platform."""

    @abstractmethod
    def authenticate(self, *, interactive: bool = True) -> None:
        """Ensure valid credentials (may open a browser on first run)."""

    @abstractmethod
    def publish(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
        thumbnail_path: Path | None = None,
        category: str | None = None,
        privacy_status: str | None = None,
    ) -> PublishResult:
        """Upload video (+ optional thumbnail) with metadata."""

    def publish_package(
        self,
        package: ContentPackage,
        *,
        video_path: Path | None = None,
        thumbnail_path: Path | None = None,
        privacy_status: str | None = None,
    ) -> PublishResult:
        """Upload using metadata from a content package."""
        resolved_video = video_path
        if resolved_video is None:
            if not package.assets.video_path:
                raise PublisherError("ContentPackage has no assets.video_path")
            resolved_video = Path(package.assets.video_path)

        resolved_thumbnail = thumbnail_path
        if resolved_thumbnail is None and package.assets.thumbnail_path:
            resolved_thumbnail = Path(package.assets.thumbnail_path)

        overrides = package.platform_overrides.youtube
        title = str(overrides.get("title") or package.content_plan.seo.title)
        description = str(
            overrides.get("description") or package.content_plan.seo.description
        )
        tags_raw = overrides.get("tags") or package.content_plan.seo.tags
        tags = [str(tag) for tag in tags_raw] if tags_raw else None
        category = overrides.get("category") or package.content_plan.seo.category

        return self.publish(
            video_path=resolved_video,
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=resolved_thumbnail,
            category=str(category) if category else None,
            privacy_status=privacy_status,
        )
