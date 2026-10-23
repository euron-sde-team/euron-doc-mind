from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from docmind.schemas.common import ApiModel


class ConversationCreate(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class ConversationUpdate(ApiModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationOut(ApiModel):
    id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=50, description="Answer only from these documents."
    )


class SourceOut(ApiModel):
    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    location: str
    heading: str
    section_ordinal: int
    char_start: int
    char_end: int
    snippet: str
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None


class CitationOut(ApiModel):
    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    location: str
    section_ordinal: int
    char_start: int
    char_end: int
    quote: str


class UsageOut(ApiModel):
    generator: str
    cache: Literal["miss", "exact", "semantic"]
    context_tokens: int = Field(description="Document tokens given to the answerer.")
    prompt_tokens: int = Field(description="Tokens a model actually received (0 without a model).")
    completion_tokens: int
    baseline_tokens: int = Field(
        description="Tokens of every document in scope: the paste-it-all cost."
    )
    saved_tokens: int
    saved_ratio: float
    latency_ms: int


class MessageOut(ApiModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[CitationOut] = []
    sources: list[SourceOut] = []
    usage: UsageOut | None = None
    created_at: datetime


class AnswerOut(ApiModel):
    conversation_id: uuid.UUID | None
    message: MessageOut
