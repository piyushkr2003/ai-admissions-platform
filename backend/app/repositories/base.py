"""Tenant-scoped repository base class.

Every repository for a college-owned entity should extend this class so
that tenant filtering is enforced in exactly one place rather than
re-implemented (and potentially forgotten) in each service.
"""
from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, college_id: uuid.UUID, entity_id: uuid.UUID) -> ModelT | None:
        """Fetch a single row, scoped to the given college.

        Returns None both when the row does not exist and when it belongs
        to a different college - the caller must not be able to
        distinguish "not found" from "belongs to another tenant".
        """
        stmt = select(self.model).where(
            self.model.id == entity_id,  # type: ignore[attr-defined]
            self.model.college_id == college_id,  # type: ignore[attr-defined]
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, college_id: uuid.UUID, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = (
            select(self.model)
            .where(self.model.college_id == college_id)  # type: ignore[attr-defined]
            .order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        self.db.flush()
        return entity
