"""Tool: get_fee_structure (docs/agent-tools.md section 13)."""
from __future__ import annotations

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.agent.tools.courses import resolve_course


def get_fee_structure(ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None) -> ToolResult:
    course = resolve_course(ctx, course_id=course_id, course_query=course_query)
    if course is None:
        return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")
    if course.annual_fee is None:
        return ToolResult.fail("KNOWLEDGE_NOT_FOUND", "No fee has been configured for this course yet.")

    return ToolResult.ok({
        "course_id": str(course.id),
        "course_name": course.name,
        "tuition_fee": float(course.annual_fee),
        "application_fee": float(course.application_fee) if course.application_fee is not None else None,
        "hostel_fee": float(course.hostel_fee) if course.hostel_fee is not None else None,
        "currency": "INR",
        "academic_year": course.fee_academic_year,
    })
