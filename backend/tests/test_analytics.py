"""Task 013 - analytics & reporting tests.

Covers: zero-data colleges, Nova/Aurora seeded data, date-range presets,
timezone boundary correctness, course/temperature/status breakdowns,
tenant isolation, platform-admin tenant selection, college-admin
college_id spoofing, RBAC, invalid/future/empty ranges, determinism,
PII exposure, and a basic N+1 query-count guard.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import event, select

from app.core.security import hash_password
from app.db.seed import seed_demo_data
from app.models.academics import Course
from app.models.applications import Application
from app.models.college import College
from app.models.conversations import Conversation, Message
from app.models.counseling import Appointment, Counselor
from app.models.leads import Lead
from app.models.student import Student
from app.models.user import User
from app.models.voice import VoiceSession

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


def _make_platform_admin(db) -> User:
    admin = User(
        college_id=None, email="platform-admin@admissions.example",
        password_hash=hash_password("PlatformAdmin#2026"), full_name="Platform Admin",
        role="platform_admin", is_active=True,
    )
    db.add(admin)
    db.commit()
    return admin


def _student(db, college_id, name="Extra Student") -> Student:
    student = Student(college_id=college_id, full_name=name, email=f"{uuid.uuid4().hex}@example.edu")
    db.add(student)
    db.flush()
    return student


def _appointment(db, college_id, counselor_id, student_id, *, created_at, status="scheduled") -> Appointment:
    start = datetime.now(timezone.utc) + timedelta(days=3)
    appt = Appointment(
        college_id=college_id, student_id=student_id, counselor_id=counselor_id,
        start_time=start, end_time=start + timedelta(minutes=30), status=status,
        created_at=created_at,
    )
    db.add(appt)
    db.flush()
    return appt


def _application(db, college_id, student_id, course_id, *, created_at, status="draft", completion=50) -> Application:
    app = Application(
        college_id=college_id, student_id=student_id, course_id=course_id,
        status=status, completion_percentage=completion, created_at=created_at,
    )
    db.add(app)
    db.flush()
    return app


def _conversation(db, college_id, *, created_at, channel="web_voice", status="completed",
                   duration_seconds=120, intent=None) -> Conversation:
    conv = Conversation(
        college_id=college_id, channel=channel, status=status, language="en",
        started_at=created_at, ended_at=created_at + timedelta(seconds=duration_seconds) if duration_seconds else None,
        duration_seconds=duration_seconds, intent=intent, created_at=created_at, state={},
    )
    db.add(conv)
    db.flush()
    return conv


def _voice_session(db, college_id, conversation_id, *, created_at, channel="web_voice",
                    status="completed", duration_seconds=90) -> VoiceSession:
    session = VoiceSession(
        college_id=college_id, conversation_id=conversation_id, channel=channel, status=status,
        language="en", duration_seconds=duration_seconds, created_at=created_at,
    )
    db.add(session)
    db.flush()
    return session


# ---------------------------------------------------------------------------
# Zero-data college
# ---------------------------------------------------------------------------

def test_zero_data_college_returns_valid_empty_structures(client, db):
    seed_demo_data(db)
    aurora = _college(db, "aurora-college-of-management")
    headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["leads"]["total_leads"] == 0
    assert data["leads"]["new_leads"] == 0
    assert data["leads"]["by_course"] == []
    assert data["leads"]["appointment_conversion"]["rate"] is None
    assert data["appointments"]["total_appointments"] == 0
    assert data["applications"]["total_applications"] == 0
    assert data["conversations"]["total_conversations"] == 0
    assert data["conversations"]["average_duration_seconds"]["value"] is None
    assert data["conversations"]["average_duration_seconds"]["measurement"] == "unavailable"
    assert data["support"]["total_tickets"] == 0
    assert data["voice"]["total_sessions"] == 0
    assert data["ai_operations"]["escalations"]["escalation_rate"] is None

    # every known enum key must default to zero, never be missing/null
    for status_key in ("new", "qualifying", "qualified", "contacted", "converted", "lost"):
        assert data["leads"]["by_status"][status_key] == 0

    trends = client.get("/api/v1/analytics/trends?range=last_7_days", headers=headers)
    assert trends.status_code == 200, trends.text
    series = trends.json()["data"]["leads_per_day"]
    assert len(series) == 7
    assert all(point["count"] == 0 for point in series)


# ---------------------------------------------------------------------------
# Nova seeded data
# ---------------------------------------------------------------------------

def test_nova_seeded_data_overview_reflects_real_counts(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Seed creates exactly 3 leads: 1 cold, 1 warm, 1 hot.
    assert data["leads"]["total_leads"] == 3
    assert data["leads"]["by_temperature"]["cold"] == 1
    assert data["leads"]["by_temperature"]["warm"] == 1
    assert data["leads"]["by_temperature"]["hot"] == 1
    # Seed creates exactly 3 support tickets: open, assigned(escalation), resolved.
    assert data["support"]["total_tickets"] == 3
    assert data["support"]["by_status"]["open"] == 1
    assert data["support"]["by_status"]["assigned"] == 1
    assert data["support"]["by_status"]["resolved"] == 1
    assert data["support"]["escalated_tickets"] == 1
    assert data["support"]["average_resolution_seconds"]["measurement"] == "directly_measured"
    assert data["support"]["average_resolution_seconds"]["value"] > 0  # regression guard for the seed timing bug


# ---------------------------------------------------------------------------
# Aurora seeded data / tenant isolation
# ---------------------------------------------------------------------------

def test_aurora_cannot_see_nova_analytics_and_vice_versa(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")

    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)

    nova_data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=nova_headers).json()["data"]
    aurora_data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=aurora_headers).json()["data"]

    assert nova_data["leads"]["total_leads"] == 3
    assert aurora_data["leads"]["total_leads"] == 0
    assert aurora_data["support"]["total_tickets"] == 0

    # Aurora admin cannot pull Nova's numbers by passing Nova's college_id.
    spoof = client.get(
        f"/api/v1/analytics/overview?range=last_30_days&college_id={nova.id}", headers=aurora_headers
    )
    assert spoof.status_code == 200
    assert spoof.json()["data"]["leads"]["total_leads"] == 0  # still Aurora's own data, not Nova's


def test_college_admin_college_id_query_param_is_ignored(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)

    resp = client.get(f"/api/v1/analytics/trends?range=last_7_days&college_id={nova.id}", headers=headers)
    assert resp.status_code == 200
    # Aurora has zero leads regardless of the college_id it tried to pass.
    assert all(point["count"] == 0 for point in resp.json()["data"]["leads_per_day"])


# ---------------------------------------------------------------------------
# Platform admin
# ---------------------------------------------------------------------------

def test_platform_admin_must_select_a_college_explicitly(client, db):
    seed_demo_data(db)
    _make_platform_admin(db)
    headers = _auth_headers(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    missing = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "FORBIDDEN"


def test_platform_admin_can_select_either_tenant(client, db):
    seed_demo_data(db)
    _make_platform_admin(db)
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    headers = _auth_headers(client, "platform-admin@admissions.example", "PlatformAdmin#2026")

    nova_resp = client.get(f"/api/v1/analytics/overview?range=last_30_days&college_id={nova.id}", headers=headers)
    aurora_resp = client.get(f"/api/v1/analytics/overview?range=last_30_days&college_id={aurora.id}", headers=headers)
    assert nova_resp.json()["data"]["leads"]["total_leads"] == 3
    assert aurora_resp.json()["data"]["leads"]["total_leads"] == 0


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

def test_unauthenticated_request_is_rejected(client, db):
    seed_demo_data(db)
    resp = client.get("/api/v1/analytics/overview?range=last_30_days")
    assert resp.status_code == 401


def test_counselor_can_read_analytics_per_current_role_policy(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
    assert resp.status_code == 200  # matches app/auth/permissions.py's existing grant, not a new rule


# ---------------------------------------------------------------------------
# Date ranges: invalid / future / empty / custom
# ---------------------------------------------------------------------------

def test_invalid_range_value_is_rejected(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get("/api/v1/analytics/overview?range=last_century", headers=headers)
    assert resp.status_code == 422


def test_custom_range_requires_both_dates(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get("/api/v1/analytics/overview?range=custom&start_date=2026-01-01", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_custom_range_end_before_start_is_rejected(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get(
        "/api/v1/analytics/overview?range=custom&start_date=2026-06-10&end_date=2026-06-01", headers=headers
    )
    assert resp.status_code == 422


def test_future_range_is_valid_and_empty(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get(
        "/api/v1/analytics/overview?range=custom&start_date=2099-01-01&end_date=2099-01-31", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["leads"]["total_leads"] == 0
    assert data["appointments"]["total_appointments"] == 0


def test_single_day_custom_range_is_valid(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    today = date.today().isoformat()
    resp = client.get(f"/api/v1/analytics/overview?range=custom&start_date={today}&end_date={today}", headers=headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Timezone boundary correctness
# ---------------------------------------------------------------------------

def test_timezone_boundary_uses_college_local_day_not_utc_day(client, db):
    """Nova's timezone is Asia/Kolkata (UTC+5:30). A lead created at
    00:30 local time today falls on the *previous* UTC calendar date.
    range=today must still include it; a custom range for the local
    "yesterday" must not."""
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    assert nova.timezone == "Asia/Kolkata"
    student = _student(db, nova.id)

    tz = ZoneInfo("Asia/Kolkata")
    today_local = datetime.now(tz).date()
    just_after_local_midnight = datetime.combine(today_local, time(0, 30), tzinfo=tz)

    lead = Lead(college_id=nova.id, student_id=student.id, source="website", status="new")
    db.add(lead)
    db.flush()
    lead.created_at = just_after_local_midnight
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    # 3 seed leads are also created "now" (today) plus the 1 extra lead
    # backdated to just after local midnight - both must count as "today".
    today_resp = client.get("/api/v1/analytics/overview?range=today", headers=headers)
    assert today_resp.status_code == 200
    assert today_resp.json()["data"]["leads"]["total_leads"] == 4

    yesterday_local = today_local - timedelta(days=1)
    yesterday_resp = client.get(
        f"/api/v1/analytics/overview?range=custom&start_date={yesterday_local}&end_date={yesterday_local}",
        headers=headers,
    )
    assert yesterday_resp.status_code == 200
    assert yesterday_resp.json()["data"]["leads"]["total_leads"] == 0


# ---------------------------------------------------------------------------
# Breakdowns: course, appointment status, application status, voice channel
# ---------------------------------------------------------------------------

def test_leads_by_course_breakdown_and_no_course_bucket(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    student = _student(db, nova.id)
    lead = Lead(college_id=nova.id, student_id=student.id, source="website", status="new", course_id=None)
    db.add(lead)
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    course_names = {row["course"] for row in data["leads"]["by_course"]}
    assert "No course specified" in course_names
    assert "B.Tech Computer Science and Engineering" in course_names


def test_appointment_status_breakdown_reflects_real_statuses(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor = db.execute(select(Counselor).where(Counselor.college_id == nova.id)).scalars().first()
    student1 = _student(db, nova.id, "Appt Student 1")
    student2 = _student(db, nova.id, "Appt Student 2")
    now = datetime.now(timezone.utc)
    _appointment(db, nova.id, counselor.id, student1.id, created_at=now, status="scheduled")
    _appointment(db, nova.id, counselor.id, student2.id, created_at=now, status="no_show")
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    assert data["appointments"]["by_status"]["scheduled"] == 1
    assert data["appointments"]["by_status"]["no_show"] == 1
    assert data["appointments"]["total_appointments"] == 2
    assert {row["counselor"] for row in data["appointments"]["by_counselor"]} == {counselor.name}


def test_application_completion_distribution_and_status(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = db.execute(select(Course).where(Course.college_id == nova.id)).scalars().first()
    student = _student(db, nova.id, "App Student")
    now = datetime.now(timezone.utc)
    _application(db, nova.id, student.id, course.id, created_at=now, status="submitted", completion=90)
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    assert data["applications"]["by_status"]["submitted"] == 1
    assert data["applications"]["completion_percentage_distribution"]["76-100"] == 1


def test_voice_channel_and_language_breakdown(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    now = datetime.now(timezone.utc)
    conv = _conversation(db, nova.id, created_at=now, channel="phone", status="completed")
    _voice_session(db, nova.id, conv.id, created_at=now, channel="phone_voice", status="failed", duration_seconds=None)
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    assert data["voice"]["by_channel"]["phone_voice"] == 1
    assert data["voice"]["by_status"]["failed"] == 1
    assert data["voice"]["failed_sessions"] == 1


# ---------------------------------------------------------------------------
# AI operations honesty
# ---------------------------------------------------------------------------

def test_ai_resolution_rate_is_explicitly_unavailable(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    assert data["ai_operations"]["ai_resolution_rate"]["measurement"] == "unavailable"
    assert "reason" in data["ai_operations"]["ai_resolution_rate"]


def test_escalated_conversation_counts_toward_escalation_rate(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    now = datetime.now(timezone.utc)
    _conversation(db, nova.id, created_at=now, status="escalated", duration_seconds=None)
    _conversation(db, nova.id, created_at=now, status="completed", duration_seconds=60)
    db.commit()

    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    data = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    escalations = data["ai_operations"]["escalations"]
    assert escalations["escalated_conversations"] == 1
    assert escalations["total_conversations"] == 2
    assert escalations["escalation_rate"] == 0.5


# ---------------------------------------------------------------------------
# Determinism / no PII / query-count guard
# ---------------------------------------------------------------------------

def test_overview_is_deterministic_across_repeated_calls(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    first = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    second = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers).json()["data"]
    first.pop("range", None)
    second.pop("range", None)
    assert first == second


def test_overview_does_not_expose_student_pii(client, db):
    seed_demo_data(db)
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
    body = resp.text
    assert "demo.student1@example.edu" not in body
    assert "Demo Student 1" not in body
    assert "9800000001" not in body


def test_overview_query_count_does_not_scale_with_row_count(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    def _count_queries() -> int:
        engine = db.get_bind()
        counter = {"n": 0}

        def _on_execute(*args, **kwargs):
            counter["n"] += 1

        event.listen(engine, "before_cursor_execute", _on_execute)
        try:
            resp = client.get("/api/v1/analytics/overview?range=last_30_days", headers=headers)
            assert resp.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _on_execute)
        return counter["n"]

    baseline = _count_queries()

    for i in range(25):
        student = _student(db, nova.id, f"Bulk Student {i}")
        db.add(Lead(college_id=nova.id, student_id=student.id, source="website", status="new"))
    db.commit()

    after_bulk_insert = _count_queries()
    assert after_bulk_insert <= baseline + 2  # allow tiny variance, never linear in row count
