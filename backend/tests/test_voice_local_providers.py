"""Task 023 - Local Free Demo Mode provider adapters, plus the Local
Voice: English/Hindi/Kannada addendum (LocalMultilingualTTSProvider).

Covers construction/validation, fail-closed behavior when the local
process/model isn't installed or running, request construction/response
parsing for Ollama, provider-factory selection for STT/TTS/LLM=local,
that no API key is ever required in local mode, and that
Settings.validate_for_production() rejects "local" outright. No real
Whisper model is downloaded, no real Ollama server is contacted, no real
Piper binary is invoked, and no real MMS-TTS/transformers model is
loaded anywhere in this file - `faster_whisper`/`transformers`/`torch`
are all genuinely installed in this development environment (unlike
when this file was first written), so their ImportError fail-closed
paths are exercised deterministically via
`monkeypatch.setitem(sys.modules, name, None)` (a documented Python
trick: it makes the next `import name` raise ImportError regardless of
whether the package is actually installed) rather than relying on real
absence. subprocess.run and urllib.request.urlopen are monkeypatched
for Piper and Ollama respectively.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from types import SimpleNamespace

import pytest

from app.agent.providers.base import LLMMessage, LLMProviderError
from app.agent.providers.factory import get_llm_provider
from app.agent.providers.local import OllamaLLMProvider
from app.core.config import Settings, get_settings
from app.core.errors import ResourceUnavailableError
from app.voice.providers.factory import get_stt_provider, get_tts_provider
from app.voice.providers.local import LocalMultilingualTTSProvider, LocalPiperTTSProvider, LocalWhisperSTTProvider
import app.voice.providers.local as local_providers


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ---------------------------------------------------------------------------
# LocalWhisperSTTProvider
# ---------------------------------------------------------------------------

def test_local_stt_recognize_returns_empty_result_for_empty_audio_without_loading_a_model():
    provider = LocalWhisperSTTProvider(model_size="base", device="cpu", compute_type="int8")
    result = provider.recognize(b"", language="en")
    assert result.text == ""
    assert result.language == "en"


def test_local_stt_fails_closed_when_faster_whisper_is_not_installed(monkeypatch):
    # `faster_whisper` is genuinely installed in this development
    # environment (it's part of the real local voice stack this addendum
    # builds on) - simulate absence deterministically rather than relying
    # on it not being there. See the module docstring for why this is a
    # legitimate technique, not a weaker test.
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    provider = LocalWhisperSTTProvider(model_size="base", device="cpu", compute_type="int8")
    with pytest.raises(ResourceUnavailableError, match="faster-whisper"):
        provider.recognize(b"some audio bytes", language="en")


# ---------------------------------------------------------------------------
# LocalPiperTTSProvider
# ---------------------------------------------------------------------------

def test_local_tts_constructor_requires_model_path():
    with pytest.raises(ValueError):
        LocalPiperTTSProvider(command="piper", model_path="", timeout_seconds=10)


def test_local_tts_fails_closed_when_piper_executable_is_missing():
    with pytest.raises(ResourceUnavailableError, match="Piper"):
        LocalPiperTTSProvider(command="definitely-not-a-real-piper-binary-xyz", model_path="voice.onnx", timeout_seconds=10)


def test_local_tts_synthesize_sends_expected_subprocess_invocation_and_parses_wav(monkeypatch, tmp_path):
    import io
    import wave

    pcm = b"\x00\x01" * 8000  # 8000 frames, 16-bit mono
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(pcm)
    wav_bytes = buf.getvalue()

    captured = {}

    def fake_run(cmd, *, input, capture_output, timeout, check):
        captured["cmd"] = cmd
        captured["input"] = input
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=wav_bytes, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # sys.executable is a real file on disk, satisfying the constructor's
    # existence check without needing a real Piper binary installed.
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)

    result = provider.synthesize("Hello there.", language="en")

    assert captured["cmd"] == [sys.executable, "--model", "en_US-lessac-medium.onnx", "--output_file", "-"]
    assert captured["input"] == b"Hello there."
    assert result.audio_bytes == wav_bytes
    assert result.duration_ms == 500  # 8000 frames / 16000 Hz


def test_local_tts_synthesize_raises_on_empty_text(monkeypatch):
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("   ")


def test_local_tts_synthesize_raises_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, *, input, capture_output, timeout, check):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"model not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("Hello")


def test_local_tts_synthesize_raises_on_timeout(monkeypatch):
    def fake_run(cmd, *, input, capture_output, timeout, check):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("Hello")


def test_local_tts_cancel_is_a_best_effort_no_op():
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    provider.cancel("some-ref")  # must not raise


# ---------------------------------------------------------------------------
# LocalMultilingualTTSProvider (Local Voice: English/Hindi/Kannada)
# ---------------------------------------------------------------------------

class _FakeWaveform:
    def __init__(self, samples: list[float]):
        self._samples = samples

    def squeeze(self):
        return self

    def tolist(self):
        return self._samples


class _FakeMmsModel:
    """Stands in for a real `transformers.VitsModel` - deliberately not a
    torch object at all, proving LocalMultilingualTTSProvider.synthesize
    only depends on the documented `.config.sampling_rate` attribute and
    a callable returning something with a `.waveform` attribute, not on
    any real tensor implementation detail."""

    def __init__(self, samples: list[float], sample_rate: int = 16000):
        self._samples = samples
        self.config = SimpleNamespace(sampling_rate=sample_rate)
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(waveform=_FakeWaveform(self._samples))


def _fake_tokenizer(text, return_tensors=None):
    return {}


@pytest.fixture(autouse=True)
def _clear_mms_cache():
    """The module-level MMS model cache must not leak state between
    tests - each test that touches it starts from empty and cleans up
    after itself regardless of pass/fail."""
    local_providers._MMS_MODEL_CACHE.clear()
    yield
    local_providers._MMS_MODEL_CACHE.clear()


def _multilingual_provider(piper_command: str = sys.executable) -> LocalMultilingualTTSProvider:
    piper = LocalPiperTTSProvider(command=piper_command, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)
    return LocalMultilingualTTSProvider(
        piper_provider=piper, hindi_model_id="facebook/mms-tts-hin", kannada_model_id="facebook/mms-tts-kan",
    )


def test_multilingual_tts_routes_english_to_piper_unchanged(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, returncode=0, stdout=_wav_bytes(), stderr=b"")

    monkeypatch.setattr("subprocess.run", fake_run)
    provider = _multilingual_provider()

    result = provider.synthesize("Hello there.", language="en")

    assert captured["args"][0] == sys.executable
    assert "--model" in captured["args"]
    assert result.audio_bytes is not None


def test_multilingual_tts_routes_hinglish_to_piper_unchanged(monkeypatch):
    """No dedicated Hinglish voice model exists - it must fall back to
    the same English Piper path as "en", not silently fail."""
    monkeypatch.setattr("subprocess.run", lambda args, **kwargs: subprocess.CompletedProcess(args, returncode=0, stdout=_wav_bytes(), stderr=b""))
    provider = _multilingual_provider()
    result = provider.synthesize("CSE ka fee kitna hai?", language="hinglish")
    assert result.audio_bytes is not None


def test_multilingual_tts_routes_hindi_to_mms_model(monkeypatch):
    fake_model = _FakeMmsModel([0.1, -0.2, 0.3, -0.1] * 400)  # ~0.1s at 16kHz
    monkeypatch.setattr(
        local_providers, "_load_mms_model",
        lambda model_id: (fake_model, _fake_tokenizer) if model_id == "facebook/mms-tts-hin" else (_ for _ in ()).throw(AssertionError(model_id)),
    )
    provider = _multilingual_provider()

    result = provider.synthesize("नमस्ते", language="hi")

    assert fake_model.calls == 1
    assert result.audio_bytes is not None
    assert result.duration_ms > 0


def test_multilingual_tts_routes_kannada_to_mms_model(monkeypatch):
    fake_model = _FakeMmsModel([0.05, -0.05, 0.2])
    monkeypatch.setattr(
        local_providers, "_load_mms_model",
        lambda model_id: (fake_model, _fake_tokenizer) if model_id == "facebook/mms-tts-kan" else (_ for _ in ()).throw(AssertionError(model_id)),
    )
    provider = _multilingual_provider()

    result = provider.synthesize("ನಮಸ್ಕಾರ", language="kn")

    assert fake_model.calls == 1
    assert result.audio_bytes is not None


def test_multilingual_tts_raises_on_empty_text():
    provider = _multilingual_provider()
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("   ", language="kn")


def test_multilingual_tts_fails_closed_when_transformers_is_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    provider = _multilingual_provider()
    with pytest.raises(ResourceUnavailableError, match="transformers"):
        provider.synthesize("ನಮಸ್ಕಾರ", language="kn")


def test_mms_model_cache_is_reused_without_reimporting_transformers(monkeypatch):
    """Item 7/21 ("load once, keep warm", proven deterministically - not
    merely asserted because model files exist on disk): exercises the
    real `_load_mms_model` function and the real `_MMS_MODEL_CACHE` dict
    (neither monkeypatched here). Pre-warm the cache directly, break the
    transformers import, then prove synthesize() still succeeds because
    it never needs to import transformers/torch again - a cache miss
    would raise ResourceUnavailableError instead."""
    fake_model = _FakeMmsModel([0.2, -0.2])
    local_providers._MMS_MODEL_CACHE["facebook/mms-tts-hin"] = (fake_model, _fake_tokenizer)
    monkeypatch.setitem(sys.modules, "transformers", None)  # would fail closed if re-imported

    provider = _multilingual_provider()
    result = provider.synthesize("नमस्ते", language="hi")

    assert fake_model.calls == 1
    assert result.audio_bytes is not None

    # A second, brand-new provider instance (mirroring the factory
    # constructing a fresh object per request - app/voice/providers/
    # factory.py) reuses the exact same warm model, never reloading it.
    second_result = _multilingual_provider().synthesize("फिर से नमस्ते", language="hi")
    assert fake_model.calls == 2
    assert second_result.audio_bytes is not None


def _wav_bytes() -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 100)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# OllamaLLMProvider
# ---------------------------------------------------------------------------

def test_ollama_provider_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse({"model": "llama3.2:3b", "message": {"role": "assistant", "content": "Sure, happy to help!"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=30)
    result = provider.generate(
        [LLMMessage(role="system", content="You are helpful."), LLMMessage(role="user", content="Hi there")],
        temperature=0.3,
    )

    assert result.content == "Sure, happy to help!"
    assert result.model == "llama3.2:3b"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == "llama3.2:3b"
    assert captured["body"]["stream"] is False
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi there"},
    ]
    assert captured["body"]["options"]["temperature"] == 0.3
    assert captured["timeout"] == 30


def test_ollama_provider_raises_on_connection_refused(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=30)
    with pytest.raises(LLMProviderError, match="ollama serve"):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_ollama_provider_raises_helpful_message_on_missing_model(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=30)
    with pytest.raises(LLMProviderError, match="ollama pull llama3.2:3b"):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_ollama_provider_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=30)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


def test_ollama_provider_raises_on_empty_content(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeHTTPResponse({"model": "llama3.2:3b", "message": {"content": ""}}),
    )
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=30)
    with pytest.raises(LLMProviderError):
        provider.generate([LLMMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# Provider factory selection - "local" mode requires no API key at all
# ---------------------------------------------------------------------------

def test_stt_factory_returns_local_provider_with_no_api_key_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "local")
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "stt_api_key", "")
    assert isinstance(get_stt_provider(), LocalWhisperSTTProvider)


def test_llm_factory_returns_local_provider_with_no_api_key_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_llm_provider", "local")
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert isinstance(get_llm_provider(), OllamaLLMProvider)


def test_tts_factory_fails_closed_when_local_selected_without_piper_model_path(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "local")
    monkeypatch.setattr(settings, "piper_model_path", "")
    with pytest.raises(ResourceUnavailableError, match="PIPER_MODEL_PATH"):
        get_tts_provider()


def test_tts_factory_returns_local_provider_when_configured_with_no_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "local")
    monkeypatch.setattr(settings, "piper_command", sys.executable)  # a real file on disk
    monkeypatch.setattr(settings, "piper_model_path", "en_US-lessac-medium.onnx")
    monkeypatch.setattr(settings, "tts_api_key", "")
    monkeypatch.setattr(settings, "google_api_key", "")
    provider = get_tts_provider()
    assert isinstance(provider, LocalMultilingualTTSProvider)
    assert isinstance(provider._piper, LocalPiperTTSProvider)


def test_tts_factory_wires_configured_mms_model_ids(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "local")
    monkeypatch.setattr(settings, "piper_command", sys.executable)
    monkeypatch.setattr(settings, "piper_model_path", "en_US-lessac-medium.onnx")
    monkeypatch.setattr(settings, "mms_hindi_model_id", "facebook/mms-tts-hin")
    monkeypatch.setattr(settings, "mms_kannada_model_id", "facebook/mms-tts-kan")
    provider = get_tts_provider()
    assert provider._model_ids == {"hi": "facebook/mms-tts-hin", "kn": "facebook/mms-tts-kan"}


def test_stt_language_mapping_passes_kannada_through_explicitly():
    """Item 9: the selected language reaches faster-whisper explicitly
    rather than falling back to auto-detection."""
    assert local_providers._to_whisper_language("kn") == "kn"
    assert local_providers._to_whisper_language("en") == "en"
    assert local_providers._to_whisper_language("hi") == "hi"
    assert local_providers._to_whisper_language("hinglish") == "hi"


# ---------------------------------------------------------------------------
# Production fail-closed: "local" providers must never run in production
# ---------------------------------------------------------------------------

def _production_settings(**overrides) -> Settings:
    base = dict(
        app_env="production", app_debug=False, jwt_secret_key="a" * 40,
        cors_allowed_origins="https://admissions.example.edu",
    )
    base.update(overrides)
    return Settings(**base)


def test_production_rejects_local_stt():
    with pytest.raises(RuntimeError, match="STT_PROVIDER=local"):
        _production_settings(stt_provider="local").validate_for_production()


def test_production_rejects_local_tts():
    with pytest.raises(RuntimeError, match="TTS_PROVIDER=local"):
        _production_settings(tts_provider="local").validate_for_production()


def test_production_rejects_local_llm():
    with pytest.raises(RuntimeError, match="AGENT_LLM_PROVIDER=local"):
        _production_settings(agent_llm_provider="local").validate_for_production()


def test_production_passes_with_default_mock_providers_and_local_not_selected():
    _production_settings().validate_for_production()  # must not raise
