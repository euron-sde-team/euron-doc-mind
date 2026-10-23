"""The document library: upload rules, original files in S3, rename, reprocess, delete."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.integration.conftest import AwsResources, Corpus, aws_client
from tests.integration.support import ask, signup, upload, wait_ready

pytestmark = pytest.mark.integration


async def test_uploads_reject_bad_files_and_skip_duplicates(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await signup(client, "Library Owner")
    csv = samples_dir / "warehouse-pilot-results.csv"

    first = await upload(
        client,
        owner,
        owner.workspace,
        [
            (csv.name, csv.read_bytes()),
            ("setup.exe", b"MZ\x90\x00" + bytes(512)),
            ("empty.txt", b""),
        ],
    )
    again = await upload(client, owner, owner.workspace, [("copy.csv", csv.read_bytes())])

    assert [d["filename"] for d in first["created"]] == [csv.name]
    assert first["created"][0]["status"] == "queued"
    assert {r["filename"] for r in first["rejected"]} == {"setup.exe", "empty.txt"}
    assert all(r["code"] and r["message"] for r in first["rejected"])
    assert not again["created"]
    assert [d["id"] for d in again["duplicates"]] == [first["created"][0]["id"]]


async def test_originals_are_stored_encrypted_and_downloadable(
    client: httpx.AsyncClient, samples_dir: Path, aws: AwsResources
) -> None:
    owner = await signup(client, "Library Owner")
    pdf = samples_dir / "Globex Master Services Agreement.pdf"
    created = (await upload(client, owner, owner.workspace, [(pdf.name, pdf.read_bytes())]))[
        "created"
    ][0]
    base = f"/api/v1/workspaces/{owner.workspace}/documents/{created['id']}"

    download = await client.get(f"{base}/file", headers=owner.headers)

    assert download.status_code == 200
    assert download.content == pdf.read_bytes()
    assert "attachment" in download.headers["content-disposition"]
    objects = aws_client("s3").list_objects_v2(Bucket=aws.bucket)["Contents"]
    key = next(o["Key"] for o in objects if created["id"] in o["Key"])
    head = aws_client("s3").head_object(Bucket=aws.bucket, Key=key)
    assert head["ServerSideEncryption"] == "aws:kms"


async def test_documents_are_parsed_into_sections_and_counted(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await signup(client, "Library Owner")
    deck = samples_dir / "Q3 2026 Board Update.pptx"
    created = (await upload(client, owner, owner.workspace, [(deck.name, deck.read_bytes())]))[
        "created"
    ][0]
    await wait_ready(client, owner, owner.workspace, [created["id"]])

    detail = (
        await client.get(
            f"/api/v1/workspaces/{owner.workspace}/documents/{created['id']}",
            headers=owner.headers,
        )
    ).json()
    stats = (
        await client.get(
            f"/api/v1/workspaces/{owner.workspace}/documents/stats", headers=owner.headers
        )
    ).json()

    assert detail["status"] == "ready"
    assert detail["kind"] == "pptx"
    assert detail["section_count"] == len(detail["sections"]) > 1
    assert all(s["label"].startswith("Slide ") for s in detail["sections"])
    assert detail["chunk_count"] >= detail["section_count"]
    assert stats["ready"] == 1
    assert stats["chunks"] == detail["chunk_count"]
    assert stats["bytes"] == deck.stat().st_size


async def test_rename_reprocess_and_delete(client: httpx.AsyncClient, samples_dir: Path) -> None:
    owner = await signup(client, "Library Owner")
    notes = samples_dir / "Release notes 4.2.txt"
    created = (await upload(client, owner, owner.workspace, [(notes.name, notes.read_bytes())]))[
        "created"
    ][0]
    await wait_ready(client, owner, owner.workspace, [created["id"]])
    base = f"/api/v1/workspaces/{owner.workspace}/documents/{created['id']}"

    renamed = await client.patch(base, json={"title": "Atlas 4.2 notes"}, headers=owner.headers)
    assert renamed.json()["title"] == "Atlas 4.2 notes"

    reprocess = await client.post(f"{base}/reprocess", headers=owner.headers)
    assert reprocess.status_code == 200
    assert (await wait_ready(client, owner, owner.workspace, [created["id"]])) == {
        created["id"]: "ready"
    }
    answer = await ask(client, owner.headers, owner.workspace, "What changed in release 4.2?")
    assert answer["citations"]

    assert (await client.delete(base, headers=owner.headers)).status_code == 204
    assert (await client.get(base, headers=owner.headers)).status_code == 404
    hits = (
        await client.post(
            f"/api/v1/workspaces/{owner.workspace}/search",
            json={"query": "release 4.2"},
            headers=owner.headers,
        )
    ).json()["hits"]
    assert hits == []


async def test_the_library_filters_by_status_kind_and_text(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    base = f"/api/v1/workspaces/{corpus.workspace}/documents"
    headers = corpus.owner.headers
    pdfs = (await client.get(base, params={"kind": "pdf"}, headers=headers)).json()
    found = (await client.get(base, params={"q": "globex"}, headers=headers)).json()
    ready = (await client.get(base, params={"status": "ready"}, headers=headers)).json()

    assert {d["kind"] for d in pdfs["items"]} == {"pdf"}
    assert pdfs["total"] == 2
    assert [d["title"] for d in found["items"]] == ["Globex Master Services Agreement"]
    assert ready["total"] == 9
