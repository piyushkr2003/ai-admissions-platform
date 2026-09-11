"""Tool: get_scholarship_information (docs/agent-tools.md section 14)."""
from __future__ import annotations

from sqlalchemy import or_, select

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.agent.tools.courses import resolve_course
from app.models.academics import Scholarship


def get_scholarship_information(
    ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None
) -> ToolResult:
    course = None
    if course_id or course_query:
        course = resolve_course(ctx, course_id=course_id, course_query=course_query)
        if course is None:
            return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    stmt = select(Scholarship).where(
        Scholarship.college_id == ctx.college_id, Scholarship.status == "active"
    )
    if course is not None:
        stmt = stmt.where(or_(Scholarship.course_id == course.id, Scholarship.course_id.is_(None)))
    scholarships = list(ctx.db.execute(stmt).scalars().all())

    if not scholarships:
        return ToolResult.fail("KNOWLEDGE_NOT_FOUND", "No scholarship is currently configured.")

    return ToolResult.ok({
        "scholarships": [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "eligibility_criteria": s.eligibility_criteria,
                "amount": float(s.amount) if s.amount is not None else None,
                "percentage": float(s.percentage) if s.percentage is not None else None,
                "application_required": s.application_required,
                "deadline": s.deadline.isoformat() if s.deadline else None,
            }
            for s in scholarships
        ]
    })
