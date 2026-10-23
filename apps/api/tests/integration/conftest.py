"""Integration fixtures: real Postgres (pgvector), Valkey and the Floci AWS emulator.

`make test-integration` starts all three (scripts/test-deps.sh) and runs this suite. It
works in a database of its own (`docmind_test`, recreated on every run), Valkey database 15
(flushed on every run) and uniquely named buckets and queues on the emulator, so the data
of a development stack is never touched. Point it elsewhere with TEST_DATABASE_ADMIN_URL,
TEST_REDIS_URL and TEST_AWS_ENDPOINT_URL.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import boto3
import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.engine import URL, make_url

from docmind.core.config import Settings
from docmind.db.migrate import migrate
from docmind.main import create_app
from tests.integration.support import Account, signup, upload, wait_ready

# The emulator accepts any credentials; real ones must never be sent to it.
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
for _name in ("AWS_SESSION_TOKEN", "AWS_PROFILE"):
    os.environ.pop(_name, None)

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql://docmind:docmind@localhost:5451/docmind"
)
REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6411/15")
AWS_ENDPOINT = os.environ.get("TEST_AWS_ENDPOINT_URL", "http://localhost:4611")
TEST_DATABASE = "docmind_test"
WEB_ORIGIN = "http://localhost:3110"
RUN = uuid.uuid4().hex[:8]


def database_url(name: str, *, with_password: bool = True) -> str:
    admin = make_url(ADMIN_URL)
    url = URL.create(
        "postgresql+asyncpg",
        username=admin.username,
        password=admin.password if with_password else None,
        host=admin.host,
        port=admin.port,
        database=name,
    )
    return url.render_as_string(hide_password=False)


async def recreate_database(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def aws_client(service: str) -> Any:
    return boto3.client(service, endpoint_url=AWS_ENDPOINT, region_name="us-east-1")


@dataclass(frozen=True)
class AwsResources:
    bucket: str
    kms_key_id: str
    queue_url: str
    dlq_url: str


def provision_aws() -> AwsResources:
    """A KMS key, a bucket and an ingestion queue with its dead-letter queue, like Terraform."""
    key_id = aws_client("kms").create_key(Description=f"docmind integration {RUN}")["KeyMetadata"][
        "KeyId"
    ]
    bucket = f"docmind-it-{RUN}"
    aws_client("s3").create_bucket(Bucket=bucket)
    sqs = aws_client("sqs")
    dlq_url = sqs.create_queue(QueueName=f"docmind-it-{RUN}-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    queue_url = sqs.create_queue(
        QueueName=f"docmind-it-{RUN}",
        Attributes={
            "VisibilityTimeout": "60",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}),
        },
    )["QueueUrl"]
    return AwsResources(bucket, key_id, queue_url, dlq_url)


def make_settings(aws: AwsResources, **overrides: Any) -> Settings:
    """Test settings, independent of the developer's environment variables."""
    values: dict[str, Any] = {
        "app_env": "test",
        "log_level": "warning",
        "database_url": database_url(TEST_DATABASE),
        "redis_url": REDIS_URL,
        "session_secret": "integration-session-secret-0123456789abcdef",
        "api_key_pepper": "integration-api-key-pepper-0123456789abcdef",
        "cors_origins": [WEB_ORIGIN],
        "web_url": WEB_ORIGIN,
        "allow_signup": True,
        "storage_backend": "s3",
        "s3_bucket": aws.bucket,
        "s3_kms_key_id": aws.kms_key_id,
        "aws_endpoint_url": AWS_ENDPOINT,
        "aws_region": "us-east-1",
        "queue_backend": "inline",
        "sqs_queue_url": aws.queue_url,
        "embeddings_provider": "local",
        "llm_provider": "none",
        "rate_limit_chat": 10_000,
        "rate_limit_login": 10_000,
        "rate_limit_upload": 10_000,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture(scope="session")
async def aws() -> AwsResources:
    return provision_aws()


@pytest.fixture(scope="session")
async def settings(aws: AwsResources) -> Settings:
    settings = make_settings(aws)
    await recreate_database(TEST_DATABASE)
    await migrate(settings)
    redis = Redis.from_url(REDIS_URL)
    await redis.flushdb()
    await redis.aclose()
    return settings


@pytest.fixture(scope="session")
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """The real application over ASGI: real database, cache, storage and inline ingestion."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
            yield http


def read_samples(folder: Path) -> list[tuple[str, bytes]]:
    return [
        (path.name, path.read_bytes())
        for path in sorted(folder.iterdir())
        if path.is_file() and not path.name.startswith(".")
    ]


@dataclass(frozen=True)
class Corpus:
    owner: Account
    workspace: str
    documents: dict[str, str]  # filename -> document id

    def document_id(self, filename: str) -> str:
        return self.documents[filename]


@pytest.fixture(scope="session")
async def corpus(client: httpx.AsyncClient, samples_dir: Path) -> Corpus:
    """Every sample document, uploaded once, parsed and indexed by the real pipeline."""
    owner = await signup(client, "Corpus Owner")
    result = await upload(client, owner, owner.workspace, read_samples(samples_dir))
    assert not result["rejected"], result["rejected"]
    documents = {d["filename"]: d["id"] for d in result["created"]}
    statuses = await wait_ready(client, owner, owner.workspace, list(documents.values()))
    assert set(statuses.values()) == {"ready"}, statuses
    return Corpus(owner=owner, workspace=owner.workspace, documents=documents)
