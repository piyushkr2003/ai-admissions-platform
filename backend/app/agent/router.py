"""Admin-facing agent configuration and test endpoints
(docs/api-contract.md sections 61-62)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.colleges.context import get_college_context
from app.core.errors import NotFoundError, ValidationAppError
from app.core.responses import envelope
from app.db.session import get_db
from app.models.agent_config import AgentConfig
from app.models.conversations import Conversation
from app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])


def _config_out(config: AgentConfig) -> dict:
    return {
        "id": str(config.id),
        "agent_name": config.agent_name,
        "personality": config.personality,
        "default_language": config.default_language,
        "supported_languages": config.supported_languages,
        "greeting_message": config.greeting_message,
        "fallback_message": config.fallback_message,
        "escalation_message": config.escalation_message,
        "lead_scoring_config": config.lead_scoring_config,
        "active": config.active,
    }


@router.get("/config")
def get_agent_config(
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent_config:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    config = db.execute(select(AgentConfig).where(AgentConfig.college_id == tenant_id)).scalar_one_or_none()
    if config is None:
        raise NotFoundError("Agent configuration has not been created for this college yet.")
    return envelope(_config_out(config))


@router.patch("/config")
def update_agent_config(
    payload: dict,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent_config:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    config = db.execute(select(AgentConfig).where(AgentConfig.college_id == tenant_id)).scalar_one_or_none()
    if config is None:
        raise NotFoundError("Agent configuration has not been created for this college yet.")

    allowed = {
        "agent_name", "personality", "default_language", "supported_languages",
        "greeting_message", "fallback_message", "escalation_message",
        "lead_scoring_config", "active",
    }
    for key, value in payload.items():
        if key in allowed:
            setattr(config, key, value)
    db.commit()
    return envelope(_config_out(config))


@router.post("/test")
def test_agent(
    payload: dict,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent_config:read")),
) -> dict:
    message = payload.get("message")
    if not message:
        raise ValidationAppError("'message' is required.")

    tenant_id = resolve_tenant_college_id(user, college_id)
    context = get_college_context(db, tenant_id)
    if context is None:
        raise NotFoundError("College not found.")

    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = db.get(Conversation, uuid.UUID(conversation_id))
        if conversation is None or conversation.college_id != tenant_id:
            raise NotFoundError("Conversation not found.")
    else:
        conversation = Conversation(
            college_id=tenant_id, channel="admin_test", session_id=uuid.uuid4().hex,
            status="active", started_at=datetime.now(timezone.utc), language=context.default_language,
            state={},
        )
        db.add(conversation)
        db.flush()

    orchestrator = AgentOrchestrator(db, context)
    result = orchestrator.handle_message(conversation, message)
    db.commit()

    return envelope({
        "response": result.response_text,
        "tools_used": result.tools_used,
        "intents": result.intents,
        "conversation_id": str(conversation.id),
    })
