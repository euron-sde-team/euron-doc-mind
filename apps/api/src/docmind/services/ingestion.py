"""The ingestion pipeline: fetch, parse, chunk, embed, and swap in atomically.

Runs in the worker (SQS) or in the API process (inline queue). Idempotent: a duplicate
message for a document that is already ready is a no-op, and the new sections and chunks
replace the old ones in one transaction, so readers never see a half-indexed document.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import anyio
import numpy as np

from docmind.core import metrics
from docmind.core.logging import get_logger
from docmind.core.text import normalize
from docmind.ingestion.chunker import chunk_document
from docmind.ingestion.parsers.registry import parse
from docmind.ingestion.sniff import title_from_filename
from docmind.ingestion.types import ParseError, ParseLimits
from docmind.integrations.queue import IngestJob
from docmind.models import Workspace
from docmind.models.enums import DocumentKind, DocumentStatus
from docmind.repositories.documents import DocumentRepository
from docmind.repositories.workspaces import WorkspaceRepository
from docmind.schemas.workspaces import WorkspaceSettings
from docmind.services.container import Container

log = get_logger("docmind.ingestion")
EMBED_BATCH = 256
MAX_ATTEMPTS = 3


class Outcome(StrEnum):
    DONE = "done"
    RETRY = "retry"


class IngestionService:
    def __init__(self, container: Container) -> None:
        self.c = container
        settings = container.settings
        self.limits = ParseLimits(
            max_pages=settings.max_document_pages,
            max_uncompressed_bytes=settings.max_uncompressed_mb * 1024 * 1024,
        )

    async def process(self, job: IngestJob, *, final_attempt: bool = True) -> Outcome:
        async with self.c.db.session() as session:
            documents = DocumentRepository(session)
            document = await documents.get_for_update(job.workspace_id, job.document_id)
            if document is None:
                return Outcome.DONE  # deleted while queued
            if document.status == DocumentStatus.READY:
                return Outcome.DONE  # duplicate delivery
            workspace = await session.get(Workspace, job.workspace_id)
            prefs = WorkspaceSettings.model_validate(workspace.settings if workspace else {})
            document.status = DocumentStatus.PROCESSING
            document.attempts += 1
            document.error = None
            kind, key, filename = (
                DocumentKind(document.kind),
                document.storage_key,
                document.filename,
            )
            title = document.title
            await session.commit()

        settings = self.c.settings
        target = prefs.chunk_tokens or settings.chunk_tokens
        overlap = (
            prefs.chunk_overlap_tokens
            if prefs.chunk_overlap_tokens is not None
            else settings.chunk_overlap_tokens
        )
        started = time.perf_counter()
        try:
            with anyio.fail_after(settings.ingest_timeout_s):
                data = await self.c.storage.get(key)
                parsed = await anyio.to_thread.run_sync(parse, kind, data, self.limits)
                sections, chunks = await anyio.to_thread.run_sync(
                    lambda: chunk_document(
                        parsed, self.c.tokens, target=target, overlap=min(overlap, target // 2)
                    )
                )
                if not chunks:
                    raise ParseError("No text could be indexed from this file.")
                parsed_title = normalize(parsed.title or "")
                if (
                    parsed_title
                    and 3 <= len(parsed_title) <= 200
                    and title == title_from_filename(filename)
                ):
                    title = parsed_title
                # Contextual embeddings: each chunk carries its document title and heading, so
                # "what is new in release 4.2" finds the NEW section of the 4.2 release notes.
                texts = [
                    f"{title}\n{c.heading}\n{c.text}" if c.heading else f"{title}\n{c.text}"
                    for c in chunks
                ]
                vectors = [
                    await self.c.embedder.embed_documents(texts[i : i + EMBED_BATCH])
                    for i in range(0, len(texts), EMBED_BATCH)
                ]
                embeddings = (
                    np.concatenate(vectors) if vectors else np.zeros((0, 0), dtype=np.float32)
                )
                hashes = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        except ParseError as exc:
            await self._fail(job, str(exc), kind)
            return Outcome.DONE
        except TimeoutError:
            await self._fail(job, "Processing took too long and was stopped.", kind)
            return Outcome.DONE
        except Exception:
            log.exception("ingest_error", document_id=str(job.document_id))
            if final_attempt:
                await self._fail(job, "Processing failed. Try reprocessing the document.", kind)
                return Outcome.DONE
            await self._requeue(job)
            return Outcome.RETRY

        async with self.c.db.session() as session:
            documents = DocumentRepository(session)
            document = await documents.get_for_update(job.workspace_id, job.document_id)
            if document is None:
                return Outcome.DONE
            await documents.replace_content(document, sections, chunks, embeddings, hashes)
            document.title = title
            document.status = DocumentStatus.READY
            document.section_count = len(sections)
            document.chunk_count = len(chunks)
            document.token_count = sum(s.token_count for s in sections)
            document.warnings = [{"code": "parse_warning", "message": w} for w in parsed.warnings]
            document.processed_at = datetime.now(UTC)
            await WorkspaceRepository(session).bump_corpus_version(job.workspace_id)
            await session.commit()

        elapsed = time.perf_counter() - started
        metrics.INGESTED_DOCUMENTS.labels(kind.value, "ready").inc()
        metrics.INGEST_DURATION.labels(kind.value).observe(elapsed)
        log.info(
            "ingested",
            document_id=str(job.document_id),
            kind=kind.value,
            sections=len(sections),
            chunks=len(chunks),
            seconds=round(elapsed, 2),
        )
        return Outcome.DONE

    async def _fail(self, job: IngestJob, message: str, kind: DocumentKind) -> None:
        metrics.INGESTED_DOCUMENTS.labels(kind.value, "failed").inc()
        log.info("ingest_failed", document_id=str(job.document_id), reason=message)
        async with self.c.db.session() as session:
            await DocumentRepository(session).mark(
                job.document_id, status=DocumentStatus.FAILED, error=message
            )
            await session.commit()

    async def _requeue(self, job: IngestJob) -> None:
        async with self.c.db.session() as session:
            await DocumentRepository(session).mark(job.document_id, status=DocumentStatus.QUEUED)
            await session.commit()

    async def reap_stale(self) -> int:
        """Re-enqueue documents stuck unfinished (a lost message, a killed worker)."""
        cutoff = datetime.now(UTC) - timedelta(minutes=self.c.settings.stale_processing_minutes)
        async with self.c.db.session() as session:
            documents = DocumentRepository(session)
            stale = await documents.unfinished_before(cutoff)
            requeue = []
            for document in stale:
                if document.attempts >= MAX_ATTEMPTS:
                    document.status = DocumentStatus.FAILED
                    document.error = "Processing did not finish after several attempts."
                else:
                    document.status = DocumentStatus.QUEUED
                    requeue.append(IngestJob(document.workspace_id, document.id))
            await session.commit()
        for job in requeue:
            await self.c.queue.enqueue(job)
        if stale:
            log.info("reaped_stale_documents", count=len(stale), requeued=len(requeue))
        return len(stale)
