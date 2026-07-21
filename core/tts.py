"""Text-to-speech narration via edge-tts (Microsoft, free)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config
from core.schemas import ContentPlan


class TtsError(RuntimeError):
    """Raised when narration synthesis fails."""


@dataclass
class VoiceResult:
    voice_path: Path
    duration_sec: float | None
    voice: str
    char_count: int


def _probe_duration_ffprobe(audio_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        return round(float(result.stdout.strip()), 2)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


async def _synthesize_async(text: str, voice: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(str(output_path))


class NarrationSynthesizer:
    """Generate voiceover MP3 from approved narration text."""

    def __init__(self, config: ChannelConfig | None = None) -> None:
        self.config = config or load_channel_config()

    @property
    def voice(self) -> str:
        if self.config.voice.provider != "edge-tts":
            raise TtsError(f"Unsupported TTS provider: {self.config.voice.provider}")
        return self.config.voice.voice

    def synthesize(
        self,
        text: str,
        output_path: Path | str | None = None,
        *,
        voice: str | None = None,
    ) -> VoiceResult:
        cleaned = text.strip()
        if not cleaned:
            raise TtsError("Narration text is empty")

        selected_voice = voice or self.voice
        target = Path(output_path) if output_path else PROJECT_ROOT / "assets" / "voice.mp3"
        if target.suffix.lower() != ".mp3":
            target = target.with_suffix(".mp3")

        try:
            asyncio.run(_synthesize_async(cleaned, selected_voice, target))
        except edge_tts.exceptions.NoAudioReceived as exc:
            raise TtsError(f"edge-tts returned no audio for voice '{selected_voice}'") from exc
        except OSError as exc:
            raise TtsError(f"Failed to write voice file: {exc}") from exc

        if not target.is_file() or target.stat().st_size < 500:
            raise TtsError(f"Voice file was not created or is too small: {target}")

        return VoiceResult(
            voice_path=target.resolve(),
            duration_sec=_probe_duration_ffprobe(target),
            voice=selected_voice,
            char_count=len(cleaned),
        )

    def synthesize_content_plan(
        self,
        content_plan: ContentPlan,
        output_path: Path | str | None = None,
    ) -> VoiceResult:
        return self.synthesize(content_plan.full_narration, output_path=output_path)
