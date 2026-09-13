"""Free local LLM provider adapter for Ollama (Task 023 - Local Free Demo Mode).

Calls a locally-running Ollama server (https://ollama.com) - no API key,
no per-request cost, no data leaving the developer's machine. Selected
via the existing `AGENT_LLM_PROVIDER=local` setting
(app/agent/providers/factory.py), mirroring `GeminiLLMProvider`'s and
`AnthropicLLMProvider`'s exact shape: implements the same `LLMProvider`
interface, so `AgentOrchestrator._open_ended_reply` - the *only* place
any LLM is ever consulted (never for admissions facts - see docs/voice.md
section 73.3) - requires no changes at all.

Uses `urllib.request` rather than an SDK, exactly like the other two real
adapters: this is one bounded local HTTP POST, not a place that needs a
client library's broader surface.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.agent.providers.base import LLMMessage, LLMProvider, LLMProviderError, LLMResponse

logger = logging.getLogger("app.agent.llm")


class OllamaLLMProvider(LLMProvider):
    name = "local"

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        ollama_messages = [{"role": m.role, "content": m.content} for m in messages if m.role in ("system", "user", "assistant")]
        if not any(m["role"] in ("user", "assistant") for m in ollama_messages):
            raise LLMProviderError("At least one user/assistant message is required.")

        payload = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        request = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("llm.ollama_http_error status=%s", exc.code)
            if exc.code == 404:
                raise LLMProviderError(
                    f"Ollama returned HTTP 404 - is the model '{self._model}' pulled? Run: ollama pull {self._model}"
                ) from exc
            raise LLMProviderError(f"Ollama returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("llm.ollama_unreachable")
            raise LLMProviderError(
                f"Ollama at {self._base_url} was unreachable or timed out - is `ollama serve` running?"
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("llm.ollama_malformed_response")
            raise LLMProviderError("Ollama returned a malformed response.") from exc

        try:
            text = (body.get("message") or {}).get("content", "").strip()
            model_used = body.get("model", self._model)
        except (AttributeError, TypeError) as exc:
            logger.warning("llm.ollama_malformed_response")
            raise LLMProviderError("Ollama returned a malformed response.") from exc

        if not text:
            raise LLMProviderError("Ollama returned no text content.")
        return LLMResponse(content=text, model=model_used)
