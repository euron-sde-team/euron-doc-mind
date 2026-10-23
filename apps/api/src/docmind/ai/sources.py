"""A retrieved passage as the answer layer sees it, numbered for citation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Source:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    location: str
    heading: str
    text: str
    token_count: int
    section_ordinal: int = 0
    char_start: int = 0
    char_end: int = 0
    vector_score: float | None = None
    keyword_score: float | None = None
    fused_score: float = 0.0
    embedding: Any = field(default=None, repr=False)
    n: int = 0

    def public(self) -> dict[str, Any]:
        """The shape sent to clients: no embedding, scores rounded."""
        return {
            "n": self.n,
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "document_title": self.document_title,
            "location": self.location,
            "heading": self.heading,
            "section_ordinal": self.section_ordinal,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "snippet": self.text[:420],
            "score": round(self.fused_score, 4),
            "vector_score": None if self.vector_score is None else round(self.vector_score, 4),
            "keyword_score": None if self.keyword_score is None else round(self.keyword_score, 4),
        }
