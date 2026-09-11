from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

LEAD_STATUSES = (
    "new",
    "qualifying",
    "qualified",
    "contacted",
    "appointment_booked",
    "application_started",
    "converted",
    "lost",
)
LEAD_TEMPERATURES = ("cold", "warm", "hot")


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new", index=True)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lead_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    lead_temperature: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="voice_agent")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    hostel_interest: Mapped[bool | None] = mapped_column(nullable=True)
    scholarship_interest: Mapped[bool | None] = mapped_column(nullable=True)
    parent_involvement: Mapped[bool | None] = mapped_column(nullable=True)
    last_contacted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadScoreEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "lead_score_events"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
