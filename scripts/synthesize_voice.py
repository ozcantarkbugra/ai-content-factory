"""Synthesize Turkish narration with edge-tts (Step 5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.agent import AgentPipelineError, ContentAgentPipeline  # noqa: E402
from core.env import load_dotenv  # noqa: E402
from core.tts import NarrationSynthesizer, TtsError  # noqa: E402
from core.schemas import ContentPlan  # noqa: E402


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Synthesize narration audio with edge-tts")
    parser.add_argument("--topic", help="Run agents first, then synthesize full_narration")
    parser.add_argument("--plan", help="Path to content plan JSON (skips agents)")
    parser.add_argument(
        "--text",
        help="Synthesize this text directly (quick test, skips agents)",
    )
    parser.add_argument(
        "--output",
        help="Output MP3 path (default: assets/voice.mp3)",
    )
    parser.add_argument(
        "--voice",
        help="Override edge-tts voice (default from config/channel.yaml)",
    )
    args = parser.parse_args()

    synthesizer = NarrationSynthesizer()

    try:
        if args.text:
            result = synthesizer.synthesize(
                args.text,
                output_path=args.output,
                voice=args.voice,
            )
        elif args.plan:
            plan = ContentPlan.from_dict(
                json.loads(Path(args.plan).read_text(encoding="utf-8"))
            )
            result = synthesizer.synthesize_content_plan(plan, output_path=args.output)
        elif args.topic:
            pipeline_result = ContentAgentPipeline().run_content_pipeline(
                manual_topic=args.topic
            )
            result = synthesizer.synthesize_content_plan(
                pipeline_result.content_plan,
                output_path=args.output,
            )
        else:
            result = synthesizer.synthesize(
                "Osmanlı ordusu, düşmanı şaşırtmak için kullandığı bu taktikle "
                "tarihe adını yazdı. Peki bu strateji neydi?",
                output_path=args.output,
                voice=args.voice,
            )
    except AgentPipelineError as exc:
        print(f"FAILED agents: {exc}")
        return 1
    except TtsError as exc:
        print(f"TTS FAILED: {exc}")
        return 1

    payload = {
        "voice_path": str(result.voice_path),
        "duration_sec": result.duration_sec,
        "voice": result.voice,
        "char_count": result.char_count,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
