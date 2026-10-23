"""Pure retrieval math: rank fusion, diversification and context packing.

The database returns two ranked lists (vector similarity and full-text rank). They are
merged with Reciprocal Rank Fusion, which needs no score calibration between the two
systems. Maximal Marginal Relevance then drops near-duplicate passages, and the result is
packed greedily into the context token budget.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import numpy as np

from docmind.ai.sources import Source

RRF_K = 60


def reciprocal_rank_fusion(
    *rankings: Sequence[uuid.UUID], k: int = RRF_K, weights: Sequence[float] | None = None
) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for index, ranking in enumerate(rankings):
        weight = weights[index] if weights else 1.0
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank + 1)
    return scores


def mmr(
    query: np.ndarray, candidates: Sequence[Source], *, limit: int, diversity: float = 0.3
) -> list[Source]:
    """Pick `limit` sources balancing relevance (fused score) against redundancy."""
    pool = [c for c in candidates if c.embedding is not None]
    if len(pool) <= 1:
        return list(candidates)[:limit]
    vectors = np.stack([np.asarray(c.embedding, dtype=np.float32) for c in pool])
    relevance = np.array([c.fused_score for c in pool], dtype=np.float32)
    span = float(relevance.max() - relevance.min()) or 1.0
    relevance = (relevance - relevance.min()) / span
    similarity = vectors @ vectors.T
    chosen: list[int] = []
    remaining = list(range(len(pool)))
    while remaining and len(chosen) < limit:
        if chosen:
            redundancy = similarity[np.ix_(remaining, chosen)].max(axis=1)
        else:
            redundancy = np.zeros(len(remaining), dtype=np.float32)
        scores = (1 - diversity) * relevance[remaining] - diversity * redundancy
        best = remaining[int(np.argmax(scores))]
        chosen.append(best)
        remaining.remove(best)
    return [pool[i] for i in chosen]


def pack_context(candidates: Sequence[Source], *, budget: int, max_sources: int) -> list[Source]:
    """Greedy fill of the token budget in preference order; numbered from 1 for citation."""
    packed: list[Source] = []
    used = 0
    for candidate in candidates:
        if len(packed) >= max_sources:
            break
        if used + candidate.token_count > budget and packed:
            continue
        packed.append(candidate)
        used += candidate.token_count
    for number, source in enumerate(packed, start=1):
        source.n = number
    return packed
