"""Task 006 - HTTP layer: public conversations + admin agent endpoints."""
from __future__ import annotations

from sqlalchemy import select

from app.db.seed import seed_demo_data
from app.models.college import College

NOVA_ADMIN_EMAIL = "admin@nova-institute-of-technology.example.edu"
NOVA_ADMIN_PASSWORD = "NovaAdmin#2026"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def test_public_conversation_flow(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    create_resp = client.post("/api/v1/conversations", json={"college_id": str(nova.id), "channel": "web_voice"})
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["data"]["conversation_id"]

    msg_resp = client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "Tell me about B.Tech CSE."}
    )
    assert msg_resp.status_code == 201
    assert "Computer Science" in msg_resp.json()["data"]["response"]
    # Internal tool names must not be exposed to the public conversation API.
    assert "tools_used" not in msg_resp.json()["data"]

    history_resp = client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert history_resp.status_code == 200
    assert len(history_resp.json()["data"]) == 2

    end_resp = client.post(f"/api/v1/conversations/{conversation_id}/end")
    assert end_resp.status_code == 200
    assert end_resp.json()["data"]["status"] == "completed"

    # A completed conversation should not accept further messages.
    blocked_resp = client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "Hello again"}
    )
    assert blocked_resp.status_code == 422


def test_conversation_rejected_for_draft_college(client, db):
    seed_demo_data(db)
    nova = _college(db, "nova-institute-of-technology")
    nova.status = "draft"
    db.commit()

    resp = client.post("/api/v1/conversations", json={"college_id": str(nova.id), "channel": "web_voice"})
    assert resp.status_code == 404


def test_conversation_invalid_college_id_rejected(client, db):
    resp = client.post("/api/v1/conversations", json={"college_id": "not-a-uuid"})
    assert resp.status_code == 422


def test_agent_test_endpoint_requires_auth(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")

    resp = client.post(
        f"/api/v1/agent/test?college_id={nova.id}", json={"message": "What is the CSE fee?"}
    )
    assert resp.status_code == 401


def test_agent_test_endpoint_returns_tools_used_for_admin(client, db):
    seed_demo_data(db)
    db.commit()
    nova = _college(db, "nova-institute-of-technology")
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/agent/test",
        json={"message": "What is the eligibility for B.Tech CSE?"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert "response" in body
    assert isinstance(body["tools_used"], list)
    assert "get_course_details" in body["tools_used"]


def test_agent_test_endpoint_ignores_spoofed_college_id_query_param(client, db):
    """A college-scoped admin's requests always run against their own
    tenant (from the signed token), regardless of what college_id query
    parameter they attach - it is not merely rejected, it is ignored."""
    seed_demo_data(db)
    db.commit()
    aurora = _college(db, "aurora-college-of-management")
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.post(
        f"/api/v1/agent/test?college_id={aurora.id}",
        json={"message": "Tell me about BBA."},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert "Bachelor of Business Administration" not in body["response"]


def test_get_agent_config_for_own_college(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, NOVA_ADMIN_EMAIL, NOVA_ADMIN_PASSWORD)

    resp = client.get(
        "/api/v1/agent/config", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["agent_name"] == "Nova Assist"


def test_counselor_cannot_write_agent_config(client, db):
    seed_demo_data(db)
    db.commit()
    tokens = _login(client, "counselor@nova-institute-of-technology.example.edu", "NovaCounselor#2026")

    resp = client.patch(
        "/api/v1/agent/config",
        json={"agent_name": "Hijacked"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
