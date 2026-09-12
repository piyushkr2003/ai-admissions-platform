"""Deterministic providers for local development and tests
(docs/voice.md section 61).

None of these talk to a real network service. They exist so the entire
voice session lifecycle - creation, events, barge-in, webhooks - can be
exercised deterministically without paid provider credentials. Wire a
real vendor SDK behind the same interfaces in app/voice/providers/ and
select it via VOICE_*_PROVIDER settings; no business logic changes.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from app.voice.providers.base import (
    InboundCallEvent,
    RealtimeTransportProvider,
    STTProvider,
    STTResult,
    TTSProvider,
    TTSResult,
    TelephonyProvider,
    TransportCredentials,
)

_WORDS_PER_MINUTE_SPOKEN = 150  # rough spoken-word rate, used only to fake a duration


class MockSTTProvider(STTProvider):
    name = "mock"

    def recognize(self, audio_bytes: bytes, *, language: str | None = None) -> STTResult:
        """Decodes the "audio" as literal UTF-8 text. Real providers
        receive actual audio frames; the mock lets tests drive a
        deterministic transcript without an audio pipeline."""
        try:
            text = audio_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = ""
        if not text:
            return STTResult(text="", is_final=True, confidence=0.0, language=language)
        return STTResult(text=text, is_final=True, confidence=0.99, language=language)


class MockTTSProvider(TTSProvider):
    name = "mock"

    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        word_count = max(1, len(text.split()))
        duration_ms = int(word_count / _WORDS_PER_MINUTE_SPOKEN * 60_000)
        ref = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return TTSResult(audio_url=f"mock://tts/{ref}", audio_bytes=None, duration_ms=duration_ms, provider_ref=ref)

    def cancel(self, provider_ref: str) -> None:
        return None


class MockTransportProvider(RealtimeTransportProvider):
    name = "mock"

    def create_session(self, *, session_id: str, college_id: str, metadata: dict) -> TransportCredentials:
        provider_session_id = f"mock-transport-{uuid.uuid4().hex[:12]}"
        token = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        return TransportCredentials(
            provider_session_id=provider_session_id, connection_token=token,
            expires_at=expires_at, ice_servers=[],
        )

    def close_session(self, provider_session_id: str) -> None:
        return None


class SharedSecretTelephonyProvider(TelephonyProvider):
    """Generic HMAC-signature-verified webhook adapter. Most real
    telephony providers (Twilio, Exotel, etc.) sign webhooks with some
    shared-secret scheme; this represents that pattern without binding
    to one vendor. Swap for a vendor-specific adapter when one is
    selected, behind the same TelephonyProvider interface."""

    name = "mock"

    def __init__(self, secret: str):
        self._secret = secret

    def verify_webhook(self, *, headers: dict, raw_body: bytes) -> bool:
        if not self._secret:
            # Never pretend an unconfigured webhook is authenticated.
            return False
        provided = headers.get("x-voice-signature") or headers.get("X-Voice-Signature")
        if not provided:
            return False
        expected = hmac.new(self._secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(provided, expected)

    def parse_inbound_payload(self, payload: dict) -> InboundCallEvent:
        return InboundCallEvent(
            call_id=str(payload.get("call_id") or ""),
            from_number=payload.get("from_number"),
            to_number=payload.get("to_number"),
            event_type=str(payload.get("event_type") or ""),
            text=payload.get("text"),
            audio_base64=payload.get("audio_base64"),
            language=payload.get("language"),
        )
