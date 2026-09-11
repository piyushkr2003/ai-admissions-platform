"""Request schemas for the support ticket & escalation API
(docs/api-contract.md sections 54-55/63)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    student_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=100)
    priority: str = Field(default="normal", max_length=30)
    idempotency_key: str | None = Field(default=None, max_length=255)


class EscalationCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)
    student_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    priority: str = Field(default="normal", max_length=30)
    idempotency_key: str | None = Field(default=None, max_length=255)


class SupportTicketUpdate(BaseModel):
    """PATCH /support-tickets/{id}. `status` and `assigned_to` are each
    independently optional - a caller may update assignment, status, or
    both in the same request."""

    status: str | None = None
    assigned_to: uuid.UUID | None = None
    priority: str | None = None
    resolution_notes: str | None = Field(default=None, max_length=5000)
