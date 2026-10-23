from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Computed, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from docmind.db.base import Base, IdMixin, TimestampMixin
from docmind.db.types import Embedding


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(8))
    mime_type: Mapped[str] = mapped_column(String(160))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    section_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    token_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None]


class DocumentSection(IdMixin, Base):
    """A page, slide, sheet or text section exactly as parsed, for the document viewer."""

    __tablename__ = "document_sections"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(default=0)


class Chunk(IdMixin, Base):
    """A retrievable passage: its text, where it came from, and both search representations."""

    __tablename__ = "chunks"

    # Denormalised from the document so retrieval filters on one column of one table.
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    section_ordinal: Mapped[int]
    ordinal: Mapped[int]
    heading: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int]
    char_end: Mapped[int]
    token_count: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[Any] = mapped_column(Embedding())
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True),
    )
