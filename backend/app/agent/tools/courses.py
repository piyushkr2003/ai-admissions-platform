"""Tool: get_course_details, plus course resolution used by other tools
(docs/agent-tools.md section 11)."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.models.academics import Course

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


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

    query_tokens = _tokens(course_query)
    if not query_tokens:
        return None

    stmt = select(Course).where(Course.college_id == ctx.college_id, Course.status == "active")
    courses = ctx.db.execute(stmt).scalars().all()
    if not courses:
        return None

    if course_query.strip().lower() in {c.code.lower() for c in courses if c.code}:
        for course in courses:
            if course.code and course.code.lower() == course_query.strip().lower():
                return course

    best_course: Course | None = None
    best_score = 0
    for course in courses:
        score = 0
        if course.code:
            code_parts = [p for p in course.code.lower().split("-") if len(p) >= 2]
            score += sum(2 for p in code_parts if p in query_tokens)
        name_tokens = {t for t in _tokens(course.name) if len(t) >= 3}
        score += len(name_tokens & query_tokens)
        if score > best_score:
            best_score = score
            best_course = course

    return best_course if best_score >= 2 else None


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
