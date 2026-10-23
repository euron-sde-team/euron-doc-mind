import io
import zipfile

import pytest

from docmind.core.errors import UnsupportedMediaTypeError
from docmind.ingestion.archive import check_ooxml
from docmind.ingestion.sniff import detect_kind, title_from_filename
from docmind.ingestion.types import ParseError
from docmind.models.enums import DocumentKind
from tests.conftest import sample_bytes


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Northwind Employee Handbook 2026.pdf", DocumentKind.PDF),
        ("Atlas v2 Product Requirements.docx", DocumentKind.DOCX),
        ("FY2027 Operating Budget.xlsx", DocumentKind.XLSX),
        ("Q3 2026 Board Update.pptx", DocumentKind.PPTX),
        ("warehouse-pilot-results.csv", DocumentKind.CSV),
        ("Release notes 4.2.txt", DocumentKind.TXT),
        ("Security Incident Response Runbook.md", DocumentKind.MD),
        ("Customer Support FAQ.html", DocumentKind.HTML),
    ],
)
def test_detects_every_supported_format(name: str, kind: DocumentKind) -> None:
    assert detect_kind(name, sample_bytes(name)[:8192]) is kind


def test_rejects_unknown_extensions() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind("setup.exe", b"MZ\x90\x00")


def test_rejects_content_that_does_not_match_the_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError) as caught:
        detect_kind("report.pdf", b"PK\x03\x04 actually a zip")
    assert caught.value.code == "content_mismatch"
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind("notes.txt", b"binary\x00\x01\x02")


def test_title_from_filename() -> None:
    assert title_from_filename("Q3_board_update.pptx") == "Q3 board update"


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_archive_guard_accepts_a_real_document() -> None:
    check_ooxml(
        sample_bytes("Atlas v2 Product Requirements.docx"),
        required_prefix="word/",
        label="Word document",
        max_uncompressed=50_000_000,
    )


def test_archive_guard_rejects_a_decompression_bomb() -> None:
    bomb = _zip({"[Content_Types].xml": b"x", "word/document.xml": b"0" * 5_000_000})
    with pytest.raises(ParseError, match="expands"):
        check_ooxml(bomb, required_prefix="word/", label="Word document", max_uncompressed=10**9)


def test_archive_guard_rejects_the_wrong_kind_of_office_file() -> None:
    sheet = _zip({"[Content_Types].xml": b"x", "xl/workbook.xml": b"<x/>"})
    with pytest.raises(ParseError, match="does not look like"):
        check_ooxml(sheet, required_prefix="word/", label="Word document", max_uncompressed=10**9)


def test_archive_guard_rejects_garbage() -> None:
    with pytest.raises(ParseError, match="not a valid"):
        check_ooxml(
            b"PK\x03\x04garbage",
            required_prefix="word/",
            label="Word document",
            max_uncompressed=10**9,
        )
