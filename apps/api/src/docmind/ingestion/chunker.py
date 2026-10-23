"""Structure-aware chunking.

Chunks never cross a section (page, slide, sheet) boundary, so every citation points at one
place. Within a section, paragraphs are packed up to the token target; a paragraph that is
too long is split at sentence boundaries, and a sentence that is still too long at word
boundaries. Consecutive chunks overlap by whole sentences up to the overlap budget, and a
heading never ends a chunk: it moves forward to the text it introduces.

Each chunk's text is an exact slice of its section's text, so the viewer can highlight a
cited passage by offsets.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from docmind.ai.tokens import TokenCounter
from docmind.core.text import sentence_spans
from docmind.ingestion.types import BLOCK_SEPARATOR, ParsedDocument, ParsedSection

_WORD = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class SectionDraft:
    ordinal: int
    kind: str
    label: str
    text: str
    token_count: int


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    section_ordinal: int
    ordinal: int
    heading: str
    location: str
    text: str
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True, slots=True)
class _Unit:
    start: int
    end: int
    tokens: int
    is_heading: bool
    path: tuple[str, ...]


def chunk_document(
    parsed: ParsedDocument, counter: TokenCounter, *, target: int, overlap: int
) -> tuple[list[SectionDraft], list[ChunkDraft]]:
    sections: list[SectionDraft] = []
    chunks: list[ChunkDraft] = []
    for index, section in enumerate(parsed.sections):
        text = section.text
        sections.append(
            SectionDraft(index, section.kind.value, section.label, text, counter.count(text))
        )
        for start, end, heading in _pack(_units(section, counter, target), target, overlap):
            body = text[start:end]
            chunks.append(
                ChunkDraft(
                    section_ordinal=index,
                    ordinal=len(chunks),
                    heading=heading,
                    location=section.label,
                    text=body,
                    char_start=start,
                    char_end=end,
                    token_count=counter.count(body),
                )
            )
    return sections, chunks


def _units(section: ParsedSection, counter: TokenCounter, target: int) -> list[_Unit]:
    units: list[_Unit] = []
    stack: list[tuple[int, str]] = []
    offset = 0
    for block in section.blocks:
        start, end = offset, offset + len(block.text)
        offset = end + len(BLOCK_SEPARATOR)
        if block.heading_level is not None:
            while stack and stack[-1][0] >= block.heading_level:
                stack.pop()
            stack.append((block.heading_level, block.text))
            path = tuple(title for _, title in stack)
            units.append(_Unit(start, end, counter.count(block.text), True, path))
            continue
        path = tuple(title for _, title in stack)
        tokens = counter.count(block.text)
        if tokens <= target:
            units.append(_Unit(start, end, tokens, False, path))
            continue
        for s_start, s_end in sentence_spans(block.text) or [(0, len(block.text))]:
            sentence = block.text[s_start:s_end]
            s_tokens = counter.count(sentence)
            if s_tokens <= target:
                units.append(_Unit(start + s_start, start + s_end, s_tokens, False, path))
            else:
                units.extend(_word_windows(sentence, start + s_start, counter, target, path))
    return units


def _word_windows(
    text: str, base: int, counter: TokenCounter, target: int, path: tuple[str, ...]
) -> Iterator[_Unit]:
    words = list(_WORD.finditer(text))
    per_window = max(8, int(target * 0.7))
    for i in range(0, len(words), per_window):
        group = words[i : i + per_window]
        start, end = group[0].start(), group[-1].end()
        yield _Unit(base + start, base + end, counter.count(text[start:end]), False, path)


def _pack(units: list[_Unit], target: int, overlap: int) -> Iterator[tuple[int, int, str]]:
    i, n = 0, len(units)
    while i < n:
        j, total = i, 0
        while j < n and (j == i or total + units[j].tokens <= target):
            total += units[j].tokens
            j += 1
        while j - 1 > i and units[j - 1].is_heading:
            j -= 1
        window = units[i:j]
        body = next((u for u in window if not u.is_heading), window[-1])
        yield window[0].start, window[-1].end, " > ".join(body.path)
        if j >= n:
            break
        back, carried = j, 0
        while (
            back - 1 > i
            and not units[back - 1].is_heading
            and carried + units[back - 1].tokens <= overlap
        ):
            back -= 1
            carried += units[back].tokens
        i = back
