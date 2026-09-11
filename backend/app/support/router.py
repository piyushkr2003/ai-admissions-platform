"""Human escalation & support ticket API (docs/api-contract.md sections
54-55/63).

Tenant scoping and RBAC follow the same pattern as every other feature
router - `resolve_tenant_college_id` derives the tenant from trusted
auth context, and `support_tickets:read`/`support_tickets:write`
(app/auth/permissions.py) give platform_admin/college_admin/
admissions_staff full access. A `counselor` account additionally gets
row-scoped visibility: their own assigned tickets plus the unassigned
queue (so they can see and claim new escalations), never a ticket
already assigned to someone else - mirroring the "assigned" row-scoping
pattern Task 008 established for appointments.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.errors import AppError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.models.support import TICKET_PRIORITIES, SupportTicket
from app.models.user import User
from app.services.support import SupportTicketService
from app.support.schemas import EscalationCreate, SupportTicketCreate, SupportTicketUpdate

router = APIRouter(prefix="/support-tickets", tags=["support"])

_STAFF_MANAGER_ROLES = {"platform_admin", "college_admin", "admissions_staff"}


def _ticket_out(ticket: SupportTicket) -> dict:
    return {
        "id": str(ticket.id),
        "college_id": str(ticket.college_id),
        "student_id": str(ticket.student_id) if ticket.student_id else None,
        "conversation_id": str(ticket.conversation_id) if ticket.conversation_id else None,
        "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        "category": ticket.category,
        "subject": ticket.subject,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }


def _visibility_scope(user: User) -> uuid.UUID | None:
    """None = unrestricted (staff-manager roles / platform_admin). A
    user id = row-scoped to that user's own tickets plus the unassigned
    queue."""
    if user.role in _STAFF_MANAGER_ROLES:
        return None
    return user.id


def _get_ticket_scoped_or_404(db: Session, tenant_id: uuid.UUID, ticket_id: uuid.UUID, user: User) -> SupportTicket:
    ticket = SupportTicketService(db).get_or_404(tenant_id, ticket_id)
    scope = _visibility_scope(user)
    if scope is not None and ticket.assigned_to not in (None, scope):
        # Never reveal that another staff member's ticket exists.
        raise NotFoundError("Support ticket not found.")
    return ticket


@router.get("")
def list_tickets(
    college_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    unassigned_only: bool = Query(default=False),
    student_id: uuid.UUID | None = Query(default=None),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support_tickets:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    scope = _visibility_scope(user)
    service = SupportTicketService(db)
    items, total = service.list_tickets(
        tenant_id, status=status, priority=priority, category=category,
        assigned_to=None if scope is not None else assigned_to,
        unassigned_only=False if scope is not None else unassigned_only,
        visible_to_user_id=scope, student_id=student_id, sort=sort, page=page, page_size=page_size,
    )
    return collection_envelope([_ticket_out(t) for t in items], page=page, page_size=page_size, total=total)


@router.post("", status_code=201)
def create_ticket(
    payload: SupportTicketCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support_tickets:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = SupportTicketService(db)
    try:
        ticket, _created = service.create_ticket(
            tenant_id, subject=payload.subject, description=payload.description,
            student_id=payload.student_id, conversation_id=payload.conversation_id,
            category=payload.category, priority=payload.priority,
            idempotency_key=payload.idempotency_key, actor_user_id=user.id,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_ticket_out(ticket))


@router.post("/escalate", status_code=201)
def create_escalation(
    payload: EscalationCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support_tickets:write")),
) -> dict:
    """Staff-initiated equivalent of the agent's escalate_to_counselor
    tool - e.g. a phone call logged manually by an admissions officer."""
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = SupportTicketService(db)
    try:
        ticket, _created = service.escalate_to_counselor(
            tenant_id, reason=payload.reason, student_id=payload.student_id,
            conversation_id=payload.conversation_id, priority=payload.priority,
            idempotency_key=payload.idempotency_key, actor_user_id=user.id,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_ticket_out(ticket))


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support_tickets:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    ticket = _get_ticket_scoped_or_404(db, tenant_id, ticket_id, user)
    return envelope(_ticket_out(ticket))


@router.patch("/{ticket_id}")
def update_ticket(
    ticket_id: uuid.UUID,
    payload: SupportTicketUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("support_tickets:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    ticket = _get_ticket_scoped_or_404(db, tenant_id, ticket_id, user)
    service = SupportTicketService(db)
    is_staff_manager = user.role in _STAFF_MANAGER_ROLES

    try:
        if payload.assigned_to is not None:
            if not is_staff_manager and payload.assigned_to != user.id:
                raise ForbiddenError("You may only assign a ticket to yourself.")
            service.assign_ticket(ticket, assignee_user_id=payload.assigned_to, actor_user_id=user.id)

        if payload.priority is not None:
            if payload.priority not in TICKET_PRIORITIES:
                raise ValidationAppError(f"Unknown priority: {payload.priority}")
            ticket.priority = payload.priority
            db.flush()

        if payload.status is not None:
            service.transition_status(
                ticket, payload.status, resolution_notes=payload.resolution_notes, actor_user_id=user.id,
            )
        elif payload.resolution_notes:
            service.transition_status(
                ticket, ticket.status, resolution_notes=payload.resolution_notes, actor_user_id=user.id,
            )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_ticket_out(ticket))
