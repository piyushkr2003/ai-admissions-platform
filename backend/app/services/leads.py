"""Lead identity, enrichment, and explainable scoring (docs/database.md
section 17, docs/api-contract.md section 26/27, docs/tasks/007).

Scoring is deterministic and driven by the college's agent_configs.
lead_scoring_config when present, falling back to the documented
platform defaults otherwise - the AI never writes an arbitrary score
directly, and every change is backed by a lead_score_events row. This is
the single canonical scoring implementation: both the REST API and the
AI agent tools call through this module rather than computing scores
themselves.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.academics import Course
from app.models.agent_config import AgentConfig
from app.models.leads import LEAD_INTENTS, LEAD_STATUSES, TERMINAL_LEAD_STATUSES, Lead, LeadScoreEvent
from app.models.student import Student
from app.services.audit import record_audit
from app.services.courses import find_course_by_query

logger = logging.getLogger("app.leads")

# ---------------------------------------------------------------------------
# Scoring policy - the single source of truth for rule points/labels.
# Every rule is named, documented, and bounded (docs/tasks/007 sections
# 9-12). Per-college overrides (docs/database.md section 32,
# agent_configs.lead_scoring_config) may replace the *points* for any of
# these keys plus the cold_max/warm_max thresholds; labels/positivity are
# platform-level and not currently configurable per college.
# ---------------------------------------------------------------------------

SCORING_RULES: dict[str, dict] = {
    # Default rules (docs/database.md section 17, docs/tasks/007 section 9).
    "course_identified": {"points": 20, "label": "Course identified", "positive": True},
    "eligibility_confirmed": {"points": 20, "label": "Eligibility confirmed", "positive": True},
    "fee_discussed": {"points": 10, "label": "Fee information discussed", "positive": True},
    "scholarship_interest": {"points": 10, "label": "Scholarship interest expressed", "positive": True},
    "appointment_requested": {"points": 20, "label": "Counselor appointment requested", "positive": True},
    "application_started": {"points": 30, "label": "Application started", "positive": True},
    # Additional deterministic signals (docs/tasks/007 section 10).
    "appointment_booked": {"points": 20, "label": "Counselor appointment booked", "positive": True},
    "qualification_provided": {"points": 5, "label": "Qualification details provided", "positive": True},
    "entrance_score_provided": {"points": 5, "label": "Entrance exam score provided", "positive": True},
    "documents_requested": {"points": 5, "label": "Required documents requested", "positive": True},
    "application_submitted": {"points": 10, "label": "Application submitted", "positive": True},
    # Negative signals (docs/tasks/007 sections 11-12) - bounded at 0, never decayed automatically.
    "disqualified": {"points": -20, "label": "Lead disqualified", "positive": False},
    "explicitly_not_interested": {"points": -10, "label": "Explicitly no longer interested", "positive": False},
}
DEFAULT_THRESHOLDS = {"cold_max": 39, "warm_max": 69}
MAX_SCORE = 100
MIN_SCORE = 0

# Status transitions (docs/database.md section 16 canonical statuses, plus
# "disqualified" and the pre-existing "qualifying" step from Task 006).
# Terminal statuses accept no further transition. Otherwise a lead may move
# forward to any later stage, or to "lost"/"disqualified" from anywhere.
_STATUS_ORDER = [
    "new", "contacted", "qualifying", "qualified",
    "appointment_booked", "application_started", "converted",
]
_STATUS_RANK = {status: i for i, status in enumerate(_STATUS_ORDER)}


def is_allowed_status_transition(current: str, new: str) -> bool:
    if new not in LEAD_STATUSES:
        return False
    if current == new:
        return True
    if current in TERMINAL_LEAD_STATUSES:
        return False
    if new in ("lost", "disqualified"):
        return True
    if new not in _STATUS_RANK or current not in _STATUS_RANK:
        return False
    return _STATUS_RANK[new] > _STATUS_RANK[current]


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower() or None


def _scoring_config(db: Session, college_id: uuid.UUID) -> dict:
    stmt = select(AgentConfig).where(AgentConfig.college_id == college_id)
    config = db.execute(stmt).scalar_one_or_none()
    merged = {k: v["points"] for k, v in SCORING_RULES.items()}
    merged.update(DEFAULT_THRESHOLDS)
    if config and config.lead_scoring_config:
        merged.update(config.lead_scoring_config)
    return merged


def temperature_for_score(score: int, scoring: dict) -> str:
    if score <= scoring.get("cold_max", DEFAULT_THRESHOLDS["cold_max"]):
        return "cold"
    if score <= scoring.get("warm_max", DEFAULT_THRESHOLDS["warm_max"]):
        return "warm"
    return "hot"


def _intent_for_events(event_types: set[str]) -> str:
    """Deterministic intent classification (docs/tasks/007 section 21) -
    derived only from real recorded events, never guessed by an LLM."""
    if "application_started" in event_types or "application_submitted" in event_types:
        return "ready_to_apply"
    if "appointment_requested" in event_types or "appointment_booked" in event_types:
        return "high_intent"
    if event_types & {"course_identified", "eligibility_confirmed", "scholarship_interest"}:
        return "interested"
    if event_types:
        return "exploring"
    return "informational"


# Fields that live on Student rather than Lead (docs/database.md's leads
# table has no name/phone/email/qualification columns - those belong to
# the student profile the lead references).
_STUDENT_FIELDS = {
    "name": "full_name", "phone": "phone", "email": "email",
    "qualification": "qualification", "qualification_score": "qualification_score",
    "entrance_exam": "entrance_exam", "entrance_exam_score": "entrance_exam_score",
    "budget": "budget_range", "location": "city",
    "parent_name": "parent_name", "parent_phone": "parent_phone",
}
# Fields that live directly on Lead.
_LEAD_FIELDS = {
    "course_id", "intent", "notes", "next_action", "hostel_interest",
    "scholarship_interest", "parent_involvement", "last_contacted_at",
}


def _is_meaningful(value) -> bool:
    """Do not overwrite valid existing data with empty/uncertain values
    (docs/tasks/007 section 18)."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


class LeadService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Student/lead resolution
    # ------------------------------------------------------------------

    def get_or_create_student(self, college_id: uuid.UUID, student_id: uuid.UUID | None) -> Student:
        if student_id is not None:
            student = self.db.get(Student, student_id)
            if student is not None and student.college_id == college_id:
                return student
        student = Student(college_id=college_id, consent_status="unknown")
        self.db.add(student)
        self.db.flush()
        return student

    def find_student_by_contact(
        self, college_id: uuid.UUID, *, phone: str | None = None, email: str | None = None
    ) -> Student | None:
        """Match an existing student by normalized phone/email within one
        college (docs/tasks/007 section 17). Matches strictly on the
        student's own contact fields (not a shared parent phone) to avoid
        accidentally combining two different prospects."""
        norm_phone = normalize_phone(phone)
        norm_email = normalize_email(email)
        if not norm_phone and not norm_email:
            return None

        conditions = []
        if norm_email:
            conditions.append(func.lower(Student.email) == norm_email)
        if norm_phone:
            conditions.append(Student.phone == norm_phone)
        if not conditions:
            return None

        stmt = (
            select(Student)
            .where(Student.college_id == college_id, or_(*conditions))
            .order_by(Student.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_active_lead(self, college_id: uuid.UUID, student_id: uuid.UUID) -> Lead | None:
        """The student's most recent non-terminal lead, if any. A
        converted/lost/disqualified lead is never silently reused for a
        new conversation or admin create/update - a fresh lead is created
        instead (docs/tasks/007 section 17)."""
        stmt = (
            select(Lead)
            .where(Lead.college_id == college_id, Lead.student_id == student_id)
            .where(Lead.status.notin_(TERMINAL_LEAD_STATUSES))
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
        logger.info("lead.created lead_id=%s college_id=%s source=%s", lead.id, college_id, source)
        return lead, True

    def get_lead_or_404(self, college_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
        lead = self.db.get(Lead, lead_id)
        if lead is None or lead.college_id != college_id:
            raise NotFoundError("Lead not found for this college.")
        return lead

    # ------------------------------------------------------------------
    # Create / update (agent + admin API)
    # ------------------------------------------------------------------

    def _resolve_course_id(
        self, college_id: uuid.UUID, course_id: uuid.UUID | None, course_interest: str | None
    ) -> uuid.UUID | None:
        if course_id is None and course_interest:
            matched = find_course_by_query(self.db, college_id, course_interest)
            course_id = matched.id if matched else None
        if course_id is not None:
            course = self.db.get(Course, course_id)
            if course is None or course.college_id != college_id:
                raise ValidationAppError("course_id does not belong to this college.")
        return course_id

    def _apply_fields_and_score(
        self, lead: Lead, student: Student, *, course_id: uuid.UUID | None,
        course_newly_identified: bool, actor_user_id: uuid.UUID | None, created: bool, **fields,
    ) -> Lead:
        student_fields = {k: v for k, v in fields.items() if k in _STUDENT_FIELDS and _is_meaningful(v)}
        if "phone" in student_fields:
            student_fields["phone"] = normalize_phone(student_fields["phone"])
        if "email" in student_fields:
            student_fields["email"] = normalize_email(student_fields["email"])
        lead_fields = {k: v for k, v in fields.items() if k in _LEAD_FIELDS and _is_meaningful(v)}

        for key, value in student_fields.items():
            setattr(student, _STUDENT_FIELDS[key], value)
        for key, value in lead_fields.items():
            setattr(lead, key, value)
        self.db.flush()

        action = "lead.created" if created else "lead.updated"
        logger.info("%s lead_id=%s college_id=%s", action, lead.id, lead.college_id)
        record_audit(
            self.db, college_id=lead.college_id, user_id=actor_user_id, action=action,
            entity_type="lead", entity_id=lead.id,
        )

        # Enrichment events derived from what was actually just provided -
        # deterministic, not agent-guessed (docs/tasks/007 sections 9-10).
        if course_newly_identified:
            self.record_score_event(lead, "course_identified", reason="Course identified.")
        if student_fields.get("qualification_score") is not None or student_fields.get("qualification") is not None:
            self.record_score_event(lead, "qualification_provided", reason="Qualification details provided.")
        if student_fields.get("entrance_exam_score") is not None:
            self.record_score_event(lead, "entrance_score_provided", reason="Entrance exam score provided.")
        if fields.get("scholarship_interest") is True:
            self.record_score_event(lead, "scholarship_interest", reason="Scholarship interest expressed.")

        self.recalculate_score(lead)
        return lead

    def create_lead(
        self,
        college_id: uuid.UUID,
        *,
        student_id: uuid.UUID | None = None,
        source: str = "admin",
        actor_user_id: uuid.UUID | None = None,
        course_id: uuid.UUID | None = None,
        course_interest: str | None = None,
        **fields,
    ) -> tuple[Lead, bool]:
        """Create a lead, or update+return a matched existing active one
        (docs/tasks/007 sections 16-18). Never trusts a client-supplied
        college_id - callers must already have resolved it server-side."""
        student: Student | None = None
        if student_id is not None:
            student = self.db.get(Student, student_id)
            if student is None or student.college_id != college_id:
                raise NotFoundError("Student not found for this college.")
        else:
            student = self.find_student_by_contact(
                college_id, phone=fields.get("phone"), email=fields.get("email")
            )

        if student is None:
            student = Student(college_id=college_id, consent_status="unknown")
            self.db.add(student)
            self.db.flush()

        course_id = self._resolve_course_id(college_id, course_id, course_interest)

        lead = self.get_active_lead(college_id, student.id)
        created = False
        course_newly_identified = False
        if lead is None:
            lead = Lead(
                college_id=college_id, student_id=student.id, course_id=course_id,
                source=source, status="new",
            )
            self.db.add(lead)
            self.db.flush()
            created = True
            course_newly_identified = course_id is not None
        elif course_id is not None and lead.course_id != course_id:
            course_newly_identified = lead.course_id is None
            lead.course_id = course_id

        self._apply_fields_and_score(
            lead, student, course_id=course_id, course_newly_identified=course_newly_identified,
            actor_user_id=actor_user_id, created=created, **fields,
        )
        return lead, created

    def update_lead(
        self, lead: Lead, *, course_id: uuid.UUID | None = None, course_interest: str | None = None,
        status: str | None = None, actor_user_id: uuid.UUID | None = None, **fields,
    ) -> Lead:
        """Update exactly the given lead (docs/api-contract.md PATCH
        /leads/{lead_id}) - unlike create_lead, this never re-resolves a
        different lead via contact-based dedup."""
        college_id = lead.college_id
        student = self.db.get(Student, lead.student_id)
        if student is None:
            raise NotFoundError("The student behind this lead no longer exists.")

        course_id = self._resolve_course_id(college_id, course_id, course_interest)
        course_newly_identified = False
        if course_id is not None and lead.course_id != course_id:
            course_newly_identified = lead.course_id is None
            lead.course_id = course_id

        self._apply_fields_and_score(
            lead, student, course_id=course_id, course_newly_identified=course_newly_identified,
            actor_user_id=actor_user_id, created=False, **fields,
        )
        if status:
            self.transition_status(lead, status, actor_user_id=actor_user_id)
        return lead

    def update_lead_fields(self, lead: Lead, **fields) -> Lead:
        """Backward-compatible partial update used by the agent's
        update_lead tool - Lead-only fields, skips empty/uncertain values."""
        changed = False
        for key, value in fields.items():
            if not _is_meaningful(value):
                continue
            if getattr(lead, key, None) != value:
                setattr(lead, key, value)
                changed = True
        if changed:
            self.db.flush()
            logger.info("lead.updated lead_id=%s college_id=%s", lead.id, lead.college_id)
        return lead

    def transition_status(self, lead: Lead, new_status: str, *, actor_user_id: uuid.UUID | None = None) -> Lead:
        if new_status not in LEAD_STATUSES:
            raise ValidationAppError(f"Unknown lead status: {new_status}")
        if not is_allowed_status_transition(lead.status, new_status):
            raise ConflictError(
                f"Cannot transition lead from '{lead.status}' to '{new_status}'.",
                details={"code": "INVALID_STATUS_TRANSITION"},
            )
        previous = lead.status
        if previous == new_status:
            return lead
        lead.status = new_status
        self.db.flush()
        logger.info("lead.status_changed lead_id=%s from=%s to=%s", lead.id, previous, new_status)
        record_audit(
            self.db, college_id=lead.college_id, user_id=actor_user_id, action="lead.status_changed",
            entity_type="lead", entity_id=lead.id, meta={"from": previous, "to": new_status},
        )
        return lead

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def record_score_event(
        self, lead: Lead, event_type: str, *, reason: str | None = None,
        source: str = "system", idempotency_key: str | None = None, points: int | None = None,
    ) -> LeadScoreEvent | None:
        """Record one scoring event, deduplicated so retries/repeats never
        inflate the score (docs/tasks/007 sections 13/41). Safe against:
          - an explicit idempotency_key seen before for this lead, and
          - the same event_type being recorded again for this lead (the
            default per-signal dedup, since a repeated identical signal
            carries no new information).
        """
        if idempotency_key:
            existing = self.db.execute(
                select(LeadScoreEvent).where(
                    LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            if existing is not None:
                logger.info(
                    "lead.duplicate_event_ignored lead_id=%s event_type=%s reason=idempotency_key",
                    lead.id, event_type,
                )
                return None

        existing_type = self.db.execute(
            select(LeadScoreEvent).where(
                LeadScoreEvent.lead_id == lead.id, LeadScoreEvent.event_type == event_type
            )
        ).scalar_one_or_none()
        if existing_type is not None:
            logger.info(
                "lead.duplicate_event_ignored lead_id=%s event_type=%s reason=already_recorded",
                lead.id, event_type,
            )
            return None

        scoring = _scoring_config(self.db, lead.college_id)
        rule_points = points if points is not None else scoring.get(event_type)
        if rule_points is None:
            return None

        event = LeadScoreEvent(
            college_id=lead.college_id, lead_id=lead.id, event_type=event_type,
            points=rule_points, reason=reason, source=source, idempotency_key=idempotency_key,
        )
        self.db.add(event)
        self.db.flush()
        logger.info("lead.score_event_created lead_id=%s event_type=%s points=%s", lead.id, event_type, rule_points)
        return event

    def add_score_event(self, lead: Lead, event_type: str, points: int, reason: str) -> LeadScoreEvent:
        """Low-level, non-deduplicated insert - kept for callers that have
        already decided a new row is warranted. Prefer record_score_event."""
        event = LeadScoreEvent(
            college_id=lead.college_id, lead_id=lead.id, event_type=event_type, points=points, reason=reason,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def get_score_events(self, lead: Lead) -> list[LeadScoreEvent]:
        stmt = (
            select(LeadScoreEvent)
            .where(LeadScoreEvent.lead_id == lead.id)
            .order_by(LeadScoreEvent.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def recalculate_score(self, lead: Lead) -> dict:
        scoring = _scoring_config(self.db, lead.college_id)
        events = self.get_score_events(lead)
        raw_score = sum(e.points for e in events)
        score = max(MIN_SCORE, min(MAX_SCORE, raw_score))
        temperature = temperature_for_score(score, scoring)
        intent = _intent_for_events({e.event_type for e in events})

        previous_score = lead.lead_score
        previous_temperature = lead.lead_temperature
        lead.lead_score = score
        lead.lead_temperature = temperature
        # Auto-classify intent from real recorded events, but never regress
        # a stronger, previously-derived intent back to a weaker one.
        if lead.intent is None or _intent_rank(intent) >= _intent_rank(lead.intent):
            lead.intent = intent
        self.db.flush()

        if score != previous_score:
            logger.info("lead.score_changed lead_id=%s from=%s to=%s", lead.id, previous_score, score)
        if temperature != previous_temperature:
            logger.info("lead.temperature_changed lead_id=%s from=%s to=%s", lead.id, previous_temperature, temperature)

        return {
            "score": score,
            "temperature": temperature,
            "intent": lead.intent,
            "previous_score": previous_score,
            "reasons": [
                {
                    "event_type": e.event_type,
                    "points": e.points,
                    "label": SCORING_RULES.get(e.event_type, {}).get("label", e.event_type),
                    "reason": e.reason,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ],
        }

    def record_event_and_rescore(
        self, lead: Lead, event_type: str, reason: str, *,
        idempotency_key: str | None = None, source: str = "agent",
    ) -> dict:
        """Record an event only once per lead (idempotent by event_type,
        or by idempotency_key when supplied) and recalculate. Avoids
        inflating the score every time the same signal is observed again
        in conversation (docs/tasks/007 section 13/41)."""
        self.record_score_event(lead, event_type, reason=reason, source=source, idempotency_key=idempotency_key)
        return self.recalculate_score(lead)

    # ------------------------------------------------------------------
    # Listing (admin API)
    # ------------------------------------------------------------------

    _SORT_COLUMNS = {
        "newest": (Lead.created_at, "desc"),
        "recently_active": (Lead.updated_at, "desc"),
        "recently_updated": (Lead.updated_at, "desc"),
        "highest_score": (Lead.lead_score, "desc"),
        "lowest_score": (Lead.lead_score, "asc"),
    }

    def list_leads(
        self,
        college_id: uuid.UUID,
        *,
        status: str | None = None,
        temperature: str | None = None,
        course_id: uuid.UUID | None = None,
        intent: str | None = None,
        source: str | None = None,
        score_min: int | None = None,
        score_max: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        activity_after: datetime | None = None,
        activity_before: datetime | None = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Lead], int]:
        conditions = [Lead.college_id == college_id]
        if status:
            conditions.append(Lead.status == status)
        if temperature:
            conditions.append(Lead.lead_temperature == temperature)
        if course_id:
            conditions.append(Lead.course_id == course_id)
        if intent:
            conditions.append(Lead.intent == intent)
        if source:
            conditions.append(Lead.source == source)
        if score_min is not None:
            conditions.append(Lead.lead_score >= score_min)
        if score_max is not None:
            conditions.append(Lead.lead_score <= score_max)
        if created_after is not None:
            conditions.append(Lead.created_at >= created_after)
        if created_before is not None:
            conditions.append(Lead.created_at <= created_before)
        if activity_after is not None:
            conditions.append(Lead.updated_at >= activity_after)
        if activity_before is not None:
            conditions.append(Lead.updated_at <= activity_before)

        total = self.db.execute(
            select(func.count()).select_from(Lead).where(*conditions)
        ).scalar_one()

        column, direction = self._SORT_COLUMNS.get(sort, self._SORT_COLUMNS["newest"])
        order = column.desc() if direction == "desc" else column.asc()
        # Deterministic pagination: always break ties on id (docs/tasks/007 section 28).
        stmt = (
            select(Lead)
            .where(*conditions)
            .order_by(order, Lead.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total


def _intent_rank(intent: str | None) -> int:
    try:
        return LEAD_INTENTS.index(intent) if intent else -1
    except ValueError:
        return -1
