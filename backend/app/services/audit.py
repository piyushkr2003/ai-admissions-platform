"""Shared audit-log recording helper.

Every service that performs a sensitive mutation should call this instead
of constructing AuditLog rows ad hoc, so the fields captured stay
consistent (docs/database.md section 27, docs/api-contract.md section 68).
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.support import AuditLog


def record_audit(
    db: Session,
    *,
    college_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        college_id=college_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta or {},
    )
    db.add(entry)
    db.flush()
    return entry
