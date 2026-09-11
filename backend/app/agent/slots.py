"""Lightweight slot extraction from free-text student messages.

Deliberately simple regex/keyword extraction rather than an LLM call -
these are narrow, well-defined fields (a percentage, an exam name, a
yes/no confirmation) where a rule is faster and fully deterministic.
"""
from __future__ import annotations

import re

_PERCENTAGE_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_EXAM_NAMES = ("jee", "cat", "mat", "cmat", "neet", "gate", "xat", "snap")
_EXAM_SCORE_RE = re.compile(
    r"(?:" + "|".join(_EXAM_NAMES) + r")\D{0,15}(\d{1,3}(?:\.\d+)?)"
    r"|(\d{1,3}(?:\.\d+)?)\D{0,15}(?:" + "|".join(_EXAM_NAMES) + r")",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
_NAME_RE = re.compile(r"\b(?:i am|i'm|my name is|this is)\s+([A-Z][a-zA-Z]{1,30})", re.IGNORECASE)

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "confirmed",
    "please book", "book it", "go ahead", "haan", "ha", "theek hai",
}
_NEGATIVE = {"no", "nope", "not now", "cancel", "nahi", "mat karo"}


def extract_percentage(text: str) -> float | None:
    match = _PERCENTAGE_RE.search(text or "")
    return float(match.group(1)) if match else None


def extract_entrance_exam(text: str) -> str | None:
    lowered = (text or "").lower()
    for exam in _EXAM_NAMES:
        if exam in lowered:
            return exam.upper()
    return None


def extract_entrance_score(text: str) -> float | None:
    match = _EXAM_SCORE_RE.search(text or "")
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return float(value) if value else None


def extract_time_of_day(text: str) -> dict | None:
    match = _TIME_RE.search(text or "")
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return {"hour": hour, "minute": minute}


def extract_name(text: str) -> str | None:
    match = _NAME_RE.search(text or "")
    return match.group(1).strip() if match else None


def _phrase_present(normalized: str, phrase: str) -> bool:
    if " " in phrase or len(phrase) > 5:
        return phrase in normalized
    return re.search(rf"\b{re.escape(phrase)}\b", normalized) is not None


def is_affirmative(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return any(_phrase_present(normalized, p) for p in _AFFIRMATIVE)


def is_negative(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return any(_phrase_present(normalized, p) for p in _NEGATIVE)
