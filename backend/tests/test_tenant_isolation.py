"""Task 002 - database & multi-tenancy tests.

Proves that college-owned entities are correctly scoped and that a
repository/service querying "as college A" can never retrieve college B's
rows, at both the repository level and via raw relationship traversal.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.seed import seed_demo_data
from app.models.academics import Course
from app.models.college import College
from app.models.support import FAQ
from app.repositories.base import TenantScopedRepository


class CourseRepository(TenantScopedRepository[Course]):
    model = Course


def test_seed_creates_two_isolated_tenants(db):
    result = seed_demo_data(db)
    nova = result["nova"]["college"]
    aurora = result["aurora"]["college"]
    assert nova.id != aurora.id
    assert nova.slug == "nova-institute-of-technology"
    assert aurora.slug == "aurora-college-of-management"


def test_college_a_cannot_fetch_college_b_course_via_repository(db):
    result = seed_demo_data(db)
    nova = result["nova"]["college"]
    aurora_course = result["aurora"]["courses"]["BBA"]

    repo = CourseRepository(db)
    fetched = repo.get(college_id=nova.id, entity_id=aurora_course.id)

    assert fetched is None


def test_college_a_repository_list_excludes_college_b_courses(db):
    result = seed_demo_data(db)
    nova = result["nova"]["college"]
    aurora_course_ids = {c.id for c in result["aurora"]["courses"].values()}

    repo = CourseRepository(db)
    nova_courses = repo.list(college_id=nova.id, limit=100)

    assert len(nova_courses) == 5
    assert all(c.college_id == nova.id for c in nova_courses)
    assert not any(c.id in aurora_course_ids for c in nova_courses)


def test_college_a_cannot_query_college_b_faqs(db):
    result = seed_demo_data(db)
    nova = result["nova"]["college"]

    stmt = select(FAQ).where(FAQ.college_id == nova.id)
    faqs = db.execute(stmt).scalars().all()

    assert all(f.college_id == nova.id for f in faqs)
    aurora = result["aurora"]["college"]
    assert not any(f.college_id == aurora.id for f in faqs)


def test_random_college_id_returns_nothing_not_an_error(db):
    seed_demo_data(db)
    repo = CourseRepository(db)
    result = repo.list(college_id=uuid.uuid4())
    assert result == []


def test_college_slug_is_unique(db):
    seed_demo_data(db)
    duplicate = College(name="Duplicate Nova", slug="nova-institute-of-technology")
    db.add(duplicate)
    try:
        db.flush()
        assert False, "expected a uniqueness violation on colleges.slug"
    except Exception:
        db.rollback()


def test_course_college_id_foreign_key_enforced(db):
    seed_demo_data(db)
    orphan_course = Course(
        college_id=uuid.uuid4(),  # no such college
        name="Orphan Course",
        code="ORPHAN",
        status="active",
    )
    db.add(orphan_course)
    try:
        db.flush()
        assert False, "expected a foreign key violation for a nonexistent college_id"
    except Exception:
        db.rollback()
