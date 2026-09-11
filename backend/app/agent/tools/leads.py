"""Tools: create_lead, update_lead, calculate_lead_score
(docs/agent-tools.md sections 21-23)."""
from __future__ import annotations

import uuid

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.core.errors import AppError
from app.services.leads import LeadService


def create_lead(ctx: ToolContext, *, course_id: str | None = None, source: str = "voice_agent") -> ToolResult:
    service = LeadService(ctx.db)
    student = service.get_or_create_student(ctx.college_id, ctx.student_id)
    lead, created = service.get_or_create_lead(
        ctx.college_id, student.id, source=source, course_id=uuid.UUID(course_id) if course_id else None,
    )
    return ToolResult.ok({
        "lead_id": str(lead.id),
        "student_id": str(student.id),
        "status": lead.status,
        "created": created,
        "score": lead.lead_score,
        "temperature": lead.lead_temperature,
    })


def update_lead(ctx: ToolContext, *, lead_id: str, **fields) -> ToolResult:
    service = LeadService(ctx.db)
    try:
        lead_uuid = uuid.UUID(lead_id)
    except ValueError:
        return ToolResult.fail("VALIDATION_ERROR", "Invalid lead_id.")

    try:
        lead = service.get_lead_or_404(ctx.college_id, lead_uuid)
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)

    allowed = {"course_id", "intent", "next_action", "notes", "hostel_interest", "scholarship_interest", "parent_involvement"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    service.update_lead_fields(lead, **updates)
    updated_fields = list(updates.keys())

    new_status = fields.get("status")
    if new_status:
        try:
            service.transition_status(lead, new_status)
        except AppError as exc:
            return ToolResult.fail(exc.code, exc.message)
        updated_fields.append("status")

    return ToolResult.ok({"lead_id": str(lead.id), "updated_fields": updated_fields, "status": lead.status})


def calculate_lead_score(ctx: ToolContext, *, lead_id: str, event_type: str | None = None, reason: str = "") -> ToolResult:
    service = LeadService(ctx.db)
    try:
        lead_uuid = uuid.UUID(lead_id)
    except ValueError:
        return ToolResult.fail("VALIDATION_ERROR", "Invalid lead_id.")

    try:
        lead = service.get_lead_or_404(ctx.college_id, lead_uuid)
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)

    if event_type:
        result = service.record_event_and_rescore(lead, event_type, reason)
    else:
        result = service.recalculate_score(lead)
    return ToolResult.ok(result)
