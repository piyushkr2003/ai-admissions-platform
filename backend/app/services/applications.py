"""Draft application creation and status (docs/architecture.md section 15).

The AI may create a DRAFT application once a course and student are
known; submission is a distinct, explicit backend action that this
scope does not implement (see Task 006 non-goals: "complete application
engine"). The agent must never describe a draft as submitted.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.academics import Course
from app.models.applications import Application
from app.models.student import Student


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db

    def create_draft(
        self,
        *,
        college_id: uuid.UUID,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        intake: str | None = None,
        idempotency_key: str | None = None,
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
            completion_percentage=10,
            idempotency_key=idempotency_key,
        )
        self.db.add(application)
        self.db.flush()
        return application, True

    def get_or_404(self, college_id: uuid.UUID, application_id: uuid.UUID) -> Application:
        application = self.db.get(Application, application_id)
        if application is None or application.college_id != college_id:
            raise NotFoundError("Application not found.")
        return application

    def next_steps(self, application: Application) -> list[str]:
        if application.status == "draft":
            return [
                "Complete your personal and academic details.",
                "Upload the required documents.",
                "Submit the application for review.",
            ]
        if application.status == "submitted":
            return ["Await review from the admissions team."]
        if application.status == "under_review":
            return ["No action needed - the admissions team is reviewing your application."]
        return []
