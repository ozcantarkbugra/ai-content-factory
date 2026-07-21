"""Generate a YouTube thumbnail (Step 7)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import AgentPipelineError, ContentAgentPipeline  # noqa: E402
from core.env import load_dotenv  # noqa: E402
from core.schemas import ContentPlan, ThumbnailPlan  # noqa: E402
from core.thumbnail import ThumbnailError, ThumbnailGenerator  # noqa: E402


def _attach_scene_assets(plan: ContentPlan, scenes_dir: Path) -> ContentPlan:
    from core.schemas import Scene

    updated = []
    for scene in plan.scenes:
        candidate = scenes_dir / f"scene_{scene.id:02d}.jpg"
        asset_path = str(candidate.resolve()) if candidate.is_file() else scene.asset_path
        updated.append(
            Scene(
                id=scene.id,
                start_sec=scene.start_sec,
                end_sec=scene.end_sec,
                narration=scene.narration,
                visual_type=scene.visual_type,
                stock_keyword=scene.stock_keyword,
                visual_prompt=scene.visual_prompt,
                on_screen_text=scene.on_screen_text,
                asset_path=asset_path,
            )
        )
    return ContentPlan(
        topic=plan.topic,
        format=plan.format,
        aspect_ratio=plan.aspect_ratio,
        target_duration_sec=plan.target_duration_sec,
        quality_score=plan.quality_score,
        hook=plan.hook,
        full_narration=plan.full_narration,
        scenes=updated,
        cta=plan.cta,
        music_mood=plan.music_mood,
        thumbnail=plan.thumbnail,
        seo=plan.seo,
        compliance=plan.compliance,
    )


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail")
    parser.add_argument("--topic", help="Run agents first, then build thumbnail")
    parser.add_argument("--plan", help="Existing content plan JSON")
    parser.add_argument("--base-image", help="Use this image as thumbnail background")
    parser.add_argument("--text", help="Overlay text override (quick test)")
    parser.add_argument("--title", help="SEO title for quick test")
    parser.add_argument(
        "--reuse-assets",
        action="store_true",
        help="Attach assets/scenes/scene_XX.jpg to the content plan",
    )
    parser.add_argument("--output", help="Output JPG path (default: output/thumbnail.jpg)")
    args = parser.parse_args()

    generator = ThumbnailGenerator()
    scenes_dir = ROOT / "assets" / "scenes"

    try:
        if args.plan:
            plan = ContentPlan.from_dict(json.loads(Path(args.plan).read_text(encoding="utf-8")))
        elif args.topic:
            plan = ContentAgentPipeline().run_content_pipeline(manual_topic=args.topic).content_plan
        elif args.base_image or args.text:
            overlay = args.text or "TARIH SHORTS"
            title = args.title or overlay
            plan = ThumbnailGenerator.from_plan_fields(
                ThumbnailPlan(concept=title, prompt=title, overlay_text=overlay),
                seo_title=title,
                scenes=[],
            )
        else:
            plan = ThumbnailGenerator.from_plan_fields(
                ThumbnailPlan(
                    concept="Osmanli savas taktiği",
                    prompt="Ottoman battle cinematic thumbnail 16:9",
                    overlay_text="GIZLI TAKTIK",
                ),
                seo_title="Osmanlı'nın Gizli Savaş Taktiği",
                scenes=[],
            )
            args.base_image = args.base_image or str(scenes_dir / "scene_01.jpg")

        if args.reuse_assets and plan.scenes:
            plan = _attach_scene_assets(plan, scenes_dir)

        if args.text:
            plan.thumbnail.overlay_text = args.text

        result = generator.generate(
            plan,
            output_path=args.output,
            base_image_path=args.base_image,
        )
    except AgentPipelineError as exc:
        print(f"FAILED agents: {exc}")
        return 1
    except ThumbnailError as exc:
        print(f"THUMBNAIL FAILED: {exc}")
        return 1

    payload = {
        "thumbnail_path": str(result.thumbnail_path),
        "resolution": f"{result.width}x{result.height}",
        "overlay_text": result.overlay_text,
        "source": result.source,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
