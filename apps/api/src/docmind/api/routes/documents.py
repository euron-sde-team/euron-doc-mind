"""Upload, list, read, download, rename, reprocess and delete documents."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from docmind.api.deps import ContainerDep, EditorDep, SessionDep, ViewerDep, rate_limit
from docmind.core.errors import UnprocessableError
from docmind.schemas.documents import (
    DocumentDetail,
    DocumentOut,
    DocumentPage,
    DocumentUpdate,
    LibraryStats,
    RejectedFile,
    SectionOut,
    UploadResult,
)
from docmind.services.documents import DocumentService, IncomingFile

router = APIRouter(prefix="/api/v1/workspaces/{workspace}/documents", tags=["documents"])
MAX_FILES_PER_REQUEST = 20


@router.get("", summary="The document library")
async def list_documents(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(queued|processing|ready|failed)$")
    ] = None,
    kind: Annotated[str | None, Query(pattern="^(pdf|docx|xlsx|csv|pptx|txt|md|html)$")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    items, total = await DocumentService(container, session).page(
        ctx.id, status=status_filter, kind=kind, query=q, limit=limit, offset=offset
    )
    return DocumentPage(
        items=[DocumentOut.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", summary="Counts, tokens and bytes in the library")
async def library_stats(
    ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> LibraryStats:
    stats = await DocumentService(container, session).stats(ctx.id)
    return LibraryStats(
        documents=sum(stats.by_status.values()),
        ready=stats.by_status.get("ready", 0),
        processing=stats.by_status.get("processing", 0) + stats.by_status.get("queued", 0),
        failed=stats.by_status.get("failed", 0),
        chunks=stats.ready_chunks,
        tokens=stats.ready_tokens,
        bytes=stats.total_bytes,
    )


@router.post(
    "",
    summary="Upload files (PDF, Word, Excel, CSV, PowerPoint, text, Markdown, HTML)",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", "rate_limit_upload"))],
)
async def upload_documents(
    ctx: EditorDep,
    container: ContainerDep,
    session: SessionDep,
    files: Annotated[
        list[UploadFile], File(description="One or more files, up to 20 per request.")
    ],
) -> UploadResult:
    if len(files) > MAX_FILES_PER_REQUEST:
        raise UnprocessableError(f"Upload at most {MAX_FILES_PER_REQUEST} files at a time.")
    limit = container.settings.max_upload_bytes
    incoming = []
    for upload in files:
        # Read one byte past the limit: enough to know the file is too large, never more.
        data = await upload.read(limit + 1)
        incoming.append(IncomingFile(filename=upload.filename or "upload", data=data))
        await upload.close()
    outcome = await DocumentService(container, session).upload(
        ctx.workspace, ctx.principal, incoming
    )
    return UploadResult(
        created=[DocumentOut.model_validate(d) for d in outcome.created],
        duplicates=[DocumentOut.model_validate(d) for d in outcome.duplicates],
        rejected=[RejectedFile(filename=f, code=c, message=m) for f, c, m in outcome.rejected],
    )


@router.get("/{document_id}", summary="A document with its parsed sections")
async def get_document(
    document_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> DocumentDetail:
    service = DocumentService(container, session)
    document = await service.get(ctx.id, document_id)
    sections = await service.sections(document)
    return DocumentDetail.model_validate(
        {
            **DocumentOut.model_validate(document).model_dump(),
            "sections": [SectionOut.model_validate(s) for s in sections],
        }
    )


@router.get(
    "/{document_id}/file", summary="Download the original file", response_class=StreamingResponse
)
async def download_document(
    document_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> StreamingResponse:
    service = DocumentService(container, session)
    document = await service.get(ctx.id, document_id)
    disposition = f"attachment; filename*=UTF-8''{quote(document.filename)}"
    return StreamingResponse(
        service.download(document),
        media_type=document.mime_type,
        headers={"content-disposition": disposition, "content-length": str(document.size_bytes)},
    )


@router.patch("/{document_id}", summary="Rename a document")
async def rename_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    ctx: EditorDep,
    container: ContainerDep,
    session: SessionDep,
) -> DocumentOut:
    service = DocumentService(container, session)
    document = await service.rename(
        ctx.workspace, ctx.principal, await service.get(ctx.id, document_id), body.title
    )
    return DocumentOut.model_validate(document)


@router.post("/{document_id}/reprocess", summary="Parse and index the document again")
async def reprocess_document(
    document_id: uuid.UUID, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> DocumentOut:
    service = DocumentService(container, session)
    document = await service.reprocess(
        ctx.workspace, ctx.principal, await service.get(ctx.id, document_id)
    )
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", summary="Delete a document and its index", status_code=204)
async def delete_document(
    document_id: uuid.UUID, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = DocumentService(container, session)
    await service.delete(ctx.workspace, ctx.principal, await service.get(ctx.id, document_id))
