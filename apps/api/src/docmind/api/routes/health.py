"""Probes, metrics and public deployment info."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from docmind import __version__
from docmind.api.deps import ContainerDep, SessionDep
from docmind.core.logging import get_logger
from docmind.ingestion.sniff import EXTENSIONS
from docmind.repositories.users import UserRepository
from docmind.schemas.system import GeneratorInfo, SystemInfo

router = APIRouter()
log = get_logger("docmind.health")


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(container: ContainerDep) -> JSONResponse:
    checks: dict[str, Any] = {}
    for name, probe in (
        ("database", container.db.ping),
        ("redis", container.redis.ping),
        ("storage", container.storage.check),
        ("queue", container.queue.check),
    ):
        try:
            await probe()
            checks[name] = "ok"
        except Exception as exc:
            log.warning("readiness_check_failed", check=name, error=type(exc).__name__)
            checks[name] = "failing"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/system/info", tags=["system"], summary="Deployment capabilities and limits")
async def system_info(container: ContainerDep, session: SessionDep) -> SystemInfo:
    settings = container.settings
    client = container.chat_client
    return SystemInfo(
        product_name=settings.product_name,
        version=__version__,
        generator=GeneratorInfo(
            label=container.generator.label,
            provider=client.provider if client else "extractive",
            model=client.model if client else None,
            uses_model=container.generator.uses_model,
        ),
        embeddings=container.embedder.name,
        embedding_dim=settings.embedding_dim,
        tokenizer=container.tokens.name,
        max_upload_mb=settings.max_upload_mb,
        accepted_extensions=sorted(EXTENSIONS),
        allow_signup=settings.allow_signup,
        needs_setup=await UserRepository(session).count() == 0,
    )
