from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("college_id", "code", name="uq_course_college_code"),)

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    degree_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_years: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    total_seats: Mapped[int | None] = mapped_column(nullable=True)
    annual_fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    application_fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    hostel_fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fee_academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    eligibility_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    admission_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    placement_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    hostel_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)


class CourseEligibilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_eligibility_rules"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True
    )
    minimum_percentage: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    required_qualification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    required_subjects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    entrance_exam_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entrance_exam_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    minimum_entrance_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    additional_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Scholarship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scholarships"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    application_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)


class AdmissionDate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admission_dates"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")


class RequiredDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "required_documents"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
