"""Task 003 - authentication & RBAC tests."""
from __future__ import annotations

import uuid

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.seed import seed_demo_data
from app.models.user import User


# ---------------------------------------------------------------------------
# Unit tests: password hashing
# ---------------------------------------------------------------------------

def test_password_hash_and_verify_roundtrip():
    hashed = hash_password("CorrectHorseBattery9")
    assert hashed != "CorrectHorseBattery9"
    assert verify_password("CorrectHorseBattery9", hashed)


def test_password_verify_rejects_wrong_password():
    hashed = hash_password("CorrectHorseBattery9")
    assert not verify_password("WrongPassword", hashed)


def test_password_too_short_is_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


# ---------------------------------------------------------------------------
# Unit tests: tokens
# ---------------------------------------------------------------------------

def test_access_token_roundtrip():
    token = create_access_token("user-1", "college_admin", "college-1")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-1"
    assert payload["role"] == "college_admin"
    assert payload["college_id"] == "college-1"


def test_expired_token_is_rejected():
    settings = get_settings()
    payload = {"sub": "user-1", "type": "access", "iat": 0, "exp": 1}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access")


def test_malformed_token_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-token", expected_type="access")


def test_wrong_token_type_is_rejected():
    token = create_access_token("user-1", "college_admin", None)
    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="refresh")


# ---------------------------------------------------------------------------
# Integration: login -> protected endpoint
# ---------------------------------------------------------------------------

NOVA_ADMIN_EMAIL = "admin@nova-institute-of-technology.example.edu"
NOVA_ADMIN_PASSWORD = "NovaAdmin#2026"
NOVA_COUNSELOR_EMAIL = "counselor@nova-institute-of-technology.example.edu"
NOVA_COUNSELOR_PASSWORD = "NovaCounselor#2026"
AURORA_ADMIN_EMAIL = "admin@aurora-college-of-management.example.edu"
AURORA_ADMIN_PASSWORD = "AuroraAdmin#2026"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_login_returns_tokens_and_safe_user_profile(client, db):
    seed_demo_data(db)
    db.commit()

    data = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_in"] > 0
    assert data["user"]["email"] == NOVA_ADMIN_EMAIL
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


def test_login_with_wrong_password_returns_generic_401(client, db):
    seed_demo_data(db)
    db.commit()

    resp = client.post(
        "/api/v1/auth/login", json={"email": NOVA_ADMIN_EMAIL, "password": "totally-wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    assert "wrong" not in resp.json()["error"]["message"].lower()


def test_login_with_nonexistent_email_returns_same_generic_401(client, db):
    seed_demo_data(db)
    db.commit()

    resp = client.post(
        "/api/v1/auth/login", json={"email": "nobody@nowhere.example", "password": "whatever123"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_requires_authentication(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_returns_current_user_with_valid_token(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == NOVA_ADMIN_EMAIL


def test_invalid_bearer_token_returns_401(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
    assert resp.status_code == 401


def test_suspended_user_is_denied(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    user = db.execute(select(User).where(User.email == NOVA_ADMIN_EMAIL)).scalar_one()
    user.is_active = False
    db.commit()

    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh / logout
# ---------------------------------------------------------------------------

def test_refresh_issues_new_tokens_and_revokes_old_session(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The original refresh token must no longer work (rotation).
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


def test_logout_revokes_refresh_session(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


def test_refresh_with_garbage_token_returns_401(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authorization: role + tenant
# ---------------------------------------------------------------------------

def test_college_admin_can_access_own_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    nova = db.execute(select(User).where(User.email == NOVA_ADMIN_EMAIL)).scalar_one()

    resp = client.get(
        f"/api/v1/_internal/college-check/{nova.college_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200


def test_college_admin_cannot_access_other_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    aurora = db.execute(select(User).where(User.email == AURORA_ADMIN_EMAIL)).scalar_one()

    resp = client.get(
        f"/api/v1/_internal/college-check/{aurora.college_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


def test_forged_college_id_in_path_cannot_bypass_authorization(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    random_college_id = uuid.uuid4()
    resp = client.get(
        f"/api/v1/_internal/college-check/{random_college_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403


def test_platform_only_endpoint_denies_college_admin(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get(
        "/api/v1/_internal/platform-only",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_counselor_cannot_reach_platform_only_endpoint(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    resp = client.get(
        "/api/v1/_internal/platform-only",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403


def test_platform_admin_bypasses_tenant_restriction_by_design(client, db):
    seed_demo_data(db)
    from app.core.security import hash_password as _hp

    platform_admin = User(
        college_id=None,
        email="platform@admissions.example",
        password_hash=_hp("PlatformAdmin#2026"),
        full_name="Platform Admin",
        role="platform_admin",
        is_active=True,
    )
    db.add(platform_admin)
    db.commit()

    tokens = _login(client, "platform@admissions.example", "PlatformAdmin#2026")
    aurora = db.execute(select(User).where(User.email == AURORA_ADMIN_EMAIL)).scalar_one()

    resp = client.get(
        f"/api/v1/_internal/college-check/{aurora.college_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200

    platform_resp = client.get(
        "/api/v1/_internal/platform-only",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert platform_resp.status_code == 200


def test_permission_matrix_denies_unlisted_permission_for_counselor():
    from app.auth.permissions import has_permission

    assert has_permission("counselor", "leads:read") is True
    assert has_permission("counselor", "college_configuration:write") is False
    assert has_permission("platform_admin", "anything:at_all") is True
    assert has_permission("unknown_role", "leads:read") is False
