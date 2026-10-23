from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, or_, select, update

from docmind.ingestion.chunker import ChunkDraft, SectionDraft
from docmind.models import Chunk, Document, DocumentSection
from docmind.models.enums import DocumentStatus
from docmind.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class LibraryStats:
    by_status: dict[str, int]
    ready_tokens: int
    ready_chunks: int
    total_bytes: int


class DocumentRepository(Repository):
    async def get(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id, Document.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .where(Document.id == document_id, Document.workspace_id == workspace_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def by_sha(self, workspace_id: uuid.UUID, sha256: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.workspace_id == workspace_id, Document.sha256 == sha256)
        )
        return result.scalar_one_or_none()

    async def add(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
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
        conditions: list[Any] = [Document.workspace_id == workspace_id]
        if status:
            conditions.append(Document.status == status)
        if kind:
            conditions.append(Document.kind == kind)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(or_(Document.title.ilike(pattern), Document.filename.ilike(pattern)))
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total

    async def stats(self, workspace_id: uuid.UUID) -> LibraryStats:
        rows = await self.session.execute(
            select(
                Document.status,
                func.count(),
                func.coalesce(func.sum(Document.token_count), 0),
                func.coalesce(func.sum(Document.chunk_count), 0),
                func.coalesce(func.sum(Document.size_bytes), 0),
            )
            .where(Document.workspace_id == workspace_id)
            .group_by(Document.status)
        )
        by_status: dict[str, int] = {}
        ready_tokens = ready_chunks = total_bytes = 0
        for status, count, tokens, chunks, size in rows.all():
            by_status[status] = int(count)
            total_bytes += int(size)
            if status == DocumentStatus.READY:
                ready_tokens, ready_chunks = int(tokens), int(chunks)
        return LibraryStats(by_status, ready_tokens, ready_chunks, total_bytes)

    async def ready_token_total(
        self, workspace_id: uuid.UUID, document_ids: Sequence[uuid.UUID] | None = None
    ) -> int:
        conditions: list[Any] = [
            Document.workspace_id == workspace_id,
            Document.status == DocumentStatus.READY,
        ]
        if document_ids:
            conditions.append(Document.id.in_(document_ids))
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Document.token_count), 0)).where(*conditions)
            )
            or 0
        )

    async def ready_ids(self, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(Document.id).where(
                Document.workspace_id == workspace_id,
                Document.id.in_(ids),
                Document.status == DocumentStatus.READY,
            )
        )
        return list(result.scalars())

    async def titles(
        self, workspace_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        result = await self.session.execute(
            select(Document.id, Document.title).where(
                Document.workspace_id == workspace_id, Document.id.in_(ids)
            )
        )
        return {row.id: row.title for row in result.all()}

    async def sections(self, document_id: uuid.UUID) -> list[DocumentSection]:
        result = await self.session.execute(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.ordinal)
        )
        return list(result.scalars())

    async def replace_content(
        self,
        document: Document,
        sections: Sequence[SectionDraft],
        chunks: Sequence[ChunkDraft],
        embeddings: Any,
        content_hashes: Sequence[str],
    ) -> None:
        """Swap a document's sections and chunks in the caller's transaction."""
        await self.session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        await self.session.execute(
            delete(DocumentSection).where(DocumentSection.document_id == document.id)
        )
        if sections:
            await self.session.execute(
                insert(DocumentSection),
                [
                    {
                        "document_id": document.id,
                        "ordinal": s.ordinal,
                        "kind": s.kind,
                        "label": s.label,
                        "text": s.text,
                        "token_count": s.token_count,
                    }
                    for s in sections
                ],
            )
        if chunks:
            await self.session.execute(
                insert(Chunk),
                [
                    {
                        "workspace_id": document.workspace_id,
                        "document_id": document.id,
                        "section_ordinal": c.section_ordinal,
                        "ordinal": c.ordinal,
                        "heading": c.heading,
                        "location": c.location,
                        "text": c.text,
                        "char_start": c.char_start,
                        "char_end": c.char_end,
                        "token_count": c.token_count,
                        "content_hash": content_hashes[i],
                        "embedding": embeddings[i],
                    }
                    for i, c in enumerate(chunks)
                ],
            )

    async def unfinished_before(
        self, cutoff: datetime, statuses: Sequence[DocumentStatus], limit: int = 100
    ) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.status.in_(list(statuses)), Document.updated_at < cutoff)
            .order_by(Document.updated_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def ids_in_workspace(self, workspace_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        result = await self.session.execute(
            select(Document.id, Document.storage_key).where(Document.workspace_id == workspace_id)
        )
        return [(row.id, row.storage_key) for row in result.all()]

    async def mark(self, document_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
