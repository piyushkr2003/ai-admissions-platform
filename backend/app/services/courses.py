"""Free-text course matching, scoped to one college.

Shared by the agent's course-resolution tool (app/agent/tools/courses.py)
and the leads API, which accepts a free-text `course_interest` per
docs/api-contract.md section 26 - the matching heuristic lives in exactly
one place so the two callers cannot silently diverge.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import Course

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def find_course_by_query(db: Session, college_id: uuid.UUID, course_query: str) -> Course | None:
    query_tokens = _tokens(course_query)
    if not query_tokens:
        return None

    stmt = select(Course).where(Course.college_id == college_id, Course.status == "active")
    courses = db.execute(stmt).scalars().all()
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
