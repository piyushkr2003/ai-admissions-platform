"""LLM provider abstraction (docs/tasks/006 section 46).

The default orchestration pipeline is fully deterministic (see
app/agent/orchestrator.py) and does not call an LLM at all - intent
routing, tool selection, and response composition for this well-defined
domain are all cases where "a deterministic rule is safer and
sufficient" (Task 006 section 13), and it keeps the agent's core logic
testable with zero external dependencies or cost.

This interface exists so a real LLM can be layered in later (e.g. for
paraphrasing template output, or handling genuinely open-ended
questions) without redesigning the orchestrator: swap
get_llm_provider()'s return value, nothing else changes. No API key is
required for the platform to function today.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        raise NotImplementedError


class LLMProviderError(Exception):
    """Raised for a runtime provider failure (timeout, HTTP error,
    malformed response) as opposed to a configuration problem (missing
    credential, which the factory raises as ResourceUnavailableError
    before any call is attempted). Callers that treat the LLM as an
    optional enhancement - e.g. AgentOrchestrator's open-ended reply -
    catch this and fall back to a deterministic response rather than
    failing the turn."""
