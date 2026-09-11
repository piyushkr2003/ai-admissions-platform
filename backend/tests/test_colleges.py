"""Task 004 - college configuration & onboarding tests."""
from __future__ import annotations

from sqlalchemy import select

from app.colleges.validators import (
    is_allowed_transition,
    is_valid_language,
    is_valid_timezone,
    normalize_slug,
)
from app.core.security import hash_password
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.user import User

NOVA_ADMIN_EMAIL = "admin@nova-institute-of-technology.example.edu"
NOVA_ADMIN_PASSWORD = "NovaAdmin#2026"
AURORA_ADMIN_EMAIL = "admin@aurora-college-of-management.example.edu"
AURORA_ADMIN_PASSWORD = "AuroraAdmin#2026"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _make_platform_admin(db) -> User:
    admin = User(
        college_id=None,
        email="platform-admin@admissions.example",
        password_hash=hash_password("PlatformAdmin#2026"),
        full_name="Platform Admin",
        role="platform_admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    return admin


# ---------------------------------------------------------------------------
# Unit: validators
# ---------------------------------------------------------------------------

def test_normalize_slug_produces_url_safe_value():
    assert normalize_slug("Nova Institute of Technology!!") == "nova-institute-of-technology"
    assert normalize_slug("  Multiple   Spaces  ") == "multiple-spaces"


def test_is_valid_timezone():
    assert is_valid_timezone("Asia/Kolkata")
    assert not is_valid_timezone("Not/A_Timezone")


def test_is_valid_language():
    assert is_valid_language("en")
    assert is_valid_language("hinglish")
    assert not is_valid_language("fr")


def test_lifecycle_transitions():
    assert is_allowed_transition("draft", "active")
    assert is_allowed_transition("active", "suspended")
    assert is_allowed_transition("suspended", "active")
    assert not is_allowed_transition("archived", "active")
    assert not is_allowed_transition("draft", "suspended")


# ---------------------------------------------------------------------------
# Integration: create -> configure -> validate -> publish
# ---------------------------------------------------------------------------

def test_platform_admin_can_create_college_in_draft(client, db):
    _make_platform_admin(db)
    tokens = _login(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    resp = client.post(
        "/api/v1/colleges",
        json={"name": "Test College", "email": "info@test-college.example.edu"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["slug"] == "test-college"
    assert body["status"] == "draft"


def test_college_admin_cannot_create_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/colleges",
        json={"name": "Rogue College"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403


def test_publish_fails_when_configuration_incomplete(client, db):
    _make_platform_admin(db)
    tokens = _login(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    create_resp = client.post(
        "/api/v1/colleges",
        json={"name": "Incomplete College"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    college_id = create_resp.json()["data"]["id"]

    publish_resp = client.post(
        f"/api/v1/colleges/{college_id}/publish",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert publish_resp.status_code == 422
    errors = publish_resp.json()["error"]["details"]["errors"]
    assert any("active course" in e for e in errors)


def test_publish_succeeds_for_fully_seeded_nova(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()
    nova.status = "draft"
    db.commit()

    resp = client.post(
        f"/api/v1/colleges/{nova.id}/publish",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "active"


def test_invalid_lifecycle_transition_rejected(client, db):
    _make_platform_admin(db)
    tokens = _login(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    create_resp = client.post(
        "/api/v1/colleges",
        json={"name": "Archived College"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    college_id = create_resp.json()["data"]["id"]

    archive_resp = client.post(
        f"/api/v1/colleges/{college_id}/archive",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["status"] == "archived"

    republish_resp = client.post(
        f"/api/v1/colleges/{college_id}/publish",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert republish_resp.status_code == 409


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

def test_college_admin_can_read_own_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    resp = client.get(
        f"/api/v1/colleges/{nova.id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200


def test_college_admin_cannot_read_other_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    aurora = db.execute(select(College).where(College.slug == "aurora-college-of-management")).scalar_one()

    resp = client.get(
        f"/api/v1/colleges/{aurora.id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


def test_college_admin_cannot_patch_other_college_by_changing_url(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    aurora = db.execute(select(College).where(College.slug == "aurora-college-of-management")).scalar_one()

    resp = client.patch(
        f"/api/v1/colleges/{aurora.id}",
        json={"name": "Hijacked Name"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403

    unchanged = db.get(College, aurora.id)
    assert unchanged.name == "Aurora College of Management"


def test_college_admin_cannot_suspend_or_archive(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    resp = client.post(
        f"/api/v1/colleges/{nova.id}/suspend",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403


def test_platform_admin_can_suspend_and_reactivate(client, db):
    seed_demo_data(db)
    db.commit()
    _make_platform_admin(db)
    tokens = _login(client, "platform-admin@admissions.example", "PlatformAdmin#2026")
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    suspend_resp = client.post(
        f"/api/v1/colleges/{nova.id}/suspend",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["data"]["status"] == "suspended"

    reactivate_resp = client.post(
        f"/api/v1/colleges/{nova.id}/publish",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["data"]["status"] == "active"


def test_configuration_update_rejects_unsupported_default_language(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    resp = client.patch(
        f"/api/v1/colleges/{nova.id}/configuration",
        json={"default_language": "fr", "supported_languages": ["en", "hi"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_configuration_update_rejects_invalid_timezone(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    resp = client.patch(
        f"/api/v1/colleges/{nova.id}/configuration",
        json={"timezone": "Not/Real"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 422


def test_counselor_can_read_but_not_write_configuration(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, "counselor@nova-institute-of-technology.example.edu", "NovaCounselor#2026")
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    read_resp = client.get(
        f"/api/v1/colleges/{nova.id}/configuration",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert read_resp.status_code == 200

    write_resp = client.patch(
        f"/api/v1/colleges/{nova.id}/configuration",
        json={"timezone": "Asia/Kolkata"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert write_resp.status_code == 403


def test_get_college_context_reflects_seeded_nova(db):
    from app.colleges.context import get_college_context

    seed_demo_data(db)
    db.commit()
    nova = db.execute(select(College).where(College.slug == "nova-institute-of-technology")).scalar_one()

    ctx = get_college_context(db, nova.id)
    assert ctx is not None
    assert ctx.name == "Nova Institute of Technology"
    assert ctx.agent_config_id is not None
    assert "en" in ctx.supported_languages
    assert ctx.feature_enabled("appointment_booking_enabled") is True


def test_duplicate_slug_returns_conflict(client, db):
    _make_platform_admin(db)
    tokens = _login(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    first = client.post(
        "/api/v1/colleges",
        json={"name": "Duplicate Slug College"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/colleges",
        json={"name": "Duplicate Slug College"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"
