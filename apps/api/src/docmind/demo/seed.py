"""`make demo`: accounts, workspaces, the sample documents and a few weeks of questions.

Everything goes through the real services: files are stored, queued, parsed, chunked and
embedded by the same code paths as any upload, and every answer is produced by the
configured answerer. The only liberty taken is time: the sample questions are spread over
the past two weeks (their usage timestamps are moved back) so the insights charts have a
shape on a brand-new stack. Re-running is safe; existing accounts, workspaces and files are
reused.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
from sqlalchemy import select, update

from docmind.core.config import Settings
from docmind.core.logging import get_logger
from docmind.core.security import hash_password
from docmind.integrations.queue import IngestJob, InlineQueue
from docmind.models import Conversation, Document, Message, UsageEvent, User, Workspace
from docmind.models.enums import DocumentStatus, Role
from docmind.repositories.users import UserRepository
from docmind.repositories.workspaces import WorkspaceRepository
from docmind.services.api_keys import ApiKeyService
from docmind.services.chat import ChatService
from docmind.services.container import Container, build_container
from docmind.services.documents import DocumentService, IncomingFile
from docmind.services.ingestion import IngestionService
from docmind.services.principal import Principal
from docmind.services.workspaces import WorkspaceService

log = get_logger("docmind.demo")


@dataclass(frozen=True)
class Person:
    email: str
    name: str
    role: Role
    admin: bool = False


PEOPLE = (
    Person("ava.martin@northwind.example", "Ava Martin", Role.OWNER, admin=True),
    Person("leo.chen@northwind.example", "Leo Chen", Role.EDITOR),
    Person("maya.patel@northwind.example", "Maya Patel", Role.VIEWER),
)

MAIN_WORKSPACE = (
    "Northwind Robotics",
    "Company handbook, board updates, budgets, contracts and product specs.",
)
SECOND_WORKSPACE = (
    "Atlas engineering",
    "Product requirements, runbooks and release notes for the Atlas line.",
)
ENGINEERING_FILES = {
    "Atlas v2 Product Requirements.docx",
    "Security Incident Response Runbook.md",
    "Release notes 4.2.txt",
}

# (days ago, conversation title, questions). Paraphrases and repeats exercise both cache levels.
CONVERSATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        13,
        "Leave and time off",
        ("How many days of annual leave do employees get?", "What is the parental leave policy?"),
    ),
    (
        12,
        "Travel expenses",
        ("What is the daily meal allowance when travelling?", "When can I book business class?"),
    ),
    (
        11,
        "Q3 board update",
        ("What was revenue in Q3 2026?", "What decisions is the board being asked to make?"),
    ),
    (
        10,
        "Budget questions",
        ("How much is the FY2027 marketing budget?", "How many engineers are we hiring in FY2027?"),
    ),
    (
        9,
        "Atlas v2 requirements",
        ("What payload must Atlas v2 carry?", "What battery life does Atlas v2 need?"),
    ),
    (
        8,
        "Incident response",
        ("Who do I page for a SEV1 incident?", "How quickly must a SEV1 be acknowledged?"),
    ),
    (
        7,
        "Globex contract",
        (
            "What uptime does the Globex agreement commit to?",
            "How much notice is needed to terminate the Globex agreement?",
        ),
    ),
    (6, "Warehouse pilots", ("Which warehouse pilot had the best pick rate?",)),
    (
        5,
        "Remote work",
        (
            "Can I work remotely from another country?",
            "How many days of annual leave do employees get?",
        ),
    ),
    (
        4,
        "Revenue follow-up",
        ("What was Q3 2026 revenue?", "How much is the FY2027 marketing budget?"),
    ),
    (3, "Support FAQ", ("How do customers reset an Atlas robot?", "What does the warranty cover?")),
    (2, "Leave again", ("How much annual leave do we get?", "What is the parental leave policy?")),
    (1, "Release 4.2", ("What changed in release 4.2?", "Who do I page for a SEV1 incident?")),
    (
        0,
        "Planning",
        ("How many engineers are we hiring in FY2027?", "What was revenue in Q3 2026?"),
    ),
)


async def _person(container: Container, person: Person, password: str) -> User:
    async with container.db.session() as session:
        users = UserRepository(session)
        user = await users.by_email(person.email)
        if user is None:
            user = await users.add(
                User(
                    email=person.email,
                    name=person.name,
                    password_hash=await anyio.to_thread.run_sync(hash_password, password),
                    is_admin=person.admin,
                )
            )
            await session.commit()
        return user


async def _workspace(
    container: Container, owner: User, name: str, description: str, members: list[tuple[User, Role]]
) -> Workspace:
    async with container.db.session() as session:
        existing = (
            await session.execute(select(Workspace).where(Workspace.name == name))
        ).scalar_one_or_none()
        workspace = existing or await WorkspaceService(container, session).create(
            Principal(user=owner), name, description
        )
        repo = WorkspaceRepository(session)
        for user, role in members:
            if await repo.membership(workspace.id, user.id) is None:
                await repo.add_member(workspace.id, user.id, role)
        await session.commit()
        return workspace


def _sample_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))


async def _upload(
    container: Container, workspace: Workspace, uploader: User, files: list[Path]
) -> None:
    async with container.db.session() as session:
        incoming = [IncomingFile(path.name, path.read_bytes()) for path in files]
        outcome = await DocumentService(container, session).upload(
            workspace, Principal(user=uploader), incoming
        )
        for filename, _, message in outcome.rejected:
            log.warning("demo_file_rejected", filename=filename, reason=message)


async def _wait_until_indexed(container: Container, timeout_s: int = 600) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        async with container.db.session() as session:
            pending = (
                (
                    await session.execute(
                        select(Document.filename).where(
                            Document.status.in_([DocumentStatus.QUEUED, DocumentStatus.PROCESSING])
                        )
                    )
                )
                .scalars()
                .all()
            )
        if not pending:
            return
        print(f"  indexing... {len(pending)} file(s) left", flush=True)
        if isinstance(container.queue, InlineQueue):
            await container.queue.drain()
        await asyncio.sleep(2)
    raise TimeoutError("documents were not indexed in time; check `make logs SERVICE=worker`")


async def _ask(
    container: Container,
    workspace: Workspace,
    user: User,
    days_ago: int,
    title: str,
    questions: tuple[str, ...],
) -> None:
    async with container.db.session() as session:
        ws = await session.get(Workspace, workspace.id)
        if ws is None:
            return
        existing = (
            await session.execute(
                select(Conversation).where(
                    Conversation.workspace_id == ws.id, Conversation.title == title
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        chat = ChatService(container, session)
        conversation = await chat.create_conversation(ws, Principal(user=user), title, None)
        for question in questions:
            async for _ in chat.ask(ws, Principal(user=user), question, conversation=conversation):
                pass
        when = datetime.now(UTC) - timedelta(days=days_ago, hours=3)
        await session.execute(
            update(Message)
            .where(Message.conversation_id == conversation.id)
            .values(created_at=when)
        )
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(created_at=when, updated_at=when)
        )
        recent = (
            select(UsageEvent.id)
            .where(UsageEvent.workspace_id == ws.id)
            .order_by(UsageEvent.created_at.desc())
            .limit(len(questions))
        )
        await session.execute(
            update(UsageEvent).where(UsageEvent.id.in_(recent)).values(created_at=when)
        )
        await session.commit()


async def run(
    settings: Settings, samples: Path, password: str, *, ask_questions: bool = True
) -> None:
    container = build_container(settings)
    if isinstance(container.queue, InlineQueue):
        container.queue.bind(IngestionService(container).process)
    try:
        files = await anyio.to_thread.run_sync(_sample_files, samples)
        if not files:
            raise SystemExit(f"no sample documents in {samples}")
        people = {p.email: await _person(container, p, password) for p in PEOPLE}
        ava, leo, maya = (people[p.email] for p in PEOPLE)
        main = await _workspace(
            container, ava, *MAIN_WORKSPACE, [(leo, Role.EDITOR), (maya, Role.VIEWER)]
        )
        engineering = await _workspace(container, leo, *SECOND_WORKSPACE, [(ava, Role.EDITOR)])
        await _upload(container, main, ava, files)
        await _upload(
            container, engineering, leo, [f for f in files if f.name in ENGINEERING_FILES]
        )
        await _wait_until_indexed(container)
        if ask_questions:
            for index, (days_ago, title, questions) in enumerate(CONVERSATIONS):
                asker = (ava, leo, maya)[index % 3]
                await _ask(container, main, asker, days_ago, title, questions)
        async with container.db.session() as session:
            ws = await session.get(Workspace, main.id)
            if ws is None:
                raise RuntimeError("demo workspace disappeared while seeding")
            _, key = await ApiKeyService(container, session).create(
                ws, Principal(user=ava), "Demo integration", "viewer", 30
            )
        print("\nDemo ready. Sign in at", settings.web_url)
        for person in PEOPLE:
            print(f"  {person.email:<34} {person.role.value:<7} password: {password}")
        print(f"\n  API key (viewer, {MAIN_WORKSPACE[0]}): {key}")
        endpoint = f"{settings.api_url}/api/v1/workspaces/{main.slug}/ask"
        print(f"  curl -s {endpoint} \\")
        print(f"    -H 'authorization: Bearer {key}' -H 'content-type: application/json' \\")
        print('    -d \'{"question": "What is the parental leave policy?"}\'')
    finally:
        await container.close()


async def reindex(settings: Settings, workspace_slug: str | None) -> int:
    container = build_container(settings)
    try:
        async with container.db.session() as session:
            query = select(Document.id, Document.workspace_id)
            if workspace_slug:
                query = query.join(Workspace, Workspace.id == Document.workspace_id).where(
                    Workspace.slug == workspace_slug
                )
            rows = (await session.execute(query)).all()
            ids = [row.id for row in rows]
            if ids:
                await session.execute(
                    update(Document)
                    .where(Document.id.in_(ids))
                    .values(status=DocumentStatus.QUEUED, attempts=0, error=None)
                )
                await session.commit()
        if isinstance(container.queue, InlineQueue):
            container.queue.bind(IngestionService(container).process)
        for row in rows:
            await container.queue.enqueue(IngestJob(row.workspace_id, row.id))
        if isinstance(container.queue, InlineQueue):
            await container.queue.drain()
        return len(rows)
    finally:
        await container.close()
