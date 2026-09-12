"""Task 016 - bounded LLM assist in AgentOrchestrator.

Proves the design boundary required by Task 016 section 3: the LLM is
never the source of truth for admissions facts (grounded intents like
fees/eligibility never reach it, regardless of provider configuration),
it is only ever consulted for genuinely unmatched input, defaults to the
existing static template when the provider is "mock" (zero behavior
change for every other test in this suite), and any LLM failure falls
back to the static template rather than breaking the turn.
"""
from __future__ import annotations

from sqlalchemy import select

import app.agent.orchestrator as orchestrator_module
from app.agent import prompts
from app.agent.orchestrator import AgentOrchestrator
from app.agent.providers.base import LLMMessage, LLMProvider, LLMProviderError, LLMResponse
from app.colleges.context import get_college_context
from app.core.config import get_settings
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.conversations import Conversation

NOVA_SLUG = "nova-institute-of-technology"


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _new_conversation(db, college_id) -> Conversation:
    conv = Conversation(college_id=college_id, channel="web_voice", session_id="t", status="active", state={})
    db.add(conv)
    db.flush()
    return conv


def _orchestrator(db, college_id) -> AgentOrchestrator:
    context = get_college_context(db, college_id)
    return AgentOrchestrator(db, context)


class _SpyLLMProvider(LLMProvider):
    """Always returns a fixed, obviously-non-template string so a test
    can tell whether the LLM path was actually used - and counts calls
    so a test can assert it was never invoked for grounded intents."""

    def __init__(self, reply: str = "Totally different LLM-generated phrasing."):
        self.reply = reply
        self.calls: list[list[LLMMessage]] = []

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self.reply, model="fake-llm")


class _FailingLLMProvider(LLMProvider):
    def __init__(self, exc: Exception):
        self._exc = exc

    def generate(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        raise self._exc


def _use_fake_llm(monkeypatch, provider: LLMProvider, *, provider_name: str = "fake-vendor"):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", provider_name)
    monkeypatch.setattr(orchestrator_module, "get_llm_provider", lambda: provider)


def test_unknown_intent_uses_static_fallback_by_default(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    result = orch.handle_message(conversation, "asdkjqhwe nonsense gibberish")

    assert result.response_text == prompts.unknown_fallback("en", "Admissions Assistant")


def test_unknown_intent_uses_llm_when_a_real_provider_is_configured(db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    fake = _SpyLLMProvider("Sure, I can help with that - are you asking about a course, fees, or an appointment?")
    _use_fake_llm(monkeypatch, fake)

    result = orch.handle_message(conversation, "asdkjqhwe nonsense gibberish")

    assert result.response_text == fake.reply
    assert len(fake.calls) == 1
    assert fake.calls[0][0].role == "system"
    assert fake.calls[0][1].content == "asdkjqhwe nonsense gibberish"


def test_llm_is_never_invoked_for_a_grounded_fee_question(db, monkeypatch):
    """The core safety guarantee: even with a real LLM provider
    configured, a factual/tool-backed intent never touches it."""
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    fake = _SpyLLMProvider("I would make up a fee if you let me.")
    _use_fake_llm(monkeypatch, fake)

    result = orch.handle_message(conversation, "What is the fee for B.Tech CSE?")

    assert "get_fee_structure" in result.tools_used
    assert fake.reply not in result.response_text
    assert fake.calls == []  # the LLM was never called at all


def test_out_of_scope_response_stays_fully_static_even_with_llm_configured(db, monkeypatch):
    """Safety refusals (out-of-scope, cross-tenant, injection) are never
    routed through the LLM - only the generic "no matching intent"
    fallback is."""
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    fake = _SpyLLMProvider("I would love to help with hostel check-in!")
    _use_fake_llm(monkeypatch, fake)

    result = orch.handle_message(conversation, "Can you help me with hostel check-in?")

    assert result.response_text == prompts.out_of_scope("en")
    assert fake.calls == []


def test_llm_provider_failure_falls_back_to_static_response(db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    _use_fake_llm(monkeypatch, _FailingLLMProvider(LLMProviderError("Anthropic API timed out.")))

    result = orch.handle_message(conversation, "asdkjqhwe nonsense gibberish")

    assert result.response_text == prompts.unknown_fallback("en", "Admissions Assistant")


def test_llm_unexpected_exception_falls_back_gracefully_without_crashing(db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    conversation = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    _use_fake_llm(monkeypatch, _FailingLLMProvider(RuntimeError("boom")))

    result = orch.handle_message(conversation, "asdkjqhwe nonsense gibberish")

    assert result.response_text == prompts.unknown_fallback("en", "Admissions Assistant")
