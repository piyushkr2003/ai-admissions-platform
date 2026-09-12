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

    # Voice/telephony configuration (Task 011, docs/voice.md section 13).
    # The inbound phone number is a real column (not buried in the JSON
    # blob below) because webhook-time tenant resolution needs a fast,
    # unique lookup - every other voice setting is low-cardinality and
    # rarely queried, so it lives in one JSON blob rather than a wide
    # column list, matching the lead_scoring_config/business_hours
    # convention already used on this table.
    voice_phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True, index=True)
    voice_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
