"""Render 9:16 Shorts from scene images, voiceover, and subtitles via FFmpeg."""

from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config
from core.media_probe import (
    FFmpegNotFoundError,
    escape_filter_path,
    probe_media_duration,
    require_ffmpeg,
)
from core.schemas import ContentPlan, Scene


class RenderError(RuntimeError):
    """Raised when video rendering fails."""


@dataclass
class RenderResult:
    video_path: Path
    duration_sec: float
    width: int
    height: int
    subtitle_path: Path | None


def _resolution(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 1080, 1920
    if aspect_ratio == "16:9":
        return 1920, 1080
    return 1080, 1080


def _format_srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _scene_weights(scenes: list[Scene]) -> list[float]:
    return [float(max(len(scene.narration.strip()), 1)) for scene in scenes]


def _allocate_durations(scenes: list[Scene], total_duration: float) -> list[float]:
    weights = _scene_weights(scenes)
    weight_sum = sum(weights)
    return [total_duration * weight / weight_sum for weight in weights]


def build_srt(content_plan: ContentPlan, durations: list[float]) -> str:
    lines: list[str] = []
    cursor = 0.0
    for index, (scene, duration) in enumerate(zip(content_plan.scenes, durations), start=1):
        start = cursor
        end = cursor + duration
        text = (scene.on_screen_text or scene.narration).strip()
        wrapped = "\n".join(textwrap.wrap(text, width=32)) if text else scene.narration.strip()
        lines.append(str(index))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(wrapped)
        lines.append("")
        cursor = end
    return "\n".join(lines).strip() + "\n"


class ShortsRenderer:
    """Build a vertical Short from scene stills and narration audio."""

    def __init__(
        self,
        config: ChannelConfig | None = None,
        *,
        fps: int = 30,
        crf: int = 23,
    ) -> None:
        self.config = config or load_channel_config()
        self.fps = fps
        self.crf = crf

    def render(
        self,
        content_plan: ContentPlan,
        voice_path: Path | str,
        output_path: Path | str | None = None,
        *,
        work_dir: Path | str | None = None,
        burn_subtitles: bool = True,
    ) -> RenderResult:
        ffmpeg = require_ffmpeg()
        voice = Path(voice_path)
        if not voice.is_file():
            raise RenderError(f"Voice file not found: {voice}")

        scenes = content_plan.scenes
        if not scenes:
            raise RenderError("Content plan has no scenes")

        for scene in scenes:
            if not scene.asset_path or not Path(scene.asset_path).is_file():
                raise RenderError(f"Scene {scene.id} is missing a downloaded image asset")

        width, height = _resolution(content_plan.aspect_ratio)
        audio_duration = probe_media_duration(voice)
        durations = _allocate_durations(scenes, audio_duration)

        base_work = Path(work_dir) if work_dir else PROJECT_ROOT / "assets" / "render"
        base_work.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        for scene, duration in zip(scenes, durations):
            clip_path = base_work / f"clip_{scene.id:02d}.mp4"
            self._render_scene_clip(
                ffmpeg=ffmpeg,
                image_path=Path(scene.asset_path),
                duration=duration,
                output_path=clip_path,
                width=width,
                height=height,
            )
            clip_paths.append(clip_path)

        concat_path = base_work / "concat.txt"
        concat_lines = [f"file '{path.resolve().as_posix()}'" for path in clip_paths]
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        merged_path = base_work / "merged_silent.mp4"
        self._concat_clips(ffmpeg, concat_path, merged_path)

        subtitle_path: Path | None = None
        if burn_subtitles:
            subtitle_path = base_work / "subtitles.srt"
            subtitle_path.write_text(build_srt(content_plan, durations), encoding="utf-8")

        target = Path(output_path) if output_path else PROJECT_ROOT / "output" / "short.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)

        self._mux_audio_and_subtitles(
            ffmpeg=ffmpeg,
            video_path=merged_path,
            voice_path=voice,
            subtitle_path=subtitle_path,
            output_path=target,
        )

        final_duration = probe_media_duration(target)
        return RenderResult(
            video_path=target.resolve(),
            duration_sec=final_duration,
            width=width,
            height=height,
            subtitle_path=subtitle_path,
        )

    def _render_scene_clip(
        self,
        *,
        ffmpeg: str,
        image_path: Path,
        duration: float,
        output_path: Path,
        width: int,
        height: int,
    ) -> None:
        frames = max(int(round(duration * self.fps)), 1)
        scale_w = width * 4
        scale_h = height * 4
        zoom_filter = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
            f"zoompan=z='min(zoom+0.0010,1.30)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={self.fps},format=yuv420p"
        )
        command = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            zoom_filter,
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(self.crf),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        self._run(command, action=f"render scene clip {output_path.name}")

    def _concat_clips(self, ffmpeg: str, concat_file: Path, output_path: Path) -> None:
        command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ]
        self._run(command, action="concatenate scene clips")

    def _mux_audio_and_subtitles(
        self,
        *,
        ffmpeg: str,
        video_path: Path,
        voice_path: Path,
        subtitle_path: Path | None,
        output_path: Path,
    ) -> None:
        if subtitle_path and subtitle_path.is_file():
            subtitle_ref = escape_filter_path(subtitle_path)
            style = (
                "FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
                "Alignment=2,MarginV=120"
            )
            video_filter = f"subtitles={subtitle_ref}:force_style='{style}'"
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(voice_path),
                "-vf",
                video_filter,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(self.crf),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]
        else:
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(voice_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(output_path),
            ]
        self._run(command, action="mux audio and subtitles")

    @staticmethod
    def _run(command: list[str], *, action: str) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise RenderError(f"Failed to {action}: {stderr[:800]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"Timed out while trying to {action}") from exc
