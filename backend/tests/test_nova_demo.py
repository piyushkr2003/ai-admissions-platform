"""Nova demo-data integration tests (fictional data only).

Covers: idempotent bootstrap/seed, structured data mapping, RAG
ingestion, Nova-scoped retrieval, tenant isolation, agent tool calls
(structured-path proof), eligibility/fee/scholarship/date/document/
counselor-availability lookups, appointment booking, application
creation, and the full demo conversation workflow end to end through
the real AgentOrchestrator - the same production pipeline used by
every other tenant, per AGENTS.md/CLAUDE.md ("do not create a special
Nova-only admissions implementation").
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import admissions, appointments, applications, courses, eligibility, fees, knowledge, leads as leads_tools, scholarships
from app.agent.tools.base import ToolContext
from app.colleges.context import get_college_context
from app.db.nova_demo import NOVA_SLUG, bootstrap_nova_demo, reset_nova_demo_knowledge
from app.db.seed import seed_demo_data
from app.models.academics import AdmissionDate, Course, CourseEligibilityRule, RequiredDocument, Scholarship
from app.models.college import College
from app.models.conversations import Conversation
from app.models.counseling import Counselor, CounselorAvailability
from app.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.models.leads import Lead
from app.models.support import FAQ
from app.rag.retrieval.service import RetrievalService


def _college(db, slug: str) -> College:
    return db.execute(select(College).where(College.slug == slug)).scalar_one()


def _new_conversation(db, college_id) -> Conversation:
    conv = Conversation(college_id=college_id, channel="web_voice", session_id="nova-demo-test", status="active", state={})
    db.add(conv)
    db.flush()
    return conv


def _orchestrator(db, college_id) -> AgentOrchestrator:
    context = get_college_context(db, college_id)
    return AgentOrchestrator(db, context)


def _tool_context(db, college_id, *, student_id=None) -> ToolContext:
    context = get_college_context(db, college_id)
    return ToolContext(db=db, college=context, conversation_id=uuid.uuid4(), student_id=student_id)


def _second_college(db) -> College:
    """A minimal, independent tenant used only to prove Nova data never
    leaks across tenants. Deliberately not the `aurora` fixture from
    app.db.seed, so these tests do not depend on that fixture's shape."""
    college = College(
        name="Test Isolation College", slug="test-isolation-college", status="active",
        supported_languages=["en"], feature_flags={"appointment_booking_enabled": True},
    )
    db.add(college)
    db.flush()
    return college


# ---------------------------------------------------------------------------
# Bootstrap / idempotency
# ---------------------------------------------------------------------------

def test_bootstrap_creates_nova_as_a_single_tenant(db):
    result = bootstrap_nova_demo(db)
    nova = result["college"]
    assert nova.slug == NOVA_SLUG
    assert nova.status == "active"
    assert nova.feature_flags["demo_only"] is True

    all_nova = db.execute(select(College).where(College.slug == NOVA_SLUG)).scalars().all()
    assert len(all_nova) == 1


def test_bootstrap_is_idempotent_on_fresh_database(db):
    first = bootstrap_nova_demo(db)
    db.commit()
    second = bootstrap_nova_demo(db)
    db.commit()

    assert first["college"].id == second["college"].id
    assert len(first["courses"]) == len(second["courses"]) == 5

    nova_id = first["college"].id
    assert db.execute(select(Course).where(Course.college_id == nova_id)).scalars().all().__len__() == 5
    assert db.execute(select(Scholarship).where(Scholarship.college_id == nova_id)).scalars().all().__len__() == 3
    assert db.execute(select(AdmissionDate).where(AdmissionDate.college_id == nova_id)).scalars().all().__len__() == 6
    assert db.execute(select(RequiredDocument).where(RequiredDocument.college_id == nova_id)).scalars().all().__len__() == 7
    assert db.execute(select(Counselor).where(Counselor.college_id == nova_id)).scalars().all().__len__() == 3
    assert db.execute(select(FAQ).where(FAQ.college_id == nova_id)).scalars().all().__len__() == 7
    assert db.execute(select(KnowledgeSource).where(KnowledgeSource.college_id == nova_id)).scalars().all().__len__() == 2

    # Availability: 5 dataset slot-entries x 5 weekdays = 25, unchanged by rerun.
    availability_count = len(
        db.execute(select(CounselorAvailability).where(CounselorAvailability.college_id == nova_id)).scalars().all()
    )
    assert availability_count == 25


def test_bootstrap_upserts_a_legacy_nova_college_without_duplication(db):
    """If app.db.seed.seed_demo_data already created a 'Nova Institute of
    Technology' row for the general test suite, the Nova demo bootstrap
    must enrich that same row - never create a second college with the
    same (unique) slug."""
    legacy = seed_demo_data(db)
    legacy_nova_id = legacy["nova"]["college"].id
    db.commit()

    result = bootstrap_nova_demo(db)
    db.commit()

    assert result["college"].id == legacy_nova_id
    all_nova = db.execute(select(College).where(College.slug == NOVA_SLUG)).scalars().all()
    assert len(all_nova) == 1

    # The legacy fixture's own course codes (also present in nova_demo_data)
    # were enriched in place, not duplicated.
    courses = db.execute(select(Course).where(Course.college_id == legacy_nova_id)).scalars().all()
    codes = [c.code for c in courses]
    assert len(codes) == len(set(codes))


def test_reset_then_rebootstrap_reingests_knowledge_without_duplicating_chunks(db):
    first = bootstrap_nova_demo(db)
    db.commit()
    nova_id = first["college"].id
    first_chunk_count = len(
        db.execute(select(KnowledgeChunk).where(KnowledgeChunk.college_id == nova_id)).scalars().all()
    )
    assert first_chunk_count > 0

    reset_nova_demo_knowledge(db)
    db.commit()
    assert db.execute(select(KnowledgeSource).where(KnowledgeSource.college_id == nova_id)).scalars().all() == []

    bootstrap_nova_demo(db)
    db.commit()
    second_chunk_count = len(
        db.execute(select(KnowledgeChunk).where(KnowledgeChunk.college_id == nova_id)).scalars().all()
    )
    assert second_chunk_count == first_chunk_count


# ---------------------------------------------------------------------------
# Structured data mapping
# ---------------------------------------------------------------------------

def test_course_fee_and_eligibility_mapped_from_dataset(db):
    result = bootstrap_nova_demo(db)
    cse = result["courses"]["BTECH-CSE"]

    assert cse.name == "B.Tech Computer Science and Engineering"
    assert float(cse.annual_fee) == 185000
    assert float(cse.application_fee) == 1000
    assert float(cse.hostel_fee) == 95000
    assert cse.hostel_available is True
    assert "25,000" in cse.description  # documented "other fee" limitation

    rule = db.execute(
        select(CourseEligibilityRule).where(CourseEligibilityRule.course_id == cse.id)
    ).scalar_one()
    assert float(rule.minimum_percentage) == 60
    assert rule.entrance_exam_required is False
    assert set(rule.required_subjects) == {"Physics", "Mathematics"}
    assert "merit" in rule.additional_conditions["routes"]


def test_scholarship_mapped_with_parsed_percentage(db):
    result = bootstrap_nova_demo(db)
    names = {s.name: s for s in result["scholarships"]}
    merit = names["Nova Merit Scholarship"]
    assert merit.percentage == 25
    assert "90%" in merit.eligibility_criteria

    girls_tech = names["Women in Technology Scholarship"]
    assert girls_tech.percentage == 10
    assert "B.Tech CSE" in girls_tech.eligibility_criteria


def test_admission_dates_and_documents_mapped(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id

    dates = {d.title: d for d in result["admission_dates"]}
    assert dates["Applications open"].date.date().isoformat() == "2026-11-01"
    assert dates["Applications open"].date_type == "application_open"

    doc_names = {d.name for d in result["documents"]}
    assert "Recent passport-size photograph" in doc_names
    category_cert = next(d for d in result["documents"] if "Category certificate" in d.name)
    assert category_cert.mandatory is False


def test_counselors_and_availability_mapped(db):
    result = bootstrap_nova_demo(db)
    counselors = result["counselors"]
    assert set(counselors) == {"Ananya Rao", "Rahul Menon", "Meera Nair"}
    assert counselors["Ananya Rao"].email == "ananya.rao@nova-demo.edu"

    windows = db.execute(
        select(CounselorAvailability).where(CounselorAvailability.counselor_id == counselors["Ananya Rao"].id)
    ).scalars().all()
    # Two daily slots x 5 weekdays.
    assert len(windows) == 10


# ---------------------------------------------------------------------------
# RAG ingestion + Nova-scoped retrieval
# ---------------------------------------------------------------------------

def test_knowledge_base_and_faq_ingested_and_ready(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id
    sources = db.execute(select(KnowledgeSource).where(KnowledgeSource.college_id == nova_id)).scalars().all()
    assert len(sources) == 2
    assert all(s.status == "ready" for s in sources)
    names = {s.name for s in sources}
    assert names == {"Nova Demo Knowledge Base", "Nova Demo FAQs"}

    chunks = db.execute(select(KnowledgeChunk).where(KnowledgeChunk.college_id == nova_id)).scalars().all()
    assert len(chunks) > 0
    assert all(c.college_id == nova_id for c in chunks)


def test_retrieval_finds_nova_hostel_and_placement_content(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id
    service = RetrievalService(db)

    hostel_result = service.search(college_id=nova_id, query="Is hostel available for students?")
    assert hostel_result.has_reliable_evidence
    assert any("hostel" in r.content.lower() for r in hostel_result.results)

    placement_result = service.search(college_id=nova_id, query="What are the placement figures and packages?")
    assert placement_result.has_reliable_evidence
    assert any("placement" in r.content.lower() for r in placement_result.results)


def test_retrieval_is_scoped_to_nova_and_excludes_other_tenants(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id
    other = _second_college(db)
    db.commit()

    other_result = RetrievalService(db).search(college_id=other.id, query="Is hostel available for students?", record_unanswered=False)
    assert other_result.has_reliable_evidence is False

    nova_result = RetrievalService(db).search(college_id=nova_id, query="Is hostel available for students?")
    assert nova_result.has_reliable_evidence is True


# ---------------------------------------------------------------------------
# Agent tool validation - structured facts come from tools/DB, not an LLM
# ---------------------------------------------------------------------------

def test_get_course_details_and_list_active_courses(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)

    all_courses = courses.list_active_courses(ctx)
    assert len(all_courses) == 5

    detail = courses.get_course_details(ctx, course_query="B.Tech Computer Science")
    assert detail.success
    assert detail.data["name"] == "B.Tech Computer Science and Engineering"


def test_fee_tool_returns_structured_fee_not_llm_text(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)
    cse = result["courses"]["BTECH-CSE"]

    tool_result = fees.get_fee_structure(ctx, course_id=str(cse.id))
    assert tool_result.success
    assert tool_result.data["tuition_fee"] == 185000
    assert tool_result.data["currency"] == "INR"


def test_eligibility_tool_82_percent_is_eligible_for_cse(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)
    cse = result["courses"]["BTECH-CSE"]

    tool_result = eligibility.check_eligibility(ctx, course_id=str(cse.id), percentage=82)
    assert tool_result.success
    assert tool_result.data["status"] == "eligible"


def test_scholarship_tool_lists_nova_scholarships(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)

    tool_result = scholarships.get_scholarship_information(ctx)
    assert tool_result.success
    names = {s["name"] for s in tool_result.data["scholarships"]}
    assert "Nova Merit Scholarship" in names


def test_admission_dates_documents_and_availability_tools(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)
    cse = result["courses"]["BTECH-CSE"]

    dates_result = admissions.get_admission_dates(ctx, course_id=str(cse.id))
    assert dates_result.success
    assert dates_result.data["dates"]

    docs_result = admissions.get_required_documents(ctx)
    assert docs_result.success
    assert any("passport" in d["name"].lower() for d in docs_result.data["documents"])

    availability_result = appointments.check_counselor_availability(ctx)
    assert availability_result.success
    assert availability_result.data["slots"]


def test_knowledge_tool_used_for_hostel_question(db):
    result = bootstrap_nova_demo(db)
    ctx = _tool_context(db, result["college"].id)

    tool_result = knowledge.search_knowledge(ctx, query="Is hostel available for students?")
    assert tool_result.success
    assert any("hostel" in r["content"].lower() for r in tool_result.data["results"])


# ---------------------------------------------------------------------------
# Tenant isolation (structured + RAG + counselor availability)
# ---------------------------------------------------------------------------

def test_other_tenant_cannot_see_nova_courses_fees_scholarships_faqs(db):
    result = bootstrap_nova_demo(db)
    other = _second_college(db)
    db.commit()

    assert db.execute(select(Course).where(Course.college_id == other.id)).scalars().all() == []
    assert db.execute(select(Scholarship).where(Scholarship.college_id == other.id)).scalars().all() == []
    assert db.execute(select(FAQ).where(FAQ.college_id == other.id)).scalars().all() == []
    assert db.execute(select(KnowledgeChunk).where(KnowledgeChunk.college_id == other.id)).scalars().all() == []
    assert db.execute(select(CounselorAvailability).where(CounselorAvailability.college_id == other.id)).scalars().all() == []

    other_ctx = _tool_context(db, other.id)
    assert appointments.check_counselor_availability(other_ctx).data["slots"] == []
    assert courses.get_course_details(other_ctx, course_query="B.Tech CSE").success is False


def test_ai_agent_never_leaks_nova_data_to_another_tenant(db):
    bootstrap_nova_demo(db)
    other = _second_college(db)
    db.commit()

    conv = _new_conversation(db, other.id)
    result = _orchestrator(db, other.id).handle_message(conv, "Tell me about B.Tech Computer Science and Engineering.")

    assert "Computer Science and Engineering" not in result.response_text
    assert "185,000" not in result.response_text and "185000" not in result.response_text


# ---------------------------------------------------------------------------
# Appointment + application workflows against real Nova data
# ---------------------------------------------------------------------------

def test_book_appointment_against_nova_availability_persists(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id
    ctx = _tool_context(db, nova_id)

    slots = appointments.check_counselor_availability(ctx)
    assert slots.success and slots.data["slots"]
    chosen = slots.data["slots"][0]

    lead_ctx = _tool_context(db, nova_id)
    lead_result = leads_tools.create_lead(lead_ctx)
    assert lead_result.success
    lead_ctx.student_id = uuid.UUID(lead_result.data["student_id"])

    booking = appointments.book_appointment(
        lead_ctx, counselor_id=chosen["counselor_id"], start_time=datetime.fromisoformat(chosen["start_time"]),
    )
    assert booking.success
    assert booking.data["status"] == "scheduled"


def test_create_application_for_nova_course(db):
    result = bootstrap_nova_demo(db)
    nova_id = result["college"].id
    cse = result["courses"]["BTECH-CSE"]

    ctx = _tool_context(db, nova_id)
    lead_result = leads_tools.create_lead(ctx, course_id=str(cse.id))
    ctx.student_id = uuid.UUID(lead_result.data["student_id"])

    app_result = applications.create_application(ctx, course_id=str(cse.id))
    assert app_result.success
    assert app_result.data["status"] == "draft"
    assert app_result.data["course_name"] == cse.name


# ---------------------------------------------------------------------------
# Full demo workflow through the real orchestrator (production pipeline)
# ---------------------------------------------------------------------------

def test_full_nova_demo_workflow_through_orchestrator(db):
    bootstrap_nova_demo(db)
    nova = _college(db, NOVA_SLUG)
    conv = _new_conversation(db, nova.id)
    orch = _orchestrator(db, nova.id)

    r1 = orch.handle_message(conv, "I want B.Tech CSE.")
    assert "get_course_details" in r1.tools_used

    r2 = orch.handle_message(conv, "I got 82% in 12th. Am I eligible?")
    assert "check_eligibility" in r2.tools_used
    assert "eligib" in r2.response_text.lower()

    r3 = orch.handle_message(conv, "How much is the fee?")
    assert "get_fee_structure" in r3.tools_used
    assert "185,000" in r3.response_text or "185000" in r3.response_text

    r4 = orch.handle_message(conv, "Is there any scholarship?")
    assert "get_scholarship_information" in r4.tools_used

    r5 = orch.handle_message(conv, "Can I talk to a counselor?")
    assert "check_counselor_availability" in r5.tools_used
    assert r5.state.pending_appointment_slot is not None

    r6 = orch.handle_message(conv, "Yes, please book it.")
    assert "book_appointment" in r6.tools_used
    assert "confirmed" in r6.response_text.lower()

    lead = db.get(Lead, uuid.UUID(r6.state.lead_id))
    assert lead is not None
    assert lead.college_id == nova.id
    assert lead.course_id is not None
    assert lead.lead_score > 0

    r7 = orch.handle_message(conv, "I want to apply.")
    assert "create_application" in r7.tools_used
    assert r7.state.last_application_id is not None

    from app.models.applications import Application
    application = db.get(Application, uuid.UUID(r7.state.last_application_id))
    assert application is not None
    assert application.college_id == nova.id
    assert application.status == "draft"
