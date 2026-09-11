from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Student(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "students"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    date_of_birth: Mapped[Date | None] = mapped_column(Date, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qualification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualification_score: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    entrance_exam: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entrance_exam_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hostel_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    scholarship_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    parent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
