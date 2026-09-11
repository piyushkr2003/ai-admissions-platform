"""Request/response schemas for the lead intelligence API
(docs/api-contract.md section 26, docs/tasks/007 section 24)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    """Explicit create schema - only fields a caller may set. college_id/
    id/score/temperature/timestamps are always server-derived."""

    student_id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    course_id: uuid.UUID | None = None
    course_interest: str | None = Field(default=None, max_length=255)
    qualification: str | None = Field(default=None, max_length=255)
    qualification_score: float | None = None
    entrance_exam: str | None = Field(default=None, max_length=255)
    entrance_exam_score: float | None = None
    budget: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    hostel_interest: bool | None = None
    scholarship_interest: bool | None = None
    parent_involvement: bool | None = None
    parent_name: str | None = Field(default=None, max_length=255)
    parent_phone: str | None = Field(default=None, max_length=50)
    intent: str | None = None
    source: str = Field(default="admin", max_length=50)
    notes: str | None = None


class LeadUpdate(BaseModel):
    """PATCH /leads/{lead_id} - partial update. Fields left unset are
    never touched; empty/blank values are ignored rather than clearing
    existing data (docs/tasks/007 section 18)."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None
    course_id: uuid.UUID | None = None
    course_interest: str | None = None
    qualification: str | None = None
    qualification_score: float | None = None
    entrance_exam: str | None = None
    entrance_exam_score: float | None = None
    budget: str | None = None
    location: str | None = None
    hostel_interest: bool | None = None
    scholarship_interest: bool | None = None
    parent_involvement: bool | None = None
    parent_name: str | None = None
    parent_phone: str | None = None
    intent: str | None = None
    status: str | None = None
    notes: str | None = None
    next_action: str | None = None
    last_contacted_at: datetime | None = None
