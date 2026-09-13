"""Production LLM provider adapter for Google Gemini (Task 016 follow-up).

Calls the Gemini API's `generateContent` endpoint
(https://ai.google.dev/api/generate-content) directly with the standard
library's `urllib` rather than adding the `google-genai` SDK as a
dependency: this is one bounded, low-volume JSON POST (see
app/agent/orchestrator.py's `_open_ended_reply` for the single call
site), not a place that needs the SDK's broader surface - the same
reasoning app/agent/providers/anthropic.py already applies to the
Anthropic adapter.

GOOGLE_API_KEY is sent only in the `x-goog-api-key` request header to
generativelanguage.googleapis.com (never in the URL, so it can never end
up in a logged/cached request line) and is never logged - see
test_llm_provider_gemini.py's log-content assertions.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.agent.providers.base import LLMMessage, LLMProvider, LLMProviderError, LLMResponse

logger = logging.getLogger("app.agent.llm")

_DEFAULT_MAX_OUTPUT_TOKENS = 300


class GeminiLLMProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float):
        if not api_key:
            raise ValueError("GeminiLLMProvider requires an api_key.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        system_text = "\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        if not contents:
            raise LLMProviderError("At least one user/assistant message is required.")

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": _DEFAULT_MAX_OUTPUT_TOKENS,
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        request = urllib.request.Request(
            f"{self._base_url}/v1beta/models/{self._model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "x-goog-api-key": self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("llm.gemini_http_error status=%s", exc.code)
            raise LLMProviderError(f"Gemini API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("llm.gemini_unreachable")
            raise LLMProviderError("Gemini API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("llm.gemini_malformed_response")
            raise LLMProviderError("Gemini API returned a malformed response.") from exc

        try:
            candidates = body.get("candidates") or []
            text = ""
            if candidates:
                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(
                    part.get("text", "") for part in parts if isinstance(part, dict)
                ).strip()
            model_version = body.get("modelVersion", self._model)
        except (AttributeError, TypeError, IndexError) as exc:
            logger.warning("llm.gemini_malformed_response")
            raise LLMProviderError("Gemini API returned a malformed response.") from exc

        if not text:
            raise LLMProviderError("Gemini API returned no text content.")
        return LLMResponse(content=text, model=model_version)
