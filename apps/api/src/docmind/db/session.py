"""Async engine and session factory.

The pgvector codec is registered on every new connection so embeddings travel in binary
form (numpy arrays in, numpy arrays out) instead of being formatted as text.
"""

from __future__ import annotations

from typing import Any

from pgvector.asyncpg import register_vector
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from docmind.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=settings.database_echo,
            connect_args={
                # JIT compilation costs more than it saves on short OLTP queries.
                "server_settings": {"application_name": "docmind", "jit": "off"},
            },
        )
        event.listen(self.engine.sync_engine, "connect", _register_codecs)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    def session(self) -> AsyncSession:
        return self.sessionmaker()

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()


def _register_codecs(dbapi_connection: Any, _: Any) -> None:
    dbapi_connection.run_async(register_vector)
