"""Two-level answer cache.

1. Exact: the normalised question, in Redis. One GET.
2. Semantic: the nearest previous question by embedding, in Postgres (pgvector), accepted
   above SEMANTIC_CACHE_THRESHOLD. "What's the parental leave policy?" and "How much
   parental leave do we get?" share one answer.

Both are keyed by the workspace's corpus version, the document scope and the generator, so
an upload or a model change retires every entry at once without a purge.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from docmind.core import metrics
from docmind.core.logging import get_logger
from docmind.models import AnswerCacheEntry
from docmind.models.enums import CacheResult
from docmind.repositories.answer_cache import AnswerCacheRepository
from docmind.services.container import Container

log = get_logger("docmind.answer_cache")


@dataclass(frozen=True, slots=True)
class CachedAnswer:
    result: CacheResult
    answer: str
    citations: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    context_tokens: int


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.lower()).strip().rstrip("?.! ")


def scope_hash(document_ids: Sequence[uuid.UUID] | None) -> str:
    if not document_ids:
        return "all"
    joined = ",".join(sorted(str(i) for i in document_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class CacheKey:
    workspace_id: uuid.UUID
    corpus_version: int
    generator: str
    scope: str

    def exact(self, question: str) -> str:
        digest = hashlib.sha256(normalize_question(question).encode()).hexdigest()
        return (
            f"ans:{self.workspace_id}:{self.corpus_version}:{self.generator}:{self.scope}:{digest}"
        )


class AnswerCache:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.repo = AnswerCacheRepository(session)

    async def lookup(self, key: CacheKey, question: str, vector: np.ndarray) -> CachedAnswer | None:
        try:
            raw = await self.c.redis.get(key.exact(question))
        except Exception:
            raw = None
        if raw:
            payload = orjson.loads(raw)
            metrics.ANSWER_CACHE.labels("exact").inc()
            return CachedAnswer(
                CacheResult.EXACT,
                payload["answer"],
                payload["citations"],
                payload["sources"],
                payload["context_tokens"],
            )
        nearest = await self.repo.nearest(
            key.workspace_id, key.scope, key.corpus_version, key.generator, vector
        )
        if nearest is not None and nearest[1] >= self.c.settings.semantic_cache_threshold:
            entry, similarity = nearest
            await self.repo.record_hit(entry.id)
            metrics.ANSWER_CACHE.labels("semantic").inc()
            log.info("semantic_cache_hit", similarity=round(similarity, 4))
            return CachedAnswer(
                CacheResult.SEMANTIC,
                entry.answer,
                entry.citations,
                entry.usage.get("sources", []),
                int(entry.usage.get("context_tokens", 0)),
            )
        metrics.ANSWER_CACHE.labels("miss").inc()
        return None

    async def store(
        self,
        key: CacheKey,
        question: str,
        vector: np.ndarray,
        *,
        answer: str,
        citations: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        context_tokens: int,
    ) -> None:
        ttl = self.c.settings.answer_cache_ttl_s
        if ttl <= 0:
            return
        payload = {
            "answer": answer,
            "citations": citations,
            "sources": sources,
            "context_tokens": context_tokens,
        }
        try:
            await self.c.redis.set(key.exact(question), orjson.dumps(payload), ex=ttl)
        except Exception:
            log.warning("answer_cache_write_failed")
        await self.repo.add(
            AnswerCacheEntry(
                workspace_id=key.workspace_id,
                scope_hash=key.scope,
                corpus_version=key.corpus_version,
                generator=key.generator,
                question=question[:2000],
                question_embedding=vector,
                answer=answer,
                citations=citations,
                usage={"sources": sources, "context_tokens": context_tokens},
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            )
        )
