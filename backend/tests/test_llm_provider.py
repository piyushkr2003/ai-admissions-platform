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
from app.agent.providers.factory import get_llm_provider
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
