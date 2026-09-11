"""Tools: check_counselor_availability, book_appointment,
reschedule_appointment, cancel_appointment (docs/agent-tools.md 17-20).

Booking must only ever report success after the backend actually
persists the appointment (docs/tasks/006 section 28).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.core.errors import AppError
from app.services.appointments import AppointmentService


def check_counselor_availability(
    ctx: ToolContext,
    *,
    preferred_date: date | None = None,
    time_range: tuple[time, time] | None = None,
) -> ToolResult:
    service = AppointmentService(ctx.db)
    slots = service.check_availability(
        college_id=ctx.college_id, preferred_date=preferred_date, time_range=time_range
    )
    return ToolResult.ok({
        "slots": [
            {
                "counselor_id": str(s.counselor_id),
                "counselor_name": s.counselor_name,
                "start_time": s.start_time.isoformat(),
                "duration_minutes": s.duration_minutes,
            }
            for s in slots
        ]
    })


def book_appointment(
    ctx: ToolContext,
    *,
    counselor_id: str,
    start_time: datetime,
    duration_minutes: int = 30,
    course_id: str | None = None,
    purpose: str | None = None,
    idempotency_key: str | None = None,
) -> ToolResult:
    if ctx.student_id is None:
        return ToolResult.fail("VALIDATION_ERROR", "A student profile is required before booking.")

    service = AppointmentService(ctx.db)
    try:
        appointment = service.book_appointment(
            college_id=ctx.college_id,
            student_id=ctx.student_id,
            counselor_id=uuid.UUID(counselor_id),
            start_time=start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc),
            duration_minutes=duration_minutes,
            course_id=uuid.UUID(course_id) if course_id else None,
            purpose=purpose,
            idempotency_key=idempotency_key,
        )
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)

    return ToolResult.ok({
        "appointment_id": str(appointment.id),
        "status": appointment.status,
        "confirmation": {
            "date": appointment.start_time.date().isoformat(),
            "time": appointment.start_time.strftime("%H:%M"),
            "counselor_id": str(appointment.counselor_id),
        },
    })


def reschedule_appointment(ctx: ToolContext, *, appointment_id: str, new_start_time: datetime) -> ToolResult:
    service = AppointmentService(ctx.db)
    try:
        appointment = service.reschedule(
            college_id=ctx.college_id,
            appointment_id=uuid.UUID(appointment_id),
            new_start_time=new_start_time if new_start_time.tzinfo else new_start_time.replace(tzinfo=timezone.utc),
        )
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)
    return ToolResult.ok({"appointment_id": str(appointment.id), "status": appointment.status,
                           "start_time": appointment.start_time.isoformat()})


def cancel_appointment(ctx: ToolContext, *, appointment_id: str, reason: str | None = None) -> ToolResult:
    service = AppointmentService(ctx.db)
    try:
        appointment = service.cancel(ctx.college_id, uuid.UUID(appointment_id), reason)
    except AppError as exc:
        return ToolResult.fail(exc.code, exc.message)
    return ToolResult.ok({"appointment_id": str(appointment.id), "status": appointment.status})
