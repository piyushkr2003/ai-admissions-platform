"""Provider-neutral voice interfaces (docs/voice.md section 60).

The voice session layer (app/services/voice.py) depends only on these
abstractions, never on a specific vendor SDK. A real integration is
added by implementing one of these interfaces and wiring it into
app/voice/providers/factory.py - business logic never changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class STTResult:
    text: str
    is_final: bool
    confidence: float | None = None
    language: str | None = None


@dataclass
class TTSResult:
    audio_url: str | None
    audio_bytes: bytes | None
    duration_ms: int
    provider_ref: str | None = None


@dataclass
class TransportCredentials:
    provider_session_id: str
    connection_token: str
    expires_at: datetime
    ice_servers: list[dict] = field(default_factory=list)
    # Public transport endpoint the client connects to (e.g. a LiveKit
    # `wss://` URL). Not a secret - it identifies a server, not a
    # credential - but is None for transports (like the mock) that have
    # no separate connection endpoint of their own.
    server_url: str | None = None


@dataclass
class InboundCallEvent:
    """One normalized event parsed from a telephony provider's webhook
    payload - the provider adapter's job is to translate its own vendor
    schema into this shape."""

    call_id: str
    from_number: str | None
    to_number: str | None
    event_type: str  # "call_started" | "speech" | "call_ended"
    text: str | None = None
    audio_base64: str | None = None
    language: str | None = None


class STTProvider(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, audio_bytes: bytes, *, language: str | None = None) -> STTResult:
        """Server-side transcription of a raw audio chunk (used by the
        phone channel when the telephony provider forwards audio rather
        than its own transcript)."""
        raise NotImplementedError


class TTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, provider_ref: str) -> None:
        """Best-effort cancellation of in-flight synthesis/playback for
        barge-in - must never raise."""
        raise NotImplementedError


class RealtimeTransportProvider(ABC):
    """Abstraction over the real-time audio transport (WebRTC/LiveKit or
    equivalent) used by web voice."""

    name: str = "base"

    @abstractmethod
    def create_session(self, *, session_id: str, college_id: str, metadata: dict) -> TransportCredentials:
        raise NotImplementedError

    @abstractmethod
    def close_session(self, provider_session_id: str) -> None:
        raise NotImplementedError


class TelephonyProvider(ABC):
    name: str = "base"

    @abstractmethod
    def verify_webhook(self, *, headers: dict, raw_body: bytes) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse_inbound_payload(self, payload: dict) -> InboundCallEvent:
        raise NotImplementedError
