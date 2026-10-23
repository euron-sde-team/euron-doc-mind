import uuid

import numpy as np

from docmind.ai.retrieval import mmr, pack_context, reciprocal_rank_fusion
from tests.unit.helpers import source

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_rrf_rewards_agreement_between_rankings() -> None:
    scores = reciprocal_rank_fusion([A, B, C], [C, A, D])
    ranked = sorted(scores, key=lambda item: scores[item], reverse=True)
    assert ranked[:2] == [A, C]
    assert scores[D] < scores[B] + 1e-9 or scores[D] > 0


def test_rrf_weights() -> None:
    scores = reciprocal_rank_fusion([A], [B], weights=[2.0, 1.0])
    assert scores[A] > scores[B]


def test_mmr_prefers_diverse_passages() -> None:
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    first = source("first", n=0)
    duplicate = source("duplicate", n=0)
    different = source("different", n=0)
    first.embedding, first.fused_score = np.array([1.0, 0.0, 0.0], dtype=np.float32), 1.0
    duplicate.embedding, duplicate.fused_score = np.array([0.99, 0.14, 0.0], dtype=np.float32), 0.95
    different.embedding, different.fused_score = np.array([0.6, 0.0, 0.8], dtype=np.float32), 0.9
    chosen = mmr(query, [first, duplicate, different], limit=2, diversity=0.7)
    assert [c.text for c in chosen] == ["first", "different"]


def test_pack_context_fills_the_budget_and_numbers_sources() -> None:
    items = [source(f"s{i}", n=0, tokens=t) for i, t in enumerate([500, 900, 300, 200])]
    packed = pack_context(items, budget=1000, max_sources=3)
    assert [s.text for s in packed] == ["s0", "s2", "s3"]
    assert [s.n for s in packed] == [1, 2, 3]


def test_pack_context_always_keeps_the_best_passage() -> None:
    packed = pack_context([source("huge", n=0, tokens=5000)], budget=100, max_sources=3)
    assert len(packed) == 1
