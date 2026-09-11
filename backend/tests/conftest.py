from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  ensure all models are registered on Base.metadata
from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app


@pytest.fixture(scope="session")
def test_engine():
    settings = get_settings()
    engine = create_engine(settings.database_url_test, future=True, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(test_engine) -> Session:
    """A session bound to a single connection/transaction that is rolled
    back after the test, even if the code under test calls commit()."""
    connection = test_engine.connect()
    outer_txn = connection.begin()
    session_factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> TestClient:
    app = create_app()

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
