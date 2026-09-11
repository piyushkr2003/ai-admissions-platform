"""Deterministic eligibility evaluation against configured college rules
(docs/database.md section 9). The AI explains the result; it never
invents eligibility criteria - everything here comes from
CourseEligibilityRule rows the college configured.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import CourseEligibilityRule


@dataclass
class EligibilityResult:
    status: str  # eligible | not_eligible | insufficient_information
    reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)


class EligibilityService:
    def __init__(self, db: Session):
        self.db = db

    def _get_rule(self, college_id: uuid.UUID, course_id: uuid.UUID) -> CourseEligibilityRule | None:
        stmt = select(CourseEligibilityRule).where(
            CourseEligibilityRule.college_id == college_id, CourseEligibilityRule.course_id == course_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def check(
        self,
        *,
        college_id: uuid.UUID,
        course_id: uuid.UUID,
        percentage: float | None = None,
        entrance_score: float | None = None,
        qualification: str | None = None,
    ) -> EligibilityResult:
        rule = self._get_rule(college_id, course_id)
        if rule is None:
            return EligibilityResult(
                status="insufficient_information",
                reasons=["No eligibility rule is configured for this course yet."],
            )

        missing: list[str] = []
        if rule.minimum_percentage is not None and percentage is None:
            missing.append("qualifying examination percentage")
        if rule.entrance_exam_required and entrance_score is None:
            missing.append(f"{rule.entrance_exam_name or 'entrance exam'} score")

        if missing:
            return EligibilityResult(status="insufficient_information", missing_information=missing)

        reasons: list[str] = []
        eligible = True

        if rule.minimum_percentage is not None and percentage is not None:
            if float(percentage) < float(rule.minimum_percentage):
                eligible = False
                reasons.append(
                    f"A minimum of {rule.minimum_percentage}% is required; {percentage}% was provided."
                )

        if rule.entrance_exam_required and rule.minimum_entrance_score is not None and entrance_score is not None:
            if float(entrance_score) < float(rule.minimum_entrance_score):
                eligible = False
                reasons.append(
                    f"A minimum {rule.entrance_exam_name or 'entrance exam'} score of "
                    f"{rule.minimum_entrance_score} is required; {entrance_score} was provided."
                )

        return EligibilityResult(status="eligible" if eligible else "not_eligible", reasons=reasons)
