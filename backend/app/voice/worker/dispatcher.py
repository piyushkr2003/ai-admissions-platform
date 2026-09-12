"""Realtime voice worker dispatch (Task 016).

Deliberately simple rather than adopting LiveKit Agents' own job-worker
protocol (docs/development.md section 5, "do not introduce
infrastructure merely because it may be useful in the future" - and
there is no real LiveKit deployment to dispatch against in this
environment anyway): a single dispatcher process polls for
`VoiceSession` rows using the `livekit` transport that don't yet have a
worker, and runs one `RealtimeVoiceWorker` per session as an asyncio
task on its own event loop.

This is a single-process design - claims are tracked in memory, not in
the database - which is a documented scope boundary (see
docs/voice.md section 73) appropriate for one dispatcher instance;
scaling to multiple dispatcher processes would need a DB-level claim
column, not a redesign of this class.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.voice import VoiceSession
from app.voice.worker.session_worker import RealtimeVoiceWorker

logger = logging.getLogger("app.voice.worker.dispatcher")

_DISPATCHABLE_STATUSES = ("connecting", "active")


class WorkerDispatcher:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        worker_factory: Callable[[uuid.UUID], object] | None = None,
        poll_interval: float | None = None,
    ):
        self._session_factory = session_factory or get_sessionmaker()
        self._worker_factory = worker_factory or (lambda session_id: RealtimeVoiceWorker(session_id))
        self._poll_interval = poll_interval if poll_interval is not None else get_settings().voice_worker_poll_interval_seconds
        self._claimed: set[uuid.UUID] = set()
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}

    def poll_once(self) -> list[uuid.UUID]:
        """Finds livekit-provider sessions that don't yet have a claimed
        worker and claims them. Returns the newly claimed session ids -
        pure, synchronous, and directly testable against the test DB."""
        db = self._session_factory()
        try:
            rows = db.execute(
                select(VoiceSession.id).where(
                    VoiceSession.provider == "livekit",
                    VoiceSession.status.in_(_DISPATCHABLE_STATUSES),
                )
            ).scalars().all()
        finally:
            db.close()
        newly_claimed = [session_id for session_id in rows if session_id not in self._claimed]
        self._claimed.update(newly_claimed)
        return newly_claimed

    def dispatch(self, session_id: uuid.UUID) -> asyncio.Task:
        worker = self._worker_factory(session_id)
        task = asyncio.create_task(worker.run())
        self._tasks[session_id] = task
        task.add_done_callback(lambda _task, sid=session_id: self._release(sid))
        logger.info("voice.worker_dispatched session_id=%s", session_id)
        return task

    def _release(self, session_id: uuid.UUID) -> None:
        self._claimed.discard(session_id)
        self._tasks.pop(session_id, None)

    async def run_forever(self) -> None:
        while True:
            for session_id in self.poll_once():
                self.dispatch(session_id)
            await asyncio.sleep(self._poll_interval)

    async def shutdown(self) -> None:
        for worker_task in list(self._tasks.values()):
            worker_task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
