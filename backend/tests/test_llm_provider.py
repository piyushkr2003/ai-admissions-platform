"""Task 016 - LLM provider abstraction.

Covers provider selection/fail-closed behavior, request construction,
response parsing, timeout/error handling, and no-secret-logging for the
production (Anthropic) adapter. No real network call is made anywhere in
this file - `urllib.request.urlopen` is monkeypatched throughout.
"""
from __future__ import annotations

import json
import logging
import urllib.error

import pytest

from app.agent.providers.anthropic import AnthropicLLMProvider
from app.agent.providers.base import LLMMessage, LLMProviderError
from app.agent.providers.factory import get_llm_provider, voice_llm_timeout
from app.agent.providers.gemini import GeminiLLMProvider
from app.agent.providers.groq import GroqLLMProvider
from app.agent.providers.local import OllamaLLMProvider
from app.agent.providers.mock import MockLLMProvider
from app.core.config import get_settings
from app.core.errors import ResourceUnavailableError


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_mock_llm_provider_is_a_deterministic_echo():
    provider = MockLLMProvider()
    result = provider.generate([LLMMessage(role="system", content="x"), LLMMessage(role="user", content="hello")])
    assert result.content == "hello"
    assert result.model == "mock-echo"


def test_factory_returns_mock_by_default():
    assert isinstance(get_llm_provider(), MockLLMProvider)


def test_factory_fails_closed_when_anthropic_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_llm_provider()


def test_factory_returns_anthropic_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_api_key", "sk-test-key")
    provider = get_llm_provider()
    assert isinstance(provider, AnthropicLLMProvider)


def test_factory_rejects_unknown_provider_name(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "some-future-vendor")
    with pytest.raises(ResourceUnavailableError):
        get_llm_provider()


def test_anthropic_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        AnthropicLLMProvider(api_key="", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)


def test_anthropic_provider_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse({"content": [{"type": "text", "text": "Sure, happy to help!"}], "model": "claude-sonnet-4-5-20250929"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = AnthropicLLMProvider(api_key="sk-secret-value", model="claude-sonnet-4-5-20250929", base_url="https://api.anthropic.com", timeout_seconds=5)
    result = provider.generate(
        [LLMMessage(role="system", content="You are helpful."), LLMMessage(role="user", content="Hi there")],
        temperature=0.3,
    )

    assert result.content == "Sure, happy to help!"
    assert result.model == "claude-sonnet-4-5-20250929"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-secret-value"
    assert captured["headers"]["anthropic-version"]
    assert captured["body"]["system"] == "You are helpful."
    assert captured["body"]["messages"] == [{"role": "user", "content": "Hi there"}]
    assert captured["body"]["temperature"] == 0.3
    assert captured["timeout"] == 5


def test_anthropic_provider_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicLLMProvider(api_key="sk-x", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_anthropic_provider_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicLLMProvider(api_key="sk-x", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_anthropic_provider_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = AnthropicLLMProvider(api_key="sk-x", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_anthropic_provider_raises_on_empty_text_content(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _FakeHTTPResponse({"content": [], "model": "m"}))
    provider = AnthropicLLMProvider(api_key="sk-x", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_factory_fails_closed_when_gemini_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_llm_provider()


def test_factory_returns_gemini_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    provider = get_llm_provider()
    assert isinstance(provider, GeminiLLMProvider)


def test_gemini_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GeminiLLMProvider(api_key="", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)


def test_gemini_provider_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse(
            {
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "Sure, happy to help!"}]}, "finishReason": "STOP"}
                ],
                "modelVersion": "gemini-2.5-flash",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = GeminiLLMProvider(
        api_key="goog-secret-value", model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com", timeout_seconds=5,
    )
    result = provider.generate(
        [LLMMessage(role="system", content="You are helpful."), LLMMessage(role="user", content="Hi there")],
        temperature=0.3,
    )

    assert result.content == "Sure, happy to help!"
    assert result.model == "gemini-2.5-flash"
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "goog-secret-value"
    assert "goog-secret-value" not in captured["url"]
    assert captured["body"]["systemInstruction"] == {"parts": [{"text": "You are helpful."}]}
    assert captured["body"]["contents"] == [{"role": "user", "parts": [{"text": "Hi there"}]}]
    assert captured["body"]["generationConfig"]["temperature"] == 0.3
    assert captured["timeout"] == 5


def test_gemini_provider_maps_assistant_role_to_model_role(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            {"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "modelVersion": "gemini-2.5-flash"}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiLLMProvider(api_key="k", model="gemini-2.5-flash", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    provider.generate(
        [
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello!"),
            LLMMessage(role="user", content="How are you?"),
        ]
    )
    assert captured["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "Hi"}]},
        {"role": "model", "parts": [{"text": "Hello!"}]},
        {"role": "user", "parts": [{"text": "How are you?"}]},
    ]


def test_gemini_provider_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiLLMProvider(api_key="k", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_gemini_provider_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiLLMProvider(api_key="k", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_gemini_provider_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = GeminiLLMProvider(api_key="k", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_gemini_provider_raises_on_empty_candidates(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=None: _FakeHTTPResponse({"candidates": [], "modelVersion": "m"})
    )
    provider = GeminiLLMProvider(api_key="k", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_gemini_provider_raises_on_safety_blocked_candidate_with_no_parts(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeHTTPResponse(
            {"candidates": [{"finishReason": "SAFETY"}], "modelVersion": "m"}
        ),
    )
    provider = GeminiLLMProvider(api_key="k", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_gemini_provider_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiLLMProvider(api_key="goog-super-secret", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5)
    with caplog.at_level(logging.DEBUG, logger="app.agent.llm"):
        with pytest.raises(LLMProviderError):
            provider.generate([LLMMessage(role="user", content="hi")])
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "goog-super-secret" not in logged_text


def test_factory_returns_ollama_provider_with_the_general_timeout_by_default(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "local")
    monkeypatch.setattr(settings, "ollama_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "ollama_voice_timeout_seconds", 6.0)

    provider = get_llm_provider()

    assert isinstance(provider, OllamaLLMProvider)
    assert provider._timeout_seconds == 30.0


def test_factory_uses_the_shorter_voice_timeout_inside_voice_llm_timeout(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "local")
    monkeypatch.setattr(settings, "ollama_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "ollama_voice_timeout_seconds", 6.0)

    with voice_llm_timeout():
        voice_provider = get_llm_provider()

    text_provider = get_llm_provider()

    assert voice_provider._timeout_seconds == 6.0
    assert text_provider._timeout_seconds == 30.0


def test_voice_llm_timeout_reverts_even_if_the_wrapped_call_raises(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "local")
    monkeypatch.setattr(settings, "ollama_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "ollama_voice_timeout_seconds", 6.0)

    with pytest.raises(RuntimeError):
        with voice_llm_timeout():
            raise RuntimeError("simulated failure mid-voice-turn")

    provider = get_llm_provider()
    assert provider._timeout_seconds == 30.0


def test_ollama_timeout_raises_llm_provider_error_for_graceful_fallback(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=6.0)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_anthropic_provider_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicLLMProvider(api_key="sk-super-secret", model="m", base_url="https://api.anthropic.com", timeout_seconds=5)
    with caplog.at_level(logging.DEBUG, logger="app.agent.llm"):
        with pytest.raises(LLMProviderError):
            provider.generate([LLMMessage(role="user", content="hi")])
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "sk-super-secret" not in logged_text


# ---------------------------------------------------------------------------
# Groq LLM provider (openai/gpt-oss-20b via Groq's OpenAI-compatible API)
# ---------------------------------------------------------------------------

def test_factory_fails_closed_when_groq_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_llm_provider()


def test_factory_returns_groq_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test-key")
    provider = get_llm_provider()
    assert isinstance(provider, GroqLLMProvider)


def test_factory_uses_the_shared_llm_timeout_for_groq_even_inside_voice_llm_timeout(monkeypatch):
    """Groq is a fast cloud API (unlike Ollama's CPU-bound local
    generation) - it reuses llm_timeout_seconds exactly like Anthropic and
    Gemini, so entering voice_llm_timeout() (Ollama-only) must not change
    it."""
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test-key")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 8.0)

    with voice_llm_timeout():
        voice_provider = get_llm_provider()
    text_provider = get_llm_provider()

    assert voice_provider._timeout_seconds == 8.0
    assert text_provider._timeout_seconds == 8.0


def test_groq_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GroqLLMProvider(api_key="", model="openai/gpt-oss-20b", base_url="https://api.groq.com", timeout_seconds=5)


def test_groq_provider_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse(
            {"choices": [{"message": {"role": "assistant", "content": "Sure, happy to help!"}}], "model": "openai/gpt-oss-20b"}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = GroqLLMProvider(api_key="gsk-secret-value", model="openai/gpt-oss-20b", base_url="https://api.groq.com", timeout_seconds=5)
    result = provider.generate(
        [LLMMessage(role="system", content="You are helpful."), LLMMessage(role="user", content="Hi there")],
        temperature=0.3,
    )

    assert result.content == "Sure, happy to help!"
    assert result.model == "openai/gpt-oss-20b"
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer gsk-secret-value"
    assert captured["headers"]["user-agent"] == "ai-admissions-platform/1.0"
    assert "gsk-secret-value" not in captured["url"]
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi there"},
    ]
    assert captured["body"]["temperature"] == 0.3
    assert captured["body"]["max_tokens"] == 150  # voice-suitable, concise replies
    assert captured["timeout"] == 5


def test_groq_provider_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqLLMProvider(api_key="gsk-x", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_groq_provider_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqLLMProvider(api_key="gsk-x", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_groq_provider_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = GroqLLMProvider(api_key="gsk-x", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_groq_provider_raises_on_empty_choices(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _FakeHTTPResponse({"choices": [], "model": "m"}))
    provider = GroqLLMProvider(api_key="gsk-x", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_groq_provider_raises_on_empty_text_content(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeHTTPResponse({"choices": [{"message": {"content": ""}}], "model": "m"}),
    )
    provider = GroqLLMProvider(api_key="gsk-x", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_groq_provider_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqLLMProvider(api_key="gsk-super-secret", model="m", base_url="https://api.groq.com", timeout_seconds=5)
    with caplog.at_level(logging.DEBUG, logger="app.agent.llm"):
        with pytest.raises(LLMProviderError):
            provider.generate([LLMMessage(role="user", content="hi")])
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "gsk-super-secret" not in logged_text
