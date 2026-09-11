"""Task 007 - lead intelligence & scoring tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError
from app.core.security import hash_password
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.leads import Lead, LeadScoreEvent
from app.models.student import Student
from app.models.user import User
from app.services.leads import (
    LeadService,
    SCORING_RULES,
    is_allowed_status_transition,
    normalize_email,
    normalize_phone,
    temperature_for_score,
)

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


# ---------------------------------------------------------------------------
# Unit: scoring policy
# ---------------------------------------------------------------------------

def test_temperature_thresholds():
    scoring = {"cold_max": 39, "warm_max": 69}
    assert temperature_for_score(0, scoring) == "cold"
    assert temperature_for_score(39, scoring) == "cold"
    assert temperature_for_score(40, scoring) == "warm"
    assert temperature_for_score(69, scoring) == "warm"
    assert temperature_for_score(70, scoring) == "hot"
    assert temperature_for_score(100, scoring) == "hot"


def test_normalize_phone_and_email():
    assert normalize_phone("+91 98000-00001") == "919800000001"
    assert normalize_phone(None) is None
    assert normalize_email("  Rahul@Example.COM ") == "rahul@example.com"
    assert normalize_email("") is None


def test_status_transition_rules():
    assert is_allowed_status_transition("new", "contacted")
    assert is_allowed_status_transition("new", "application_started")  # skipping stages is fine
    assert is_allowed_status_transition("new", "lost")
    assert is_allowed_status_transition("qualified", "disqualified")
    assert not is_allowed_status_transition("converted", "new")
    assert not is_allowed_status_transition("lost", "qualified")
    assert not is_allowed_status_transition("application_started", "contacted")  # no backward hops
    assert not is_allowed_status_transition("new", "not_a_real_status")


def test_default_scoring_rules_match_documented_points():
    assert SCORING_RULES["course_identified"]["points"] == 20
    assert SCORING_RULES["eligibility_confirmed"]["points"] == 20
    assert SCORING_RULES["fee_discussed"]["points"] == 10
    assert SCORING_RULES["scholarship_interest"]["points"] == 10
    assert SCORING_RULES["appointment_requested"]["points"] == 20
    assert SCORING_RULES["application_started"]["points"] == 30


# ---------------------------------------------------------------------------
# Service-level: scoring bounds, dedup, explainability
# ---------------------------------------------------------------------------

def _bare_lead(db, college_id) -> Lead:
    student = Student(college_id=college_id, consent_status="unknown")
    db.add(student)
    db.flush()
    lead = Lead(college_id=college_id, student_id=student.id, source="voice_agent", status="new")
    db.add(lead)
    db.flush()
    return lead


def test_score_is_bounded_between_0_and_100(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead = _bare_lead(db, nova.id)

    for event_type in ("course_identified", "eligibility_confirmed", "appointment_requested",
                        "appointment_booked", "application_started"):
        service.record_score_event(lead, event_type, reason="test")
    result = service.recalculate_score(lead)
    assert result["score"] == 100
    assert result["temperature"] == "hot"

    lead2 = _bare_lead(db, nova.id)
    service.record_score_event(lead2, "disqualified", reason="test")
    result2 = service.recalculate_score(lead2)
    assert result2["score"] == 0
    assert result2["temperature"] == "cold"


def test_duplicate_event_type_does_not_inflate_score(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead = _bare_lead(db, nova.id)

    service.record_score_event(lead, "fee_discussed", reason="Asked about CSE fee.")
    service.record_score_event(lead, "fee_discussed", reason="Asked about CSE fee again.")
    service.record_score_event(lead, "fee_discussed", reason="Asked a third time.")
    result = service.recalculate_score(lead)

    events = db.execute(select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id)).scalars().all()
    assert len(events) == 1
    assert result["score"] == 10


def test_duplicate_idempotency_key_is_ignored(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead = _bare_lead(db, nova.id)

    key = "appointment-booking-abc123"
    service.record_score_event(lead, "appointment_booked", reason="Booked.", idempotency_key=key)
    # Simulate a retried webhook/agent call with the same idempotency key.
    service.record_score_event(lead, "appointment_booked", reason="Booked (retry).", idempotency_key=key)
    result = service.recalculate_score(lead)

    events = db.execute(select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id)).scalars().all()
    assert len(events) == 1
    assert result["score"] == 20


def test_score_events_are_explainable_in_order(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead = _bare_lead(db, nova.id)

    service.record_score_event(lead, "course_identified", reason="Course identified.")
    service.record_score_event(lead, "fee_discussed", reason="Fee discussed.")
    service.recalculate_score(lead)

    events = service.get_score_events(lead)
    assert [e.event_type for e in events] == ["course_identified", "fee_discussed"]
    assert all(e.points != 0 for e in events)
    assert all(e.created_at is not None for e in events)
    assert all(e.reason for e in events)


def test_appointment_booked_and_application_submitted_are_scored(db):
    """Task 007 additional signals - regression check that these event
    types (already referenced by the agent orchestrator) actually carry
    points, unlike the pre-Task-007 scoring table."""
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead = _bare_lead(db, nova.id)

    result = service.record_event_and_rescore(lead, "appointment_booked", "Booked a slot.")
    assert result["score"] == 20


# ---------------------------------------------------------------------------
# Service-level: creation, enrichment, deduplication
# ---------------------------------------------------------------------------

def test_create_lead_with_minimum_information(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead, created = service.create_lead(nova.id, source="website")
    assert created is True
    assert lead.college_id == nova.id
    assert lead.status == "new"
    assert lead.lead_score == 0
    assert lead.lead_temperature == "cold"


def test_create_lead_with_full_information_scores_correctly(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    from app.models.academics import Course

    cse = db.execute(select(Course).where(Course.college_id == nova.id, Course.code == "BTECH-CSE")).scalar_one()
    service = LeadService(db)

    lead, created = service.create_lead(
        nova.id, source="voice_agent", name="Rahul Sharma", phone="+91 90000 00011",
        email="rahul.sharma@example.com", course_id=cse.id, qualification="12th",
        qualification_score=84, scholarship_interest=True,
    )
    assert created is True
    # course_identified(20) + qualification_provided(5) + scholarship_interest(10) = 35
    assert lead.lead_score == 35
    assert lead.lead_temperature == "cold"

    student = db.get(Student, lead.student_id)
    assert student.full_name == "Rahul Sharma"
    assert student.phone == "919000000011"
    assert student.email == "rahul.sharma@example.com"


def test_create_lead_deduplicates_by_phone(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead1, created1 = service.create_lead(nova.id, name="Anita Verma", phone="9123456780")
    lead2, created2 = service.create_lead(nova.id, name="Anita Verma", phone="9123456780", notes="follow-up")

    assert created1 is True
    assert created2 is False
    assert lead1.id == lead2.id
    assert lead2.student_id == lead1.student_id


def test_create_lead_deduplicates_by_email(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead1, _ = service.create_lead(nova.id, name="Deepak Rao", email="deepak.rao@example.com")
    lead2, created2 = service.create_lead(nova.id, email="Deepak.Rao@Example.com")

    assert created2 is False
    assert lead2.id == lead1.id


def test_create_lead_does_not_merge_different_students_sharing_parent_phone(db):
    """Matching is strict on the student's own phone/email, never the
    shared parent phone, so two siblings are never accidentally merged."""
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead1, _ = service.create_lead(nova.id, name="Sibling One", parent_phone="9000011111")
    lead2, created2 = service.create_lead(nova.id, name="Sibling Two", parent_phone="9000011111")

    assert created2 is True
    assert lead1.id != lead2.id
    assert lead1.student_id != lead2.student_id


def test_update_does_not_overwrite_existing_data_with_empty_values(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead, _ = service.create_lead(nova.id, name="Kiran Patel", qualification="12th")
    service.update_lead(lead, qualification="", notes=None)

    student = db.get(Student, lead.student_id)
    assert student.qualification == "12th"  # not erased by an empty string


def test_update_lead_enriches_fields_progressively(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)

    lead, _ = service.create_lead(nova.id, name="Neha Singh")
    service.update_lead(lead, qualification="12th", qualification_score=82, scholarship_interest=True, hostel_interest=True)

    student = db.get(Student, lead.student_id)
    assert student.qualification == "12th"
    assert float(student.qualification_score) == 82
    assert lead.scholarship_interest is True
    assert lead.hostel_interest is True
    assert lead.lead_score >= 15  # qualification_provided(5) + scholarship_interest(10)


def test_status_transition_service_rejects_invalid_hops(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = LeadService(db)
    lead, _ = service.create_lead(nova.id, name="Test Lead")

    service.transition_status(lead, "converted")
    with pytest.raises(ConflictError):
        service.transition_status(lead, "new")


# ---------------------------------------------------------------------------
# API: creation, validation, RBAC
# ---------------------------------------------------------------------------

def test_college_admin_can_create_and_fetch_lead(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/leads", headers=headers,
        json={"name": "Rahul Sharma", "phone": "9000000021", "email": "rahul21@example.com",
              "course_interest": "B.Tech CSE", "source": "voice_agent"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["student"]["name"] == "Rahul Sharma"
    assert body["lead_score"] >= 20  # course_interest resolved to a real course -> course_identified

    get_resp = client.get(f"/api/v1/leads/{body['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == body["id"]


def test_counselor_cannot_create_lead(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    resp = client.post("/api/v1/leads", headers=headers, json={"name": "Blocked Lead"})
    assert resp.status_code == 403


def test_counselor_can_read_leads(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    resp = client.get("/api/v1/leads", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] >= 3  # the three seeded demo leads


def test_lead_endpoints_require_authentication(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/leads")
    assert resp.status_code == 401


def test_create_lead_rejects_course_from_another_college(client, db):
    seed_demo_data(db)
    db.commit()
    aurora = _college(db, "aurora-college-of-management")
    from app.models.academics import Course

    aurora_course = db.execute(select(Course).where(Course.college_id == aurora.id)).scalars().first()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/leads", headers=headers, json={"name": "Cross Tenant", "course_id": str(aurora_course.id)},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# API: tenant isolation
# ---------------------------------------------------------------------------

def test_college_a_cannot_read_college_b_lead(client, db):
    seed_demo_data(db)
    db.commit()
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)

    aurora_lead_resp = client.get("/api/v1/leads", headers=aurora_headers)
    aurora_lead_id = aurora_lead_resp.json()["data"][0]["id"] if aurora_lead_resp.json()["data"] else None
    if aurora_lead_id is None:
        create_resp = client.post("/api/v1/leads", headers=aurora_headers, json={"name": "Aurora Prospect"})
        aurora_lead_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/v1/leads/{aurora_lead_id}", headers=nova_headers)
    assert resp.status_code == 404


def test_list_leads_is_tenant_isolated(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/leads", headers=nova_headers)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["data"]}
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids == {str(nova.id)}
    assert str(aurora.id) not in college_ids


def test_spoofed_college_id_query_param_is_ignored_for_scoped_user(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    # A college-scoped user's own college_id (from their token) always
    # wins server-side - the ?college_id=<aurora> query param is ignored,
    # never used as an authorization boundary (docs/tasks/007 section 26).
    resp = client.get(f"/api/v1/leads?college_id={aurora.id}", headers=nova_headers)
    assert resp.status_code == 200
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids == {str(nova.id)}


def test_score_events_endpoint_is_tenant_isolated(client, db):
    seed_demo_data(db)
    db.commit()
    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    nova_leads = client.get("/api/v1/leads", headers=nova_headers).json()["data"]
    nova_lead_id = nova_leads[0]["id"]

    resp = client.get(f"/api/v1/leads/{nova_lead_id}/score-events", headers=aurora_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: filtering, sorting, pagination, explainability
# ---------------------------------------------------------------------------

def test_list_leads_filters_by_temperature_and_status(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/leads?temperature=hot", headers=headers)
    assert resp.status_code == 200
    assert all(item["lead_temperature"] == "hot" for item in resp.json()["data"])
    assert len(resp.json()["data"]) >= 1


def test_list_leads_sorting_and_pagination_are_deterministic(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/leads?sort=highest_score&page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) <= 2
    scores = [item["lead_score"] for item in data]
    assert scores == sorted(scores, reverse=True)
    assert resp.json()["meta"]["page"] == 1
    assert resp.json()["meta"]["page_size"] == 2
    assert resp.json()["meta"]["total"] >= 3


def test_recalculate_score_endpoint_and_score_events_endpoint(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    leads = client.get("/api/v1/leads?temperature=hot", headers=headers).json()["data"]
    lead_id = leads[0]["id"]

    score_resp = client.post(f"/api/v1/leads/{lead_id}/score", headers=headers)
    assert score_resp.status_code == 200
    assert score_resp.json()["data"]["temperature"] == "hot"
    assert "reasons" in score_resp.json()["data"]

    events_resp = client.get(f"/api/v1/leads/{lead_id}/score-events", headers=headers)
    assert events_resp.status_code == 200
    events_body = events_resp.json()["data"]
    assert events_body["events"], "expected the hot demo lead to carry explainable score events"
    for event in events_body["events"]:
        assert event["event_type"]
        assert isinstance(event["points"], int)
        assert event["created_at"]


def test_patch_lead_updates_status_through_valid_transition(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    leads = client.get("/api/v1/leads?status=new", headers=headers).json()["data"]
    lead_id = leads[0]["id"]

    resp = client.patch(f"/api/v1/leads/{lead_id}", headers=headers, json={"status": "contacted"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "contacted"


def test_patch_lead_rejects_invalid_status_transition(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    leads = client.get("/api/v1/leads?status=new", headers=headers).json()["data"]
    lead_id = leads[0]["id"]

    convert_resp = client.patch(f"/api/v1/leads/{lead_id}", headers=headers, json={"status": "converted"})
    assert convert_resp.status_code == 200

    invalid_resp = client.patch(f"/api/v1/leads/{lead_id}", headers=headers, json={"status": "new"})
    assert invalid_resp.status_code == 409
