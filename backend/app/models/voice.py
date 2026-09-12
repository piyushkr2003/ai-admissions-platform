"""Voice session records (docs/voice.md sections 6-7).

A voice session is the channel-neutral wrapper around one web or phone
voice interaction; it always owns exactly one Conversation, so
transcript/message history lives in the existing conversations/messages
tables rather than being duplicated here.
"""
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VOICE_CHANNELS = ("web_voice", "phone_voice")
VOICE_SESSION_STATUSES = ("created", "connecting", "active", "ending", "completed", "failed")
VOICE_TURN_STATES = ("idle", "listening", "processing", "speaking")


class VoiceSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        # NULLs are distinct in Postgres unique indexes, so this only
        # constrains real phone calls (provider_call_id not null) -
        # concurrent web sessions never collide against it.
        UniqueConstraint("provider", "provider_call_id", name="uq_voice_session_provider_call"),
        # Serves analytics date-range queries (Task 013).
        Index("ix_voice_sessions_college_created", "college_id", "created_at"),
    )

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, unique=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="mock")
    provider_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created", index=True)
    turn_state: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    caller_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Idempotency for the most recent inbound event only - enough to make
    # an exact webhook/event retry a safe no-op replay without a growing
    # side table (section 18).
    last_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    session_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
