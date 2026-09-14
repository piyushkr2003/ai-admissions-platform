"""LLM provider selection (mirrors app/voice/providers/factory.py's
pattern exactly). Selecting a named provider that is missing its
required credential raises a clear ResourceUnavailableError instead of
silently falling back to the mock - the platform must never pretend an
LLM is configured when it isn't (Task 016).
"""
from __future__ import annotations

import contextvars

from app.agent.providers.base import LLMProvider
from app.agent.providers.mock import MockLLMProvider
from app.core.config import get_settings
from app.core.errors import ResourceUnavailableError

# Voice-specific Ollama timeout (latency audit, first optimization pass).
#
# get_llm_provider() is called from exactly one place -
# AgentOrchestrator._open_ended_reply() - which is shared, unmodified,
# by every channel (text chat and both voice paths) and has no notion of
# "which channel is this". Rather than threading a new parameter through
# AgentOrchestrator/VoiceSessionService to express "this call happens to
# be part of a voice turn", the voice layer marks that fact in a
# contextvar immediately around its own (otherwise unchanged) call into
# the orchestrator - see app/services/voice.py::_handle_final_transcript
# and its use of `voice_llm_timeout()` below. A text conversation never
# sets this, so get_llm_provider() falls through to
# settings.ollama_timeout_seconds exactly as before - zero behavior
# change for non-voice callers.
_voice_llm_timeout_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_voice_llm_timeout_active", default=False
)


class voice_llm_timeout:
    """Context manager: while active on the current task/thread, a
    `local`/Ollama LLM provider constructed by get_llm_provider() uses
    `settings.ollama_voice_timeout_seconds` instead of the general
    `settings.ollama_timeout_seconds`. No effect on any other provider
    (Anthropic/Gemini already use their own, already-fast cloud
    timeout - this addresses Ollama's specifically slow CPU generation)."""

    def __enter__(self) -> None:
        self._token = _voice_llm_timeout_active.set(True)

    def __exit__(self, *exc_info) -> None:
        _voice_llm_timeout_active.reset(self._token)


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    name = settings.agent_llm_provider.lower()
    if name == "mock":
        return MockLLMProvider()
    if name == "anthropic":
        if not settings.llm_api_key:
            raise ResourceUnavailableError("LLM provider 'anthropic' is selected but no LLM_API_KEY is configured.")
        from app.agent.providers.anthropic import AnthropicLLMProvider

        return AnthropicLLMProvider(
            api_key=settings.llm_api_key, model=settings.llm_model,
            base_url=settings.llm_api_base_url, timeout_seconds=settings.llm_timeout_seconds,
        )
    if name == "gemini":
        if not settings.google_api_key:
            raise ResourceUnavailableError("LLM provider 'gemini' is selected but no GOOGLE_API_KEY is configured.")
        from app.agent.providers.gemini import GeminiLLMProvider

        return GeminiLLMProvider(
            api_key=settings.google_api_key, model=settings.gemini_model,
            base_url=settings.gemini_api_base_url, timeout_seconds=settings.llm_timeout_seconds,
        )
    if name == "local":
        from app.agent.providers.local import OllamaLLMProvider

        timeout_seconds = (
            settings.ollama_voice_timeout_seconds if _voice_llm_timeout_active.get() else settings.ollama_timeout_seconds
        )
        return OllamaLLMProvider(
            base_url=settings.ollama_base_url, model=settings.ollama_model,
            timeout_seconds=timeout_seconds,
        )
    raise ResourceUnavailableError(f"LLM provider '{name}' has no adapter implemented yet.")
