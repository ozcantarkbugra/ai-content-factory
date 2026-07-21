"""Parse JSON from LLM responses that may include markdown fences or extra text."""

from __future__ import annotations

import json
import re
from typing import Any

from core.schemas import SchemaError

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise SchemaError("LLM returned empty response")

    cleaned = text.strip()

    fence_match = _FENCE_PATTERN.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise SchemaError("LLM response does not contain a JSON object") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise SchemaError(f"Failed to parse JSON from LLM response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise SchemaError("LLM response JSON must be an object")
    return parsed
