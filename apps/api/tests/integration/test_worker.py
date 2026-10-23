"""The ingestion worker on the emulator's SQS: delivery, failures and the stale-document reaper."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from docmind.core.config import Settings
from docmind.integrations.queue import SqsQueue
from docmind.models import Document, User, Workspace
from docmind.models.enums import DocumentStatus
from docmind.services.container import Container, build_container
from docmind.services.documents import DocumentService, IncomingFile
from docmind.services.ingestion import IngestionService
from docmind.services.principal import Principal
from docmind.worker import Worker
from tests.integration.conftest import AwsResources, aws_client
from tests.integration.support import signup

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def sqs(settings: Settings) -> AsyncIterator[Container]:
    """A worker-side container: same database, storage and cache, ingestion through SQS."""
    container = build_container(settings.model_copy(update={"queue_backend": "sqs"}))
    yield container
    await container.close()


async def _owner(client: httpx.AsyncClient, container: Container) -> tuple[Principal, Workspace]:
    account = await signup(client, "Worker Owner")
    async with container.db.session() as session:
        user = await session.get(User, uuid.UUID(account.user_id))
        workspace = (
            await session.execute(select(Workspace).where(Workspace.slug == account.workspace))
        ).scalar_one()
    assert user is not None
    return Principal(user=user), workspace


async def _upload(
    container: Container, principal: Principal, workspace: Workspace, name: str, data: bytes
) -> uuid.UUID:
    async with container.db.session() as session:
        target = await session.get(Workspace, workspace.id)
        assert target is not None
        outcome = await DocumentService(container, session).upload(
            target, principal, [IncomingFile(name, data)]
        )
    assert outcome.created, outcome.rejected
    return outcome.created[0].id


async def _document(container: Container, document_id: uuid.UUID) -> Document:
    async with container.db.session() as session:
        document = await session.get(Document, document_id)
    assert document is not None
    return document


async def _set(container: Container, document_id: uuid.UUID, **values: Any) -> None:
    async with container.db.session() as session:
        await session.execute(update(Document).where(Document.id == document_id).values(**values))
        await session.commit()


def _depth(queue_url: str) -> tuple[int, int]:
    """(waiting, in flight) messages."""
    attributes = aws_client("sqs").get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return (
        int(attributes["ApproximateNumberOfMessages"]),
        int(attributes["ApproximateNumberOfMessagesNotVisible"]),
    )


def _lose_messages(queue_url: str) -> None:
    sqs = aws_client("sqs")
    while messages := sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
    ).get("Messages"):
        for message in messages:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


async def _work_until(
    container: Container, finished: Callable[[], Awaitable[bool]], timeout_s: float = 180
) -> None:
    """Run a real worker until `finished`, then stop it the way SIGTERM does."""
    assert isinstance(container.queue, SqsQueue)
    worker = Worker(container, container.queue)
    running = asyncio.create_task(worker.run())
    try:
        deadline = time.monotonic() + timeout_s
        while not await finished():
            assert not running.done(), "the worker stopped on its own"
            assert time.monotonic() < deadline, "the worker did not finish in time"
            await asyncio.sleep(0.5)
    finally:
        worker.stop()
        await asyncio.wait_for(running, timeout=60)


def _reaches(
    container: Container, document_id: uuid.UUID, status: DocumentStatus
) -> Callable[[], Awaitable[bool]]:
    async def check() -> bool:
        return (await _document(container, document_id)).status == status

    return check


async def test_uploads_travel_through_sqs_and_get_indexed(
    client: httpx.AsyncClient, sqs: Container, aws: AwsResources, samples_dir: Path
) -> None:
    principal, workspace = await _owner(client, sqs)
    faq = samples_dir / "Customer Support FAQ.html"

    document_id = await _upload(sqs, principal, workspace, faq.name, faq.read_bytes())
    assert (await _document(sqs, document_id)).status == DocumentStatus.QUEUED
    assert _depth(aws.queue_url) == (1, 0)

    await _work_until(sqs, _reaches(sqs, document_id, DocumentStatus.READY))

    document = await _document(sqs, document_id)
    assert document.attempts == 1
    assert document.chunk_count > 0
    assert _depth(aws.queue_url) == (0, 0)


async def test_an_unreadable_file_fails_once_and_leaves_the_queue(
    client: httpx.AsyncClient, sqs: Container, aws: AwsResources
) -> None:
    principal, workspace = await _owner(client, sqs)
    broken = b"%PDF-1.7\n" + bytes(range(256)) * 16

    document_id = await _upload(sqs, principal, workspace, "scan.pdf", broken)
    await _work_until(sqs, _reaches(sqs, document_id, DocumentStatus.FAILED))

    document = await _document(sqs, document_id)
    assert document.attempts == 1
    assert document.error
    assert _depth(aws.queue_url) == (0, 0)


async def test_the_reaper_resends_a_document_whose_message_was_lost(
    client: httpx.AsyncClient, sqs: Container, aws: AwsResources, samples_dir: Path
) -> None:
    principal, workspace = await _owner(client, sqs)
    notes = samples_dir / "Release notes 4.2.txt"
    document_id = await _upload(sqs, principal, workspace, notes.name, notes.read_bytes())
    _lose_messages(aws.queue_url)
    await _set(sqs, document_id, updated_at=datetime.now(UTC) - timedelta(hours=1))

    assert await IngestionService(sqs).reap_stale() == 1
    assert _depth(aws.queue_url) == (1, 0)
    # Its clock restarted: the next round does not send it again.
    assert await IngestionService(sqs).reap_stale() == 0

    await _work_until(sqs, _reaches(sqs, document_id, DocumentStatus.READY))


async def test_the_reaper_leaves_waiting_documents_alone_during_a_backlog(
    client: httpx.AsyncClient, sqs: Container, aws: AwsResources, samples_dir: Path
) -> None:
    principal, workspace = await _owner(client, sqs)
    notes = samples_dir / "Security Incident Response Runbook.md"
    document_id = await _upload(sqs, principal, workspace, notes.name, notes.read_bytes())
    await _set(sqs, document_id, updated_at=datetime.now(UTC) - timedelta(hours=1))

    # Its message is still waiting in the queue, so resending would only duplicate it.
    assert await IngestionService(sqs).reap_stale() == 0
    assert _depth(aws.queue_url) == (1, 0)

    await _work_until(sqs, _reaches(sqs, document_id, DocumentStatus.READY))


async def test_a_document_out_of_attempts_is_marked_failed(
    client: httpx.AsyncClient, sqs: Container, aws: AwsResources, samples_dir: Path
) -> None:
    principal, workspace = await _owner(client, sqs)
    notes = samples_dir / "Release notes 4.2.txt"
    document_id = await _upload(sqs, principal, workspace, notes.name, notes.read_bytes())
    _lose_messages(aws.queue_url)
    await _set(
        sqs,
        document_id,
        status=DocumentStatus.PROCESSING,
        attempts=3,
        updated_at=datetime.now(UTC) - timedelta(hours=1),
    )

    assert await IngestionService(sqs).reap_stale() == 1

    document = await _document(sqs, document_id)
    assert document.status == DocumentStatus.FAILED
    assert "several attempts" in (document.error or "")
    assert _depth(aws.queue_url) == (0, 0)
