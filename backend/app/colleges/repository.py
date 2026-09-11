from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.academics import Course
from app.models.agent_config import AgentConfig
from app.models.college import College
from app.models.knowledge import KnowledgeSource


class CollegeRepository:
    """Colleges are the tenant root, not a tenant-owned entity, so this
    repository does not extend TenantScopedRepository."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, college_id: uuid.UUID) -> College | None:
        return self.db.get(College, college_id)

    def get_by_slug(self, slug: str) -> College | None:
        stmt = select(College).where(College.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> list[College]:
        stmt = select(College).order_by(College.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, college: College) -> College:
        self.db.add(college)
        self.db.flush()
        return college

    def has_active_course(self, college_id: uuid.UUID) -> bool:
        stmt = select(func.count()).select_from(Course).where(
            Course.college_id == college_id, Course.status == "active"
        )
        return (self.db.execute(stmt).scalar_one() or 0) > 0

    def knowledge_source_count(self, college_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(KnowledgeSource).where(
            KnowledgeSource.college_id == college_id
        )
        return self.db.execute(stmt).scalar_one() or 0

    def has_agent_config(self, college_id: uuid.UUID) -> bool:
        stmt = select(func.count()).select_from(AgentConfig).where(
            AgentConfig.college_id == college_id
        )
        return (self.db.execute(stmt).scalar_one() or 0) > 0
