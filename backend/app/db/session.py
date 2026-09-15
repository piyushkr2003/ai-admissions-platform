"""Database engine/session management.

Provides a clean, reusable session pattern:
- one Engine per process (pooled connections)
- one Session per request/unit of work
- explicit commit/rollback boundaries owned by the caller (service layer),
  never left as an unmanaged global session.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def normalize_database_url(url: str) -> str:
    """Rewrites a bare `postgresql://` URL to `postgresql+psycopg://`.

    Managed Postgres providers (Render, Heroku, etc.) hand back a plain
    `postgresql://...` connection string, which SQLAlchemy resolves to the
    psycopg2 dialect - not installed here (this project uses psycopg3, the
    `psycopg` dialect, via the `psycopg[binary]` dependency). Any URL that
    already names a driver (`postgresql+psycopg://`, `+psycopg2`, etc.) or
    isn't Postgres at all (sqlite, for tests) passes through unchanged.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session_factory = get_sessionmaker()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for scripts/services outside the request lifecycle."""
    session_factory = get_sessionmaker()
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_engine_for_tests(database_url: str) -> None:
    """Rebind the module-level engine/sessionmaker to a different database.

    Used only by the test suite to point the app at a dedicated test
    database without mutating global settings.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
