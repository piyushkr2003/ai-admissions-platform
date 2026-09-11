"""The AI Admissions Agent orchestrator (docs/tasks/006).

Deterministic pipeline: understand -> identify intent -> use
authoritative data (structured tools first, RAG second) -> maintain
context -> update admission state -> take real actions -> confirm only
verified results -> escalate when necessary. There is no LLM in this
decision loop (see app/agent/providers/base.py for why and how one
could be added later).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.agent import guardrails, intents as I, prompts, slots as S
from app.agent.language import detect_language
from app.agent.schemas import ToolCallRecord, ToolResult
from app.agent.state import AgentState
from app.agent.tools import admissions, applications, appointments, courses, eligibility
from app.agent.tools import escalation, fees, knowledge, leads, scholarships
from app.agent.tools.base import ToolContext
from app.colleges.context import CollegeContext
from app.core.config import get_settings
from app.models.conversations import Conversation, Message

logger = logging.getLogger("app.agent")

_KNOWLEDGE_INTENTS = (I.HOSTEL, I.FACILITIES, I.PLACEMENTS, I.GENERAL_COLLEGE_INFO)


@dataclass
class AgentTurnResult:
    response_text: str
    intents: list[str]
    tools_used: list[str] = field(default_factory=list)
    escalation_required: bool = False
    state: AgentState | None = None


class _ToolBudgetExceeded(Exception):
    pass


class AgentOrchestrator:
    def __init__(self, db: Session, college: CollegeContext):
        self.db = db
        self.college = college
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle_message(self, conversation: Conversation, user_text: str) -> AgentTurnResult:
        state = AgentState.from_dict(conversation.state)
        state.turn_count += 1
        state.language = detect_language(user_text, fallback=state.language or self.college.default_language)

        self._record_message(conversation, "student", user_text)

        if guardrails.contains_prompt_injection(user_text):
            logger.warning("prompt_injection_attempt conversation_id=%s", conversation.id)
            response = prompts.injection_refusal(state.language)
            return self._finish(conversation, state, response, intents=[], tools_used=[])

        if guardrails.requests_another_tenant(user_text):
            response = prompts.cross_tenant_refusal(state.language)
            return self._finish(conversation, state, response, intents=[], tools_used=[])

        detected = I.detect_intents(user_text)

        ctx = ToolContext(
            db=self.db, college=self.college, conversation_id=conversation.id,
            student_id=uuid.UUID(state.student_id) if state.student_id else None,
        )

        course_match = courses.resolve_course(ctx, course_query=user_text)
        if course_match is not None:
            state.course_id = str(course_match.id)
            state.course_name = course_match.name
            if I.COURSE_INFORMATION not in detected:
                detected = [I.COURSE_INFORMATION] + detected

        if state.pending_appointment_slot and (S.is_affirmative(user_text) or S.is_negative(user_text)):
            if I.APPOINTMENT not in detected:
                detected = [I.APPOINTMENT] + [d for d in detected if d != I.UNKNOWN]

        if detected and detected[0] != I.UNKNOWN:
            state.remember_intent(detected[0])

        self._merge_slots(state, user_text)

        if I.is_out_of_scope(detected):
            response = prompts.out_of_scope(state.language)
            return self._finish(conversation, state, response, intents=detected, tools_used=[])

        tool_calls: list[ToolCallRecord] = []
        response_parts: list[str] = []
        lead_signals: list[tuple[str, str]] = []
        escalation_required = False

        def run_tool(name: str, fn, **kwargs) -> ToolResult:
            if len(tool_calls) >= self.settings.agent_max_tool_calls_per_turn:
                raise _ToolBudgetExceeded()
            result = fn(ctx, **kwargs)
            tool_calls.append(ToolCallRecord(tool_name=name, arguments=kwargs, result=result))
            return result

        try:
            for intent in detected:
                if intent == I.UNKNOWN:
                    continue

                if intent == I.COURSE_INFORMATION:
                    self._handle_course_info(ctx, run_tool, state, response_parts, user_text, lead_signals)

                elif intent == I.ELIGIBILITY:
                    self._handle_eligibility(ctx, run_tool, state, response_parts, lead_signals)

                elif intent == I.FEES:
                    self._handle_fees(ctx, run_tool, state, response_parts, lead_signals)

                elif intent == I.SCHOLARSHIP:
                    self._handle_scholarship(ctx, run_tool, state, response_parts, lead_signals)

                elif intent == I.ADMISSION_PROCESS:
                    self._handle_admission_process(ctx, run_tool, state, response_parts)

                elif intent == I.REQUIRED_DOCUMENTS:
                    self._handle_required_documents(ctx, run_tool, state, response_parts)

                elif intent == I.ADMISSION_DATES:
                    self._handle_admission_dates(ctx, run_tool, state, response_parts)

                elif intent in _KNOWLEDGE_INTENTS and intent != I.GENERAL_COLLEGE_INFO:
                    if intent == I.HOSTEL:
                        state.hostel_interest = True
                    self._handle_knowledge_lookup(ctx, run_tool, state, response_parts, user_text)

                elif intent in (I.COUNSELOR, I.APPOINTMENT):
                    if not self.college.feature_enabled("appointment_booking_enabled"):
                        response_parts.append(prompts.no_verified_info(state.language))
                        continue
                    esc = self._handle_appointment(ctx, run_tool, state, response_parts, user_text, lead_signals)
                    escalation_required = escalation_required or esc

                elif intent == I.APPLICATION:
                    if not self.college.feature_enabled("application_assistance_enabled"):
                        response_parts.append(prompts.no_verified_info(state.language))
                        continue
                    self._handle_application(ctx, run_tool, state, response_parts, lead_signals)

                elif intent == I.APPLICATION_STATUS:
                    self._handle_application_status(ctx, run_tool, state, response_parts)

                elif intent == I.SUPPORT:
                    self._handle_support(ctx, run_tool, state, response_parts, user_text)

                elif intent == I.HUMAN_ESCALATION:
                    self._handle_escalation(ctx, run_tool, state, response_parts, "Student explicitly requested a human counselor.")
                    escalation_required = True

                elif intent == I.GENERAL_COLLEGE_INFO:
                    if not response_parts:
                        response_parts.append(
                            prompts.greeting(state.language, self._agent_name(), self.college.name)
                        )

            if lead_signals:
                self._apply_lead_signals(ctx, run_tool, state, lead_signals)
        except _ToolBudgetExceeded:
            logger.warning("agent_tool_budget_exceeded conversation_id=%s", conversation.id)
            response_parts.append(prompts.no_verified_info(state.language))
            escalation_required = True

        if not response_parts:
            response_parts.append(prompts.unknown_fallback(state.language, self._agent_name()))

        response_text = " ".join(part for part in response_parts if part).strip()

        if escalation_required:
            conversation.status = "escalated"

        return self._finish(
            conversation, state, response_text, intents=detected,
            tools_used=[t.tool_name for t in tool_calls], escalation_required=escalation_required,
        )

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_course_info(self, ctx, run_tool, state, out, user_text, lead_signals):
        result = run_tool(
            "get_course_details", courses.get_course_details,
            course_id=state.course_id, course_query=user_text if not state.course_id else None,
        )
        if result.success:
            data = result.data
            state.course_id = data["course_id"]
            state.course_name = data["name"]
            out.append(prompts.course_info(state.language, data["name"], data["duration_years"], data["degree_type"], data.get("description")))
            lead_signals.append(("course_identified", f"Student asked about {data['name']}."))
        elif not state.course_id:
            out.append("Sure - which course are you interested in?")
            state.pending_question = "course"

    def _handle_eligibility(self, ctx, run_tool, state, out, lead_signals):
        if not state.course_id:
            out.append("Sure. Which course are you interested in?")
            state.pending_question = "course"
            return
        result = run_tool(
            "check_eligibility", eligibility.check_eligibility,
            course_id=state.course_id, percentage=state.qualification_percentage,
            entrance_score=state.entrance_score, qualification=state.qualification,
        )
        if not result.success:
            out.append(prompts.no_verified_info(state.language))
            return
        data = result.data
        if data["status"] == "insufficient_information":
            out.append(prompts.eligibility_missing_info(state.language, data["missing_information"]))
            state.pending_question = "eligibility_info"
        elif data["status"] == "eligible":
            out.append(prompts.eligibility_eligible(state.language, data["course_name"]))
            lead_signals.append(("eligibility_confirmed", "Eligibility confirmed as eligible."))
        else:
            out.append(prompts.eligibility_not_eligible(state.language, data["course_name"], data["reasons"]))

    def _handle_fees(self, ctx, run_tool, state, out, lead_signals):
        if not state.course_id:
            out.append("Sure - which course would you like fee details for?")
            state.pending_question = "course"
            return
        result = run_tool("get_fee_structure", fees.get_fee_structure, course_id=state.course_id)
        if not result.success:
            out.append(prompts.fee_unavailable(state.language))
            return
        data = result.data
        out.append(prompts.fee_info(state.language, data["course_name"], data["tuition_fee"], data["academic_year"], data.get("hostel_fee")))
        lead_signals.append(("fee_discussed", "Fee structure discussed."))

    def _handle_scholarship(self, ctx, run_tool, state, out, lead_signals):
        state.scholarship_interest = True
        result = run_tool(
            "get_scholarship_information", scholarships.get_scholarship_information, course_id=state.course_id
        )
        if not result.success:
            out.append(prompts.scholarship_unavailable(state.language))
            return
        out.append(prompts.scholarship_info(state.language, result.data["scholarships"]))
        lead_signals.append(("scholarship_interest", "Student expressed scholarship interest."))

    def _handle_admission_process(self, ctx, run_tool, state, out):
        if state.course_id:
            result = run_tool("get_admission_requirements", admissions.get_admission_requirements, course_id=state.course_id)
            if result.success:
                out.append(prompts.admission_process(state.language, result.data.get("admission_process")))
                return
        kr = run_tool("search_knowledge", knowledge.search_knowledge, query="admission process")
        if kr.success:
            out.append(guardrails.keep_voice_friendly(kr.data["results"][0]["content"], max_sentences=3))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_required_documents(self, ctx, run_tool, state, out):
        result = run_tool("get_required_documents", admissions.get_required_documents, course_id=state.course_id)
        if result.success:
            out.append(prompts.required_documents(state.language, [d["name"] for d in result.data["documents"]]))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_admission_dates(self, ctx, run_tool, state, out):
        result = run_tool("get_admission_dates", admissions.get_admission_dates, course_id=state.course_id)
        if result.success:
            out.append(prompts.admission_dates(state.language, result.data["dates"]))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_knowledge_lookup(self, ctx, run_tool, state, out, user_text):
        result = run_tool("search_knowledge", knowledge.search_knowledge, query=user_text)
        if result.success:
            top = result.data["results"][0]
            out.append(guardrails.keep_voice_friendly(top["content"], max_sentences=3))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_appointment(self, ctx, run_tool, state, out, user_text, lead_signals) -> bool:
        self._ensure_lead(ctx, run_tool, state)
        time_hint = S.extract_time_of_day(user_text)
        wants_booking = I.APPOINTMENT in I.detect_intents(user_text) or S.is_affirmative(user_text)

        if state.pending_appointment_slot and wants_booking and not S.is_negative(user_text):
            slot = state.pending_appointment_slot
            result = run_tool(
                "book_appointment", appointments.book_appointment,
                counselor_id=slot["counselor_id"], start_time=datetime.fromisoformat(slot["start_time"]),
                course_id=state.course_id,
            )
            if result.success:
                out.append(prompts.appointment_confirmed(state.language, slot["counselor_name"], self._friendly_time(slot["start_time"])))
                state.pending_appointment_slot = None
                lead_signals.append(("appointment_booked", "Appointment booked."))
                return False
            out.append(prompts.appointment_failed(state.language))
            state.pending_appointment_slot = None
            # fall through to offer fresh availability

        preferred_date = None
        if "tomorrow" in user_text.lower():
            preferred_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()

        time_range = None
        if time_hint:
            t = time(hour=time_hint["hour"], minute=time_hint["minute"])
            time_range = (t, (datetime.combine(date.today(), t) + timedelta(minutes=29)).time())

        result = run_tool(
            "check_counselor_availability", appointments.check_counselor_availability,
            preferred_date=preferred_date, time_range=time_range,
        )
        slots = result.data["slots"] if result.success else []

        if time_hint and slots:
            chosen = slots[0]
            book_result = run_tool(
                "book_appointment", appointments.book_appointment,
                counselor_id=chosen["counselor_id"], start_time=datetime.fromisoformat(chosen["start_time"]),
                course_id=state.course_id,
            )
            if book_result.success:
                out.append(prompts.appointment_confirmed(state.language, chosen["counselor_name"], self._friendly_time(chosen["start_time"])))
                lead_signals.append(("appointment_requested", "Student requested a counselor appointment."))
                lead_signals.append(("appointment_booked", "Appointment booked."))
                return False
            out.append(prompts.appointment_failed(state.language))
            lead_signals.append(("appointment_requested", "Student requested a counselor appointment."))
            return True

        out.append(prompts.counselor_slots(state.language, slots))
        if slots:
            state.pending_appointment_slot = {
                "counselor_id": slots[0]["counselor_id"],
                "counselor_name": slots[0]["counselor_name"],
                "start_time": slots[0]["start_time"],
            }
        lead_signals.append(("appointment_requested", "Student requested a counselor appointment."))
        return not slots

    def _handle_application(self, ctx, run_tool, state, out, lead_signals):
        self._ensure_lead(ctx, run_tool, state)
        if not state.course_id:
            out.append("Sure - which course would you like to apply for?")
            state.pending_question = "course"
            return
        result = run_tool(
            "create_application", applications.create_application, course_id=state.course_id,
        )
        if result.success:
            state.last_application_id = result.data["application_id"]
            out.append(prompts.application_draft_created(state.language, result.data["course_name"]))
            lead_signals.append(("application_started", "Application draft created."))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_application_status(self, ctx, run_tool, state, out):
        if not state.last_application_id:
            out.append("Could you share your application ID so I can check its status?")
            state.pending_question = "application_id"
            return
        result = run_tool(
            "get_application_status", applications.get_application_status, application_id=state.last_application_id,
        )
        if result.success:
            out.append(prompts.application_status(state.language, result.data["status"], result.data["next_steps"]))
        else:
            out.append(prompts.no_verified_info(state.language))

    def _handle_support(self, ctx, run_tool, state, out, user_text):
        result = run_tool(
            "create_support_ticket", escalation.create_support_ticket,
            subject="Student support request", description=user_text, priority="normal",
        )
        if result.success:
            out.append("I've logged your request with our support team.")

    def _handle_escalation(self, ctx, run_tool, state, out, reason: str):
        result = run_tool("escalate_to_counselor", escalation.escalate_to_counselor, reason=reason)
        if result.success:
            out.append(prompts.escalation_created(state.language))
        else:
            out.append(prompts.no_verified_info(state.language))

    # ------------------------------------------------------------------
    # Lead management
    # ------------------------------------------------------------------

    def _ensure_lead(self, ctx, run_tool, state) -> None:
        """Create the student/lead record early when a tool needs
        ctx.student_id before the end-of-turn lead-signal processing runs
        (e.g. booking an appointment in the same turn it was requested)."""
        if ctx.student_id is not None:
            return
        result = run_tool("create_lead", leads.create_lead, course_id=state.course_id)
        if result.success:
            state.student_id = result.data["student_id"]
            state.lead_id = result.data["lead_id"]
            ctx.student_id = uuid.UUID(state.student_id)

    def _apply_lead_signals(self, ctx, run_tool, state, lead_signals: list[tuple[str, str]]) -> None:
        lead_result = run_tool("create_lead", leads.create_lead, course_id=state.course_id)
        if not lead_result.success:
            return
        state.student_id = lead_result.data["student_id"]
        state.lead_id = lead_result.data["lead_id"]
        ctx.student_id = uuid.UUID(state.student_id)

        status_by_event = {
            "appointment_booked": "appointment_booked",
            "application_started": "application_started",
        }
        for event_type, reason in lead_signals:
            score_result = run_tool(
                "calculate_lead_score", leads.calculate_lead_score,
                lead_id=state.lead_id, event_type=event_type, reason=reason,
            )
            if score_result.success:
                state.lead_score = score_result.data["score"]
            new_status = status_by_event.get(event_type)
            if new_status:
                run_tool("update_lead", leads.update_lead, lead_id=state.lead_id, status=new_status)
                state.lead_status = new_status

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _merge_slots(self, state: AgentState, user_text: str) -> None:
        percentage = S.extract_percentage(user_text)
        if percentage is not None:
            state.qualification_percentage = percentage
        exam = S.extract_entrance_exam(user_text)
        if exam:
            state.entrance_exam = exam
        score = S.extract_entrance_score(user_text)
        if score is not None:
            state.entrance_score = score
        name = S.extract_name(user_text)
        if name:
            state.student_name = name

    def _agent_name(self) -> str:
        return "Admissions Assistant"

    @staticmethod
    def _friendly_time(iso_value: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_value)
        except ValueError:
            return iso_value
        return dt.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ")

    def _record_message(self, conversation: Conversation, sender_type: str, content: str, tool_meta: dict | None = None) -> Message:
        message = Message(
            college_id=self.college.college_id,
            conversation_id=conversation.id,
            sender_type=sender_type,
            content=content,
            tool_name=(tool_meta or {}).get("tool_name"),
            tool_arguments=(tool_meta or {}).get("arguments"),
            tool_result=(tool_meta or {}).get("result"),
        )
        self.db.add(message)
        self.db.flush()
        return message

    def _finish(
        self, conversation: Conversation, state: AgentState, response_text: str, *,
        intents: list[str], tools_used: list[str], escalation_required: bool = False,
    ) -> AgentTurnResult:
        state.update_summary(self._summary_note(intents))
        conversation.state = state.to_dict()
        conversation.intent = state.current_intent
        conversation.summary = state.summary
        if state.student_id and not conversation.student_id:
            conversation.student_id = uuid.UUID(state.student_id)
        tool_meta = {"result": {"tools_used": tools_used}} if tools_used else None
        self._record_message(conversation, "ai", response_text, tool_meta)
        self.db.flush()
        return AgentTurnResult(
            response_text=response_text, intents=intents, tools_used=tools_used,
            escalation_required=escalation_required, state=state,
        )

    def _summary_note(self, intents: list[str]) -> str:
        readable = {
            I.COURSE_INFORMATION: "Discussed a course.",
            I.ELIGIBILITY: "Checked eligibility.",
            I.FEES: "Discussed fees.",
            I.SCHOLARSHIP: "Discussed scholarships.",
            I.APPOINTMENT: "Requested a counselor appointment.",
            I.COUNSELOR: "Requested a counselor.",
            I.APPLICATION: "Started an application.",
            I.HUMAN_ESCALATION: "Requested human escalation.",
        }
        notes = [readable[i] for i in intents if i in readable]
        return " ".join(notes)
