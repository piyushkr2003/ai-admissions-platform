"""CollegeContext: the normalized, validated college representation later
consumed by the AI agent, RAG, appointment, and application systems
(Task 004 section 35). Downstream code should depend on this rather than
querying college/agent_config tables directly.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.agent_config import AgentConfig
from app.models.college import College


@dataclass(frozen=True)
class CollegeContext:
    college_id: uuid.UUID
    name: str
    slug: str
    timezone: str
    supported_languages: list[str]
    default_language: str
    status: str
    feature_flags: dict
    agent_config_id: uuid.UUID | None
    contact_email: str | None
    contact_phone: str | None

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def feature_enabled(self, flag: str) -> bool:
        return bool(self.feature_flags.get(flag, False))


def get_college_context(db: Session, college_id: uuid.UUID) -> CollegeContext | None:
    college = db.get(College, college_id)
    if college is None:
        return None
    agent_config = db.query(AgentConfig).filter(AgentConfig.college_id == college_id).one_or_none()
    return CollegeContext(
        college_id=college.id,
        name=college.name,
        slug=college.slug,
        timezone=college.timezone,
        supported_languages=list(college.supported_languages or []),
        default_language=college.default_language,
        status=college.status,
        feature_flags=dict(college.feature_flags or {}),
        agent_config_id=agent_config.id if agent_config else None,
        contact_email=college.email,
        contact_phone=college.phone,
    )
