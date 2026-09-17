"""Groq STT/TTS provider adapters (whisper-large-v3-turbo + Orpheus TTS via
Groq's OpenAI-compatible API).

Covers request construction (including the hand-rolled multipart body -
Groq's transcription endpoint, unlike the JSON-only Gemini/Anthropic
adapters, takes a file upload), response parsing, timeout/HTTP-error/
malformed-response handling, empty/invalid-audio safety, language
mapping, provider-factory selection/fail-closed behavior, production
fail-closed validation, and no-secret-logging. No real network call is
made anywhere in this file - `urllib.request.urlopen` is monkeypatched
throughout, exactly like tests/test_voice_gemini.py does for the sibling
Gemini adapter.

TTS coverage mirrors test_voice_gemini.py's TTS section, with one
structural difference: Groq's TTS endpoint returns raw audio bytes
directly (not JSON/base64), so GroqTTSProvider's response handling is
simpler than GeminiTTSProvider's - there is no candidates/parts/
inlineData shape to unwrap, so there are no "no candidates"/"no audio
data" malformed-response variants to test here, only "empty body".
"""
from __future__ import annotations

import json
import logging
import urllib.error
import wave
from io import BytesIO

import pytest

from app.core.config import Settings, get_settings
from app.core.errors import ResourceUnavailableError
from app.voice.providers.factory import get_stt_provider, get_tts_provider
from app.voice.providers.groq import GroqSTTProvider, GroqTTSProvider, _to_groq_language

FAKE_KEY = "gsk-super-secret-value"


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeBinaryResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sample_wav_bytes(num_frames: int = 4800, frame_rate: int = 24000) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames)
    return buffer.getvalue()


def _sample_pcm16(num_samples: int = 400) -> bytes:
    return bytes(range(256)) * (num_samples // 256 + 1)


def _stt_response(text: str) -> _FakeHTTPResponse:
    return _FakeHTTPResponse({"text": text})


# ---------------------------------------------------------------------------
# Language mapping
# ---------------------------------------------------------------------------

def test_language_mapping_matches_whisper_iso_codes():
    assert _to_groq_language("en") == "en"
    assert _to_groq_language("hi") == "hi"
    assert _to_groq_language("hinglish") == "hi"
    assert _to_groq_language("kn") == "kn"
    assert _to_groq_language(None) is None
    assert _to_groq_language("unknown") is None


# ---------------------------------------------------------------------------
# GroqSTTProvider - construction / request / response
# ---------------------------------------------------------------------------

def test_stt_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GroqSTTProvider(api_key="", model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)


def test_stt_recognize_returns_empty_result_for_empty_audio_without_network_call(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("must not call the network for empty audio")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    result = provider.recognize(b"", language="en")
    assert result.text == ""
    assert result.language == "en"


def test_stt_recognize_handles_invalid_audio_safely_without_raising(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("must not call the network when raw audio cannot be wrapped")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    # num_channels=0 makes the WAV writer reject the buffer (wave.Error),
    # exercising the "invalid audio" safety path without a real bad payload.
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=0)
    result = provider.recognize(_sample_pcm16(), language="en")
    assert result.text == ""


def test_stt_recognize_sends_expected_multipart_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _stt_response("What is the fee for B.Tech CSE?")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = GroqSTTProvider(
        api_key=FAKE_KEY, model="whisper-large-v3-turbo", base_url="https://api.groq.com",
        timeout_seconds=8, sample_rate=16000, num_channels=1,
    )
    result = provider.recognize(_sample_pcm16(), language="en")

    assert result.text == "What is the fee for B.Tech CSE?"
    assert result.language == "en"
    assert captured["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert captured["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
    assert captured["headers"]["user-agent"] == "ai-admissions-platform/1.0"
    assert captured["headers"]["content-type"].startswith("multipart/form-data; boundary=")
    assert captured["timeout"] == 8

    boundary = captured["headers"]["content-type"].split("boundary=", 1)[1]
    body_text = captured["body"].decode("utf-8", errors="replace")
    assert boundary in body_text
    assert 'name="model"' in body_text
    assert "whisper-large-v3-turbo" in body_text
    assert 'name="language"' in body_text
    assert 'name="file"; filename="audio.wav"' in body_text
    assert "Content-Type: audio/wav" in body_text
    assert FAKE_KEY not in body_text  # the key must only ever be in the header, never the body


# ---------------------------------------------------------------------------
# Browser-recorded (compressed) audio containers - Task: continuous voice
# STT bugfix. The browser's `MediaRecorder` (frontend/features/voice/
# voice-console.tsx::beginListeningTurn - no mimeType is ever passed, so
# the browser's own default applies) never produces raw PCM16 - Chrome
# defaults to WebM/Opus, Firefox to Ogg/Opus, Safari to MP4/AAC. Before
# this fix, any such input fell through to pcm16_to_wav_bytes (meant only
# for the LiveKit worker's genuinely-raw-PCM16 buffers), which just adds
# a WAV header without decoding anything - producing a structurally
# valid but acoustically meaningless WAV, so Whisper returned an empty
# or garbage transcript for every real spoken browser turn even though
# the HTTP call to Groq itself succeeded (200 OK). These tests confirm a
# recognizable container is now forwarded to Groq byte-for-byte with a
# matching filename/content-type instead of being misinterpreted as PCM.
# ---------------------------------------------------------------------------

def test_stt_recognize_forwards_webm_audio_unchanged_with_matching_content_type(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = request.data
        return _stt_response("What is the fee for B.Tech CSE?")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    # A real Chrome-recorded clip starts with the WebM/Matroska EBML
    # header - the exact bytes don't matter beyond that magic prefix,
    # since this path forwards them as-is rather than parsing them.
    webm_bytes = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="whisper-large-v3-turbo", base_url="https://api.groq.com", timeout_seconds=8, sample_rate=16000, num_channels=1)
    result = provider.recognize(webm_bytes, language="en")

    assert result.text == "What is the fee for B.Tech CSE?"
    boundary = captured["headers"]["content-type"].split("boundary=", 1)[1]
    body_text = captured["body"]
    assert b'filename="audio.webm"' in body_text
    assert b"Content-Type: audio/webm" in body_text
    # The original bytes were forwarded unchanged - never reinterpreted as PCM16.
    assert webm_bytes in body_text
    assert boundary.encode() in body_text


def test_stt_recognize_forwards_ogg_audio_unchanged_with_matching_content_type(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = request.data
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    ogg_bytes = b"OggS" + b"\x00" * 64  # Firefox's default MediaRecorder output
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=8, sample_rate=16000, num_channels=1)
    provider.recognize(ogg_bytes, language="en")

    assert b'filename="audio.ogg"' in captured["body"]
    assert b"Content-Type: audio/ogg" in captured["body"]
    assert ogg_bytes in captured["body"]


def test_stt_recognize_forwards_mp4_audio_unchanged_with_matching_content_type(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = request.data
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64  # Safari's default MediaRecorder output
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=8, sample_rate=16000, num_channels=1)
    provider.recognize(mp4_bytes, language="en")

    assert b'filename="audio.mp4"' in captured["body"]
    assert b"Content-Type: audio/mp4" in captured["body"]
    assert mp4_bytes in captured["body"]


def test_stt_recognize_still_treats_headerless_bytes_as_raw_pcm16(monkeypatch):
    """Guards the LiveKit realtime worker's path (genuinely raw PCM16,
    app/voice/worker/session_worker.py) - bytes with none of the known
    container magic numbers must still go through pcm16_to_wav_bytes
    exactly as before this fix, not be forwarded as-is."""
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = request.data
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=8, sample_rate=16000, num_channels=1)
    provider.recognize(_sample_pcm16(), language="en")

    assert b'filename="audio.wav"' in captured["body"]
    assert b"Content-Type: audio/wav" in captured["body"]
    # A genuine WAV header (RIFF/WAVE chunk markers) was added by
    # pcm16_to_wav_bytes - confirming this path still wraps raw PCM16
    # exactly as before this fix, rather than skipping straight to the
    # container pass-through the WebM/Ogg/MP4 tests above exercise.
    assert b"RIFF" in captured["body"]
    assert b"WAVE" in captured["body"]


def test_stt_recognize_omits_language_field_when_unselected(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = request.data.decode("utf-8", errors="replace")
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    provider.recognize(_sample_pcm16(), language=None)
    assert 'name="language"' not in captured["body"]


def test_stt_recognize_passes_already_wrapped_wav_through_unchanged(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = request.data
        return _stt_response("hi")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    wav_bytes = b"RIFF" + b"\x00" * 40  # only the RIFF magic matters to _as_wav's branch
    provider.recognize(wav_bytes, language="en")
    assert wav_bytes in captured["body"]


def test_stt_recognize_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16(), language="en")


def test_stt_recognize_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None, context=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16(), language="en")


def test_stt_recognize_uses_an_explicit_certifi_backed_ssl_context(monkeypatch):
    """Diagnosed failure: urllib.request.urlopen() with no explicit SSL
    context falls back to the OS trust store, which on some machines
    lacks (or has a stale copy of) a root certificate api.groq.com's
    chain needs - the connection then fails the TLS handshake in well
    under a second, previously indistinguishable from a genuine slow/
    dropped connection (see the module's _SSL_CONTEXT docstring)."""
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["context"] = context
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    provider.recognize(_sample_pcm16(), language="en")

    import ssl

    assert isinstance(captured["context"], ssl.SSLContext)


def test_stt_recognize_reports_a_tls_certificate_failure_distinctly_from_a_timeout(monkeypatch):
    """A certificate-verification failure must never be reported as
    "unreachable or timed out" again - that message previously hid the
    real, locally-diagnosable cause (see this fix's investigation)."""
    import ssl
    import urllib.error

    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError) as exc_info:
        provider.recognize(_sample_pcm16(), language="en")

    message = str(exc_info.value)
    assert "certificate" in message.lower()
    assert "timed out" not in message.lower()


def test_stt_recognize_still_reports_a_genuine_connection_failure_as_unreachable(monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.URLError(OSError("Connection refused"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError) as exc_info:
        provider.recognize(_sample_pcm16(), language="en")

    assert "unreachable or timed out" in str(exc_info.value).lower()


def test_stt_recognize_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None, context=None: _BadResponse({}))
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16(), language="en")


def test_stt_recognize_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://api.groq.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with caplog.at_level(logging.DEBUG, logger="app.voice.groq"):
        with pytest.raises(ResourceUnavailableError):
            provider.recognize(_sample_pcm16(), language="en")
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_KEY not in logged_text


# ---------------------------------------------------------------------------
# Provider factory selection / fail-closed
#
# Note: unlike test_voice_gemini.py's "still returns mock by default" test,
# there is no bare no-monkeypatch default-provider test here - a developer
# environment configured for the Local Free Demo Mode (STT_PROVIDER=local
# in .env) makes "the default" ambiguous, so every test below pins
# stt_provider explicitly via monkeypatch instead of relying on whatever
# Settings() happens to load unset fields as.
# ---------------------------------------------------------------------------

def test_stt_factory_fails_closed_when_groq_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_stt_provider()


def test_stt_factory_returns_groq_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    provider = get_stt_provider()
    assert isinstance(provider, GroqSTTProvider)


# ---------------------------------------------------------------------------
# GroqTTSProvider - construction / request / response
# ---------------------------------------------------------------------------

def test_tts_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GroqTTSProvider(api_key="", model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")


def test_tts_provider_constructor_requires_voice_name():
    with pytest.raises(ValueError):
        GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="")


def test_tts_synthesize_raises_on_empty_text():
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("   ")


def test_tts_synthesize_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}
    wav_bytes = _sample_wav_bytes(num_frames=4800, frame_rate=24000)

    def fake_urlopen(request, timeout=None, context=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeBinaryResponse(wav_bytes)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")

    result = provider.synthesize("Your tuition fee is one lakh fifty thousand rupees.", language="en")

    assert captured["url"] == "https://api.groq.com/openai/v1/audio/speech"
    assert captured["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in captured["url"]
    assert captured["body"] == {
        "model": "canopylabs/orpheus-v1-english", "input": "Your tuition fee is one lakh fifty thousand rupees.",
        "voice": "troy", "response_format": "wav",
    }
    assert captured["timeout"] == 5

    assert result.audio_url is None
    assert result.audio_bytes == wav_bytes
    assert result.provider_ref
    assert result.duration_ms == 200  # 4800 frames / 24000 Hz


def test_tts_synthesize_honors_voice_id_override(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeBinaryResponse(_sample_wav_bytes())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    provider.synthesize("hello", voice_id="hannah")
    assert captured["body"]["voice"] == "hannah"


def test_tts_synthesize_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_includes_groqs_own_error_message_on_http_error(monkeypatch):
    """Diagnosability fix: a bare 'Groq TTS API returned HTTP 400.' gives
    no way to tell a bad model/voice name apart from a not-yet-enabled
    model on this account - Groq's own JSON error body carries that
    reason, so it must be surfaced rather than discarded."""
    error_body = json.dumps({"error": {"message": "model_not_found: the requested model does not exist"}}).encode("utf-8")

    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", hdrs=None, fp=BytesIO(error_body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError, match="model_not_found"):
        provider.synthesize("hello")


def test_tts_synthesize_raises_on_http_error_with_unparseable_body(monkeypatch):
    """A malformed/absent error body must not itself crash error
    handling - falls back to the bare HTTP-status message."""
    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=BytesIO(b"not json"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError, match="Groq TTS API returned HTTP 500"):
        provider.synthesize("hello")


def test_tts_synthesize_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None, context=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_raises_when_response_body_is_empty(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None, context=None: _FakeBinaryResponse(b""))
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_returns_zero_duration_for_a_non_wav_body_without_raising(monkeypatch):
    """A malformed/non-WAV 200 response must not crash the turn - the
    duration estimate degrades to 0 rather than the whole synthesis
    failing, mirroring _wav_duration_ms's documented fail-safe contract."""
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None, context=None: _FakeBinaryResponse(b"not a wav file"))
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    result = provider.synthesize("hello")
    assert result.duration_ms == 0
    assert result.audio_bytes == b"not a wav file"


def test_tts_synthesize_computes_duration_from_actual_bytes_despite_a_bogus_declared_wav_size(monkeypatch):
    """Regression test for a real bug observed against Groq's live TTS
    API: it writes a placeholder 0xFFFFFFFF size into the RIFF and `data`
    subchunk headers (streamed generation, final size unknown up front),
    which previously made `wave.getnframes()` report a ~25-hour duration
    for an 8-second reply. The real payload here is 48000 bytes of 16-bit
    mono PCM at 24000 Hz (48000 / 2 / 24000 * 1000 = 1000ms), with both
    size fields in the header lying about it."""
    fmt_chunk = (
        b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")  # PCM
        + (1).to_bytes(2, "little")  # mono
        + (24000).to_bytes(4, "little")  # sample rate
        + (48000).to_bytes(4, "little")  # byte rate
        + (2).to_bytes(2, "little")  # block align
        + (16).to_bytes(2, "little")  # bits per sample
    )
    payload = b"\x00\x00" * 24000  # 48000 bytes = 1000ms at 24kHz mono 16-bit
    wav_bytes = (
        b"RIFF" + (0xFFFFFFFF).to_bytes(4, "little") + b"WAVE"
        + fmt_chunk
        + b"data" + (0xFFFFFFFF).to_bytes(4, "little") + payload
    )

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None, context=None: _FakeBinaryResponse(wav_bytes))
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    result = provider.synthesize("hello")

    assert result.duration_ms == 1000
    assert result.audio_bytes == wav_bytes


def test_tts_synthesize_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None, context=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    with caplog.at_level(logging.DEBUG, logger="app.voice.groq"):
        with pytest.raises(ResourceUnavailableError):
            provider.synthesize("hello")
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_KEY not in logged_text


def test_tts_cancel_is_a_best_effort_no_op():
    provider = GroqTTSProvider(api_key=FAKE_KEY, model="canopylabs/orpheus-v1-english", base_url="https://api.groq.com", timeout_seconds=5, voice_name="troy")
    provider.cancel("some-ref")  # must not raise


def test_tts_factory_fails_closed_when_groq_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_tts_provider()


def test_tts_factory_returns_groq_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    assert isinstance(get_tts_provider(), GroqTTSProvider)


# ---------------------------------------------------------------------------
# Production fail-closed validation
# ---------------------------------------------------------------------------

def _production_settings(**overrides) -> Settings:
    # Explicitly pins stt_provider/tts_provider/agent_llm_provider to
    # "mock" (rather than leaving them unset) so this helper's baseline is
    # deterministic regardless of what a developer's own .env happens to
    # set them to (e.g. Local Free Demo Mode's STT_PROVIDER=local) - see
    # the factory-selection section's note above.
    base = dict(
        app_env="production", app_debug=False, jwt_secret_key="a" * 40,
        cors_allowed_origins="https://admissions.example.edu",
        stt_provider="mock", tts_provider="mock", agent_llm_provider="mock",
        groq_api_key="",
    )
    base.update(overrides)
    return Settings(**base)


def test_production_requires_groq_api_key_when_groq_stt_selected():
    settings = _production_settings(stt_provider="groq")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        settings.validate_for_production()


def test_production_requires_groq_api_key_when_groq_tts_selected():
    settings = _production_settings(tts_provider="groq")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        settings.validate_for_production()


def test_production_requires_groq_api_key_when_groq_llm_selected():
    settings = _production_settings(agent_llm_provider="groq")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        settings.validate_for_production()


def test_production_passes_with_groq_stt_and_llm_and_api_key():
    settings = _production_settings(stt_provider="groq", agent_llm_provider="groq", groq_api_key="k")
    settings.validate_for_production()  # must not raise


def test_production_passes_with_default_mock_providers():
    settings = _production_settings()
    settings.validate_for_production()  # must not raise
