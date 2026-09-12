"""Thin wrapper around `livekit.rtc` (Task 016).

Mirrors frontend/lib/voice/livekit-room.ts's role on the backend: the
realtime voice worker's own orchestration logic
(app/voice/worker/session_worker.py) depends only on this small,
duck-typed interface, never on `livekit.rtc` directly - no real LiveKit
server is reachable in this environment, so every worker-logic test
substitutes a fake object exposing the same methods (see
tests/test_voice_worker.py's `FakeRoomClient`) rather than exercising
this module itself.

This class also translates LiveKit's raw, low-level room events into
the simpler, session_worker-facing shape it needs: `track_subscribed`
(track, publication, participant) becomes `on_track_subscribed(track,
identity)` filtered to audio tracks, and `active_speakers_changed`
(a list of currently-speaking participants) becomes edge-triggered
`on_speaking_started(identity)` / `on_speaking_stopped(identity)` calls
- LiveKit's server already computes "who is speaking now" for every
room, so this reuses that as the VAD signal instead of a hand-rolled one.
"""
from __future__ import annotations

import array
import asyncio
import logging
from collections.abc import AsyncIterator, Callable

from livekit import rtc

from app.voice.worker.pcm import chunk_pcm16

logger = logging.getLogger("app.voice.worker.room")


class VoiceRoomClient:
    """One real LiveKit room connection for the agent (worker) participant."""

    def __init__(self, url: str, token: str):
        self._url = url
        self._token = token
        self._room = rtc.Room()
        self._audio_source: rtc.AudioSource | None = None
        self._speaking_identities: set[str] = set()

        self._on_track_subscribed: Callable | None = None
        self._on_speaking_started: Callable | None = None
        self._on_speaking_stopped: Callable | None = None
        self._on_participant_disconnected: Callable | None = None
        self._on_disconnected: Callable | None = None

    # ------------------------------------------------------------------
    # Handler registration (session_worker.py calls these once, before connect())
    # ------------------------------------------------------------------

    def on_track_subscribed(self, callback: Callable) -> None:
        self._on_track_subscribed = callback

    def on_speaking_started(self, callback: Callable) -> None:
        self._on_speaking_started = callback

    def on_speaking_stopped(self, callback: Callable) -> None:
        self._on_speaking_stopped = callback

    def on_participant_disconnected(self, callback: Callable) -> None:
        self._on_participant_disconnected = callback

    def on_disconnected(self, callback: Callable) -> None:
        self._on_disconnected = callback

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._room.on("track_subscribed", self._raw_track_subscribed)
        self._room.on("active_speakers_changed", self._raw_active_speakers_changed)
        self._room.on("participant_disconnected", self._raw_participant_disconnected)
        self._room.on("disconnected", self._raw_disconnected)
        await self._room.connect(self._url, self._token, options=rtc.RoomOptions(auto_subscribe=True))

    async def disconnect(self) -> None:
        await self._room.disconnect()

    # ------------------------------------------------------------------
    # Raw LiveKit event -> normalized callback translation
    # ------------------------------------------------------------------

    def _raw_track_subscribed(self, track, publication, participant) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO or self._on_track_subscribed is None:
            return
        asyncio.create_task(self._on_track_subscribed(track, participant.identity))

    def _raw_active_speakers_changed(self, speakers) -> None:
        current = {p.identity for p in speakers}
        started = current - self._speaking_identities
        stopped = self._speaking_identities - current
        self._speaking_identities = current
        for identity in started:
            if self._on_speaking_started is not None:
                asyncio.create_task(self._on_speaking_started(identity))
        for identity in stopped:
            if self._on_speaking_stopped is not None:
                asyncio.create_task(self._on_speaking_stopped(identity))

    def _raw_participant_disconnected(self, participant) -> None:
        if self._on_participant_disconnected is not None:
            asyncio.create_task(self._on_participant_disconnected(participant.identity))

    def _raw_disconnected(self, reason=None) -> None:
        if self._on_disconnected is not None:
            asyncio.create_task(self._on_disconnected(reason))

    # ------------------------------------------------------------------
    # Media I/O
    # ------------------------------------------------------------------

    async def remote_audio_frames(self, track, *, sample_rate: int, num_channels: int) -> AsyncIterator[bytes]:
        """Yields raw PCM16 bytes for each decoded frame of a remote
        (student) audio track."""
        stream = rtc.AudioStream.from_track(track=track, sample_rate=sample_rate, num_channels=num_channels)
        try:
            async for event in stream:
                yield bytes(event.frame.data)
        finally:
            await stream.aclose()

    async def publish_audio(
        self, pcm_bytes: bytes, *, sample_rate: int, num_channels: int, frame_ms: int = 20,
        stop_event: asyncio.Event | None = None,
    ) -> bool:
        """Publishes raw PCM16 audio into the room as the agent's speech,
        frame by frame. Returns True if playback completed, False if it
        was cut short by `stop_event` (barge-in)."""
        if self._audio_source is None:
            self._audio_source = rtc.AudioSource(sample_rate, num_channels)
            track = rtc.LocalAudioTrack.create_audio_track("agent-voice", self._audio_source)
            await self._room.local_participant.publish_track(track)

        samples_per_frame = int(sample_rate * frame_ms / 1000)
        for chunk in chunk_pcm16(pcm_bytes, sample_rate=sample_rate, num_channels=num_channels, frame_ms=frame_ms):
            if stop_event is not None and stop_event.is_set():
                return False
            frame = rtc.AudioFrame.create(sample_rate, num_channels, samples_per_frame)
            samples = array.array("h")
            samples.frombytes(chunk)
            frame.data[:] = samples
            await self._audio_source.capture_frame(frame)
        return True

    @property
    def local_identity(self) -> str:
        return self._room.local_participant.identity
