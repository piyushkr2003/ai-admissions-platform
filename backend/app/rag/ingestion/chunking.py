"""Paragraph-aware chunking (docs/rag.md section 17/24).

Splits on paragraph boundaries first so headings stay attached to the
text that follows them, then merges/splits to stay within
[min_chars, max_chars], with a small overlap between adjacent chunks so
context is not lost at a boundary.
"""
from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def chunk_text(
    text: str, *, max_chars: int = 400, overlap_chars: int = 50
) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
        else:
            current = paragraph

        # A single paragraph longer than max_chars must still be split.
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars - overlap_chars :] if overlap_chars else current[max_chars:]

    if current.strip():
        chunks.append(current.strip())

    return chunks
