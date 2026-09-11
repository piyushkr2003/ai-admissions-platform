"""Tools: get_admission_requirements, get_required_documents, admission
dates (docs/agent-tools.md sections 15-16)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.agent.tools.courses import resolve_course
from app.models.academics import AdmissionDate, RequiredDocument


def get_admission_requirements(
    ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None
) -> ToolResult:
    course = resolve_course(ctx, course_id=course_id, course_query=course_query)
    if course is None:
        return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    return ToolResult.ok({
        "course_id": str(course.id),
        "course_name": course.name,
        "eligibility_summary": course.eligibility_summary,
        "admission_process": course.admission_process,
    })


def get_required_documents(
    ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None
) -> ToolResult:
    course = None
    if course_id or course_query:
        course = resolve_course(ctx, course_id=course_id, course_query=course_query)
        if course is None:
            return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    stmt = select(RequiredDocument).where(RequiredDocument.college_id == ctx.college_id)
    if course is not None:
        stmt = stmt.where(
            (RequiredDocument.course_id == course.id) | (RequiredDocument.course_id.is_(None))
        )
    else:
        stmt = stmt.where(RequiredDocument.course_id.is_(None))
    documents = list(ctx.db.execute(stmt).scalars().all())

    if not documents:
        return ToolResult.fail("KNOWLEDGE_NOT_FOUND", "No document checklist is configured yet.")

    return ToolResult.ok({
        "documents": [{"name": d.name, "required": d.mandatory} for d in documents]
    })


def get_admission_dates(
    ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None
) -> ToolResult:
    course = None
    if course_id or course_query:
        course = resolve_course(ctx, course_id=course_id, course_query=course_query)
        if course is None:
            return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")

    now = datetime.now(timezone.utc)
    stmt = select(AdmissionDate).where(
        AdmissionDate.college_id == ctx.college_id, AdmissionDate.status == "active"
    )
    if course is not None:
        stmt = stmt.where(
            (AdmissionDate.course_id == course.id) | (AdmissionDate.course_id.is_(None))
        )
    stmt = stmt.order_by(AdmissionDate.date.asc())
    dates = [d for d in ctx.db.execute(stmt).scalars().all() if d.date >= now][:5]

    if not dates:
        return ToolResult.fail("KNOWLEDGE_NOT_FOUND", "No upcoming admission dates are configured.")

    return ToolResult.ok({
        "dates": [
            {"title": d.title, "date": d.date.date().isoformat(), "date_type": d.date_type}
            for d in dates
        ]
    })
