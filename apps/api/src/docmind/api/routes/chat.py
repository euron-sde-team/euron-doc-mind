"""Conversations and answers, as JSON or as server-sent events.

Every answering endpoint has two forms: the plain path returns one JSON body when the
answer is complete; `/stream` sends `sources`, `delta`, `done` (or `error`) events as the
answer is produced.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from docmind.api.deps import ContainerDep, SessionDep, ViewerDep, WorkspaceContext, rate_limit
from docmind.core.errors import AppError, UpstreamError, error_body
from docmind.core.logging import get_logger
from docmind.models import Workspace
from docmind.repositories.conversations import ConversationRepository
from docmind.schemas.chat import (
    AnswerOut,
    AskRequest,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from docmind.services.chat import ChatEvent, ChatService
from docmind.services.container import Container

router = APIRouter(prefix="/api/v1/workspaces/{workspace}", tags=["chat"])
log = get_logger("docmind.chat.routes")
_limited = [Depends(rate_limit("chat", "rate_limit_chat"))]


def _message(message: Any) -> MessageOut:
    return MessageOut.model_validate(
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "citations": message.citations or [],
            "sources": message.sources or [],
            "usage": message.usage or None,
            "created_at": message.created_at,
        }
    )


async def _events(
    container: Container,
    ctx: WorkspaceContext,
    body: AskRequest,
    conversation_id: uuid.UUID | None,
) -> AsyncIterator[ChatEvent]:
    """Run one answer in its own session, so streaming never outlives the request's session."""
    async with container.db.session() as session:
        workspace = await session.get(Workspace, ctx.id)
        if workspace is None:
            yield ChatEvent("error", error_body("not_found", "Workspace not found."))
            return
        conversation = None
        if conversation_id is not None:
            conversation = await ConversationRepository(session).get(
                ctx.id, conversation_id, ctx.principal.user_id or uuid.UUID(int=0)
            )
            if conversation is None:
                yield ChatEvent("error", error_body("not_found", "Conversation not found."))
                return
        try:
            async for event in ChatService(container, session).ask(
                workspace,
                ctx.principal,
                body.question,
                conversation=conversation,
                document_ids=body.document_ids,
            ):
                yield event
        except AppError as exc:
            yield ChatEvent("error", error_body(exc.code, exc.message))
        except Exception:
            log.exception("answer_failed")
            yield ChatEvent(
                "error", error_body("internal_error", "Something went wrong on our side.")
            )


async def _collect(events: AsyncIterator[ChatEvent]) -> AnswerOut:
    async for event in events:
        if event.event == "error":
            error = event.data["error"]
            raise (
                AppError(error["message"], code=error["code"])
                if error["code"] != "upstream_error"
                else UpstreamError(error["message"])
            )
        if event.event == "done":
            return AnswerOut.model_validate(event.data)
    raise UpstreamError("The answer did not complete.")


def _sse(events: AsyncIterator[ChatEvent]) -> AsyncIterator[ServerSentEvent]:
    async def stream() -> AsyncIterator[ServerSentEvent]:
        async for event in events:
            yield ServerSentEvent(event=event.event, data=event.data)

    return stream()


@router.get("/conversations", summary="Your conversations in this workspace")
async def list_conversations(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationOut]:
    items = await ChatService(container, session).list_conversations(
        ctx.id, ctx.principal, limit=limit, offset=offset
    )
    return [ConversationOut.model_validate(c) for c in items]


@router.post("/conversations", summary="Start a conversation", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> ConversationOut:
    conversation = await ChatService(container, session).create_conversation(
        ctx.workspace, ctx.principal, body.title, body.document_ids
    )
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}", summary="One conversation")
async def get_conversation(
    conversation_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> ConversationOut:
    conversation = await ChatService(container, session).get_conversation(
        ctx.id, conversation_id, ctx.principal
    )
    return ConversationOut.model_validate(conversation)


@router.patch("/conversations/{conversation_id}", summary="Rename a conversation")
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
) -> ConversationOut:
    service = ChatService(container, session)
    conversation = await service.rename(
        await service.get_conversation(ctx.id, conversation_id, ctx.principal), body.title
    )
    return ConversationOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", summary="Delete a conversation", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> None:
    service = ChatService(container, session)
    await service.delete(await service.get_conversation(ctx.id, conversation_id, ctx.principal))


@router.get("/conversations/{conversation_id}/messages", summary="Messages, oldest first")
async def list_messages(
    conversation_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[MessageOut]:
    service = ChatService(container, session)
    conversation = await service.get_conversation(ctx.id, conversation_id, ctx.principal)
    return [_message(m) for m in await service.messages(conversation)]


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Ask in a conversation",
    dependencies=_limited,
)
async def ask_in_conversation(
    conversation_id: uuid.UUID,
    body: AskRequest,
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
) -> AnswerOut:
    await ChatService(container, session).get_conversation(ctx.id, conversation_id, ctx.principal)
    return await _collect(_events(container, ctx, body, conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    summary="Ask in a conversation, streamed as server-sent events",
    response_class=EventSourceResponse,
    dependencies=_limited,
)
async def ask_in_conversation_stream(
    conversation_id: uuid.UUID,
    body: AskRequest,
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
) -> AsyncIterator[ServerSentEvent]:
    await ChatService(container, session).get_conversation(ctx.id, conversation_id, ctx.principal)
    async for event in _sse(_events(container, ctx, body, conversation_id)):
        yield event


@router.post(
    "/ask", summary="One-off question, no conversation (works with API keys)", dependencies=_limited
)
async def ask(body: AskRequest, ctx: ViewerDep, container: ContainerDep) -> AnswerOut:
    return await _collect(_events(container, ctx, body, None))


@router.post(
    "/ask/stream",
    summary="One-off question, streamed as server-sent events",
    response_class=EventSourceResponse,
    dependencies=_limited,
)
async def ask_stream(
    body: AskRequest, ctx: ViewerDep, container: ContainerDep
) -> AsyncIterator[ServerSentEvent]:
    async for event in _sse(_events(container, ctx, body, None)):
        yield event
