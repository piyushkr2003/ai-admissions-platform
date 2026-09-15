"""Production LLM provider adapter for Groq (fast cloud inference).

Calls Groq's OpenAI-compatible Chat Completions API
(https://console.groq.com/docs/api-reference#chat-create) directly with
the standard library's `urllib` rather than adding the `groq` SDK as a
dependency - same "one bounded, low-volume JSON POST" reasoning as
`app/agent/providers/anthropic.py`/`gemini.py`. `GROQ_API_KEY` is sent
only in the `Authorization: Bearer` request header and is never logged.

Selected via the existing `AGENT_LLM_PROVIDER=groq` setting
(app/agent/providers/factory.py) - no second, competing provider-name
setting is introduced.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.agent.providers.base import LLMMessage, LLMProvider, LLMProviderError, LLMResponse

logger = logging.getLogger("app.agent.llm")

# AgentOrchestrator._open_ended_reply (the only caller of any LLM
# provider - never the source of admissions facts, see docs/voice.md
# section 73.3) is used identically for text chat and voice. Groq is
# fast enough that no separate voice-timeout override is needed (unlike
# Ollama's CPU-bound generation - see app/agent/providers/factory.py's
# voice_llm_timeout), but a voice reply is still spoken aloud, so this
# caps generation length to keep replies short and conversational rather
# than a long written-style paragraph.
_DEFAULT_MAX_TOKENS = 150


class GroqLLMProvider(LLMProvider):
    name = "groq"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float):
        if not api_key:
            raise ValueError("GroqLLMProvider requires an api_key.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        chat_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role in ("system", "user", "assistant")
        ]
        if not any(m["role"] in ("user", "assistant") for m in chat_messages):
            raise LLMProviderError("At least one user/assistant message is required.")

        payload = {
            "model": self._model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": _DEFAULT_MAX_TOKENS,
        }
        request = urllib.request.Request(
            f"{self._base_url}/openai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self._api_key}",
                "user-agent": "ai-admissions-platform/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("llm.groq_http_error status=%s", exc.code)
            raise LLMProviderError(f"Groq API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("llm.groq_unreachable")
            raise LLMProviderError("Groq API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("llm.groq_malformed_response")
            raise LLMProviderError("Groq API returned a malformed response.") from exc

        try:
            choices = body.get("choices") or []
            text = (choices[0].get("message") or {}).get("content", "").strip()
            model_used = body.get("model", self._model)
        except (AttributeError, TypeError, IndexError) as exc:
            logger.warning("llm.groq_malformed_response")
            raise LLMProviderError("Groq API returned a malformed response.") from exc

        if not text:
            raise LLMProviderError("Groq API returned no text content.")
        return LLMResponse(content=text, model=model_used)
