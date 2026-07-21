"""Instagram Reels Graph API adapter (Step 16 — stub)."""

from __future__ import annotations

from pathlib import Path

from publishers.base import BasePublisher, PublishResult, PublisherError

_NOT_READY = (
    "Instagram Reels publisher is not implemented yet (Step 16). "
    "Set publish.platforms to [youtube] in config/channel.yaml for now."
)


class InstagramPublisher(BasePublisher):
    platform = "instagram"

    def authenticate(self, *, interactive: bool = True) -> None:
        raise PublisherError(_NOT_READY)

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
        raise PublisherError(_NOT_READY)
