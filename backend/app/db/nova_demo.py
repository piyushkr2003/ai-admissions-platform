"""Nova Institute of Technology demo-data bootstrap (fictional data only).

Loads the canonical Nova demo dataset from ``nova_demo_data/`` at the repo
root (``nova_demo_seed.json``, ``nova_demo_knowledge_base.md``,
``nova_faqs.csv``) and maps it onto the *existing* multi-tenant schema and
services - no new tables, no Nova-specific code path in the agent, tools,
or RAG pipeline (docs/development.md sections 44-45, 70).

Nova is one tenant, resolved by slug. This module is safe to run against:
  - an empty database (Nova is created fresh), or
  - a database where ``app.db.seed.seed_demo_data`` already created a
    "Nova Institute of Technology" fixture for the general test suite
    (that college row is enriched/upserted in place, never duplicated -
    every write here is a get-or-create/get-or-update keyed on a natural
    identity: college slug, course code, scholarship name, admission
    date title, document name, counselor email, FAQ question, or
    knowledge source content hash).

Running ``bootstrap_nova_demo`` twice against the same database is a
no-op the second time for every structured row and for knowledge
ingestion (content-hash deduplicated by ``IngestionService``).

Mapping notes / known limitations (see docs/development.md "Nova Demo
Data"):
  - ``courses[].annual_other_fee_inr`` (a second, smaller annual fee on
    top of tuition) has no dedicated column on ``Course`` - it is
    recorded in ``Course.description`` and in the ingested knowledge
    base/FAQ text, both of which the fee-related RAG/tool answers can
    surface, rather than inventing a new fee column.
  - ``hostel`` and ``placements`` in the dataset are college-wide, but
    ``Course.hostel_available``/``hostel_fee``/``placement_summary`` are
    per-course columns (the only existing representation) - the same
    college-wide values are applied to every Nova course.
  - ``availability[]`` gives specific-date sample slots, but
    ``CounselorAvailability`` only models a *recurring* weekly schedule.
    Each sample slot's time-of-day is applied Monday-Friday (matching
    the convention already used for the general demo fixture in
    ``app.db.seed``), not just the single sample date.
  - A scholarship restricted to two courses (Women in Technology) is
    stored as one college-wide row with the restriction spelled out in
    ``eligibility_criteria`` text, since ``Scholarship.course_id`` is a
    single nullable FK, not a many-to-many relationship.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import AdmissionDate, Course, CourseEligibilityRule, RequiredDocument, Scholarship
from app.models.agent_config import AgentConfig
from app.models.college import College
from app.models.counseling import Counselor, CounselorAvailability
from app.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.models.support import FAQ
from app.rag.ingestion.service import IngestionService

NOVA_SLUG = "nova-institute-of-technology"

_DEGREE_META = {
    "BTECH-CSE": ("B.Tech", "Engineering"),
    "BTECH-AIML": ("B.Tech", "Engineering"),
    "BCA": ("BCA", "Computer Applications"),
    "MBA": ("MBA", "Management"),
    "MCA": ("MCA", "Computer Applications"),
}

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _data_dir() -> Path:
    # backend/app/db/nova_demo.py -> parents[3] is the repo root.
    return Path(__file__).resolve().parents[3] / "nova_demo_data"


def load_seed() -> dict:
    path = _data_dir() / "nova_demo_seed.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_knowledge_markdown() -> str:
    path = _data_dir() / "nova_demo_knowledge_base.md"
    return path.read_text(encoding="utf-8")


def load_faq_rows() -> list[tuple[str, str]]:
    path = _data_dir() / "nova_faqs.csv"
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [(row["question"].strip(), row["answer"].strip()) for row in reader if row.get("question")]


def _faqs_as_text(rows: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"Q: {question}\nA: {answer}" for question, answer in rows)


# ---------------------------------------------------------------------------
# College
# ---------------------------------------------------------------------------

def _get_or_create_college(db: Session, data: dict) -> College:
    college = db.execute(select(College).where(College.slug == data["slug"])).scalar_one_or_none()
    location = data["location"]
    if college is None:
        college = College(name=data["name"], slug=data["slug"])
        db.add(college)

    college.name = data["name"]
    college.description = (
        f"{data['name']} is a fictional demo institution used for development, testing, and "
        "product demonstrations. It does not represent any real college."
    )
    college.website_url = f"https://{data['slug']}.example.edu"
    college.email = data["contact"]["email"]
    college.phone = data["contact"]["phone"]
    college.city = location["city"]
    college.state = location["state"]
    college.country = location["country"]
    college.timezone = location["timezone"]
    college.default_language = data["languages"][0] if data["languages"] else "en"
    # "kn" (Kannada) is a platform capability (Local Voice: English/Hindi/
    # Kannada addendum), not a fictional college fact, so it's unioned in
    # here rather than added to nova_demo_data/nova_demo_seed.json.
    college.supported_languages = sorted(set(data["languages"]) | {"kn"})
    college.feature_flags = {
        **(college.feature_flags or {}),
        "voice_enabled": True,
        "phone_enabled": False,
        "appointment_booking_enabled": True,
        "application_assistance_enabled": True,
        "knowledge_search_enabled": True,
        "demo_only": True,
    }
    college.status = "active"
    db.flush()
    return college


# ---------------------------------------------------------------------------
# Courses / eligibility
# ---------------------------------------------------------------------------

def _eligibility_summary(course: dict, level: str) -> str:
    qualification = "10+2/equivalent" if level == "UG" else "a recognized bachelor's degree"
    subjects = course.get("required_subjects") or []
    subject_clause = f" with {' and '.join(subjects)}" if subjects else ""
    return f"{qualification}{subject_clause}, minimum {course['minimum_aggregate_percent']}% aggregate."


def _admission_process(data: dict, course: dict) -> str:
    routes = ", ".join(course.get("routes") or [])
    return (
        f"Admission routes: {routes}. Application fee ₹{data['application_fee_inr']:,}. "
        f"Applications open {data['application_open']}, priority deadline {data['priority_deadline']}, "
        f"final deadline {data['final_deadline']} for academic year {data['academic_year']}."
    )


def _placement_summary(placements: dict) -> str:
    return (
        f"Fictional demo figures: {placements['placement_rate_percent']}% placement rate among eligible "
        f"participating students; average package {placements['average_package_lpa']} LPA; highest package "
        f"{placements['highest_package_lpa']} LPA. Demo data only - not real placement statistics."
    )


def _course_description(data: dict, course: dict) -> str:
    other_fee = course.get("annual_other_fee_inr")
    note = (
        f" Additional annual academic fees of ₹{other_fee:,} apply on top of tuition (fictional demo data)."
        if other_fee
        else ""
    )
    return f"{course['name']} at {data['name']} (fictional demo data).{note}"


def _upsert_courses(db: Session, college: College, data: dict) -> dict[str, Course]:
    hostel = data.get("hostel") or {}
    placement_text = _placement_summary(data["placements"]) if data.get("placements") else None

    courses: dict[str, Course] = {}
    for course in data["courses"]:
        code = course["code"]
        degree_type, department = _DEGREE_META.get(code, (course["level"], "General"))

        row = db.execute(
            select(Course).where(Course.college_id == college.id, Course.code == code)
        ).scalar_one_or_none()
        if row is None:
            row = Course(college_id=college.id, code=code, name=course["name"])
            db.add(row)

        row.name = course["name"]
        row.degree_type = degree_type
        row.department = department
        row.description = _course_description(data, course)
        row.duration_years = course["duration_years"]
        row.total_seats = course["seats"]
        row.annual_fee = course["annual_tuition_inr"]
        row.application_fee = data["application_fee_inr"]
        row.hostel_fee = hostel.get("annual_fee_inr") if hostel.get("available") else None
        row.fee_academic_year = data["academic_year"]
        row.eligibility_summary = _eligibility_summary(course, course["level"])
        row.admission_process = _admission_process(data, course)
        row.placement_summary = placement_text
        row.hostel_available = bool(hostel.get("available"))
        row.status = "active"
        db.flush()
        courses[code] = row

        rule = db.execute(
            select(CourseEligibilityRule).where(
                CourseEligibilityRule.college_id == college.id, CourseEligibilityRule.course_id == row.id
            )
        ).scalar_one_or_none()
        if rule is None:
            rule = CourseEligibilityRule(college_id=college.id, course_id=row.id)
            db.add(rule)
        rule.minimum_percentage = course["minimum_aggregate_percent"]
        rule.required_qualification = "10+2" if course["level"] == "UG" else "Bachelor's Degree"
        rule.required_subjects = course.get("required_subjects") or []
        rule.entrance_exam_required = False  # every Nova course also admits via a "merit" route
        rule.entrance_exam_name = None
        rule.minimum_entrance_score = None
        rule.additional_conditions = {"routes": course.get("routes") or [], "demo_only": True}
        db.flush()

    return courses


def _upsert_scholarships(db: Session, college: College, data: dict) -> list[Scholarship]:
    results: list[Scholarship] = []
    for scholarship in data["scholarships"]:
        row = db.execute(
            select(Scholarship).where(Scholarship.college_id == college.id, Scholarship.name == scholarship["name"])
        ).scalar_one_or_none()
        if row is None:
            row = Scholarship(college_id=college.id, name=scholarship["name"])
            db.add(row)

        percent_match = _PERCENT_RE.search(scholarship["benefit"])
        row.description = scholarship["benefit"]
        row.eligibility_criteria = scholarship["eligibility"]
        row.percentage = float(percent_match.group(1)) if percent_match else None
        row.amount = None
        row.course_id = None  # dataset restrictions (if any) are spelled out in eligibility_criteria
        row.application_required = True
        row.status = "active"
        db.flush()
        results.append(row)
    return results


def _upsert_admission_dates(db: Session, college: College, data: dict) -> list[AdmissionDate]:
    date_type_by_event = {
        "Applications open": "application_open",
        "Priority application deadline": "priority_deadline",
        "Final application deadline": "final_deadline",
        "NOVA-AT Session 1": "entrance_exam",
        "NOVA-AT Session 2": "entrance_exam",
        "Counselling begins": "counselling",
    }
    results: list[AdmissionDate] = []
    for entry in data["important_dates"]:
        row = db.execute(
            select(AdmissionDate).where(
                AdmissionDate.college_id == college.id,
                AdmissionDate.course_id.is_(None),
                AdmissionDate.title == entry["event"],
            )
        ).scalar_one_or_none()
        if row is None:
            row = AdmissionDate(college_id=college.id, title=entry["event"])
            db.add(row)

        parsed = date.fromisoformat(entry["date"])
        row.date = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
        row.date_type = date_type_by_event.get(entry["event"], "other")
        row.academic_year = data["academic_year"]
        row.status = "active"
        db.flush()
        results.append(row)
    return results


def _upsert_documents(db: Session, college: College, data: dict) -> list[RequiredDocument]:
    results: list[RequiredDocument] = []
    for name in data["documents"]:
        row = db.execute(
            select(RequiredDocument).where(
                RequiredDocument.college_id == college.id,
                RequiredDocument.course_id.is_(None),
                RequiredDocument.name == name,
            )
        ).scalar_one_or_none()
        if row is None:
            row = RequiredDocument(college_id=college.id, name=name)
            db.add(row)
        row.mandatory = "if applicable" not in name.lower() and "where applicable" not in name.lower()
        db.flush()
        results.append(row)
    return results


def _counselor_email(name: str, data: dict) -> str:
    domain = data["contact"]["email"].split("@", 1)[1]
    local = name.lower().replace(" ", ".")
    return f"{local}@{domain}"


def _upsert_counselors(db: Session, college: College, data: dict) -> dict[str, Counselor]:
    results: dict[str, Counselor] = {}
    for entry in data["counselors"]:
        email = _counselor_email(entry["name"], data)
        row = db.execute(
            select(Counselor).where(Counselor.college_id == college.id, Counselor.email == email)
        ).scalar_one_or_none()
        if row is None:
            row = Counselor(college_id=college.id, name=entry["name"], email=email)
            db.add(row)
        row.name = entry["name"]
        languages = ", ".join(entry.get("languages") or [])
        row.specialization = f"{entry['role']} (languages: {languages})" if languages else entry["role"]
        row.active = True
        db.flush()
        results[entry["name"]] = row
    return results


def _upsert_availability(db: Session, college: College, counselors: dict[str, Counselor], data: dict) -> None:
    for entry in data["availability"]:
        counselor = counselors.get(entry["counselor"])
        if counselor is None:
            continue
        start_time = time.fromisoformat(entry["start"])
        end_time = time.fromisoformat(entry["end"])
        for day_of_week in range(0, 5):  # Monday-Friday; see module docstring mapping note
            existing = db.execute(
                select(CounselorAvailability).where(
                    CounselorAvailability.college_id == college.id,
                    CounselorAvailability.counselor_id == counselor.id,
                    CounselorAvailability.day_of_week == day_of_week,
                    CounselorAvailability.start_time == start_time,
                    CounselorAvailability.end_time == end_time,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.active = True
                continue
            db.add(CounselorAvailability(
                college_id=college.id, counselor_id=counselor.id, day_of_week=day_of_week,
                start_time=start_time, end_time=end_time, timezone=data["location"]["timezone"], active=True,
            ))
    db.flush()


def _upsert_faqs(db: Session, college: College, faq_rows: list[tuple[str, str]]) -> list[FAQ]:
    results: list[FAQ] = []
    for question, answer in faq_rows:
        row = db.execute(
            select(FAQ).where(FAQ.college_id == college.id, FAQ.question == question)
        ).scalar_one_or_none()
        if row is None:
            row = FAQ(college_id=college.id, question=question)
            db.add(row)
        row.answer = answer
        row.category = "general"
        row.active = True
        db.flush()
        results.append(row)
    return results


def _ensure_agent_config(db: Session, college: College, data: dict) -> AgentConfig:
    """Create-only: an AgentConfig already present (e.g. from the general
    ``app.db.seed`` fixture) is left untouched so its persona/tests are
    never disturbed by this bootstrap."""
    config = db.execute(select(AgentConfig).where(AgentConfig.college_id == college.id)).scalar_one_or_none()
    if config is not None:
        return config
    config = AgentConfig(
        college_id=college.id,
        agent_name="Nova Assist",
        personality="friendly_professional",
        default_language=data["languages"][0] if data["languages"] else "en",
        supported_languages=sorted(set(data["languages"]) | {"kn"}),
        greeting_message=(
            "Hi! I'm Nova Assist. I can help with courses, eligibility, fees, scholarships, "
            "and booking a counselor appointment for Nova Institute of Technology (a fictional demo college)."
        ),
        fallback_message="I don't have verified information about that yet. I can connect you with an admissions counselor.",
        escalation_message="Let me connect you with an admissions counselor who can help further.",
        active=True,
    )
    db.add(config)
    db.flush()
    return config


def _ingest_knowledge(db: Session, college: College, faq_rows: list[tuple[str, str]]) -> list[KnowledgeSource]:
    service = IngestionService(db)
    sources = [
        service.ingest(
            college_id=college.id, name="Nova Demo Knowledge Base", source_type="manual",
            text=load_knowledge_markdown(),
        ),
        service.ingest(
            college_id=college.id, name="Nova Demo FAQs", source_type="faq",
            text=_faqs_as_text(faq_rows),
        ),
    ]
    return sources


def bootstrap_nova_demo(db: Session) -> dict:
    """Idempotently create/upsert the Nova Institute of Technology demo
    tenant from ``nova_demo_data/`` and ingest its knowledge base/FAQs
    through the existing RAG pipeline. Safe to call repeatedly and safe
    to call whether or not ``app.db.seed.seed_demo_data`` has already
    seeded a Nova fixture in this database."""
    data = load_seed()
    faq_rows = load_faq_rows()

    college = _get_or_create_college(db, data)
    courses = _upsert_courses(db, college, data)
    scholarships = _upsert_scholarships(db, college, data)
    admission_dates = _upsert_admission_dates(db, college, data)
    documents = _upsert_documents(db, college, data)
    counselors = _upsert_counselors(db, college, data)
    _upsert_availability(db, college, counselors, data)
    faqs = _upsert_faqs(db, college, faq_rows)
    agent_config = _ensure_agent_config(db, college, data)
    knowledge_sources = _ingest_knowledge(db, college, faq_rows)

    db.flush()
    return {
        "college": college,
        "courses": courses,
        "scholarships": scholarships,
        "admission_dates": admission_dates,
        "documents": documents,
        "counselors": counselors,
        "faqs": faqs,
        "agent_config": agent_config,
        "knowledge_sources": knowledge_sources,
    }


def reset_nova_demo_knowledge(db: Session) -> None:
    """Delete Nova's ingested knowledge sources/chunks so a subsequent
    ``bootstrap_nova_demo`` call re-ingests the demo dataset from scratch
    (docs/development.md section 70, "Demo Reset"). Never touches leads,
    appointments, applications, or other interaction history - only the
    RAG content this bootstrap owns. Never call against production data.
    """
    college = db.execute(select(College).where(College.slug == NOVA_SLUG)).scalar_one_or_none()
    if college is None:
        return
    source_ids = db.execute(
        select(KnowledgeSource.id).where(KnowledgeSource.college_id == college.id)
    ).scalars().all()
    if not source_ids:
        return
    db.query(KnowledgeChunk).filter(KnowledgeChunk.knowledge_source_id.in_(source_ids)).delete(
        synchronize_session=False
    )
    db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(source_ids)).delete(synchronize_session=False)
    db.flush()
