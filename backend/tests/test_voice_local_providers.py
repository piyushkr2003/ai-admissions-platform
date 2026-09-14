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
absence. Piper is exercised via a fake subprocess.Popen standing in for
its persistent `--json-input` process (see _FakePiperProcess below -
second latency-audit pass); urllib.request.urlopen is monkeypatched for
Ollama.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import urllib.error
from pathlib import Path
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


class _FakeWhisperSegment:
    def __init__(self, text: str):
        self.text = text


class _FakeWhisperModel:
    """Stands in for a real faster_whisper.WhisperModel - counts how many
    times it was constructed, deliberately not touching any real model
    weights, so the warm-cache behavior can be proven deterministically
    and fast."""

    construct_calls = 0

    def __init__(self, model_size, device, compute_type):
        _FakeWhisperModel.construct_calls += 1
        self.model_size = model_size

    def transcribe(self, path, language=None, vad_filter=True):
        return [_FakeWhisperSegment("hello there")], object()


def _install_fake_faster_whisper(monkeypatch) -> None:
    fake_module = type(sys)("faster_whisper")
    fake_module.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)


def test_local_stt_warm_caches_the_whisper_model_across_provider_instances(monkeypatch):
    """Regression test for the latency-audit finding: app/voice/providers/
    factory.py::get_stt_provider() constructs a fresh
    LocalWhisperSTTProvider on every call, so without a module-level
    cache the Whisper model was reloaded (measured: ~1s with a warm OS
    disk cache, up to ~3s cold) on every single utterance. Two separate
    provider instances for the same (model_size, device, compute_type)
    must share exactly one loaded model - mirrors
    test_mms_model_cache_is_reused_without_reimporting_transformers's
    proof style for the MMS models above."""
    _FakeWhisperModel.construct_calls = 0
    _install_fake_faster_whisper(monkeypatch)

    provider1 = LocalWhisperSTTProvider(model_size="base", device="cpu", compute_type="int8")
    result1 = provider1.recognize(b"fake audio bytes one", language="en")

    provider2 = LocalWhisperSTTProvider(model_size="base", device="cpu", compute_type="int8")
    result2 = provider2.recognize(b"fake audio bytes two", language="en")

    assert _FakeWhisperModel.construct_calls == 1  # loaded once, reused by the second provider instance
    assert result1.text == "hello there"
    assert result2.text == "hello there"


def test_local_stt_uses_a_separate_cache_entry_per_model_configuration(monkeypatch):
    """A different (model_size, device, compute_type) must not reuse a
    cached model built for a different configuration."""
    _FakeWhisperModel.construct_calls = 0
    _install_fake_faster_whisper(monkeypatch)

    LocalWhisperSTTProvider(model_size="base", device="cpu", compute_type="int8").recognize(b"x", language="en")
    LocalWhisperSTTProvider(model_size="small", device="cpu", compute_type="int8").recognize(b"x", language="en")

    assert _FakeWhisperModel.construct_calls == 2


# ---------------------------------------------------------------------------
# LocalPiperTTSProvider - persistent/warm process (second latency-audit pass)
# ---------------------------------------------------------------------------

def test_local_tts_constructor_requires_model_path():
    with pytest.raises(ValueError):
        LocalPiperTTSProvider(command="piper", model_path="", timeout_seconds=10)


def test_local_tts_fails_closed_when_piper_executable_is_missing():
    with pytest.raises(ResourceUnavailableError, match="Piper"):
        LocalPiperTTSProvider(command="definitely-not-a-real-piper-binary-xyz", model_path="voice.onnx", timeout_seconds=10)


def _make_wav_bytes(frames: int = 8000, rate: int = 16000) -> bytes:
    import io
    import wave

    pcm = b"\x00\x01" * frames
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)
    return buf.getvalue()


class _FakePiperProcess:
    """Stands in for the persistent `--json-input` subprocess.Popen
    _PersistentPiperWorker spawns. `on_request(text, output_file,
    stdout_lines)` decides what happens for each stdin line written to
    it - normally it writes the requested wav bytes to output_file and
    puts that same path onto the fake stdout queue (mirroring the real
    binary's completion echo, confirmed by hand - see
    _PersistentPiperWorker's docstring); it can instead simulate a crash
    (put None -> ends the stdout iterator) or a hang (do nothing, for the
    timeout path)."""

    def __init__(self, cmd, on_request):
        self.cmd = cmd
        self._on_request = on_request
        self.stdin = self
        self.stdout = self
        self.stderr = iter(())
        self._lines: queue.Queue = queue.Queue()
        self._returncode = None

    # stdin-like
    def write(self, line: str) -> None:
        request = json.loads(line)
        self._on_request(request["text"], request["output_file"], self._lines)

    def flush(self) -> None:
        pass

    # stdout-like (iterable of completion-echo lines)
    def __iter__(self):
        return self

    def __next__(self):
        line = self._lines.get()
        if line is None:
            raise StopIteration
        return line + "\n"

    def poll(self):
        return self._returncode

    def kill(self) -> None:
        self._returncode = -9
        self._lines.put(None)


def _on_request_writes(wav_bytes: bytes):
    def _cb(text, output_file, lines):
        Path(output_file).write_bytes(wav_bytes)
        lines.put(output_file)
    return _cb


def _on_request_crashes(text, output_file, lines):
    lines.put(None)  # the process died without producing a completion line


def _on_request_hangs(text, output_file, lines):
    pass  # never responds - exercises the timeout path


def _install_fake_piper_popen(monkeypatch, on_request, *, captured: dict | None = None):
    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        if captured is not None:
            captured["cmd"] = cmd
            captured["cwd"] = cwd
        return _FakePiperProcess(cmd, on_request)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_local_tts_synthesize_spawns_the_persistent_process_in_piper_s_own_directory(monkeypatch):
    """The subprocess is still started with its cwd pinned to Piper's own
    directory (so it reliably finds espeak-ng-data/onnxruntime resources
    beside it) and with `--json-input`, not a per-call `--output_file -`
    stream-to-stdout invocation."""
    captured = {}
    _install_fake_piper_popen(monkeypatch, _on_request_writes(_make_wav_bytes()), captured=captured)
    # sys.executable is a real file on disk, satisfying the constructor's
    # existence check without needing a real Piper binary installed.
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)

    result = provider.synthesize("Hello there.", language="en")

    assert captured["cmd"] == [sys.executable, "--model", "en_US-lessac-medium.onnx", "--json-input"]
    assert captured["cwd"] == str(Path(sys.executable).resolve().parent)
    assert result.audio_bytes == _make_wav_bytes()
    assert result.duration_ms == 500  # 8000 frames / 16000 Hz


def test_local_tts_synthesize_reuses_the_same_warm_process_across_calls_and_instances(monkeypatch):
    """Regression test for this pass's core change: app/voice/providers/
    factory.py::get_tts_provider() constructs a fresh LocalPiperTTSProvider
    on every call, so without a warm, cached persistent process the
    Piper binary (and its ONNX model) was spawned/reloaded fresh on every
    single utterance (measured against the real binary: cold per-call
    ~1.2-1.3s vs ~0.6s once warm - about half the cost, dominated by
    voice-model load time). Two provider instances for the same
    (command, model_path) must share exactly one spawned process."""
    spawn_calls = []

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        return _FakePiperProcess(cmd, _on_request_writes(_make_wav_bytes()))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    provider1 = LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)
    result1 = provider1.synthesize("First call.")
    provider2 = LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)
    result2 = provider2.synthesize("Second call, same warm process.")

    assert len(spawn_calls) == 1  # spawned once, reused by the second provider instance and second call
    assert result1.audio_bytes is not None
    assert result2.audio_bytes is not None


def test_local_tts_uses_a_separate_warm_process_per_model_configuration(monkeypatch):
    """A different (command, model_path) must not reuse a process warmed
    for a different configuration."""
    spawn_calls = []

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        return _FakePiperProcess(cmd, _on_request_writes(_make_wav_bytes()))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10).synthesize("x")
    LocalPiperTTSProvider(command=sys.executable, model_path="en_US-other-voice.onnx", timeout_seconds=10).synthesize("x")

    assert len(spawn_calls) == 2


def test_local_tts_synthesize_ignores_a_non_file_voice_id(monkeypatch):
    """Root-cause regression test for the historical Windows crash
    (STATUS_STACK_BUFFER_OVERRUN / 0xC0000409) this provider fixed before
    this pass: `voice_id` is a cross-provider concept - for Gemini it's a
    named voice string (e.g. "Kore") that is never a filesystem path, and
    a college's seeded AgentConfig.voice_settings sets it that way by
    default ("nova-assist-default" - see app/db/seed.py). A bogus,
    non-file voice_id must still be ignored, reusing the default warm
    process exactly as if no voice_id had been supplied - never spawning
    a second process for a nonexistent "model"."""
    spawn_calls = []

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        return _FakePiperProcess(cmd, _on_request_writes(_make_wav_bytes()))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    provider = LocalPiperTTSProvider(
        command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10,
    )

    result = provider.synthesize("Hi! I'm Nova Assist.", language="en", voice_id="nova-assist-default")

    assert len(spawn_calls) == 1
    assert spawn_calls[0] == [sys.executable, "--model", "en_US-lessac-medium.onnx", "--json-input"]
    assert result.audio_bytes is not None


def test_local_tts_synthesize_honors_a_voice_id_that_is_a_real_model_file(monkeypatch, tmp_path):
    """The legitimate use of voice_id - overriding to a different,
    actually-existing Piper voice model - must still work, spawning
    (and then keeping warm) a separate persistent process for that
    specific model file."""
    real_model = tmp_path / "en_US-other-voice.onnx"
    real_model.write_bytes(b"not a real onnx file, existence is all that's checked")
    spawn_calls = []

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        return _FakePiperProcess(cmd, _on_request_writes(_make_wav_bytes()))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    provider = LocalPiperTTSProvider(
        command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10,
    )

    provider.synthesize("Hello", language="en", voice_id=str(real_model))

    assert spawn_calls == [[sys.executable, "--model", str(real_model), "--json-input"]]


def test_local_tts_synthesize_raises_on_empty_text(monkeypatch):
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("   ")


def test_local_tts_synthesize_raises_and_recovers_when_the_persistent_process_dies_mid_request(monkeypatch):
    """Covers what used to be two separate per-call failure modes
    (nonzero exit / the Windows STATUS_STACK_BUFFER_OVERRUN crash) - with
    a persistent process there is only one way this surfaces at the
    synthesize() layer: the whole process dies before echoing a
    completion line. Must fail closed with a clear error, never hang or
    raise an unhandled exception - and the *next* call must transparently
    spawn a fresh process rather than staying wedged forever."""
    spawn_calls = []
    processes = []

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        on_request = _on_request_crashes if len(spawn_calls) == 1 else _on_request_writes(_make_wav_bytes())
        process = _FakePiperProcess(cmd, on_request)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)

    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("Hello")

    result = provider.synthesize("Hello again, after the crash.")
    assert result.audio_bytes is not None
    assert len(spawn_calls) == 2  # the dead process was replaced, not reused


def test_local_tts_synthesize_raises_on_timeout(monkeypatch):
    _install_fake_piper_popen(monkeypatch, _on_request_hangs)
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=0.05)
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("Hello")


def test_local_tts_cancel_is_a_best_effort_no_op():
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    provider.cancel("some-ref")  # must not raise


# ---------------------------------------------------------------------------
# LocalPiperTTSProvider.synthesize_stream - sentence-level early TTS
# ---------------------------------------------------------------------------

def test_split_into_sentences_finds_safe_boundaries():
    assert local_providers._split_into_sentences("Hello there. How are you? Fine!") == [
        "Hello there.", "How are you?", "Fine!",
    ]
    assert local_providers._split_into_sentences("No terminal punctuation here") == ["No terminal punctuation here"]
    assert local_providers._split_into_sentences("   ") == []


def test_synthesize_stream_yields_one_chunk_per_sentence_from_the_warm_process(monkeypatch):
    spawn_calls = []
    request_texts = []

    def _on_request(text, output_file, lines):
        request_texts.append(text)
        Path(output_file).write_bytes(_make_wav_bytes())
        lines.put(output_file)

    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        spawn_calls.append(cmd)
        return _FakePiperProcess(cmd, _on_request)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)

    chunks = list(provider.synthesize_stream("First sentence. Second sentence. Third one."))

    assert len(chunks) == 3
    assert all(chunk.audio_bytes is not None for chunk in chunks)
    assert request_texts == ["First sentence.", "Second sentence.", "Third one."]
    assert len(spawn_calls) == 1  # the same warm process serves every sentence, not a new one per sentence


def test_synthesize_stream_raises_on_empty_text():
    provider = LocalPiperTTSProvider(command=sys.executable, model_path="voice.onnx", timeout_seconds=10)
    with pytest.raises(ResourceUnavailableError):
        list(provider.synthesize_stream("   "))


def test_base_tts_provider_synthesize_stream_default_falls_back_to_a_single_synthesize_call():
    """Every provider that does NOT override synthesize_stream (e.g.
    Gemini, mock) keeps working unchanged - TTSProvider's own default
    implementation just wraps the one synthesize() result."""
    from app.voice.providers.mock import MockTTSProvider

    provider = MockTTSProvider()
    chunks = list(provider.synthesize_stream("Hello there.", language="en"))
    assert len(chunks) == 1
    assert chunks[0].audio_bytes is not None


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
    """The module-level MMS/Whisper/Piper warm caches must not leak state
    between tests - each test that touches any of them starts from empty
    and cleans up after itself regardless of pass/fail. (Also covers
    _WHISPER_MODEL_CACHE and _PIPER_WORKER_CACHE, added by the two
    latency-audit warm-cache passes - kept in this one fixture rather
    than near-identical extra ones.)"""
    local_providers._MMS_MODEL_CACHE.clear()
    local_providers._WHISPER_MODEL_CACHE.clear()
    local_providers._PIPER_WORKER_CACHE.clear()
    yield
    local_providers._MMS_MODEL_CACHE.clear()
    local_providers._WHISPER_MODEL_CACHE.clear()
    local_providers._PIPER_WORKER_CACHE.clear()


def _multilingual_provider(piper_command: str = sys.executable) -> LocalMultilingualTTSProvider:
    piper = LocalPiperTTSProvider(command=piper_command, model_path="en_US-lessac-medium.onnx", timeout_seconds=10)
    return LocalMultilingualTTSProvider(
        piper_provider=piper, hindi_model_id="facebook/mms-tts-hin", kannada_model_id="facebook/mms-tts-kan",
    )


def _install_fake_piper_popen_writing(monkeypatch, wav_bytes: bytes, *, captured: dict | None = None):
    def fake_popen(cmd, *, stdin, stdout, stderr, text, bufsize, cwd=None):
        if captured is not None:
            captured["cmd"] = cmd
        return _FakePiperProcess(cmd, _on_request_writes(wav_bytes))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_multilingual_tts_routes_english_to_piper_unchanged(monkeypatch):
    captured = {}
    _install_fake_piper_popen_writing(monkeypatch, _wav_bytes(), captured=captured)
    provider = _multilingual_provider()

    result = provider.synthesize("Hello there.", language="en")

    assert captured["cmd"][0] == sys.executable
    assert "--model" in captured["cmd"]
    assert result.audio_bytes is not None


def test_multilingual_tts_routes_hinglish_to_piper_unchanged(monkeypatch):
    """No dedicated Hinglish voice model exists - it must fall back to
    the same English Piper path as "en", not silently fail."""
    _install_fake_piper_popen_writing(monkeypatch, _wav_bytes())
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
    # Explicit constructor kwargs always win over a developer's local
    # backend/.env in pydantic-settings' precedence order, so the three
    # provider fields must always be passed here (defaulting to "mock")
    # rather than left unset - otherwise a real backend/.env configured
    # for local voice mode (STT_PROVIDER=local/TTS_PROVIDER=local/
    # AGENT_LLM_PROVIDER=local, exactly as this addendum's own setup
    # instructs a developer to set) would leak into
    # test_production_passes_with_default_mock_providers_and_local_not_selected
    # and make it fail non-deterministically across machines.
    base = dict(
        app_env="production", app_debug=False, jwt_secret_key="a" * 40,
        cors_allowed_origins="https://admissions.example.edu",
        stt_provider="mock", tts_provider="mock", agent_llm_provider="mock",
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
