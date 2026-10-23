"""The two-level answer cache against real Valkey and pgvector."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.integration.support import Account, ask, signup, upload, wait_ready

pytestmark = pytest.mark.integration

LEAVE = "How many days of annual leave do employees get?"


async def _workspace_with(client: httpx.AsyncClient, samples_dir: Path, *names: str) -> Account:
    owner = await signup(client, "Cache Owner")
    files = [(name, (samples_dir / name).read_bytes()) for name in names]
    created = (await upload(client, owner, owner.workspace, files))["created"]
    statuses = await wait_ready(client, owner, owner.workspace, [d["id"] for d in created])
    assert set(statuses.values()) == {"ready"}
    return owner


async def test_repeats_hit_exactly_paraphrases_semantically_and_new_documents_reset(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await _workspace_with(client, samples_dir, "Northwind Employee Handbook 2026.pdf")

    first = await ask(client, owner.headers, owner.workspace, LEAVE)
    again = await ask(client, owner.headers, owner.workspace, LEAVE.lower().rstrip("?"))
    paraphrase = await ask(
        client, owner.headers, owner.workspace, "How many annual leave days do employees get?"
    )

    assert [m["usage"]["cache"] for m in (first, again, paraphrase)] == [
        "miss",
        "exact",
        "semantic",
    ]
    assert again["content"] == first["content"] == paraphrase["content"]
    assert again["citations"] == first["citations"]
    assert again["usage"]["context_tokens"] == 0
    assert again["usage"]["saved_tokens"] == again["usage"]["baseline_tokens"]

    # A new document can change the right answer, so earlier answers are not reused.
    notes = "Release notes 4.2.txt"
    created = (
        await upload(client, owner, owner.workspace, [(notes, (samples_dir / notes).read_bytes())])
    )["created"]
    await wait_ready(client, owner, owner.workspace, [created[0]["id"]])
    after = await ask(client, owner.headers, owner.workspace, LEAVE)
    assert after["usage"]["cache"] == "miss"
    assert after["content"] == first["content"]


async def test_the_document_scope_is_part_of_the_cache_key(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await _workspace_with(
        client, samples_dir, "Northwind Employee Handbook 2026.pdf", "Customer Support FAQ.html"
    )
    library = (
        await client.get(f"/api/v1/workspaces/{owner.workspace}/documents", headers=owner.headers)
    ).json()["items"]
    handbook = next(d["id"] for d in library if d["filename"].startswith("Northwind"))

    unscoped = await ask(client, owner.headers, owner.workspace, LEAVE)
    scoped = await ask(client, owner.headers, owner.workspace, LEAVE, document_ids=[handbook])
    scoped_again = await ask(client, owner.headers, owner.workspace, LEAVE, document_ids=[handbook])

    assert [m["usage"]["cache"] for m in (unscoped, scoped, scoped_again)] == [
        "miss",
        "miss",
        "exact",
    ]


async def test_owners_can_turn_the_cache_off(client: httpx.AsyncClient, samples_dir: Path) -> None:
    owner = await _workspace_with(client, samples_dir, "Northwind Employee Handbook 2026.pdf")
    response = await client.patch(
        f"/api/v1/workspaces/{owner.workspace}",
        json={"settings": {"cache_enabled": False}},
        headers=owner.headers,
    )
    assert response.status_code == 200, response.text

    answers = [await ask(client, owner.headers, owner.workspace, LEAVE) for _ in range(2)]
    assert [m["usage"]["cache"] for m in answers] == ["miss", "miss"]


async def test_insights_count_questions_hits_and_saved_tokens(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await _workspace_with(client, samples_dir, "Northwind Employee Handbook 2026.pdf")
    for _ in range(3):
        await ask(client, owner.headers, owner.workspace, LEAVE)
    await ask(client, owner.headers, owner.workspace, "What is the parental leave policy?")

    insights = (
        await client.get(f"/api/v1/workspaces/{owner.workspace}/insights", headers=owner.headers)
    ).json()
    totals = insights["totals"]
    assert totals["questions"] == 4
    assert totals["cache_hits"] == 2
    assert totals["cache_hit_rate"] == pytest.approx(0.5)
    assert totals["saved_tokens"] > 0
    assert insights["top_documents"][0]["title"] == "Northwind Employee Handbook 2026"
    assert insights["library"]["ready"] == 1
