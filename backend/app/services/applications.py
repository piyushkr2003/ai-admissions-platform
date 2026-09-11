"""Draft application creation, submission, documents, and status
(docs/architecture.md section 15, docs/database.md sections 18-19,
docs/api-contract.md sections 29-31/74, docs/tasks/009 - application
assistance & management).

The AI may create a DRAFT application once a course and student are
known; submission is a distinct, explicit backend action guarded by real
validation - the agent (and this service) must never describe a draft as
submitted, and must never report a document as verified unless a member
of staff actually verified it.

A successful submission best-effort-enriches an *existing* active lead
(never creates one) via app.services.lead_signals, mirroring the
integration pattern used by AppointmentService.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.academics import Course, CourseEligibilityRule, RequiredDocument
from app.models.applications import Application, ApplicationDocument
from app.models.student import Student
from app.services.audit import record_audit
from app.services.lead_signals import notify_lead

logger = logging.getLogger("app.applications")

TERMINAL_APPLICATION_STATUSES = ("approved", "rejected", "withdrawn")
EDITABLE_STATUSES = ("draft", "in_progress", "documents_pending")
DOCUMENT_STATUSES = ("pending", "uploaded", "verified", "rejected")

# Explicit transition graph rather than a simple rank order - the
# lifecycle is not strictly linear (documents_pending can occur either
# before first submission or after review requests more documents).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_progress", "documents_pending", "submitted", "withdrawn"},
    "in_progress": {"documents_pending", "submitted", "withdrawn"},
    "documents_pending": {"in_progress", "submitted", "under_review", "withdrawn"},
    "submitted": {"under_review", "documents_pending", "withdrawn"},
    "under_review": {"documents_pending", "approved", "rejected", "withdrawn"},
    "approved": set(),
    "rejected": set(),
    "withdrawn": set(),
}


def is_allowed_application_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in ALLOWED_TRANSITIONS.get(current, set())


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_draft(
        self,
        *,
        college_id: uuid.UUID,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        intake: str | None = None,
        idempotency_key: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> tuple[Application, bool]:
        student = self.db.get(Student, student_id)
        if student is None or student.college_id != college_id:
            raise NotFoundError("Student not found for this college.")
        course = self.db.get(Course, course_id)
        if course is None or course.college_id != college_id:
            raise NotFoundError("Course not found for this college.")

        if idempotency_key:
            existing = self.db.execute(
                select(Application).where(
                    Application.college_id == college_id, Application.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing, False

        existing_draft = self.db.execute(
            select(Application).where(
                Application.college_id == college_id,
                Application.student_id == student_id,
                Application.course_id == course_id,
                Application.status.in_(("draft", "in_progress")),
            )
        ).scalar_one_or_none()
        if existing_draft is not None:
            return existing_draft, False

        application = Application(
            college_id=college_id,
            student_id=student_id,
            course_id=course_id,
            intake=intake,
            status="draft",
            completion_percentage=0,
            idempotency_key=idempotency_key,
        )
        self.db.add(application)
        self.db.flush()
        self.recalculate_completion(application)

        logger.info("application.created application_id=%s college_id=%s", application.id, college_id)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="application.created",
            entity_type="application", entity_id=application.id,
        )
        return application, True

    def get_or_404(self, college_id: uuid.UUID, application_id: uuid.UUID) -> Application:
        application = self.db.get(Application, application_id)
        if application is None or application.college_id != college_id:
            raise NotFoundError("Application not found.")
        return application

    def list_applications(
        self,
        college_id: uuid.UUID,
        *,
        status: str | None = None,
        course_id: uuid.UUID | None = None,
        student_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Application], int]:
        conditions = [Application.college_id == college_id]
        if status:
            conditions.append(Application.status == status)
        if course_id:
            conditions.append(Application.course_id == course_id)
        if student_id:
            conditions.append(Application.student_id == student_id)

        total = self.db.execute(select(func.count()).select_from(Application).where(*conditions)).scalar_one()
        stmt = (
            select(Application)
            .where(*conditions)
            .order_by(Application.created_at.desc(), Application.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    # ------------------------------------------------------------------
    # Draft update
    # ------------------------------------------------------------------

    def update_draft(self, application: Application, *, intake: str | None = None, notes: str | None = None) -> Application:
        if application.status not in EDITABLE_STATUSES:
            raise ConflictError(
                "Only a draft/in-progress application can be updated.",
                details={"code": "APPLICATION_NOT_EDITABLE"},
            )
        changed = False
        if intake is not None and intake.strip() and application.intake != intake:
            application.intake = intake
            changed = True
        if notes is not None and notes.strip():
            application.notes = self._append_note(application.notes, notes)
            changed = True
        if changed:
            if application.status == "draft":
                application.status = "in_progress"
            self.db.flush()
            self.recalculate_completion(application)
            logger.info("application.updated application_id=%s", application.id)
        return application

    @staticmethod
    def _append_note(existing: str | None, addition: str) -> str:
        stamp = datetime.now(timezone.utc).isoformat()
        entry = f"[{stamp}] {addition.strip()}"
        return f"{existing}\n{entry}" if existing else entry

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def _required_documents(self, application: Application) -> list[RequiredDocument]:
        stmt = select(RequiredDocument).where(
            RequiredDocument.college_id == application.college_id,
            (RequiredDocument.course_id == application.course_id) | (RequiredDocument.course_id.is_(None)),
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_documents(self, application: Application) -> list[ApplicationDocument]:
        stmt = select(ApplicationDocument).where(ApplicationDocument.application_id == application.id)
        return list(self.db.execute(stmt).scalars().all())

    def checklist(self, application: Application) -> list[dict]:
        """Merge the college's configured required-document list with
        what has actually been registered for this application - the
        source of truth for "missing / uploaded / verified / rejected"
        (docs/api-contract.md section 30)."""
        required = self._required_documents(application)
        uploaded_by_type: dict[str, ApplicationDocument] = {}
        for doc in self.list_documents(application):
            uploaded_by_type[doc.document_type] = doc

        items: list[dict] = []
        seen_types = set()
        for req in required:
            seen_types.add(req.name)
            doc = uploaded_by_type.get(req.name)
            items.append({
                "document_type": req.name,
                "mandatory": req.mandatory,
                "status": doc.status if doc else "missing",
                "document_id": str(doc.id) if doc else None,
            })
        # Documents registered outside the configured checklist (e.g. an
        # optional extra document) are still shown for staff visibility.
        for doc_type, doc in uploaded_by_type.items():
            if doc_type not in seen_types:
                items.append({
                    "document_type": doc_type, "mandatory": False,
                    "status": doc.status, "document_id": str(doc.id),
                })
        return items

    def add_document(
        self, application: Application, *, document_type: str, file_name: str | None = None,
        file_url: str | None = None,
    ) -> ApplicationDocument:
        if application.status in TERMINAL_APPLICATION_STATUSES:
            raise ConflictError("Cannot add documents to a finalized application.")
        document = ApplicationDocument(
            college_id=application.college_id, application_id=application.id,
            document_type=document_type, file_name=file_name, file_url=file_url, status="uploaded",
        )
        self.db.add(document)
        self.db.flush()
        self.recalculate_completion(application)
        logger.info("application.document_added application_id=%s document_type=%s", application.id, document_type)
        return document

    def get_document_or_404(self, application: Application, document_id: uuid.UUID) -> ApplicationDocument:
        document = self.db.get(ApplicationDocument, document_id)
        if document is None or document.application_id != application.id:
            raise NotFoundError("Document not found for this application.")
        return document

    def update_document_status(
        self, application: Application, document: ApplicationDocument, *, status: str, actor_user_id: uuid.UUID | None = None,
    ) -> ApplicationDocument:
        """Staff-only verification action. The system must never report a
        document as verified unless this was actually called."""
        if status not in DOCUMENT_STATUSES:
            raise ValidationAppError(f"Unknown document status: {status}")
        document.status = status
        document.verified_at = datetime.now(timezone.utc) if status == "verified" else None
        self.db.flush()
        self.recalculate_completion(application)
        logger.info("application.document_status_changed application_id=%s document_id=%s status=%s", application.id, document.id, status)
        record_audit(
            self.db, college_id=application.college_id, user_id=actor_user_id, action="application.document_status_changed",
            entity_type="application_document", entity_id=document.id, meta={"status": status},
        )
        return document

    def remove_document(self, application: Application, document: ApplicationDocument) -> None:
        if application.status in TERMINAL_APPLICATION_STATUSES:
            raise ConflictError("Cannot remove documents from a finalized application.")
        if document.status == "verified":
            raise ConflictError("A verified document cannot be removed.")
        self.db.delete(document)
        self.db.flush()
        self.recalculate_completion(application)
        logger.info("application.document_removed application_id=%s document_id=%s", application.id, document.id)

    # ------------------------------------------------------------------
    # Completion / readiness
    # ------------------------------------------------------------------

    def missing_information(self, application: Application) -> list[str]:
        missing: list[str] = []
        if not application.intake:
            missing.append("Intended intake/batch")

        student = self.db.get(Student, application.student_id)
        rule = self.db.execute(
            select(CourseEligibilityRule).where(
                CourseEligibilityRule.college_id == application.college_id,
                CourseEligibilityRule.course_id == application.course_id,
            )
        ).scalar_one_or_none()
        if rule is not None and student is not None:
            if rule.minimum_percentage is not None and student.qualification_score is None:
                missing.append("Qualifying examination percentage")
            if rule.entrance_exam_required and student.entrance_exam_score is None:
                missing.append(f"{rule.entrance_exam_name or 'Entrance exam'} score")

        for item in self.checklist(application):
            if item["mandatory"] and item["status"] == "missing":
                missing.append(f"Upload {item['document_type']}")

        return missing

    def recalculate_completion(self, application: Application) -> int:
        """Deterministic, explainable completion score (0-100) - never an
        LLM guess. Weights: course selected (always true once created)
        20, intake specified 20, student qualification info present 20,
        mandatory documents uploaded 40 (split evenly)."""
        score = 20  # a course is always selected once an application exists
        if application.intake:
            score += 20

        student = self.db.get(Student, application.student_id)
        rule = self.db.execute(
            select(CourseEligibilityRule).where(
                CourseEligibilityRule.college_id == application.college_id,
                CourseEligibilityRule.course_id == application.course_id,
            )
        ).scalar_one_or_none()
        needs_qualification_info = bool(rule and (rule.minimum_percentage is not None or rule.entrance_exam_required))
        if not needs_qualification_info:
            score += 20
        elif student is not None:
            has_percentage = rule.minimum_percentage is None or student.qualification_score is not None
            has_entrance = not rule.entrance_exam_required or student.entrance_exam_score is not None
            if has_percentage and has_entrance:
                score += 20
            elif has_percentage or has_entrance:
                score += 10

        mandatory_items = [item for item in self.checklist(application) if item["mandatory"]]
        if mandatory_items:
            satisfied = sum(1 for item in mandatory_items if item["status"] in ("uploaded", "verified"))
            score += round(40 * satisfied / len(mandatory_items))
        else:
            score += 40

        score = max(0, min(100, score))
        if application.completion_percentage != score:
            application.completion_percentage = score
            self.db.flush()
        return score

    def status_report(self, application: Application) -> dict:
        missing = self.missing_information(application)
        next_steps = [f"Provide: {item}" for item in missing]
        if not missing and application.status in EDITABLE_STATUSES:
            next_steps.append("Ready to submit your application.")
        elif application.status == "submitted":
            next_steps = ["Await review from the admissions team."]
        elif application.status == "under_review":
            next_steps = ["No action needed - the admissions team is reviewing your application."]
        elif application.status == "documents_pending":
            next_steps = next_steps or ["Additional documents were requested - check your document checklist."]
        elif application.status in TERMINAL_APPLICATION_STATUSES:
            next_steps = []

        return {
            "application_id": str(application.id),
            "status": application.status,
            "completion_percentage": self.recalculate_completion(application),
            "missing_information": missing,
            "next_steps": next_steps,
            "application_number": application.application_number,
            "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
        }

    def next_steps(self, application: Application) -> list[str]:
        """Backward-compatible convenience wrapper around status_report."""
        return self.status_report(application)["next_steps"]

    # ------------------------------------------------------------------
    # Submission / withdrawal / staff decisions
    # ------------------------------------------------------------------

    def transition_status(self, application: Application, new_status: str, *, actor_user_id: uuid.UUID | None = None) -> Application:
        if new_status not in ALLOWED_TRANSITIONS:
            raise ValidationAppError(f"Unknown application status: {new_status}")
        if not is_allowed_application_transition(application.status, new_status):
            raise ConflictError(
                f"Cannot transition application from '{application.status}' to '{new_status}'.",
                details={"code": "INVALID_STATUS_TRANSITION"},
            )
        previous = application.status
        if previous == new_status:
            return application
        application.status = new_status
        if new_status == "under_review":
            application.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info("application.status_changed application_id=%s from=%s to=%s", application.id, previous, new_status)
        record_audit(
            self.db, college_id=application.college_id, user_id=actor_user_id, action="application.status_changed",
            entity_type="application", entity_id=application.id, meta={"from": previous, "to": new_status},
        )
        return application

    def _generate_application_number(self, application: Application) -> str:
        year = datetime.now(timezone.utc).year
        return f"APP-{year}-{str(application.id)[:8].upper()}"

    def submit(
        self, college_id: uuid.UUID, application_id: uuid.UUID, *,
        actor_user_id: uuid.UUID | None = None, idempotency_key: str | None = None,
    ) -> Application:
        application = self.get_or_404(college_id, application_id)

        if application.status not in EDITABLE_STATUSES:
            # Retrying the exact same submit request is idempotent; a
            # genuinely new attempt against an already-decided application
            # is a conflict, never a silent duplicate submission.
            if idempotency_key and application.idempotency_key == idempotency_key:
                return application
            raise ConflictError(
                "This application has already been submitted or finalized.",
                details={"code": "APPLICATION_ALREADY_SUBMITTED"},
            )

        missing = self.missing_information(application)
        if missing:
            raise ValidationAppError(
                "This application is not ready to submit.",
                details={"code": "APPLICATION_INVALID", "missing_information": missing},
            )

        self.transition_status(application, "submitted", actor_user_id=actor_user_id)
        application.submitted_at = datetime.now(timezone.utc)
        application.application_number = application.application_number or self._generate_application_number(application)
        if idempotency_key:
            application.idempotency_key = idempotency_key
        self.db.flush()

        logger.info("application.submitted application_id=%s application_number=%s", application.id, application.application_number)
        record_audit(
            self.db, college_id=college_id, user_id=actor_user_id, action="application.submitted",
            entity_type="application", entity_id=application.id,
        )
        notify_lead(self.db, college_id, application.student_id, "application_submitted", "Application submitted.")
        return application

    def withdraw(
        self, college_id: uuid.UUID, application_id: uuid.UUID, *,
        reason: str | None = None, actor_user_id: uuid.UUID | None = None,
    ) -> Application:
        application = self.get_or_404(college_id, application_id)
        if application.status == "withdrawn":
            return application
        if not is_allowed_application_transition(application.status, "withdrawn"):
            raise ConflictError("This application can no longer be withdrawn.")
        if reason:
            application.notes = self._append_note(application.notes, f"Withdrawn: {reason}")
        self.transition_status(application, "withdrawn", actor_user_id=actor_user_id)
        return application
