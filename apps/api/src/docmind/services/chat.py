"""Questions in, cited answers out.

    cache (exact, then semantic) -> retrieval -> generation (streamed) -> citations
    -> persist message and usage -> cache the answer

`ask` yields events that the route sends as server-sent events, or collects into one JSON
response. Every answer records the token arithmetic behind the savings meter: the tokens
of every document in scope (what pasting them all would cost) against the tokens the
answer actually used.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from docmind.ai.citations import extract_citations
from docmind.ai.extractive import NOT_FOUND
from docmind.ai.generation import GenerationRequest, Generator, Usage
from docmind.ai.prompts import Turn, condense_messages, heuristic_standalone, is_follow_up
from docmind.core import metrics
from docmind.core.errors import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
    error_body,
)
from docmind.core.ids import uuid7
from docmind.core.logging import get_logger
from docmind.core.text import truncate
from docmind.models import Conversation, Message, UsageEvent, Workspace
from docmind.models.enums import CacheResult, MessageRole, UsageKind
from docmind.repositories.conversations import ConversationRepository
from docmind.repositories.documents import DocumentRepository
from docmind.repositories.usage import UsageRepository
from docmind.schemas.workspaces import WorkspaceSettings
from docmind.services.answer_cache import AnswerCache, CacheKey, scope_hash
from docmind.services.container import Container
from docmind.services.principal import Principal
from docmind.services.retrieval import RetrievalService

log = get_logger("docmind.chat")
DEFAULT_TITLE = "New conversation"
NO_DOCUMENTS = (
    "There are no ready documents to answer from yet. Upload files on the Documents page first."
)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    event: str
    data: dict[str, Any]
    # The exception behind an "error" event, so a JSON response keeps its status code.
    error: AppError | None = field(default=None, compare=False, repr=False)

    @classmethod
    def failure(cls, exc: AppError) -> ChatEvent:
        return cls("error", error_body(exc.code, exc.message), exc)


class ChatService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.conversations = ConversationRepository(session)
        self.documents = DocumentRepository(session)

    async def validated_scope(
        self, workspace_id: uuid.UUID, document_ids: Sequence[uuid.UUID] | None
    ) -> list[uuid.UUID] | None:
        """Only ready documents of this workspace; ids from elsewhere are silently dropped."""
        if not document_ids:
            return None
        ready = await self.documents.ready_ids(workspace_id, list(dict.fromkeys(document_ids)))
        if not ready:
            raise UnprocessableError(
                "None of the selected documents are ready yet.", code="empty_scope"
            )
        return ready

    async def create_conversation(
        self,
        workspace: Workspace,
        principal: Principal,
        title: str | None,
        document_ids: Sequence[uuid.UUID] | None,
    ) -> Conversation:
        if principal.user is None:
            raise ForbiddenError("API keys cannot own conversations. Use the ask endpoint.")
        conversation = await self.conversations.add(
            Conversation(
                workspace_id=workspace.id,
                user_id=principal.user.id,
                title=(title or DEFAULT_TITLE).strip()[:200],
                document_ids=await self.validated_scope(workspace.id, document_ids),
            )
        )
        await self.session.commit()
        return conversation

    async def get_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID, principal: Principal
    ) -> Conversation:
        if principal.user is None:
            raise NotFoundError("Conversation not found.")
        conversation = await self.conversations.get(
            workspace_id, conversation_id, principal.user.id
        )
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def list_conversations(
        self, workspace_id: uuid.UUID, principal: Principal, *, limit: int, offset: int
    ) -> list[Conversation]:
        if principal.user is None:
            return []
        return await self.conversations.recent(
            workspace_id, principal.user.id, limit=limit, offset=offset
        )

    async def rename(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title.strip()[:200]
        await self.session.commit()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)
        await self.session.commit()

    async def messages(self, conversation: Conversation) -> list[Message]:
        return await self.conversations.messages(conversation.id)

    async def _standalone(self, question: str, history: list[Turn], generator: Generator) -> str:
        if not history or not is_follow_up(question):
            return question
        if generator.uses_model and self.c.chat_client is not None:
            try:
                rewritten = await self.c.chat_client.complete(condense_messages(question, history))
                if rewritten:
                    return rewritten[:500]
            except AppError:
                log.warning("condense_failed_using_heuristic")
        return heuristic_standalone(question, history)

    async def ask(
        self,
        workspace: Workspace,
        principal: Principal,
        question: str,
        *,
        conversation: Conversation | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> AsyncGenerator[ChatEvent]:
        started = time.perf_counter()
        question = question.strip()
        prefs = WorkspaceSettings.model_validate(workspace.settings)
        generator: Generator = (
            self.c.generator if prefs.answer_mode == "auto" else self.c.extractive
        )
        scope = (
            conversation.document_ids
            if conversation is not None
            else await self.validated_scope(workspace.id, document_ids)
        )

        history: list[Turn] = []
        if conversation is not None:
            previous = await self.conversations.messages(conversation.id, limit=40)
            history = [Turn(m.role, m.content) for m in previous[-6:]]
            if conversation.message_count == 0 and conversation.title == DEFAULT_TITLE:
                conversation.title = truncate(question, 80)
            user_message = await self.conversations.add_message(
                Message(conversation_id=conversation.id, role=MessageRole.USER, content=question)
            )
            await self.session.commit()
            yield ChatEvent("user_message", {"id": str(user_message.id), "content": question})

        standalone = await self._standalone(question, history, generator)
        vector = await self.c.embedder.embed_query(standalone)
        baseline = await self.documents.ready_token_total(
            workspace.id, scope
        ) + self.c.tokens.count(question)
        key = CacheKey(
            workspace.id,
            workspace.corpus_version,
            f"{generator.label}#{generator.version}",
            scope_hash(scope),
        )
        cache = AnswerCache(self.c, self.session)
        cached = await cache.lookup(key, standalone, vector) if prefs.cache_enabled else None

        usage = Usage()
        if cached is not None:
            sources_public = cached.sources
            yield ChatEvent("sources", {"sources": sources_public})
            yield ChatEvent("delta", {"text": cached.answer})
            answer, citations = cached.answer, cached.citations
            context_tokens, cache_result = 0, cached.result
        else:
            retrieval = RetrievalService(self.c, self.session)
            sources = await retrieval.retrieve(
                workspace.id,
                standalone,
                scope,
                top_k=prefs.top_k,
                budget=prefs.context_token_budget or self.c.settings.context_token_budget,
                query_vector=vector,
            )
            sources_public = [s.public() for s in sources]
            yield ChatEvent("sources", {"sources": sources_public})
            parts: list[str] = []
            if sources:
                generation_started = time.perf_counter()
                try:
                    request = GenerationRequest(standalone, sources, history)
                    async for delta in generator.stream(request, usage):
                        parts.append(delta)
                        yield ChatEvent("delta", {"text": delta})
                except AppError as exc:
                    log.warning("generation_failed", code=exc.code)
                    yield ChatEvent.failure(exc)
                    return
                metrics.GENERATION_DURATION.labels(generator.label.split(":")[0]).observe(
                    time.perf_counter() - generation_started
                )
            else:
                parts.append(
                    NO_DOCUMENTS if baseline <= self.c.tokens.count(question) else NOT_FOUND
                )
                yield ChatEvent("delta", {"text": parts[0]})
            answer, citations = extract_citations("".join(parts), sources)
            context_tokens, cache_result = sum(s.token_count for s in sources), CacheResult.MISS
            if prefs.cache_enabled and citations and not answer.startswith(NOT_FOUND):
                await cache.store(
                    key,
                    standalone,
                    vector,
                    answer=answer,
                    citations=citations,
                    sources=sources_public,
                    context_tokens=context_tokens,
                )

        saved = max(0, baseline - context_tokens)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage_payload = {
            "generator": generator.label,
            "cache": cache_result.value,
            "context_tokens": context_tokens,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "baseline_tokens": baseline,
            "saved_tokens": saved,
            "saved_ratio": round(saved / baseline, 4) if baseline else 0.0,
            "latency_ms": latency_ms,
        }
        message_id, created_at = uuid7(), datetime.now(UTC)
        if conversation is not None:
            stored = await self.conversations.add_message(
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    citations=citations,
                    sources=sources_public,
                    usage=usage_payload,
                )
            )
            message_id, created_at = stored.id, stored.created_at
        cited = list(dict.fromkeys(uuid.UUID(c["document_id"]) for c in citations))
        await UsageRepository(self.session).add(
            UsageEvent(
                workspace_id=workspace.id,
                user_id=principal.user_id,
                api_key_id=principal.api_key_id,
                kind=UsageKind.ANSWER,
                cache=cache_result.value,
                generator=generator.label,
                context_tokens=context_tokens,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                baseline_tokens=baseline,
                saved_tokens=saved,
                latency_ms=latency_ms,
                cited_document_ids=cited,
            )
        )
        await self.session.commit()
        for kind, value in (
            ("context", context_tokens),
            ("prompt", usage.prompt_tokens),
            ("completion", usage.completion_tokens),
            ("baseline", baseline),
            ("saved", saved),
        ):
            metrics.TOKENS.labels(kind).inc(value)

        yield ChatEvent(
            "done",
            {
                "conversation_id": str(conversation.id) if conversation else None,
                "message": {
                    "id": str(message_id),
                    "role": MessageRole.ASSISTANT.value,
                    "content": answer,
                    "citations": citations,
                    "sources": sources_public,
                    "usage": usage_payload,
                    "created_at": (created_at or datetime.now(UTC)).isoformat(),
                },
            },
        )
