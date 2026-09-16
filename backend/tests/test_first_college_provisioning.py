"""First-production-tenant bootstrap: `scripts/create_first_college.py`,
which combines the existing `CollegeService.create_college` and
`create_initial_admin` in one transaction.

Deliberately does not use `app.db.seed.seed_demo_data` or
`app.db.nova_demo.bootstrap_nova_demo` - this script is the
production-safe alternative to both fictional fixtures.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select

from app.colleges.repository import CollegeRepository
from app.core.security import verify_password
from app.models.college import College
from app.models.support import AuditLog
from app.models.user import User

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import create_first_college  # noqa: E402


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


def _run(db, monkeypatch, argv, *, password="StrongPass123", set_password_env=True):
    monkeypatch.setattr(create_first_college, "session_scope", lambda: _fake_session_scope(db))
    if set_password_env:
        monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", password)
    else:
        monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    return create_first_college.main(argv)


_BASE_ARGS = [
    "--name", "Nova Institute of Technology",
    "--email", "admissions@nova-institute-of-technology.example.edu",
    "--phone", "+91-9800000000",
    "--admin-email", "admin@nova-institute-of-technology.example.edu",
    "--admin-full-name", "Priya Sharma",
]


def test_creates_college_and_admin_in_one_transaction(db, monkeypatch, capsys):
    exit_code = _run(db, monkeypatch, _BASE_ARGS)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "StrongPass123" not in out

    college = db.execute(
        select(College).where(College.slug == "nova-institute-of-technology")
    ).scalar_one()
    assert college.name == "Nova Institute of Technology"
    assert college.email == "admissions@nova-institute-of-technology.example.edu"
    assert college.phone == "+91-9800000000"
    assert college.status == "draft"  # never auto-published

    admin = db.execute(
        select(User).where(User.email == "admin@nova-institute-of-technology.example.edu")
    ).scalar_one()
    assert admin.role == "college_admin"
    assert admin.college_id == college.id
    assert admin.full_name == "Priya Sharma"
    assert verify_password("StrongPass123", admin.password_hash)

    # Audit trail recorded via the existing shared mechanism.
    actions = {
        a.action
        for a in db.execute(select(AuditLog).where(AuditLog.college_id == college.id)).scalars().all()
    }
    assert actions == {"college_created", "college_admin_bootstrapped"}


def test_creates_no_demo_or_related_data(db, monkeypatch):
    _run(db, monkeypatch, _BASE_ARGS)

    college = db.execute(
        select(College).where(College.slug == "nova-institute-of-technology")
    ).scalar_one()
    repo = CollegeRepository(db)
    assert repo.has_active_course(college.id) is False
    assert repo.knowledge_source_count(college.id) == 0
    assert repo.has_agent_config(college.id) is False

    # Exactly one college, one user overall - nothing extra was seeded.
    assert len(db.execute(select(College)).scalars().all()) == 1
    assert len(db.execute(select(User)).scalars().all()) == 1


def test_slug_is_auto_derived_when_omitted(db, monkeypatch):
    args = [a for a in _BASE_ARGS]  # no --slug passed
    _run(db, monkeypatch, args)

    college = db.execute(select(College)).scalar_one()
    assert college.slug == "nova-institute-of-technology"


def test_rejects_duplicate_college_slug(db, monkeypatch, capsys):
    first = _run(db, monkeypatch, _BASE_ARGS)
    assert first == 0

    second_args = _BASE_ARGS + []
    second_args[second_args.index("--admin-email") + 1] = "second-admin@nova-institute-of-technology.example.edu"
    exit_code = _run(db, monkeypatch, second_args)

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err

    # Only the first college/admin exist - the rejected second call created nothing.
    assert len(db.execute(select(College)).scalars().all()) == 1
    assert len(db.execute(select(User)).scalars().all()) == 1


def test_rejects_duplicate_admin_email_and_rolls_back_college(db, monkeypatch, capsys):
    first = _run(db, monkeypatch, _BASE_ARGS)
    assert first == 0

    second_args = [
        "--name", "Aurora College of Management",
        "--slug", "aurora-college-of-management",
        "--email", "admissions@aurora-college-of-management.example.edu",
        "--phone", "+91-9800000001",
        "--admin-email", "admin@nova-institute-of-technology.example.edu",  # already taken
        "--admin-full-name", "Kavita Rao",
    ]
    exit_code = _run(db, monkeypatch, second_args, password="AnotherStrongPass123")

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err

    # The second college must NOT have been left behind: college creation
    # and admin creation share one transaction, so the failed admin step
    # rolls the college insert back too.
    assert db.execute(
        select(College).where(College.slug == "aurora-college-of-management")
    ).scalar_one_or_none() is None
    assert len(db.execute(select(College)).scalars().all()) == 1
    assert len(db.execute(select(User)).scalars().all()) == 1


def test_rejects_weak_password_before_any_write(db, monkeypatch, capsys):
    exit_code = _run(db, monkeypatch, _BASE_ARGS, password="short")

    assert exit_code == 1
    assert "Invalid input" in capsys.readouterr().err
    assert db.execute(select(College)).scalars().all() == []
    assert db.execute(select(User)).scalars().all() == []


def test_prefers_env_password_over_prompt(db, monkeypatch):
    def _fail_if_prompted(*a, **kw):
        raise AssertionError("should not prompt when ADMIN_BOOTSTRAP_PASSWORD is set")

    monkeypatch.setattr(create_first_college.getpass, "getpass", _fail_if_prompted)
    exit_code = _run(db, monkeypatch, _BASE_ARGS)

    assert exit_code == 0
