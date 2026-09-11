"""Task 009 - application assistance & management tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.seed import seed_demo_data
from app.models.academics import Course
from app.models.applications import Application, ApplicationDocument
from app.models.college import College
from app.models.leads import LeadScoreEvent
from app.models.student import Student
from app.services.applications import ApplicationService, is_allowed_application_transition
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


def _course(db, college_id, code: str) -> Course:
    return db.execute(select(Course).where(Course.college_id == college_id, Course.code == code)).scalar_one()


def _bare_student(db, college_id, **fields) -> Student:
    student = Student(college_id=college_id, **fields)
    db.add(student)
    db.flush()
    return student


def _fully_qualified_bca_student(db, college_id) -> Student:
    return _bare_student(db, college_id, full_name="Ready Student", qualification="12th", qualification_score=72)


def _upload_all_mandatory_documents(service: ApplicationService, application: Application) -> None:
    for item in service.checklist(application):
        if item["mandatory"]:
            service.add_document(application, document_type=item["document_type"])


# ---------------------------------------------------------------------------
# Service-level: creation, dedup, idempotency, tenant validation
# ---------------------------------------------------------------------------

def test_create_draft_creates_application_with_expected_defaults(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)

    application, created = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)
    assert created is True
    assert application.status == "draft"
    assert application.application_number is None
    assert 0 <= application.completion_percentage <= 100


def test_create_draft_rejects_course_from_another_college(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    aurora = _college(db, "aurora-college-of-management")
    aurora_course = _course(db, aurora.id, "BBA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        service.create_draft(college_id=nova.id, student_id=student.id, course_id=aurora_course.id)


def test_create_draft_reuses_existing_draft_for_same_student_course(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)

    first, created1 = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)
    second, created2 = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)
    assert created1 is True
    assert created2 is False
    assert first.id == second.id


def test_create_draft_is_idempotent_via_idempotency_key(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)

    key = "draft-retry-key"
    first, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, idempotency_key=key)
    second, created2 = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, idempotency_key=key)
    assert first.id == second.id
    assert created2 is False


# ---------------------------------------------------------------------------
# Service-level: draft editing
# ---------------------------------------------------------------------------

def test_update_draft_sets_intake_and_moves_to_in_progress(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)

    service.update_draft(application, intake="2026-27")
    assert application.intake == "2026-27"
    assert application.status == "in_progress"


def test_update_draft_rejected_once_submitted(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)
    service.submit(nova.id, application.id)

    with pytest.raises(ConflictError):
        service.update_draft(application, intake="2027-28")


# ---------------------------------------------------------------------------
# Service-level: documents & checklist
# ---------------------------------------------------------------------------

def test_checklist_reflects_missing_and_uploaded_documents(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)

    checklist = service.checklist(application)
    mandatory_types = [item["document_type"] for item in checklist if item["mandatory"]]
    assert "Class 10 marksheet" in mandatory_types
    assert all(item["status"] == "missing" for item in checklist)

    service.add_document(application, document_type="Class 10 marksheet", file_name="marksheet.pdf")
    checklist2 = service.checklist(application)
    updated = next(i for i in checklist2 if i["document_type"] == "Class 10 marksheet")
    assert updated["status"] == "uploaded"


def test_update_document_status_to_verified_sets_verified_at(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)
    document = service.add_document(application, document_type="Class 10 marksheet")

    verified = service.update_document_status(application, document, status="verified")
    assert verified.status == "verified"
    assert verified.verified_at is not None


def test_cannot_remove_a_verified_document(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)
    document = service.add_document(application, document_type="Class 10 marksheet")
    service.update_document_status(application, document, status="verified")

    with pytest.raises(ConflictError):
        service.remove_document(application, document)


# ---------------------------------------------------------------------------
# Service-level: submission validation & lifecycle
# ---------------------------------------------------------------------------

def test_submit_rejects_when_information_missing(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id)

    with pytest.raises(ValidationAppError):
        service.submit(nova.id, application.id)


def test_submit_succeeds_and_generates_application_number(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)

    submitted = service.submit(nova.id, application.id)
    assert submitted.status == "submitted"
    assert submitted.application_number is not None
    assert submitted.submitted_at is not None
    assert submitted.completion_percentage == 100


def test_submit_is_idempotent_with_idempotency_key(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)

    key = "submit-retry-key"
    first = service.submit(nova.id, application.id, idempotency_key=key)
    second = service.submit(nova.id, application.id, idempotency_key=key)
    assert first.application_number == second.application_number
    assert second.status == "submitted"


def test_submit_without_idempotency_key_conflicts_when_already_submitted(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)
    service.submit(nova.id, application.id)

    with pytest.raises(ConflictError):
        service.submit(nova.id, application.id)


def test_submit_enriches_existing_lead_and_never_creates_one(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    lead_service = LeadService(db)
    lead, _ = lead_service.create_lead(nova.id, name="Applicant Student")
    student = db.get(Student, lead.student_id)
    student.qualification = "12th"
    student.qualification_score = 72
    db.flush()

    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)
    score_before_submit = db.get(type(lead), lead.id).lead_score

    service.submit(nova.id, application.id)
    db.refresh(lead)
    assert lead.lead_score == score_before_submit + 10
    event = db.execute(
        select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.event_type == "application_submitted")
    ).scalar_one()
    assert event.points == 10


def test_submit_does_not_create_a_lead_for_a_student_without_one(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)
    application, _ = service.create_draft(college_id=nova.id, student_id=student.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, application)
    service.submit(nova.id, application.id)

    from app.models.leads import Lead
    count = db.execute(select(Lead).where(Lead.student_id == student.id)).scalars().all()
    assert count == []


def test_withdraw_from_draft_and_blocked_after_approval(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student1 = _fully_qualified_bca_student(db, nova.id)
    student2 = _fully_qualified_bca_student(db, nova.id)
    service = ApplicationService(db)

    draft_app, _ = service.create_draft(college_id=nova.id, student_id=student1.id, course_id=course.id)
    withdrawn = service.withdraw(nova.id, draft_app.id, reason="Changed mind")
    assert withdrawn.status == "withdrawn"
    assert "Changed mind" in withdrawn.notes

    app2, _ = service.create_draft(college_id=nova.id, student_id=student2.id, course_id=course.id, intake="2026-27")
    _upload_all_mandatory_documents(service, app2)
    service.submit(nova.id, app2.id)
    service.transition_status(app2, "under_review")
    service.transition_status(app2, "approved")

    with pytest.raises(ConflictError):
        service.withdraw(nova.id, app2.id)


def test_status_transition_graph_rejects_invalid_moves(db):
    assert is_allowed_application_transition("draft", "in_progress")
    assert is_allowed_application_transition("submitted", "under_review")
    assert is_allowed_application_transition("under_review", "approved")
    assert not is_allowed_application_transition("draft", "approved")
    assert not is_allowed_application_transition("approved", "under_review")
    assert not is_allowed_application_transition("withdrawn", "draft")


# ---------------------------------------------------------------------------
# API: creation, RBAC, tenant isolation
# ---------------------------------------------------------------------------

def test_college_admin_can_create_and_get_application(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/applications", headers=headers,
        json={"student_id": str(student.id), "course_id": str(course.id), "intake": "2026-27"},
    )
    assert resp.status_code == 201, resp.text
    application_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "draft"

    get_resp = client.get(f"/api/v1/applications/{application_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == application_id


def test_counselor_cannot_create_application_but_can_read(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    db.commit()
    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)

    create_resp = client.post(
        "/api/v1/applications", headers=counselor_headers,
        json={"student_id": str(student.id), "course_id": str(course.id)},
    )
    assert create_resp.status_code == 403

    list_resp = client.get("/api/v1/applications", headers=counselor_headers)
    assert list_resp.status_code == 200


def test_unauthenticated_access_denied(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/applications")
    assert resp.status_code == 401


def test_college_a_cannot_access_college_b_application(client, db):
    seed_demo_data(db)
    db.commit()
    aurora = _college(db, "aurora-college-of-management")
    aurora_course = _course(db, aurora.id, "BBA")
    aurora_student = _bare_student(db, aurora.id)
    db.commit()

    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    create_resp = client.post(
        "/api/v1/applications", headers=aurora_headers,
        json={"student_id": str(aurora_student.id), "course_id": str(aurora_course.id)},
    )
    application_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/v1/applications/{application_id}", headers=nova_headers)
    assert resp.status_code == 404


def test_list_applications_is_tenant_isolated(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get("/api/v1/applications", headers=headers)
    assert resp.status_code == 200
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids <= {str(nova.id)}


# ---------------------------------------------------------------------------
# API: full lifecycle through submission, documents, withdrawal
# ---------------------------------------------------------------------------

def test_full_application_lifecycle_via_api(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _fully_qualified_bca_student(db, nova.id)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post(
        "/api/v1/applications", headers=headers,
        json={"student_id": str(student.id), "course_id": str(course.id)},
    )
    application_id = create_resp.json()["data"]["id"]

    patch_resp = client.patch(
        f"/api/v1/applications/{application_id}", headers=headers, json={"intake": "2026-27"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["status"] == "in_progress"

    checklist_resp = client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    assert checklist_resp.status_code == 200
    mandatory_docs = [d["document_type"] for d in checklist_resp.json()["data"] if d["mandatory"]]
    assert mandatory_docs

    for doc_type in mandatory_docs:
        doc_resp = client.post(
            f"/api/v1/applications/{application_id}/documents", headers=headers,
            json={"document_type": doc_type, "file_name": "scan.pdf"},
        )
        assert doc_resp.status_code == 201, doc_resp.text

    status_resp = client.get(f"/api/v1/applications/{application_id}/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["missing_information"] == []

    submit_resp = client.post(f"/api/v1/applications/{application_id}/submit", headers=headers, json={})
    assert submit_resp.status_code == 200, submit_resp.text
    assert submit_resp.json()["data"]["status"] == "submitted"
    assert submit_resp.json()["data"]["application_number"]

    # Staff decision workflow via PATCH status.
    review_resp = client.patch(
        f"/api/v1/applications/{application_id}", headers=headers, json={"status": "under_review"},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["data"]["status"] == "under_review"

    invalid_resp = client.patch(
        f"/api/v1/applications/{application_id}", headers=headers, json={"status": "draft"},
    )
    assert invalid_resp.status_code == 409


def test_submit_via_api_rejects_incomplete_application(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post(
        "/api/v1/applications", headers=headers,
        json={"student_id": str(student.id), "course_id": str(course.id)},
    )
    application_id = create_resp.json()["data"]["id"]

    submit_resp = client.post(f"/api/v1/applications/{application_id}/submit", headers=headers, json={})
    assert submit_resp.status_code == 422
    assert submit_resp.json()["error"]["details"]["missing_information"]


def test_withdraw_via_api(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post(
        "/api/v1/applications", headers=headers,
        json={"student_id": str(student.id), "course_id": str(course.id)},
    )
    application_id = create_resp.json()["data"]["id"]

    withdraw_resp = client.post(
        f"/api/v1/applications/{application_id}/withdraw", headers=headers, json={"reason": "No longer interested"},
    )
    assert withdraw_resp.status_code == 200
    assert withdraw_resp.json()["data"]["status"] == "withdrawn"


def test_document_verify_and_delete_via_api(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    course = _course(db, nova.id, "BCA")
    student = _bare_student(db, nova.id)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post(
        "/api/v1/applications", headers=headers,
        json={"student_id": str(student.id), "course_id": str(course.id)},
    )
    application_id = create_resp.json()["data"]["id"]

    doc_resp = client.post(
        f"/api/v1/applications/{application_id}/documents", headers=headers,
        json={"document_type": "Class 10 marksheet"},
    )
    document_id = doc_resp.json()["data"]["id"]

    verify_resp = client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}", headers=headers, json={"status": "verified"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["data"]["status"] == "verified"

    delete_resp = client.delete(f"/api/v1/applications/{application_id}/documents/{document_id}", headers=headers)
    assert delete_resp.status_code == 409  # verified documents cannot be removed
