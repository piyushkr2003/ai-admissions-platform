"""Deterministic mock provider used for tests/CI and as the default -
guarantees the agent never depends on a paid external call
(docs/tasks/006 section 66, "Mocking Strategy")."""
from __future__ import annotations

from app.agent.providers.base import LLMMessage, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(content=last_user, model="mock-echo")


def get_llm_provider() -> LLMProvider:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.agent_llm_provider == "mock":
        return MockLLMProvider()
    raise ValueError(
        f"Unsupported AGENT_LLM_PROVIDER '{settings.agent_llm_provider}'. "
        "Implement an LLMProvider subclass and register it here to add a new provider."
    )
