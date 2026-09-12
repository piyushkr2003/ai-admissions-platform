"""Task 016 - realtime voice worker dispatcher (app/voice/worker/dispatcher.py)."""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.colleges.context import get_college_context
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.voice import VoiceSession
from app.services.voice import VoiceSessionService
from app.voice.worker.dispatcher import WorkerDispatcher

NOVA_SLUG = "nova-institute-of-technology"


class FakeWorker:
    def __init__(self, session_id, *, gate: asyncio.Event | None = None):
        self.session_id = session_id
        self.ran = False
        self._gate = gate

    async def run(self) -> None:
        if self._gate is not None:
            await self._gate.wait()
        self.ran = True


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _make_session(db, college: College, *, provider: str = "livekit", status: str = "connecting") -> VoiceSession:
    context = get_college_context(db, college.id)
    service = VoiceSessionService(db)
    session, _conversation, _credentials, _greeting = service.create_web_session(context)
    session.provider = provider
    session.status = status
    db.commit()
    return session


def test_poll_once_claims_only_livekit_sessions_in_a_dispatchable_status(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    livekit_session = _make_session(db, nova, provider="livekit", status="connecting")
    _make_session(db, nova, provider="mock", status="connecting")  # must be ignored
    _make_session(db, nova, provider="livekit", status="completed")  # must be ignored (already ended)

    dispatcher = WorkerDispatcher(session_factory=lambda: db, poll_interval=0.01)
    claimed = dispatcher.poll_once()

    assert claimed == [livekit_session.id]


def test_poll_once_does_not_reclaim_an_already_claimed_session(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    session = _make_session(db, nova, provider="livekit", status="connecting")

    dispatcher = WorkerDispatcher(session_factory=lambda: db, poll_interval=0.01)
    first = dispatcher.poll_once()
    second = dispatcher.poll_once()

    assert first == [session.id]
    assert second == []  # still claimed from the first poll


def test_dispatch_runs_the_worker_and_releases_the_claim_on_completion(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    session = _make_session(db, nova, provider="livekit", status="connecting")

    created: dict = {}

    def worker_factory(session_id):
        worker = FakeWorker(session_id)
        created["worker"] = worker
        return worker

    dispatcher = WorkerDispatcher(session_factory=lambda: db, worker_factory=worker_factory, poll_interval=0.01)
    dispatcher._claimed.add(session.id)

    async def scenario():
        task = dispatcher.dispatch(session.id)
        await task

    asyncio.run(scenario())

    assert created["worker"].ran is True
    assert session.id not in dispatcher._claimed
    assert session.id not in dispatcher._tasks


def test_run_forever_dispatches_newly_claimed_sessions_each_poll(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    session = _make_session(db, nova, provider="livekit", status="connecting")

    gate = asyncio.Event()
    dispatched_ids = []

    def worker_factory(session_id):
        dispatched_ids.append(session_id)
        return FakeWorker(session_id, gate=gate)

    dispatcher = WorkerDispatcher(session_factory=lambda: db, worker_factory=worker_factory, poll_interval=0.01)

    async def scenario():
        runner = asyncio.create_task(dispatcher.run_forever())
        await asyncio.sleep(0.05)
        runner.cancel()
        gate.set()
        try:
            await runner
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert dispatched_ids == [session.id]  # dispatched exactly once, never duplicated across polls


def test_shutdown_cancels_all_in_flight_worker_tasks(db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, NOVA_SLUG)
    session = _make_session(db, nova, provider="livekit", status="connecting")

    never_finishes = asyncio.Event()  # never set - the worker would hang forever without cancellation

    def worker_factory(session_id):
        return FakeWorker(session_id, gate=never_finishes)

    dispatcher = WorkerDispatcher(session_factory=lambda: db, worker_factory=worker_factory, poll_interval=0.01)
    dispatcher._claimed.add(session.id)

    async def scenario():
        dispatcher.dispatch(session.id)
        await asyncio.sleep(0.01)
        await asyncio.wait_for(dispatcher.shutdown(), timeout=1)

    asyncio.run(scenario())  # must not hang or raise
