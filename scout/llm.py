"""Thin wrapper around Google Gemini (free tier) that always returns parsed JSON."""
from __future__ import annotations

import json
import os
import re
import time

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


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


def pick_flash_model(names: list[str]) -> str | None:
    """Choose the newest general 'flash' model from a list of model names."""
    candidates = []
    for name in names:
        short = name.split("/")[-1]
        if "flash" not in short or any(x in short for x in ("lite", "image", "tts", "audio", "live", "exp", "preview")):
            continue
        numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", short)]
        candidates.append((numbers[0] if numbers else 0.0, short))
    return max(candidates)[1] if candidates else None


def _is_model_missing(exc: Exception) -> bool:
    text = str(exc)
    return "404" in text or "NOT_FOUND" in text or "no longer available" in text


class GeminiClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise LLMError("No Gemini API key. Add GEMINI_API_KEY to your .env file or paste it in the sidebar.")
        from google import genai  # imported lazily so demo mode works without the SDK configured

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def _fallback_model(self) -> str | None:
        """Model names change often: ask the API which flash models this key can use."""
        try:
            names = [m.name for m in self.client.models.list()
                     if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"])]
        except Exception:
            return None
        choice = pick_flash_model(names)
        return choice if choice and choice != self.model else None

    def generate_json(self, prompt: str, system: str, temperature: float = 0.4, retries: int = 2):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
        )
        last_error: Exception | None = None
        switched = False
        for attempt in range(retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
                return extract_json(response.text)
            except LLMError as exc:  # malformed JSON: retry
                last_error = exc
            except Exception as exc:
                last_error = exc
                if _is_model_missing(exc) and not switched:
                    fallback = self._fallback_model()
                    if fallback:
                        self.model, switched = fallback, True
                        continue
                    break  # retrying an unknown model is pointless
                time.sleep(2 * (attempt + 1))  # network or free-tier rate limit
        raise LLMError(f"Gemini call failed ({self.model}): {last_error}")