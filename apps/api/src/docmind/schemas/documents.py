from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from docmind.schemas.common import ApiModel, Paged


class DocumentOut(ApiModel):
    id: uuid.UUID
    title: str
    filename: str
    kind: str
    mime_type: str
    size_bytes: int
    status: str
    error: str | None
    warnings: list[str]
    section_count: int
    chunk_count: int
    token_count: int
    attempts: int
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None

    @field_validator("warnings", mode="before")
    @classmethod
    def _messages(cls, value: Any) -> list[str]:
        return [w["message"] if isinstance(w, dict) else str(w) for w in value or []]


class DocumentPage(Paged):
    items: list[DocumentOut]


class RejectedFile(ApiModel):
    filename: str
    code: str
    message: str


class UploadResult(ApiModel):
    created: list[DocumentOut]
    duplicates: list[DocumentOut] = Field(description="Already in this workspace (same bytes).")
    rejected: list[RejectedFile]


class SectionOut(ApiModel):
    ordinal: int
    kind: str
    label: str
    text: str
    token_count: int


class DocumentDetail(DocumentOut):
    sections: list[SectionOut]


class DocumentUpdate(ApiModel):
    title: str = Field(min_length=1, max_length=300)


class LibraryStats(ApiModel):
    documents: int
    ready: int
    processing: int
    failed: int
    chunks: int
    tokens: int
    bytes: int
