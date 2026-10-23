"""Who can do what: workspace isolation, roles, API keys, sessions and CSRF."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from docmind.core.config import Settings
from docmind.main import create_app
from tests.integration.conftest import WEB_ORIGIN, Corpus
from tests.integration.support import (
    PASSWORD,
    add_member,
    ask,
    bearer,
    create_workspace,
    login,
    signup,
    upload,
    wait_ready,
)

pytestmark = pytest.mark.integration


async def test_outsiders_get_not_found_for_everything_in_another_workspace(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    outsider = await signup(client, "Outsider")
    ws = f"/api/v1/workspaces/{corpus.workspace}"
    document = corpus.document_id("Globex Master Services Agreement.pdf")
    conversation = (
        await client.post(f"{ws}/conversations", json={}, headers=corpus.owner.headers)
    ).json()["id"]
    probes: list[tuple[str, str, object]] = [
        ("GET", ws, None),
        ("PATCH", ws, {"name": "Taken over"}),
        ("DELETE", ws, None),
        ("GET", f"{ws}/documents", None),
        ("GET", f"{ws}/documents/stats", None),
        ("GET", f"{ws}/documents/{document}", None),
        ("GET", f"{ws}/documents/{document}/file", None),
        ("PATCH", f"{ws}/documents/{document}", {"title": "Renamed"}),
        ("POST", f"{ws}/documents/{document}/reprocess", None),
        ("DELETE", f"{ws}/documents/{document}", None),
        ("POST", f"{ws}/search", {"query": "globex uptime"}),
        ("POST", f"{ws}/ask", {"question": "What uptime does Globex get?"}),
        ("POST", f"{ws}/ask/stream", {"question": "What uptime does Globex get?"}),
        ("GET", f"{ws}/conversations", None),
        ("GET", f"{ws}/conversations/{conversation}", None),
        ("GET", f"{ws}/conversations/{conversation}/messages", None),
        ("DELETE", f"{ws}/conversations/{conversation}", None),
        ("GET", f"{ws}/members", None),
        ("POST", f"{ws}/members", {"email": outsider.email, "role": "owner"}),
        ("GET", f"{ws}/api-keys", None),
        ("POST", f"{ws}/api-keys", {"name": "Exfiltrate"}),
        ("GET", f"{ws}/insights", None),
        ("GET", f"{ws}/audit", None),
    ]

    for method, path, body in probes:
        response = await client.request(method, path, json=body, headers=outsider.headers)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
        assert response.json()["error"]["code"] == "not_found"

    still_there = await client.get(f"{ws}/documents/{document}", headers=corpus.owner.headers)
    assert still_there.status_code == 200


async def test_ids_from_another_workspace_resolve_to_nothing(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    other = await signup(client, "Other Owner")
    ws = f"/api/v1/workspaces/{other.workspace}"
    document = corpus.document_id("Globex Master Services Agreement.pdf")

    detail = await client.get(f"{ws}/documents/{document}", headers=other.headers)
    original = await client.get(f"{ws}/documents/{document}/file", headers=other.headers)
    scoped = await client.post(
        f"{ws}/ask",
        json={"question": "What uptime does Globex get?", "document_ids": [document]},
        headers=other.headers,
    )
    search = await client.post(
        f"{ws}/search", json={"query": "Globex uptime"}, headers=other.headers
    )

    assert detail.status_code == 404
    assert original.status_code == 404
    assert scoped.status_code == 422
    assert scoped.json()["error"]["code"] == "empty_scope"
    assert search.json()["hits"] == []


async def test_roles_decide_who_reads_who_edits_and_who_manages(
    client: httpx.AsyncClient, samples_dir: Path
) -> None:
    owner = await signup(client, "Owner")
    editor = await signup(client, "Editor")
    viewer = await signup(client, "Viewer")
    workspace = await create_workspace(client, owner, "Roles")
    await add_member(client, owner, workspace, editor, "editor")
    await add_member(client, owner, workspace, viewer, "viewer")
    ws = f"/api/v1/workspaces/{workspace}"
    notes = samples_dir / "Release notes 4.2.txt"

    # Viewers cannot change the library.
    denied = await client.post(
        f"{ws}/documents",
        files=[("files", (notes.name, notes.read_bytes(), "text/plain"))],
        headers=viewer.headers,
    )
    assert denied.status_code == 403
    # Editors can, but cannot manage people, keys or settings.
    created = (await upload(client, editor, workspace, [(notes.name, notes.read_bytes())]))[
        "created"
    ][0]
    for method, path, body in [
        ("POST", f"{ws}/members", {"email": viewer.email, "role": "owner"}),
        ("GET", f"{ws}/api-keys", None),
        ("PATCH", ws, {"name": "Renamed"}),
        ("GET", f"{ws}/audit", None),
    ]:
        response = await client.request(method, path, json=body, headers=editor.headers)
        assert response.status_code == 403, f"{method} {path}: {response.status_code}"
    # Viewers read and ask.
    await wait_ready(client, editor, workspace, [created["id"]])
    message = await ask(client, viewer.headers, workspace, "What changed in release 4.2?")
    assert message["citations"]
    deleted = await client.delete(f"{ws}/documents/{created['id']}", headers=viewer.headers)
    assert deleted.status_code == 403

    # Removing a member ends their access at once.
    removed = await client.delete(f"{ws}/members/{editor.user_id}", headers=owner.headers)
    assert removed.status_code == 204
    gone = await client.get(f"{ws}/documents", headers=editor.headers)
    assert gone.status_code == 404
    audit = (await client.get(f"{ws}/audit", headers=owner.headers)).json()
    actions = {entry["action"] for entry in audit}
    assert {"member.added", "document.uploaded", "member.removed"} <= actions


async def test_api_keys_are_scoped_to_one_workspace_and_revocable(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    ws = f"/api/v1/workspaces/{corpus.workspace}"
    created = await client.post(
        f"{ws}/api-keys",
        json={"name": "Support bot", "role": "viewer"},
        headers=corpus.owner.headers,
    )
    assert created.status_code == 201, created.text
    key, key_id = created.json()["key"], created.json()["id"]
    assert key.startswith("dmk_")

    answer = await ask(
        client, bearer(key), corpus.workspace, "How do customers reset an Atlas robot?"
    )
    assert answer["citations"]
    other = await signup(client, "Elsewhere")
    elsewhere = await client.get(
        f"/api/v1/workspaces/{other.workspace}/documents", headers=bearer(key)
    )
    account = await client.get("/api/v1/auth/me", headers=bearer(key))
    write = await client.post(
        f"{ws}/documents",
        files=[("files", ("note.txt", b"A short note about nothing.", "text/plain"))],
        headers=bearer(key),
    )
    assert elsewhere.status_code == 404
    assert account.status_code == 403
    assert write.status_code == 403

    listed = (await client.get(f"{ws}/api-keys", headers=corpus.owner.headers)).json()
    entry = next(item for item in listed if item["id"] == key_id)
    assert "key" not in entry
    assert entry["last_used_at"] is not None

    revoked = await client.delete(f"{ws}/api-keys/{key_id}", headers=corpus.owner.headers)
    assert revoked.status_code == 204
    after = await client.post(f"{ws}/ask", json={"question": "Warranty?"}, headers=bearer(key))
    forged = await client.post(
        f"{ws}/ask", json={"question": "Warranty?"}, headers=bearer(key[:-6] + "AAAAAA")
    )
    assert after.status_code == 401
    assert forged.status_code == 401


async def test_sign_out_ends_one_session_and_a_password_change_ends_the_rest(
    client: httpx.AsyncClient,
) -> None:
    account = await signup(client, "Session Person")
    second = await login(client, account.email)
    third = await login(client, account.email)

    assert (await client.post("/api/v1/auth/logout", headers=bearer(second))).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(second))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=bearer(third))).status_code == 200

    changed = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "A-brand-new-pass-77"},
        headers=bearer(third),
    )
    client.cookies.clear()
    assert changed.status_code == 200, changed.text
    for token in (account.token, third):
        assert (await client.get("/api/v1/auth/me", headers=bearer(token))).status_code == 401
    fresh = changed.json()["token"]
    assert (await client.get("/api/v1/auth/me", headers=bearer(fresh))).status_code == 200
    old_password = await client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
    )
    assert old_password.status_code == 401


async def test_cookie_sessions_only_accept_writes_from_the_web_app(
    client: httpx.AsyncClient,
) -> None:
    account = await signup(client, "Cookie Person")
    signed_in = await client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200
    assert client.cookies.get("docmind_session")
    try:
        read = await client.get("/api/v1/auth/me")
        forged = await client.post(
            "/api/v1/workspaces",
            json={"name": "Cross-site"},
            headers={"origin": "https://attacker.example"},
        )
        bare = await client.post("/api/v1/workspaces", json={"name": "No origin"})
        same_site = await client.post(
            "/api/v1/workspaces", json={"name": "From the app"}, headers={"origin": WEB_ORIGIN}
        )
    finally:
        client.cookies.clear()

    assert read.status_code == 200
    assert forged.status_code == 403
    assert forged.json()["error"]["code"] == "csrf"
    assert bare.status_code == 403
    assert same_site.status_code == 201


async def test_sign_up_is_closed_after_the_first_account_unless_enabled(
    settings: Settings, client: httpx.AsyncClient
) -> None:
    await signup(client, "Somebody First")
    closed = create_app(settings.model_copy(update={"allow_signup": False}))
    async with closed.router.lifespan_context(closed):
        transport = httpx.ASGITransport(app=closed)
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
            response = await http.post(
                "/api/v1/auth/signup",
                json={"email": "late@example.com", "name": "Late", "password": PASSWORD},
            )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
