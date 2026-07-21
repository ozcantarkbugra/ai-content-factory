"""Upload a rendered Short to YouTube (Step 9)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import load_channel_config  # noqa: E402
from core.db import ContentFactoryDB  # noqa: E402
from core.env import get_env, load_dotenv  # noqa: E402
from core.schemas import ContentPackage  # noqa: E402
from publishers.base import PublisherError  # noqa: E402
from publishers.youtube import YouTubePublisher  # noqa: E402


def _resolve_output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_file():
        return candidate.resolve()
    rooted = (ROOT / candidate).resolve()
    if rooted.is_file():
        return rooted
    raise PublisherError(f"File not found: {value}")


def _load_package(path: str) -> ContentPackage:
    package_path = Path(path)
    if not package_path.is_file():
        package_path = ROOT / path
    if not package_path.is_file():
        raise PublisherError(f"Content package not found: {path}")
    return ContentPackage.from_dict(json.loads(package_path.read_text(encoding="utf-8")))


def _default_privacy() -> str:
    config = load_channel_config()
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
    env_privacy = get_env("YOUTUBE_PRIVACY_STATUS", "unlisted").lower()
    return env_privacy if env_privacy in {"public", "unlisted", "private"} else "unlisted"


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Upload video to YouTube via OAuth")
    parser.add_argument("--auth-only", action="store_true", help="Run OAuth and save token only")
    parser.add_argument("--package", help="content_package.json path")
    parser.add_argument("--video", help="Video file (default: output/short.mp4)")
    parser.add_argument("--thumbnail", help="Thumbnail JPG (default: output/thumbnail.jpg)")
    parser.add_argument("--title", help="Override title")
    parser.add_argument("--description", help="Override description")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument(
        "--privacy",
        choices=["public", "unlisted", "private"],
        help="Privacy status (default: channel.yaml or unlisted)",
    )
    parser.add_argument(
        "--skip-thumbnail",
        action="store_true",
        help="Upload video only (skip custom thumbnail API call)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files and metadata without uploading",
    )
    args = parser.parse_args()

    privacy = args.privacy or _default_privacy()
    publisher = YouTubePublisher(privacy_status=privacy)

    if args.auth_only:
        try:
            publisher.authenticate()
        except PublisherError as exc:
            print(f"AUTH FAILED: {exc}")
            return 1
        print(json.dumps({"status": "authenticated", "token_file": str(publisher.token_file)}, indent=2))
        return 0

    try:
        if args.package:
            package = _load_package(args.package)
            video_path = Path(args.video) if args.video else None
            thumbnail_path = Path(args.thumbnail) if args.thumbnail else None

            if args.dry_run:
                resolved_video = video_path or Path(package.assets.video_path or "output/short.mp4")
                resolved_thumb = thumbnail_path
                if resolved_thumb is None and package.assets.thumbnail_path:
                    resolved_thumb = Path(package.assets.thumbnail_path)
                payload = {
                    "dry_run": True,
                    "title": package.content_plan.seo.title,
                    "privacy_status": privacy,
                    "video_path": str(_resolve_output_path(str(resolved_video))),
                    "thumbnail_path": str(_resolve_output_path(str(resolved_thumb)))
                    if resolved_thumb
                    else None,
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            result = publisher.publish_package(
                package,
                video_path=video_path,
                thumbnail_path=None if args.skip_thumbnail else thumbnail_path,
                privacy_status=privacy,
            )
            topic = package.topic.topic
            seo_title = package.content_plan.seo.title
        else:
            video_arg = args.video or "output/short.mp4"
            video_path = _resolve_output_path(video_arg)
            thumbnail_path = _resolve_output_path(args.thumbnail) if args.thumbnail else None
            if thumbnail_path is None and not args.skip_thumbnail:
                default_thumb = ROOT / "output" / "thumbnail.jpg"
                if default_thumb.is_file():
                    thumbnail_path = default_thumb

            title = args.title or "AI Content Factory Short"
            description = args.description or title
            tags = [tag.strip() for tag in args.tags.split(",")] if args.tags else ["tarih", "shorts"]

            if args.dry_run:
                payload = {
                    "dry_run": True,
                    "title": title,
                    "privacy_status": privacy,
                    "video_path": str(video_path),
                    "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            publisher.authenticate()
            result = publisher.publish(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                thumbnail_path=None if args.skip_thumbnail else thumbnail_path,
                category="Education",
                privacy_status=privacy,
            )
            topic = title
            seo_title = title

        if not args.dry_run:
            config = load_channel_config()
            ContentFactoryDB().log_production_run(
                niche=config.channel.niche,
                topic=topic,
                status="published",
                seo_title=seo_title,
                video_path=str(args.video or "output/short.mp4"),
                thumbnail_path=str(args.thumbnail or "output/thumbnail.jpg"),
                metadata={
                    "platform": result.platform,
                    "remote_id": result.remote_id,
                    "url": result.url,
                    "privacy_status": result.privacy_status,
                    "thumbnail_applied": result.thumbnail_applied,
                    "thumbnail_warning": result.thumbnail_warning,
                },
            )

    except PublisherError as exc:
        print(f"UPLOAD FAILED: {exc}")
        return 1

    payload = {
        "platform": result.platform,
        "video_id": result.remote_id,
        "url": result.url,
        "title": result.title,
        "privacy_status": result.privacy_status,
        "thumbnail_applied": result.thumbnail_applied,
    }
    if result.thumbnail_warning:
        payload["thumbnail_warning"] = result.thumbnail_warning

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
