"""Production analytics aggregation (Task 013).

Every metric here is computed with SQL aggregation (COUNT/GROUP BY/AVG)
against the existing transactional tables - nothing is fabricated, and
no table is loaded into Python just to count rows. Every query is
filtered by `college_id` first, so cross-tenant totals can never leak
(docs/database.md section 45, docs/api-contract.md section 64).

Metric provenance is always labeled:
  - "directly_measured": a real COUNT/AVG/breakdown of persisted rows.
  - "derived": computed from more than one directly-measured quantity
    using a documented, explainable formula (e.g. a rate).
  - "unavailable": intentionally not computed because the current data
    model cannot support a trustworthy answer - never guessed.

Date-range filtering uses each table's `created_at` (the one timestamp
guaranteed to be present, timezone-aware, and populated at row-creation
time on every relevant table) so that the same range semantics apply
uniformly everywhere; a handful of derived timing metrics (conversation
duration, ticket resolution time) additionally require a specific
event timestamp to be non-null and say so explicitly.

"Conversion" metrics join leads to appointments/applications through
the one relationship that actually exists in the schema - the shared,
non-nullable `student_id` foreign key - not a fabricated `lead_id` link
on those tables. This is a student-level conversion signal ("did this
lead's student go on to book an appointment / start an application,
at any point"), not a claim about which specific lead caused it, and
is documented as such wherever it is reported.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.dates import ResolvedRange, local_day_sequence
from app.core.errors import NotFoundError
from app.models.academics import Course
from app.models.applications import Application
from app.models.college import College
from app.models.conversations import Conversation, Message
from app.models.counseling import Appointment, Counselor
from app.models.knowledge import UnansweredQuestion
from app.models.leads import LEAD_STATUSES, LEAD_TEMPERATURES, Lead
from app.models.support import SupportTicket
from app.models.voice import VOICE_CHANNELS, VOICE_SESSION_STATUSES, VoiceSession

_UNSPECIFIED = "unspecified"


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Tenant/timezone resolution
    # ------------------------------------------------------------------

    def get_college_or_404(self, college_id: uuid.UUID) -> College:
        college = self.db.get(College, college_id)
        if college is None:
            raise NotFoundError("College not found.")
        return college

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _grouped_counts(self, model, column, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        rows = self.db.execute(
            select(column, func.count())
            .where(
                model.college_id == college_id,
                model.created_at >= resolved.start_utc,
                model.created_at < resolved.end_utc,
            )
            .group_by(column)
        ).all()
        result: dict = {}
        for value, count in rows:
            key = value if value is not None else _UNSPECIFIED
            result[key] = result.get(key, 0) + count
        return result

    @staticmethod
    def _fill_known(counts: dict, known_values: tuple[str, ...]) -> dict:
        filled = {value: counts.get(value, 0) for value in known_values}
        for key, value in counts.items():
            if key not in filled:
                filled[key] = value
        return filled

    def _daily_series(self, model, college_id: uuid.UUID, resolved: ResolvedRange) -> list[dict]:
        local_day = func.date_trunc("day", func.timezone(resolved.timezone, model.created_at))
        rows = self.db.execute(
            select(local_day, func.count())
            .where(
                model.college_id == college_id,
                model.created_at >= resolved.start_utc,
                model.created_at < resolved.end_utc,
            )
            .group_by(local_day)
        ).all()
        counts = {bucket.date(): count for bucket, count in rows}
        return [
            {"date": day.isoformat(), "count": counts.get(day, 0)}
            for day in local_day_sequence(resolved)
        ]

    def _conversion_rate(
        self, college_id: uuid.UUID, resolved: ResolvedRange, target_model, target_student_column, *, definition: str
    ) -> dict:
        lead_student_ids = [
            row[0]
            for row in self.db.execute(
                select(Lead.student_id.distinct()).where(
                    Lead.college_id == college_id,
                    Lead.created_at >= resolved.start_utc,
                    Lead.created_at < resolved.end_utc,
                )
            ).all()
        ]
        leads_student_count = len(lead_student_ids)
        if leads_student_count == 0:
            return {
                "measurement": "derived",
                "definition": definition,
                "leads_student_count": 0,
                "converted_student_count": 0,
                "rate": None,
            }
        converted_student_count = self.db.execute(
            select(func.count(func.distinct(target_student_column))).where(
                target_model.college_id == college_id,
                target_student_column.in_(lead_student_ids),
            )
        ).scalar_one()
        return {
            "measurement": "derived",
            "definition": definition,
            "leads_student_count": leads_student_count,
            "converted_student_count": converted_student_count,
            "rate": converted_student_count / leads_student_count,
        }

    # ------------------------------------------------------------------
    # Domain sections
    # ------------------------------------------------------------------

    def _conversations_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        status_counts = self._grouped_counts(Conversation, Conversation.status, college_id, resolved)
        channel_counts = self._grouped_counts(Conversation, Conversation.channel, college_id, resolved)
        language_counts = self._grouped_counts(Conversation, Conversation.language, college_id, resolved)
        total = sum(status_counts.values())

        avg_seconds, sample_size = self.db.execute(
            select(func.avg(Conversation.duration_seconds), func.count(Conversation.duration_seconds)).where(
                Conversation.college_id == college_id,
                Conversation.created_at >= resolved.start_utc,
                Conversation.created_at < resolved.end_utc,
                Conversation.duration_seconds.isnot(None),
            )
        ).one()

        return {
            "total_conversations": total,
            "by_status": status_counts,
            "by_channel": channel_counts,
            "by_language": language_counts,
            "average_duration_seconds": {
                "measurement": "directly_measured" if sample_size else "unavailable",
                "value": float(avg_seconds) if avg_seconds is not None else None,
                "sample_size": sample_size,
                "note": "Average over conversations that have ended and recorded a duration."
                if sample_size
                else "No conversation in this range has recorded an end duration yet.",
            },
        }

    def _leads_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        raw_status_counts = self._grouped_counts(Lead, Lead.status, college_id, resolved)
        status_counts = self._fill_known(raw_status_counts, LEAD_STATUSES)
        temperature_counts = self._fill_known(
            self._grouped_counts(Lead, Lead.lead_temperature, college_id, resolved), LEAD_TEMPERATURES
        )
        total = sum(raw_status_counts.values())

        by_course_rows = self.db.execute(
            select(Course.name, func.count(Lead.id))
            .select_from(Lead)
            .join(Course, Course.id == Lead.course_id)
            .where(
                Lead.college_id == college_id,
                Lead.created_at >= resolved.start_utc,
                Lead.created_at < resolved.end_utc,
            )
            .group_by(Course.name)
            .order_by(func.count(Lead.id).desc())
        ).all()
        no_course_count = self.db.execute(
            select(func.count()).where(
                Lead.college_id == college_id,
                Lead.created_at >= resolved.start_utc,
                Lead.created_at < resolved.end_utc,
                Lead.course_id.is_(None),
            )
        ).scalar_one()
        by_course = [{"course": name, "count": count} for name, count in by_course_rows]
        if no_course_count:
            by_course.append({"course": "No course specified", "count": no_course_count})

        return {
            "total_leads": total,
            "new_leads": status_counts.get("new", 0),
            "by_status": status_counts,
            "by_temperature": temperature_counts,
            "by_course": by_course,
            "appointment_conversion": self._conversion_rate(
                college_id, resolved, Appointment, Appointment.student_id,
                definition=(
                    "Share of students behind a lead created in this range who have booked at least one "
                    "appointment (at any time). Linked via the shared student_id - leads do not carry a "
                    "direct appointment reference, so this is a student-level signal, not a per-lead one."
                ),
            ),
            "application_conversion": self._conversion_rate(
                college_id, resolved, Application, Application.student_id,
                definition=(
                    "Share of students behind a lead created in this range who have started at least one "
                    "application (at any time). Linked via the shared student_id - leads do not carry a "
                    "direct application reference, so this is a student-level signal, not a per-lead one."
                ),
            ),
        }

    def _appointments_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        status_counts = self._grouped_counts(Appointment, Appointment.status, college_id, resolved)
        total = sum(status_counts.values())

        by_counselor_rows = self.db.execute(
            select(Counselor.name, func.count(Appointment.id))
            .select_from(Appointment)
            .join(Counselor, Counselor.id == Appointment.counselor_id)
            .where(
                Appointment.college_id == college_id,
                Appointment.created_at >= resolved.start_utc,
                Appointment.created_at < resolved.end_utc,
            )
            .group_by(Counselor.name)
            .order_by(func.count(Appointment.id).desc())
        ).all()

        return {
            "total_appointments": total,
            "by_status": status_counts,
            "by_counselor": [{"counselor": name, "count": count} for name, count in by_counselor_rows],
        }

    def _applications_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        status_counts = self._grouped_counts(Application, Application.status, college_id, resolved)
        total = sum(status_counts.values())

        by_course_rows = self.db.execute(
            select(Course.name, func.count(Application.id))
            .select_from(Application)
            .join(Course, Course.id == Application.course_id)
            .where(
                Application.college_id == college_id,
                Application.created_at >= resolved.start_utc,
                Application.created_at < resolved.end_utc,
            )
            .group_by(Course.name)
            .order_by(func.count(Application.id).desc())
        ).all()

        completion_bucket = func.width_bucket(Application.completion_percentage, 1, 101, 4)
        bucket_rows = self.db.execute(
            select(completion_bucket, func.count()).where(
                Application.college_id == college_id,
                Application.created_at >= resolved.start_utc,
                Application.created_at < resolved.end_utc,
            ).group_by(completion_bucket)
        ).all()
        bucket_labels = {0: "0", 1: "1-25", 2: "26-50", 3: "51-75", 4: "76-100"}
        completion_distribution = {label: 0 for label in bucket_labels.values()}
        for bucket_index, count in bucket_rows:
            completion_distribution[bucket_labels.get(bucket_index, "76-100")] = (
                completion_distribution.get(bucket_labels.get(bucket_index, "76-100"), 0) + count
            )

        return {
            "total_applications": total,
            "by_status": status_counts,
            "by_course": [{"course": name, "count": count} for name, count in by_course_rows],
            "completion_percentage_distribution": completion_distribution,
        }

    def _support_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        status_counts = self._grouped_counts(SupportTicket, SupportTicket.status, college_id, resolved)
        category_counts = self._grouped_counts(SupportTicket, SupportTicket.category, college_id, resolved)
        total = sum(status_counts.values())

        avg_seconds, resolved_sample_size = self.db.execute(
            select(
                func.avg(func.extract("epoch", SupportTicket.resolved_at - SupportTicket.created_at)),
                func.count(SupportTicket.resolved_at),
            ).where(
                SupportTicket.college_id == college_id,
                SupportTicket.created_at >= resolved.start_utc,
                SupportTicket.created_at < resolved.end_utc,
                SupportTicket.resolved_at.isnot(None),
            )
        ).one()

        return {
            "total_tickets": total,
            "by_status": status_counts,
            "by_category": category_counts,
            "escalated_tickets": category_counts.get("counselor_escalation", 0),
            "average_resolution_seconds": {
                "measurement": "directly_measured" if resolved_sample_size else "unavailable",
                "value": float(avg_seconds) if avg_seconds is not None else None,
                "sample_size": resolved_sample_size,
                "note": "Average over tickets in this range that have a resolved_at timestamp."
                if resolved_sample_size
                else "No ticket in this range has been resolved yet.",
            },
        }

    def _voice_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        raw_status_counts = self._grouped_counts(VoiceSession, VoiceSession.status, college_id, resolved)
        status_counts = self._fill_known(raw_status_counts, VOICE_SESSION_STATUSES)
        channel_counts = self._fill_known(
            self._grouped_counts(VoiceSession, VoiceSession.channel, college_id, resolved), VOICE_CHANNELS
        )
        language_counts = self._grouped_counts(VoiceSession, VoiceSession.language, college_id, resolved)
        total = sum(raw_status_counts.values())

        avg_seconds, sample_size = self.db.execute(
            select(func.avg(VoiceSession.duration_seconds), func.count(VoiceSession.duration_seconds)).where(
                VoiceSession.college_id == college_id,
                VoiceSession.created_at >= resolved.start_utc,
                VoiceSession.created_at < resolved.end_utc,
                VoiceSession.duration_seconds.isnot(None),
            )
        ).one()

        return {
            "total_sessions": total,
            "by_status": status_counts,
            "by_channel": channel_counts,
            "by_language": language_counts,
            "failed_sessions": status_counts.get("failed", 0),
            "average_duration_seconds": {
                "measurement": "directly_measured" if sample_size else "unavailable",
                "value": float(avg_seconds) if avg_seconds is not None else None,
                "sample_size": sample_size,
                "note": "Average over sessions that have ended and recorded a duration."
                if sample_size
                else "No voice session in this range has recorded an end duration yet.",
            },
        }

    def _ai_operations_section(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        status_counts = self._grouped_counts(Conversation, Conversation.status, college_id, resolved)
        total_conversations = sum(status_counts.values())
        escalated = status_counts.get("escalated", 0)

        tool_call_turns, total_tool_invocations = self.db.execute(
            select(
                func.count().filter(Message.tool_result.isnot(None)),
                func.coalesce(func.sum(func.json_array_length(Message.tool_result["tools_used"])), 0),
            ).where(
                Message.college_id == college_id,
                Message.sender_type == "ai",
                Message.created_at >= resolved.start_utc,
                Message.created_at < resolved.end_utc,
            )
        ).one()

        unanswered_count = self.db.execute(
            select(func.count()).select_from(UnansweredQuestion).where(
                UnansweredQuestion.college_id == college_id,
                UnansweredQuestion.created_at >= resolved.start_utc,
                UnansweredQuestion.created_at < resolved.end_utc,
            )
        ).scalar_one()

        intent_rows = self.db.execute(
            select(Conversation.intent, func.count())
            .where(
                Conversation.college_id == college_id,
                Conversation.created_at >= resolved.start_utc,
                Conversation.created_at < resolved.end_utc,
                Conversation.intent.isnot(None),
            )
            .group_by(Conversation.intent)
            .order_by(func.count().desc())
        ).all()

        return {
            "escalations": {
                "measurement": "directly_measured",
                "definition": "Conversations whose current status is 'escalated'.",
                "escalated_conversations": escalated,
                "total_conversations": total_conversations,
                "escalation_rate": (escalated / total_conversations) if total_conversations else None,
            },
            "tool_usage": {
                "measurement": "directly_measured",
                "definition": (
                    "Counts derived from the tools_used list recorded on each AI response message "
                    "(app.agent.orchestrator._finish)."
                ),
                "ai_turns_with_tool_calls": tool_call_turns,
                "total_tool_invocations": int(total_tool_invocations),
            },
            "unanswered_questions": {
                "measurement": "directly_measured",
                "definition": (
                    "Knowledge-base queries the RAG retrieval service found no reliable evidence for "
                    "(app.rag.retrieval.service, unanswered_questions table)."
                ),
                "count": unanswered_count,
            },
            "query_categories": {
                "measurement": "directly_measured",
                "definition": (
                    "Breakdown by each conversation's most recently detected intent. This reflects the "
                    "last intent recorded on the conversation, not a full per-turn intent history."
                ),
                "breakdown": [{"intent": intent, "count": count} for intent, count in intent_rows],
            },
            "ai_resolution_rate": {
                "measurement": "unavailable",
                "reason": (
                    "The data model has no persisted resolution/satisfaction signal independent of "
                    "escalation or ticket creation. Treating a non-escalated 'completed' conversation as "
                    "'resolved by AI' would not be a trustworthy inference, so this metric is intentionally "
                    "not reported rather than approximated."
                ),
            },
        }

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def build_overview(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        self.get_college_or_404(college_id)
        return {
            "range": resolved.as_meta(),
            "conversations": self._conversations_section(college_id, resolved),
            "leads": self._leads_section(college_id, resolved),
            "appointments": self._appointments_section(college_id, resolved),
            "applications": self._applications_section(college_id, resolved),
            "support": self._support_section(college_id, resolved),
            "voice": self._voice_section(college_id, resolved),
            "ai_operations": self._ai_operations_section(college_id, resolved),
        }

    def build_trends(self, college_id: uuid.UUID, resolved: ResolvedRange) -> dict:
        self.get_college_or_404(college_id)
        return {
            "range": resolved.as_meta(),
            "conversations_per_day": self._daily_series(Conversation, college_id, resolved),
            "leads_per_day": self._daily_series(Lead, college_id, resolved),
            "appointments_per_day": self._daily_series(Appointment, college_id, resolved),
            "applications_per_day": self._daily_series(Application, college_id, resolved),
            "support_tickets_per_day": self._daily_series(SupportTicket, college_id, resolved),
            "voice_sessions_per_day": self._daily_series(VoiceSession, college_id, resolved),
        }
