"""Twilio phone-voice adapter - minimum viable integration.

Covers TwiML generation, real Twilio request-signature validation,
mu-law/PCM turn-detection (VAD), the inbound-call webhook (creates the
VoiceSession, idempotent, signature-gated), and TwilioStreamSession's
connected/start/media/stop handling bridging into the *real*
VoiceSessionService/AgentOrchestrator/TTS pipeline - the same one every
other channel uses, exercised here with the deterministic mock STT/TTS
providers exactly like tests/test_voice.py already does for the phone
webhook and web channels. No real Twilio account/credentials and no
network calls anywhere in this file.
"""
from __future__ import annotations

import array
import base64
import math

from sqlalchemy import select

from app.core.config import get_settings
from app.db.seed import seed_demo_data
from app.models.college import College
from app.services.voice import VoiceSessionService
from app.voice.providers.mock import MockSTTProvider
from app.voice.providers.twilio import compute_twilio_signature, generate_twiml, verify_twilio_signature
from app.voice.twilio_stream import TwilioStreamSession, TwilioTurnDetector, build_media_message, frame_mulaw
from app.voice.worker.pcm import mulaw_to_pcm16, pcm16_to_mulaw


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _mulaw_frame(*, loud: bool) -> bytes:
    """One 20ms (160-sample) mu-law frame, either near-silent or a clear tone."""
    if not loud:
        samples = array.array("h", [0] * 160)
    else:
        samples = array.array("h", [int(9000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(160)])
    return pcm16_to_mulaw(samples.tobytes())


# ---------------------------------------------------------------------------
# TwiML generation
# ---------------------------------------------------------------------------

def test_generate_twiml_embeds_the_stream_url_in_a_connect_stream_verb():
    xml = generate_twiml("wss://example.com/api/v1/voice/twilio/stream")
    assert "<Connect>" in xml
    assert '<Stream url="wss://example.com/api/v1/voice/twilio/stream"/>' in xml
    assert xml.startswith("<?xml")
    assert "<Response>" in xml and "</Response>" in xml


def test_generate_twiml_escapes_special_characters_in_the_url():
    xml = generate_twiml("wss://example.com/stream?a=1&b=2")
    assert "&amp;" in xml
    assert "&b=2" not in xml  # raw unescaped & must not appear


# ---------------------------------------------------------------------------
# Twilio request-signature validation
# ---------------------------------------------------------------------------

def test_verify_twilio_signature_accepts_a_genuine_signature():
    auth_token = "test-auth-token-value"
    url = "https://example.com/api/v1/voice/twilio/incoming"
    params = {"CallSid": "CA123", "From": "+15550001111", "To": "+15550002222"}
    signature = compute_twilio_signature(auth_token, url, params)
    assert verify_twilio_signature(auth_token=auth_token, url=url, params=params, signature=signature)


def test_verify_twilio_signature_rejects_tampered_params():
    auth_token = "test-auth-token-value"
    url = "https://example.com/api/v1/voice/twilio/incoming"
    params = {"CallSid": "CA123", "From": "+15550001111", "To": "+15550002222"}
    signature = compute_twilio_signature(auth_token, url, params)
    tampered = {**params, "From": "+19995551234"}
    assert not verify_twilio_signature(auth_token=auth_token, url=url, params=tampered, signature=signature)


def test_verify_twilio_signature_rejects_wrong_auth_token():
    url = "https://example.com/api/v1/voice/twilio/incoming"
    params = {"CallSid": "CA123"}
    signature = compute_twilio_signature("correct-token", url, params)
    assert not verify_twilio_signature(auth_token="wrong-token", url=url, params=params, signature=signature)


def test_verify_twilio_signature_rejects_missing_signature():
    assert not verify_twilio_signature(auth_token="token", url="https://example.com/x", params={}, signature=None)


def test_verify_twilio_signature_rejects_when_auth_token_unconfigured():
    # Never pretend an unconfigured signature scheme authenticated the request.
    assert not verify_twilio_signature(auth_token="", url="https://example.com/x", params={}, signature="anything")


# ---------------------------------------------------------------------------
# TwilioTurnDetector (server-side VAD) - same "real speech observed, then
# silence" contract as the browser's lib/voice/simple-vad.ts.
# ---------------------------------------------------------------------------

def test_turn_detector_never_fires_on_pure_silence():
    detector = TwilioTurnDetector(silence_duration_ms=100)
    for _ in range(50):
        assert detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=False))) is None


def test_turn_detector_fires_after_speech_followed_by_silence():
    detector = TwilioTurnDetector(silence_duration_ms=100)  # 5 frames of silence at 20ms each
    assert detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=True))) is None
    for _ in range(4):
        assert detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=False))) is None
    result = detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=False)))
    assert result is not None
    assert len(result) == 6 * 320  # 6 frames fed, 160 samples * 2 bytes each


def test_turn_detector_resets_after_firing_so_a_new_turn_can_start():
    detector = TwilioTurnDetector(silence_duration_ms=40)
    detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=True)))
    first = None
    for _ in range(5):
        first = detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=False)))
        if first is not None:
            break
    assert first is not None
    # A second turn must be tracked independently - pure silence afterward must not refire.
    assert detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=False))) is None


def test_turn_detector_safety_cap_fires_even_without_silence():
    detector = TwilioTurnDetector(silence_duration_ms=10_000, max_turn_duration_ms=100)  # 5 frames
    results = [detector.feed(mulaw_to_pcm16(_mulaw_frame(loud=True))) for _ in range(5)]
    assert results[:-1] == [None, None, None, None]
    assert results[-1] is not None


# ---------------------------------------------------------------------------
# Outbound media message framing
# ---------------------------------------------------------------------------

def test_build_media_message_shape_and_base64_roundtrip():
    chunk = b"\xff\x00\x7f"
    message = build_media_message("MZ123", chunk)
    assert message["event"] == "media"
    assert message["streamSid"] == "MZ123"
    assert base64.b64decode(message["media"]["payload"]) == chunk


def test_frame_mulaw_splits_into_160_byte_frames_and_preserves_bytes():
    mulaw_bytes = bytes(range(256)) * 2  # 512 bytes
    frames = frame_mulaw(mulaw_bytes, frame_bytes=160)
    assert len(frames) == 4  # 160, 160, 160, 32
    assert b"".join(frames) == mulaw_bytes
    assert len(frames[-1]) == 32


def test_frame_mulaw_empty_input_returns_no_frames():
    assert frame_mulaw(b"") == []


# ---------------------------------------------------------------------------
# POST /voice/twilio/incoming - TwiML webhook
# ---------------------------------------------------------------------------

def test_twilio_incoming_returns_twiml_and_creates_a_voice_session(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_stream_public_url", "wss://example.com/api/v1/voice/twilio/stream")
    monkeypatch.setattr(settings, "twilio_auth_token", "")  # signature check skipped when unconfigured (dev/demo)
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post(
        "/api/v1/voice/twilio/incoming",
        data={"CallSid": "CA_test_001", "From": "+15550001111", "To": "+91-9800000099"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Stream" in resp.text
    assert "wss://example.com/api/v1/voice/twilio/stream" in resp.text

    session = VoiceSessionService(db).get_by_provider_call_or_404("twilio", "CA_test_001")
    assert session.college_id == nova.id
    assert session.channel == "phone_voice"
    assert session.status in ("created", "connecting", "active")


def test_twilio_incoming_is_idempotent_for_the_same_call_sid(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_stream_public_url", "wss://example.com/api/v1/voice/twilio/stream")
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    seed_demo_data(db)
    db.commit()

    body = {"CallSid": "CA_test_idempotent", "From": "+15550001111", "To": "+91-9800000099"}
    first = client.post("/api/v1/voice/twilio/incoming", data=body)
    second = client.post("/api/v1/voice/twilio/incoming", data=body)
    assert first.status_code == 200
    assert second.status_code == 200

    from app.models.voice import VoiceSession

    matches = db.execute(
        select(VoiceSession).where(VoiceSession.provider == "twilio", VoiceSession.provider_call_id == "CA_test_idempotent")
    ).scalars().all()
    assert len(matches) == 1


def test_twilio_incoming_requires_stream_public_url_to_be_configured(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_stream_public_url", "")
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    seed_demo_data(db)
    db.commit()

    resp = client.post(
        "/api/v1/voice/twilio/incoming",
        data={"CallSid": "CA_test_no_url", "From": "+15550001111", "To": "+91-9800000099"},
    )
    assert resp.status_code != 200


def test_twilio_incoming_rejects_an_invalid_signature_when_auth_token_is_configured(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_stream_public_url", "wss://example.com/api/v1/voice/twilio/stream")
    monkeypatch.setattr(settings, "twilio_auth_token", "a-real-auth-token")
    seed_demo_data(db)
    db.commit()

    resp = client.post(
        "/api/v1/voice/twilio/incoming",
        data={"CallSid": "CA_test_bad_sig", "From": "+15550001111", "To": "+91-9800000099"},
        headers={"X-Twilio-Signature": "not-a-real-signature"},
    )
    assert resp.status_code == 401


def test_twilio_incoming_accepts_a_genuinely_valid_signature(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_stream_public_url", "wss://example.com/api/v1/voice/twilio/stream")
    monkeypatch.setattr(settings, "twilio_auth_token", "a-real-auth-token")
    seed_demo_data(db)
    db.commit()

    params = {"CallSid": "CA_test_good_sig", "From": "+15550001111", "To": "+91-9800000099"}
    url = f"{client.base_url}/api/v1/voice/twilio/incoming"
    signature = compute_twilio_signature("a-real-auth-token", url, params)

    resp = client.post(
        "/api/v1/voice/twilio/incoming", data=params, headers={"X-Twilio-Signature": signature},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# TwilioStreamSession - the real STT -> AgentOrchestrator -> TTS bridge,
# tested by direct instantiation (session_factory injected to share the
# test's own transactional `db`, exactly like RealtimeVoiceWorker's tests
# do for the LiveKit worker - see tests/test_voice_worker.py) rather than
# through the actual WebSocket, which would use its own separate DB
# connection and never see this test's uncommitted seed data.
# ---------------------------------------------------------------------------

def _setup_twilio_call(db, *, call_sid: str) -> None:
    seed_demo_data(db)
    db.commit()
    VoiceSessionService(db).create_phone_session(
        provider_name="twilio", call_id=call_sid, from_number="+15550001111", to_number="+91-9800000099",
    )
    db.commit()


def _collect_sent(sent: list[dict]):
    async def _send(message: dict) -> None:
        sent.append(message)

    return _send


def test_stream_session_plays_the_greeting_on_start(db, monkeypatch):
    import asyncio

    monkeypatch.setattr(get_settings(), "stt_provider", "mock")
    monkeypatch.setattr(get_settings(), "tts_provider", "mock")
    _setup_twilio_call(db, call_sid="CA_stream_greeting")

    sent: list[dict] = []

    async def scenario():
        send = _collect_sent(sent)
        session = TwilioStreamSession(send=send, session_factory=lambda: db)
        await session.handle_message({"event": "connected"})
        await session.handle_message({"event": "start", "start": {"callSid": "CA_stream_greeting", "streamSid": "MZ1"}})

    asyncio.run(scenario())

    assert sent, "expected the greeting to be sent as one or more outbound media messages"
    assert all(m["event"] == "media" and m["streamSid"] == "MZ1" for m in sent)
    for m in sent:
        base64.b64decode(m["media"]["payload"])  # must always be valid base64 mu-law


def test_stream_session_processes_a_spoken_turn_through_the_real_orchestrator(db, monkeypatch):
    import asyncio

    monkeypatch.setattr(get_settings(), "stt_provider", "mock")
    monkeypatch.setattr(get_settings(), "tts_provider", "mock")
    monkeypatch.setattr(get_settings(), "agent_llm_provider", "mock")
    _setup_twilio_call(db, call_sid="CA_stream_turn")

    # MockSTTProvider decodes "audio" as literal UTF-8 text (see its own
    # docstring) - the Twilio bridge always wraps PCM into a real WAV
    # container first (matching what a real STT vendor needs), so this
    # monkeypatch swaps in a fixed transcript for this one call the same
    # way tests/test_voice_worker.py already does for the LiveKit worker.
    def fake_recognize(self, audio_bytes, *, language=None):
        from app.voice.providers.base import STTResult

        return STTResult(text="What courses do you offer?", is_final=True, confidence=0.99, language=language)

    monkeypatch.setattr(MockSTTProvider, "recognize", fake_recognize)

    sent: list[dict] = []

    async def scenario():
        send = _collect_sent(sent)
        session = TwilioStreamSession(send=send, session_factory=lambda: db)
        await session.handle_message({"event": "start", "start": {"callSid": "CA_stream_turn", "streamSid": "MZ2"}})
        sent.clear()  # only care about the turn's own reply below, not the greeting

        for frame in (_mulaw_frame(loud=True), *[_mulaw_frame(loud=False) for _ in range(41)]):
            payload = base64.b64encode(frame).decode("ascii")
            await session.handle_message({"event": "media", "media": {"payload": payload}})

    asyncio.run(scenario())

    assert sent, "expected the agent's reply to be sent back as outbound media messages"
    assert all(m["event"] == "media" and m["streamSid"] == "MZ2" for m in sent)

    from app.models.voice import VoiceSession

    session_row = db.execute(
        select(VoiceSession).where(VoiceSession.provider == "twilio", VoiceSession.provider_call_id == "CA_stream_turn")
    ).scalar_one()
    assert session_row.status == "active"  # a normal turn must not end the call


def test_stream_session_stop_ends_the_voice_session(db, monkeypatch):
    import asyncio

    monkeypatch.setattr(get_settings(), "stt_provider", "mock")
    monkeypatch.setattr(get_settings(), "tts_provider", "mock")
    _setup_twilio_call(db, call_sid="CA_stream_stop")

    async def scenario():
        send = _collect_sent([])
        session = TwilioStreamSession(send=send, session_factory=lambda: db)
        await session.handle_message({"event": "start", "start": {"callSid": "CA_stream_stop", "streamSid": "MZ3"}})
        await session.handle_message({"event": "stop", "stop": {"callSid": "CA_stream_stop"}})

    asyncio.run(scenario())

    from app.models.voice import VoiceSession

    session_row = db.execute(
        select(VoiceSession).where(VoiceSession.provider == "twilio", VoiceSession.provider_call_id == "CA_stream_stop")
    ).scalar_one()
    assert session_row.status == "completed"
    assert session_row.termination_reason == "caller_hangup"


def test_stream_session_ignores_media_before_start_without_crashing(db):
    import asyncio

    async def scenario():
        send = _collect_sent([])
        session = TwilioStreamSession(send=send, session_factory=lambda: db)
        payload = base64.b64encode(_mulaw_frame(loud=True)).decode("ascii")
        await session.handle_message({"event": "media", "media": {"payload": payload}})  # no start yet

    asyncio.run(scenario())  # must not raise
