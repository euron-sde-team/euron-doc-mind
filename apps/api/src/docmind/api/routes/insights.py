from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from docmind.api.deps import ContainerDep, SessionDep, ViewerDep
from docmind.schemas.insights import InsightsOut
from docmind.services.insights import InsightsService

router = APIRouter(prefix="/api/v1/workspaces/{workspace}", tags=["insights"])


@router.get("/insights", summary="Questions, tokens saved, cache hit rate and most-cited documents")
async def insights(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> InsightsOut:
    return InsightsOut.model_validate(
        await InsightsService(container, session).overview(ctx.workspace, days)
    )
