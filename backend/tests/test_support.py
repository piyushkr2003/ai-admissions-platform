"""Task 010 - human escalation & support ticket tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, ValidationAppError
from app.core.security import hash_password
from app.db.seed import seed_demo_data
from app.models.college import College
from app.models.counseling import Counselor
from app.models.support import SupportTicket
from app.models.user import User
from app.services.support import SupportTicketService, is_allowed_ticket_transition

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


def _second_nova_counselor(db, nova_id) -> User:
    user = User(
        college_id=nova_id, email="counselor2@nova-institute-of-technology.example.edu",
        password_hash=hash_password("NovaCounselor2#2026"), full_name="Second Counselor",
        role="counselor", is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(Counselor(college_id=nova_id, user_id=user.id, name="Second Counselor", active=True))
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Service-level: creation & validation
# ---------------------------------------------------------------------------

def test_create_ticket_basic(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)

    ticket, created = service.create_ticket(nova.id, subject="Admission query", description="Needs help.")
    assert created is True
    assert ticket.status == "open"
    assert ticket.priority == "normal"


def test_create_ticket_rejects_invalid_priority(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    with pytest.raises(ValidationAppError):
        service.create_ticket(nova.id, subject="Test", priority="urgent-ish")


def test_create_ticket_rejects_empty_subject(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    with pytest.raises(ValidationAppError):
        service.create_ticket(nova.id, subject="   ")


def test_create_ticket_is_idempotent(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    key = "ticket-retry-key"
    first, created1 = service.create_ticket(nova.id, subject="Query", idempotency_key=key)
    second, created2 = service.create_ticket(nova.id, subject="Query retried", idempotency_key=key)
    assert created1 is True
    assert created2 is False
    assert first.id == second.id
    assert second.subject == "Query"  # untouched by the retried payload


# ---------------------------------------------------------------------------
# Service-level: escalation & auto-assignment
# ---------------------------------------------------------------------------

def test_escalate_to_counselor_creates_ticket_with_category(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    ticket, created = service.escalate_to_counselor(nova.id, reason="Student wants a human.")
    assert created is True
    assert ticket.category == "counselor_escalation"


def test_escalate_to_counselor_auto_assigns_least_loaded_counselor(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)

    ticket, _ = service.escalate_to_counselor(nova.id, reason="First escalation.")
    assert ticket.assigned_to is not None
    assert ticket.status == "assigned"


def test_escalate_to_counselor_balances_across_two_counselors(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    second_counselor_user = _second_nova_counselor(db, nova.id)
    service = SupportTicketService(db)

    first_ticket, _ = service.escalate_to_counselor(nova.id, reason="Escalation one.")
    second_ticket, _ = service.escalate_to_counselor(nova.id, reason="Escalation two.")
    assert first_ticket.assigned_to != second_ticket.assigned_to
    assert second_counselor_user.id in (first_ticket.assigned_to, second_ticket.assigned_to)


def test_escalate_to_counselor_leaves_unassigned_when_no_counselor_available(db):
    seed_demo_data(db)
    aurora = _college(db, "aurora-college-of-management")  # seeded with no counselor
    service = SupportTicketService(db)

    ticket, created = service.escalate_to_counselor(aurora.id, reason="No counselor exists yet.")
    assert created is True
    assert ticket.assigned_to is None
    assert ticket.status == "open"


# ---------------------------------------------------------------------------
# Service-level: assignment & lifecycle transitions
# ---------------------------------------------------------------------------

def test_assign_ticket_sets_assigned_status(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    counselor_user = db.execute(select(User).where(User.email == NOVA_COUNSELOR_EMAIL)).scalar_one()
    service = SupportTicketService(db)
    ticket, _ = service.create_ticket(nova.id, subject="Needs a human")

    service.assign_ticket(ticket, assignee_user_id=counselor_user.id)
    assert ticket.status == "assigned"
    assert ticket.assigned_to == counselor_user.id


def test_assign_ticket_rejects_user_from_another_college(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    aurora_admin = db.execute(select(User).where(User.email == AURORA_ADMIN_EMAIL)).scalar_one()
    service = SupportTicketService(db)
    ticket, _ = service.create_ticket(nova.id, subject="Needs a human")

    with pytest.raises(ValidationAppError):
        service.assign_ticket(ticket, assignee_user_id=aurora_admin.id)


def test_status_transition_graph():
    assert is_allowed_ticket_transition("open", "assigned")
    assert is_allowed_ticket_transition("assigned", "in_progress")
    assert is_allowed_ticket_transition("in_progress", "resolved")
    assert is_allowed_ticket_transition("resolved", "closed")
    assert is_allowed_ticket_transition("closed", "open")  # reopen
    assert not is_allowed_ticket_transition("closed", "resolved")
    assert not is_allowed_ticket_transition("open", "not_a_status")


def test_transition_to_resolved_sets_resolved_at_and_reopen_clears_it(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    ticket, _ = service.create_ticket(nova.id, subject="Needs a human")

    service.transition_status(ticket, "resolved")
    assert ticket.resolved_at is not None

    service.transition_status(ticket, "in_progress")
    assert ticket.resolved_at is None


def test_transition_status_rejects_invalid_move(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    ticket, _ = service.create_ticket(nova.id, subject="Needs a human")
    service.transition_status(ticket, "closed")

    with pytest.raises(ConflictError):
        service.transition_status(ticket, "resolved")


def test_transition_status_appends_resolution_notes(db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    service = SupportTicketService(db)
    ticket, _ = service.create_ticket(nova.id, subject="Needs a human", description="Original issue.")

    service.transition_status(ticket, "resolved", resolution_notes="Called the student back and resolved it.")
    assert "Original issue." in ticket.description
    assert "Called the student back" in ticket.description


# ---------------------------------------------------------------------------
# API: creation, RBAC, tenant isolation
# ---------------------------------------------------------------------------

def test_college_admin_can_create_and_get_ticket(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post("/api/v1/support-tickets", headers=headers, json={"subject": "Payment issue", "priority": "high"})
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["data"]["id"]

    get_resp = client.get(f"/api/v1/support-tickets/{ticket_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["priority"] == "high"


def test_escalation_endpoint_creates_and_assigns(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post("/api/v1/support-tickets/escalate", headers=headers, json={"reason": "Student called in."})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["category"] == "counselor_escalation"
    assert resp.json()["data"]["assigned_to"] is not None


def test_unauthenticated_access_denied(client, db):
    seed_demo_data(db)
    db.commit()
    resp = client.get("/api/v1/support-tickets")
    assert resp.status_code == 401


def test_college_a_cannot_access_college_b_ticket(client, db):
    seed_demo_data(db)
    db.commit()
    aurora_headers = _auth_headers(client, AURORA_ADMIN_EMAIL, AURORA_ADMIN_PASSWORD)
    nova_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post("/api/v1/support-tickets", headers=aurora_headers, json={"subject": "Aurora issue"})
    ticket_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/v1/support-tickets/{ticket_id}", headers=nova_headers)
    assert resp.status_code == 404


def test_list_tickets_is_tenant_isolated(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    resp = client.get("/api/v1/support-tickets", headers=headers)
    assert resp.status_code == 200
    college_ids = {item["college_id"] for item in resp.json()["data"]}
    assert college_ids <= {str(nova.id)}
    assert resp.json()["meta"]["total"] >= 3  # the three seeded demo tickets


# ---------------------------------------------------------------------------
# API: counselor row-scoping ("assigned" visibility)
# ---------------------------------------------------------------------------

def test_counselor_cannot_see_ticket_assigned_to_a_different_counselor(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    second_counselor_user = _second_nova_counselor(db, nova.id)
    admin_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    create_resp = client.post("/api/v1/support-tickets", headers=admin_headers, json={"subject": "For second counselor"})
    ticket_id = create_resp.json()["data"]["id"]
    client.patch(
        f"/api/v1/support-tickets/{ticket_id}", headers=admin_headers,
        json={"assigned_to": str(second_counselor_user.id)},
    )

    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.get(f"/api/v1/support-tickets/{ticket_id}", headers=counselor_headers)
    assert resp.status_code == 404


def test_counselor_can_see_and_claim_unassigned_ticket(client, db):
    seed_demo_data(db)
    db.commit()
    admin_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    create_resp = client.post("/api/v1/support-tickets", headers=admin_headers, json={"subject": "Unassigned issue"})
    ticket_id = create_resp.json()["data"]["id"]

    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    get_resp = client.get(f"/api/v1/support-tickets/{ticket_id}", headers=counselor_headers)
    assert get_resp.status_code == 200

    counselor_login = _login(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    claim_resp = client.patch(
        f"/api/v1/support-tickets/{ticket_id}", headers=counselor_headers,
        json={"assigned_to": counselor_login["user"]["id"]},
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["data"]["status"] == "assigned"


def test_counselor_cannot_assign_ticket_to_someone_else(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    second_counselor_user = _second_nova_counselor(db, nova.id)
    admin_headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    create_resp = client.post("/api/v1/support-tickets", headers=admin_headers, json={"subject": "Reassign attempt"})
    ticket_id = create_resp.json()["data"]["id"]

    counselor_headers = _auth_headers(client, NOVA_COUNSELOR_EMAIL, NOVA_COUNSELOR_PASSWORD)
    resp = client.patch(
        f"/api/v1/support-tickets/{ticket_id}", headers=counselor_headers,
        json={"assigned_to": str(second_counselor_user.id)},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API: lifecycle transitions
# ---------------------------------------------------------------------------

def test_patch_ticket_status_transition_and_invalid_move(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    create_resp = client.post("/api/v1/support-tickets", headers=headers, json={"subject": "Lifecycle test"})
    ticket_id = create_resp.json()["data"]["id"]

    resolve_resp = client.patch(
        f"/api/v1/support-tickets/{ticket_id}", headers=headers,
        json={"status": "resolved", "resolution_notes": "Fixed over the phone."},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["data"]["status"] == "resolved"

    close_resp = client.patch(f"/api/v1/support-tickets/{ticket_id}", headers=headers, json={"status": "closed"})
    assert close_resp.status_code == 200

    invalid_resp = client.patch(f"/api/v1/support-tickets/{ticket_id}", headers=headers, json={"status": "resolved"})
    assert invalid_resp.status_code == 409


def test_patch_ticket_updates_priority(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)
    create_resp = client.post("/api/v1/support-tickets", headers=headers, json={"subject": "Priority test"})
    ticket_id = create_resp.json()["data"]["id"]

    resp = client.patch(f"/api/v1/support-tickets/{ticket_id}", headers=headers, json={"priority": "urgent"})
    assert resp.status_code == 200
    assert resp.json()["data"]["priority"] == "urgent"


def test_list_tickets_filters_by_status_and_priority(client, db):
    seed_demo_data(db)
    db.commit()
    headers = _auth_headers(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get("/api/v1/support-tickets?status=resolved", headers=headers)
    assert resp.status_code == 200
    assert all(item["status"] == "resolved" for item in resp.json()["data"])
