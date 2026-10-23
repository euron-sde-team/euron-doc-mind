"""Uploads, the document library, downloads, deletion and reprocessing."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import PurePath

from sqlalchemy.ext.asyncio import AsyncSession

from docmind.core.errors import AppError, NotFoundError
from docmind.core.ids import uuid7
from docmind.core.logging import get_logger
from docmind.ingestion.sniff import MIME_TYPES, detect_kind, title_from_filename
from docmind.integrations.queue import IngestJob
from docmind.integrations.storage import document_key
from docmind.models import Document, DocumentSection, Workspace
from docmind.models.enums import DocumentStatus
from docmind.repositories.documents import DocumentRepository, LibraryStats
from docmind.repositories.workspaces import WorkspaceRepository
from docmind.services import audit
from docmind.services.container import Container
from docmind.services.principal import Principal

log = get_logger("docmind.documents")


@dataclass(frozen=True, slots=True)
class IncomingFile:
    filename: str
    data: bytes


@dataclass(slots=True)
class UploadOutcome:
    created: list[Document] = field(default_factory=list)
    duplicates: list[Document] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)


def clean_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip() or "upload"
    return "".join(ch for ch in base if ch.isprintable())[:300]


class DocumentService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.documents = DocumentRepository(session)

    async def upload(
        self, workspace: Workspace, principal: Principal, files: list[IncomingFile]
    ) -> UploadOutcome:
        outcome = UploadOutcome()
        limit = self.c.settings.max_upload_bytes
        for incoming in files:
            filename = clean_filename(incoming.filename)
            try:
                if not incoming.data:
                    raise AppError("The file is empty.", code="empty_file")
                if len(incoming.data) > limit:
                    raise AppError(
                        f"The file is larger than {self.c.settings.max_upload_mb} MB.",
                        code="payload_too_large",
                    )
                kind = detect_kind(filename, incoming.data[:8192])
            except AppError as exc:
                outcome.rejected.append((filename, exc.code, exc.message))
                continue

            sha256 = hashlib.sha256(incoming.data).hexdigest()
            existing = await self.documents.by_sha(workspace.id, sha256)
            if existing is not None:
                outcome.duplicates.append(existing)
                continue

            document_id = uuid7()
            key = document_key(workspace.id, document_id, PurePath(filename).suffix.lower())
            await self.c.storage.put(key, incoming.data, MIME_TYPES[kind])
            document = await self.documents.add(
                Document(
                    id=document_id,
                    workspace_id=workspace.id,
                    title=title_from_filename(filename),
                    filename=filename,
                    kind=kind.value,
                    mime_type=MIME_TYPES[kind],
                    size_bytes=len(incoming.data),
                    sha256=sha256,
                    storage_key=key,
                    status=DocumentStatus.QUEUED,
                    uploaded_by=principal.user_id,
                )
            )
            await audit.record(
                self.session,
                workspace_id=workspace.id,
                principal=principal,
                action="document.uploaded",
                target_type="document",
                target_id=document.id,
                details={"filename": filename, "bytes": len(incoming.data)},
            )
            await self.session.commit()
            # After the commit: the worker must be able to read the row it is told about.
            # If this enqueue is lost, the stale-job reaper re-enqueues the document.
            await self.c.queue.enqueue(IngestJob(workspace.id, document.id))
            outcome.created.append(document)
        return outcome

    async def get(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self.documents.get(workspace_id, document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def page(
        self,
        workspace_id: uuid.UUID,
        *,
        status: str | None,
        kind: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        return await self.documents.page(
            workspace_id, status=status, kind=kind, query=query, limit=limit, offset=offset
        )

    async def stats(self, workspace_id: uuid.UUID) -> LibraryStats:
        return await self.documents.stats(workspace_id)

    async def sections(self, document: Document) -> list[DocumentSection]:
        return await self.documents.sections(document.id)

    async def rename(
        self, workspace: Workspace, principal: Principal, document: Document, title: str
    ) -> Document:
        document.title = title.strip()
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="document.renamed",
            target_type="document",
            target_id=document.id,
            details={"title": document.title},
        )
        await self.session.commit()
        return document

    def download(self, document: Document) -> AsyncIterator[bytes]:
        return self.c.storage.stream(document.storage_key)

    async def delete(self, workspace: Workspace, principal: Principal, document: Document) -> None:
        was_ready = document.status == DocumentStatus.READY
        key = document.storage_key
        await self.session.delete(document)
        if was_ready:
            await WorkspaceRepository(self.session).bump_corpus_version(workspace.id)
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="document.deleted",
            target_type="document",
            target_id=document.id,
            details={"filename": document.filename},
        )
        await self.session.commit()
        try:
            await self.c.storage.delete(key)
        except Exception:
            log.warning("storage_delete_failed", key=key)

    async def reprocess(
        self, workspace: Workspace, principal: Principal, document: Document
    ) -> Document:
        document.status = DocumentStatus.QUEUED
        document.error = None
        document.attempts = 0
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="document.reprocessed",
            target_type="document",
            target_id=document.id,
        )
        await self.session.commit()
        await self.c.queue.enqueue(IngestJob(workspace.id, document.id))
        return document
