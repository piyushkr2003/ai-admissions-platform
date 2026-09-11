from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    college_id: str
    channel: str = "web_voice"
    language: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
