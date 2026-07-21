"""Platform upload adapters — YouTube, TikTok, Instagram (planned)."""

from publishers.instagram import InstagramPublisher
from publishers.registry import (
    IMPLEMENTED_PLATFORMS,
    SUPPORTED_PLATFORMS,
    create_publisher,
    normalize_platforms,
    publish_to_platforms,
    resolve_platforms,
)
from publishers.tiktok import TikTokPublisher
from publishers.youtube import YouTubePublisher

__all__ = [
    "BasePublisher",
    "PublishResult",
    "PublisherError",
    "YouTubePublisher",
    "TikTokPublisher",
    "InstagramPublisher",
    "SUPPORTED_PLATFORMS",
    "IMPLEMENTED_PLATFORMS",
    "create_publisher",
    "normalize_platforms",
    "publish_to_platforms",
    "resolve_platforms",
]
