"""The ingestion queue: SQS (with a dead-letter queue) in deployments, in-process otherwise.

Messages carry ids only. The worker re-reads the document row, so a duplicated or stale
message is harmless: processing is idempotent and keyed by the document's content hash.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import anyio
import orjson

from docmind.core.config import Settings
from docmind.core.logging import get_logger
from docmind.integrations import aws

log = get_logger("docmind.queue")


@dataclass(frozen=True, slots=True)
class IngestJob:
    workspace_id: uuid.UUID
    document_id: uuid.UUID

    def encode(self) -> str:
        return orjson.dumps(
            {"workspace_id": str(self.workspace_id), "document_id": str(self.document_id)}
        ).decode()

    @classmethod
    def decode(cls, body: str) -> IngestJob:
        data = orjson.loads(body)
        return cls(uuid.UUID(data["workspace_id"]), uuid.UUID(data["document_id"]))


@dataclass(frozen=True, slots=True)
class ReceivedJob:
    job: IngestJob
    receipt: str
    receive_count: int


class JobQueue(Protocol):
    async def enqueue(self, job: IngestJob) -> None: ...

    async def check(self) -> None: ...


Handler = Callable[[IngestJob], Awaitable[object]]


class InlineQueue:
    """Runs ingestion as a background task in the API process. Development and tests."""

    def __init__(self) -> None:
        self._handler: Handler | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def bind(self, handler: Handler) -> None:
        self._handler = handler

    async def enqueue(self, job: IngestJob) -> None:
        if self._handler is None:
            raise RuntimeError("InlineQueue has no handler bound")
        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: IngestJob) -> None:
        if self._handler is None:
            return
        try:
            await self._handler(job)
        except Exception:
            log.exception("inline_ingest_failed", document_id=str(job.document_id))

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def check(self) -> None:
        return None


class SqsQueue:
    def __init__(self, settings: Settings) -> None:
        if not settings.sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL is required for QUEUE_BACKEND=sqs")
        self.url = settings.sqs_queue_url
        self._client = aws.sqs_client(settings)

    async def enqueue(self, job: IngestJob) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.send_message(QueueUrl=self.url, MessageBody=job.encode())
        )

    async def receive(
        self, *, max_messages: int, wait_s: int, visibility_s: int
    ) -> list[ReceivedJob]:
        response = await anyio.to_thread.run_sync(
            lambda: self._client.receive_message(
                QueueUrl=self.url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_s,
                VisibilityTimeout=visibility_s,
                MessageSystemAttributeNames=["ApproximateReceiveCount"],
            )
        )
        received = []
        for message in response.get("Messages", []):
            try:
                job = IngestJob.decode(message["Body"])
            except (ValueError, KeyError):
                log.warning("queue_message_malformed", message_id=message.get("MessageId"))
                await self.delete(message["ReceiptHandle"])
                continue
            count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            received.append(ReceivedJob(job, message["ReceiptHandle"], count))
        return received

    async def delete(self, receipt: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.delete_message(QueueUrl=self.url, ReceiptHandle=receipt)
        )

    async def extend(self, receipt: str, visibility_s: int) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.change_message_visibility(
                QueueUrl=self.url, ReceiptHandle=receipt, VisibilityTimeout=visibility_s
            )
        )

    async def check(self) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.get_queue_attributes(
                QueueUrl=self.url, AttributeNames=["ApproximateNumberOfMessages"]
            )
        )


def build_queue(settings: Settings) -> InlineQueue | SqsQueue:
    if settings.queue_backend == "sqs":
        return SqsQueue(settings)
    return InlineQueue()
