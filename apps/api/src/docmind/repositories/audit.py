from __future__ import annotations

import uuid

from sqlalchemy import select

from docmind.models import AuditEvent, User
from docmind.repositories.base import Repository


class AuditRepository(Repository):
    async def add(self, event: AuditEvent) -> None:
        self.session.add(event)

    async def recent(
        self, workspace_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[tuple[AuditEvent, str | None]]:
        result = await self.session.execute(
            select(AuditEvent, User.name)
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.workspace_id == workspace_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(event, name) for event, name in result.all()]
