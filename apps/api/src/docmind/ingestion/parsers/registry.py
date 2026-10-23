from __future__ import annotations

from collections.abc import Callable

from docmind.ingestion.parsers.docx import parse_docx
from docmind.ingestion.parsers.pdf import parse_pdf
from docmind.ingestion.parsers.pptx import parse_pptx
from docmind.ingestion.parsers.sheets import parse_csv, parse_xlsx
from docmind.ingestion.parsers.text import parse_html, parse_markdown, parse_txt
from docmind.ingestion.types import ParsedDocument, ParseLimits
from docmind.models.enums import DocumentKind

Parser = Callable[[bytes, ParseLimits], ParsedDocument]

PARSERS: dict[DocumentKind, Parser] = {
    DocumentKind.PDF: parse_pdf,
    DocumentKind.DOCX: parse_docx,
    DocumentKind.XLSX: parse_xlsx,
    DocumentKind.CSV: parse_csv,
    DocumentKind.PPTX: parse_pptx,
    DocumentKind.TXT: parse_txt,
    DocumentKind.MD: parse_markdown,
    DocumentKind.HTML: parse_html,
}


def parse(kind: DocumentKind, data: bytes, limits: ParseLimits) -> ParsedDocument:
    return PARSERS[kind](data, limits)
