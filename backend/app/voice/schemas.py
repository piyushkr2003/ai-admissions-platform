"""Request schemas for the voice session API (docs/voice.md section 8)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceSessionCreate(BaseModel):
    college_id: str
    channel: str = Field(default="web_voice", max_length=20)
    language: str | None = None


class VoiceEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=50)
    text: str | None = Field(default=None, max_length=4000)
    event_id: str | None = Field(default=None, max_length=255)


class VoiceSessionEnd(BaseModel):
    reason: str | None = Field(default="completed", max_length=50)
