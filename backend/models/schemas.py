from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..config import MAX_MESSAGE_CHARS, MAX_HISTORY_MESSAGES


class HistoryMessage(BaseModel):
    role: Literal["user", "model"]
    text: str = Field(default="", max_length=20000)


class ClarificationContext(BaseModel):
    awaiting_clarification: bool = False
    original_intent: Optional[str] = Field(default=None, max_length=40)


def _trim_history(v: list[HistoryMessage]) -> list[HistoryMessage]:
    return v[-MAX_HISTORY_MESSAGES:]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)
    context: ClarificationContext = Field(default_factory=ClarificationContext)

    _trim = field_validator("history")(_trim_history)


class RagInitiateRequest(BaseModel):
    company: str = Field(min_length=1, max_length=100)


class RagQueryRequest(BaseModel):
    doc_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=100)

    _trim = field_validator("history")(_trim_history)
