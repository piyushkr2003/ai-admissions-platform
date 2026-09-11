"""Counselor availability and transactional appointment booking
(docs/architecture.md section 13, docs/database.md sections 13-15,
docs/tasks/008 - counselor availability & appointments).

Booking must never silently double-book a counselor. The (counselor_id,
start_time) unique constraint added in Task 002's migration is the
final safety net against a race between two concurrent bookings; the
application-level checks here exist to produce a clear, user-facing
error instead of a raw database exception in the common case.

Appointment outcomes are wired into the Task 007 lead-intelligence
subsystem here (not duplicated in the REST router or the agent tools):
a successful booking/reschedule/cancellation enriches an *existing*
active lead for the student, but this service never creates a lead on
its own - a staff-initiated booking with no prior lead is not, by
itself, evidence of a new admissions prospect. Lead updates are
best-effort: a scoring failure must never roll back a real, persisted
appointment (docs/api-contract.md: "creating an appointment and sending
a notification are separate concerns").
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date as date_, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.academics import Course
from app.models.counseling import Appointment, Counselor, CounselorAvailability
from app.services.audit import record_audit
from app.services.lead_signals import notify_lead as _notify_lead

logger = logging.getLogger("app.appointments")

SLOT_MINUTES = 30
_ACTIVE_STATUSES = ("scheduled",)


@dataclass
class AvailableSlot:
    counselor_id: uuid.UUID
    counselor_name: str
    start_time: datetime
    duration_minutes: int = SLOT_MINUTES


class AppointmentService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Counselors
    # ------------------------------------------------------------------

    def list_counselors(self, college_id: uuid.UUID, *, active_only: bool = True) -> list[Counselor]:
        stmt = select(Counselor).where(Counselor.college_id == college_id)
        if active_only:
            stmt = stmt.where(Counselor.active.is_(True))
        stmt = stmt.order_by(Counselor.name.asc())
        return list(self.db.execute(stmt).scalars().all())

    def get_counselor_or_404(self, college_id: uuid.UUID, counselor_id: uuid.UUID) -> Counselor:
        counselor = self.db.get(Counselor, counselor_id)
        if counselor is None or counselor.college_id != college_id:
            raise NotFoundError("Counselor not found for this college.")
        return counselor

    def get_counselor_for_user(self, college_id: uuid.UUID, user_id: uuid.UUID) -> Counselor | None:
        stmt = select(Counselor).where(Counselor.college_id == college_id, Counselor.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_counselor(
        self, college_id: uuid.UUID, *, name: str, email: str | None = None, phone: str | None = None,
        specialization: str | None = None, user_id: uuid.UUID | None = None,
    ) -> Counselor:
        counselor = Counselor(
            college_id=college_id, name=name, email=email, phone=phone,
            specialization=specialization, user_id=user_id, active=True,
        )
        try:
            with self.db.begin_nested():
                self.db.add(counselor)
                self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "A counselor with this email already exists for this college.",
                details={"code": "COUNSELOR_ALREADY_EXISTS"},
            ) from exc
        logger.info("counselor.created counselor_id=%s college_id=%s", counselor.id, college_id)
        return counselor

    def update_counselor(self, counselor: Counselor, **fields) -> Counselor:
        allowed = {"name", "email", "phone", "specialization", "active"}
        changed = False
        for key, value in fields.items():
            if key not in allowed or value is None:
                continue
            if getattr(counselor, key) != value:
                setattr(counselor, key, value)
                changed = True
        if changed:
            self.db.flush()
            logger.info("counselor.updated counselor_id=%s", counselor.id)
        return counselor

    # ------------------------------------------------------------------
    # Availability windows (recurring weekly schedule)
    # ------------------------------------------------------------------

    def list_availability_windows(self, counselor: Counselor, *, active_only: bool = True) -> list[CounselorAvailability]:
        stmt = select(CounselorAvailability).where(CounselorAvailability.counselor_id == counselor.id)
        if active_only:
            stmt = stmt.where(CounselorAvailability.active.is_(True))
        stmt = stmt.order_by(CounselorAvailability.day_of_week.asc(), CounselorAvailability.start_time.asc())
        return list(self.db.execute(stmt).scalars().all())

    def add_availability_window(
        self, counselor: Counselor, *, day_of_week: int, start_time: time, end_time: time,
        window_timezone: str = "Asia/Kolkata",
    ) -> CounselorAvailability:
        if not (0 <= day_of_week <= 6):
            raise ValidationAppError("day_of_week must be between 0 (Monday) and 6 (Sunday).")
        if end_time <= start_time:
            raise ValidationAppError("end_time must be after start_time.")
        window = CounselorAvailability(
            college_id=counselor.college_id, counselor_id=counselor.id, day_of_week=day_of_week,
            start_time=start_time, end_time=end_time, timezone=window_timezone, active=True,
        )
        self.db.add(window)
        self.db.flush()
        logger.info("counselor.availability_added counselor_id=%s day_of_week=%s", counselor.id, day_of_week)
        return window

    def get_availability_window_or_404(self, counselor: Counselor, window_id: uuid.UUID) -> CounselorAvailability:
        window = self.db.get(CounselorAvailability, window_id)
        if window is None or window.counselor_id != counselor.id:
            raise NotFoundError("Availability window not found for this counselor.")
        return window

    def remove_availability_window(self, window: CounselorAvailability) -> None:
        window.active = False
        self.db.flush()
        logger.info("counselor.availability_removed counselor_id=%s window_id=%s", window.counselor_id, window.id)

    # ------------------------------------------------------------------
    # Availability search
    # ------------------------------------------------------------------

    def _active_counselors(self, college_id: uuid.UUID, counselor_id: uuid.UUID | None) -> list[Counselor]:
        stmt = select(Counselor).where(Counselor.college_id == college_id, Counselor.active.is_(True))
        if counselor_id is not None:
            stmt = stmt.where(Counselor.id == counselor_id)
        return list(self.db.execute(stmt).scalars().all())

    def check_availability(
        self,
        *,
        college_id: uuid.UUID,
        preferred_date: date_ | None = None,
        time_range: tuple[time, time] | None = None,
        counselor_id: uuid.UUID | None = None,
        days_ahead: int = 5,
        max_slots: int = 8,
    ) -> list[AvailableSlot]:
        counselors = self._active_counselors(college_id, counselor_id)
        if not counselors:
            return []

        dates = [preferred_date] if preferred_date else [
            (datetime.now(timezone.utc).date() + timedelta(days=i)) for i in range(1, days_ahead + 1)
        ]

        slots: list[AvailableSlot] = []
        for counselor in counselors:
            tzinfo = ZoneInfo(self._availability_timezone(counselor))
            existing_starts = self._booked_start_times(counselor.id)
            for day in dates:
                weekday = day.weekday()
                windows = self._availability_windows(counselor.id, weekday)
                for window_start, window_end in windows:
                    cursor = datetime.combine(day, window_start, tzinfo=tzinfo)
                    end = datetime.combine(day, window_end, tzinfo=tzinfo)
                    while cursor + timedelta(minutes=SLOT_MINUTES) <= end:
                        if time_range is None or (time_range[0] <= cursor.time() <= time_range[1]):
                            if cursor > datetime.now(tzinfo) and cursor.astimezone(timezone.utc) not in existing_starts:
                                slots.append(AvailableSlot(counselor.id, counselor.name, cursor))
                                if len(slots) >= max_slots:
                                    return slots
                        cursor += timedelta(minutes=SLOT_MINUTES)
        return slots

    def _availability_timezone(self, counselor: Counselor) -> str:
        stmt = select(CounselorAvailability.timezone).where(
            CounselorAvailability.counselor_id == counselor.id
        ).limit(1)
        tz = self.db.execute(stmt).scalar_one_or_none()
        return tz or "Asia/Kolkata"

    def _availability_windows(self, counselor_id: uuid.UUID, weekday: int) -> list[tuple[time, time]]:
        stmt = select(CounselorAvailability.start_time, CounselorAvailability.end_time).where(
            CounselorAvailability.counselor_id == counselor_id,
            CounselorAvailability.day_of_week == weekday,
            CounselorAvailability.active.is_(True),
        )
        return [(row[0], row[1]) for row in self.db.execute(stmt).all()]

    def _booked_start_times(self, counselor_id: uuid.UUID) -> set[datetime]:
        stmt = select(Appointment.start_time).where(
            Appointment.counselor_id == counselor_id, Appointment.status.in_(_ACTIVE_STATUSES)
        )
        return {row[0].astimezone(timezone.utc) for row in self.db.execute(stmt).all()}

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------

    def _validate_common(
        self, college_id: uuid.UUID, student_id: uuid.UUID, counselor_id: uuid.UUID,
        course_id: uuid.UUID | None = None,
    ) -> Counselor:
        from app.models.student import Student

        student = self.db.get(Student, student_id)
        if student is None or student.college_id != college_id:
            raise NotFoundError("Student not found for this college.")
        counselor = self.db.get(Counselor, counselor_id)
        if counselor is None or counselor.college_id != college_id or not counselor.active:
            raise NotFoundError("Counselor not found or not available for this college.")
        if course_id is not None:
            course = self.db.get(Course, course_id)
            if course is None or course.college_id != college_id:
                raise ValidationAppError("course_id does not belong to this college.")
        return counselor

    def book_appointment(
        self,
        *,
        college_id: uuid.UUID,
        student_id: uuid.UUID,
        counselor_id: uuid.UUID,
        start_time: datetime,
        duration_minutes: int = SLOT_MINUTES,
        course_id: uuid.UUID | None = None,
        purpose: str | None = None,
        source: str = "ai_agent",
        idempotency_key: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> Appointment:
        self._validate_common(college_id, student_id, counselor_id, course_id)

        if idempotency_key:
            stmt = select(Appointment).where(
                Appointment.college_id == college_id, Appointment.idempotency_key == idempotency_key
            )
            existing = self.db.execute(stmt).scalar_one_or_none()
            if existing is not None:
                return existing

        if start_time <= datetime.now(timezone.utc):
            raise ValidationAppError("Appointment slot must be in the future.")

        conflict_stmt = select(Appointment.id).where(
            Appointment.counselor_id == counselor_id,
            Appointment.start_time == start_time,
            Appointment.status.in_(_ACTIVE_STATUSES),
        )
        if self.db.execute(conflict_stmt).scalar_one_or_none() is not None:
            raise ConflictError("The selected appointment slot is no longer available.", details={"code": "APPOINTMENT_SLOT_UNAVAILABLE"})

        appointment = Appointment(
            college_id=college_id,
            student_id=student_id,
            counselor_id=counselor_id,
            course_id=course_id,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=duration_minutes),
            status="scheduled",
            meeting_type="phone",
            notes=purpose,
            source=source,
            idempotency_key=idempotency_key,
        )
        try:
            with self.db.begin_nested():
                self.db.add(appointment)
                self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "The selected appointment slot is no longer available.",
                details={"code": "APPOINTMENT_SLOT_UNAVAILABLE"},
            ) from exc

        logger.info(
            "appointment.created appointment_id=%s college_id=%s counselor_id=%s start_time=%s",
            appointment.id, college_id, counselor_id, appointment.start_time.isoformat(),
        )
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="appointment.created",
            entity_type="appointment", entity_id=appointment.id,
        )
        _notify_lead(self.db, college_id, student_id, "appointment_booked", "Counselor appointment booked.")
        return appointment

    def get_or_404(self, college_id: uuid.UUID, appointment_id: uuid.UUID) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None or appointment.college_id != college_id:
            raise NotFoundError("Appointment not found.")
        return appointment

    def list_appointments(
        self,
        college_id: uuid.UUID,
        *,
        status: str | None = None,
        counselor_id: uuid.UUID | None = None,
        student_id: uuid.UUID | None = None,
        course_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Appointment], int]:
        conditions = [Appointment.college_id == college_id]
        if status:
            conditions.append(Appointment.status == status)
        if counselor_id:
            conditions.append(Appointment.counselor_id == counselor_id)
        if student_id:
            conditions.append(Appointment.student_id == student_id)
        if course_id:
            conditions.append(Appointment.course_id == course_id)
        if from_date is not None:
            conditions.append(Appointment.start_time >= from_date)
        if to_date is not None:
            conditions.append(Appointment.start_time <= to_date)

        total = self.db.execute(select(func.count()).select_from(Appointment).where(*conditions)).scalar_one()
        stmt = (
            select(Appointment)
            .where(*conditions)
            .order_by(Appointment.start_time.desc(), Appointment.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def reschedule(
        self, college_id: uuid.UUID, appointment_id: uuid.UUID, new_start_time: datetime,
        *, actor_user_id: uuid.UUID | None = None,
    ) -> Appointment:
        appointment = self.get_or_404(college_id, appointment_id)
        if appointment.status != "scheduled":
            raise ConflictError("Only a scheduled appointment can be rescheduled.")
        if new_start_time <= datetime.now(timezone.utc):
            raise ValidationAppError("New appointment slot must be in the future.")

        conflict_stmt = select(Appointment.id).where(
            Appointment.counselor_id == appointment.counselor_id,
            Appointment.start_time == new_start_time,
            Appointment.status.in_(_ACTIVE_STATUSES),
            Appointment.id != appointment.id,
        )
        if self.db.execute(conflict_stmt).scalar_one_or_none() is not None:
            raise ConflictError(
                "The requested new slot is no longer available.",
                details={"code": "APPOINTMENT_SLOT_UNAVAILABLE"},
            )

        duration = appointment.end_time - appointment.start_time
        previous_start = appointment.start_time
        try:
            with self.db.begin_nested():
                appointment.start_time = new_start_time
                appointment.end_time = new_start_time + duration
                self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "The requested new slot is no longer available.",
                details={"code": "APPOINTMENT_SLOT_UNAVAILABLE"},
            ) from exc

        logger.info(
            "appointment.rescheduled appointment_id=%s from=%s to=%s",
            appointment.id, previous_start.isoformat(), new_start_time.isoformat(),
        )
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="appointment.rescheduled",
            entity_type="appointment", entity_id=appointment.id,
            meta={"from": previous_start.isoformat(), "to": new_start_time.isoformat()},
        )
        _notify_lead(self.db, college_id, appointment.student_id, "appointment_rescheduled", "Appointment rescheduled.")
        return appointment

    def update_details(self, appointment: Appointment, **fields) -> Appointment:
        allowed = {"notes", "meeting_type", "meeting_link"}
        changed = False
        for key, value in fields.items():
            if key not in allowed or value is None:
                continue
            if getattr(appointment, key) != value:
                setattr(appointment, key, value)
                changed = True
        if changed:
            self.db.flush()
        return appointment

    def cancel(
        self, college_id: uuid.UUID, appointment_id: uuid.UUID, reason: str | None,
        *, actor_user_id: uuid.UUID | None = None,
    ) -> Appointment:
        appointment = self.get_or_404(college_id, appointment_id)
        if appointment.status == "cancelled":
            return appointment
        if appointment.status != "scheduled":
            raise ConflictError("Only a scheduled appointment can be cancelled.")
        appointment.status = "cancelled"
        if reason:
            appointment.cancellation_reason = reason
        self.db.flush()

        logger.info("appointment.cancelled appointment_id=%s", appointment.id)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="appointment.cancelled",
            entity_type="appointment", entity_id=appointment.id, meta={"reason": reason} if reason else None,
        )
        _notify_lead(self.db, college_id, appointment.student_id, "appointment_cancelled", "Appointment cancelled.")
        return appointment

    def complete(
        self, college_id: uuid.UUID, appointment_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None,
    ) -> Appointment:
        appointment = self.get_or_404(college_id, appointment_id)
        if appointment.status != "scheduled":
            raise ConflictError("Only a scheduled appointment can be marked completed.")
        appointment.status = "completed"
        self.db.flush()
        logger.info("appointment.completed appointment_id=%s", appointment.id)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="appointment.completed",
            entity_type="appointment", entity_id=appointment.id,
        )
        return appointment

    def mark_no_show(
        self, college_id: uuid.UUID, appointment_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None,
    ) -> Appointment:
        appointment = self.get_or_404(college_id, appointment_id)
        if appointment.status != "scheduled":
            raise ConflictError("Only a scheduled appointment can be marked as a no-show.")
        appointment.status = "no_show"
        self.db.flush()
        logger.info("appointment.no_show appointment_id=%s", appointment.id)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="appointment.no_show",
            entity_type="appointment", entity_id=appointment.id,
        )
        return appointment
