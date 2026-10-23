import uuid
from pathlib import Path

import pytest

from docmind.core.ids import uuid7
from docmind.integrations.queue import IngestJob, InlineQueue
from docmind.integrations.storage import LocalStorage, document_key
from docmind.services.answer_cache import CacheKey, normalize_question, scope_hash


def test_uuid7_layout_and_order() -> None:
    first, second = uuid7(), uuid7()
    assert first.version == 7
    assert first.variant == uuid.RFC_4122
    assert first.int >> 80 <= second.int >> 80


def test_answer_cache_keys_ignore_case_spacing_and_punctuation() -> None:
    assert normalize_question("  How MUCH leave?? ") == "how much leave"
    a, b = uuid.uuid4(), uuid.uuid4()
    assert scope_hash(None) == "all"
    assert scope_hash([a, b]) == scope_hash([b, a])
    key = CacheKey(a, 3, "extractive#2", "all")
    assert key.exact("How much leave?") == key.exact("how much leave")
    assert CacheKey(a, 4, "extractive#2", "all").exact("x") != key.exact("x")


async def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = document_key(uuid.uuid4(), uuid.uuid4(), ".pdf")
    await storage.put(key, b"%PDF-1.7 data", "application/pdf")
    assert await storage.get(key) == b"%PDF-1.7 data"
    assert b"".join([chunk async for chunk in storage.stream(key)]) == b"%PDF-1.7 data"
    await storage.delete(key)
    await storage.delete(key)  # idempotent


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs/path", "a/../../b", "a b"])
async def test_local_storage_refuses_unsafe_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match=r"unsafe|escapes"):
        await LocalStorage(tmp_path).put(key, b"x", "text/plain")


async def test_inline_queue_runs_and_drains() -> None:
    seen: list[IngestJob] = []

    async def handler(job: IngestJob) -> None:
        seen.append(job)

    queue = InlineQueue()
    queue.bind(handler)
    job = IngestJob(uuid.uuid4(), uuid.uuid4())
    await queue.enqueue(job)
    await queue.drain()
    assert seen == [job]
    assert IngestJob.decode(job.encode()) == job
