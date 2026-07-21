"""Core production pipeline — config, schemas, and shared utilities."""

from core.config import (
    ChannelConfig,
    build_agent_prompt,
    load_channel_config,
    load_prompt_template,
    render_prompt,
)
from core.schemas import (
    ContentPackage,
    ContentPlan,
    ReviewDecision,
    ReviewResult,
    SchemaError,
    TopicSelection,
)

__all__ = [
    "ChannelConfig",
    "ContentPackage",
    "ContentPlan",
    "ReviewDecision",
    "ReviewResult",
    "SchemaError",
    "TopicSelection",
    "build_agent_prompt",
    "load_channel_config",
    "load_prompt_template",
    "render_prompt",
]
