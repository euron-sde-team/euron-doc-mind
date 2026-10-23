from __future__ import annotations

from fastapi import APIRouter, Depends

from docmind.api.deps import ContainerDep, SessionDep, ViewerDep, rate_limit
from docmind.schemas.search import SearchHit, SearchOut, SearchRequest
from docmind.services.search import SearchService

router = APIRouter(prefix="/api/v1/workspaces/{workspace}", tags=["search"])


@router.post(
    "/search",
    summary="Hybrid search: meaning and keywords, ranked together",
    dependencies=[Depends(rate_limit("chat", "rate_limit_chat"))],
)
async def search(
    body: SearchRequest, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> SearchOut:
    hits, took_ms = await SearchService(container, session).search(
        ctx.workspace, ctx.principal, body.query, body.document_ids, body.limit
    )
    return SearchOut(
        query=body.query, hits=[SearchHit.model_validate(h) for h in hits], took_ms=took_ms
    )
