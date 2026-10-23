from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from docmind.db.base import Base, IdMixin


class UsageEvent(IdMixin, Base):
    """One answered question or search, with the token arithmetic behind the savings meter."""

    __tablename__ = "usage_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))
    cache: Mapped[str] = mapped_column(String(16))
    generator: Mapped[str] = mapped_column(String(120))
    context_tokens: Mapped[int] = mapped_column(default=0)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    baseline_tokens: Mapped[int] = mapped_column(default=0)
    saved_tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    cited_document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
