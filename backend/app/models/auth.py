from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class RefreshSession(UUIDPrimaryKeyMixin, Base):
    """A persisted, revocable refresh-token session.

    Only the token's jti is stored (not the raw token), so a leaked
    database row cannot itself be replayed as a bearer credential -
    the caller must still present a validly signed JWT with a matching jti.
    """

    __tablename__ = "refresh_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
