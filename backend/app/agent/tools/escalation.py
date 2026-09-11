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
from app.models.support import SupportTicket


def create_support_ticket(
    ctx: ToolContext, *, subject: str, description: str, priority: str = "normal",
) -> ToolResult:
    ticket = SupportTicket(
        college_id=ctx.college_id,
        student_id=ctx.student_id,
        conversation_id=ctx.conversation_id,
        subject=subject,
        description=description,
        priority=priority if priority in ("low", "normal", "high", "urgent") else "normal",
        status="open",
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    return ToolResult.ok({"ticket_id": str(ticket.id), "status": ticket.status})


def escalate_to_counselor(ctx: ToolContext, *, reason: str, priority: str = "normal") -> ToolResult:
    ticket = SupportTicket(
        college_id=ctx.college_id,
        student_id=ctx.student_id,
        conversation_id=ctx.conversation_id,
        category="counselor_escalation",
        subject="Counselor escalation requested",
        description=reason,
        priority=priority if priority in ("low", "normal", "high", "urgent") else "normal",
        status="open",
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    return ToolResult.ok({
        "ticket_id": str(ticket.id),
        "status": "escalation_requested",
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
