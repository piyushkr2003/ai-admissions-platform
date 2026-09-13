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
    # Base64-encoded recorded audio for the web channel (Task 023 - Local
    # Free Demo Mode), mirroring the telephony webhook's existing
    # `audio_base64` field (app/voice/providers/base.py's
    # InboundCallEvent). When provided without `text` on a
    # final_transcript event, the router runs server-side STT before
    # handing the recognized text to VoiceSessionService, exactly like
    # the phone channel already does - no VoiceSessionService change.
    audio_base64: str | None = Field(default=None)
    event_id: str | None = Field(default=None, max_length=255)


class VoiceSessionEnd(BaseModel):
    reason: str | None = Field(default="completed", max_length=50)
