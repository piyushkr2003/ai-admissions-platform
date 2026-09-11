"""Text extraction per supported source type (docs/rag.md sections 16-19).

Kept independent from chunking/embedding so a new format only needs a
new function here (Task 005 section 16).
"""
from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from app.core.errors import AppError

SUPPORTED_SOURCE_TYPES = ("pdf", "txt", "manual", "faq")


class ExtractionError(AppError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, status_code=422)


def extract_plain_text(text: str) -> str:
    if not text or not text.strip():
        raise ExtractionError("EMPTY_DOCUMENT", "The supplied text is empty.")
    return text


def extract_pdf_text(file_base64: str) -> str:
    try:
        raw = base64.b64decode(file_base64, validate=True)
    except Exception as exc:  # noqa: BLE001 - any decode failure is a client error
        raise ExtractionError("UNSUPPORTED_FILE_TYPE", "file_base64 is not valid base64 content.") from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - malformed PDFs must fail safely, not crash
        raise ExtractionError("EXTRACTION_FAILED", "The PDF could not be processed.") from exc

    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise ExtractionError(
            "EMPTY_DOCUMENT",
            "No extractable text was found (the PDF may be image-only/scanned; OCR is not implemented).",
        )
    return text
