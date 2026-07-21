"""Platform registry and multi-publisher orchestration (Step 14)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config import ChannelConfig
from core.schemas import ContentPackage
from publishers.base import BasePublisher, PublishResult, PublisherError
from publishers.instagram import InstagramPublisher
from publishers.tiktok import TikTokPublisher
from publishers.youtube import YouTubePublisher

SUPPORTED_PLATFORMS: tuple[str, ...] = ("youtube", "tiktok", "instagram")
IMPLEMENTED_PLATFORMS: frozenset[str] = frozenset({"youtube"})


@dataclass
class PublishBatchResult:
    results: list[PublishResult]
    errors: list[tuple[str, str]]

    @property
    def succeeded(self) -> bool:
        return bool(self.results)

    @property
    def failed_platforms(self) -> list[str]:
        return [platform for platform, _ in self.errors]


def normalize_platforms(names: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in names:
        platform = raw.strip().lower()
        if not platform:
            continue
        if platform not in SUPPORTED_PLATFORMS:
            supported = ", ".join(SUPPORTED_PLATFORMS)
            raise PublisherError(f"Unknown platform '{raw}'. Supported: {supported}")
        if platform in seen:
            continue
        seen.add(platform)
        cleaned.append(platform)
    if not cleaned:
        raise PublisherError("At least one platform is required")
    return cleaned


def resolve_platforms(
    config: ChannelConfig,
    *,
    cli_platforms: list[str] | None = None,
) -> list[str]:
    if cli_platforms:
        return normalize_platforms(cli_platforms)
    return list(config.publish.platforms)


def create_publisher(platform: str, *, privacy_status: str | None = None) -> BasePublisher:
    if platform == "youtube":
        return YouTubePublisher(privacy_status=privacy_status or "unlisted")
    if platform == "tiktok":
        return TikTokPublisher()
    if platform == "instagram":
        return InstagramPublisher()
    raise PublisherError(f"Unknown platform: {platform}")


def publish_to_platforms(
    package: ContentPackage,
    platforms: list[str],
    *,
    video_path: Path,
    thumbnail_path: Path | None,
    skip_thumbnail_upload: bool,
    privacy_status: str | None,
    fail_fast: bool,
) -> PublishBatchResult:
    normalized = normalize_platforms(platforms)
    results: list[PublishResult] = []
    errors: list[tuple[str, str]] = []

    for platform in normalized:
        if platform not in IMPLEMENTED_PLATFORMS:
            message = (
                f"{platform} publisher is not implemented yet "
                f"(coming in Phase 2 — remove from platforms or wait for next step)."
            )
            errors.append((platform, message))
            if fail_fast:
                break
            continue

        publisher = create_publisher(platform, privacy_status=privacy_status)
        thumb_path = thumbnail_path
        if skip_thumbnail_upload or platform != "youtube":
            thumb_path = None

        try:
            publisher.authenticate()
            results.append(
                publisher.publish_package(
                    package,
                    video_path=video_path,
                    thumbnail_path=thumb_path,
                    privacy_status=privacy_status if platform == "youtube" else None,
                )
            )
        except PublisherError as exc:
            errors.append((platform, str(exc)))
            if fail_fast:
                break

    return PublishBatchResult(results=results, errors=errors)


def default_youtube_privacy(config: ChannelConfig) -> str:
    try:
        import yaml

        with config.config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        youtube = raw.get("youtube") or {}
        privacy = str(youtube.get("privacy_status", "")).strip().lower()
        if privacy in {"public", "unlisted", "private"}:
            return privacy
    except Exception:
        pass
    from core.env import get_env

    env_privacy = get_env("YOUTUBE_PRIVACY_STATUS", "unlisted").lower()
    return env_privacy if env_privacy in {"public", "unlisted", "private"} else "unlisted"
