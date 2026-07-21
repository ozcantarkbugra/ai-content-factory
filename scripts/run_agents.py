"""Run the Topic → Master → Reviewer agent pipeline (Step 3 smoke test)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import AgentPipelineError, ContentAgentPipeline  # noqa: E402
from core.config import build_agent_prompt, load_channel_config  # noqa: E402
from core.env import load_dotenv  # noqa: E402


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Run AI Content Factory agent pipeline")
    parser.add_argument("--topic", help="Skip topic agent and use this manual topic")
    parser.add_argument("--angle", help="Optional angle for manual topic")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompts only; do not call Gemini (requires --topic)",
    )
    args = parser.parse_args()

    if args.dry_run:
        if not args.topic:
            print("--dry-run requires --topic")
            return 1
        config = load_channel_config()
        print("=== MASTER PROMPT PREVIEW ===")
        print(
            build_agent_prompt(
                "master_agent.txt",
                config,
                topic=args.topic,
                angle=args.angle or "Manuel test",
            )[:2000]
        )
        print("\n(dry-run: Gemini not called)")
        return 0

    pipeline = ContentAgentPipeline()

    try:
        result = pipeline.run_content_pipeline(
            manual_topic=args.topic,
            manual_angle=args.angle,
        )
    except AgentPipelineError as exc:
        print(f"FAILED: {exc}")
        return 1
    except EnvironmentError as exc:
        print(f"CONFIG: {exc}")
        return 1

    payload = {
        "approved": result.approved,
        "attempts": result.attempts,
        "topic": result.topic.to_dict(),
        "seo_title": result.content_plan.seo.title,
        "scene_count": len(result.content_plan.scenes),
        "review_summary": result.review.summary,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
