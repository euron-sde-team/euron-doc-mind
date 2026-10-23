from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from docmind.models import AuditEvent
from docmind.repositories.audit import AuditRepository
from docmind.services.principal import Principal


async def record(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    principal: Principal | None,
    action: str,
    target_type: str,
    target_id: object | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the caller's transaction (it commits with the change it records)."""
    await AuditRepository(session).add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=principal.user_id if principal else None,
            actor_api_key_id=principal.api_key_id if principal else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
        )
    )
