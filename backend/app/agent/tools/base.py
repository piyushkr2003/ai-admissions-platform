"""Shared tool context (docs/agent-tools.md section 5).

Every tool receives its college_id from this context - which is
constructed once per conversation from the trusted CollegeContext/
conversation record - never from a model-generated argument. A tool
must not accept `college_id` as a caller-supplied parameter.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.colleges.context import CollegeContext


@dataclass
class ToolContext:
    db: Session
    college: CollegeContext
    conversation_id: uuid.UUID
    student_id: uuid.UUID | None = None

    @property
    def college_id(self) -> uuid.UUID:
        return self.college.college_id
