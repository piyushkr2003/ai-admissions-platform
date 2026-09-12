"""Task 015 - realtime LiveKit voice transport.

Covers provider selection, production fail-closed behavior, token
generation/security, tenant isolation, and end-to-end session creation
using the real (but network-free) LiveKit JWT token format. No network
calls are made anywhere in this file - LIVEKIT_URL is never dialed, only
a JWT is minted and verified locally, exactly like the platform's own
JWT auth tests do for app/core/security.py.
"""
from __future__ import annotations

import logging

import jwt
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.errors import ResourceUnavailableError
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.voice import VoiceSession
from app.voice.providers.factory import get_transport_provider
from app.voice.providers.livekit import LiveKitTransportProvider, _room_name
from app.voice.providers.mock import MockTransportProvider

FAKE_URL = "wss://fake-project.livekit.cloud"
FAKE_KEY = "APItestkey123"
FAKE_SECRET = "test-secret-value-do-not-log-me-32b"


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _configure_livekit(monkeypatch, *, url=FAKE_URL, key=FAKE_KEY, secret=FAKE_SECRET):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_transport_provider", "livekit")
    monkeypatch.setattr(settings, "livekit_url", url)
    monkeypatch.setattr(settings, "livekit_api_key", key)
    monkeypatch.setattr(settings, "livekit_api_secret", secret)


# ---------------------------------------------------------------------------
# Provider selection / mode switching
# ---------------------------------------------------------------------------

def test_transport_provider_defaults_to_mock():
    assert isinstance(get_transport_provider(), MockTransportProvider)
    assert get_transport_provider().name == "mock"


def test_transport_factory_returns_livekit_when_fully_configured(monkeypatch):
    _configure_livekit(monkeypatch)
    provider = get_transport_provider()
    assert isinstance(provider, LiveKitTransportProvider)
    assert provider.name == "livekit"


@pytest.mark.parametrize(
    "missing",
    ["livekit_url", "livekit_api_key", "livekit_api_secret"],
)
def test_transport_factory_fails_closed_when_any_credential_missing(monkeypatch, missing):
    """Selecting livekit with a partial credential set must raise, never
    silently fall back to the mock provider or pretend to work."""
    _configure_livekit(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, missing, "")
    with pytest.raises(ResourceUnavailableError):
        get_transport_provider()


def test_livekit_provider_constructor_rejects_missing_credentials():
    with pytest.raises(ValueError):
        LiveKitTransportProvider(url=FAKE_URL, api_key="", api_secret=FAKE_SECRET, ttl_seconds=60)


# ---------------------------------------------------------------------------
# Production fail-closed behavior
# ---------------------------------------------------------------------------

def _production_settings(**overrides) -> Settings:
    base = dict(
        app_env="production",
        app_debug=False,
        jwt_secret_key="a" * 40,
        cors_allowed_origins="https://admissions.example.edu",
        voice_transport_provider="livekit",
    )
    base.update(overrides)
    return Settings(**base)


def test_production_requires_livekit_credentials_when_selected():
    settings = _production_settings()
    with pytest.raises(RuntimeError, match="LIVEKIT"):
        settings.validate_for_production()


def test_production_passes_with_full_livekit_credentials():
    settings = _production_settings(
        livekit_url=FAKE_URL, livekit_api_key=FAKE_KEY, livekit_api_secret=FAKE_SECRET,
    )
    settings.validate_for_production()  # must not raise


def test_production_does_not_require_livekit_credentials_for_mock_transport():
    settings = _production_settings(voice_transport_provider="mock")
    settings.validate_for_production()  # must not raise


# ---------------------------------------------------------------------------
# Token generation / security
# ---------------------------------------------------------------------------

def _decode(token: str, secret: str = FAKE_SECRET) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def test_livekit_token_is_valid_hs256_jwt_with_room_join_grant():
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=300)
    creds = provider.create_session(session_id="sess-1", college_id="college-a", metadata={})

    claims = _decode(creds.connection_token)
    assert claims["iss"] == FAKE_KEY
    assert claims["sub"] == "student-sess-1"
    assert claims["video"]["room"] == "college-college-a-voice-sess-1"
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["canSubscribe"] is True
    assert claims["exp"] > claims["nbf"]

    assert creds.server_url == FAKE_URL
    assert creds.provider_session_id == "college-college-a-voice-sess-1"
    assert creds.ice_servers == []


def test_livekit_token_cannot_be_verified_with_wrong_secret():
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=300)
    creds = provider.create_session(session_id="sess-1", college_id="college-a", metadata={})
    with pytest.raises(jwt.InvalidSignatureError):
        _decode(creds.connection_token, secret="wrong-secret")


def test_livekit_token_ttl_is_short_lived_and_configurable():
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=30)
    creds = provider.create_session(session_id="sess-1", college_id="college-a", metadata={})
    claims = _decode(creds.connection_token)
    assert 0 < (claims["exp"] - claims["nbf"]) <= 31


def test_livekit_secret_and_token_are_never_logged(caplog):
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=300)
    with caplog.at_level(logging.DEBUG, logger="app.voice.livekit"):
        creds = provider.create_session(session_id="sess-log-check", college_id="college-a", metadata={})
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_SECRET not in logged_text
    assert creds.connection_token not in logged_text


def test_livekit_close_session_is_best_effort_and_never_raises():
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=300)
    provider.close_session("some-room-name")  # must not raise


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

def test_room_name_embeds_college_id_so_sessions_never_collide_across_tenants():
    room_a = _room_name(college_id="college-a", session_id="sess-1")
    room_b = _room_name(college_id="college-b", session_id="sess-1")
    assert room_a != room_b
    assert "college-a" in room_a
    assert "college-b" in room_b


def test_token_for_one_college_session_is_scoped_to_that_colleges_room_only():
    provider = LiveKitTransportProvider(url=FAKE_URL, api_key=FAKE_KEY, api_secret=FAKE_SECRET, ttl_seconds=300)
    creds_a = provider.create_session(session_id="sess-shared-id", college_id="college-a", metadata={})
    creds_b = provider.create_session(session_id="sess-shared-id", college_id="college-b", metadata={})

    room_in_token_a = _decode(creds_a.connection_token)["video"]["room"]
    room_in_token_b = _decode(creds_b.connection_token)["video"]["room"]
    assert room_in_token_a != room_in_token_b
    assert "college-b" not in room_in_token_a
    assert "college-a" not in room_in_token_b


# ---------------------------------------------------------------------------
# End-to-end session creation via the API (integration)
# ---------------------------------------------------------------------------

def test_create_web_session_uses_livekit_when_configured(client, db, monkeypatch):
    _configure_livekit(monkeypatch)
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "web_voice"})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]

    assert data["provider"] == "livekit"
    assert data["server_url"] == FAKE_URL
    assert data["connection_token"]
    claims = _decode(data["connection_token"])
    assert claims["video"]["room"] == f"college-{nova.id}-voice-{data['session_id']}"

    session = db.get(VoiceSession, data["session_id"])
    assert session.provider == "livekit"


def test_create_web_session_fails_closed_without_livekit_credentials(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_transport_provider", "livekit")
    monkeypatch.setattr(settings, "livekit_url", "")
    monkeypatch.setattr(settings, "livekit_api_key", "")
    monkeypatch.setattr(settings, "livekit_api_secret", "")
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "web_voice"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "RESOURCE_UNAVAILABLE"

    remaining = db.execute(select(VoiceSession).where(VoiceSession.college_id == nova.id)).scalars().all()
    assert remaining == []  # the partially-created session/conversation must roll back, not leak


def test_livekit_session_reconnect_lifecycle_matches_mock_behavior(client, db, monkeypatch):
    """The transport provider only issues credentials - session lifecycle,
    turn-taking, and reconnect idempotency in app/services/voice.py must
    behave identically regardless of which transport is selected."""
    _configure_livekit(monkeypatch)
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "web_voice"})
    session_id = resp.json()["data"]["session_id"]

    disconnect = client.post(f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "client_disconnect"})
    assert disconnect.status_code == 200
    assert disconnect.json()["data"]["status"] == "completed"

    # A session that has already ended cannot be resurrected by reconnect.
    reconnect = client.post(f"/api/v1/voice/sessions/{session_id}/events", json={"event_type": "client_reconnect"})
    assert reconnect.status_code == 409


def test_livekit_final_transcript_still_drives_existing_agent_orchestrator(client, db, monkeypatch):
    """Guards against a second/duplicate agent path being introduced for
    the livekit transport - the same final_transcript -> AgentOrchestrator
    flow used by mock/phone channels must run unchanged."""
    _configure_livekit(monkeypatch)
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post("/api/v1/voice/sessions", json={"college_id": str(nova.id), "channel": "web_voice"})
    session_id = resp.json()["data"]["session_id"]

    turn = client.post(
        f"/api/v1/voice/sessions/{session_id}/events",
        json={"event_type": "final_transcript", "text": "What is the fee for B.Tech CSE?"},
    )
    assert turn.status_code == 200
    body = turn.json()["data"]
    assert "get_fee_structure" in body["tools_used"]
    assert body["response_text"]
