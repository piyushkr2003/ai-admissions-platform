"""Lead intelligence & scoring API (docs/api-contract.md section 26,
docs/tasks/007 section 24).

Every route resolves its tenant server-side via `resolve_tenant_college_id`
- a client-supplied college_id is never trusted as an authorization
boundary (docs/tasks/007 section 26). RBAC is enforced through the same
`leads:read` / `leads:write` permissions already defined in
app/auth/permissions.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.errors import AppError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.leads.schemas import LeadCreate, LeadUpdate
from app.models.academics import Course
from app.models.leads import Lead
from app.models.student import Student
from app.models.user import User
from app.services.leads import LeadService

router = APIRouter(prefix="/leads", tags=["leads"])


def _lead_out(db: Session, lead: Lead) -> dict:
    student = db.get(Student, lead.student_id)
    course = db.get(Course, lead.course_id) if lead.course_id else None
    return {
        "id": str(lead.id),
        "college_id": str(lead.college_id),
        "student_id": str(lead.student_id),
        "course_id": str(lead.course_id) if lead.course_id else None,
        "course_name": course.name if course else None,
        "status": lead.status,
        "intent": lead.intent,
        "lead_score": lead.lead_score,
        "lead_temperature": lead.lead_temperature,
        "source": lead.source,
        "notes": lead.notes,
        "next_action": lead.next_action,
        "hostel_interest": lead.hostel_interest,
        "scholarship_interest": lead.scholarship_interest,
        "parent_involvement": lead.parent_involvement,
        "last_contacted_at": lead.last_contacted_at.isoformat() if lead.last_contacted_at else None,
        "last_activity_at": lead.updated_at.isoformat(),
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
        "student": None if student is None else {
            "id": str(student.id),
            "name": student.full_name,
            "phone": student.phone,
            "email": student.email,
            "qualification": student.qualification,
            "qualification_score": float(student.qualification_score) if student.qualification_score is not None else None,
            "entrance_exam": student.entrance_exam,
            "entrance_exam_score": float(student.entrance_exam_score) if student.entrance_exam_score is not None else None,
            "budget": student.budget_range,
            "location": student.city,
            "parent_name": student.parent_name,
            "parent_phone": student.parent_phone,
        },
    }


def _score_event_out(event) -> dict:
    return {
        "id": str(event.id),
        "lead_id": str(event.lead_id),
        "event_type": event.event_type,
        "points": event.points,
        "reason": event.reason,
        "source": event.source,
        "created_at": event.created_at.isoformat(),
    }


@router.get("")
def list_leads(
    college_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    temperature: str | None = Query(default=None),
    course_id: uuid.UUID | None = Query(default=None),
    intent: str | None = Query(default=None),
    source: str | None = Query(default=None),
    score_min: int | None = Query(default=None, ge=0, le=100),
    score_max: int | None = Query(default=None, ge=0, le=100),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    activity_after: datetime | None = Query(default=None),
    activity_before: datetime | None = Query(default=None),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = LeadService(db)
    items, total = service.list_leads(
        tenant_id, status=status, temperature=temperature, course_id=course_id, intent=intent,
        source=source, score_min=score_min, score_max=score_max, created_after=created_after,
        created_before=created_before, activity_after=activity_after, activity_before=activity_before,
        sort=sort, page=page, page_size=page_size,
    )
    return collection_envelope([_lead_out(db, lead) for lead in items], page=page, page_size=page_size, total=total)


@router.post("", status_code=201)
def create_lead(
    payload: LeadCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = LeadService(db)
    data = payload.model_dump(exclude={"student_id", "course_id", "course_interest", "source"}, exclude_none=True)
    try:
        lead, _created = service.create_lead(
            tenant_id, student_id=payload.student_id, source=payload.source,
            actor_user_id=user.id, course_id=payload.course_id, course_interest=payload.course_interest,
            **data,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_lead_out(db, lead))


def _get_lead_or_404(db: Session, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
    return LeadService(db).get_lead_or_404(tenant_id, lead_id)


@router.get("/{lead_id}")
def get_lead(
    lead_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    lead = _get_lead_or_404(db, tenant_id, lead_id)
    return envelope(_lead_out(db, lead))


@router.patch("/{lead_id}")
def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    lead = _get_lead_or_404(db, tenant_id, lead_id)
    service = LeadService(db)
    data = payload.model_dump(exclude={"course_id", "course_interest", "status"}, exclude_unset=True, exclude_none=True)
    try:
        service.update_lead(
            lead, course_id=payload.course_id, course_interest=payload.course_interest,
            status=payload.status, actor_user_id=user.id, **data,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_lead_out(db, lead))


@router.post("/{lead_id}/score")
def recalculate_score(
    lead_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    lead = _get_lead_or_404(db, tenant_id, lead_id)
    service = LeadService(db)
    result = service.recalculate_score(lead)
    db.commit()
    return envelope(result)


@router.get("/{lead_id}/score-events")
def list_score_events(
    lead_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("leads:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    lead = _get_lead_or_404(db, tenant_id, lead_id)
    service = LeadService(db)
    events = service.get_score_events(lead)
    return envelope({
        "lead_id": str(lead.id),
        "score": lead.lead_score,
        "temperature": lead.lead_temperature,
        "events": [_score_event_out(e) for e in events],
    })
