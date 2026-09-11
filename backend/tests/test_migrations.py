"""Task 002 - migration tests.

Verifies migrations apply cleanly to a fresh schema and that downgrade/
upgrade round-trips without error. Runs against the dedicated test
database via subprocess so it does not interfere with the transactional
`db` fixture used by other tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    from app.core.config import get_settings

    env["ALEMBIC_DATABASE_URL"] = get_settings().database_url_test
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_migrations_downgrade_and_upgrade_cleanly():
    down = _run_alembic("downgrade", "base")
    assert down.returncode == 0, down.stderr

    up = _run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    current = _run_alembic("current")
    assert current.returncode == 0
    assert "head" in current.stdout or current.stdout.strip() != ""
