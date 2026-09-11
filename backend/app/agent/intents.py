"""Deterministic, rule-based intent detection (docs/tasks/006 section 12-13).

An LLM is deliberately not used here: intent routing for a fixed,
well-understood set of admissions topics is exactly the case where "a
deterministic rule is safer and sufficient" (Task 006 section 13), and
it keeps the agent fully testable without any external model call.

A single message may match several intents ("CSE ka fees kitna hai aur
scholarship milegi kya?" -> FEES + SCHOLARSHIP); detect_intents returns
all matches in a stable, priority-ordered list.
"""
from __future__ import annotations

import re

GENERAL_COLLEGE_INFO = "GENERAL_COLLEGE_INFO"
COURSE_INFORMATION = "COURSE_INFORMATION"
ELIGIBILITY = "ELIGIBILITY"
FEES = "FEES"
SCHOLARSHIP = "SCHOLARSHIP"
ADMISSION_PROCESS = "ADMISSION_PROCESS"
REQUIRED_DOCUMENTS = "REQUIRED_DOCUMENTS"
ADMISSION_DATES = "ADMISSION_DATES"
HOSTEL = "HOSTEL"
FACILITIES = "FACILITIES"
PLACEMENTS = "PLACEMENTS"
COUNSELOR = "COUNSELOR"
APPOINTMENT = "APPOINTMENT"
LEAD_CAPTURE = "LEAD_CAPTURE"
APPLICATION = "APPLICATION"
APPLICATION_STATUS = "APPLICATION_STATUS"
SUPPORT = "SUPPORT"
HUMAN_ESCALATION = "HUMAN_ESCALATION"
POST_ADMISSION_REQUEST = "POST_ADMISSION_REQUEST"
UNKNOWN = "UNKNOWN"

ALL_INTENTS = (
    GENERAL_COLLEGE_INFO, COURSE_INFORMATION, ELIGIBILITY, FEES, SCHOLARSHIP,
    ADMISSION_PROCESS, REQUIRED_DOCUMENTS, ADMISSION_DATES, HOSTEL, FACILITIES,
    PLACEMENTS, COUNSELOR, APPOINTMENT, LEAD_CAPTURE, APPLICATION,
    APPLICATION_STATUS, SUPPORT, HUMAN_ESCALATION, POST_ADMISSION_REQUEST, UNKNOWN,
)

# Checked in this order; APPLICATION_STATUS/APPOINTMENT must be checked
# before their broader siblings (APPLICATION/COUNSELOR).
_PATTERNS: list[tuple[str, list[str]]] = [
    (POST_ADMISSION_REQUEST, [
        "orientation", "hostel check-in", "hostel check in", "campus map",
        "navigate the campus", "campus navigation", "academic calendar",
        "exam timetable", "exam schedule", "hall ticket", "bus route",
        "bus schedule", "transport schedule", "department contact",
    ]),
    (HUMAN_ESCALATION, [
        "talk to a human", "speak to a human", "real person", "human counselor",
        "human counsellor", "speak to a person", "talk to someone real",
        "customer care", "insaan se baat", "escalate",
    ]),
    (APPLICATION_STATUS, [
        "application status", "status of my application", "check my application",
        "status of application", "application ka status",
    ]),
    (APPLICATION, [
        "want to apply", "start my application", "start application",
        "apply for", "submit application", "apply karna", "apply karni",
    ]),
    (APPOINTMENT, [
        "book appointment", "book a slot", "book an appointment", "schedule a call",
        "schedule an appointment", "book the slot", "confirm the slot",
        "book that slot", "slot book",
    ]),
    (COUNSELOR, [
        "counselor", "counsellor", "talk to someone", "speak with an advisor",
        "speak to an advisor", "call back", "counselor se baat",
    ]),
    (SCHOLARSHIP, [
        "scholarship", "financial aid", "fee waiver", "scholarship milegi",
    ]),
    (FEES, [
        "fee", "fees", "cost of", "tuition", "how much does it cost",
        "kitna hai", "fees kitni",
    ]),
    (ELIGIBILITY, [
        "eligible", "eligibility", "can i get into", "can i apply for",
        "qualify for", "am i eligible", "admission mil sakta",
    ]),
    (REQUIRED_DOCUMENTS, [
        "documents required", "required documents", "which documents",
        "papers needed", "documents needed", "documents kya", "documents",
        "document", "kagaz",
    ]),
    (ADMISSION_DATES, [
        "deadline", "last date", "important dates", "application date",
        "when does admission", "when do applications open", "kab tak",
    ]),
    (ADMISSION_PROCESS, [
        "admission process", "how to apply", "application process",
        "steps to apply", "admission procedure", "process kya hai",
    ]),
    (HOSTEL, [
        "hostel", "accommodation", "dormitory", "pg near", "hostel ka",
    ]),
    (PLACEMENTS, [
        "placement", "placements", "package", "recruiters", "job after",
    ]),
    (FACILITIES, [
        "facilities", "campus facilities", "infrastructure", "labs available",
        "library facilities",
    ]),
    (SUPPORT, [
        "complaint", "not working", "issue with", "problem with my",
        "support ticket",
    ]),
    (GENERAL_COLLEGE_INFO, [
        "tell me about", "about your college", "about the college",
        "hi", "hello", "hey", "good morning", "good afternoon", "namaste",
    ]),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _keyword_present(normalized_text: str, keyword: str) -> bool:
    """Substring match for multi-word phrases (naturally specific), but a
    word-boundary match for single short words - otherwise "hi" would
    match inside "scholarship" and similar false positives."""
    if " " in keyword or len(keyword) > 6:
        return keyword in normalized_text
    return re.search(rf"\b{re.escape(keyword)}\b", normalized_text) is not None


def detect_intents(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return [UNKNOWN]

    matched: list[str] = []
    for intent, keywords in _PATTERNS:
        if any(_keyword_present(normalized, keyword) for keyword in keywords):
            matched.append(intent)

    if not matched:
        return [UNKNOWN]
    return matched


def is_out_of_scope(intents: list[str]) -> bool:
    return POST_ADMISSION_REQUEST in intents


def wants_human(intents: list[str]) -> bool:
    return HUMAN_ESCALATION in intents
