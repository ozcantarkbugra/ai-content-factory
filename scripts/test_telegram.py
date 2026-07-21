"""Send a test Telegram message (Step 12)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.env import load_dotenv, require_env  # noqa: E402
from core.telegram import TelegramError, TelegramNotifier  # noqa: E402


def main() -> int:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Test Telegram bot notification")
    parser.add_argument("--message", default="AI Content Factory — Telegram test OK")
    args = parser.parse_args()

    require_env("TELEGRAM_BOT_TOKEN")
    require_env("TELEGRAM_CHAT_ID")

    notifier = TelegramNotifier()
    try:
        notifier.send_message(args.message)
    except TelegramError as exc:
        print(f"TELEGRAM FAILED: {exc}")
        return 1

    print("Telegram message sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
