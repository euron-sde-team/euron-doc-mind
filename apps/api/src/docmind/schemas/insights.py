from __future__ import annotations

import uuid

from docmind.schemas.common import ApiModel
from docmind.schemas.documents import LibraryStats


class Totals(ApiModel):
    questions: int
    searches: int
    context_tokens: int
    prompt_tokens: int
    completion_tokens: int
    baseline_tokens: int
    saved_tokens: int
    saved_ratio: float
    cache_hits: int
    cache_hit_rate: float
    p50_latency_ms: int
    p95_latency_ms: int


class DailyPoint(ApiModel):
    day: str
    questions: int
    context_tokens: int
    baseline_tokens: int
    saved_tokens: int
    cache_hits: int


class TopDocument(ApiModel):
    document_id: uuid.UUID
    title: str
    citations: int


class InsightsOut(ApiModel):
    days: int
    totals: Totals
    daily: list[DailyPoint]
    top_documents: list[TopDocument]
    library: LibraryStats
    generator: str
    embeddings: str
