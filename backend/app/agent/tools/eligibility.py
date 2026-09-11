"""Tool: check_eligibility (docs/agent-tools.md section 12)."""
from __future__ import annotations

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.agent.tools.courses import resolve_course
from app.services.eligibility import EligibilityService


def check_eligibility(
    ctx: ToolContext,
    *,
    course_id: str | None = None,
    course_query: str | None = None,
    percentage: float | None = None,
    entrance_score: float | None = None,
    qualification: str | None = None,
) -> ToolResult:
    course = resolve_course(ctx, course_id=course_id, course_query=course_query)
    if course is None:
        return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    service = EligibilityService(ctx.db)
    result = service.check(
        college_id=ctx.college_id, course_id=course.id, percentage=percentage,
        entrance_score=entrance_score, qualification=qualification,
    )
    return ToolResult.ok({
        "course_id": str(course.id),
        "course_name": course.name,
        "status": result.status,
        "reasons": result.reasons,
        "missing_information": result.missing_information,
    })
