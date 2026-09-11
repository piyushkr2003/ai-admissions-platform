from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(description="One of: pdf, txt, manual, faq")
    text: str | None = None
    file_base64: str | None = None
    visibility: str = "public"
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)
