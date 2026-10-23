from __future__ import annotations

import uuid
from datetime import datetime

import numpy as np
from sqlalchemy import delete, func, select, update

from docmind.models import AnswerCacheEntry
from docmind.repositories.base import Repository


class AnswerCacheRepository(Repository):
    async def nearest(
        self,
        workspace_id: uuid.UUID,
        scope_hash: str,
        corpus_version: int,
        generator: str,
        query: np.ndarray,
    ) -> tuple[AnswerCacheEntry, float] | None:
        distance = AnswerCacheEntry.question_embedding.cosine_distance(query)
        result = await self.session.execute(
            select(AnswerCacheEntry, (1 - distance).label("similarity"))
            .where(
                AnswerCacheEntry.workspace_id == workspace_id,
                AnswerCacheEntry.scope_hash == scope_hash,
                AnswerCacheEntry.corpus_version == corpus_version,
                AnswerCacheEntry.generator == generator,
                AnswerCacheEntry.expires_at > func.now(),
            )
            .order_by(distance)
            .limit(1)
        )
        row = result.first()
        return (row[0], float(row[1])) if row else None

    async def add(self, entry: AnswerCacheEntry) -> None:
        self.session.add(entry)
        await self.session.flush()

    async def record_hit(self, entry_id: uuid.UUID) -> None:
        await self.session.execute(
            update(AnswerCacheEntry)
            .where(AnswerCacheEntry.id == entry_id)
            .values(hits=AnswerCacheEntry.hits + 1, last_hit_at=func.now())
        )

    async def purge_expired(self, now: datetime) -> int:
        result = await self.session.execute(
            delete(AnswerCacheEntry).where(AnswerCacheEntry.expires_at <= now)
        )
        return int(getattr(result, "rowcount", 0) or 0)
