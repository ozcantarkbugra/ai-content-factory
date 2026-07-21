"""Load environment variables from .env at project root."""

from __future__ import annotations

import os
from pathlib import Path

from core.config import PROJECT_ROOT


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and set {name}."
        )
    return value


def get_env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()
