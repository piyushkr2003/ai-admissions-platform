"""College configuration validation.

Centralizes every rule that must hold before a college can be activated,
so route handlers never duplicate this logic (Task 004 section 44).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.college import College

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SUPPORTED_LANGUAGE_CODES = {"en", "hi", "hinglish", "kn"}


def normalize_slug(raw: str) -> str:
    lowered = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug


def is_valid_slug(slug: str) -> bool:
    return bool(slug) and bool(_SLUG_RE.match(slug))


def is_valid_timezone(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def is_valid_language(code: str) -> bool:
    return code in SUPPORTED_LANGUAGE_CODES


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_college_configuration(college: College, *, has_active_course: bool) -> ValidationResult:
    errors: list[str] = []

    if not college.name or not college.name.strip():
        errors.append("College name is required.")

    if not is_valid_slug(college.slug or ""):
        errors.append("College slug is missing or invalid.")

    if not college.email:
        errors.append("Primary contact email is missing.")

    if not college.timezone or not is_valid_timezone(college.timezone):
        errors.append("College time zone is missing or invalid.")

    supported = college.supported_languages or []
    if not supported:
        errors.append("At least one supported language is required.")
    else:
        unsupported = [code for code in supported if not is_valid_language(code)]
        if unsupported:
            errors.append(f"Unsupported language code(s): {', '.join(unsupported)}.")

    if not college.default_language:
        errors.append("Default language is required.")
    elif college.default_language not in supported:
        errors.append("Default language must be one of the configured supported languages.")

    if not has_active_course:
        errors.append("At least one active course must be configured before publishing.")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "archived"},
    "active": {"suspended", "archived"},
    "suspended": {"active", "archived"},
    "archived": set(),
}


def is_allowed_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
