"""Shared best-effort lead-scoring notification hook.

Used by AppointmentService and ApplicationService so that a successful
domain action (booking, submission, ...) can enrich an *existing* active
lead without either service owning lead-creation logic or duplicating
this glue code (docs/tasks/007 section 22-23: "provide the clean
integration points needed for ... services to update leads").

Never raises: a lead-scoring hiccup must never roll back or fail a real,
already-persisted domain operation (docs/api-contract.md: "creating an
appointment/application and updating a lead are separate concerns").
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

logger = logging.getLogger("app.lead_signals")


def notify_lead(db: Session, college_id: uuid.UUID, student_id: uuid.UUID, event_type: str, reason: str) -> None:
    try:
        from app.services.leads import LeadService

        lead_service = LeadService(db)
        lead = lead_service.get_active_lead(college_id, student_id)
        if lead is not None:
            lead_service.record_event_and_rescore(lead, event_type, reason, source="domain_service")
    except Exception:  # noqa: BLE001 - deliberately broad: must never break the caller
        logger.warning("lead_notification_failed event_type=%s student_id=%s", event_type, student_id, exc_info=True)
