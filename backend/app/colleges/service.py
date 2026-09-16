from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.colleges.repository import CollegeRepository
from app.colleges.schemas import (
    CollegeAdminBootstrap,
    CollegeConfigurationUpdate,
    CollegeCreate,
    CollegeIdentityUpdate,
)
from app.colleges.validators import (
    ValidationResult,
    is_allowed_transition,
    is_valid_language,
    is_valid_timezone,
    normalize_slug,
    validate_college_configuration,
)
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.security import hash_password
from app.models.college import College
from app.models.user import User
from app.services.audit import record_audit


class CollegeService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CollegeRepository(db)

    # -- retrieval ---------------------------------------------------

    def get_or_404(self, college_id: uuid.UUID) -> College:
        college = self.repo.get(college_id)
        if college is None:
            raise NotFoundError("College not found.")
        return college

    def list_colleges(self, *, limit: int = 100, offset: int = 0) -> list[College]:
        return self.repo.list(limit=limit, offset=offset)

    def configuration_status(self, college: College) -> dict:
        return {
            "identity": "complete" if college.name and college.email and college.phone else "incomplete",
            "branding": "complete" if college.website_url or college.logo_url else "incomplete",
            "languages": "complete" if college.supported_languages and college.default_language in college.supported_languages else "incomplete",
            "admissions": "complete" if self.repo.has_active_course(college.id) else "incomplete",
            "knowledge": "complete" if self.repo.knowledge_source_count(college.id) > 0 else "incomplete",
            "agent": "complete" if self.repo.has_agent_config(college.id) else "incomplete",
        }

    # -- create / update ----------------------------------------------

    def create_college(self, payload: CollegeCreate, *, actor_user_id: uuid.UUID | None) -> College:
        slug = normalize_slug(payload.slug or payload.name)
        if not slug:
            raise ValidationAppError("A valid slug could not be derived from the college name.")
        if self.repo.get_by_slug(slug) is not None:
            raise ConflictError(f"A college with slug '{slug}' already exists.")

        for code in payload.supported_languages:
            if not is_valid_language(code):
                raise ValidationAppError(f"Unsupported language code: {code}")
        if payload.default_language not in payload.supported_languages:
            raise ValidationAppError("default_language must be one of supported_languages.")
        if not is_valid_timezone(payload.timezone):
            raise ValidationAppError(f"Invalid timezone: {payload.timezone}")

        college = College(
            name=payload.name,
            slug=slug,
            description=payload.description,
            website_url=payload.website_url,
            email=payload.email,
            phone=payload.phone,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            postal_code=payload.postal_code,
            timezone=payload.timezone,
            default_language=payload.default_language,
            supported_languages=payload.supported_languages,
            feature_flags={
                "voice_enabled": False,
                "phone_enabled": False,
                "appointment_booking_enabled": False,
                "application_assistance_enabled": False,
                "knowledge_search_enabled": False,
            },
            status="draft",
        )
        self.repo.add(college)
        record_audit(
            self.db, college_id=college.id, user_id=actor_user_id,
            action="college_created", entity_type="college", entity_id=college.id,
        )
        return college

    def create_initial_admin(
        self, college: College, payload: CollegeAdminBootstrap, *, actor_user_id: uuid.UUID | None
    ) -> User:
        """Provision the first `college_admin` account for `college`.

        Production onboarding bootstrap only - deliberately separate from
        `app/db/seed.py`'s fictional demo fixture. Refuses to run if the
        college already has a college_admin (this is a one-time bootstrap,
        not a general admin-invite mechanism) or if the email is already
        taken (User.email is globally unique).
        """
        normalized_email = payload.email.strip().lower()

        existing_admin = self.db.execute(
            select(User).where(User.college_id == college.id, User.role == "college_admin")
        ).scalar_one_or_none()
        if existing_admin is not None:
            raise ConflictError(f"College '{college.slug}' already has a college_admin.")

        existing_user = self.db.execute(
            select(User).where(User.email == normalized_email)
        ).scalar_one_or_none()
        if existing_user is not None:
            raise ConflictError("A user with this email already exists.")

        try:
            password_hash = hash_password(payload.password)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc

        admin = User(
            college_id=college.id,
            email=normalized_email,
            password_hash=password_hash,
            full_name=payload.full_name,
            role="college_admin",
            is_active=True,
        )
        self.db.add(admin)
        self.db.flush()
        record_audit(
            self.db, college_id=college.id, user_id=actor_user_id,
            action="college_admin_bootstrapped", entity_type="user", entity_id=admin.id,
            meta={"email": normalized_email},
        )
        return admin

    def update_identity(
        self, college: College, payload: CollegeIdentityUpdate, *, actor_user_id: uuid.UUID | None
    ) -> College:
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(college, field, value)
        self.db.flush()
        record_audit(
            self.db, college_id=college.id, user_id=actor_user_id,
            action="college_updated", entity_type="college", entity_id=college.id,
            meta={"fields": list(data.keys())},
        )
        return college

    def update_configuration(
        self, college: College, payload: CollegeConfigurationUpdate, *, actor_user_id: uuid.UUID | None
    ) -> College:
        data = payload.model_dump(exclude_unset=True)

        new_languages = data.get("supported_languages", college.supported_languages)
        new_default = data.get("default_language", college.default_language)
        for code in new_languages or []:
            if not is_valid_language(code):
                raise ValidationAppError(f"Unsupported language code: {code}")
        if new_default not in (new_languages or []):
            raise ValidationAppError("default_language must be one of supported_languages.")

        new_timezone = data.get("timezone", college.timezone)
        if not is_valid_timezone(new_timezone):
            raise ValidationAppError(f"Invalid timezone: {new_timezone}")

        for field, value in data.items():
            setattr(college, field, value)
        self.db.flush()
        record_audit(
            self.db, college_id=college.id, user_id=actor_user_id,
            action="college_configuration_changed", entity_type="college", entity_id=college.id,
            meta={"fields": list(data.keys())},
        )
        return college

    # -- lifecycle ------------------------------------------------------

    def validate_for_publish(self, college: College) -> ValidationResult:
        has_active_course = self.repo.has_active_course(college.id)
        return validate_college_configuration(college, has_active_course=has_active_course)

    def _transition(
        self, college: College, target_status: str, *, action: str, actor_user_id: uuid.UUID | None
    ) -> College:
        if not is_allowed_transition(college.status, target_status):
            raise ConflictError(
                f"Cannot transition college from '{college.status}' to '{target_status}'."
            )
        college.status = target_status
        self.db.flush()
        record_audit(
            self.db, college_id=college.id, user_id=actor_user_id,
            action=action, entity_type="college", entity_id=college.id,
            meta={"new_status": target_status},
        )
        return college

    def publish(self, college: College, *, actor_user_id: uuid.UUID | None) -> College:
        if college.status not in ("draft", "suspended"):
            raise ConflictError(f"Cannot publish a college in status '{college.status}'.")
        result = self.validate_for_publish(college)
        if not result.valid:
            raise ValidationAppError(
                "College configuration is not valid for publishing.",
                details={"errors": result.errors},
            )
        return self._transition(college, "active", action="college_published", actor_user_id=actor_user_id)

    def suspend(self, college: College, *, actor_user_id: uuid.UUID | None) -> College:
        return self._transition(college, "suspended", action="college_suspended", actor_user_id=actor_user_id)

    def archive(self, college: College, *, actor_user_id: uuid.UUID | None) -> College:
        return self._transition(college, "archived", action="college_archived", actor_user_id=actor_user_id)
