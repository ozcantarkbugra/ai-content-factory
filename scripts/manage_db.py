"""Inspect and manage SQLite topic/run history (Step 8)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import load_channel_config  # noqa: E402
from core.db import ContentFactoryDB, DEFAULT_DB_PATH  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Manage AI Content Factory SQLite data")
    parser.add_argument("--db", help=f"Database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--list-topics", action="store_true", help="List used topics")
    parser.add_argument("--list-runs", action="store_true", help="List production runs")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to show")
    args = parser.parse_args()

    config = load_channel_config()
    db = ContentFactoryDB(args.db)

    if not args.list_topics and not args.list_runs:
        args.list_topics = True
        args.list_runs = True

    payload: dict[str, object] = {
        "db_path": str(db.db_path.resolve()),
        "niche": config.channel.niche,
    }

    if args.list_topics:
        payload["used_topics"] = db.get_used_topics(config.channel.niche, limit=args.limit)

    if args.list_runs:
        payload["production_runs"] = [
            {
                "id": run.id,
                "topic": run.topic,
                "status": run.status,
                "seo_title": run.seo_title,
                "review_overall": run.review_overall,
                "attempts": run.attempts,
                "created_at": run.created_at,
            }
            for run in db.list_production_runs(config.channel.niche, limit=args.limit)
        ]

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
