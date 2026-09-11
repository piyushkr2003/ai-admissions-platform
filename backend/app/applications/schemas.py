"""Request schemas for the application assistance & management API
(docs/api-contract.md sections 29-31)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    student_id: uuid.UUID
    course_id: uuid.UUID
    intake: str | None = Field(default=None, max_length=20)
    idempotency_key: str | None = Field(default=None, max_length=255)


class ApplicationUpdate(BaseModel):
    """PATCH /applications/{id}. `status` is a staff-driven lifecycle
    move (e.g. under_review -> approved) validated against the same
    transition graph submit()/withdraw() use; intake/notes are only
    editable while the application is still a draft."""

    intake: str | None = None
    notes: str | None = None
    status: str | None = None


class ApplicationSubmit(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=255)


class ApplicationWithdraw(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ApplicationDocumentCreate(BaseModel):
    document_type: str = Field(min_length=1, max_length=100)
    file_name: str | None = Field(default=None, max_length=255)
    file_url: str | None = Field(default=None, max_length=2000)


class ApplicationDocumentStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=50)
