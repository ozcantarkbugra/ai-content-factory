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
        """Upload using metadata from a content package — override per platform."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement publish_package()"
        )
