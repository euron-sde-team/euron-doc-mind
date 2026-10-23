"""Every parser against the sample corpus, plus the edge cases that matter."""

import io

import pytest
from pypdf import PdfWriter

from docmind.ingestion.parsers.common import (
    blocks_from_layout,
    blocks_from_text,
    looks_like_heading,
)
from docmind.ingestion.parsers.registry import parse
from docmind.ingestion.parsers.sheets import format_value
from docmind.ingestion.types import ParseError, ParseLimits
from docmind.models.enums import DocumentKind, SectionKind
from tests.conftest import sample_bytes

LIMITS = ParseLimits()


def _headings(doc: object) -> list[str]:
    return [b.text for s in doc.sections for b in s.blocks if b.heading_level]  # type: ignore[attr-defined]


def _blocks(doc: object) -> list[str]:
    return [b.text for s in doc.sections for b in s.blocks]  # type: ignore[attr-defined]


def test_pdf_pages_headings_and_tables() -> None:
    doc = parse(DocumentKind.PDF, sample_bytes("Northwind Employee Handbook 2026.pdf"), LIMITS)
    assert doc.title == "Northwind Employee Handbook 2026"
    assert [s.label for s in doc.sections][:2] == ["Page 1", "Page 2"]
    assert all(s.kind is SectionKind.PAGE for s in doc.sections)
    assert {"Remote work", "Time off", "Travel and expenses", "Equipment and learning"} <= set(
        _headings(doc)
    )
    assert (
        "Item: Hotel per night; United States: $220; Europe: 180 euros; India: 9,000 rupees"
        in _blocks(doc)
    )
    assert any(
        text.startswith("\N{BULLET} Meals: a daily meal allowance of $75") for text in _blocks(doc)
    )


def test_pdf_numbered_and_wrapped_headings() -> None:
    doc = parse(DocumentKind.PDF, sample_bytes("Globex Master Services Agreement.pdf"), LIMITS)
    headings = _headings(doc)
    assert headings[0] == "Master Services Agreement: Northwind Robotics and Globex Corporation"
    assert {"4. Service levels", "5. Termination"} <= set(headings)
    assert (
        "Priority: P1; Definition: Fleet stopped at a site; Response: 15 minutes, 24/7; Target resolution: 4 hours"
        in _blocks(doc)
    )


def test_pdf_without_text_explains_ocr() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ParseError, match="OCR"):
        parse(DocumentKind.PDF, buffer.getvalue(), LIMITS)


def test_encrypted_pdf_is_refused() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret", owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ParseError, match="password"):
        parse(DocumentKind.PDF, buffer.getvalue(), LIMITS)


def test_pdf_page_limit() -> None:
    with pytest.raises(ParseError, match="limit"):
        parse(
            DocumentKind.PDF,
            sample_bytes("Northwind Employee Handbook 2026.pdf"),
            ParseLimits(max_pages=2),
        )


def test_docx_sections_tables_and_lists() -> None:
    doc = parse(DocumentKind.DOCX, sample_bytes("Atlas v2 Product Requirements.docx"), LIMITS)
    assert doc.title == "Atlas v2 Product Requirements"
    assert [s.label for s in doc.sections][1:4] == [
        "Overview",
        "Personas",
        "Functional requirements",
    ]
    assert (
        "ID: FR-2; Requirement: Battery life; Target: 10 hours of continuous operation on one charge"
        in _blocks(doc)
    )
    assert any(
        text.startswith("\N{BULLET} Safety: certified to ISO 3691-4") for text in _blocks(doc)
    )


def test_xlsx_one_section_per_sheet_with_formats() -> None:
    doc = parse(DocumentKind.XLSX, sample_bytes("FY2027 Operating Budget.xlsx"), LIMITS)
    assert [s.label for s in doc.sections] == [
        "Sheet: Summary",
        "Sheet: Opex by department",
        "Sheet: Headcount plan",
        "Sheet: Capex",
    ]
    blocks = _blocks(doc)
    assert "Metric: Gross margin; FY2026 forecast: 60.0%; FY2027 budget: 63.0%" in blocks
    assert (
        "Department: Marketing; FY2026 forecast: $4,900,000; FY2027 budget: $6,800,000; Change: 38.8%"
        in blocks
    )


def test_csv_rows_become_records() -> None:
    doc = parse(DocumentKind.CSV, sample_bytes("warehouse-pilot-results.csv"), LIMITS)
    assert doc.sections[0].blocks[0].text.startswith("Columns: Site, Region")
    assert any(b.text.startswith("Site: Rotterdam; Region: Europe") for b in doc.sections[0].blocks)


def test_csv_row_limit_warns() -> None:
    doc = parse(
        DocumentKind.CSV,
        sample_bytes("warehouse-pilot-results.csv"),
        ParseLimits(max_rows_per_sheet=2),
    )
    assert doc.warnings
    assert "first 2 rows" in doc.warnings[0]


def test_pptx_slides_tables_and_speaker_notes() -> None:
    doc = parse(DocumentKind.PPTX, sample_bytes("Q3 2026 Board Update.pptx"), LIMITS)
    labels = [s.label for s in doc.sections]
    assert labels[0] == "Slide 1: Q3 2026 Board Update"
    assert "Slide 8: Key risks" in labels
    blocks = _blocks(doc)
    assert "Segment: Total; Q3 2026 revenue: $18.4M; Year over year: +32%" in blocks
    assert any(b.startswith("Speaker notes: The LiDAR risk is the most urgent") for b in blocks)


def test_markdown_sections_and_tables() -> None:
    doc = parse(DocumentKind.MD, sample_bytes("Security Incident Response Runbook.md"), LIMITS)
    assert doc.title == "Security Incident Response Runbook"
    assert "Severity levels" in [s.label for s in doc.sections]
    assert any(
        b.startswith("Severity: SEV1; Examples: Customer data exposed") for b in _blocks(doc)
    )


def test_html_drops_chrome_and_keeps_questions_as_sections() -> None:
    doc = parse(DocumentKind.HTML, sample_bytes("Customer Support FAQ.html"), LIMITS)
    assert doc.title == "Atlas Customer Support FAQ"
    assert "How do I reset an Atlas robot?" in [s.label for s in doc.sections]


def test_html_scripts_are_never_indexed() -> None:
    html = b"<html><body><script>alert('x')</script><h1>Title</h1><p>Visible text here.</p></body></html>"
    doc = parse(DocumentKind.HTML, html, LIMITS)
    assert "alert" not in " ".join(_blocks(doc))


def test_plain_text_all_caps_headings() -> None:
    doc = parse(DocumentKind.TXT, sample_bytes("Release notes 4.2.txt"), LIMITS)
    assert [s.label for s in doc.sections][1:4] == ["NEW", "IMPROVED", "FIXED"]


def test_empty_text_file_is_refused() -> None:
    with pytest.raises(ParseError):
        parse(DocumentKind.TXT, b"   \n\n  ", LIMITS)


def test_heading_heuristics() -> None:
    assert looks_like_heading("Travel and expenses")
    assert looks_like_heading("4. Service levels")
    assert not looks_like_heading("This is a sentence that ends.")
    assert not looks_like_heading("- a bullet item")


def test_blocks_from_text_rejoins_hyphenation_and_splits_bullets() -> None:
    blocks = blocks_from_text(
        "The budget for engi-\nneering grows.\n\N{BULLET} First item\n\N{BULLET} Second item"
    )
    assert [b.text for b in blocks] == [
        "The budget for engineering grows.",
        "\N{BULLET} First item",
        "\N{BULLET} Second item",
    ]


def test_layout_tables_survive_blank_lines_between_rows() -> None:
    raw = "Intro paragraph here.\n  Name    Role    Team\n\n  Ava    Owner    Ops\n\n  Leo    Editor    Eng\nAfter."
    texts = [b.text for b in blocks_from_layout(raw)]
    assert "Name: Ava; Role: Owner; Team: Ops" in texts
    assert "Name: Leo; Role: Editor; Team: Eng" in texts


@pytest.mark.parametrize(
    ("value", "fmt", "expected"),
    [
        (0.388, "0.0%", "38.8%"),
        (6800000, '"$"#,##0', "$6,800,000"),
        (48, "General", "48"),
        (12500, "General", "12,500"),
    ],
)
def test_spreadsheet_number_formats(value: float, fmt: str, expected: str) -> None:
    assert format_value(value, fmt) == expected
