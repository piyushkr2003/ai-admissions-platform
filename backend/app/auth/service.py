"""Authentication business logic.

Kept separate from the HTTP layer (router.py) and from authorization
(dependencies.py / permissions.py) so each concern is independently
testable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.auth import RefreshSession
from app.models.user import User

logger = logging.getLogger("app.auth")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, email: str, password: str) -> User:
        stmt = select(User).where(User.email == _normalize_email(email))
        user = self.db.execute(stmt).scalar_one_or_none()
        # Deliberately identical error for "no such user" and "wrong
        # password" to avoid account enumeration.
        if user is None or not verify_password(password, user.password_hash):
            logger.info("login_failed email_domain=%s", email.split("@")[-1] if "@" in email else "-")
            raise UnauthorizedError("Invalid email or password.")
        if not user.is_active:
            logger.info("login_rejected_inactive_user user_id=%s", user.id)
            raise ForbiddenError("This account is inactive.")
        return user

    def issue_tokens(self, user: User) -> dict:
        settings = get_settings()
        access = create_access_token(
            str(user.id), user.role, str(user.college_id) if user.college_id else None
        )
        refresh, jti = create_refresh_token(str(user.id))
        session = RefreshSession(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(session)
        self.db.flush()
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    def login(self, email: str, password: str) -> tuple[User, dict]:
        user = self.authenticate(email, password)
        user.last_login_at = datetime.now(timezone.utc)
        tokens = self.issue_tokens(user)
        logger.info("login_success user_id=%s role=%s", user.id, user.role)
        return user, tokens

    def _get_session(self, jti: str) -> RefreshSession | None:
        stmt = select(RefreshSession).where(RefreshSession.jti == jti)
        return self.db.execute(stmt).scalar_one_or_none()

    def refresh(self, refresh_token: str) -> tuple[User, dict]:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except InvalidTokenError as exc:
            raise UnauthorizedError("Invalid or expired refresh token.") from exc

        session = self._get_session(payload.get("jti", ""))
        if session is None or session.revoked_at is not None:
            raise UnauthorizedError("This session has been revoked. Please log in again.")
        if session.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("This session has expired. Please log in again.")

        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Account is no longer active.")

        # Rotate: revoke the presented refresh token and issue a new pair.
        session.revoked_at = datetime.now(timezone.utc)
        tokens = self.issue_tokens(user)
        logger.info("token_refreshed user_id=%s", user.id)
        return user, tokens

    def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except InvalidTokenError:
            return  # logout is idempotent even for an already-invalid token
        session = self._get_session(payload.get("jti", ""))
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            logger.info("logout user_id=%s", session.user_id)
