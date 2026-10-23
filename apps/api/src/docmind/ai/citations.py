"""Turn [n] markers in an answer into verified citations.

Markers that point at a source the answer was not given are removed rather than shown, so
a citation is never a dead link. Each kept citation carries the sentence from the source
that best supports the claim, used for the hover preview and the viewer highlight.
"""

from __future__ import annotations

import re
from typing import Any

from docmind.ai.sources import Source
from docmind.core.text import content_terms, split_sentences, truncate

_MARKER = re.compile(r"\s?\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]")
# Blocks (paragraphs, list items) come before sentences: list items rarely end with a full
# stop, so splitting a slide or a list by sentence alone would quote the whole list.
_BLOCK = re.compile(r"\n\s*\n|\n(?=\s*[\N{BULLET}*-]\s)")


def _numbers(group: str) -> list[int]:
    return [int(part) for part in re.split(r"[,;]\s*", group) if part.strip().isdigit()]


def best_quote(claim: str, passage: str) -> str:
    claim_terms = set(content_terms(claim))
    pieces = [sentence for block in _BLOCK.split(passage) for sentence in split_sentences(block)]
    best = max(pieces or [passage], key=lambda s: len(claim_terms & set(content_terms(s))))
    return truncate(" ".join(best.lstrip("\N{BULLET}*- ").split()), 320)


def extract_citations(answer: str, sources: list[Source]) -> tuple[str, list[dict[str, Any]]]:
    by_number = {s.n: s for s in sources}
    claims: dict[int, str] = {}

    def keep_valid(match: re.Match[str]) -> str:
        valid = [n for n in _numbers(match.group(1)) if n in by_number]
        return "".join(f" [{n}]" for n in dict.fromkeys(valid))

    cleaned = _MARKER.sub(keep_valid, answer).strip()
    for sentence in split_sentences(cleaned) or [cleaned]:
        for match in _MARKER.finditer(sentence):
            for n in _numbers(match.group(1)):
                claims.setdefault(n, _MARKER.sub("", sentence))

    citations = []
    for n in sorted(claims):
        source = by_number[n]
        citations.append(
            {
                "n": n,
                "chunk_id": str(source.chunk_id),
                "document_id": str(source.document_id),
                "document_title": source.document_title,
                "location": source.location,
                "section_ordinal": source.section_ordinal,
                "char_start": source.char_start,
                "char_end": source.char_end,
                "quote": best_quote(claims[n], source.text),
            }
        )
    return cleaned, citations
