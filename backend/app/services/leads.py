"""Lead identity, updates, and explainable scoring (docs/database.md
section 17, docs/api-contract.md section 27).

Scoring is deterministic and driven by the college's agent_configs.
lead_scoring_config when present, falling back to the documented
platform defaults otherwise - the AI never writes an arbitrary score
directly, and every change is backed by a lead_score_events row.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_config import AgentConfig
from app.models.leads import Lead, LeadScoreEvent
from app.models.student import Student

DEFAULT_SCORING = {
    "course_identified": 20,
    "eligibility_confirmed": 20,
    "fee_discussed": 10,
    "scholarship_interest": 10,
    "appointment_requested": 20,
    "application_started": 30,
    "cold_max": 39,
    "warm_max": 69,
}
MAX_SCORE = 100


def _scoring_config(db: Session, college_id: uuid.UUID) -> dict:
    stmt = select(AgentConfig).where(AgentConfig.college_id == college_id)
    config = db.execute(stmt).scalar_one_or_none()
    if config and config.lead_scoring_config:
        merged = dict(DEFAULT_SCORING)
        merged.update(config.lead_scoring_config)
        return merged
    return DEFAULT_SCORING


def temperature_for_score(score: int, scoring: dict) -> str:
    if score <= scoring.get("cold_max", 39):
        return "cold"
    if score <= scoring.get("warm_max", 69):
        return "warm"
    return "hot"


class LeadService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_student(self, college_id: uuid.UUID, student_id: uuid.UUID | None) -> Student:
        if student_id is not None:
            student = self.db.get(Student, student_id)
            if student is not None and student.college_id == college_id:
                return student
        student = Student(college_id=college_id, consent_status="unknown")
        self.db.add(student)
        self.db.flush()
        return student

    def get_active_lead(self, college_id: uuid.UUID, student_id: uuid.UUID) -> Lead | None:
        stmt = (
            select(Lead)
            .where(Lead.college_id == college_id, Lead.student_id == student_id)
            .order_by(Lead.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_or_create_lead(
        self, college_id: uuid.UUID, student_id: uuid.UUID, *, source: str = "voice_agent",
        course_id: uuid.UUID | None = None,
    ) -> tuple[Lead, bool]:
        lead = self.get_active_lead(college_id, student_id)
        if lead is not None:
            if course_id and lead.course_id != course_id:
                lead.course_id = course_id
                self.db.flush()
            return lead, False
        lead = Lead(college_id=college_id, student_id=student_id, course_id=course_id, source=source, status="new")
        self.db.add(lead)
        self.db.flush()
        return lead, True

    def update_lead_fields(self, lead: Lead, **fields) -> Lead:
        changed = False
        for key, value in fields.items():
            if value is None:
                continue
            if getattr(lead, key, None) != value:
                setattr(lead, key, value)
                changed = True
        if changed:
            self.db.flush()
        return lead

    def add_score_event(self, lead: Lead, event_type: str, points: int, reason: str) -> LeadScoreEvent:
        event = LeadScoreEvent(
            college_id=lead.college_id, lead_id=lead.id, event_type=event_type, points=points, reason=reason,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def recalculate_score(self, lead: Lead) -> dict:
        scoring = _scoring_config(self.db, lead.college_id)
        stmt = select(LeadScoreEvent).where(LeadScoreEvent.lead_id == lead.id)
        events = list(self.db.execute(stmt).scalars().all())
        raw_score = sum(e.points for e in events)
        score = max(0, min(MAX_SCORE, raw_score))
        temperature = temperature_for_score(score, scoring)

        lead.lead_score = score
        lead.lead_temperature = temperature
        self.db.flush()

        return {
            "score": score,
            "temperature": temperature,
            "reasons": [{"event": e.event_type, "points": e.points} for e in events],
        }

    def record_event_and_rescore(self, lead: Lead, event_type: str, reason: str) -> dict:
        """Record an event only once per lead (idempotent by event_type) and
        recalculate. Avoids inflating the score every time the same signal
        is observed again in conversation (Task 006 section 27)."""
        scoring = _scoring_config(self.db, lead.college_id)
        existing = self.db.execute(
            select(LeadScoreEvent).where(
                LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.event_type == event_type
            )
        ).scalar_one_or_none()
        if existing is None:
            points = scoring.get(event_type, 0)
            if points:
                self.add_score_event(lead, event_type, points, reason)
        return self.recalculate_score(lead)
