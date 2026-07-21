"""Verify channel config loads and agent prompts render without placeholders left behind."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import build_agent_prompt, load_channel_config  # noqa: E402

UNRESOLVED = re.compile(r"\{[A-Z_]+\}")


def main() -> int:
    config = load_channel_config()
    print(f"Channel: {config.channel.name}")
    print(f"Niche:   {config.channel.niche_label} ({config.channel.niche})")
    print(f"Format:  {config.format.type} {config.format.aspect_ratio}")

    templates = [
        ("topic_agent.txt", {"used_topics": ["Örnek konu"]}),
        ("master_agent.txt", {"topic": "Test konusu", "angle": "Test açı"}),
        ("reviewer_agent.txt", {"content_json": "{}"}),
    ]

    for name, kwargs in templates:
        prompt = build_agent_prompt(name, config, **kwargs)
        unresolved = UNRESOLVED.findall(prompt)
        if unresolved:
            print(f"FAIL {name}: unresolved placeholders: {unresolved}")
            return 1
        print(f"OK   {name} ({len(prompt)} chars)")

    print("\nConfig verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
