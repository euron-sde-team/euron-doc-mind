"""The two candidate searches behind hybrid retrieval, plus chunk hydration.

Vector search uses the HNSW index with iterative scans (pgvector 0.8), so filtering by
workspace and documents does not starve the result list the way post-filtering would.
Every statement is static SQL with bound parameters; nothing is assembled from strings.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import text

from docmind.core.text import content_terms
from docmind.repositories.base import Repository

_SAFE_TERM = re.compile(r"^[a-z0-9]+$")
# Search snippets mark matches with control characters, never HTML: the client splits on
# them and renders text nodes, so document content can never be interpreted as markup.
HIGHLIGHT_START = chr(1)
HIGHLIGHT_END = chr(2)
_HEADLINE_OPTIONS = (
    "MaxFragments=2, MaxWords=32, MinWords=12, FragmentDelimiter= ... , "
    f"StartSel={HIGHLIGHT_START}, StopSel={HIGHLIGHT_END}"
)

_TUNE_HNSW = text(
    "SELECT set_config('hnsw.ef_search', :ef_search, true), "
    "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
)
# In both candidate queries a NULL :document_ids means "every document in the workspace".
_VECTOR = text(
    "SELECT c.id, 1 - (c.embedding <=> :query) AS score FROM chunks c "
    "WHERE c.workspace_id = :workspace_id "
    "AND (CAST(:document_ids AS uuid[]) IS NULL "
    "OR c.document_id = ANY(CAST(:document_ids AS uuid[]))) "
    "ORDER BY c.embedding <=> :query LIMIT :limit"
)
_KEYWORD = text(
    "SELECT c.id, ts_rank_cd(c.tsv, q, 32) AS rank "
    "FROM chunks c, to_tsquery('english', :query) q "
    "WHERE c.workspace_id = :workspace_id AND c.tsv @@ q "
    "AND (CAST(:document_ids AS uuid[]) IS NULL "
    "OR c.document_id = ANY(CAST(:document_ids AS uuid[]))) "
    "ORDER BY rank DESC LIMIT :limit"
)
_HYDRATE = text(
    "SELECT c.id, c.document_id, d.title AS document_title, c.location, c.heading, c.text, "
    "c.token_count, c.section_ordinal, c.char_start, c.char_end, c.embedding "
    "FROM chunks c JOIN documents d ON d.id = c.document_id "
    "WHERE c.workspace_id = :workspace_id AND c.id = ANY(:ids)"
)
# Two candidate snippets per passage: one around all the query words together, one around
# any of them. The first is better when it exists ("parental leave", not just "leave").
_HEADLINES = text(
    "SELECT c.id, "
    "ts_headline('english', c.text, to_tsquery('english', :every), :options) AS every_word, "
    "ts_headline('english', c.text, to_tsquery('english', :any), :options) AS any_word "
    "FROM chunks c WHERE c.workspace_id = :workspace_id AND c.id = ANY(:ids)"
)


@dataclass(frozen=True, slots=True)
class ChunkRow:
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    location: str
    heading: str
    text: str
    token_count: int
    section_ordinal: int
    char_start: int
    char_end: int
    embedding: Any


def _terms(question: str) -> list[str]:
    return [t for t in dict.fromkeys(content_terms(question)) if _SAFE_TERM.match(t)][:24]


def keyword_query(question: str) -> str | None:
    """An OR query over the question's content words, ranked by cover density.

    `websearch_to_tsquery` would AND every word, which is right for a search box and wrong
    for a natural-language question where most words are not in the passage.
    """
    return " | ".join(_terms(question)) or None


def all_words_query(question: str) -> str | None:
    """The same words joined with AND, for snippets that show them together."""
    return " & ".join(_terms(question)) or None


def _scope(document_ids: Sequence[uuid.UUID] | None) -> list[uuid.UUID] | None:
    return list(document_ids) if document_ids else None


class SearchRepository(Repository):
    async def vector_candidates(
        self,
        workspace_id: uuid.UUID,
        query: np.ndarray,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        await self.session.execute(_TUNE_HNSW, {"ef_search": str(max(40, limit * 2))})
        rows = (
            await self.session.execute(
                _VECTOR,
                {
                    "query": query,
                    "workspace_id": workspace_id,
                    "document_ids": _scope(document_ids),
                    "limit": limit,
                },
            )
        ).all()
        # relaxed_order may return near-ties out of order; the fusion step needs true order.
        return sorted(((r.id, float(r.score)) for r in rows), key=lambda item: -item[1])

    async def keyword_candidates(
        self,
        workspace_id: uuid.UUID,
        question: str,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        query = keyword_query(question)
        if query is None:
            return []
        rows = (
            await self.session.execute(
                _KEYWORD,
                {
                    "query": query,
                    "workspace_id": workspace_id,
                    "document_ids": _scope(document_ids),
                    "limit": limit,
                },
            )
        ).all()
        return [(r.id, float(r.rank)) for r in rows]

    async def hydrate(
        self, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ChunkRow]:
        if not ids:
            return {}
        rows = (
            await self.session.execute(_HYDRATE, {"workspace_id": workspace_id, "ids": list(ids)})
        ).all()
        return {
            r.id: ChunkRow(
                id=r.id,
                document_id=r.document_id,
                document_title=r.document_title,
                location=r.location,
                heading=r.heading,
                text=r.text,
                token_count=r.token_count,
                section_ordinal=r.section_ordinal,
                char_start=r.char_start,
                char_end=r.char_end,
                embedding=_as_array(r.embedding),
            )
            for r in rows
        }

    async def headlines(
        self, workspace_id: uuid.UUID, question: str, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        any_word, every_word = keyword_query(question), all_words_query(question)
        if any_word is None or every_word is None or not ids:
            return {}
        rows = (
            await self.session.execute(
                _HEADLINES,
                {
                    "every": every_word,
                    "any": any_word,
                    "options": _HEADLINE_OPTIONS,
                    "workspace_id": workspace_id,
                    "ids": list(ids),
                },
            )
        ).all()
        return {r.id: r.every_word if HIGHLIGHT_START in r.every_word else r.any_word for r in rows}


def _as_array(value: Any) -> np.ndarray:
    if value is None:
        return np.zeros(0, dtype=np.float32)
    to_numpy = getattr(value, "to_numpy", None)
    return np.asarray(to_numpy() if to_numpy else value, dtype=np.float32)
