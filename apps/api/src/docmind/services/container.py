"""Process-wide infrastructure, built once at startup and shared by every request.

Services are cheap objects created per request around one database session; everything
expensive (connection pools, the embedding model, HTTP clients) lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from docmind.ai.embeddings import CachedEmbedder, Embedder, LocalEmbedder, build_embedder
from docmind.ai.generation import (
    ChatClient,
    ExtractiveGenerator,
    Generator,
    ModelGenerator,
    build_chat_client,
)
from docmind.ai.tokens import TokenCounter
from docmind.core.config import Settings
from docmind.core.ratelimit import RateLimiter
from docmind.db.session import Database
from docmind.integrations.queue import InlineQueue, SqsQueue, build_queue
from docmind.integrations.storage import Storage, build_storage


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    storage: Storage
    queue: InlineQueue | SqsQueue
    embedder: Embedder
    base_embedder: Embedder
    tokens: TokenCounter
    generator: Generator
    extractive: ExtractiveGenerator
    chat_client: ChatClient | None
    limiter: RateLimiter

    async def close(self) -> None:
        if self.chat_client is not None:
            await self.chat_client.aclose()
        closer = getattr(self.base_embedder, "aclose", None)
        if closer is not None:
            await closer()
        await self.redis.aclose()
        await self.db.dispose()

    async def warm_up(self) -> None:
        if isinstance(self.base_embedder, LocalEmbedder):
            await self.base_embedder.warm_up()


def build_container(settings: Settings) -> Container:
    redis = Redis.from_url(
        settings.redis_url, decode_responses=False, health_check_interval=30, socket_timeout=5
    )
    tokens = TokenCounter(settings.tokenizer)
    base_embedder = build_embedder(settings)
    chat_client = build_chat_client(settings)
    embedder = CachedEmbedder(base_embedder, redis, settings.embedding_cache_ttl_s)
    extractive = ExtractiveGenerator(embedder)
    generator: Generator = ModelGenerator(chat_client, tokens) if chat_client else extractive
    return Container(
        settings=settings,
        db=Database(settings),
        redis=redis,
        storage=build_storage(settings),
        queue=build_queue(settings),
        embedder=embedder,
        base_embedder=base_embedder,
        tokens=tokens,
        generator=generator,
        extractive=extractive,
        chat_client=chat_client,
        limiter=RateLimiter(redis),
    )
