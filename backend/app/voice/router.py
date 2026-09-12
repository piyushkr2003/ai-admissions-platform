"""Voice session API (docs/voice.md section 8).

Two trust models, matching the rest of this codebase's conventions:

- Session lifecycle endpoints (create/get/events/end) are intentionally
  unauthenticated, exactly like POST /conversations - a prospective
  caller has no account. The session_id (an unguessable UUID) and the
  transport `connection_token` are the capability tokens. college_id in
  the create-session request only selects which college's public agent
  to talk to (the same trust boundary as picking which college's website
  to visit); it is never used to read or write another tenant's data,
  and every subsequent call is scoped to the session's own resolved
  college_id, never a client-supplied one.
- Staff-facing listing/administration requires the existing
  `voice_sessions:read`/`voice_sessions:write` permissions and resolves
  the tenant from trusted auth context via `resolve_tenant_college_id`,
  identically to every other admin resource in this API.
- The telephony webhook is neither of the above: it authenticates the
  *caller* (the telephony provider) via signature verification instead
  of a bearer token or a capability UUID.
"""
from __future__ import annotations

import base64
import json
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.colleges.context import get_college_context
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, UnauthorizedError, ValidationAppError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.models.user import User
from app.models.voice import VoiceSession
from app.services.voice import VoiceSessionService
from app.voice.providers.factory import get_stt_provider, get_telephony_provider
from app.voice.schemas import VoiceEventCreate, VoiceSessionCreate, VoiceSessionEnd

router = APIRouter(prefix="/voice", tags=["voice"])


def _session_out(session: VoiceSession) -> dict:
    return {
        "id": str(session.id),
        "college_id": str(session.college_id),
        "conversation_id": str(session.conversation_id),
        "channel": session.channel,
        "provider": session.provider,
        "status": session.status,
        "turn_state": session.turn_state,
        "language": session.language,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "connected_at": session.connected_at.isoformat() if session.connected_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "duration_seconds": session.duration_seconds,
        "termination_reason": session.termination_reason,
    }


def _get_active_college_context(db: Session, college_id: str):
    try:
        college_uuid = uuid.UUID(college_id)
    except ValueError as exc:
        raise ValidationAppError("Invalid college_id.") from exc
    context = get_college_context(db, college_uuid)
    if context is None or not context.is_active:
        raise NotFoundError("This college is not currently available.")
    return context


# ---------------------------------------------------------------------------
# Web voice - public session lifecycle
# ---------------------------------------------------------------------------

@router.post("/sessions", status_code=201)
def create_session(payload: VoiceSessionCreate, db: Session = Depends(get_db)) -> dict:
    if payload.channel != "web_voice":
        raise ValidationAppError("Only 'web_voice' sessions may be created through this endpoint.")
    college = _get_active_college_context(db, payload.college_id)

    service = VoiceSessionService(db)
    try:
        session, conversation, credentials, greeting = service.create_web_session(college, language=payload.language)
    except AppError:
        db.rollback()
        raise
    db.commit()

    return envelope({
        "session_id": str(session.id),
        "conversation_id": str(conversation.id),
        "status": session.status,
        "language": session.language,
        "provider": session.provider,
        "server_url": credentials.server_url,
        "connection_token": credentials.connection_token,
        "connection_expires_at": credentials.expires_at.isoformat(),
        "ice_servers": credentials.ice_servers,
        "greeting": greeting,
    })


@router.get("/sessions/{session_id}")
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    session = VoiceSessionService(db).get_or_404(session_id)
    return envelope(_session_out(session))


@router.post("/sessions/{session_id}/events")
def post_event(session_id: uuid.UUID, payload: VoiceEventCreate, db: Session = Depends(get_db)) -> dict:
    service = VoiceSessionService(db)
    session = service.get_or_404(session_id)
    try:
        result = service.record_event(session, event_type=payload.event_type, text=payload.text, event_id=payload.event_id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(result)


@router.post("/sessions/{session_id}/end")
def end_session(session_id: uuid.UUID, payload: VoiceSessionEnd, db: Session = Depends(get_db)) -> dict:
    service = VoiceSessionService(db)
    session = service.get_or_404(session_id)
    service.end_session(session, reason=payload.reason or "completed")
    db.commit()
    return envelope(_session_out(session))


# ---------------------------------------------------------------------------
# Staff-facing administration
# ---------------------------------------------------------------------------

@router.get("/sessions")
def list_sessions(
    college_id: uuid.UUID | None = Query(default=None),
    channel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("voice_sessions:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    items, total = VoiceSessionService(db).list_sessions(
        tenant_id, channel=channel, status=status, page=page, page_size=page_size,
    )
    return collection_envelope([_session_out(s) for s in items], page=page, page_size=page_size, total=total)


@router.get("/sessions/{session_id}/admin")
def get_session_admin(
    session_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("voice_sessions:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    session = VoiceSessionService(db).get_or_404(session_id, college_id=tenant_id)
    return envelope(_session_out(session))


@router.post("/sessions/{session_id}/force-end")
def force_end_session(
    session_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("voice_sessions:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = VoiceSessionService(db)
    session = service.get_or_404(session_id, college_id=tenant_id)
    service.end_session(session, reason="staff_terminated")
    db.commit()
    return envelope(_session_out(session))


# ---------------------------------------------------------------------------
# Phone voice - telephony provider webhook
# ---------------------------------------------------------------------------

@router.post("/telephony/{provider_name}/inbound")
async def telephony_inbound(provider_name: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """`async def` only so the raw body can be read before signature
    verification (Starlette's Request.body() is a coroutine). Everything
    after that is synchronous DB work and is explicitly offloaded to the
    threadpool via run_in_threadpool - left inline, it would run directly
    on the event loop and block every other concurrent request on this
    worker for the duration of the webhook's database transaction."""
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await run_in_threadpool(_process_telephony_webhook, db, provider_name, headers, raw_body)


def _process_telephony_webhook(db: Session, provider_name: str, headers: dict, raw_body: bytes) -> dict:
    settings = get_settings()
    if provider_name.lower() != settings.telephony_provider.lower():
        raise NotFoundError("Unknown telephony provider.")

    telephony = get_telephony_provider()
    if not telephony.verify_webhook(headers=headers, raw_body=raw_body):
        raise UnauthorizedError("Webhook signature verification failed.")

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationAppError("Malformed webhook payload.") from exc

    event = telephony.parse_inbound_payload(payload)
    if not event.call_id:
        raise ValidationAppError("call_id is required.")

    service = VoiceSessionService(db)

    if event.event_type == "call_started":
        try:
            session, conversation, greeting, created = service.create_phone_session(
                provider_name=telephony.name, call_id=event.call_id,
                from_number=event.from_number, to_number=event.to_number, language=event.language,
            )
        except AppError:
            db.rollback()
            raise
        db.commit()
        return envelope({
            "session_id": str(session.id), "conversation_id": str(conversation.id),
            "status": session.status, "created": created, "greeting": greeting,
        })

    if event.event_type == "speech":
        session = service.get_by_provider_call_or_404(telephony.name, event.call_id)
        text = event.text
        if text is None and event.audio_base64:
            try:
                audio_bytes = base64.b64decode(event.audio_base64)
            except (ValueError, TypeError) as exc:
                raise ValidationAppError("Invalid audio_base64 payload.") from exc
            stt_result = get_stt_provider().recognize(audio_bytes, language=event.language or session.language)
            text = stt_result.text
        try:
            result = service.record_event(session, event_type="final_transcript", text=text, event_id=payload.get("event_id"))
        except AppError:
            db.rollback()
            raise
        db.commit()
        return envelope(result)

    if event.event_type == "call_ended":
        session = service.get_by_provider_call_or_404(telephony.name, event.call_id)
        service.end_session(session, reason="caller_hangup")
        db.commit()
        return envelope({"session_id": str(session.id), "status": session.status})

    raise ValidationAppError(f"Unknown event_type: {event.event_type}")
