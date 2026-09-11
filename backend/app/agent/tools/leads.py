"""Tools: create_lead, update_lead, calculate_lead_score
(docs/agent-tools.md sections 21-23)."""
from __future__ import annotations

import uuid

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
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

    from app.models.leads import Lead
    lead = ctx.db.get(Lead, lead_uuid)
    if lead is None or lead.college_id != ctx.college_id:
        return ToolResult.fail("NOT_FOUND", "Lead not found for this college.")

    allowed = {"course_id", "status", "intent", "next_action", "notes", "hostel_interest", "scholarship_interest", "parent_involvement"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    service.update_lead_fields(lead, **updates)
    return ToolResult.ok({"lead_id": str(lead.id), "updated_fields": list(updates.keys())})


def calculate_lead_score(ctx: ToolContext, *, lead_id: str, event_type: str | None = None, reason: str = "") -> ToolResult:
    service = LeadService(ctx.db)
    try:
        lead_uuid = uuid.UUID(lead_id)
    except ValueError:
        return ToolResult.fail("VALIDATION_ERROR", "Invalid lead_id.")

    from app.models.leads import Lead
    lead = ctx.db.get(Lead, lead_uuid)
    if lead is None or lead.college_id != ctx.college_id:
        return ToolResult.fail("NOT_FOUND", "Lead not found for this college.")

    if event_type:
        result = service.record_event_and_rescore(lead, event_type, reason)
    else:
        result = service.recalculate_score(lead)
    return ToolResult.ok(result)
