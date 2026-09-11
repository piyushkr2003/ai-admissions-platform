"""Tools: create_application, get_application_status
(docs/agent-tools.md sections 24-25)."""
from __future__ import annotations

import uuid

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.agent.tools.courses import resolve_course
from app.core.errors import AppError
from app.services.applications import ApplicationService


def create_application(
    ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None,
    intake: str | None = None, idempotency_key: str | None = None,
) -> ToolResult:
    if ctx.student_id is None:
        return ToolResult.fail("VALIDATION_ERROR", "A student profile is required before applying.")

    course = resolve_course(ctx, course_id=course_id, course_query=course_query)
    if course is None:
        return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    service = ApplicationService(ctx.db)
    try:
        application, created = service.create_draft(
            college_id=ctx.college_id, student_id=ctx.student_id, course_id=course.id,
            intake=intake, idempotency_key=idempotency_key,
        )
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)

    return ToolResult.ok({
        "application_id": str(application.id),
        "status": application.status,
        "course_name": course.name,
        "created": created,
    })


def get_application_status(ctx: ToolContext, *, application_id: str) -> ToolResult:
    service = ApplicationService(ctx.db)
    try:
        application = service.get_or_404(ctx.college_id, uuid.UUID(application_id))
    except (AppError, ValueError) as exc:
        code = getattr(exc, "code", "VALIDATION_ERROR")
        message = getattr(exc, "message", "Invalid application_id.")
        return ToolResult.fail(code, message)

    return ToolResult.ok({
        "application_id": str(application.id),
        "status": application.status,
        "completion_percentage": application.completion_percentage,
        "next_steps": service.next_steps(application),
    })
