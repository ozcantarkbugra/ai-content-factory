"""Fetch scene visuals from Pexels (stock) and Pollinations (AI)."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config
from core.env import require_env
from core.schemas import ContentPlan, Scene, VisualType


class ImageFetchError(RuntimeError):
    """Raised when a scene visual cannot be downloaded."""


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Content-Factory/1.0",
    "Accept": "*/*",
}


def _merge_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(DEFAULT_HEADERS)
    if extra:
        merged.update(extra)
    return merged


@dataclass
class SceneAssetsResult:
    work_dir: Path
    content_plan: ContentPlan
    downloaded: list[Path]


def _http_get_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise ImageFetchError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ImageFetchError(f"Network error for {url}: {exc}") from exc


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    raw = _http_get_bytes(url, headers=headers, timeout=timeout)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ImageFetchError("Invalid JSON response from remote API") from exc
    if not isinstance(data, dict):
        raise ImageFetchError("Expected JSON object from remote API")
    return data


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _aspect_to_pollinations_size(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 768, 1344
    if aspect_ratio == "16:9":
        return 1344, 768
    return 1024, 1024


class PexelsClient:
    """Download portrait stock photos from Pexels."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or require_env("PEXELS_API_KEY")

    def search_photo_url(self, query: str, *, orientation: str = "portrait") -> str:
        params = urllib.parse.urlencode(
            {"query": query, "orientation": orientation, "per_page": 15, "page": 1}
        )
        url = f"https://api.pexels.com/v1/search?{params}"
        data = _http_get_json(url, headers=_merge_headers({"Authorization": self.api_key}))
        photos = data.get("photos") or []
        if not photos:
            raise ImageFetchError(f"Pexels returned no photos for query: {query}")
        choice = random.choice(photos[:5])
        src = choice.get("src") or {}
        for key in ("portrait", "large2x", "large", "medium", "original"):
            if src.get(key):
                return str(src[key])
        raise ImageFetchError(f"Pexels photo has no usable src for query: {query}")

    def download_photo(self, query: str, output_path: Path) -> Path:
        image_url = self.search_photo_url(query)
        image_bytes = _http_get_bytes(image_url, headers=DEFAULT_HEADERS, timeout=90)
        suffix = output_path.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            output_path = output_path.with_suffix(".jpg")
        return _write_bytes(output_path, image_bytes)


class PollinationsClient:
    """Download AI-generated images via Pollinations public endpoint."""

    def build_url(self, prompt: str, *, width: int, height: int, seed: int) -> str:
        encoded_prompt = urllib.parse.quote(prompt, safe="")
        params = urllib.parse.urlencode(
            {
                "width": width,
                "height": height,
                "seed": seed,
                "nologo": "true",
                "enhance": "true",
            }
        )
        return f"https://image.pollinations.ai/prompt/{encoded_prompt}?{params}"

    def download_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        aspect_ratio: str = "9:16",
        seed: int | None = None,
        retries: int = 2,
    ) -> Path:
        width, height = _aspect_to_pollinations_size(aspect_ratio)
        seed_value = seed if seed is not None else random.randint(1, 999_999)
        url = self.build_url(prompt, width=width, height=height, seed=seed_value)
        headers = _merge_headers({"Accept": "image/*"})

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                image_bytes = _http_get_bytes(url, headers=headers, timeout=120)
                if len(image_bytes) < 1000:
                    raise ImageFetchError("Pollinations returned an unexpectedly small image")
                if output_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    output_path = output_path.with_suffix(".jpg")
                return _write_bytes(output_path, image_bytes)
            except ImageFetchError as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
        raise ImageFetchError(f"Pollinations failed after {retries + 1} attempt(s): {last_error}")


class SceneAssetFetcher:
    """Download all scene assets for an approved content plan."""

    def __init__(
        self,
        config: ChannelConfig | None = None,
        pexels: PexelsClient | None = None,
        pollinations: PollinationsClient | None = None,
    ) -> None:
        self.config = config or load_channel_config()
        self._pexels = pexels
        self._pollinations = pollinations or PollinationsClient()

    @property
    def pexels(self) -> PexelsClient:
        if self._pexels is None:
            self._pexels = PexelsClient()
        return self._pexels

    @property
    def pollinations(self) -> PollinationsClient:
        return self._pollinations

    def fetch_scenes(
        self,
        content_plan: ContentPlan,
        work_dir: Path | str | None = None,
    ) -> SceneAssetsResult:
        base_dir = Path(work_dir) if work_dir else PROJECT_ROOT / "assets" / "scenes"
        base_dir.mkdir(parents=True, exist_ok=True)

        updated_scenes: list[Scene] = []
        downloaded: list[Path] = []

        for scene in content_plan.scenes:
            filename = f"scene_{scene.id:02d}.jpg"
            output_path = base_dir / filename

            if scene.visual_type == VisualType.STOCK:
                assert scene.stock_keyword
                path = self.pexels.download_photo(scene.stock_keyword, output_path)
            else:
                assert scene.visual_prompt
                path = self.pollinations.download_image(
                    scene.visual_prompt,
                    output_path,
                    aspect_ratio=content_plan.aspect_ratio,
                    seed=scene.id * 1000,
                )

            updated = Scene(
                id=scene.id,
                start_sec=scene.start_sec,
                end_sec=scene.end_sec,
                narration=scene.narration,
                visual_type=scene.visual_type,
                stock_keyword=scene.stock_keyword,
                visual_prompt=scene.visual_prompt,
                on_screen_text=scene.on_screen_text,
                asset_path=str(path.resolve()),
            )
            updated_scenes.append(updated)
            downloaded.append(path)

        updated_plan = ContentPlan(
            topic=content_plan.topic,
            format=content_plan.format,
            aspect_ratio=content_plan.aspect_ratio,
            target_duration_sec=content_plan.target_duration_sec,
            quality_score=content_plan.quality_score,
            hook=content_plan.hook,
            full_narration=content_plan.full_narration,
            scenes=updated_scenes,
            cta=content_plan.cta,
            music_mood=content_plan.music_mood,
            thumbnail=content_plan.thumbnail,
            seo=content_plan.seo,
            compliance=content_plan.compliance,
        )

        return SceneAssetsResult(work_dir=base_dir, content_plan=updated_plan, downloaded=downloaded)
