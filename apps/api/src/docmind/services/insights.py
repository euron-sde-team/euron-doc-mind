"""Workspace insights: questions, tokens saved, cache hit rate, latency, most-cited files."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from docmind.core.logging import get_logger
from docmind.models import Workspace
from docmind.models.enums import DocumentStatus
from docmind.repositories.documents import DocumentRepository
from docmind.repositories.usage import UsageRepository
from docmind.services.container import Container

CACHE_SECONDS = 30
log = get_logger("docmind.insights")


class InsightsService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.usage = UsageRepository(session)
        self.documents = DocumentRepository(session)

    async def overview(self, workspace: Workspace, days: int) -> dict[str, Any]:
        cache_key = f"insights:{workspace.id}:{days}"
        try:
            cached = await self.c.redis.get(cache_key)
        except Exception:
            cached = None
        if cached:
            result: dict[str, Any] = orjson.loads(cached)
            return result

        since = datetime.now(UTC) - timedelta(days=days)
        totals = await self.usage.totals(workspace.id, since)
        daily = {point.day: point for point in await self.usage.daily(workspace.id, since)}
        top = await self.usage.top_documents(workspace.id, since)
        titles = await self.documents.titles(workspace.id, [doc_id for doc_id, _ in top])
        stats = await self.documents.stats(workspace.id)

        series = []
        start = (datetime.now(UTC) - timedelta(days=days - 1)).date()
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            point = daily.get(day)
            series.append(
                {
                    "day": day,
                    "questions": point.questions if point else 0,
                    "context_tokens": point.context_tokens if point else 0,
                    "baseline_tokens": point.baseline_tokens if point else 0,
                    "saved_tokens": point.saved_tokens if point else 0,
                    "cache_hits": point.cache_hits if point else 0,
                }
            )

        payload: dict[str, Any] = {
            "days": days,
            "totals": {
                **totals.__dict__,
                "saved_ratio": round(totals.saved_tokens / totals.baseline_tokens, 4)
                if totals.baseline_tokens
                else 0.0,
                "cache_hit_rate": round(totals.cache_hits / totals.questions, 4)
                if totals.questions
                else 0.0,
            },
            "daily": series,
            "top_documents": [
                {
                    "document_id": str(doc_id),
                    "title": titles.get(doc_id, "Deleted document"),
                    "citations": count,
                }
                for doc_id, count in top
                if doc_id in titles
            ],
            "library": {
                "documents": sum(stats.by_status.values()),
                "ready": stats.by_status.get(DocumentStatus.READY, 0),
                "processing": stats.by_status.get(DocumentStatus.PROCESSING, 0)
                + stats.by_status.get(DocumentStatus.QUEUED, 0),
                "failed": stats.by_status.get(DocumentStatus.FAILED, 0),
                "chunks": stats.ready_chunks,
                "tokens": stats.ready_tokens,
                "bytes": stats.total_bytes,
            },
            "generator": self.c.generator.label,
            "embeddings": self.c.embedder.name,
        }
        try:
            await self.c.redis.set(
                cache_key, orjson.dumps(payload, default=_default), ex=CACHE_SECONDS
            )
        except Exception:  # the cache only saves work; never fail the request over it
            log.warning("insights_cache_write_failed")
        return orjson.loads(orjson.dumps(payload, default=_default))  # type: ignore[no-any-return]


def _default(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)
