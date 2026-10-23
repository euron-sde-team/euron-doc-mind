"""The ingestion worker: long-polls SQS and processes documents with bounded concurrency.

    python -m docmind.worker

- Message visibility is extended while a document is being processed, so a slow parse is
  never handed to a second worker.
- A failure returns the message to the queue with growing back-off; after three receives
  SQS moves it to the dead-letter queue and the document is marked failed.
- SIGTERM stops receiving, lets in-flight documents finish (up to a grace period), then
  exits: a rolling deploy never loses work.
- One worker at a time (elected through Redis) re-enqueues documents stuck unfinished and
  purges expired cache rows.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from datetime import UTC, datetime

from prometheus_client import start_http_server

from docmind.core.config import get_settings
from docmind.core.logging import configure_logging, get_logger
from docmind.db.migrate import migrate
from docmind.integrations.queue import ReceivedJob, SqsQueue
from docmind.repositories.answer_cache import AnswerCacheRepository
from docmind.services.container import Container, build_container
from docmind.services.ingestion import MAX_ATTEMPTS, IngestionService, Outcome

log = get_logger("docmind.worker")
VISIBILITY_S = 300
SHUTDOWN_GRACE_S = 120
REAPER_INTERVAL_S = 60


class Worker:
    def __init__(self, container: Container, queue: SqsQueue) -> None:
        self.c = container
        self.queue = queue
        self.ingestion = IngestionService(container)
        self.concurrency = container.settings.worker_concurrency
        self.stopping = asyncio.Event()
        self.inflight: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        if not self.stopping.is_set():
            log.info("worker_stopping", inflight=len(self.inflight))
            self.stopping.set()

    async def run(self) -> None:
        reaper = asyncio.create_task(self._reaper())
        while not self.stopping.is_set():
            free = self.concurrency - len(self.inflight)
            if free <= 0:
                await asyncio.wait(self.inflight, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                received = await self.queue.receive(
                    max_messages=min(10, free), wait_s=10, visibility_s=VISIBILITY_S
                )
            except Exception:
                log.exception("queue_receive_failed")
                await asyncio.sleep(5)
                continue
            for item in received:
                task = asyncio.create_task(self._handle(item))
                self.inflight.add(task)
                task.add_done_callback(self.inflight.discard)
        if self.inflight:
            await asyncio.wait(self.inflight, timeout=SHUTDOWN_GRACE_S)
        reaper.cancel()

    async def _handle(self, item: ReceivedJob) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(item.receipt))
        try:
            final = item.receive_count >= MAX_ATTEMPTS
            outcome = await self.ingestion.process(item.job, final_attempt=final)
            if outcome is Outcome.DONE:
                await self.queue.delete(item.receipt)
            else:
                await self.queue.extend(item.receipt, 30 * item.receive_count)
        except Exception:
            log.exception("job_failed", document_id=str(item.job.document_id))
        finally:
            heartbeat.cancel()

    async def _heartbeat(self, receipt: str) -> None:
        while True:
            await asyncio.sleep(VISIBILITY_S / 2)
            with contextlib.suppress(Exception):
                await self.queue.extend(receipt, VISIBILITY_S)

    async def _reaper(self) -> None:
        while True:
            await asyncio.sleep(REAPER_INTERVAL_S)
            try:
                if await self.c.redis.set("lock:reaper", b"1", ex=REAPER_INTERVAL_S - 5, nx=True):
                    await self.ingestion.reap_stale()
                    async with self.c.db.session() as session:
                        await AnswerCacheRepository(session).purge_expired(datetime.now(UTC))
                        await session.commit()
            except Exception:
                log.exception("reaper_failed")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.migrate_on_boot:
        await migrate(settings)
    container = build_container(settings)
    if not isinstance(container.queue, SqsQueue):
        raise SystemExit(
            "The worker needs QUEUE_BACKEND=sqs. With the inline queue the API ingests in process."
        )
    if port := int(os.environ.get("WORKER_METRICS_PORT", "0")):
        start_http_server(port)
    await container.warm_up()
    worker = Worker(container, container.queue)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    log.info("worker_started", concurrency=worker.concurrency, embeddings=container.embedder.name)
    try:
        await worker.run()
    finally:
        await container.close()
        log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
