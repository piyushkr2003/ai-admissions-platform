"""Voice session lifecycle (docs/voice.md).

This is an adapter layer around the existing Task 006 agent, not a
second reasoning system: a final transcript is handed straight to
`AgentOrchestrator.handle_message`, which already owns intent
detection, RAG, every agent tool, lead/appointment/application/
escalation integration, and message persistence. This service is
responsible only for session lifecycle, turn-taking/barge-in state,
provider selection, and turning the orchestrator's text response into
speech.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.colleges.context import CollegeContext, get_college_context
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, RateLimitedError, ResourceUnavailableError, ValidationAppError
from app.models.agent_config import AgentConfig
from app.models.conversations import Conversation, Message
from app.models.voice import VoiceSession
from app.services.audit import record_audit
from app.voice import state_machine
from app.voice.providers.base import TransportCredentials
from app.voice.providers.factory import get_transport_provider, get_tts_provider

logger = logging.getLogger("app.voice")

DEFAULT_VOICE_SETTINGS = {
    "web_enabled": True,
    "phone_enabled": False,
    "default_language": None,  # falls back to the college's default_language
    "fallback_language": None,
    "voice_id": None,
    "greeting_override": None,
    "session_idle_timeout_seconds": None,  # falls back to global setting
    "max_session_duration_seconds": None,
    "recording_enabled": False,
    "transcript_enabled": True,
    "max_concurrent_sessions": None,
}

_ACTIVE_SESSION_STATUSES = ("created", "connecting", "active")
_KNOWN_EVENT_TYPES = (
    "speech_started", "partial_transcript", "final_transcript", "speech_stopped",
    "interruption", "client_disconnect", "client_reconnect",
)


def _voice_settings_for(config: AgentConfig | None) -> dict:
    merged = dict(DEFAULT_VOICE_SETTINGS)
    if config and config.voice_settings:
        merged.update(config.voice_settings)
    return merged


def _resolve_language(requested: str | None, settings: dict, college: CollegeContext) -> str:
    default = settings.get("default_language") or college.default_language
    fallback = settings.get("fallback_language") or default
    supported = set(college.supported_languages or [default])
    if requested:
        if requested in supported:
            return requested
        return fallback if fallback in supported else default
    return default


def _initial_conversation_state(requested: str | None, resolved_language: str) -> dict:
    """The conversation's starting AgentState (docs/voice.md "Language
    Selection"). When the caller explicitly requested a language (the
    voice console's language picker, or a future phone IVR selection),
    it is locked in as authoritative for the whole conversation -
    AgentOrchestrator.handle_message will never let per-turn
    detect_language() heuristics override it (this is required for "kn",
    which detect_language cannot recognize at all). When no language was
    requested (legacy/auto callers), state starts empty exactly as
    before, and per-turn auto-detection behaves unchanged."""
    if requested is None:
        return {}
    return {"language": resolved_language, "language_locked": True}


def _playable_audio_url(tts_result) -> str | None:
    """Returns a URL the browser's `<audio>` element can actually play.

    The mock provider's `audio_url` (`mock://tts/...`) is deliberately
    left untouched - it is a synthetic tone, not real speech, and the
    frontend intentionally treats it as non-playable (see
    frontend/features/voice/voice-console-helpers.ts). A real provider
    (Gemini, or the local Task 023 Whisper/Ollama/Piper stack) returns
    `audio_url=None` alongside real WAV bytes in `audio_bytes` - for
    those, build a `data:` URI so the exact same REST event response
    already consumed by the voice console (no LiveKit/transport changes)
    can play genuine synthesized speech without a separate file-serving
    endpoint."""
    if tts_result.audio_url:
        return tts_result.audio_url
    if tts_result.audio_bytes:
        return f"data:audio/wav;base64,{base64.b64encode(tts_result.audio_bytes).decode('ascii')}"
    return None


def _greeting_text(config: AgentConfig | None, college: CollegeContext) -> str:
    settings = _voice_settings_for(config)
    if settings.get("greeting_override"):
        return settings["greeting_override"]
    if config and config.greeting_message:
        return config.greeting_message
    return (
        f"Hello! Welcome to {college.name} admissions. "
        "I'm your AI admissions assistant. How can I help you today?"
    )


class VoiceSessionService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _agent_config(self, college_id: uuid.UUID) -> AgentConfig | None:
        return self.db.execute(select(AgentConfig).where(AgentConfig.college_id == college_id)).scalar_one_or_none()

    def _count_active_sessions(self, college_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(VoiceSession).where(
            VoiceSession.college_id == college_id, VoiceSession.status.in_(_ACTIVE_SESSION_STATUSES)
        )
        return self.db.execute(stmt).scalar_one()

    def _enforce_concurrency(self, college_id: uuid.UUID, settings: dict) -> None:
        limit = settings.get("max_concurrent_sessions") or get_settings().voice_max_concurrent_sessions_per_college
        if self._count_active_sessions(college_id) >= limit:
            raise RateLimitedError("Too many concurrent voice sessions for this college. Please try again shortly.")

    def _speak_greeting(self, session: VoiceSession, conversation: Conversation, config: AgentConfig | None, college: CollegeContext) -> dict:
        text = _greeting_text(config, college)
        self.db.add(Message(
            college_id=college.college_id, conversation_id=conversation.id,
            sender_type="ai", content=text,
        ))
        self.db.flush()

        settings = _voice_settings_for(config)
        voice_id = settings.get("voice_id") or (config.voice_id if config else None)
        tts_result = get_tts_provider().synthesize(text, language=conversation.language, voice_id=voice_id)
        return {"text": text, "audio_url": _playable_audio_url(tts_result), "audio_duration_ms": tts_result.duration_ms}

    # ------------------------------------------------------------------
    # Session creation
    # ------------------------------------------------------------------

    def create_web_session(
        self, college: CollegeContext, *, language: str | None = None,
    ) -> tuple[VoiceSession, Conversation, TransportCredentials, dict]:
        config = self._agent_config(college.college_id)
        settings = _voice_settings_for(config)
        if not settings.get("web_enabled", True):
            raise ResourceUnavailableError("Web voice is not enabled for this college.")
        self._enforce_concurrency(college.college_id, settings)

        lang = _resolve_language(language, settings, college)
        now = datetime.now(timezone.utc)
        conversation = Conversation(
            college_id=college.college_id, channel="web_voice", session_id=uuid.uuid4().hex,
            status="active", started_at=now, language=lang,
            state=_initial_conversation_state(language, lang),
        )
        self.db.add(conversation)
        self.db.flush()

        transport = get_transport_provider()
        session = VoiceSession(
            college_id=college.college_id, conversation_id=conversation.id, channel="web_voice",
            provider=transport.name, status="created", turn_state=state_machine.IDLE,
            language=lang, started_at=now,
        )
        self.db.add(session)
        self.db.flush()

        credentials = transport.create_session(
            session_id=str(session.id), college_id=str(college.college_id), metadata={"channel": "web_voice"},
        )
        session.provider_session_id = credentials.provider_session_id
        session.status = "connecting"
        self.db.flush()

        logger.info("voice.session_created session_id=%s college_id=%s channel=web_voice provider=%s", session.id, college.college_id, transport.name)
        record_audit(
            self.db, college_id=college.college_id, user_id=None, action="voice.session_created",
            entity_type="voice_session", entity_id=session.id, meta={"channel": "web_voice"},
        )

        greeting = self._speak_greeting(session, conversation, config, college)
        return session, conversation, credentials, greeting

    def create_phone_session(
        self, *, provider_name: str, call_id: str, from_number: str | None, to_number: str | None,
        language: str | None = None,
    ) -> tuple[VoiceSession, Conversation, dict | None, bool]:
        if not call_id:
            raise ValidationAppError("call_id is required.")

        existing = self.db.execute(
            select(VoiceSession).where(VoiceSession.provider == provider_name, VoiceSession.provider_call_id == call_id)
        ).scalar_one_or_none()
        if existing is not None:
            conversation = self.db.get(Conversation, existing.conversation_id)
            return existing, conversation, None, False

        if not to_number:
            raise NotFoundError("No college is configured for this phone number.")
        config = self.db.execute(select(AgentConfig).where(AgentConfig.voice_phone_number == to_number)).scalar_one_or_none()
        if config is None:
            raise NotFoundError("No college is configured for this phone number.")
        college = get_college_context(self.db, config.college_id)
        if college is None or not college.is_active:
            raise NotFoundError("This college is not currently available.")

        settings = _voice_settings_for(config)
        if not settings.get("phone_enabled", False):
            raise ResourceUnavailableError("Phone voice is not enabled for this college.")
        self._enforce_concurrency(college.college_id, settings)

        lang = _resolve_language(language, settings, college)
        now = datetime.now(timezone.utc)
        conversation = Conversation(
            college_id=college.college_id, channel="phone_voice", session_id=call_id,
            status="active", started_at=now, language=lang,
            state=_initial_conversation_state(language, lang),
        )
        self.db.add(conversation)
        self.db.flush()

        session = VoiceSession(
            college_id=college.college_id, conversation_id=conversation.id, channel="phone_voice",
            provider=provider_name, provider_call_id=call_id, status="active", turn_state=state_machine.IDLE,
            language=lang, caller_number=from_number, started_at=now, connected_at=now,
        )
        try:
            with self.db.begin_nested():
                self.db.add(session)
                self.db.flush()
        except IntegrityError:
            # A concurrent duplicate webhook created it first - idempotent replay.
            existing = self.db.execute(
                select(VoiceSession).where(VoiceSession.provider == provider_name, VoiceSession.provider_call_id == call_id)
            ).scalar_one()
            return existing, self.db.get(Conversation, existing.conversation_id), None, False

        logger.info(
            "voice.session_created session_id=%s college_id=%s channel=phone_voice provider=%s call_id=%s",
            session.id, college.college_id, provider_name, call_id,
        )
        record_audit(
            self.db, college_id=college.college_id, user_id=None, action="voice.session_created",
            entity_type="voice_session", entity_id=session.id, meta={"channel": "phone_voice"},
        )

        greeting = self._speak_greeting(session, conversation, config, college)
        return session, conversation, greeting, True

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_or_404(self, session_id: uuid.UUID, *, college_id: uuid.UUID | None = None) -> VoiceSession:
        session = self.db.get(VoiceSession, session_id)
        if session is None:
            raise NotFoundError("Voice session not found.")
        if college_id is not None and session.college_id != college_id:
            raise NotFoundError("Voice session not found.")
        return session

    def get_by_provider_call_or_404(self, provider_name: str, call_id: str) -> VoiceSession:
        session = self.db.execute(
            select(VoiceSession).where(VoiceSession.provider == provider_name, VoiceSession.provider_call_id == call_id)
        ).scalar_one_or_none()
        if session is None:
            raise NotFoundError("No voice session found for this call.")
        return session

    def list_sessions(
        self, college_id: uuid.UUID, *, channel: str | None = None, status: str | None = None,
        page: int = 1, page_size: int = 25,
    ) -> tuple[list[VoiceSession], int]:
        conditions = [VoiceSession.college_id == college_id]
        if channel:
            conditions.append(VoiceSession.channel == channel)
        if status:
            conditions.append(VoiceSession.status == status)
        total = self.db.execute(select(func.count()).select_from(VoiceSession).where(*conditions)).scalar_one()
        stmt = (
            select(VoiceSession).where(*conditions)
            .order_by(VoiceSession.created_at.desc(), VoiceSession.id.asc())
            .limit(page_size).offset((page - 1) * page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def record_event(
        self, session: VoiceSession, *, event_type: str, text: str | None = None,
        event_id: str | None = None,
    ) -> dict:
        if event_type not in _KNOWN_EVENT_TYPES:
            raise ValidationAppError(f"Unknown event_type: {event_type}")
        if session.status in ("completed", "failed"):
            raise ConflictError("This voice session has already ended.", details={"code": "VOICE_SESSION_ENDED"})

        if event_id and session.last_event_id == event_id:
            logger.info("voice.duplicate_event_ignored session_id=%s event_id=%s", session.id, event_id)
            return session.last_event_result or {"event_type": event_type, "duplicate": True}

        conversation = self.db.get(Conversation, session.conversation_id)
        college = get_college_context(self.db, session.college_id)
        if conversation is None or college is None:
            raise NotFoundError("Voice session context is no longer available.")

        settings = _voice_settings_for(self._agent_config(session.college_id))
        global_settings = get_settings()
        now = datetime.now(timezone.utc)

        max_duration = settings.get("max_session_duration_seconds") or global_settings.voice_session_max_duration_seconds
        if session.started_at and (now - session.started_at).total_seconds() > max_duration:
            self.end_session(session, conversation, reason="max_duration_exceeded")
            return {
                "event_type": event_type, "status": session.status,
                "response_text": "This session has reached its maximum allowed duration and has ended.",
            }

        # Idle-timeout: no infrastructure exists to proactively sweep silent
        # sessions in the background, so this is a lazy check applied to
        # whatever event next arrives - a session that never sends another
        # event after going idle simply stays "active" until staff force-end
        # it (known limitation).
        idle_timeout = settings.get("session_idle_timeout_seconds") or global_settings.voice_session_idle_timeout_seconds
        last_activity = session.updated_at or session.started_at
        if event_type != "client_reconnect" and last_activity and (now - last_activity).total_seconds() > idle_timeout:
            self.end_session(session, conversation, reason="idle_timeout")
            return {
                "event_type": event_type, "status": session.status,
                "response_text": "Are you still there? This session has ended due to inactivity.",
            }

        if event_type == "client_reconnect":
            # A session that has already ended is rejected by the status
            # guard above - reconnect only ever refreshes a still-open
            # (created/connecting/active) session after a silent network
            # drop, never resurrects a completed/failed one.
            session.status = "active"
            session.connected_at = session.connected_at or datetime.now(timezone.utc)
            self.db.flush()
            result = {"event_type": event_type, "status": session.status, "turn_state": session.turn_state}
            self._remember_event(session, event_id, result)
            return result

        if event_type == "client_disconnect":
            self.end_session(session, conversation, reason="client_disconnect")
            result = {"event_type": event_type, "status": session.status}
            self._remember_event(session, event_id, result)
            return result

        result: dict = {"event_type": event_type, "turn_state": session.turn_state}

        if state_machine.is_barge_in(session.turn_state, event_type):
            try:
                get_tts_provider().cancel(session.provider_session_id or str(session.id))
            except ResourceUnavailableError:
                pass  # cancellation is best-effort; never fail the interruption itself
            logger.info("voice.interruption session_id=%s", session.id)
            result["interrupted"] = True

        new_turn = state_machine.next_state(session.turn_state, event_type)
        if new_turn is not None:
            session.turn_state = new_turn

        if session.status in ("created", "connecting"):
            session.status = "active"
            session.connected_at = session.connected_at or datetime.now(timezone.utc)

        if event_type == "final_transcript":
            result.update(self._handle_final_transcript(session, conversation, college, text))

        self.db.flush()
        self._remember_event(session, event_id, result)
        return result

    def _remember_event(self, session: VoiceSession, event_id: str | None, result: dict) -> None:
        if event_id:
            session.last_event_id = event_id
            # Leading-underscore keys (e.g. _tts_audio_bytes) are internal-only
            # for a same-process caller and are never JSON-serializable /
            # never persisted - a replayed duplicate event simply won't
            # re-carry them, which is fine since nothing re-publishes audio
            # for an exact-retry anyway.
            session.last_event_result = {k: v for k, v in result.items() if not k.startswith("_")}
            self.db.flush()

    def _handle_final_transcript(
        self, session: VoiceSession, conversation: Conversation, college: CollegeContext, text: str | None,
    ) -> dict:
        """Partial transcripts never reach here - only a sufficiently
        final utterance is handed to the existing agent, per docs/voice.md
        section 14 ('do not book an appointment based on an incomplete
        partial transcript')."""
        if not text or not text.strip():
            return {"error": "empty_transcript", "response_text": "Sorry, I didn't catch that. Could you please repeat it?"}

        orchestrator = AgentOrchestrator(self.db, college)
        t0 = time.perf_counter()
        try:
            turn_result = orchestrator.handle_message(conversation, text.strip())
        except Exception:  # noqa: BLE001 - a broken turn must still produce a voice-safe reply
            logger.exception("voice.agent_turn_failed session_id=%s", session.id)
            session.turn_state = state_machine.IDLE
            return {
                "error": "agent_failure",
                "response_text": "I'm sorry, I'm having trouble processing that right now. "
                                  "I can try again, or I can connect this request to our admissions team.",
            }
        agent_latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info("voice.agent_latency session_id=%s latency_ms=%s", session.id, agent_latency_ms)

        settings = _voice_settings_for(self._agent_config(session.college_id))
        t1 = time.perf_counter()
        audio_bytes: bytes | None = None
        try:
            tts_result = get_tts_provider().synthesize(
                turn_result.response_text, language=conversation.language, voice_id=settings.get("voice_id"),
            )
            audio_url, audio_duration_ms, tts_error = _playable_audio_url(tts_result), tts_result.duration_ms, None
            audio_bytes = tts_result.audio_bytes
        except ResourceUnavailableError as exc:
            logger.warning("voice.tts_failed session_id=%s error=%s", session.id, exc.message)
            audio_url, audio_duration_ms, tts_error = None, 0, "tts_unavailable"
        tts_latency_ms = int((time.perf_counter() - t1) * 1000)
        logger.info("voice.tts_latency session_id=%s latency_ms=%s", session.id, tts_latency_ms)

        session.turn_state = state_machine.SPEAKING
        if session.language != conversation.language:
            session.language = conversation.language

        return {
            "response_text": turn_result.response_text,
            "audio_url": audio_url,
            "audio_duration_ms": audio_duration_ms,
            "tts_error": tts_error,
            "tools_used": turn_result.tools_used,
            "intents": turn_result.intents,
            "escalation_required": turn_result.escalation_required,
            "agent_latency_ms": agent_latency_ms,
            "tts_latency_ms": tts_latency_ms,
            "turn_state": session.turn_state,
            # Internal only - raw synthesized audio for a same-process caller
            # (the realtime voice worker, Task 016) that needs to publish it
            # into a LiveKit room. Never part of the public HTTP contract:
            # every JSON-facing call site must pop this key before enveloping
            # the result (see app/voice/router.py) since it is not
            # JSON-serializable and was never intended for a browser anyway.
            "_tts_audio_bytes": audio_bytes,
        }

    # ------------------------------------------------------------------
    # Termination
    # ------------------------------------------------------------------

    def end_session(
        self, session: VoiceSession, conversation: Conversation | None = None, *,
        reason: str = "completed", failure_reason: str | None = None,
    ) -> VoiceSession:
        if session.status in ("completed", "failed"):
            return session

        now = datetime.now(timezone.utc)
        session.status = "failed" if reason in ("error", "provider_failure") else "completed"
        session.ended_at = now
        session.termination_reason = reason
        if failure_reason:
            session.failure_reason = failure_reason
        if session.started_at:
            session.duration_seconds = int((now - session.started_at).total_seconds())
        self.db.flush()

        if conversation is None:
            conversation = self.db.get(Conversation, session.conversation_id)
        if conversation is not None and conversation.status == "active":
            conversation.status = "completed" if session.status == "completed" else "failed"
            conversation.ended_at = now
            if conversation.started_at:
                conversation.duration_seconds = int((now - conversation.started_at).total_seconds())
            self.db.flush()

        logger.info(
            "voice.session_ended session_id=%s status=%s reason=%s duration_s=%s",
            session.id, session.status, reason, session.duration_seconds,
        )
        record_audit(
            self.db, college_id=session.college_id, user_id=None, action="voice.session_ended",
            entity_type="voice_session", entity_id=session.id,
            meta={"reason": reason, "status": session.status},
        )
        return session
