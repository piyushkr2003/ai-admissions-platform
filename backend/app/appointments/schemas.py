"""Request schemas for the counselor & appointment API
(docs/api-contract.md sections 24-25, docs/database.md sections 13-15)."""
from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field, field_validator


def _require_timezone_aware(value: datetime) -> datetime:
    """Appointment APIs must always preserve timezone information
    (docs/api-contract.md section 77) - a naive datetime is ambiguous
    about which instant it means and is rejected outright rather than
    silently assumed to be any particular zone."""
    if value.tzinfo is None:
        raise ValueError("must include a UTC offset, e.g. 2026-09-20T15:00:00+05:30")
    return value


class CounselorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    specialization: str | None = Field(default=None, max_length=255)
    user_id: uuid.UUID | None = None


class CounselorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    specialization: str | None = None
    active: bool | None = None


class AvailabilityWindowCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time
    timezone: str = Field(default="Asia/Kolkata", max_length=100)


class AppointmentCreate(BaseModel):
    student_id: uuid.UUID
    counselor_id: uuid.UUID
    start_time: datetime
    duration_minutes: int = Field(default=30, ge=15, le=180)
    course_id: uuid.UUID | None = None
    purpose: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=255)

    _validate_start_time = field_validator("start_time")(_require_timezone_aware)


class AppointmentReschedule(BaseModel):
    new_start_time: datetime

    _validate_new_start_time = field_validator("new_start_time")(_require_timezone_aware)


class AppointmentUpdate(BaseModel):
    notes: str | None = None
    meeting_type: str | None = Field(default=None, max_length=50)
    meeting_link: str | None = None


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
