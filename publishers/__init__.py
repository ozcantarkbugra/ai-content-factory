"""Platform upload adapters — YouTube, TikTok, Instagram (planned)."""

from publishers.base import BasePublisher, PublishResult, PublisherError
from publishers.youtube import YouTubePublisher

__all__ = [
    "BasePublisher",
    "PublishResult",
    "PublisherError",
    "YouTubePublisher",
]
