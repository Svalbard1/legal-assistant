from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    session_id: UUID | None = None
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20)


class Source(BaseModel):
    file: str
    text: str
    score: float
    page: int | None = None


class MessageSourceResponse(Source):
    position: int


class AskResponse(BaseModel):
    session_id: UUID
    answer: str
    sources: list[Source]
    took_ms: int
    llm: str


class SessionResponse(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class MessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    sources: list[MessageSourceResponse] = Field(default_factory=list)
    took_ms: int | None = None
    llm: str | None = None


class MessageListResponse(BaseModel):
    session_id: UUID
    messages: list[MessageResponse]
