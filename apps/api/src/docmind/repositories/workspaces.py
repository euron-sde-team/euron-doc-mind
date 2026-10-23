from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update

from docmind.models import Document, Membership, User, Workspace
from docmind.models.enums import DocumentStatus, Role
from docmind.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    workspace: Workspace
    role: str
    document_count: int
    member_count: int


class WorkspaceRepository(Repository):
    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self.session.get(Workspace, workspace_id)

    async def by_slug(self, slug: str) -> Workspace | None:
        result = await self.session.execute(select(Workspace).where(Workspace.slug == slug))
        return result.scalar_one_or_none()

    async def slug_taken(self, slug: str) -> bool:
        return bool(await self.session.scalar(select(func.count()).where(Workspace.slug == slug)))

    async def add(self, workspace: Workspace) -> Workspace:
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def membership(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
        return await self.session.get(Membership, (workspace_id, user_id))

    async def for_user(self, user_id: uuid.UUID) -> list[WorkspaceSummary]:
        documents = (
            select(func.count())
            .where(Document.workspace_id == Workspace.id, Document.status == DocumentStatus.READY)
            .scalar_subquery()
        )
        members = (
            select(func.count()).where(Membership.workspace_id == Workspace.id).scalar_subquery()
        )
        result = await self.session.execute(
            select(Workspace, Membership.role, documents, members)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
            .order_by(Workspace.name)
        )
        return [WorkspaceSummary(w, role, docs, people) for w, role, docs, people in result.all()]

    async def members(self, workspace_id: uuid.UUID) -> list[tuple[Membership, User]]:
        result = await self.session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == workspace_id)
            .order_by(Membership.created_at)
        )
        return [(m, u) for m, u in result.all()]

    async def owner_count(self, workspace_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(
                    Membership.workspace_id == workspace_id, Membership.role == Role.OWNER
                )
            )
            or 0
        )

    async def add_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, role: Role
    ) -> Membership:
        membership = Membership(workspace_id=workspace_id, user_id=user_id, role=role.value)
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def bump_corpus_version(self, workspace_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Workspace)
            .where(Workspace.id == workspace_id)
            .values(corpus_version=Workspace.corpus_version + 1)
        )
