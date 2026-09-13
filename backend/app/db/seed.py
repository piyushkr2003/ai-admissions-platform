"""Deterministic fictional demo data.

Seeds two tenants:
  - Nova Institute of Technology  (primary demo college)
  - Aurora College of Management  (second tenant, exists solely to prove
    tenant isolation)

All data is fictional. Re-running against a database that already contains
these slugs is a no-op for the college rows (idempotent by slug) but will
currently insert duplicate child rows if called twice in the same database -
callers should seed once per environment/test transaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.academics import AdmissionDate, Course, CourseEligibilityRule, RequiredDocument, Scholarship
from app.models.agent_config import AgentConfig
from app.models.college import College
from app.models.counseling import Counselor, CounselorAvailability
from app.models.leads import Lead
from app.models.student import Student
from app.models.support import FAQ, SupportTicket
from app.models.user import User


def _create_college(db: Session, *, name: str, slug: str) -> College:
    college = College(
        name=name,
        slug=slug,
        description=f"{name} is a fictional demo institution used for development and testing.",
        website_url=f"https://{slug}.example.edu",
        email=f"admissions@{slug}.example.edu",
        phone="+91-9800000000",
        city="Pune",
        state="Maharashtra",
        country="India",
        timezone="Asia/Kolkata",
        default_language="en",
        supported_languages=["en", "hi", "hinglish", "kn"],
        feature_flags={
            "voice_enabled": False,
            "phone_enabled": False,
            "appointment_booking_enabled": True,
            "application_assistance_enabled": True,
            "knowledge_search_enabled": True,
        },
        status="active",
    )
    db.add(college)
    db.flush()
    return college


def _seed_nova(db: Session) -> dict:
    college = _create_college(db, name="Nova Institute of Technology", slug="nova-institute-of-technology")

    admin = User(
        college_id=college.id,
        email="admin@nova-institute-of-technology.example.edu",
        password_hash=hash_password("NovaAdmin#2026"),
        full_name="Priya Sharma",
        role="college_admin",
        is_active=True,
    )
    counselor_user = User(
        college_id=college.id,
        email="counselor@nova-institute-of-technology.example.edu",
        password_hash=hash_password("NovaCounselor#2026"),
        full_name="Arjun Mehta",
        role="counselor",
        is_active=True,
    )
    db.add_all([admin, counselor_user])
    db.flush()

    courses_data = [
        dict(name="B.Tech Computer Science and Engineering", code="BTECH-CSE", degree_type="B.Tech",
             department="Engineering", duration_years=4, total_seats=120, annual_fee=150000,
             application_fee=1000, hostel_fee=90000, fee_academic_year="2026-27",
             eligibility_summary="10+2 with PCM, minimum 60%, JEE score required.",
             admission_process="Apply online, appear for entrance counseling, submit documents, pay fees.",
             placement_summary="Average package for 2025 batch was 7.2 LPA with top recruiters in software and product roles.",
             hostel_available=True),
        dict(name="B.Tech Artificial Intelligence and Machine Learning", code="BTECH-AIML", degree_type="B.Tech",
             department="Engineering", duration_years=4, total_seats=90, annual_fee=160000,
             application_fee=1000, hostel_fee=90000, fee_academic_year="2026-27",
             eligibility_summary="10+2 with PCM, minimum 60%, JEE score required.",
             admission_process="Apply online, appear for entrance counseling, submit documents, pay fees.",
             placement_summary="Growing recruiter interest from AI/ML product companies.",
             hostel_available=True),
        dict(name="Bachelor of Computer Applications", code="BCA", degree_type="BCA",
             department="Computer Applications", duration_years=3, total_seats=60, annual_fee=90000,
             application_fee=800, hostel_fee=80000, fee_academic_year="2026-27",
             eligibility_summary="10+2 in any stream, minimum 50%.",
             admission_process="Apply online, merit-based counseling, submit documents, pay fees.",
             placement_summary="Placed in regional IT services and software support roles.",
             hostel_available=True),
        dict(name="Master of Business Administration", code="MBA", degree_type="MBA",
             department="Management", duration_years=2, total_seats=60, annual_fee=180000,
             application_fee=1500, hostel_fee=95000, fee_academic_year="2026-27",
             eligibility_summary="Bachelor's degree with minimum 50%, CAT/MAT/CMAT score required.",
             admission_process="Apply online, entrance score screening, group discussion, personal interview.",
             placement_summary="Average package for 2025 batch was 8.5 LPA.",
             hostel_available=True),
        dict(name="Master of Computer Applications", code="MCA", degree_type="MCA",
             department="Computer Applications", duration_years=2, total_seats=60, annual_fee=110000,
             application_fee=1000, hostel_fee=85000, fee_academic_year="2026-27",
             eligibility_summary="Bachelor's degree with Mathematics, minimum 50%.",
             admission_process="Apply online, merit-based counseling, submit documents, pay fees.",
             placement_summary="Placed in software development and analytics roles.",
             hostel_available=True),
    ]
    courses: dict[str, Course] = {}
    for data in courses_data:
        course = Course(college_id=college.id, status="active", **data)
        db.add(course)
        db.flush()
        courses[course.code] = course

        db.add(CourseEligibilityRule(
            college_id=college.id,
            course_id=course.id,
            minimum_percentage=60 if course.degree_type == "B.Tech" else 50,
            required_qualification="12th" if course.degree_type == "B.Tech" else (
                "Bachelor's Degree" if course.degree_type in ("MBA", "MCA") else "12th"
            ),
            entrance_exam_required=course.degree_type in ("B.Tech", "MBA"),
            entrance_exam_name="JEE" if course.degree_type == "B.Tech" else ("CAT/MAT/CMAT" if course.degree_type == "MBA" else None),
            minimum_entrance_score=50 if course.degree_type in ("B.Tech", "MBA") else None,
        ))

        db.add(Scholarship(
            college_id=college.id,
            course_id=course.id,
            name=f"{course.code} Merit Scholarship",
            description="Merit-based scholarship for high-scoring admitted students.",
            eligibility_criteria="Minimum 90% in qualifying examination, subject to seat availability.",
            percentage=25,
            application_required=True,
            deadline=datetime(2026, 7, 15, tzinfo=timezone.utc),
            status="active",
        ))

        db.add(AdmissionDate(
            college_id=college.id, course_id=course.id, title="Application Opens",
            date=datetime(2026, 3, 1, tzinfo=timezone.utc), date_type="application_open",
            academic_year="2026-27", status="active",
        ))
        db.add(AdmissionDate(
            college_id=college.id, course_id=course.id, title="Application Deadline",
            date=datetime(2026, 6, 30, tzinfo=timezone.utc), date_type="application_deadline",
            academic_year="2026-27", status="active",
        ))

        for doc_name, mandatory in [
            ("Class 10 marksheet", True),
            ("Class 12 marksheet", True),
            ("Government-issued photo ID", True),
            ("Passport-size photographs", True),
            ("Entrance exam scorecard", course.degree_type in ("B.Tech", "MBA")),
        ]:
            db.add(RequiredDocument(
                college_id=college.id, course_id=course.id, name=doc_name, mandatory=mandatory,
            ))

    counselor = Counselor(
        college_id=college.id,
        user_id=counselor_user.id,
        name="Arjun Mehta",
        email="counselor@nova-institute-of-technology.example.edu",
        phone="+91-9811111111",
        specialization="Engineering Admissions",
        active=True,
    )
    db.add(counselor)
    db.flush()

    for day in range(0, 5):  # Monday-Friday
        db.add(CounselorAvailability(
            college_id=college.id, counselor_id=counselor.id, day_of_week=day,
            start_time=time(10, 0), end_time=time(17, 0), timezone="Asia/Kolkata", active=True,
        ))

    faqs = [
        ("Does Nova Institute provide hostel facilities?",
         "Yes, hostel accommodation is available for most programs; hostel fees are listed alongside each course's fee structure."),
        ("What is the medium of instruction?",
         "All programs are taught in English."),
        ("Is there a transport facility for day scholars?",
         "Limited local transport routes are available; please confirm current routes with the admissions office."),
    ]
    for question, answer in faqs:
        db.add(FAQ(college_id=college.id, question=question, answer=answer, category="general", active=True))

    db.add(AgentConfig(
        college_id=college.id,
        agent_name="Nova Assist",
        personality="friendly_professional",
        default_language="en",
        supported_languages=["en", "hi", "hinglish", "kn"],
        greeting_message="Hi! I'm Nova Assist. I can help with courses, eligibility, fees, scholarships, and booking a counselor appointment.",
        fallback_message="I don't have verified information about that yet. I can connect you with an admissions counselor.",
        escalation_message="Let me connect you with an admissions counselor who can help further.",
        lead_scoring_config={
            "course_identified": 20,
            "eligibility_confirmed": 20,
            "fee_discussed": 10,
            "scholarship_interest": 10,
            "appointment_requested": 20,
            "application_started": 30,
            "cold_max": 39,
            "warm_max": 69,
        },
        voice_phone_number="+91-9800000099",
        voice_settings={
            "web_enabled": True,
            "phone_enabled": True,
            "default_language": "en",
            "fallback_language": "en",
            "voice_id": "nova-assist-default",
            "session_idle_timeout_seconds": 60,
            "max_session_duration_seconds": 1800,
            "recording_enabled": False,
            "transcript_enabled": True,
        },
        active=True,
    ))

    leads = _seed_nova_leads(db, college, courses)
    tickets = _seed_nova_support_tickets(db, college, counselor_user)

    return {"college": college, "courses": courses, "counselor": counselor, "leads": leads, "support_tickets": tickets}


def _seed_nova_leads(db: Session, college: College, courses: dict) -> dict:
    """Three deterministic demo leads covering COLD/WARM/HOT
    (docs/tasks/007 section 45). Fictional data only; safe to rerun once
    per fresh database the way the rest of seed_demo_data is."""
    from app.services.leads import LeadService

    service = LeadService(db)

    cold_student = Student(
        college_id=college.id, full_name="Demo Student 1", email="demo.student1@example.edu",
        phone="9800000001", qualification="12th", consent_status="granted",
    )
    warm_student = Student(
        college_id=college.id, full_name="Demo Student 2", email="demo.student2@example.edu",
        phone="9800000002", qualification="12th", qualification_score=78, consent_status="granted",
    )
    hot_student = Student(
        college_id=college.id, full_name="Demo Student 3", email="demo.student3@example.edu",
        phone="9800000003", qualification="12th", qualification_score=91, scholarship_interest=True,
        consent_status="granted",
    )
    db.add_all([cold_student, warm_student, hot_student])
    db.flush()

    cold_lead = Lead(
        college_id=college.id, student_id=cold_student.id, course_id=courses["BCA"].id,
        source="website", status="new",
    )
    warm_lead = Lead(
        college_id=college.id, student_id=warm_student.id, course_id=courses["BTECH-CSE"].id,
        source="voice_agent", status="contacted",
    )
    hot_lead = Lead(
        college_id=college.id, student_id=hot_student.id, course_id=courses["BTECH-AIML"].id,
        source="voice_agent", status="qualified", scholarship_interest=True,
    )
    db.add_all([cold_lead, warm_lead, hot_lead])
    db.flush()

    service.record_score_event(cold_lead, "course_identified", reason="Asked about BCA.")
    service.recalculate_score(cold_lead)

    service.record_score_event(warm_lead, "course_identified", reason="Interested in B.Tech CSE.")
    service.record_score_event(warm_lead, "eligibility_confirmed", reason="12th percentage confirmed eligible.")
    service.record_score_event(warm_lead, "fee_discussed", reason="Asked about CSE annual fee.")
    service.recalculate_score(warm_lead)

    service.record_score_event(hot_lead, "course_identified", reason="Interested in B.Tech AI & ML.")
    service.record_score_event(hot_lead, "eligibility_confirmed", reason="12th percentage confirmed eligible.")
    service.record_score_event(hot_lead, "scholarship_interest", reason="Asked about merit scholarship.")
    service.record_score_event(hot_lead, "appointment_requested", reason="Requested a counselor appointment.")
    service.recalculate_score(hot_lead)

    return {"cold": cold_lead, "warm": warm_lead, "hot": hot_lead}


def _seed_nova_support_tickets(db: Session, college: College, counselor_user: User) -> dict:
    """Three deterministic demo tickets covering the open/assigned/
    resolved lifecycle (docs/tasks/010). Fictional data only."""
    open_ticket = SupportTicket(
        college_id=college.id,
        category="technical",
        subject="Unable to access fee payment portal",
        description="A prospective student reported the online fee payment portal was not loading.",
        priority="normal",
        status="open",
    )
    escalated_ticket = SupportTicket(
        college_id=college.id,
        assigned_to=counselor_user.id,
        category="counselor_escalation",
        subject="Counselor escalation requested",
        description="Student wants a detailed comparison between B.Tech CSE and AI & ML before deciding.",
        priority="high",
        status="assigned",
    )
    resolved_ticket = SupportTicket(
        college_id=college.id,
        assigned_to=counselor_user.id,
        category="general",
        subject="Question about hostel allocation timing",
        description="Student asked when hostel rooms are allocated relative to admission confirmation.",
        priority="low",
        status="resolved",
        # created_at is explicitly backdated (rather than left at the
        # server_default "now") so resolved_at falls after it - otherwise
        # this demo ticket would appear to resolve before it was created,
        # producing a negative resolution-time metric (Task 013).
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        resolved_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add_all([open_ticket, escalated_ticket, resolved_ticket])
    db.flush()
    return {"open": open_ticket, "escalated": escalated_ticket, "resolved": resolved_ticket}


def _seed_aurora(db: Session) -> dict:
    """Second fictional tenant used purely to prove tenant isolation."""
    college = _create_college(db, name="Aurora College of Management", slug="aurora-college-of-management")

    admin = User(
        college_id=college.id,
        email="admin@aurora-college-of-management.example.edu",
        password_hash=hash_password("AuroraAdmin#2026"),
        full_name="Kavita Rao",
        role="college_admin",
        is_active=True,
    )
    db.add(admin)
    db.flush()

    course = Course(
        college_id=college.id,
        name="Bachelor of Business Administration",
        code="BBA",
        degree_type="BBA",
        department="Management",
        duration_years=3,
        total_seats=60,
        annual_fee=120000,
        application_fee=900,
        hostel_fee=70000,
        fee_academic_year="2026-27",
        eligibility_summary="10+2 in any stream, minimum 50%.",
        admission_process="Apply online, merit-based counseling.",
        hostel_available=True,
        status="active",
    )
    db.add(course)
    db.flush()

    db.add(CourseEligibilityRule(
        college_id=college.id, course_id=course.id, minimum_percentage=50,
        required_qualification="12th", entrance_exam_required=False,
    ))
    db.add(FAQ(
        college_id=college.id,
        question="What is Aurora College's hostel fee?",
        answer="Aurora College's hostel fee is a fictional placeholder used only for tenant-isolation tests.",
        category="general", active=True,
    ))
    db.add(AgentConfig(
        college_id=college.id,
        agent_name="Aurora Assist",
        default_language="en",
        supported_languages=["en"],
        greeting_message="Hi, I'm Aurora Assist.",
        active=True,
    ))

    return {"college": college, "courses": {"BBA": course}}


def seed_demo_data(db: Session) -> dict:
    """Seed both fictional tenants. Returns a dict of created references."""
    nova = _seed_nova(db)
    aurora = _seed_aurora(db)
    db.flush()
    return {"nova": nova, "aurora": aurora}
