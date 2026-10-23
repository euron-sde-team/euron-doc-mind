"""Value sets stored as text with CHECK constraints (cheaper to evolve than Postgres enums)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {Role.VIEWER: 1, Role.EDITOR: 2, Role.OWNER: 3}[self]

    def allows(self, required: Role) -> bool:
        return self.rank >= required.rank


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    PPTX = "pptx"
    TXT = "txt"
    MD = "md"
    HTML = "html"


class SectionKind(StrEnum):
    PAGE = "page"
    SLIDE = "slide"
    SHEET = "sheet"
    SECTION = "section"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class CacheResult(StrEnum):
    MISS = "miss"
    EXACT = "exact"
    SEMANTIC = "semantic"


class UsageKind(StrEnum):
    ANSWER = "answer"
    SEARCH = "search"
