from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_configs"

    college_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("colleges.id"), nullable=False, unique=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Admissions Assistant")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str] = mapped_column(String(100), nullable=False, default="friendly_professional")
    voice_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_language: Mapped[str] = mapped_column(String(20), nullable=False, default="en")
    supported_languages: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["en"])
    greeting_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    lead_scoring_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    business_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
