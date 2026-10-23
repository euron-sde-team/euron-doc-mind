from __future__ import annotations

import uuid

from pydantic import Field

from docmind.schemas.common import ApiModel


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=500)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    limit: int = Field(default=10, ge=1, le=50)


class SearchHit(ApiModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    location: str
    heading: str
    section_ordinal: int
    char_start: int
    char_end: int
    snippet: str = Field(description="Matches are wrapped in U+0001 and U+0002, never HTML.")
    score: float
    vector_score: float | None
    keyword_score: float | None


class SearchOut(ApiModel):
    query: str
    hits: list[SearchHit]
    took_ms: int
