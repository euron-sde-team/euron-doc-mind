from __future__ import annotations

import uuid

from sqlalchemy import func, select, update

from docmind.models import Conversation, Message
from docmind.repositories.base import Repository


class ConversationRepository(Repository):
    async def get(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def recent(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id, Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def messages(self, conversation_id: uuid.UUID, *, limit: int = 200) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def add_message(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == message.conversation_id)
            .values(message_count=Conversation.message_count + 1, updated_at=func.now())
        )
        await self.session.flush()
        return message
