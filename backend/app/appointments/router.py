"""Counselor & appointment API (docs/api-contract.md sections 24-25).

Tenant scoping follows the same pattern as every other feature router:
`resolve_tenant_college_id` derives the tenant from trusted auth context,
never from a client-supplied `college_id`. On top of that, a `counselor`
account is further row-scoped to its own linked Counselor record - per
docs/api-contract.md's RBAC table, a counselor's access to appointments is
"Assigned" (their own), not the whole college's, unlike college_admin/
admissions_staff/platform_admin which have "Full" access.
"""
from __future__ import annotations

import uuid
from datetime import date as date_, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.appointments.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentUpdate,
    AvailabilityWindowCreate,
    CounselorCreate,
    CounselorUpdate,
)
from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.models.academics import Course
from app.models.counseling import Appointment, Counselor, CounselorAvailability
from app.models.student import Student
from app.models.user import User
from app.services.appointments import AppointmentService

counselors_router = APIRouter(prefix="/counselors", tags=["counselors"])
appointments_router = APIRouter(prefix="/appointments", tags=["appointments"])

_STAFF_MANAGER_ROLES = {"platform_admin", "college_admin", "admissions_staff"}


def _own_counselor_scope(db: Session, tenant_id: uuid.UUID, user: User) -> uuid.UUID | None:
    """None for college-wide roles. The user's own counselor_id when the
    caller is a `counselor` account - raises if that account has no
    linked Counselor row, rather than silently granting/denying access to
    an unrelated resource."""
    if user.role != "counselor":
        return None
    service = AppointmentService(db)
    counselor = service.get_counselor_for_user(tenant_id, user.id)
    if counselor is None:
        raise ForbiddenError("This account is not linked to a counselor profile.")
    return counselor.id


def _counselor_out(counselor: Counselor) -> dict:
    return {
        "id": str(counselor.id),
        "college_id": str(counselor.college_id),
        "user_id": str(counselor.user_id) if counselor.user_id else None,
        "name": counselor.name,
        "email": counselor.email,
        "phone": counselor.phone,
        "specialization": counselor.specialization,
        "active": counselor.active,
        "created_at": counselor.created_at.isoformat(),
        "updated_at": counselor.updated_at.isoformat(),
    }


def _window_out(window: CounselorAvailability) -> dict:
    return {
        "id": str(window.id),
        "counselor_id": str(window.counselor_id),
        "day_of_week": window.day_of_week,
        "start_time": window.start_time.isoformat(),
        "end_time": window.end_time.isoformat(),
        "timezone": window.timezone,
        "active": window.active,
    }


def _appointment_out(db: Session, appointment: Appointment) -> dict:
    student = db.get(Student, appointment.student_id)
    counselor = db.get(Counselor, appointment.counselor_id)
    course = db.get(Course, appointment.course_id) if appointment.course_id else None
    return {
        "id": str(appointment.id),
        "college_id": str(appointment.college_id),
        "student_id": str(appointment.student_id),
        "student_name": student.full_name if student else None,
        "counselor_id": str(appointment.counselor_id),
        "counselor_name": counselor.name if counselor else None,
        "course_id": str(appointment.course_id) if appointment.course_id else None,
        "course_name": course.name if course else None,
        "start_time": appointment.start_time.isoformat(),
        "end_time": appointment.end_time.isoformat(),
        "status": appointment.status,
        "meeting_type": appointment.meeting_type,
        "meeting_link": appointment.meeting_link,
        "notes": appointment.notes,
        "cancellation_reason": appointment.cancellation_reason,
        "source": appointment.source,
        "created_at": appointment.created_at.isoformat(),
        "updated_at": appointment.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Counselors
# ---------------------------------------------------------------------------

@counselors_router.get("")
def list_counselors(
    college_id: uuid.UUID | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = AppointmentService(db)
    items = service.list_counselors(tenant_id, active_only=active_only)
    return envelope([_counselor_out(c) for c in items])


@counselors_router.post("", status_code=201)
def create_counselor(
    payload: CounselorCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    if user.role not in _STAFF_MANAGER_ROLES:
        raise ForbiddenError("Only college staff may create counselor profiles.")
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = AppointmentService(db)
    try:
        counselor = service.create_counselor(
            tenant_id, name=payload.name, email=payload.email, phone=payload.phone,
            specialization=payload.specialization, user_id=payload.user_id,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_counselor_out(counselor))


def _get_counselor_or_404(db: Session, tenant_id: uuid.UUID, counselor_id: uuid.UUID) -> Counselor:
    return AppointmentService(db).get_counselor_or_404(tenant_id, counselor_id)


def _require_own_counselor_or_staff(user: User, counselor: Counselor) -> None:
    if user.role in _STAFF_MANAGER_ROLES:
        return
    if user.role == "counselor" and counselor.user_id == user.id:
        return
    raise ForbiddenError("You may only manage your own counselor profile.")


@counselors_router.get("/{counselor_id}")
def get_counselor(
    counselor_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    counselor = _get_counselor_or_404(db, tenant_id, counselor_id)
    return envelope(_counselor_out(counselor))


@counselors_router.patch("/{counselor_id}")
def update_counselor(
    counselor_id: uuid.UUID,
    payload: CounselorUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    counselor = _get_counselor_or_404(db, tenant_id, counselor_id)
    _require_own_counselor_or_staff(user, counselor)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if user.role == "counselor":
        data.pop("active", None)  # a counselor cannot deactivate their own account
    service = AppointmentService(db)
    service.update_counselor(counselor, **data)
    db.commit()
    return envelope(_counselor_out(counselor))


@counselors_router.get("/{counselor_id}/availability")
def get_counselor_availability(
    counselor_id: uuid.UUID,
    date: date_ | None = Query(default=None),
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    _get_counselor_or_404(db, tenant_id, counselor_id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=tenant_id, preferred_date=date, counselor_id=counselor_id)
    return envelope({
        "counselor_id": str(counselor_id),
        "slots": [
            {"start_time": s.start_time.isoformat(), "duration_minutes": s.duration_minutes}
            for s in slots
        ],
    })


@counselors_router.get("/{counselor_id}/availability-windows")
def list_availability_windows(
    counselor_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    counselor = _get_counselor_or_404(db, tenant_id, counselor_id)
    service = AppointmentService(db)
    windows = service.list_availability_windows(counselor)
    return envelope([_window_out(w) for w in windows])


@counselors_router.post("/{counselor_id}/availability-windows", status_code=201)
def add_availability_window(
    counselor_id: uuid.UUID,
    payload: AvailabilityWindowCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    counselor = _get_counselor_or_404(db, tenant_id, counselor_id)
    _require_own_counselor_or_staff(user, counselor)
    service = AppointmentService(db)
    try:
        window = service.add_availability_window(
            counselor, day_of_week=payload.day_of_week, start_time=payload.start_time,
            end_time=payload.end_time, window_timezone=payload.timezone,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_window_out(window))


@counselors_router.delete("/{counselor_id}/availability-windows/{window_id}", status_code=200)
def remove_availability_window(
    counselor_id: uuid.UUID,
    window_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    counselor = _get_counselor_or_404(db, tenant_id, counselor_id)
    _require_own_counselor_or_staff(user, counselor)
    service = AppointmentService(db)
    window = service.get_availability_window_or_404(counselor, window_id)
    service.remove_availability_window(window)
    db.commit()
    return envelope({"success": True})


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

@appointments_router.get("")
def list_appointments(
    college_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    counselor_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    course_id: uuid.UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    effective_counselor_id = own_scope if own_scope is not None else counselor_id

    service = AppointmentService(db)
    items, total = service.list_appointments(
        tenant_id, status=status, counselor_id=effective_counselor_id, student_id=student_id,
        course_id=course_id, from_date=from_, to_date=to, page=page, page_size=page_size,
    )
    return collection_envelope(
        [_appointment_out(db, a) for a in items], page=page, page_size=page_size, total=total
    )


@appointments_router.post("", status_code=201)
def create_appointment(
    payload: AppointmentCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    if own_scope is not None and payload.counselor_id != own_scope:
        raise ForbiddenError("A counselor may only book appointments under their own profile.")

    service = AppointmentService(db)
    try:
        appointment = service.book_appointment(
            college_id=tenant_id, student_id=payload.student_id, counselor_id=payload.counselor_id,
            start_time=payload.start_time, duration_minutes=payload.duration_minutes,
            course_id=payload.course_id, purpose=payload.purpose, source="admin",
            idempotency_key=payload.idempotency_key, actor_user_id=user.id,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_appointment_out(db, appointment))


def _get_appointment_scoped_or_404(
    db: Session, tenant_id: uuid.UUID, appointment_id: uuid.UUID, own_scope: uuid.UUID | None,
) -> Appointment:
    service = AppointmentService(db)
    appointment = service.get_or_404(tenant_id, appointment_id)
    if own_scope is not None and appointment.counselor_id != own_scope:
        # Never reveal that another counselor's appointment exists.
        raise NotFoundError("Appointment not found.")
    return appointment


@appointments_router.get("/{appointment_id}")
def get_appointment(
    appointment_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    appointment = _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    return envelope(_appointment_out(db, appointment))


@appointments_router.patch("/{appointment_id}")
def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    appointment = _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    service = AppointmentService(db)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    service.update_details(appointment, **data)
    db.commit()
    return envelope(_appointment_out(db, appointment))


@appointments_router.patch("/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentReschedule,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    service = AppointmentService(db)
    try:
        appointment = service.reschedule(tenant_id, appointment_id, payload.new_start_time, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_appointment_out(db, appointment))


@appointments_router.post("/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancel,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    service = AppointmentService(db)
    try:
        appointment = service.cancel(tenant_id, appointment_id, payload.reason, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_appointment_out(db, appointment))


@appointments_router.post("/{appointment_id}/complete")
def complete_appointment(
    appointment_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    service = AppointmentService(db)
    try:
        appointment = service.complete(tenant_id, appointment_id, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_appointment_out(db, appointment))


@appointments_router.post("/{appointment_id}/no-show")
def mark_no_show(
    appointment_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("appointments:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    own_scope = _own_counselor_scope(db, tenant_id, user)
    _get_appointment_scoped_or_404(db, tenant_id, appointment_id, own_scope)
    service = AppointmentService(db)
    try:
        appointment = service.mark_no_show(tenant_id, appointment_id, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_appointment_out(db, appointment))
