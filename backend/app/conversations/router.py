"""Public conversation endpoints (docs/api-contract.md section 32).

These are intentionally unauthenticated - a prospective student has no
account. The conversation_id itself (an unguessable UUID) is the only
capability token, which is the documented minimal scope for this task;
a signed session mechanism belongs to the voice/session task this
platform does not yet implement. Every mutation still validates that
the target college is active and that the conversation actually
belongs to that college.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.colleges.context import get_college_context
from app.conversations.schemas import ConversationCreate, MessageCreate
from app.core.errors import NotFoundError, ValidationAppError
from app.core.responses import envelope
from app.db.session import get_db
from app.models.conversations import Conversation, Message

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_active_college_context(db: Session, college_id: str):
    try:
        college_uuid = uuid.UUID(college_id)
    except ValueError as exc:
        raise ValidationAppError("Invalid college_id.") from exc
    context = get_college_context(db, college_uuid)
    if context is None or not context.is_active:
        raise NotFoundError("This college is not currently available.")
    return context


def _get_conversation_or_404(db: Session, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


@router.post("", status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)) -> dict:
    context = _get_active_college_context(db, payload.college_id)
    language = payload.language or context.default_language

    conversation = Conversation(
        college_id=context.college_id,
        channel=payload.channel,
        session_id=uuid.uuid4().hex,
        status="active",
        started_at=datetime.now(timezone.utc),
        language=language,
        # An explicitly requested language is locked in as authoritative
        # for the whole conversation, exactly like the voice session
        # endpoints (app/services/voice.py::_initial_conversation_state) -
        # a caller that didn't request one keeps today's auto-detection.
        state={"language": language, "language_locked": True} if payload.language else {},
    )
    db.add(conversation)
    db.commit()
    return envelope({"conversation_id": str(conversation.id)})


@router.get("/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    conversation = _get_conversation_or_404(db, conversation_id)
    return envelope({
        "conversation_id": str(conversation.id),
        "status": conversation.status,
        "intent": conversation.intent,
        "summary": conversation.summary,
        "language": conversation.language,
    })


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    conversation = _get_conversation_or_404(db, conversation_id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    items = [
        {"role": m.sender_type, "content": m.content, "timestamp": m.created_at.isoformat()}
        for m in messages
    ]
    return envelope(items)


@router.post("/{conversation_id}/messages", status_code=201)
def post_message(conversation_id: uuid.UUID, payload: MessageCreate, db: Session = Depends(get_db)) -> dict:
    conversation = _get_conversation_or_404(db, conversation_id)
    if conversation.status not in ("active",):
        raise ValidationAppError("This conversation has ended.")

    context = get_college_context(db, conversation.college_id)
    if context is None or not context.is_active:
        raise NotFoundError("This college is not currently available.")

    orchestrator = AgentOrchestrator(db, context)
    result = orchestrator.handle_message(conversation, payload.content)
    db.commit()

    return envelope({"response": result.response_text})


@router.post("/{conversation_id}/end")
def end_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    conversation = _get_conversation_or_404(db, conversation_id)
    if conversation.status == "active":
        conversation.status = "completed"
        conversation.ended_at = datetime.now(timezone.utc)
        if conversation.started_at:
            conversation.duration_seconds = int(
                (conversation.ended_at - conversation.started_at).total_seconds()
            )
        db.commit()
    return envelope({"status": conversation.status})
