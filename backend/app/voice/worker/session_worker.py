"""Realtime voice worker session logic (Task 016).

One `RealtimeVoiceWorker` instance manages exactly one `VoiceSession`'s
LiveKit room for its whole lifetime: it performs speech recognition on
the student's published audio and drives the *existing*
`AgentOrchestrator` through `VoiceSessionService.record_event` - the
identical call the mock/phone channels already use in
app/voice/router.py, so there is no second admissions brain here - then
publishes the agent's synthesized speech back into the room.

Turn-taking/VAD is derived from LiveKit's own `active_speakers_changed`
room signal (translated by app/voice/worker/room_client.py into simple
`on_speaking_started`/`on_speaking_stopped` callbacks) rather than a
hand-rolled ML voice-activity model - the transport already computes
this, so duplicating it here would be unnecessary complexity.

This class depends only on the small `room_client_factory` duck-typed
interface (see room_client.py's `VoiceRoomClient`), never on
`livekit.rtc` directly, so it is fully unit-testable with an in-memory
fake room - no real LiveKit server is reachable in this environment
(see tests/test_voice_worker.py).

Known simplification: `VoiceSessionService` calls run synchronously on
the worker's own asyncio task rather than via `asyncio.to_thread` -
acceptable because one worker instance only ever drives one session's
turns sequentially; a deployment running many sessions per worker
process could move this to a thread without changing this class's
public behavior.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.colleges.context import CollegeContext, get_college_context
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_sessionmaker
from app.models.voice import VoiceSession
from app.services.voice import VoiceSessionService
from app.voice import state_machine
from app.voice.providers.factory import get_stt_provider
from app.voice.providers.livekit import mint_access_token, room_name_for
from app.voice.worker.pcm import wav_bytes_to_pcm16
from app.voice.worker.room_client import VoiceRoomClient

logger = logging.getLogger("app.voice.worker")

_ENDED_STATUSES = ("completed", "failed")


class RealtimeVoiceWorker:
    def __init__(
        self,
        session_id,
        *,
        session_factory: sessionmaker[Session] | None = None,
        room_client_factory: Callable[[str, str], object] | None = None,
    ):
        self.session_id = session_id
        self._session_factory = session_factory or get_sessionmaker()
        self._room_client_factory = room_client_factory or (lambda url, token: VoiceRoomClient(url, token))

        self._db: Session | None = None
        self._session: VoiceSession | None = None
        self._college: CollegeContext | None = None
        self._room_client = None
        self._student_identity: str | None = None

        self._done = asyncio.Event()
        self._utterance_buffer = bytearray()
        self._speaking_task: asyncio.Task | None = None
        self._speaking_stop: asyncio.Event | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._db = self._session_factory()
        try:
            self._session = self._db.get(VoiceSession, self.session_id)
            if self._session is None:
                logger.warning("voice.worker_session_not_found session_id=%s", self.session_id)
                return
            if self._session.status in _ENDED_STATUSES:
                return
            self._college = get_college_context(self._db, self._session.college_id)
            if self._college is None:
                logger.warning("voice.worker_college_not_found session_id=%s", self.session_id)
                return

            settings = get_settings()
            room = room_name_for(college_id=str(self._session.college_id), session_id=str(self._session.id))
            self._student_identity = f"student-{self._session.id}"
            token, _ = mint_access_token(
                api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret,
                identity=settings.livekit_worker_identity, room=room,
                ttl_seconds=settings.livekit_token_ttl_seconds,
            )
            self._room_client = self._room_client_factory(settings.livekit_url, token)
            self._room_client.on_track_subscribed(self._handle_track_subscribed)
            self._room_client.on_speaking_started(self._handle_speaking_started)
            self._room_client.on_speaking_stopped(self._handle_speaking_stopped)
            self._room_client.on_participant_disconnected(self._handle_participant_disconnected)
            self._room_client.on_disconnected(self._handle_room_disconnected)

            await self._room_client.connect()
            logger.info("voice.worker_joined_room session_id=%s room=%s", self._session.id, room)
            await self._done.wait()
        except Exception:  # noqa: BLE001 - a crashed worker must still close out the session record
            logger.exception("voice.worker_crashed session_id=%s", self.session_id)
            self._end(reason="provider_failure")
        finally:
            if self._room_client is not None:
                try:
                    await self._room_client.disconnect()
                except Exception:  # noqa: BLE001 - best-effort teardown
                    logger.warning("voice.worker_disconnect_failed session_id=%s", self.session_id)
            if self._db is not None:
                self._db.close()

    def stop(self) -> None:
        """Lets an external caller (the dispatcher) request a clean stop,
        e.g. on process shutdown."""
        self._done.set()

    # ------------------------------------------------------------------
    # Room event handlers (called by room_client with a normalized,
    # duck-typed interface - see room_client.py's docstring)
    # ------------------------------------------------------------------

    async def _handle_track_subscribed(self, track, identity: str) -> None:
        if identity != self._student_identity:
            return  # never buffer audio from any participant but the student
        settings = get_settings()
        async for pcm_chunk in self._room_client.remote_audio_frames(
            track, sample_rate=settings.voice_worker_sample_rate, num_channels=settings.voice_worker_channels,
        ):
            if self._done.is_set():
                return
            self._utterance_buffer.extend(pcm_chunk)

    async def _handle_speaking_started(self, identity: str) -> None:
        if identity != self._student_identity:
            return
        if self._session is not None and state_machine.is_barge_in(self._session.turn_state, "speech_started"):
            await self._interrupt_agent_speech()
        self._utterance_buffer.clear()

    async def _handle_speaking_stopped(self, identity: str) -> None:
        if identity != self._student_identity or not self._utterance_buffer:
            return
        pcm_bytes = bytes(self._utterance_buffer)
        self._utterance_buffer.clear()
        await self._process_utterance(pcm_bytes)

    async def _handle_participant_disconnected(self, identity: str) -> None:
        if identity != self._student_identity:
            return
        self._record_event("client_disconnect")
        self._done.set()

    async def _handle_room_disconnected(self, reason=None) -> None:
        logger.info("voice.worker_room_disconnected session_id=%s reason=%s", self.session_id, reason)
        self._end(reason="provider_failure")

    # ------------------------------------------------------------------
    # Turn processing
    # ------------------------------------------------------------------

    async def _process_utterance(self, pcm_bytes: bytes) -> None:
        try:
            stt_result = get_stt_provider().recognize(pcm_bytes, language=self._session.language)
        except Exception:  # noqa: BLE001 - an STT failure must not crash the worker
            logger.exception("voice.worker_stt_failed session_id=%s", self.session_id)
            return
        if not stt_result.text:
            return

        result = self._record_event("final_transcript", text=stt_result.text)
        if result is None:
            return
        if result.get("status") in _ENDED_STATUSES:
            self._done.set()
            return

        audio_bytes = result.get("_tts_audio_bytes")
        if audio_bytes:
            await self._speak(audio_bytes)

    async def _speak(self, wav_bytes: bytes) -> None:
        try:
            pcm, sample_rate, channels = wav_bytes_to_pcm16(wav_bytes)
        except ValueError:
            logger.warning("voice.worker_tts_audio_unusable session_id=%s", self.session_id)
            return

        self._speaking_stop = asyncio.Event()
        self._speaking_task = asyncio.create_task(
            self._room_client.publish_audio(
                pcm, sample_rate=sample_rate, num_channels=channels, stop_event=self._speaking_stop,
            )
        )
        try:
            await self._speaking_task
        except asyncio.CancelledError:
            pass
        finally:
            self._speaking_task = None

    async def _interrupt_agent_speech(self) -> None:
        if self._speaking_stop is not None:
            self._speaking_stop.set()
        if self._speaking_task is not None:
            await self._speaking_task
        self._record_event("interruption")

    # ------------------------------------------------------------------
    # VoiceSessionService bridge - the ONLY place this class touches
    # persistence/orchestration, and it is the exact same service method
    # the REST event endpoint uses (app/voice/router.py::post_event).
    # ------------------------------------------------------------------

    def _record_event(self, event_type: str, *, text: str | None = None) -> dict | None:
        service = VoiceSessionService(self._db)
        try:
            result = service.record_event(self._session, event_type=event_type, text=text)
        except AppError:
            self._db.rollback()
            logger.warning("voice.worker_record_event_failed session_id=%s event_type=%s", self.session_id, event_type)
            return None
        self._db.commit()
        return result

    def _end(self, *, reason: str) -> None:
        if self._session is not None and self._db is not None:
            try:
                service = VoiceSessionService(self._db)
                service.end_session(self._session, reason=reason)
                self._db.commit()
            except Exception:  # noqa: BLE001 - never let cleanup itself crash the worker
                self._db.rollback()
                logger.exception("voice.worker_end_session_failed session_id=%s", self.session_id)
        self._done.set()
