"""Decide what an upload is from its name *and* its bytes.

The extension picks the parser; the magic bytes must agree, so a renamed executable or a
mislabeled file is refused before any parser sees it.
"""

from __future__ import annotations

from pathlib import PurePath

from docmind.core.errors import UnsupportedMediaTypeError
from docmind.models.enums import DocumentKind

EXTENSIONS: dict[str, DocumentKind] = {
    ".pdf": DocumentKind.PDF,
    ".docx": DocumentKind.DOCX,
    ".xlsx": DocumentKind.XLSX,
    ".csv": DocumentKind.CSV,
    ".pptx": DocumentKind.PPTX,
    ".txt": DocumentKind.TXT,
    ".md": DocumentKind.MD,
    ".markdown": DocumentKind.MD,
    ".html": DocumentKind.HTML,
    ".htm": DocumentKind.HTML,
}

MIME_TYPES: dict[DocumentKind, str] = {
    DocumentKind.PDF: "application/pdf",
    DocumentKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    DocumentKind.CSV: "text/csv",
    DocumentKind.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    DocumentKind.TXT: "text/plain",
    DocumentKind.MD: "text/markdown",
    DocumentKind.HTML: "text/html",
}

_OOXML = {DocumentKind.DOCX, DocumentKind.XLSX, DocumentKind.PPTX}
_TEXT = {DocumentKind.CSV, DocumentKind.TXT, DocumentKind.MD, DocumentKind.HTML}
SUPPORTED_LABEL = (
    "PDF, Word (.docx), Excel (.xlsx), CSV, PowerPoint (.pptx), text, Markdown or HTML"
)


def detect_kind(filename: str, head: bytes) -> DocumentKind:
    suffix = PurePath(filename).suffix.lower()
    kind = EXTENSIONS.get(suffix)
    if kind is None:
        raise UnsupportedMediaTypeError(
            f"{suffix or 'Files without an extension'} is not supported. Upload {SUPPORTED_LABEL}."
        )
    if not _content_matches(kind, head):
        raise UnsupportedMediaTypeError(
            f"The file's content does not match its {suffix} extension.",
            code="content_mismatch",
        )
    return kind


def _content_matches(kind: DocumentKind, head: bytes) -> bool:
    if kind is DocumentKind.PDF:
        return b"%PDF-" in head[:1024]
    if kind in _OOXML:
        return head[:4] == b"PK\x03\x04"
    if kind in _TEXT:
        if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return True  # UTF-16 text legitimately contains NUL bytes
        return b"\x00" not in head[:8192]
    return False


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename).stem.replace("_", " ").strip()
    return stem or "Untitled document"
