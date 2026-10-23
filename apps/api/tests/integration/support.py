"""Small HTTP helpers shared by the integration tests."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

PASSWORD = "Integration-pass-2026"


@dataclass(frozen=True)
class Account:
    email: str
    user_id: str
    token: str
    workspace: str  # slug of the personal workspace created at sign-up

    @property
    def headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}"}


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


async def signup(client: httpx.AsyncClient, name: str = "Test Person") -> Account:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "name": name, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    # Bearer tokens only: a cookie left in the shared client would authenticate later calls.
    client.cookies.clear()
    me = (await client.get("/api/v1/auth/me", headers=bearer(token))).json()
    return Account(email, me["user"]["id"], token, me["workspaces"][0]["slug"])


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return str(response.json()["token"])


async def create_workspace(client: httpx.AsyncClient, owner: Account, name: str) -> str:
    response = await client.post("/api/v1/workspaces", json={"name": name}, headers=owner.headers)
    assert response.status_code == 201, response.text
    return str(response.json()["slug"])


async def add_member(
    client: httpx.AsyncClient, owner: Account, workspace: str, member: Account, role: str
) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{workspace}/members",
        json={"email": member.email, "role": role},
        headers=owner.headers,
    )
    assert response.status_code == 201, response.text


async def upload(
    client: httpx.AsyncClient, account: Account, workspace: str, files: list[tuple[str, bytes]]
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/workspaces/{workspace}/documents",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def wait_ready(
    client: httpx.AsyncClient,
    account: Account,
    workspace: str,
    document_ids: list[str],
    timeout_s: float = 240,
) -> dict[str, str]:
    """Poll until every document is ready or failed; returns id -> status."""
    deadline = time.monotonic() + timeout_s
    while True:
        statuses = {}
        for document_id in document_ids:
            response = await client.get(
                f"/api/v1/workspaces/{workspace}/documents/{document_id}", headers=account.headers
            )
            statuses[document_id] = response.json()["status"]
        if all(status in {"ready", "failed"} for status in statuses.values()):
            return statuses
        if time.monotonic() > deadline:
            raise AssertionError(f"documents not indexed in time: {statuses}")
        await asyncio.sleep(0.5)


async def ask(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    workspace: str,
    question: str,
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/workspaces/{workspace}/ask", json={"question": question, **extra}, headers=headers
    )
    assert response.status_code == 200, response.text
    message: dict[str, Any] = response.json()["message"]
    return message


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """`event:`/`data:` frames of a server-sent event stream, in order."""
    events = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events
