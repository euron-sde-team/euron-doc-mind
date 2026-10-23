from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Date, cast, func, select, text

from docmind.models import UsageEvent
from docmind.models.enums import CacheResult, UsageKind
from docmind.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class DailyUsage:
    day: str
    questions: int
    context_tokens: int
    baseline_tokens: int
    saved_tokens: int
    cache_hits: int


@dataclass(frozen=True, slots=True)
class UsageTotals:
    questions: int
    searches: int
    context_tokens: int
    prompt_tokens: int
    completion_tokens: int
    baseline_tokens: int
    saved_tokens: int
    cache_hits: int
    p50_latency_ms: int
    p95_latency_ms: int


class UsageRepository(Repository):
    async def add(self, event: UsageEvent) -> None:
        self.session.add(event)
        await self.session.flush()

    async def totals(self, workspace_id: uuid.UUID, since: datetime) -> UsageTotals:
        answers = UsageEvent.kind == UsageKind.ANSWER
        row = (
            await self.session.execute(
                select(
                    func.count().filter(answers),
                    func.count().filter(UsageEvent.kind == UsageKind.SEARCH),
                    func.coalesce(func.sum(UsageEvent.context_tokens).filter(answers), 0),
                    func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.baseline_tokens).filter(answers), 0),
                    func.coalesce(func.sum(UsageEvent.saved_tokens).filter(answers), 0),
                    func.count().filter(answers, UsageEvent.cache != CacheResult.MISS),
                    func.coalesce(
                        func.percentile_cont(0.5)
                        .within_group(UsageEvent.latency_ms)
                        .filter(answers),
                        0,
                    ),
                    func.coalesce(
                        func.percentile_cont(0.95)
                        .within_group(UsageEvent.latency_ms)
                        .filter(answers),
                        0,
                    ),
                ).where(UsageEvent.workspace_id == workspace_id, UsageEvent.created_at >= since)
            )
        ).one()
        return UsageTotals(*(int(value) for value in row))

    async def daily(self, workspace_id: uuid.UUID, since: datetime) -> list[DailyUsage]:
        day = cast(func.date_trunc("day", UsageEvent.created_at), Date)
        rows = await self.session.execute(
            select(
                day.label("day"),
                func.count(),
                func.coalesce(func.sum(UsageEvent.context_tokens), 0),
                func.coalesce(func.sum(UsageEvent.baseline_tokens), 0),
                func.coalesce(func.sum(UsageEvent.saved_tokens), 0),
                func.count().filter(UsageEvent.cache != CacheResult.MISS),
            )
            .where(
                UsageEvent.workspace_id == workspace_id,
                UsageEvent.created_at >= since,
                UsageEvent.kind == UsageKind.ANSWER,
            )
            .group_by(day)
            .order_by(day)
        )
        return [
            DailyUsage(d.isoformat(), int(q), int(c), int(b), int(s), int(h))
            for d, q, c, b, s, h in rows.all()
        ]

    async def top_documents(
        self, workspace_id: uuid.UUID, since: datetime, limit: int = 6
    ) -> list[tuple[uuid.UUID, int]]:
        rows = await self.session.execute(
            text(
                "SELECT doc_id, count(*) AS cites "
                "FROM usage_events, unnest(cited_document_ids) AS doc_id "
                "WHERE workspace_id = :workspace_id AND created_at >= :since "
                "GROUP BY doc_id ORDER BY cites DESC LIMIT :limit"
            ),
            {"workspace_id": workspace_id, "since": since, "limit": limit},
        )
        return [(r.doc_id, int(r.cites)) for r in rows.all()]
