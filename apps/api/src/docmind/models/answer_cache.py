from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from docmind.db.base import Base, IdMixin
from docmind.db.types import Embedding


class AnswerCacheEntry(IdMixin, Base):
    """A finished answer, reusable for the same or a near-identical question.

    Valid only for the corpus version, scope and generator it was produced with; lookups
    filter on all three, so stale entries are never served and need no eager purge.
    """

    __tablename__ = "answer_cache"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    scope_hash: Mapped[str] = mapped_column(String(64))
    corpus_version: Mapped[int]
    generator: Mapped[str] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text)
    question_embedding: Mapped[Any] = mapped_column(Embedding())
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    hits: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_hit_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
