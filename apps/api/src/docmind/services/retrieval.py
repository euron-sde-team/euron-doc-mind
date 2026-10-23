"""Hybrid retrieval: vector and full-text candidates, fused, diversified and packed."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from docmind.ai.retrieval import mmr, pack_context, reciprocal_rank_fusion
from docmind.ai.sources import Source
from docmind.core import metrics
from docmind.repositories.search import SearchRepository
from docmind.services.container import Container


class RetrievalService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.search_repo = SearchRepository(session)

    async def candidates(
        self,
        workspace_id: uuid.UUID,
        question: str,
        document_ids: Sequence[uuid.UUID] | None,
        query_vector: np.ndarray | None = None,
        limit: int | None = None,
    ) -> tuple[list[Source], np.ndarray]:
        started = time.perf_counter()
        limit = limit or self.c.settings.retrieval_candidates
        vector = (
            query_vector
            if query_vector is not None
            else await self.c.embedder.embed_query(question)
        )
        by_vector = await self.search_repo.vector_candidates(
            workspace_id, vector, document_ids, limit
        )
        by_keyword = await self.search_repo.keyword_candidates(
            workspace_id, question, document_ids, limit
        )
        fused = reciprocal_rank_fusion([i for i, _ in by_vector], [i for i, _ in by_keyword])
        ranked = sorted(fused, key=lambda item: fused[item], reverse=True)[:limit]
        rows = await self.search_repo.hydrate(workspace_id, ranked)
        vector_scores, keyword_scores = dict(by_vector), dict(by_keyword)
        sources = [
            Source(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.document_title,
                location=row.location,
                heading=row.heading,
                text=row.text,
                token_count=row.token_count,
                section_ordinal=row.section_ordinal,
                char_start=row.char_start,
                char_end=row.char_end,
                vector_score=vector_scores.get(row.id),
                keyword_score=keyword_scores.get(row.id),
                fused_score=fused[row.id],
                embedding=row.embedding,
            )
            for chunk_id in ranked
            if (row := rows.get(chunk_id)) is not None
        ]
        metrics.RETRIEVAL_DURATION.observe(time.perf_counter() - started)
        return sources, vector

    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        question: str,
        document_ids: Sequence[uuid.UUID] | None,
        *,
        top_k: int,
        budget: int,
        query_vector: np.ndarray | None = None,
    ) -> list[Source]:
        sources, vector = await self.candidates(workspace_id, question, document_ids, query_vector)
        diversified = mmr(vector, sources, limit=top_k * 2)
        return pack_context(diversified, budget=budget, max_sources=top_k)

    async def headlines(
        self, workspace_id: uuid.UUID, question: str, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        return await self.search_repo.headlines(workspace_id, question, ids)
