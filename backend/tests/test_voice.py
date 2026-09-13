"""Task 011 - voice agent (web + phone) tests.

Uses only the deterministic mock providers (app/voice/providers/mock.py)
- no external network calls, no paid provider credentials.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.errors import ResourceUnavailableError
from app.db.seed import seed_demo_data
from app.models.agent_config import AgentConfig
from app.models.college import College
from app.models.conversations import Conversation, Message
from app.models.counseling import Appointment
from app.models.leads import Lead
from app.models.support import SupportTicket
from app.models.voice import VoiceSession
from app.services.voice import VoiceSessionService, _playable_audio_url
from app.voice import state_machine
from app.voice.providers.base import TTSResult
from app.voice.providers.factory import get_stt_provider, get_telephony_provider, get_tts_provider
from app.voice.providers.mock import MockSTTProvider, MockTTSProvider

NOVA_ADMIN_EMAIL = "admin@nova-institute-of-technology.example.edu"
NOVA_ADMIN_PASSWORD = "NovaAdmin#2026"
NOVA_COUNSELOR_EMAIL = "counselor@nova-institute-of-technology.example.edu"
NOVA_COUNSELOR_PASSWORD = "NovaCounselor#2026"
AURORA_ADMIN_EMAIL = "admin@aurora-college-of-management.example.edu"
AURORA_ADMIN_PASSWORD = "AuroraAdmin#2026"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth_headers(client, email: str, password: str) -> dict:
    tokens = _login(client, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _create_web_session(client, college_id: str) -> dict:
    resp = client.post("/api/v1/voice/sessions", json={"college_id": college_id, "channel": "web_voice"})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Provider unit tests
# ---------------------------------------------------------------------------

def test_mock_stt_recognizes_utf8_text():
    result = MockSTTProvider().recognize("What is the CSE fee?".encode("utf-8"), language="en")
    assert result.text == "What is the CSE fee?"
    assert result.is_final is True
    assert result.confidence and result.confidence > 0


def test_mock_stt_empty_audio_returns_empty_result():
    result = MockSTTProvider().recognize(b"", language="en")
    assert result.text == ""
    assert result.confidence == 0.0


def test_playable_audio_url_prefers_a_real_provider_url_when_present():
    # Mock's "mock://tts/..." reference must pass through unchanged - the
    # frontend intentionally treats it as non-playable (a synthetic tone,
    # not real speech), so it must never be silently replaced.
    result = TTSResult(audio_url="mock://tts/abc123", audio_bytes=b"RIFF....", duration_ms=500)
    assert _playable_audio_url(result) == "mock://tts/abc123"


def test_playable_audio_url_builds_a_data_uri_from_real_audio_bytes():
    # A real provider (Gemini, or Task 023's local Whisper/Ollama/Piper
    # stack) returns audio_url=None alongside real bytes - this is what
    # makes that audio playable through the existing REST event response
    # with zero LiveKit/transport changes.
    result = TTSResult(audio_url=None, audio_bytes=b"RIFF-fake-wav-bytes", duration_ms=500)
    url = _playable_audio_url(result)
    assert url.startswith("data:audio/wav;base64,")
    assert base64.b64decode(url.removeprefix("data:audio/wav;base64,")) == b"RIFF-fake-wav-bytes"


def test_playable_audio_url_is_none_when_no_url_and_no_bytes():
    result = TTSResult(audio_url=None, audio_bytes=None, duration_ms=0)
    assert _playable_audio_url(result) is None


def test_mock_tts_synthesizes_with_positive_duration():
    result = MockTTSProvider().synthesize("Your appointment is confirmed for tomorrow at 3 PM.", language="en")
    assert result.audio_url and result.audio_url.startswith("mock://tts/")
    assert result.duration_ms > 0


def test_provider_factory_returns_mock_by_default():
    assert get_stt_provider().name == "mock"
    assert get_tts_provider().name == "mock"
    assert get_telephony_provider().name == "mock"


def test_provider_factory_rejects_unconfigured_named_provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "some-real-vendor")
    monkeypatch.setattr(settings, "tts_api_key", "")
    with pytest.raises(ResourceUnavailableError):
        get_tts_provider()


def test_telephony_provider_rejects_webhook_when_secret_unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telephony_webhook_secret", "")
    telephony = get_telephony_provider()
    assert telephony.verify_webhook(headers={}, raw_body=b"{}") is False


# ---------------------------------------------------------------------------
# Turn-taking state machine
# ---------------------------------------------------------------------------

def test_turn_state_transitions():
    assert state_machine.next_state(state_machine.IDLE, "speech_started") == state_machine.LISTENING
    assert state_machine.next_state(state_machine.LISTENING, "final_transcript") == state_machine.PROCESSING
    assert state_machine.next_state(state_machine.PROCESSING, "agent_response_ready") == state_machine.SPEAKING


def test_barge_in_detected_only_while_speaking():
    assert state_machine.is_barge_in(state_machine.SPEAKING, "speech_started") is True
    assert state_machine.is_barge_in(state_machine.LISTENING, "speech_started") is False


# ---------------------------------------------------------------------------
# Web voice: session creation
# ---------------------------------------------------------------------------

def test_create_web_session_returns_token_and_greeting(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    data = _create_web_session(client, str(nova.id))
    assert data["status"] == "connecting"
    assert data["connection_token"]
    assert data["greeting"]["text"]
    assert data["greeting"]["audio_url"].startswith("mock://tts/")

    session = db.get(VoiceSession, data["session_id"])
    assert session.channel == "web_voice"
    assert session.provider == "mock"

    messages = db.execute(select(Message).where(Message.conversation_id == session.conversation_id)).scalars().all()
    assert len(messages) == 1
    assert messages[0].sender_type == "ai"


def test_create_web_session_unknown_college_404(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.post(
        "/api/v1/voice/sessions",
        json={"college_id": "00000000-0000-0000-0000-000000000000", "channel": "web_voice"},
    )
    assert resp.status_code == 404


def test_create_web_session_disabled_returns_503(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    config = db.execute(select(AgentConfig).where(AgentConfig.college_id == nova.id)).scalar_one()
    config.voice_settings = {**(config.voice_settings or {}), "web_enabled": False}
    db.commit()

    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "web_voice"})
    assert resp.status_code == 503


def test_create_session_rejects_non_web_channel(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "phone_voice"})
    assert resp.status_code == 422


def test_get_session_status(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))

    resp = client.get(f"/api/v1/voice/sessions/{data['session_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "connecting"


# ---------------------------------------------------------------------------
# Web voice: events, turn-taking, transcripts
# ---------------------------------------------------------------------------

def test_final_transcript_invokes_agent_and_persists_transcript(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "Tell me about B.Tech CSE."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["response_text"]
    assert body["audio_url"]
    assert body["turn_state"] == "speaking"
    assert "agent_latency_ms" in body and body["agent_latency_ms"] >= 0

    session = db.get(VoiceSession, session_id)
    messages = db.execute(
        select(Message).where(Message.conversation_id == session.conversation_id).order_by(Message.created_at.asc())
    ).scalars().all()
    # greeting (ai) + student utterance + ai response
    assert [m.sender_type for m in messages] == ["ai", "student", "ai"]


def test_final_transcript_with_audio_base64_runs_server_side_stt_first(client, db):
    """Task 023 - the web channel now accepts audio_base64 exactly like
    the phone webhook already does, so a browser recording (local mode)
    can drive the same final_transcript path a real STT callback would,
    with no VoiceSessionService/AgentOrchestrator change."""
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    audio_base64 = base64.b64encode("Tell me about B.Tech CSE.".encode("utf-8")).decode("ascii")
    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "audio_base64": audio_base64},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert "get_course_details" in body["tools_used"]
    assert body["response_text"]


def test_final_transcript_rejects_invalid_audio_base64(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "audio_base64": "not-valid-base64!!!"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_partial_transcript_does_not_invoke_agent(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "partial_transcript", "text": "Tell me about"},
    )
    assert resp.status_code == 200
    assert "response_text" not in resp.json()["data"]

    session = db.get(VoiceSession, session_id)
    messages = db.execute(select(Message).where(Message.conversation_id == session.conversation_id)).scalars().all()
    assert len(messages) == 1  # only the greeting - no student/ai turn from a partial


def test_duplicate_event_id_replays_cached_result_without_reprocessing(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    first = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "What courses do you offer?", "event_id": "evt-1"},
    )
    second = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "What courses do you offer?", "event_id": "evt-1"},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"] == second.json()["data"]

    session = db.get(VoiceSession, session_id)
    messages = db.execute(select(Message).where(Message.conversation_id == session.conversation_id)).scalars().all()
    # greeting + exactly one student/ai pair, not two
    assert len(messages) == 3


def test_speech_started_while_speaking_triggers_interruption(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "What is the CSE fee?"},
    )
    session = db.get(VoiceSession, session_id)
    assert session.turn_state == "speaking"

    resp = client.post(f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "speech_started"})
    assert resp.status_code == 200
    assert resp.json()["data"]["interrupted"] is True
    db.refresh(session)
    assert session.turn_state == "listening"


def test_client_disconnect_ends_session_and_conversation(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    resp = client.post(f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "client_disconnect"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"

    session = db.get(VoiceSession, session_id)
    conversation = db.get(Conversation, session.conversation_id)
    assert session.status == "completed"
    assert session.duration_seconds is not None
    assert conversation.status == "completed"


def test_events_after_session_ended_are_rejected(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]
    client.post(f"/api/v1/voice/sessions/{session_id}/end", json={"reason": "completed"})

    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "final_transcript", "text": "Hello?"}
    )
    assert resp.status_code == 409


def test_end_session_is_idempotent(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    first = client.post(f"/api/v1/voice/sessions/{session_id}/end", json={})
    second = client.post(f"/api/v1/voice/sessions/{session_id}/end", json={})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["duration_seconds"] == second.json()["data"]["duration_seconds"]


def test_unknown_event_type_rejected(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    resp = client.post(
        f"/api/v1/voice/sessions/{data['session_id']}/events", json={"event_type": "not_a_real_event"}
    )
    assert resp.status_code == 422


def test_session_force_ends_after_max_duration(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session = db.get(VoiceSession, data["session_id"])
    session.started_at = datetime.now(timezone.utc) - timedelta(seconds=9999)
    db.commit()

    resp = client.post(
        f"/api/v1/voice/sessions/{data['session_id']}/events",
        json={"event_type": "final_transcript", "text": "Hello?"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"
    db.refresh(session)
    assert session.status == "completed"
    assert session.termination_reason == "max_duration_exceeded"


def test_session_ends_after_idle_timeout(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session = db.get(VoiceSession, data["session_id"])
    # Simulate silence: the session was touched long ago but is nowhere
    # near its max duration.
    stale = datetime.now(timezone.utc) - timedelta(seconds=300)
    session.updated_at = stale
    db.commit()

    resp = client.post(
        f"/api/v1/voice/sessions/{data['session_id']}/events",
        json={"event_type": "final_transcript", "text": "Hello?"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"
    db.refresh(session)
    assert session.status == "completed"
    assert session.termination_reason == "idle_timeout"


# ---------------------------------------------------------------------------
# Agent integration: real tools through the voice layer
# ---------------------------------------------------------------------------

def test_voice_appointment_booking_updates_lead_and_persists_appointment(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "I am interested in B.Tech CSE."},
    )
    offer_resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "I want to talk to a counselor."},
    )
    assert offer_resp.status_code == 200

    confirm_resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "yes"},
    )
    assert confirm_resp.status_code == 200
    response_text = confirm_resp.json()["data"]["response_text"].lower()

    session = db.get(VoiceSession, session_id)
    conversation = db.get(Conversation, session.conversation_id)
    state = AgentState.from_dict(conversation.state)
    appointments = db.execute(select(Appointment).where(Appointment.college_id == nova.id)).scalars().all()

    if appointments:
        assert "confirmed" in response_text
        assert state.lead_id is not None
        lead = db.get(Lead, uuid.UUID(state.lead_id))
        assert lead.lead_score > 0
    else:
        # Availability may be exhausted in rare CI timing; either way the
        # agent must never claim success without a persisted appointment.
        assert "confirmed" not in response_text


def test_voice_tool_failure_never_falsely_reported(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    availability_resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "I want to talk to a counselor."},
    )
    assert availability_resp.status_code == 200

    session = db.get(VoiceSession, session_id)
    conversation = db.get(Conversation, session.conversation_id)
    state = AgentState.from_dict(conversation.state)
    slot = state.pending_appointment_slot
    if slot is None:
        pytest.skip("no counselor slot was offered - nothing to race against")

    from app.models.student import Student

    other_student = Student(college_id=nova.id)
    db.add(other_student)
    db.flush()
    db.add(Appointment(
        college_id=nova.id, student_id=other_student.id, counselor_id=slot["counselor_id"],
        start_time=datetime.fromisoformat(slot["start_time"]),
        end_time=datetime.fromisoformat(slot["start_time"]) + timedelta(minutes=30),
        status="scheduled",
    ))
    db.commit()

    confirm_resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "final_transcript", "text": "yes"},
    )
    response_text = confirm_resp.json()["data"]["response_text"].lower()
    assert "confirmed" not in response_text


def test_voice_escalation_creates_ticket_and_marks_conversation(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    session_id = data["session_id"]

    resp = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "I want to speak to a human counselor."},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["escalation_required"] is True

    session = db.get(VoiceSession, session_id)
    conversation = db.get(Conversation, session.conversation_id)
    assert conversation.status == "escalated"
    ticket = db.execute(
        select(SupportTicket).where(SupportTicket.conversation_id == conversation.id)
    ).scalar_one()
    assert ticket.category == "counselor_escalation"


# ---------------------------------------------------------------------------
# Phone voice: telephony webhook
# ---------------------------------------------------------------------------

def _webhook(client, secret: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(secret, body)
    return client.post(
        "/api/v1/voice/telephony/mock/inbound", content=body,
        headers={"content-type": "application/json", "X-Voice-Signature": signature},
    )


def test_phone_call_started_creates_session_and_resolves_tenant(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")

    resp = _webhook(client, "test-secret", {
        "call_id": "call-001", "from_number": "+91-9000000001", "to_number": "+91-9800000099",
        "event_type": "call_started",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["created"] is True
    assert body["greeting"]["text"]

    session = db.execute(select(VoiceSession).where(VoiceSession.provider_call_id == "call-001")).scalar_one()
    assert session.channel == "phone_voice"
    assert session.caller_number == "+91-9000000001"


def test_phone_webhook_invalid_signature_rejected(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")

    body = json.dumps({"call_id": "call-002", "to_number": "+91-9800000099", "event_type": "call_started"}).encode()
    resp = client.post(
        "/api/v1/voice/telephony/mock/inbound", content=body,
        headers={"content-type": "application/json", "X-Voice-Signature": "deadbeef"},
    )
    assert resp.status_code == 401


def test_phone_webhook_missing_signature_rejected(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")

    body = json.dumps({"call_id": "call-003", "to_number": "+91-9800000099", "event_type": "call_started"}).encode()
    resp = client.post("/api/v1/voice/telephony/mock/inbound", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 401


def test_phone_unknown_number_returns_404(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")

    resp = _webhook(client, "test-secret", {
        "call_id": "call-004", "from_number": "+91-9000000002", "to_number": "+91-0000000000",
        "event_type": "call_started",
    })
    assert resp.status_code == 404


def test_phone_duplicate_call_started_is_idempotent(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")
    payload = {"call_id": "call-005", "from_number": "+91-9000000003", "to_number": "+91-9800000099", "event_type": "call_started"}

    first = _webhook(client, "test-secret", payload)
    second = _webhook(client, "test-secret", payload)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["session_id"] == second.json()["data"]["session_id"]
    assert second.json()["data"]["created"] is False

    count = db.execute(select(VoiceSession).where(VoiceSession.provider_call_id == "call-005")).scalars().all()
    assert len(count) == 1


def test_phone_speech_event_invokes_agent(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")
    _webhook(client, "test-secret", {
        "call_id": "call-006", "from_number": "+91-9000000004", "to_number": "+91-9800000099",
        "event_type": "call_started",
    })

    resp = _webhook(client, "test-secret", {
        "call_id": "call-006", "event_type": "speech", "text": "What courses do you offer?",
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["response_text"]


def test_phone_call_ended_ends_session_and_duplicate_is_safe(client, db, monkeypatch):
    seed_demo_data(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "telephony_webhook_secret", "test-secret")
    _webhook(client, "test-secret", {
        "call_id": "call-007", "from_number": "+91-9000000005", "to_number": "+91-9800000099",
        "event_type": "call_started",
    })

    first = _webhook(client, "test-secret", {"call_id": "call-007", "event_type": "call_ended"})
    second = _webhook(client, "test-secret", {"call_id": "call-007", "event_type": "call_ended"})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["status"] == "completed"
    assert second.json()["data"]["status"] == "completed"


# ---------------------------------------------------------------------------
# Staff administration: RBAC + tenant isolation
# ---------------------------------------------------------------------------

def test_staff_list_sessions_requires_authentication(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/voice/sessions")
    assert resp.status_code == 401


def test_staff_list_sessions_is_tenant_isolated(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    _create_web_session(client, str(nova.id))
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/voice/sessions", headers=headers)
    assert resp.status_code == 200
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids <= {str(nova.id)}


def test_spoofed_college_id_ignored_for_scoped_staff_list(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    _create_web_session(client, str(nova.id))
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get(f"/api/v1/voice/sessions?college_id={aurora.id}", headers=nova_headers)
    assert resp.status_code == 200
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids <= {str(nova.id)}


def test_admin_can_force_end_session(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(f"/api/v1/voice/sessions/{data['session_id']}/force-end", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"
    assert resp.json()["data"]["termination_reason"] == "staff_terminated"


def test_college_a_cannot_force_end_college_b_session(client, db):
    seed_demo_data(db)
    db.commit()
    aurora = _college(db, "aurora-college-of-management")
    config = db.execute(select(AgentConfig).where(AgentConfig.college_id == aurora.id)).scalar_one()
    config.voice_settings = {**(config.voice_settings or {}), "web_enabled": True}
    db.commit()
    data = _create_web_session(client, str(aurora.id))

    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.post(f"/api/v1/voice/sessions/{data['session_id']}/force-end", headers=nova_headers)
    assert resp.status_code == 404


def test_counselor_cannot_force_end_session(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    data = _create_web_session(client, str(nova.id))
    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    resp = client.post(f"/api/v1/voice/sessions/{data['session_id']}/force-end", headers=counselor_headers)
    assert resp.status_code == 403
