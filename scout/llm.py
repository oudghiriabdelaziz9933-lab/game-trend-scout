"""Thin wrapper around Google Gemini (free tier) that always returns parsed JSON."""
from __future__ import annotations

import json
import os
import re
import time

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class LLMError(RuntimeError):
    pass


def extract_json(text: str):
    """Parse JSON even if the model wrapped it in a markdown code fence."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model did not return valid JSON: {exc}") from exc


class GeminiClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise LLMError("No Gemini API key. Add GEMINI_API_KEY to your .env file or paste it in the sidebar.")
        from google import genai  # imported lazily so demo mode works without the SDK configured

        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate_json(self, prompt: str, system: str, temperature: float = 0.4, retries: int = 2):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
        )
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
                return extract_json(response.text)
            except LLMError as exc:  # malformed JSON: retry once more
                last_error = exc
            except Exception as exc:  # network, quota (free tier rate limits), etc.
                last_error = exc
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"Gemini call failed: {last_error}")
