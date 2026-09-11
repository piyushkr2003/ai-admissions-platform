"""Password hashing and JWT helpers.

Uses Argon2id (via argon2-cffi) for password hashing and PyJWT for signed,
expiring access/refresh tokens. No homemade cryptography.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

from app.core.config import get_settings

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def _create_token(subject: str, token_type: str, claims: dict[str, Any], expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str, college_id: str | None) -> str:
    settings = get_settings()
    return _create_token(
        subject=user_id,
        token_type="access",
        claims={"role": role, "college_id": college_id},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (token, jti) so the caller can persist/revoke the session."""
    settings = get_settings()
    jti = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if expected_type and payload.get("type") != expected_type:
        raise InvalidTokenError(f"Expected token type '{expected_type}'")
    return payload
