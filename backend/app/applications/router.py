"""Application assistance & management API (docs/api-contract.md
sections 29-31).

Tenant scoping and permission checks follow the same pattern as every
other feature router - `resolve_tenant_college_id` derives the tenant
from trusted auth context, and `applications:read`/`applications:write`
(already defined in app/auth/permissions.py) give platform_admin/
college_admin/admissions_staff full access and `counselor` read-only
access, matching docs/api-contract.md's RBAC table exactly.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.applications.schemas import (
    ApplicationCreate,
    ApplicationDocumentCreate,
    ApplicationDocumentStatusUpdate,
    ApplicationSubmit,
    ApplicationUpdate,
    ApplicationWithdraw,
)
from app.auth.dependencies import require_permission, resolve_tenant_college_id
from app.core.errors import AppError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.models.academics import Course
from app.models.applications import Application, ApplicationDocument
from app.models.student import Student
from app.models.user import User
from app.services.applications import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])


def _application_out(db: Session, application: Application) -> dict:
    student = db.get(Student, application.student_id)
    course = db.get(Course, application.course_id)
    return {
        "id": str(application.id),
        "college_id": str(application.college_id),
        "student_id": str(application.student_id),
        "student_name": student.full_name if student else None,
        "course_id": str(application.course_id),
        "course_name": course.name if course else None,
        "application_number": application.application_number,
        "intake": application.intake,
        "status": application.status,
        "completion_percentage": application.completion_percentage,
        "notes": application.notes,
        "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
        "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
        "created_at": application.created_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
    }


def _document_out(document: ApplicationDocument) -> dict:
    return {
        "id": str(document.id),
        "application_id": str(document.application_id),
        "document_type": document.document_type,
        "file_name": document.file_name,
        "file_url": document.file_url,
        "status": document.status,
        "verified_at": document.verified_at.isoformat() if document.verified_at else None,
        "created_at": document.created_at.isoformat(),
    }


@router.get("")
def list_applications(
    college_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    course_id: uuid.UUID | None = Query(default=None),
    student_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = ApplicationService(db)
    items, total = service.list_applications(
        tenant_id, status=status, course_id=course_id, student_id=student_id, page=page, page_size=page_size,
    )
    return collection_envelope(
        [_application_out(db, a) for a in items], page=page, page_size=page_size, total=total
    )


@router.post("", status_code=201)
def create_application(
    payload: ApplicationCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = ApplicationService(db)
    try:
        application, _created = service.create_draft(
            college_id=tenant_id, student_id=payload.student_id, course_id=payload.course_id,
            intake=payload.intake, idempotency_key=payload.idempotency_key, actor_user_id=user.id,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_application_out(db, application))


def _get_application_or_404(db: Session, tenant_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    return ApplicationService(db).get_or_404(tenant_id, application_id)


@router.get("/{application_id}")
def get_application(
    application_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    return envelope(_application_out(db, application))


@router.get("/{application_id}/status")
def get_application_status(
    application_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    report = service.status_report(application)
    db.commit()
    return envelope(report)


@router.patch("/{application_id}")
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    try:
        if payload.intake is not None or payload.notes is not None:
            service.update_draft(application, intake=payload.intake, notes=payload.notes)
        if payload.status is not None:
            service.transition_status(application, payload.status, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_application_out(db, application))


@router.post("/{application_id}/submit")
def submit_application(
    application_id: uuid.UUID,
    payload: ApplicationSubmit,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = ApplicationService(db)
    try:
        application = service.submit(
            tenant_id, application_id, actor_user_id=user.id, idempotency_key=payload.idempotency_key,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_application_out(db, application))


@router.post("/{application_id}/withdraw")
def withdraw_application(
    application_id: uuid.UUID,
    payload: ApplicationWithdraw,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    service = ApplicationService(db)
    try:
        application = service.withdraw(tenant_id, application_id, reason=payload.reason, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_application_out(db, application))


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/{application_id}/documents")
def list_documents(
    application_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:read")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    return envelope(service.checklist(application))


@router.post("/{application_id}/documents", status_code=201)
def add_document(
    application_id: uuid.UUID,
    payload: ApplicationDocumentCreate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    try:
        document = service.add_document(
            application, document_type=payload.document_type, file_name=payload.file_name, file_url=payload.file_url,
        )
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_document_out(document))


def _get_document_or_404(db: Session, application: Application, document_id: uuid.UUID) -> ApplicationDocument:
    return ApplicationService(db).get_document_or_404(application, document_id)


@router.patch("/{application_id}/documents/{document_id}")
def update_document_status(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: ApplicationDocumentStatusUpdate,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    document = _get_document_or_404(db, application, document_id)
    try:
        service.update_document_status(application, document, status=payload.status, actor_user_id=user.id)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope(_document_out(document))


@router.delete("/{application_id}/documents/{document_id}")
def remove_document(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    college_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("applications:write")),
) -> dict:
    tenant_id = resolve_tenant_college_id(user, college_id)
    application = _get_application_or_404(db, tenant_id, application_id)
    service = ApplicationService(db)
    document = _get_document_or_404(db, application, document_id)
    try:
        service.remove_document(application, document)
    except AppError:
        db.rollback()
        raise
    db.commit()
    return envelope({"success": True})
