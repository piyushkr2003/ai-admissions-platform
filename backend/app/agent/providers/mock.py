"""Deterministic mock provider used for tests/CI and as the default -
guarantees the agent never depends on a paid external call
(docs/tasks/006 section 66, "Mocking Strategy")."""
from __future__ import annotations

from app.agent.providers.base import LLMMessage, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(content=last_user, model="mock-echo")
