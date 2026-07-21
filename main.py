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


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main() -> int:
    load_dotenv()
    _configure_stdout()

    parser = argparse.ArgumentParser(
        description="Run the full AI Content Factory pipeline (topic → YouTube)",
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
        "--no-notify",
        action="store_true",
        help="Skip Telegram notification even when configured",
    )
    parser.add_argument(
        "--output-root",
        help="Output directory root (default: output/)",
    )
    args = parser.parse_args()

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

    if result.publish_result:
        payload["youtube"] = {
            "video_id": result.publish_result.remote_id,
            "url": result.publish_result.url,
            "privacy_status": result.publish_result.privacy_status,
            "thumbnail_applied": result.publish_result.thumbnail_applied,
        }
        if result.publish_result.thumbnail_warning:
            payload["youtube"]["thumbnail_warning"] = result.publish_result.thumbnail_warning

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
