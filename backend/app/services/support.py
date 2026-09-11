"""Human escalation & support ticket lifecycle (docs/database.md section
26, docs/api-contract.md sections 54-55/63, docs/tasks/010 - human
escalation & support tickets).

Every ticket is the single record of "something needs a human" - a
general support request and a counselor escalation both create the same
SupportTicket row (differentiated by `category`), so staff work one
queue rather than two disconnected concepts. Escalation may
best-effort auto-assign an active counselor, but the AI must never
describe that as a completed live transfer - only that a ticket was
created and, where a counselor was actually found, who it was handed to.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.counseling import Counselor
from app.models.support import TICKET_PRIORITIES, TICKET_STATUSES, SupportTicket
from app.models.user import User
from app.services.audit import record_audit

logger = logging.getLogger("app.support")

TERMINAL_TICKET_STATUSES = ("closed",)

# Explicit transition graph - a ticket queue is not a strictly linear
# pipeline (a resolved issue can recur, a closed ticket can be reopened).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"assigned", "in_progress", "resolved", "closed"},
    "assigned": {"in_progress", "open", "resolved", "closed"},
    "in_progress": {"assigned", "resolved", "closed"},
    "resolved": {"in_progress", "closed"},
    "closed": {"open"},
}


def is_allowed_ticket_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in ALLOWED_TRANSITIONS.get(current, set())


class SupportTicketService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_ticket(
        self,
        college_id: uuid.UUID,
        *,
        subject: str,
        description: str | None = None,
        student_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        category: str | None = None,
        priority: str = "normal",
        idempotency_key: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> tuple[SupportTicket, bool]:
        if priority not in TICKET_PRIORITIES:
            raise ValidationAppError(f"Unknown priority: {priority}")
        if not subject or not subject.strip():
            raise ValidationAppError("subject is required.")

        if idempotency_key:
            existing = self.db.execute(
                select(SupportTicket).where(
                    SupportTicket.college_id == college_id, SupportTicket.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing, False

        ticket = SupportTicket(
            college_id=college_id,
            student_id=student_id,
            conversation_id=conversation_id,
            category=category,
            subject=subject.strip(),
            description=description,
            priority=priority,
            status="open",
            idempotency_key=idempotency_key,
        )
        self.db.add(ticket)
        self.db.flush()

        logger.info("support_ticket.created ticket_id=%s college_id=%s category=%s priority=%s", ticket.id, college_id, category, priority)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="support_ticket.created",
            entity_type="support_ticket", entity_id=ticket.id,
        )
        return ticket, True

    def _least_loaded_assignable_counselor(self, college_id: uuid.UUID) -> Counselor | None:
        """Pick the active, login-linked counselor with the fewest
        currently open/assigned/in_progress tickets - simple, deterministic
        load balancing, not a scheduling optimizer."""
        counselors = list(self.db.execute(
            select(Counselor).where(
                Counselor.college_id == college_id, Counselor.active.is_(True), Counselor.user_id.isnot(None),
            )
        ).scalars().all())
        if not counselors:
            return None

        open_counts = dict(self.db.execute(
            select(SupportTicket.assigned_to, func.count(SupportTicket.id))
            .where(
                SupportTicket.college_id == college_id,
                SupportTicket.status.in_(("open", "assigned", "in_progress")),
                SupportTicket.assigned_to.isnot(None),
            )
            .group_by(SupportTicket.assigned_to)
        ).all())

        return min(counselors, key=lambda c: open_counts.get(c.user_id, 0))

    def escalate_to_counselor(
        self,
        college_id: uuid.UUID,
        *,
        reason: str,
        student_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        priority: str = "normal",
        idempotency_key: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> tuple[SupportTicket, bool]:
        """Record an escalation to human assistance
        (docs/api-contract.md section 55): reason, conversation, student,
        college, timestamp, and status are always recorded; an assigned
        counselor is recorded only when one was actually found and set -
        never claimed otherwise."""
        ticket, created = self.create_ticket(
            college_id, subject="Counselor escalation requested", description=reason,
            student_id=student_id, conversation_id=conversation_id, category="counselor_escalation",
            priority=priority, idempotency_key=idempotency_key, actor_user_id=actor_user_id,
        )
        if not created:
            return ticket, False

        counselor = self._least_loaded_assignable_counselor(college_id)
        if counselor is not None:
            ticket.assigned_to = counselor.user_id
            ticket.status = "assigned"
            self.db.flush()
            logger.info("support_ticket.assigned ticket_id=%s counselor_id=%s", ticket.id, counselor.id)

        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="escalation.created",
            entity_type="support_ticket", entity_id=ticket.id,
            meta={"assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None},
        )
        return ticket, True

    # ------------------------------------------------------------------
    # Retrieval / listing
    # ------------------------------------------------------------------

    def get_or_404(self, college_id: uuid.UUID, ticket_id: uuid.UUID) -> SupportTicket:
        ticket = self.db.get(SupportTicket, ticket_id)
        if ticket is None or ticket.college_id != college_id:
            raise NotFoundError("Support ticket not found for this college.")
        return ticket

    _SORT_COLUMNS = {
        "newest": (SupportTicket.created_at, "desc"),
        "oldest": (SupportTicket.created_at, "asc"),
        "recently_updated": (SupportTicket.updated_at, "desc"),
        "priority": (SupportTicket.priority, "desc"),
    }

    def list_tickets(
        self,
        college_id: uuid.UUID,
        *,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        assigned_to: uuid.UUID | None = None,
        unassigned_only: bool = False,
        visible_to_user_id: uuid.UUID | None = None,
        student_id: uuid.UUID | None = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[SupportTicket], int]:
        conditions = [SupportTicket.college_id == college_id]
        if status:
            conditions.append(SupportTicket.status == status)
        if priority:
            conditions.append(SupportTicket.priority == priority)
        if category:
            conditions.append(SupportTicket.category == category)
        if student_id:
            conditions.append(SupportTicket.student_id == student_id)
        if visible_to_user_id is not None:
            # Row-scoped visibility (e.g. a counselor): their own tickets
            # plus the unassigned queue, never someone else's ticket.
            conditions.append(
                (SupportTicket.assigned_to == visible_to_user_id) | (SupportTicket.assigned_to.is_(None))
            )
        elif unassigned_only:
            conditions.append(SupportTicket.assigned_to.is_(None))
        elif assigned_to:
            conditions.append(SupportTicket.assigned_to == assigned_to)

        total = self.db.execute(select(func.count()).select_from(SupportTicket).where(*conditions)).scalar_one()
        column, direction = self._SORT_COLUMNS.get(sort, self._SORT_COLUMNS["newest"])
        order = column.desc() if direction == "desc" else column.asc()
        stmt = (
            select(SupportTicket)
            .where(*conditions)
            .order_by(order, SupportTicket.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    # ------------------------------------------------------------------
    # Assignment / lifecycle
    # ------------------------------------------------------------------

    def assign_ticket(self, ticket: SupportTicket, *, assignee_user_id: uuid.UUID, actor_user_id: uuid.UUID | None = None) -> SupportTicket:
        assignee = self.db.get(User, assignee_user_id)
        if assignee is None or (assignee.college_id is not None and assignee.college_id != ticket.college_id):
            raise ValidationAppError("assigned_to must be a staff account belonging to this college.")
        if ticket.status in TERMINAL_TICKET_STATUSES:
            raise ConflictError("Cannot assign a closed ticket.")

        previous = ticket.assigned_to
        ticket.assigned_to = assignee_user_id
        if ticket.status == "open":
            ticket.status = "assigned"
        self.db.flush()
        logger.info("support_ticket.assigned ticket_id=%s assigned_to=%s", ticket.id, assignee_user_id)
        record_audit(
            self.db, college_id=ticket.college_id, user_id=actor_user_id, action="support_ticket.assigned",
            entity_type="support_ticket", entity_id=ticket.id,
            meta={"from": str(previous) if previous else None, "to": str(assignee_user_id)},
        )
        return ticket

    @staticmethod
    def _append_note(existing: str | None, addition: str) -> str:
        stamp = datetime.now(timezone.utc).isoformat()
        entry = f"[{stamp}] {addition.strip()}"
        return f"{existing}\n{entry}" if existing else entry

    def transition_status(
        self, ticket: SupportTicket, new_status: str, *, resolution_notes: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> SupportTicket:
        if new_status not in TICKET_STATUSES:
            raise ValidationAppError(f"Unknown ticket status: {new_status}")
        if not is_allowed_ticket_transition(ticket.status, new_status):
            raise ConflictError(
                f"Cannot transition ticket from '{ticket.status}' to '{new_status}'.",
                details={"code": "INVALID_STATUS_TRANSITION"},
            )
        previous = ticket.status
        if resolution_notes:
            ticket.description = self._append_note(ticket.description, resolution_notes)
        if previous == new_status:
            self.db.flush()
            return ticket

        ticket.status = new_status
        ticket.resolved_at = datetime.now(timezone.utc) if new_status == "resolved" else (
            None if new_status in ("open", "assigned", "in_progress") else ticket.resolved_at
        )
        self.db.flush()
        logger.info("support_ticket.status_changed ticket_id=%s from=%s to=%s", ticket.id, previous, new_status)
        record_audit(
            self.db, college_id=ticket.college_id, user_id=actor_user_id, action="support_ticket.status_changed",
            entity_type="support_ticket", entity_id=ticket.id, meta={"from": previous, "to": new_status},
        )
        return ticket
