"""Structured conversation state (docs/tasks/006 section 9-11).

Persisted as JSON on Conversation.state between turns. Fields are all
optional and updated incrementally - not every field is populated in
every conversation, and the agent must not ask for information it
already has recorded here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentState:
    current_intent: str | None = None
    previous_intent: str | None = None

    course_id: str | None = None
    course_name: str | None = None

    qualification: str | None = None
    qualification_percentage: float | None = None
    entrance_exam: str | None = None
    entrance_score: float | None = None

    budget: str | None = None
    location: str | None = None
    hostel_interest: bool | None = None
    scholarship_interest: bool | None = None
    application_interest: bool | None = None
    appointment_interest: bool | None = None

    student_name: str | None = None
    student_id: str | None = None
    lead_id: str | None = None
    lead_status: str | None = None
    lead_score: int | None = None

    pending_question: str | None = None
    language: str = "en"
    summary: str = ""
    turn_count: int = 0

    last_tool_results: dict[str, Any] = field(default_factory=dict)
    pending_appointment_slot: dict[str, Any] | None = None  # {counselor_id, counselor_name, start_time}
    last_application_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgentState":
        if not data:
            return cls()
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def remember_intent(self, intent: str) -> None:
        if intent != self.current_intent:
            self.previous_intent = self.current_intent
        self.current_intent = intent

    def update_summary(self, note: str) -> None:
        """Append a compact fact to the running summary rather than storing
        full transcript history (Task 006 section 11)."""
        if note and note not in self.summary:
            self.summary = f"{self.summary} {note}".strip()
