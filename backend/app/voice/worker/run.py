"""CLI entrypoint for the realtime voice worker dispatcher (Task 016).

Run alongside the backend and frontend when VOICE_TRANSPORT_PROVIDER=livekit:

    python -m app.voice.worker.run

No arguments and no configuration beyond the LIVEKIT_*/voice-worker
settings documented in docs/development.md. Idles safely (does nothing)
when no livekit-provider voice sessions exist, which is always true
under the default mock provider used by local development and CI - this
process is optional there.
"""
from __future__ import annotations

import asyncio
import logging

from app.voice.worker.dispatcher import WorkerDispatcher

logger = logging.getLogger("app.voice.worker.run")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("voice.worker_dispatcher_starting")
    dispatcher = WorkerDispatcher()
    try:
        asyncio.run(dispatcher.run_forever())
    except KeyboardInterrupt:
        logger.info("voice.worker_dispatcher_stopping")


if __name__ == "__main__":
    main()
