"""Production college_admin bootstrap: `CollegeService.create_initial_admin`,
the `CollegeAdminBootstrap` schema, and the `scripts/create_college_admin.py`
CLI wrapper around them.

Deliberately does not use `app.db.seed.seed_demo_data` - this mechanism is
the production-safe alternative to the fictional demo fixture, so its
tests build their own minimal college/admin state.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.colleges.schemas import CollegeAdminBootstrap
from app.colleges.service import CollegeService
from app.core.errors import ConflictError
from app.core.security import verify_password
from app.models.college import College
from app.models.support import AuditLog
from app.models.user import User

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import create_college_admin  # noqa: E402


def _make_college(db, *, slug: str = "test-college") -> College:
    college = College(name="Test College", slug=slug, status="active")
    db.add(college)
    db.flush()
    return college


# ---------------------------------------------------------------------------
# Schema validation (password hashing precondition)
# ---------------------------------------------------------------------------

def test_bootstrap_schema_rejects_short_password():
    with pytest.raises(ValidationError):
        CollegeAdminBootstrap(email="admin@example.edu", full_name="Admin", password="short")


def test_bootstrap_schema_rejects_invalid_email():
    with pytest.raises(ValidationError):
        CollegeAdminBootstrap(email="not-an-email", full_name="Admin", password="LongEnough123")


# ---------------------------------------------------------------------------
# CollegeService.create_initial_admin
# ---------------------------------------------------------------------------

def test_create_initial_admin_hashes_password_and_sets_role(db):
    college = _make_college(db)
    payload = CollegeAdminBootstrap(email="Admin@Test-College.example.edu", full_name="Priya Sharma", password="StrongPass123")

    admin = CollegeService(db).create_initial_admin(college, payload, actor_user_id=None)
    db.commit()

    assert admin.role == "college_admin"
    assert admin.college_id == college.id
    assert admin.email == "admin@test-college.example.edu"  # normalized
    assert admin.password_hash != "StrongPass123"
    assert verify_password("StrongPass123", admin.password_hash)


def test_create_initial_admin_records_audit_log(db):
    college = _make_college(db)
    payload = CollegeAdminBootstrap(email="admin@test-college.example.edu", full_name="Priya Sharma", password="StrongPass123")

    admin = CollegeService(db).create_initial_admin(college, payload, actor_user_id=None)
    db.flush()

    entry = db.execute(
        select(AuditLog).where(AuditLog.entity_id == admin.id, AuditLog.entity_type == "user")
    ).scalar_one()
    assert entry.action == "college_admin_bootstrapped"
    assert entry.college_id == college.id


def test_create_initial_admin_rejects_second_admin_for_same_college(db):
    college = _make_college(db)
    service = CollegeService(db)
    service.create_initial_admin(
        college,
        CollegeAdminBootstrap(email="first@test-college.example.edu", full_name="First Admin", password="StrongPass123"),
        actor_user_id=None,
    )
    db.flush()

    with pytest.raises(ConflictError):
        service.create_initial_admin(
            college,
            CollegeAdminBootstrap(email="second@test-college.example.edu", full_name="Second Admin", password="StrongPass123"),
            actor_user_id=None,
        )


def test_create_initial_admin_rejects_duplicate_email_across_colleges(db):
    college_a = _make_college(db, slug="college-a")
    college_b = _make_college(db, slug="college-b")
    service = CollegeService(db)
    service.create_initial_admin(
        college_a,
        CollegeAdminBootstrap(email="shared@example.edu", full_name="Admin A", password="StrongPass123"),
        actor_user_id=None,
    )
    db.flush()

    with pytest.raises(ConflictError):
        service.create_initial_admin(
            college_b,
            CollegeAdminBootstrap(email="shared@example.edu", full_name="Admin B", password="StrongPass123"),
            actor_user_id=None,
        )


# ---------------------------------------------------------------------------
# CLI wrapper (scripts/create_college_admin.py)
# ---------------------------------------------------------------------------

@contextmanager
def _fake_session_scope(db):
    yield db


def test_cli_rejects_unknown_college_slug(db, monkeypatch, capsys):
    monkeypatch.setattr(create_college_admin, "session_scope", lambda: _fake_session_scope(db))
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "StrongPass123")

    exit_code = create_college_admin.main(
        ["--college-slug", "does-not-exist", "--email", "admin@example.edu", "--full-name", "Admin"]
    )

    assert exit_code == 1
    assert "No college found" in capsys.readouterr().err
    assert db.execute(select(User).where(User.email == "admin@example.edu")).scalar_one_or_none() is None


def test_cli_creates_admin_and_prefers_env_password_over_prompt(db, monkeypatch, capsys):
    college = _make_college(db)
    db.commit()
    monkeypatch.setattr(create_college_admin, "session_scope", lambda: _fake_session_scope(db))
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "StrongPass123")

    def _fail_if_prompted():
        raise AssertionError("should not prompt when ADMIN_BOOTSTRAP_PASSWORD is set")

    monkeypatch.setattr(create_college_admin.getpass, "getpass", lambda *a, **kw: _fail_if_prompted())

    exit_code = create_college_admin.main(
        ["--college-slug", college.slug, "--email", "admin@test-college.example.edu", "--full-name", "Priya Sharma"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "admin@test-college.example.edu" in out
    assert "StrongPass123" not in out

    created = db.execute(select(User).where(User.email == "admin@test-college.example.edu")).scalar_one()
    assert created.role == "college_admin"
    assert verify_password("StrongPass123", created.password_hash)


def test_cli_rejects_duplicate_admin_for_college(db, monkeypatch, capsys):
    college = _make_college(db)
    CollegeService(db).create_initial_admin(
        college,
        CollegeAdminBootstrap(email="existing@test-college.example.edu", full_name="Existing Admin", password="StrongPass123"),
        actor_user_id=None,
    )
    db.commit()

    monkeypatch.setattr(create_college_admin, "session_scope", lambda: _fake_session_scope(db))
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "AnotherPass123")

    exit_code = create_college_admin.main(
        ["--college-slug", college.slug, "--email", "second@test-college.example.edu", "--full-name", "Second Admin"]
    )

    assert exit_code == 1
    assert "already has a college_admin" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# End-to-end: the created admin can log in through the real, unmodified
# /api/v1/auth/login endpoint (proves existing login behavior is preserved).
# ---------------------------------------------------------------------------

def test_created_admin_can_log_in(client, db):
    college = _make_college(db)
    CollegeService(db).create_initial_admin(
        college,
        CollegeAdminBootstrap(email="admin@test-college.example.edu", full_name="Priya Sharma", password="StrongPass123"),
        actor_user_id=None,
    )
    db.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test-college.example.edu", "password": "StrongPass123"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["user"]["role"] == "college_admin"
    assert body["user"]["college_id"] == str(college.id)
    assert "access_token" in body and "refresh_token" in body
