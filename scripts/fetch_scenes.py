"""Download scene images for a content plan (Step 4)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import AgentPipelineError, ContentAgentPipeline  # noqa: E402
from core.env import load_dotenv, require_env  # noqa: E402
from core.images import ImageFetchError, PollinationsClient, SceneAssetFetcher  # noqa: E402
from core.schemas import ContentPlan  # noqa: E402


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Fetch scene visuals (Pexels + Pollinations)")
    parser.add_argument("--topic", help="Run agents first, then fetch visuals for this topic")
    parser.add_argument("--plan", help="Path to content plan JSON (skips agents)")
    parser.add_argument(
        "--pollinations-only",
        action="store_true",
        help="Test Pollinations with a single AI prompt (no Pexels key required)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for downloaded scene files (default: assets/scenes)",
    )
    args = parser.parse_args()

    if args.pollinations_only:
        client = PollinationsClient()
        out = Path(args.output_dir or ROOT / "assets" / "scenes" / "pollinations_test.jpg")
        path = client.download_image(
            "Ottoman fortress cinematic aerial view, golden hour, dramatic clouds, vertical 9:16",
            out,
            aspect_ratio="9:16",
            seed=42,
        )
        print(json.dumps({"ok": True, "path": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if args.plan:
        plan_path = Path(args.plan)
        plan = ContentPlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
    elif args.topic:
        try:
            result = ContentAgentPipeline().run_content_pipeline(manual_topic=args.topic)
        except AgentPipelineError as exc:
            print(f"FAILED agents: {exc}")
            return 1
        plan = result.content_plan
    else:
        print("Provide --topic, --plan, or --pollinations-only")
        return 1

    try:
        if not args.pollinations_only:
            require_env("PEXELS_API_KEY")
        fetcher = SceneAssetFetcher()
        assets = fetcher.fetch_scenes(plan, work_dir=args.output_dir)
    except EnvironmentError as exc:
        print(f"CONFIG: {exc}")
        return 1
    except ImageFetchError as exc:
        print(f"FETCH FAILED: {exc}")
        return 1

    summary = {
        "work_dir": str(assets.work_dir),
        "scene_count": len(assets.downloaded),
        "files": [str(p) for p in assets.downloaded],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
