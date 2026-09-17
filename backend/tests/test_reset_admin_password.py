"""Password-reset recovery tool: `scripts/reset_admin_password.py`.

Covers recovering a lost `college_admin` password without creating or
deleting any College/User row, and without ever printing the new
plaintext password.
"""
from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.college import College
from app.models.support import AuditLog
from app.models.user import User

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reset_admin_password  # noqa: E402


@contextmanager
def _fake_session_scope(db):
    """Mirrors the real `session_scope()`'s commit-on-success/rollback-on-
    exception behavior (minus closing the session, which the shared `db`
    test fixture owns across multiple calls in a single test)."""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def _run(db, monkeypatch, argv, *, new_password="NewStrongPass123", set_env=True):
    monkeypatch.setattr(reset_admin_password, "session_scope", lambda: _fake_session_scope(db))
    if set_env:
        monkeypatch.setenv("ADMIN_PASSWORD_RESET", new_password)
    else:
        monkeypatch.delenv("ADMIN_PASSWORD_RESET", raising=False)
    return reset_admin_password.main(argv)


def _make_college_admin(db, *, email="admin@nova-institute-of-technology.example.edu", role="college_admin"):
    college = College(
        name="Nova Institute of Technology",
        slug="nova-institute-of-technology",
        email="admissions@nova-institute-of-technology.example.edu",
        phone="+91-9800000000",
        status="draft",
        default_language="en",
        supported_languages=["en"],
    )
    db.add(college)
    db.flush()
    user = User(
        college_id=college.id,
        email=email,
        password_hash=hash_password("OriginalPass123"),
        full_name="Priya Sharma",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.commit()
    return college, user


def test_resets_password_for_existing_admin(db, monkeypatch, capsys):
    college, user = _make_college_admin(db)

    exit_code = _run(db, monkeypatch, ["--email", user.email])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "NewStrongPass123" not in out

    refreshed = db.execute(select(User).where(User.id == user.id)).scalar_one()
    assert verify_password("NewStrongPass123", refreshed.password_hash)
    # Nothing else about the user changed.
    assert refreshed.full_name == "Priya Sharma"
    assert refreshed.role == "college_admin"
    assert refreshed.college_id == college.id


def test_records_audit_entry_without_password(db, monkeypatch, capsys):
    _, user = _make_college_admin(db)

    _run(db, monkeypatch, ["--email", user.email])

    entry = db.execute(
        select(AuditLog).where(AuditLog.action == "admin_password_reset")
    ).scalar_one()
    assert entry.entity_id == user.id
    assert entry.meta == {"email": user.email}
    assert "NewStrongPass123" not in str(entry.meta)


def test_refuses_when_email_does_not_exist(db, monkeypatch, capsys):
    exit_code = _run(db, monkeypatch, ["--email", "nobody@example.edu"])

    assert exit_code == 1
    assert "No user found" in capsys.readouterr().err
    assert db.execute(select(AuditLog)).scalars().all() == []


def test_refuses_when_user_is_not_college_admin(db, monkeypatch, capsys):
    _, user = _make_college_admin(db, email="staff@nova-institute-of-technology.example.edu", role="admissions_staff")
    original_hash = user.password_hash

    exit_code = _run(db, monkeypatch, ["--email", user.email])

    assert exit_code == 1
    assert "not a college_admin" in capsys.readouterr().err
    refreshed = db.execute(select(User).where(User.id == user.id)).scalar_one()
    assert refreshed.password_hash == original_hash


def test_refuses_when_env_var_not_set(db, monkeypatch, capsys):
    _, user = _make_college_admin(db)
    original_hash = user.password_hash

    exit_code = _run(db, monkeypatch, ["--email", user.email], set_env=False)

    assert exit_code == 1
    assert "ADMIN_PASSWORD_RESET" in capsys.readouterr().err
    refreshed = db.execute(select(User).where(User.id == user.id)).scalar_one()
    assert refreshed.password_hash == original_hash


def test_refuses_weak_password_before_any_write(db, monkeypatch, capsys):
    _, user = _make_college_admin(db)
    original_hash = user.password_hash

    exit_code = _run(db, monkeypatch, ["--email", user.email], new_password="short")

    assert exit_code == 1
    assert "Invalid password" in capsys.readouterr().err
    refreshed = db.execute(select(User).where(User.id == user.id)).scalar_one()
    assert refreshed.password_hash == original_hash


def test_never_creates_or_deletes_college_or_user(db, monkeypatch):
    _make_college_admin(db)

    _run(db, monkeypatch, ["--email", "admin@nova-institute-of-technology.example.edu"])

    assert len(db.execute(select(College)).scalars().all()) == 1
    assert len(db.execute(select(User)).scalars().all()) == 1


def test_email_lookup_is_case_and_whitespace_insensitive(db, monkeypatch):
    _, user = _make_college_admin(db)

    exit_code = _run(db, monkeypatch, ["--email", "  ADMIN@Nova-Institute-Of-Technology.example.edu  "])

    assert exit_code == 0
    refreshed = db.execute(select(User).where(User.id == user.id)).scalar_one()
    assert verify_password("NewStrongPass123", refreshed.password_hash)
