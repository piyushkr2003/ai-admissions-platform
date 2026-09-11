"""Task 008 - counselor availability & appointments tests."""
from __future__ import annotations

import threading
import uuid as uuid_lib
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from app.core.errors import ConflictError, ValidationAppError
from app.core.security import hash_password
from app.db.seed import seed_demo_data
from app.models.academics import Course
from app.models.college import College
from app.models.counseling import Appointment, Counselor, CounselorAvailability
from app.models.leads import LeadScoreEvent
from app.models.student import Student
from app.models.support import AuditLog
from app.models.user import User
from app.services.appointments import AppointmentService
from app.services.leads import LeadService

NOVA_ADMIN_EMAIL = "admin@nova-institute-of-technology.example.edu"
NOVA_ADMIN_PASSWORD = "NovaAdmin#2026"
NOVA_COUNSELOR_EMAIL = "counselor@nova-institute-of-technology.example.edu"
NOVA_COUNSELOR_PASSWORD = "NovaCounselor#2026"
AURORA_ADMIN_EMAIL = "admin@aurora-college-of-management.example.edu"
AURORA_ADMIN_PASSWORD = "AuroraAdmin#2026"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth_headers(client, email: str, password: str) -> dict:
    tokens = _login(client, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _bare_student(db, college_id) -> Student:
    student = Student(college_id=college_id)
    db.add(student)
    db.flush()
    return student


# ---------------------------------------------------------------------------
# Service-level: booking, validation, conflicts, idempotency
# ---------------------------------------------------------------------------

def test_book_appointment_creates_scheduled_appointment(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student = _bare_student(db, nova.id)
    service = AppointmentService(db)

    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)
    assert slots

    appointment = service.book_appointment(
        college_id=nova.id, student_id=student.id, counselor_id=counselor.id, start_time=slots[0].start_time,
    )
    assert appointment.status == "scheduled"
    assert appointment.college_id == nova.id


def test_book_appointment_rejects_course_from_another_college(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    aurora_course = db.execute(select(Course).where(Course.college_id == aurora.id)).scalars().first()
    student = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)

    with pytest.raises(ValidationAppError):
        service.book_appointment(
            college_id=nova.id, student_id=student.id, counselor_id=counselor.id,
            start_time=slots[0].start_time, course_id=aurora_course.id,
        )


def test_double_booking_same_slot_is_rejected(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student1 = _bare_student(db, nova.id)
    student2 = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)
    slot_time = slots[0].start_time

    service.book_appointment(college_id=nova.id, student_id=student1.id, counselor_id=counselor.id, start_time=slot_time)
    with pytest.raises(ConflictError):
        service.book_appointment(college_id=nova.id, student_id=student2.id, counselor_id=counselor.id, start_time=slot_time)


def test_idempotency_key_returns_existing_appointment_without_duplicating(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)

    key = "retry-key-abc"
    first = service.book_appointment(
        college_id=nova.id, student_id=student.id, counselor_id=counselor.id,
        start_time=slots[0].start_time, idempotency_key=key,
    )
    second = service.book_appointment(
        college_id=nova.id, student_id=student.id, counselor_id=counselor.id,
        start_time=slots[0].start_time, idempotency_key=key,
    )
    assert first.id == second.id
    count = db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.idempotency_key == key)
    ).scalar_one()
    assert count == 1


def test_reschedule_rejects_conflicting_slot(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student1 = _bare_student(db, nova.id)
    student2 = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id, max_slots=2)
    assert len(slots) >= 2

    appt1 = service.book_appointment(college_id=nova.id, student_id=student1.id, counselor_id=counselor.id, start_time=slots[0].start_time)
    appt2 = service.book_appointment(college_id=nova.id, student_id=student2.id, counselor_id=counselor.id, start_time=slots[1].start_time)

    with pytest.raises(ConflictError):
        service.reschedule(nova.id, appt2.id, slots[0].start_time)

    # A no-op reschedule (unaffected) still works fine.
    third_slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id, max_slots=3)
    new_time = third_slots[-1].start_time
    rescheduled = service.reschedule(nova.id, appt1.id, new_time)
    assert rescheduled.start_time == new_time


def test_cancel_preserves_notes_and_records_reason(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)

    appt = service.book_appointment(
        college_id=nova.id, student_id=student.id, counselor_id=counselor.id,
        start_time=slots[0].start_time, purpose="B.Tech CSE admission counseling",
    )
    cancelled = service.cancel(nova.id, appt.id, "Student requested cancellation")
    assert cancelled.status == "cancelled"
    assert cancelled.notes == "B.Tech CSE admission counseling"  # not clobbered
    assert cancelled.cancellation_reason == "Student requested cancellation"


def test_complete_and_no_show_transitions(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student1 = _bare_student(db, nova.id)
    student2 = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id, max_slots=2)

    appt1 = service.book_appointment(college_id=nova.id, student_id=student1.id, counselor_id=counselor.id, start_time=slots[0].start_time)
    completed = service.complete(nova.id, appt1.id)
    assert completed.status == "completed"
    with pytest.raises(ConflictError):
        service.complete(nova.id, appt1.id)

    appt2 = service.book_appointment(college_id=nova.id, student_id=student2.id, counselor_id=counselor.id, start_time=slots[1].start_time)
    no_show = service.mark_no_show(nova.id, appt2.id)
    assert no_show.status == "no_show"


# ---------------------------------------------------------------------------
# Service-level: lead integration (Task 007 seam)
# ---------------------------------------------------------------------------

def test_booking_enriches_an_existing_active_lead(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    lead_service = LeadService(db)
    lead, _ = lead_service.create_lead(nova.id, name="Interested Student")
    baseline_score = lead.lead_score

    appt_service = AppointmentService(db)
    slots = appt_service.check_availability(college_id=nova.id, counselor_id=counselor.id)
    appt_service.book_appointment(
        college_id=nova.id, student_id=lead.student_id, counselor_id=counselor.id, start_time=slots[0].start_time,
    )

    db.refresh(lead)
    assert lead.lead_score == baseline_score + 20
    event = db.execute(
        select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.event_type == "appointment_booked")
    ).scalar_one()
    assert event.points == 20


def test_booking_never_creates_a_lead_for_a_student_without_one(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student = _bare_student(db, nova.id)
    service = AppointmentService(db)
    slots = service.check_availability(college_id=nova.id, counselor_id=counselor.id)

    service.book_appointment(college_id=nova.id, student_id=student.id, counselor_id=counselor.id, start_time=slots[0].start_time)

    from app.models.leads import Lead
    count = db.execute(select(func.count()).select_from(Lead).where(Lead.student_id == student.id)).scalar_one()
    assert count == 0


def test_cancellation_records_zero_point_audit_event(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    lead_service = LeadService(db)
    lead, _ = lead_service.create_lead(nova.id, name="Cancelling Student")

    appt_service = AppointmentService(db)
    slots = appt_service.check_availability(college_id=nova.id, counselor_id=counselor.id)
    appt = appt_service.book_appointment(
        college_id=nova.id, student_id=lead.student_id, counselor_id=counselor.id, start_time=slots[0].start_time,
    )
    score_after_booking = db.get(type(lead), lead.id).lead_score
    appt_service.cancel(nova.id, appt.id, "No longer needed")

    db.refresh(lead)
    assert lead.lead_score == score_after_booking  # 0-point audit event, score unchanged
    event = db.execute(
        select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.event_type == "appointment_cancelled")
    ).scalar_one()
    assert event.points == 0


def test_reschedule_adds_small_positive_lead_signal(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    lead_service = LeadService(db)
    lead, _ = lead_service.create_lead(nova.id, name="Rescheduling Student")

    appt_service = AppointmentService(db)
    slots = appt_service.check_availability(college_id=nova.id, counselor_id=counselor.id, max_slots=2)
    appt = appt_service.book_appointment(
        college_id=nova.id, student_id=lead.student_id, counselor_id=counselor.id, start_time=slots[0].start_time,
    )
    score_after_booking = db.get(type(lead), lead.id).lead_score
    appt_service.reschedule(nova.id, appt.id, slots[1].start_time)

    db.refresh(lead)
    assert lead.lead_score == score_after_booking + 5


# ---------------------------------------------------------------------------
# Concurrency: a genuine cross-connection race
# ---------------------------------------------------------------------------

def test_concurrent_booking_of_same_slot_is_race_safe(test_engine):
    """Two independent DB sessions race to book the exact same
    (counselor, start_time) slot. Exactly one must win; the other must
    fail safely with ConflictError - proving the unique-constraint safety
    net in AppointmentService.book_appointment under real concurrency,
    not just the pre-check."""
    session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    suffix = uuid_lib.uuid4().hex[:8]

    setup = session_factory()
    college = College(name=f"Concurrency Test College {suffix}", slug=f"concurrency-test-{suffix}")
    setup.add(college)
    setup.flush()
    counselor = Counselor(college_id=college.id, name="Race Counselor", email=f"race-{suffix}@example.com", active=True)
    setup.add(counselor)
    setup.flush()
    for day in range(7):
        setup.add(CounselorAvailability(
            college_id=college.id, counselor_id=counselor.id, day_of_week=day,
            start_time=time(0, 0), end_time=time(23, 59), timezone="UTC", active=True,
        ))
    student_a = Student(college_id=college.id)
    student_b = Student(college_id=college.id)
    setup.add_all([student_a, student_b])
    setup.commit()

    service = AppointmentService(setup)
    slots = service.check_availability(college_id=college.id, counselor_id=counselor.id, days_ahead=2)
    assert slots, "expected at least one available slot for the race"
    slot_start = slots[0].start_time
    student_a_id, student_b_id, counselor_id, college_id = student_a.id, student_b.id, counselor.id, college.id
    setup.close()

    results: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _attempt(name: str, student_id) -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=5)
            AppointmentService(session).book_appointment(
                college_id=college_id, student_id=student_id, counselor_id=counselor_id, start_time=slot_start,
            )
            session.commit()
            results[name] = "success"
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results[name] = type(exc).__name__
        finally:
            session.close()

    t1 = threading.Thread(target=_attempt, args=("a", student_a_id))
    t2 = threading.Thread(target=_attempt, args=("b", student_b_id))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    try:
        assert sorted(results.values()) == ["ConflictError", "success"], f"unexpected race outcome: {results}"
        cleanup = session_factory()
        count = cleanup.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.counselor_id == counselor_id, Appointment.start_time == slot_start,
            )
        ).scalar_one()
        assert count == 1
        cleanup.close()
    finally:
        cleanup = session_factory()
        cleanup.execute(delete(AuditLog).where(AuditLog.college_id == college_id))
        cleanup.execute(delete(Appointment).where(Appointment.counselor_id == counselor_id))
        cleanup.execute(delete(CounselorAvailability).where(CounselorAvailability.counselor_id == counselor_id))
        cleanup.execute(delete(Student).where(Student.college_id == college_id))
        cleanup.execute(delete(Counselor).where(Counselor.id == counselor_id))
        cleanup.execute(delete(College).where(College.id == college_id))
        cleanup.commit()
        cleanup.close()


# ---------------------------------------------------------------------------
# API: counselors, RBAC, timezone validation
# ---------------------------------------------------------------------------

def test_college_admin_can_create_counselor_and_availability_window(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/counselors", headers=headers,
        json={"name": "New Counselor", "email": "new.counselor@nova-institute-of-technology.example.edu"},
    )
    assert resp.status_code == 201, resp.text
    counselor_id = resp.json()["data"]["id"]

    window_resp = client.post(
        f"/api/v1/counselors/{counselor_id}/availability-windows", headers=headers,
        json={"day_of_week": 0, "start_time": "09:00:00", "end_time": "12:00:00", "timezone": "Asia/Kolkata"},
    )
    assert window_resp.status_code == 201, window_resp.text

    windows_resp = client.get(f"/api/v1/counselors/{counselor_id}/availability-windows", headers=headers)
    assert len(windows_resp.json()["data"]) == 1


def test_counselor_cannot_create_counselor_profile(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.post("/api/v1/counselors", headers=headers, json={"name": "Blocked"})
    assert resp.status_code == 403


def test_counselor_can_update_own_profile_but_not_others(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    own_counselor = db.execute(
        select(Counselor).where(Counselor.college_id == nova.id, Counselor.email == NOVA_COUNSELOR_EMAIL)
    ).scalar_one()
    other_counselor = Counselor(college_id=nova.id, name="Other Counselor", active=True)
    db.add(other_counselor)
    db.commit()

    headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    own_resp = client.patch(
        f"/api/v1/counselors/{own_counselor.id}", headers=headers, json={"specialization": "STEM Admissions"}
    )
    assert own_resp.status_code == 200
    assert own_resp.json()["data"]["specialization"] == "STEM Admissions"

    other_resp = client.patch(
        f"/api/v1/counselors/{other_counselor.id}", headers=headers, json={"specialization": "Hijack"}
    )
    assert other_resp.status_code == 403


def test_get_counselor_availability_endpoint_returns_slots(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get(f"/api/v1/counselors/{counselor.id}/availability", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["slots"]
    # Timezone information must be preserved in every slot.
    for slot in resp.json()["data"]["slots"]:
        assert "+" in slot["start_time"] or "Z" in slot["start_time"] or slot["start_time"].count("-") >= 3


# ---------------------------------------------------------------------------
# API: appointment booking, timezone validation, RBAC scoping, isolation
# ---------------------------------------------------------------------------

def _first_slot(client, headers, counselor_id) -> str:
    resp = client.get(f"/api/v1/counselors/{counselor_id}/availability", headers=headers)
    return resp.json()["data"]["slots"][0]["start_time"]


def test_create_appointment_rejects_naive_datetime(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    student = _bare_student(db, nova.id)
    db.commit()

    resp = client.post(
        "/api/v1/appointments", headers=headers,
        json={"student_id": str(student.id), "counselor_id": str(counselor.id), "start_time": "2026-09-20T15:00:00"},
    )
    assert resp.status_code == 422


def test_create_appointment_via_api_success_and_get(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    student = _bare_student(db, nova.id)
    db.commit()

    start_time = _first_slot(client, headers, counselor.id)
    resp = client.post(
        "/api/v1/appointments", headers=headers,
        json={"student_id": str(student.id), "counselor_id": str(counselor.id), "start_time": start_time, "purpose": "CSE counseling"},
    )
    assert resp.status_code == 201, resp.text
    appt = resp.json()["data"]
    assert appt["status"] == "scheduled"
    assert "+" in appt["start_time"] or "Z" in appt["start_time"]

    get_resp = client.get(f"/api/v1/appointments/{appt['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == appt["id"]


def test_counselor_can_only_book_under_own_profile(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    other_counselor = Counselor(college_id=nova.id, name="Other Counselor", active=True)
    db.add(other_counselor)
    db.flush()
    for day in range(7):
        db.add(CounselorAvailability(
            college_id=nova.id, counselor_id=other_counselor.id, day_of_week=day,
            start_time=time(9, 0), end_time=time(17, 0), timezone="Asia/Kolkata", active=True,
        ))
    student = _bare_student(db, nova.id)
    db.commit()

    admin_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    start_time = _first_slot(client, admin_headers, other_counselor.id)

    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.post(
        "/api/v1/appointments", headers=counselor_headers,
        json={"student_id": str(student.id), "counselor_id": str(other_counselor.id), "start_time": start_time},
    )
    assert resp.status_code == 403


def test_counselor_sees_only_own_appointments_in_list(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    own_counselor = db.execute(
        select(Counselor).where(Counselor.college_id == nova.id, Counselor.email == NOVA_COUNSELOR_EMAIL)
    ).scalar_one()
    other_counselor = Counselor(college_id=nova.id, name="Other Counselor", active=True)
    db.add(other_counselor)
    db.flush()
    for day in range(7):
        db.add(CounselorAvailability(
            college_id=nova.id, counselor_id=other_counselor.id, day_of_week=day,
            start_time=time(9, 0), end_time=time(17, 0), timezone="Asia/Kolkata", active=True,
        ))
    student1 = _bare_student(db, nova.id)
    student2 = _bare_student(db, nova.id)
    db.commit()

    admin_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    own_slot = _first_slot(client, admin_headers, own_counselor.id)
    other_slot = _first_slot(client, admin_headers, other_counselor.id)
    client.post("/api/v1/appointments", headers=admin_headers, json={
        "student_id": str(student1.id), "counselor_id": str(own_counselor.id), "start_time": own_slot,
    })
    client.post("/api/v1/appointments", headers=admin_headers, json={
        "student_id": str(student2.id), "counselor_id": str(other_counselor.id), "start_time": other_slot,
    })

    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.get("/api/v1/appointments", headers=counselor_headers)
    assert resp.status_code == 200
    counselor_ids = {item["counselor_id"] for item in resp.json()["data"]}
    assert counselor_ids == {str(own_counselor.id)}


def test_college_a_cannot_access_college_b_appointment(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student = _bare_student(db, nova.id)
    db.commit()
    start_time = _first_slot(client, nova_headers, counselor.id)
    create_resp = client.post("/api/v1/appointments", headers=nova_headers, json={
        "student_id": str(student.id), "counselor_id": str(counselor.id), "start_time": start_time,
    })
    appointment_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/v1/appointments/{appointment_id}", headers=aurora_headers)
    assert resp.status_code == 404


def test_reschedule_cancel_complete_lifecycle_via_api(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    student = _bare_student(db, nova.id)
    db.commit()

    start_time = _first_slot(client, headers, counselor.id)
    create_resp = client.post("/api/v1/appointments", headers=headers, json={
        "student_id": str(student.id), "counselor_id": str(counselor.id), "start_time": start_time,
    })
    appointment_id = create_resp.json()["data"]["id"]

    new_slot = None
    for slot in client.get(f"/api/v1/counselors/{counselor.id}/availability", headers=headers).json()["data"]["slots"]:
        if slot["start_time"] != start_time:
            new_slot = slot["start_time"]
            break
    assert new_slot is not None

    reschedule_resp = client.patch(
        f"/api/v1/appointments/{appointment_id}/reschedule", headers=headers, json={"new_start_time": new_slot},
    )
    assert reschedule_resp.status_code == 200
    assert reschedule_resp.json()["data"]["start_time"] == new_slot

    complete_resp = client.post(f"/api/v1/appointments/{appointment_id}/complete", headers=headers)
    assert complete_resp.status_code == 200
    assert complete_resp.json()["data"]["status"] == "completed"

    invalid_cancel_resp = client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers, json={})
    assert invalid_cancel_resp.status_code == 409


def test_unauthenticated_access_denied(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/appointments")
    assert resp.status_code == 401
    resp2 = client.get("/api/v1/counselors")
    assert resp2.status_code == 401
