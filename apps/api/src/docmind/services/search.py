"""Hybrid search across a workspace, with highlighted snippets."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from docmind.ai.sources import Source
from docmind.models import UsageEvent, Workspace
from docmind.models.enums import CacheResult, UsageKind
from docmind.repositories.usage import UsageRepository
from docmind.services.chat import ChatService
from docmind.services.container import Container
from docmind.services.principal import Principal
from docmind.services.retrieval import RetrievalService

# A passage found by meaning alone is kept only when it is about as close to the query as
# the best match. Embeddings always return a nearest neighbour, even for unrelated text, and
# a search box should not pad its results with passages that merely share a domain.
MEANING_ONLY_MARGIN = 0.1


def relevant(sources: Sequence[Source]) -> list[Source]:
    """Keyword matches, plus meaning-only matches within the margin of the best one."""
    scores = [s.vector_score for s in sources if s.vector_score is not None]
    if not scores:
        return list(sources)
    floor = max(scores) - MEANING_ONLY_MARGIN
    return [
        s
        for s in sources
        if s.keyword_score is not None or (s.vector_score is not None and s.vector_score >= floor)
    ]


class SearchService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session

    async def search(
        self,
        workspace: Workspace,
        principal: Principal,
        query: str,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        started = time.perf_counter()
        scope = await ChatService(self.c, self.session).validated_scope(workspace.id, document_ids)
        retrieval = RetrievalService(self.c, self.session)
        sources, _ = await retrieval.candidates(
            workspace.id, query, scope, limit=max(limit * 2, 20)
        )
        sources = relevant(sources)[:limit]
        snippets = await retrieval.headlines(workspace.id, query, [s.chunk_id for s in sources])
        hits = [
            {
                "chunk_id": s.chunk_id,
                "document_id": s.document_id,
                "document_title": s.document_title,
                "location": s.location,
                "heading": s.heading,
                "section_ordinal": s.section_ordinal,
                "char_start": s.char_start,
                "char_end": s.char_end,
                "snippet": snippets.get(s.chunk_id) or s.text[:280],
                "score": round(s.fused_score, 4),
                "vector_score": None if s.vector_score is None else round(s.vector_score, 4),
                "keyword_score": None if s.keyword_score is None else round(s.keyword_score, 4),
            }
            for s in sources
        ]
        took_ms = int((time.perf_counter() - started) * 1000)
        await UsageRepository(self.session).add(
            UsageEvent(
                workspace_id=workspace.id,
                user_id=principal.user_id,
                api_key_id=principal.api_key_id,
                kind=UsageKind.SEARCH,
                cache=CacheResult.MISS.value,
                generator="search",
                latency_ms=took_ms,
            )
        )
        await self.session.commit()
        return hits, took_ms
