"""Language detection for English/Hindi/Hinglish routing
(docs/tasks/006 section 42, docs/agent-tools.md section 48).

Structured facts (fees, dates, eligibility) never change based on
language - only the phrasing of the agent's response does.
"""
from __future__ import annotations

import re

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

_HINGLISH_MARKERS = (
    "kya", "hai", "hain", "kitna", "kitni", "chahiye", "kaise", "mujhe",
    "aap", "kab", "karna", "karni", "milegi", "mil", "wala", "vala",
    "acha", "theek", "haan", "nahi", "namaste", "dhanyavad",
)


def detect_language(text: str, *, fallback: str = "en") -> str:
    if not text or not text.strip():
        return fallback

    if _DEVANAGARI_RE.search(text):
        return "hi"

    lowered = text.lower()
    tokens = re.findall(r"[a-z]+", lowered)
    if tokens and any(marker in tokens for marker in _HINGLISH_MARKERS):
        return "hinglish"

    return "en"
