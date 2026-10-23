"""Which passages a search keeps: keyword matches always, meaning-only ones near the best."""

from __future__ import annotations

import uuid

from docmind.ai.sources import Source
from docmind.repositories.search import all_words_query, keyword_query
from docmind.services.search import MEANING_ONLY_MARGIN, relevant


def _source(vector: float | None, keyword: float | None) -> Source:
    return Source(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Handbook",
        location="Page 1",
        heading="",
        text="text",
        token_count=1,
        vector_score=vector,
        keyword_score=keyword,
    )


def test_meaning_only_matches_far_below_the_best_are_dropped() -> None:
    best = _source(0.72, 0.55)
    close = _source(0.72 - MEANING_ONLY_MARGIN / 2, None)
    unrelated = _source(0.56, None)
    keyword_only = _source(None, 0.1)

    assert relevant([best, close, unrelated, keyword_only]) == [best, close, keyword_only]


def test_without_vector_scores_everything_is_kept() -> None:
    sources = [_source(None, 0.4), _source(None, 0.2)]

    assert relevant(sources) == sources


def test_snippet_queries_join_the_same_words_two_ways() -> None:
    assert keyword_query("What is the parental leave policy?") == "parental | leav | policy"
    assert all_words_query("What is the parental leave policy?") == "parental & leav & policy"
    assert all_words_query("the of and") is None
