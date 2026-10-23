import itertools

from docmind.ai.tokens import TokenCounter
from docmind.ingestion.chunker import chunk_document
from docmind.ingestion.parsers.registry import parse
from docmind.ingestion.types import Block, ParsedDocument, ParsedSection, ParseLimits
from docmind.models.enums import DocumentKind, SectionKind
from tests.conftest import sample_bytes

COUNTER = TokenCounter("heuristic")


def _doc(*sections: ParsedSection) -> ParsedDocument:
    return ParsedDocument(title=None, sections=list(sections))


def test_chunks_are_exact_slices_of_their_section() -> None:
    for name, kind in (
        ("Northwind Employee Handbook 2026.pdf", DocumentKind.PDF),
        ("Q3 2026 Board Update.pptx", DocumentKind.PPTX),
        ("FY2027 Operating Budget.xlsx", DocumentKind.XLSX),
    ):
        parsed = parse(kind, sample_bytes(name), ParseLimits())
        sections, chunks = chunk_document(parsed, COUNTER, target=120, overlap=20)
        texts = {s.ordinal: s.text for s in sections}
        assert chunks, name
        for chunk in chunks:
            assert texts[chunk.section_ordinal][chunk.char_start : chunk.char_end] == chunk.text


def test_chunks_never_cross_sections_and_are_numbered() -> None:
    doc = _doc(
        ParsedSection(SectionKind.PAGE, "Page 1", [Block("Alpha sentence one. " * 40)]),
        ParsedSection(SectionKind.PAGE, "Page 2", [Block("Beta sentence two. " * 40)]),
    )
    _, chunks = chunk_document(doc, COUNTER, target=60, overlap=10)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert {c.location for c in chunks if "Alpha" in c.text} == {"Page 1"}
    assert {c.location for c in chunks if "Beta" in c.text} == {"Page 2"}


def test_targets_are_respected_and_consecutive_chunks_overlap() -> None:
    text = " ".join(f"Sentence number {i} carries a little bit of meaning." for i in range(60))
    doc = _doc(ParsedSection(SectionKind.SECTION, "Body", [Block(text)]))
    _, chunks = chunk_document(doc, COUNTER, target=80, overlap=20)
    assert len(chunks) > 3
    assert all(c.token_count <= 80 for c in chunks)
    for previous, current in itertools.pairwise(chunks):
        assert current.char_start < previous.char_end, "consecutive chunks should overlap"


def test_a_heading_never_ends_a_chunk_and_names_the_text_below() -> None:
    blocks = [Block("Intro paragraph that is long enough. " * 6), Block("Leave", heading_level=2)]
    blocks += [Block("Employees receive 24 days of annual leave every year, accrued monthly.")]
    doc = _doc(ParsedSection(SectionKind.SECTION, "Handbook", blocks))
    _, chunks = chunk_document(doc, COUNTER, target=60, overlap=0)
    leave = next(c for c in chunks if "24 days" in c.text)
    assert leave.text.startswith("Leave")
    assert leave.heading == "Leave"
    assert all(not c.text.rstrip().endswith("Leave") for c in chunks if c is not leave)


def test_huge_sentences_fall_back_to_word_windows() -> None:
    sentence = "word " * 1000
    doc = _doc(ParsedSection(SectionKind.SECTION, "Body", [Block(sentence.strip())]))
    _, chunks = chunk_document(doc, COUNTER, target=100, overlap=0)
    assert len(chunks) >= 8
    assert all(c.token_count <= 110 for c in chunks)
