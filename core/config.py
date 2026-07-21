"""Load channel configuration from YAML — single source of truth for niche and format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANNEL_CONFIG = PROJECT_ROOT / "config" / "channel.yaml"


@dataclass(frozen=True)
class ChannelIdentity:
    name: str
    niche: str
    niche_label: str
    language: str
    tone: str
    target_audience: str


@dataclass(frozen=True)
class FormatSettings:
    type: str
    aspect_ratio: str
    target_duration_sec: int
    scene_duration_sec: int


@dataclass(frozen=True)
class VoiceSettings:
    provider: str
    voice: str


@dataclass(frozen=True)
class VisualSettings:
    stock_provider: str
    ai_provider: str
    default_visual_type: str


@dataclass(frozen=True)
class ProductionSettings:
    reviewer_min_score: float
    reviewer_max_retries: int
    altered_content_default: bool


@dataclass(frozen=True)
class PublishSettings:
    platforms: tuple[str, ...]
    fail_fast: bool


@dataclass(frozen=True)
class ChannelConfig:
    channel: ChannelIdentity
    format: FormatSettings
    voice: VoiceSettings
    visuals: VisualSettings
    production: ProductionSettings
    publish: PublishSettings
    config_path: Path

    def prompt_variables(
        self,
        *,
        used_topics: list[str] | None = None,
        trend_hints: str = "",
        topic: str = "",
        angle: str = "",
        content_json: str = "",
    ) -> dict[str, str]:
        """Placeholder values for prompts/*.txt — change niche in YAML only."""
        used = used_topics or []
        used_display = ", ".join(used) if used else "(henüz konu üretilmedi)"
        return {
            "NICHE": self.channel.niche,
            "NICHE_LABEL": self.channel.niche_label,
            "TONE": self.channel.tone,
            "TARGET_AUDIENCE": self.channel.target_audience,
            "FORMAT": self.format.type,
            "TARGET_DURATION_SEC": str(self.format.target_duration_sec),
            "SCENE_DURATION_SEC": str(self.format.scene_duration_sec),
            "ASPECT_RATIO": self.format.aspect_ratio,
            "REVIEWER_MIN_SCORE": str(self.production.reviewer_min_score),
            "USED_TOPICS": used_display,
            "TREND_HINTS": trend_hints or "(yok)",
            "TOPIC": topic,
            "ANGLE": angle,
            "CONTENT_JSON": content_json,
        }


def _require(data: dict[str, Any], key: str, section: str) -> Any:
    if key not in data:
        raise ValueError(f"Missing '{key}' in config section '{section}'")
    return data[key]


def load_channel_config(path: Path | str | None = None) -> ChannelConfig:
    config_path = Path(path) if path else DEFAULT_CHANNEL_CONFIG
    if not config_path.is_file():
        raise FileNotFoundError(f"Channel config not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid channel config (expected mapping): {config_path}")

    channel = _require(raw, "channel", "root")
    fmt = _require(raw, "format", "root")
    voice = _require(raw, "voice", "root")
    visuals = _require(raw, "visuals", "root")
    production = _require(raw, "production", "root")
    publish = raw.get("publish") or {}

    platforms_raw = publish.get("platforms") or ["youtube"]
    if not isinstance(platforms_raw, list):
        raise ValueError("publish.platforms must be a list in channel config")
    platforms = tuple(str(item).strip().lower() for item in platforms_raw if str(item).strip())
    if not platforms:
        platforms = ("youtube",)

    return ChannelConfig(
        channel=ChannelIdentity(
            name=_require(channel, "name", "channel"),
            niche=_require(channel, "niche", "channel"),
            niche_label=_require(channel, "niche_label", "channel"),
            language=_require(channel, "language", "channel"),
            tone=_require(channel, "tone", "channel"),
            target_audience=_require(channel, "target_audience", "channel"),
        ),
        format=FormatSettings(
            type=_require(fmt, "type", "format"),
            aspect_ratio=_require(fmt, "aspect_ratio", "format"),
            target_duration_sec=int(_require(fmt, "target_duration_sec", "format")),
            scene_duration_sec=int(_require(fmt, "scene_duration_sec", "format")),
        ),
        voice=VoiceSettings(
            provider=_require(voice, "provider", "voice"),
            voice=_require(voice, "voice", "voice"),
        ),
        visuals=VisualSettings(
            stock_provider=_require(visuals, "stock_provider", "visuals"),
            ai_provider=_require(visuals, "ai_provider", "visuals"),
            default_visual_type=_require(visuals, "default_visual_type", "visuals"),
        ),
        production=ProductionSettings(
            reviewer_min_score=float(_require(production, "reviewer_min_score", "production")),
            reviewer_max_retries=int(_require(production, "reviewer_max_retries", "production")),
            altered_content_default=bool(_require(production, "altered_content_default", "production")),
        ),
        publish=PublishSettings(
            platforms=platforms,
            fail_fast=bool(publish.get("fail_fast", True)),
        ),
        config_path=config_path.resolve(),
    )


def load_prompt_template(name: str, prompts_dir: Path | None = None) -> str:
    directory = prompts_dir or (PROJECT_ROOT / "prompts")
    path = directory / name
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, variables: dict[str, str]) -> str:
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", value)
    return result


def build_agent_prompt(
    template_name: str,
    config: ChannelConfig,
    *,
    used_topics: list[str] | None = None,
    trend_hints: str = "",
    topic: str = "",
    angle: str = "",
    content_json: str = "",
) -> str:
    """Compose a full agent prompt with global system block and config placeholders."""
    variables = config.prompt_variables(
        used_topics=used_topics,
        trend_hints=trend_hints,
        topic=topic,
        angle=angle,
        content_json=content_json,
    )
    global_system = render_prompt(load_prompt_template("global_system.txt"), variables)
    template = load_prompt_template(template_name).replace("{GLOBAL_SYSTEM}", global_system)
    return render_prompt(template, variables)
