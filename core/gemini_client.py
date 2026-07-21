"""Google Gemini API client for agent prompts."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from core.env import get_env, require_env
from core.json_utils import extract_json_object


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        key = api_key or require_env("GEMINI_API_KEY")
        self.model_name = model_name or get_env("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.temperature = temperature
        self._client = genai.Client(api_key=key)

    def generate_text(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=self.temperature),
        )
        text = response.text
        if not text:
            raise RuntimeError("Gemini returned no text content")
        return text.strip()

    def generate_json(self, prompt: str) -> dict[str, Any]:
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                response_mime_type="application/json",
            ),
        )
        text = response.text
        if not text:
            raise RuntimeError("Gemini returned no JSON content")
        return extract_json_object(text)
