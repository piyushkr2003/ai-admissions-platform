"""Tool: get_course_details, plus course resolution used by other tools
(docs/agent-tools.md section 11)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.models.academics import Course
from app.services.courses import find_course_by_query


def resolve_course(ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None) -> Course | None:
    if course_id:
        try:
            course = ctx.db.get(Course, uuid.UUID(course_id))
        except ValueError:
            course = None
        if course is not None and course.college_id == ctx.college_id and course.status == "active":
            return course
        return None

    if not course_query:
        return None

    return find_course_by_query(ctx.db, ctx.college_id, course_query)


def list_active_courses(ctx: ToolContext) -> list[Course]:
    stmt = select(Course).where(Course.college_id == ctx.college_id, Course.status == "active")
    return list(ctx.db.execute(stmt).scalars().all())


def get_course_details(ctx: ToolContext, *, course_id: str | None = None, course_query: str | None = None) -> ToolResult:
    course = resolve_course(ctx, course_id=course_id, course_query=course_query)
    if course is None:
        return ToolResult.fail("NOT_FOUND", "That course could not be found for this college.")
    return ToolResult.ok({
        "course_id": str(course.id),
        "name": course.name,
        "code": course.code,
        "degree_type": course.degree_type,
        "department": course.department,
        "duration_years": float(course.duration_years) if course.duration_years is not None else None,
        "description": course.description,
        "active": course.status == "active",
        "hostel_available": course.hostel_available,
    })
