from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_college_permission, require_platform_admin
from app.colleges.schemas import CollegeConfigurationUpdate, CollegeCreate, CollegeIdentityUpdate
from app.colleges.service import CollegeService
from app.core.errors import TenantAccessDeniedError
from app.core.responses import collection_envelope, envelope
from app.db.session import get_db
from app.models.college import College
from app.models.user import User

router = APIRouter(prefix="/colleges", tags=["colleges"])


def _college_out(service: CollegeService, college: College) -> dict:
    return {
        "id": str(college.id),
        "name": college.name,
        "slug": college.slug,
        "description": college.description,
        "logo_url": college.logo_url,
        "website_url": college.website_url,
        "email": college.email,
        "phone": college.phone,
        "city": college.city,
        "state": college.state,
        "country": college.country,
        "timezone": college.timezone,
        "default_language": college.default_language,
        "supported_languages": college.supported_languages,
        "feature_flags": college.feature_flags,
        "status": college.status,
        "configuration_status": service.configuration_status(college),
    }


def _require_read_access(college_id: uuid.UUID, user: User) -> None:
    if user.role == "platform_admin":
        return
    if user.college_id is None or user.college_id != college_id:
        raise TenantAccessDeniedError()


@router.get("")
def list_colleges(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    service = CollegeService(db)
    if user.role == "platform_admin":
        colleges = service.list_colleges()
    elif user.college_id is not None:
        college = service.get_or_404(user.college_id)
        colleges = [college]
    else:
        colleges = []
    items = [_college_out(service, c) for c in colleges]
    return collection_envelope(items, page=1, page_size=max(len(items), 1), total=len(items))


@router.post("", status_code=201)
def create_college(
    payload: CollegeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
) -> dict:
    service = CollegeService(db)
    college = service.create_college(payload, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))


@router.get("/{college_id}")
def get_college(
    college_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    _require_read_access(college_id, user)
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    return envelope(_college_out(service, college))


@router.patch("/{college_id}")
def update_college(
    college_id: uuid.UUID,
    payload: CollegeIdentityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_college_permission("college_configuration:write")),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    college = service.update_identity(college, payload, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))


@router.get("/{college_id}/configuration")
def get_configuration(
    college_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    _require_read_access(college_id, user)
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    return envelope(_college_out(service, college))


@router.patch("/{college_id}/configuration")
def update_configuration(
    college_id: uuid.UUID,
    payload: CollegeConfigurationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_college_permission("college_configuration:write")),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    college = service.update_configuration(college, payload, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))


@router.post("/{college_id}/validate")
def validate_college(
    college_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_college_permission("college_configuration:read")),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    result = service.validate_for_publish(college)
    return envelope({"valid": result.valid, "errors": result.errors})


@router.post("/{college_id}/publish")
def publish_college(
    college_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_college_permission("college_configuration:write")),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    college = service.publish(college, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))


@router.post("/{college_id}/suspend")
def suspend_college(
    college_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    college = service.suspend(college, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))


@router.post("/{college_id}/archive")
def archive_college(
    college_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
) -> dict:
    service = CollegeService(db)
    college = service.get_or_404(college_id)
    college = service.archive(college, actor_user_id=user.id)
    db.commit()
    return envelope(_college_out(service, college))
