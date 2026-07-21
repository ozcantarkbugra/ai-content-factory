"""Render a 9:16 Short from scenes + voice (Step 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import AgentPipelineError, ContentAgentPipeline  # noqa: E402
from core.env import load_dotenv, require_env  # noqa: E402
from core.images import ImageFetchError, SceneAssetFetcher  # noqa: E402
from core.media_probe import FFmpegNotFoundError  # noqa: E402
from core.render import RenderError, ShortsRenderer  # noqa: E402
from core.schemas import ContentPlan, Scene  # noqa: E402
from core.tts import NarrationSynthesizer, TtsError  # noqa: E402


def _attach_existing_scene_assets(plan: ContentPlan, scenes_dir: Path) -> ContentPlan:
    updated_scenes: list[Scene] = []
    for scene in plan.scenes:
        candidate = scenes_dir / f"scene_{scene.id:02d}.jpg"
        asset_path = str(candidate.resolve()) if candidate.is_file() else scene.asset_path
        updated_scenes.append(
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
        scenes=updated_scenes,
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

    parser = argparse.ArgumentParser(description="Render 9:16 Short with FFmpeg")
    parser.add_argument("--topic", help="Run agents to build the content plan")
    parser.add_argument("--plan", help="Existing content plan JSON path")
    parser.add_argument("--voice", help="Voice MP3 path (default: assets/voice.mp3)")
    parser.add_argument("--scenes-dir", help="Scene images directory (default: assets/scenes)")
    parser.add_argument(
        "--reuse-assets",
        action="store_true",
        help="Use existing scene images/voice instead of re-downloading or re-synthesizing",
    )
    parser.add_argument("--output", help="Output MP4 path (default: output/short.mp4)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run agents, fetch scenes, synthesize voice, then render",
    )
    args = parser.parse_args()

    scenes_dir = Path(args.scenes_dir or ROOT / "assets" / "scenes")
    voice_path = Path(args.voice or ROOT / "assets" / "voice.mp3")

    try:
        if args.plan:
            plan = ContentPlan.from_dict(json.loads(Path(args.plan).read_text(encoding="utf-8")))
        elif args.topic:
            result = ContentAgentPipeline().run_content_pipeline(manual_topic=args.topic)
            plan = result.content_plan
        else:
            print("Provide --topic, --plan, or --full with --topic")
            return 1

        if args.full and args.topic:
            require_env("PEXELS_API_KEY")
            plan = SceneAssetFetcher().fetch_scenes(plan, work_dir=scenes_dir).content_plan
            voice = NarrationSynthesizer().synthesize_content_plan(plan, output_path=voice_path)
            voice_path = voice.voice_path
        elif args.reuse_assets:
            plan = _attach_existing_scene_assets(plan, scenes_dir)
            if not voice_path.is_file():
                voice = NarrationSynthesizer().synthesize_content_plan(plan, output_path=voice_path)
                voice_path = voice.voice_path
        elif args.topic and not args.reuse_assets:
            require_env("PEXELS_API_KEY")
            plan = SceneAssetFetcher().fetch_scenes(plan, work_dir=scenes_dir).content_plan
            voice = NarrationSynthesizer().synthesize_content_plan(plan, output_path=voice_path)
            voice_path = voice.voice_path

        render_result = ShortsRenderer().render(
            plan,
            voice_path,
            output_path=args.output,
            burn_subtitles=True,
        )
    except AgentPipelineError as exc:
        print(f"FAILED agents: {exc}")
        return 1
    except EnvironmentError as exc:
        print(f"CONFIG: {exc}")
        return 1
    except (ImageFetchError, TtsError, RenderError, FFmpegNotFoundError) as exc:
        print(f"RENDER FAILED: {exc}")
        return 1

    payload = {
        "video_path": str(render_result.video_path),
        "duration_sec": render_result.duration_sec,
        "resolution": f"{render_result.width}x{render_result.height}",
        "subtitle_path": str(render_result.subtitle_path) if render_result.subtitle_path else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
