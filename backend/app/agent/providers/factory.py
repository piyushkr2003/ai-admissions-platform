"""LLM provider selection (mirrors app/voice/providers/factory.py's
pattern exactly). Selecting a named provider that is missing its
required credential raises a clear ResourceUnavailableError instead of
silently falling back to the mock - the platform must never pretend an
LLM is configured when it isn't (Task 016).
"""
from __future__ import annotations

from app.agent.providers.base import LLMProvider
from app.agent.providers.mock import MockLLMProvider
from app.core.config import get_settings
from app.core.errors import ResourceUnavailableError


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
    raise ResourceUnavailableError(f"LLM provider '{name}' has no adapter implemented yet.")
