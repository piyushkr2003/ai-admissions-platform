"""Production LLM provider adapter (Task 016).

Calls the Anthropic Messages API (https://docs.anthropic.com/en/api/messages)
directly with the standard library's `urllib` rather than adding the
`anthropic` SDK as a dependency: this is one bounded, low-volume JSON
POST (see app/agent/orchestrator.py's `_open_ended_reply` for the single
call site), not a place that needs streaming, retries, or the SDK's
broader surface - consistent with this codebase's preference for
stdlib over a new dependency when it already does the job (see
app/voice/providers/livekit.py's identical reasoning for PyJWT).

LLM_API_KEY is sent only in a request header to api.anthropic.com and is
never logged - see test_llm_provider.py's log-content assertions.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.agent.providers.base import LLMMessage, LLMProvider, LLMProviderError, LLMResponse

logger = logging.getLogger("app.agent.llm")

_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 300


class AnthropicLLMProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float):
        if not api_key:
            raise ValueError("AnthropicLLMProvider requires an api_key.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        system_text = "\n".join(m.content for m in messages if m.role == "system") or None
        chat_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role in ("user", "assistant")
        ]
        if not chat_messages:
            raise LLMProviderError("At least one user/assistant message is required.")

        payload: dict = {
            "model": self._model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_text:
            payload["system"] = system_text

        request = urllib.request.Request(
            f"{self._base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("llm.anthropic_http_error status=%s", exc.code)
            raise LLMProviderError(f"Anthropic API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("llm.anthropic_unreachable")
            raise LLMProviderError("Anthropic API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("llm.anthropic_malformed_response")
            raise LLMProviderError("Anthropic API returned a malformed response.") from exc

        content_blocks = body.get("content") or []
        text = "".join(
            block.get("text", "") for block in content_blocks if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not text:
            raise LLMProviderError("Anthropic API returned no text content.")
        return LLMResponse(content=text, model=body.get("model", self._model))
