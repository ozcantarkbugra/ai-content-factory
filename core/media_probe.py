"""FFmpeg helpers shared across render and TTS modules."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from core.env import get_env


class FFmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg/ffprobe is not available on PATH."""


def _winget_ffmpeg_bin(name: str) -> str | None:
    """Locate ffmpeg/ffprobe installed by winget when PATH was not refreshed."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages.is_dir():
        return None
    matches = sorted(packages.glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"))
    if not matches:
        return None
    return str(matches[-1])


def _resolve_binary(name: str, env_var: str) -> str | None:
    configured = get_env(env_var)
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate.resolve())
        raise FFmpegNotFoundError(f"{env_var} points to a missing file: {configured}")

    found = shutil.which(name)
    if found:
        return found

    winget_path = _winget_ffmpeg_bin(name)
    if winget_path:
        return winget_path

    return None


def require_ffmpeg() -> str:
    path = _resolve_binary("ffmpeg", "FFMPEG_PATH")
    if not path:
        raise FFmpegNotFoundError(
            "ffmpeg not found. Install FFmpeg, restart the terminal, or set FFMPEG_PATH in .env.\n"
            "Windows: winget install Gyan.FFmpeg  OR  https://www.gyan.dev/ffmpeg/builds/"
        )
    return path


def require_ffprobe() -> str:
    configured = get_env("FFPROBE_PATH")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate.resolve())
        raise FFmpegNotFoundError(f"FFPROBE_PATH points to a missing file: {configured}")

    found = shutil.which("ffprobe")
    if found:
        return found

    ffmpeg_path = _resolve_binary("ffmpeg", "FFMPEG_PATH")
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe.exe")
        if sibling.is_file():
            return str(sibling.resolve())

    winget_path = _winget_ffmpeg_bin("ffprobe")
    if winget_path:
        return winget_path

    raise FFmpegNotFoundError(
        "ffprobe not found. Install FFmpeg, restart the terminal, or set FFPROBE_PATH in .env."
    )


def probe_media_duration(path: Path) -> float:
    ffprobe = require_ffprobe()
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return round(float(result.stdout.strip()), 3)


def escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg filter arguments on Windows."""
    resolved = str(path.resolve()).replace("\\", "/")
    if ":" in resolved:
        resolved = resolved.replace(":", "\\:", 1)
    return f"'{resolved}'"
