"""AI Content Factory — end-to-end Shorts pipeline (Step 10)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env import load_dotenv  # noqa: E402
from core.pipeline import ContentFactoryPipeline, PipelineError  # noqa: E402
from core.telegram import TelegramError, TelegramNotifier  # noqa: E402
from publishers.registry import SUPPORTED_PLATFORMS, normalize_platforms  # noqa: E402


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _parse_platforms(value: str) -> list[str]:
    return normalize_platforms([part.strip() for part in value.split(",") if part.strip()])


def main() -> int:
    load_dotenv()
    _configure_stdout()

    supported = ", ".join(SUPPORTED_PLATFORMS)
    parser = argparse.ArgumentParser(
        description="Run the full AI Content Factory pipeline (topic → publish)",
    )
    parser.add_argument("--topic", help="Use this topic instead of the Topic Agent")
    parser.add_argument("--angle", help="Optional angle when --topic is set")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Stop after writing output/<package_id>/content_package.json",
    )
    parser.add_argument(
        "--skip-thumbnail-upload",
        action="store_true",
        help="Upload video without custom thumbnail API call",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write run history to SQLite",
    )
    parser.add_argument(
        "--privacy",
        choices=["public", "unlisted", "private"],
        help="YouTube privacy (default: channel.yaml or unlisted)",
    )
    parser.add_argument(
        "--platforms",
        help=f"Comma-separated publish targets (default: config/channel.yaml). Supported: {supported}",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip Telegram notification even when configured",
    )
    parser.add_argument(
        "--output-root",
        help="Output directory root (default: output/)",
    )
    args = parser.parse_args()

    platforms = _parse_platforms(args.platforms) if args.platforms else None

    pipeline = ContentFactoryPipeline()
    notifier = TelegramNotifier()
    notify = notifier.enabled and not args.no_notify

    try:
        result = pipeline.run(
            manual_topic=args.topic,
            manual_angle=args.angle,
            upload=not args.no_upload,
            skip_thumbnail_upload=args.skip_thumbnail_upload,
            privacy_status=args.privacy,
            platforms=platforms,
            persist=not args.no_persist,
            output_root=args.output_root,
        )
    except EnvironmentError as exc:
        print(f"CONFIG: {exc}")
        if notify:
            _safe_notify_failure(notifier, str(exc), args.topic)
        return 1
    except PipelineError as exc:
        print(f"PIPELINE FAILED: {exc}")
        if notify:
            _safe_notify_failure(notifier, str(exc), args.topic)
        return 1

    if notify:
        try:
            notifier.notify_success(result)
        except TelegramError as exc:
            print(f"TELEGRAM WARNING: {exc}")

    payload: dict = {
        "status": result.package.status,
        "package_id": result.package.package_id,
        "package_dir": str(result.package_dir),
        "seo_title": result.package.content_plan.seo.title,
        "topic": result.package.topic.topic,
        "video_path": result.package.assets.video_path,
        "thumbnail_path": result.package.assets.thumbnail_path,
        "content_package": str(result.package_dir / "content_package.json"),
    }

    if result.publish_results:
        payload["publish_results"] = [
            {
                "platform": item.platform,
                "remote_id": item.remote_id,
                "url": item.url,
                "privacy_status": item.privacy_status,
                "thumbnail_applied": item.thumbnail_applied,
                "thumbnail_warning": item.thumbnail_warning,
            }
            for item in result.publish_results
        ]

    youtube = result.publish_result
    if youtube and youtube.platform == "youtube":
        payload["youtube"] = {
            "video_id": youtube.remote_id,
            "url": youtube.url,
            "privacy_status": youtube.privacy_status,
            "thumbnail_applied": youtube.thumbnail_applied,
        }
        if youtube.thumbnail_warning:
            payload["youtube"]["thumbnail_warning"] = youtube.thumbnail_warning

    if result.publish_errors:
        payload["publish_errors"] = [
            {"platform": platform, "error": message}
            for platform, message in result.publish_errors
        ]

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _safe_notify_failure(
    notifier: TelegramNotifier,
    error: str,
    topic: str | None,
) -> None:
    try:
        notifier.notify_failure(error, topic=topic)
    except TelegramError as exc:
        print(f"TELEGRAM WARNING: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
