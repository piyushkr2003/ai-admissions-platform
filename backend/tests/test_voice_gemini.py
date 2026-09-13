"""Task 017 - real Gemini STT/TTS provider adapters.

Covers request construction, response parsing, timeout/HTTP-error/
malformed-response/safety(no-candidates) handling, empty/invalid-audio
safety, language handling, provider-factory selection/fail-closed
behavior, production fail-closed validation, no-secret-logging, and a
full realtime-worker turn (audio -> STT -> AgentOrchestrator -> TTS ->
LiveKit-style audio publish) with the Gemini adapters selected. No real
network call is made anywhere in this file - `urllib.request.urlopen` is
monkeypatched throughout, exactly like tests/test_llm_provider.py does
for the sibling Gemini LLM adapter. A real-API smoke test (never run by
pytest) lives separately in scripts/smoke_test_gemini_voice.py.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import wave
from io import BytesIO

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.errors import ResourceUnavailableError
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.conversations import Message
from app.voice.providers.factory import get_stt_provider, get_tts_provider
from app.voice.providers.gemini import GeminiSTTProvider, GeminiTTSProvider
from app.voice.providers.mock import MockSTTProvider, MockTTSProvider
from app.voice.worker.pcm import pcm16_to_wav_bytes

FAKE_KEY = "goog-super-secret-value"


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sample_pcm16(num_samples: int = 400) -> bytes:
    return bytes(range(256)) * (num_samples // 256 + 1)


def _stt_response(text: str) -> _FakeHTTPResponse:
    return _FakeHTTPResponse(
        {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}
    )


def _tts_response(pcm_bytes: bytes, *, rate: int = 24000) -> _FakeHTTPResponse:
    return _FakeHTTPResponse(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": f"audio/L16;codec=pcm;rate={rate}",
                                    "data": base64.b64encode(pcm_bytes).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ],
            "modelVersion": "gemini-2.5-flash-preview-tts",
        }
    )


# ---------------------------------------------------------------------------
# GeminiSTTProvider - construction / request / response
# ---------------------------------------------------------------------------

def test_stt_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GeminiSTTProvider(api_key="", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)


def test_stt_recognize_returns_empty_result_for_empty_audio_without_network_call(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("must not call the network for empty audio")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    result = provider.recognize(b"", language="en")
    assert result.text == ""
    assert result.language == "en"


def test_stt_recognize_handles_invalid_audio_safely_without_raising(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("must not call the network when raw audio cannot be wrapped")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    # num_channels=0 makes the WAV writer reject the buffer (wave.Error),
    # exercising the "invalid audio" safety path without a real bad payload.
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=0)
    result = provider.recognize(_sample_pcm16(), language="en")
    assert result.text == ""


def test_stt_recognize_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _stt_response("What is the fee for B.Tech CSE?")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="gemini-3.6-flash", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)

    result = provider.recognize(_sample_pcm16(), language="hinglish")

    assert result.text == "What is the fee for B.Tech CSE?"
    assert result.language == "hinglish"
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == FAKE_KEY
    assert FAKE_KEY not in captured["url"]
    assert captured["timeout"] == 5

    parts = captured["body"]["contents"][0]["parts"]
    assert "hinglish" in parts[0]["text"]
    assert parts[1]["inlineData"]["mimeType"] == "audio/wav"
    # The transmitted audio must be a real, self-describing WAV (not a bare PCM dump).
    wav_bytes = base64.b64decode(parts[1]["inlineData"]["data"])
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        assert wav_file.getnchannels() == 1


def test_stt_recognize_passes_through_an_already_wav_encoded_buffer(monkeypatch):
    captured = {}
    wav_bytes = pcm16_to_wav_bytes(_sample_pcm16(), sample_rate=48000, num_channels=2)

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _stt_response("hello")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    provider.recognize(wav_bytes, language=None)

    sent_wav = base64.b64decode(captured["body"]["contents"][0]["parts"][1]["inlineData"]["data"])
    assert sent_wav == wav_bytes  # passed through untouched, not re-wrapped at the provider's own default rate


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_stt_recognize_includes_language_hint_in_prompt(monkeypatch, language):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _stt_response("ok")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    provider.recognize(_sample_pcm16(), language=language)
    assert language in captured["body"]["contents"][0]["parts"][0]["text"]


def test_stt_recognize_returns_empty_text_when_gemini_hears_no_speech(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeHTTPResponse(
            {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]}
        ),
    )
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    result = provider.recognize(_sample_pcm16(), language="en")
    assert result.text == ""


def test_stt_recognize_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16())


def test_stt_recognize_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16())


def test_stt_recognize_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16())


def test_stt_recognize_raises_when_no_candidates_returned(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _FakeHTTPResponse({"candidates": []}))
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with pytest.raises(ResourceUnavailableError):
        provider.recognize(_sample_pcm16())


def test_stt_recognize_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiSTTProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, sample_rate=16000, num_channels=1)
    with caplog.at_level(logging.DEBUG, logger="app.voice.gemini"):
        with pytest.raises(ResourceUnavailableError):
            provider.recognize(_sample_pcm16())
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_KEY not in logged_text


# ---------------------------------------------------------------------------
# GeminiTTSProvider - construction / request / response
# ---------------------------------------------------------------------------

def test_tts_provider_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GeminiTTSProvider(api_key="", model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")


def test_tts_provider_constructor_requires_voice_name():
    with pytest.raises(ValueError):
        GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="")


def test_tts_synthesize_raises_on_empty_text():
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("   ")


def test_tts_synthesize_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}
    pcm_bytes = _sample_pcm16()

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _tts_response(pcm_bytes, rate=24000)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="gemini-2.5-flash-preview-tts", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")

    result = provider.synthesize("Your tuition fee is one lakh fifty thousand rupees.", language="en")

    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
    assert captured["headers"]["x-goog-api-key"] == FAKE_KEY
    assert FAKE_KEY not in captured["url"]
    assert captured["body"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert captured["body"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert captured["timeout"] == 5

    assert result.audio_url is None
    assert result.provider_ref
    with wave.open(BytesIO(result.audio_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.readframes(wav_file.getnframes()) == pcm_bytes
    assert result.duration_ms == int(len(pcm_bytes) / 2 / 24000 * 1000)


def test_tts_synthesize_honors_voice_id_override(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _tts_response(_sample_pcm16())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    provider.synthesize("hello", voice_id="Puck")
    assert captured["body"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"


def test_tts_synthesize_raises_on_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_raises_on_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_raises_on_malformed_response(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _BadResponse({}))
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_raises_when_no_candidates_returned(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _FakeHTTPResponse({"candidates": []}))
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_raises_when_response_has_no_audio_data(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeHTTPResponse(
            {"candidates": [{"content": {"parts": [{"text": "I can't say that."}]}, "finishReason": "SAFETY"}]}
        ),
    )
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with pytest.raises(ResourceUnavailableError):
        provider.synthesize("hello")


def test_tts_synthesize_never_logs_the_api_key(monkeypatch, caplog):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    with caplog.at_level(logging.DEBUG, logger="app.voice.gemini"):
        with pytest.raises(ResourceUnavailableError):
            provider.synthesize("hello")
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_KEY not in logged_text


def test_tts_cancel_is_a_best_effort_no_op():
    provider = GeminiTTSProvider(api_key=FAKE_KEY, model="m", base_url="https://generativelanguage.googleapis.com", timeout_seconds=5, voice_name="Kore")
    provider.cancel("some-ref")  # must not raise


# ---------------------------------------------------------------------------
# Provider factory selection / fail-closed
# ---------------------------------------------------------------------------

def test_factory_still_returns_mock_by_default():
    assert isinstance(get_stt_provider(), MockSTTProvider)
    assert isinstance(get_tts_provider(), MockTTSProvider)


def test_stt_factory_fails_closed_when_gemini_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_stt_provider()


def test_stt_factory_returns_gemini_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    assert isinstance(get_stt_provider(), GeminiSTTProvider)


def test_tts_factory_fails_closed_when_gemini_selected_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_tts_provider()


def test_tts_factory_returns_gemini_provider_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    assert isinstance(get_tts_provider(), GeminiTTSProvider)


# ---------------------------------------------------------------------------
# Production fail-closed validation
# ---------------------------------------------------------------------------

def _production_settings(**overrides) -> Settings:
    base = dict(
        app_env="production", app_debug=False, jwt_secret_key="a" * 40,
        cors_allowed_origins="https://admissions.example.edu",
        google_api_key="",
    )
    base.update(overrides)
    return Settings(**base)


def test_production_requires_google_api_key_when_gemini_stt_selected():
    settings = _production_settings(stt_provider="gemini")
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        settings.validate_for_production()


def test_production_requires_google_api_key_when_gemini_tts_selected():
    settings = _production_settings(tts_provider="gemini")
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        settings.validate_for_production()


def test_production_passes_with_gemini_stt_and_tts_and_api_key():
    settings = _production_settings(stt_provider="gemini", tts_provider="gemini", google_api_key="k")
    settings.validate_for_production()  # must not raise


def test_production_passes_with_default_mock_providers():
    settings = _production_settings()
    settings.validate_for_production()  # must not raise


# ---------------------------------------------------------------------------
# Realtime worker integration: audio -> STT -> orchestrator -> TTS -> publish
# ---------------------------------------------------------------------------

class FakeRoomClient:
    """Minimal duck-type stand-in for app/voice/worker/room_client.py's
    VoiceRoomClient - see tests/test_voice_worker.py's identical fixture
    for the full documented contract this mirrors."""

    def __init__(self):
        self.published: list[bytes] = []
        self.audio_frames_to_yield: list[bytes] = []
        self._on_track_subscribed = None
        self._on_speaking_started = None
        self._on_speaking_stopped = None
        self._on_participant_disconnected = None
        self._on_disconnected = None

    def on_track_subscribed(self, callback):
        self._on_track_subscribed = callback

    def on_speaking_started(self, callback):
        self._on_speaking_started = callback

    def on_speaking_stopped(self, callback):
        self._on_speaking_stopped = callback

    def on_participant_disconnected(self, callback):
        self._on_participant_disconnected = callback

    def on_disconnected(self, callback):
        self._on_disconnected = callback

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def remote_audio_frames(self, track, *, sample_rate, num_channels):
        for chunk in self.audio_frames_to_yield:
            yield chunk

    async def publish_audio(self, pcm_bytes, *, sample_rate, num_channels, frame_ms=20, stop_event=None):
        self.published.append(pcm_bytes)
        return True


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _make_web_session(db, college):
    from app.colleges.context import get_college_context
    from app.services.voice import VoiceSessionService

    context = get_college_context(db, college.id)
    service = VoiceSessionService(db)
    session, conversation, _credentials, _greeting = service.create_web_session(context)
    db.commit()
    return session, conversation, context


def _bootstrap_worker(db, session, context, fake_room: FakeRoomClient):
    from app.voice.worker.session_worker import RealtimeVoiceWorker

    worker = RealtimeVoiceWorker(session.id, session_factory=lambda: db, room_client_factory=lambda url, token: fake_room)
    worker._db = db
    worker._session = session
    worker._college = context
    worker._room_client = fake_room
    worker._student_identity = f"student-{session.id}"
    return worker


async def _speak_utterance(worker, fake_room: FakeRoomClient, raw_audio: bytes) -> None:
    fake_room.audio_frames_to_yield = [raw_audio]
    await worker._handle_track_subscribed(object(), worker._student_identity)
    await worker._handle_speaking_stopped(worker._student_identity)


def test_worker_drives_a_full_turn_through_the_real_gemini_adapters(db, monkeypatch):
    """No real network call is made - `urllib.request.urlopen` is faked to
    distinguish the STT request (audio inlineData) from the TTS request
    (responseModalities=AUDIO) by inspecting the outgoing payload shape,
    proving the worker's STT -> AgentOrchestrator -> TTS -> publish
    pipeline (app/voice/worker/session_worker.py) is completely unchanged
    by which provider the factory returns."""
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "gemini")
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")

    tts_pcm = _sample_pcm16(200)

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        if body.get("generationConfig", {}).get("responseModalities"):
            return _tts_response(tts_pcm)
        return _stt_response("What is the fee for B.Tech CSE?")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    session, conversation, context = _make_web_session(db, nova)
    fake_room = FakeRoomClient()
    worker = _bootstrap_worker(db, session, context, fake_room)

    asyncio.run(_speak_utterance(worker, fake_room, _sample_pcm16()))

    messages = db.execute(
        select(Message).where(Message.conversation_id == conversation.id, Message.sender_type == "ai")
    ).scalars().all()
    assert messages, "the agent should have replied"
    last_reply = messages[-1]
    assert "fee" in last_reply.content.lower() or "tuition" in last_reply.content.lower()
    assert last_reply.tool_result and "get_fee_structure" in last_reply.tool_result.get("tools_used", [])

    assert fake_room.published, "the worker must publish the Gemini-synthesized speech back into the room"
    assert all(len(chunk) > 0 for chunk in fake_room.published)
