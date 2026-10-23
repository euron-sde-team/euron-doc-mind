"""Platform pieces against the real services: S3 with KMS, Valkey, Secrets Manager,
migrations and readiness."""

from __future__ import annotations

import asyncio
import json
import uuid

import asyncpg
import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from docmind.core.config import Settings
from docmind.core.errors import NotFoundError
from docmind.core.ratelimit import RateLimiter
from docmind.db.migrate import migrate
from docmind.db.session import Database
from docmind.integrations.storage import S3Storage
from docmind.main import create_app
from tests.integration.conftest import (
    ADMIN_URL,
    RUN,
    TEST_DATABASE,
    aws_client,
    database_url,
    recreate_database,
)

pytestmark = pytest.mark.integration


async def test_s3_storage_round_trip(settings: Settings) -> None:
    storage = S3Storage(settings)
    key = f"it/{uuid.uuid4()}/hello.txt"
    data = b"hello from the integration suite " * 2000

    await storage.put(key, data, "text/plain")
    assert await storage.get(key) == data
    assert b"".join([part async for part in storage.stream(key)]) == data
    await storage.delete(key)

    with pytest.raises(NotFoundError):
        await storage.get(key)
    await storage.check()


async def test_rate_limits_are_counted_in_valkey(settings: Settings) -> None:
    redis = Redis.from_url(settings.redis_url)
    try:
        limiter = RateLimiter(redis)
        key = f"it:{uuid.uuid4()}"
        results = [await limiter.hit(key, 3) for _ in range(4)]
    finally:
        await redis.aclose()

    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[0].headers()["x-ratelimit-remaining"] == "2"
    assert results[-1].headers()["x-ratelimit-limit"] == "3"


async def test_sign_in_attempts_are_rate_limited_per_client(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"rate_limit_login": 2}))
    body = {"email": f"{uuid.uuid4().hex}@example.com", "password": "not-the-password"}
    async with app.router.lifespan_context(app):
        # A client address of its own, so no other test shares this sign-in bucket.
        address = ".".join(str(b) for b in (10, *uuid.uuid4().bytes[:3]))
        transport = httpx.ASGITransport(app=app, client=(address, 4242))
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
            codes = [
                (await http.post("/api/v1/auth/login", json=body)).status_code for _ in range(3)
            ]
            limited = await http.post("/api/v1/auth/login", json=body)

    assert codes == [401, 401, 429]
    assert limited.json()["error"]["code"] == "rate_limited"


async def test_the_database_password_can_come_from_secrets_manager(settings: Settings) -> None:
    password = make_url(ADMIN_URL).password
    secret = aws_client("secretsmanager").create_secret(
        Name=f"docmind-it-{RUN}-database",
        SecretString=json.dumps({"username": "docmind", "password": password}),
    )
    from_secret = settings.model_copy(
        update={
            "database_url": database_url(TEST_DATABASE, with_password=False),
            "database_secret_arn": secret["ARN"],
        }
    )
    db = Database(from_secret)
    sent: list[object] = []
    # Runs after the secret listener, so it sees exactly what the driver is given.
    event.listen(
        db.engine.sync_engine, "do_connect", lambda *args: sent.append(args[3].get("password"))
    )
    try:
        async with db.session() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await db.dispose()

    assert make_url(from_secret.database_url).password is None
    assert sent == [password]


async def test_migrations_are_idempotent_and_safe_to_run_at_the_same_time(
    settings: Settings,
) -> None:
    name = f"docmind_migrate_{RUN}"
    await recreate_database(name)
    fresh = settings.model_copy(update={"database_url": database_url(name)})

    # Several replicas booting together: the advisory lock lets exactly one migrate.
    await asyncio.gather(*(migrate(fresh) for _ in range(3)))
    await migrate(fresh)

    dsn = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    conn = await asyncpg.connect(dsn)
    try:
        versions = await conn.fetch("SELECT version_num FROM alembic_version")
        extensions = {r["extname"] for r in await conn.fetch("SELECT extname FROM pg_extension")}
        tables = {
            r["tablename"]
            for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }
        indexes = {
            r["indexname"]
            for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'")
        }
    finally:
        await conn.close()
        admin = await asyncpg.connect(ADMIN_URL)
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()

    assert len(versions) == 1
    assert "vector" in extensions
    assert {"users", "workspaces", "documents", "chunks", "messages", "answer_cache"} <= tables
    assert {"ix_chunks_embedding_hnsw", "ix_chunks_tsv"} <= indexes


async def test_readiness_reports_every_dependency(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "storage": "ok", "queue": "ok"},
    }
