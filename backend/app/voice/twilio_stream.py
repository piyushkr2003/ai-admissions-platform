"""Twilio Media Streams WebSocket bridge (minimum viable phone integration).

Mirrors app/voice/worker/session_worker.py's RealtimeVoiceWorker pattern
(one instance per call, bridging real-time audio to the *existing*
VoiceSessionService/AgentOrchestrator/STT/TTS pipeline - no second
admissions brain, no changes to any of those) but for Twilio's Media
Streams protocol instead of LiveKit:

    Twilio phone call
          |
    TwiML <Connect><Stream> (app/voice/router.py::twilio_incoming)
          |
    This WebSocket (app/voice/router.py::twilio_stream)
          |  connected / start / media / stop messages
    TwilioTurnDetector           <- simple RMS-based VAD (app/voice/worker/pcm.py::rms_energy),
          |                         same "loud, then N ms silent" contract as the browser's
          |                         lib/voice/simple-vad.ts, just server-side and frame-counted
          |                         instead of wall-clock (Twilio delivers a media message every
          |                         exactly 20ms, so counting frames is simpler and more robust
          |                         than timing)
    mulaw_to_pcm16 -> WAV         <- app/voice/worker/pcm.py
          |
    STTProvider.recognize()       <- unchanged (Groq/mock/whichever STT_PROVIDER is configured)
          |
    VoiceSessionService.record_event()  <- the EXACT method every other channel already uses
          |
    AgentOrchestrator.handle_message()  <- unchanged
          |
    TTSProvider.synthesize()      <- unchanged
          |
    resample -> pcm16_to_mulaw -> framed "media" WebSocket messages
          |
    Twilio -> caller hears the agent

Message parsing/dispatch (`handle_message`) is deliberately decoupled from
the actual transport: it takes an already-decoded dict and an injected
`send` callback rather than a raw `WebSocket`, so the whole
connected/start/media/stop/turn-taking/audio-format logic is unit-testable
with a plain fake - see tests/test_voice_twilio.py. The real FastAPI route
(app/voice/router.py::twilio_stream) is a thin adapter: decode each
incoming WebSocket text frame as JSON, call `handle_message`, and pass
`websocket.send_json` as `send`.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.colleges.context import CollegeContext, get_college_context
from app.core.errors import AppError, NotFoundError, ResourceUnavailableError
from app.db.session import get_sessionmaker
from app.models.conversations import Conversation, Message
from app.models.voice import VoiceSession
from app.services.voice import VoiceSessionService
from app.voice.providers.factory import get_stt_provider, get_tts_provider
from app.voice.worker.pcm import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    pcm16_to_wav_bytes,
    resample_pcm16_mono,
    rms_energy,
    wav_bytes_to_pcm16,
)

logger = logging.getLogger("app.voice.twilio_stream")

_ENDED_STATUSES = ("completed", "failed")

# Twilio's Media Streams protocol delivers exactly one 20ms mu-law frame
# (160 bytes/samples @ 8kHz) per "media" message - both constants below
# are expressed in frame counts rather than wall-clock milliseconds for
# exactly that reason (simpler and more deterministic than timing).
_FRAME_MS = 20
_TWILIO_FRAME_BYTES = 160  # 20ms @ 8kHz mu-law, 1 byte/sample


class TwilioTurnDetector:
    """Minimal server-side voice-activity detector for inbound Twilio
    audio - same contract as the browser's lib/voice/simple-vad.ts (a
    turn ends only after real speech was observed, followed by
    `silence_duration_ms` of continuous quiet; pure silence never ends a
    turn), reimplemented frame-counted instead of timer-based since
    Twilio's own 20ms cadence already provides a reliable clock.
    `volume_threshold` is on the same 16-bit PCM RMS scale as
    app/voice/worker/pcm.py::rms_energy - tune here if real call audio
    proves noisier/quieter than this demo default."""

    def __init__(
        self, *, volume_threshold: float = 400.0, silence_duration_ms: int = 800, max_turn_duration_ms: int = 60_000,
    ):
        self._volume_threshold = volume_threshold
        self._silence_frames_needed = max(1, silence_duration_ms // _FRAME_MS)
        self._max_frames = max(1, max_turn_duration_ms // _FRAME_MS)
        self._buffer = bytearray()
        self._has_speech = False
        self._silent_frame_streak = 0
        self._frame_count = 0

    def feed(self, pcm16_frame: bytes) -> bytes | None:
        """Call once per inbound 20ms PCM16 frame. Returns the
        accumulated utterance (and resets) once a turn is judged
        complete; otherwise returns None."""
        self._buffer.extend(pcm16_frame)
        self._frame_count += 1
        if rms_energy(pcm16_frame) > self._volume_threshold:
            self._has_speech = True
            self._silent_frame_streak = 0
        else:
            self._silent_frame_streak += 1

        if self._has_speech and (
            self._silent_frame_streak >= self._silence_frames_needed or self._frame_count >= self._max_frames
        ):
            result = bytes(self._buffer)
            self.reset()
            return result
        return None

    def reset(self) -> None:
        self._buffer = bytearray()
        self._has_speech = False
        self._silent_frame_streak = 0
        self._frame_count = 0


def build_media_message(stream_sid: str, mulaw_chunk: bytes) -> dict:
    """One outbound Twilio Media Streams "media" message - raw mu-law
    audio, base64-encoded, no WAV header, per Twilio's documented wire
    format."""
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(mulaw_chunk).decode("ascii")},
    }


def frame_mulaw(mulaw_bytes: bytes, *, frame_bytes: int = _TWILIO_FRAME_BYTES) -> list[bytes]:
    """Splits raw mu-law audio into Twilio's expected ~20ms frame size for
    outbound "media" messages (Twilio accepts larger chunks in practice,
    but framing to its own cadence is the documented, spec-compliant
    shape)."""
    if frame_bytes <= 0 or not mulaw_bytes:
        return [mulaw_bytes] if mulaw_bytes else []
    return [mulaw_bytes[i : i + frame_bytes] for i in range(0, len(mulaw_bytes), frame_bytes)]


class TwilioStreamSession:
    """One instance per Twilio Media Stream WebSocket connection (i.e.
    per phone call). See module docstring for the full bridge."""

    def __init__(
        self,
        *,
        send: Callable[[dict], Awaitable[None]],
        session_factory: sessionmaker[Session] | None = None,
    ):
        self._send = send
        self._session_factory = session_factory or get_sessionmaker()
        self._turn_detector = TwilioTurnDetector()

        self._db: Session | None = None
        self._voice_session: VoiceSession | None = None
        self._college: CollegeContext | None = None
        self._stream_sid: str | None = None
        self._call_sid: str | None = None
        self._closed = False

    async def handle_message(self, message: dict) -> None:
        event = message.get("event")
        if event == "connected":
            logger.info("voice.twilio_stream_connected")
        elif event == "start":
            await self._handle_start(message)
        elif event == "media":
            await self._handle_media(message)
        elif event == "stop":
            await self._handle_stop()
        # "mark" and anything else: no handling needed for this minimum
        # integration - never an error, just ignored.

    async def close(self) -> None:
        """Called by the route on an unexpected WebSocket disconnect
        (browser/network drop, not a clean Twilio "stop" message) - same
        end-of-call bookkeeping, different trigger."""
        await self._handle_stop(reason="provider_failure")

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def _handle_start(self, message: dict) -> None:
        start = message.get("start") or {}
        self._stream_sid = message.get("streamSid") or start.get("streamSid")
        self._call_sid = start.get("callSid")
        if not self._call_sid:
            logger.warning("voice.twilio_stream_start_missing_call_sid")
            return

        self._db = self._session_factory()
        service = VoiceSessionService(self._db)
        try:
            self._voice_session = service.get_by_provider_call_or_404("twilio", self._call_sid)
        except NotFoundError:
            logger.warning("voice.twilio_stream_session_not_found call_sid=%s", self._call_sid)
            return
        self._college = get_college_context(self._db, self._voice_session.college_id)
        await self._play_greeting()

    async def _handle_media(self, message: dict) -> None:
        if self._closed or self._voice_session is None:
            return
        payload_b64 = (message.get("media") or {}).get("payload")
        if not payload_b64:
            return
        try:
            mulaw_chunk = base64.b64decode(payload_b64)
        except (ValueError, TypeError):
            return
        pcm_frame = mulaw_to_pcm16(mulaw_chunk)
        turn_pcm = self._turn_detector.feed(pcm_frame)
        if turn_pcm is not None:
            await self._process_turn(turn_pcm)

    async def _handle_stop(self, *, reason: str = "caller_hangup") -> None:
        if self._closed:
            return
        self._closed = True
        if self._voice_session is not None and self._db is not None:
            await asyncio.to_thread(self._end_session, reason)
        if self._db is not None:
            self._db.close()

    # ------------------------------------------------------------------
    # Turn processing - reuses the existing STT -> orchestrator -> TTS
    # pipeline exactly as every other voice channel does.
    # ------------------------------------------------------------------

    async def _process_turn(self, pcm_bytes: bytes) -> None:
        wav_bytes = pcm16_to_wav_bytes(pcm_bytes, sample_rate=8000, num_channels=1)
        stt_provider = get_stt_provider()
        try:
            stt_result = await asyncio.to_thread(
                stt_provider.recognize, wav_bytes, language=self._voice_session.language,
            )
        except ResourceUnavailableError:
            logger.warning("voice.twilio_stream_stt_failed call_sid=%s", self._call_sid)
            return
        if not stt_result.text:
            return

        result = await asyncio.to_thread(self._record_event, "final_transcript", stt_result.text)
        if result is None:
            return
        if result.get("status") in _ENDED_STATUSES:
            self._closed = True
            if self._db is not None:
                self._db.close()
            return

        audio_bytes = result.get("_tts_audio_bytes")
        if audio_bytes:
            await self._speak(audio_bytes)

    async def _play_greeting(self) -> None:
        if self._voice_session is None or self._db is None:
            return
        conversation = self._db.get(Conversation, self._voice_session.conversation_id)
        if conversation is None:
            return
        # The greeting text was already persisted as the conversation's
        # first message by VoiceSessionService._speak_greeting (called
        # from create_phone_session when the TwiML webhook created this
        # session, moments before Twilio opened this WebSocket) - reusing
        # it here means college-specific greeting_override/greeting_message
        # configuration is honored without duplicating that lookup logic.
        first_message = self._db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        greeting_text = first_message.content if first_message else None
        if not greeting_text:
            return
        tts_provider = get_tts_provider()
        try:
            tts_result = await asyncio.to_thread(
                tts_provider.synthesize, greeting_text, language=conversation.language or "en",
            )
        except ResourceUnavailableError:
            logger.warning("voice.twilio_stream_greeting_tts_failed call_sid=%s", self._call_sid)
            return
        if tts_result.audio_bytes:
            await self._speak(tts_result.audio_bytes)

    async def _speak(self, wav_bytes: bytes) -> None:
        try:
            pcm, sample_rate, _channels = wav_bytes_to_pcm16(wav_bytes)
        except ValueError:
            logger.warning("voice.twilio_stream_tts_audio_unusable call_sid=%s", self._call_sid)
            return
        pcm_8k = resample_pcm16_mono(pcm, src_rate=sample_rate, dst_rate=8000)
        mulaw_bytes = pcm16_to_mulaw(pcm_8k)
        for chunk in frame_mulaw(mulaw_bytes):
            await self._send(build_media_message(self._stream_sid or "", chunk))

    # ------------------------------------------------------------------
    # VoiceSessionService bridge - the ONLY place this class touches
    # persistence/orchestration, identical to how session_worker.py's
    # RealtimeVoiceWorker bridges LiveKit audio to the same service.
    # ------------------------------------------------------------------

    def _record_event(self, event_type: str, text: str | None = None) -> dict | None:
        service = VoiceSessionService(self._db)
        try:
            result = service.record_event(self._voice_session, event_type=event_type, text=text)
        except AppError:
            self._db.rollback()
            logger.warning("voice.twilio_stream_record_event_failed call_sid=%s event_type=%s", self._call_sid, event_type)
            return None
        self._db.commit()
        return result

    def _end_session(self, reason: str) -> None:
        service = VoiceSessionService(self._db)
        try:
            service.end_session(self._voice_session, reason=reason)
            self._db.commit()
        except Exception:  # noqa: BLE001 - never let call-end cleanup itself crash
            self._db.rollback()
            logger.exception("voice.twilio_stream_end_session_failed call_sid=%s", self._call_sid)
