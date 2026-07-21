"""Generate YouTube thumbnails from scene art and overlay text."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config
from core.images import ImageFetchError, PollinationsClient
from core.schemas import ContentPlan, ThumbnailPlan


class ThumbnailError(RuntimeError):
    """Raised when thumbnail generation fails."""


@dataclass
class ThumbnailResult:
    thumbnail_path: Path
    width: int
    height: int
    overlay_text: str
    source: str


def _youtube_thumbnail_size() -> tuple[int, int]:
    return 1280, 720


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)


def _draw_bottom_gradient(image: Image.Image, *, strength: float = 0.72) -> None:
    width, height = image.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    gradient_height = int(height * 0.45)
    top = height - gradient_height
    for y in range(gradient_height):
        alpha = int(255 * strength * (y / max(gradient_height - 1, 1)))
        draw.line([(0, top + y), (width, top + y)], fill=(0, 0, 0, alpha))
    image.alpha_composite(overlay)


def _wrap_overlay(text: str, *, max_chars: int = 14, max_lines: int = 3) -> list[str]:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    lines = textwrap.wrap(cleaned, width=max_chars)
    return lines[:max_lines]


class ThumbnailGenerator:
    """Build a 1280x720 YouTube thumbnail with bold overlay text."""

    def __init__(
        self,
        config: ChannelConfig | None = None,
        pollinations: PollinationsClient | None = None,
    ) -> None:
        self.config = config or load_channel_config()
        self.pollinations = pollinations or PollinationsClient()

    def generate(
        self,
        content_plan: ContentPlan,
        output_path: Path | str | None = None,
        *,
        base_image_path: Path | str | None = None,
        work_dir: Path | str | None = None,
    ) -> ThumbnailResult:
        width, height = _youtube_thumbnail_size()
        target = Path(output_path) if output_path else PROJECT_ROOT / "output" / "thumbnail.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)

        overlay_text = content_plan.thumbnail.overlay_text.strip() or content_plan.seo.title
        base_path, source = self._resolve_base_image(
            content_plan,
            base_image_path=base_image_path,
            work_dir=work_dir,
        )

        image = _fit_cover(Image.open(base_path), width, height).convert("RGBA")
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = ImageEnhance.Color(image).enhance(1.12)
        _draw_bottom_gradient(image)

        draw = ImageDraw.Draw(image)
        lines = _wrap_overlay(overlay_text)
        if not lines:
            lines = _wrap_overlay(content_plan.seo.title)

        font_size = 88 if len(lines) <= 2 else 64
        font = _load_font(font_size)
        line_spacing = 12
        line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
        total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
        y = height - int(height * 0.12) - total_text_height

        for line, line_height in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)]:
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
            y += line_height + line_spacing

        image.convert("RGB").save(target, format="JPEG", quality=92, optimize=True)
        return ThumbnailResult(
            thumbnail_path=target.resolve(),
            width=width,
            height=height,
            overlay_text=overlay_text,
            source=source,
        )

    def _resolve_base_image(
        self,
        content_plan: ContentPlan,
        *,
        base_image_path: Path | str | None,
        work_dir: Path | str | None,
    ) -> tuple[Path, str]:
        if base_image_path:
            path = Path(base_image_path)
            if not path.is_file():
                raise ThumbnailError(f"Base image not found: {path}")
            return path.resolve(), "manual"

        for scene in content_plan.scenes:
            if scene.asset_path and Path(scene.asset_path).is_file():
                return Path(scene.asset_path).resolve(), f"scene_{scene.id:02d}"

        work = Path(work_dir) if work_dir else PROJECT_ROOT / "assets" / "thumbnail"
        work.mkdir(parents=True, exist_ok=True)
        generated = work / "thumbnail_base.jpg"
        try:
            self.pollinations.download_image(
                content_plan.thumbnail.prompt,
                generated,
                aspect_ratio="16:9",
                seed=999,
            )
        except ImageFetchError as exc:
            raise ThumbnailError(f"Failed to generate thumbnail base image: {exc}") from exc
        return generated.resolve(), "pollinations"

    @staticmethod
    def from_plan_fields(
        thumbnail: ThumbnailPlan,
        seo_title: str,
        scenes: list,
        **plan_kwargs,
    ) -> ContentPlan:
        """Helper for lightweight CLI tests with minimal plan data."""
        from core.schemas import ComplianceInfo, SeoPackage

        return ContentPlan(
            topic=plan_kwargs.get("topic", seo_title),
            format=plan_kwargs.get("format", "shorts"),
            aspect_ratio=plan_kwargs.get("aspect_ratio", "9:16"),
            target_duration_sec=plan_kwargs.get("target_duration_sec", 55),
            quality_score=8,
            hook=plan_kwargs.get("hook", seo_title),
            full_narration=plan_kwargs.get("full_narration", seo_title),
            scenes=scenes,
            cta=plan_kwargs.get("cta", ""),
            music_mood=plan_kwargs.get("music_mood", "epic"),
            thumbnail=thumbnail,
            seo=SeoPackage(
                title=seo_title,
                description=plan_kwargs.get("description", seo_title),
                tags=plan_kwargs.get("tags", [seo_title]),
                hashtags=plan_kwargs.get("hashtags", ["#shorts"]),
                category=plan_kwargs.get("category", "Education"),
            ),
            compliance=ComplianceInfo(altered_content_label=False, risk_notes="yok"),
        )
