"""Tools: create_support_ticket, escalate_to_counselor, send_confirmation
(docs/agent-tools.md sections 26-28).

send_confirmation talks to a NotificationProvider adapter. No real SMS/
email provider is configured in this scope (that belongs to a later
integrations task) - the adapter always reports an honest
"not configured" failure rather than pretending a message went out,
per "never claim a message was delivered if delivery failed."
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.models.support import TICKET_PRIORITIES
from app.services.support import SupportTicketService


def _safe_priority(priority: str) -> str:
    """The agent must never crash a conversation turn over a malformed
    priority value - normalize defensively here; the REST API validates
    strictly instead (docs/tasks/010)."""
    return priority if priority in TICKET_PRIORITIES else "normal"


def create_support_ticket(
    ctx: ToolContext, *, subject: str, description: str, priority: str = "normal",
) -> ToolResult:
    service = SupportTicketService(ctx.db)
    ticket, _created = service.create_ticket(
        ctx.college_id, subject=subject, description=description, priority=_safe_priority(priority),
        student_id=ctx.student_id, conversation_id=ctx.conversation_id,
    )
    return ToolResult.ok({"ticket_id": str(ticket.id), "status": ticket.status})


def escalate_to_counselor(ctx: ToolContext, *, reason: str, priority: str = "normal") -> ToolResult:
    service = SupportTicketService(ctx.db)
    ticket, _created = service.escalate_to_counselor(
        ctx.college_id, reason=reason, priority=_safe_priority(priority),
        student_id=ctx.student_id, conversation_id=ctx.conversation_id,
    )
    return ToolResult.ok({
        "ticket_id": str(ticket.id),
        "status": ticket.status,
        "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        "live_transfer_completed": False,
    })


class NotificationProvider(ABC):
    @abstractmethod
    def send(self, *, channel: str, recipient_hint: str, message: str) -> tuple[bool, str]:
        """Returns (delivered, status_message)."""
        raise NotImplementedError


class UnconfiguredNotificationProvider(NotificationProvider):
    def send(self, *, channel: str, recipient_hint: str, message: str) -> tuple[bool, str]:
        return False, "No notification provider is configured for this environment."


def get_notification_provider() -> NotificationProvider:
    return UnconfiguredNotificationProvider()


def send_confirmation(ctx: ToolContext, *, confirmation_type: str, resource_id: str, channel: str = "sms") -> ToolResult:
    provider = get_notification_provider()
    delivered, status_message = provider.send(
        channel=channel, recipient_hint=str(ctx.student_id or ""), message=f"{confirmation_type}:{resource_id}"
    )
    if not delivered:
        return ToolResult.fail("RESOURCE_UNAVAILABLE", status_message)
    return ToolResult.ok({"delivered": True, "channel": channel})
