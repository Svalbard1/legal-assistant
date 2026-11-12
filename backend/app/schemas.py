from typing import Literal

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)


class Source(BaseModel):
    file: str
    text: str
    score: float
    page: int | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    took_ms: int
    llm: str
