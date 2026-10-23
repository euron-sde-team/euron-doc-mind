"""Embedding providers behind one interface, with a shared Redis cache.

| Provider | Runs | Use |
| local    | in process, ONNX (fastembed), no network after the model is cached | default |
| openai   | any OpenAI-compatible /embeddings endpoint, truncated to EMBEDDING_DIM | hosted |
| ollama   | a local Ollama server (/api/embed) | local GPU or CPU |
| hash     | deterministic feature hashing, lexical only | tests |

Every vector is L2-normalised, so cosine similarity is a dot product everywhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

import anyio
import httpx
import numpy as np
from redis.asyncio import Redis

from docmind.core import metrics
from docmind.core.config import Settings
from docmind.core.errors import UpstreamError
from docmind.core.logging import get_logger
from docmind.core.text import content_terms

log = get_logger("docmind.embeddings")
Matrix = np.ndarray[Any, np.dtype[np.float32]]

# bge v1.5 retrieves best when short queries carry this instruction; passages do not.
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def first_row(matrix: Matrix) -> Matrix:
    row: Matrix = matrix[0]
    return row


def normalize_rows(matrix: Matrix) -> Matrix:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized: Matrix = (matrix / norms).astype(np.float32)
    return normalized


class Embedder(Protocol):
    name: str
    dim: int

    async def embed_documents(self, texts: Sequence[str]) -> Matrix: ...

    async def embed_query(self, text: str) -> Matrix: ...


class HashEmbedder:
    """Signed feature hashing of stemmed words and word pairs. Tests only."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vector(self, text: str) -> Matrix:
        terms = content_terms(text)
        features = Counter(terms)
        features.update({f"{a} {b}": 0.5 for a, b in pairwise(terms)})
        vector = np.zeros(self.dim, dtype=np.float32)
        for feature, weight in features.items():
            digest = int.from_bytes(
                hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little"
            )
            sign = 1.0 if digest >> 63 else -1.0
            vector[digest % self.dim] += (
                sign * (1 + math.log(weight)) if weight >= 1 else sign * weight
            )
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return normalize_rows(np.stack([self._vector(t) for t in texts]).astype(np.float32))

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))


class LocalEmbedder:
    """fastembed (ONNX Runtime) in a worker thread; the model loads once per process."""

    def __init__(self, model: str, dim: int, cache_dir: Path | None, batch_size: int) -> None:
        self.name = model
        self.dim = dim
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._batch_size = batch_size
        self._model: Any = None
        self._lock = asyncio.Lock()
        self._query_prefix = _BGE_QUERY_INSTRUCTION if "bge" in model.lower() else ""

    async def _load(self) -> Any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = await anyio.to_thread.run_sync(
                        lambda: TextEmbedding(model_name=self.name, cache_dir=self._cache_dir)
                    )
                    log.info("embedding_model_loaded", model=self.name)
        return self._model

    async def warm_up(self) -> None:
        await self.embed_query("warm up")

    async def _embed(self, texts: Sequence[str]) -> Matrix:
        model = await self._load()
        vectors = await anyio.to_thread.run_sync(
            lambda: list(model.embed(list(texts), batch_size=self._batch_size))
        )
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape[1] != self.dim:
            raise ValueError(
                f"{self.name} produces {matrix.shape[1]} dims; EMBEDDING_DIM is {self.dim}"
            )
        return normalize_rows(matrix)

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return await self._embed(texts)

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._embed([self._query_prefix + text]))


class OpenAIEmbedder:
    def __init__(
        self, base_url: str, api_key: str | None, model: str, dim: int, timeout: float
    ) -> None:
        self.name = model
        self.dim = dim
        headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self.name, "input": list(texts), "dimensions": self.dim},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The embedding provider request failed.") from exc
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return normalize_rows(np.asarray([item["embedding"] for item in data], dtype=np.float32))

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaEmbedder:
    def __init__(self, url: str, model: str, dim: int, timeout: float) -> None:
        self.name = model
        self.dim = dim
        self._client = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=timeout)

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        try:
            response = await self._client.post(
                "/api/embed", json={"model": self.name, "input": list(texts)}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The Ollama embedding request failed.") from exc
        matrix = np.asarray(response.json()["embeddings"], dtype=np.float32)
        if matrix.shape[1] != self.dim:
            raise UpstreamError(
                f"{self.name} produces {matrix.shape[1]} dims; EMBEDDING_DIM is {self.dim}."
            )
        return normalize_rows(matrix)

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class CachedEmbedder:
    """Read-through Redis cache keyed by model, width and the SHA-256 of the text.

    Re-uploading a file, uploading the same paragraph in two documents, or asking a popular
    question again costs one Redis round trip instead of a model call.
    """

    def __init__(self, inner: Embedder, redis: Redis, ttl_s: int) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self._redis = redis
        self._ttl = ttl_s

    def _key(self, text: str, kind: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        return f"emb:{self.name}:{self.dim}:{kind}:{digest}"

    async def _cached(self, texts: Sequence[str], kind: str) -> Matrix:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        keys = [self._key(t, kind) for t in texts]
        try:
            stored = await self._redis.mget(keys)
        except Exception:
            stored = [None] * len(texts)
        result = np.zeros((len(texts), self.dim), dtype=np.float32)
        missing = [i for i, raw in enumerate(stored) if raw is None]
        for i, raw in enumerate(stored):
            if raw is not None:
                buffer = raw.encode("latin-1") if isinstance(raw, str) else raw
                result[i] = np.frombuffer(buffer, dtype=np.float32)
        metrics.EMBEDDING_CACHE.labels("hit").inc(len(texts) - len(missing))
        metrics.EMBEDDING_CACHE.labels("miss").inc(len(missing))
        if missing:
            fresh = (
                await self.inner.embed_documents([texts[i] for i in missing])
                if kind == "doc"
                else np.stack([await self.inner.embed_query(texts[i]) for i in missing])
            )
            for row, i in enumerate(missing):
                result[i] = fresh[row]
            try:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for row, i in enumerate(missing):
                        pipe.set(keys[i], fresh[row].tobytes(), ex=self._ttl or None)
                    await pipe.execute()
            except Exception:
                log.warning("embedding_cache_write_failed")
        return result

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        return await self._cached(texts, "doc")

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._cached([text], "query"))


def build_embedder(settings: Settings) -> Embedder:
    match settings.embeddings_provider:
        case "hash":
            return HashEmbedder(settings.embedding_dim)
        case "openai":
            key = (
                settings.embeddings_api_key.get_secret_value()
                if settings.embeddings_api_key
                else None
            )
            return OpenAIEmbedder(
                settings.embeddings_api_base,
                key,
                settings.embeddings_model,
                settings.embedding_dim,
                60.0,
            )
        case "ollama":
            return OllamaEmbedder(
                settings.ollama_url, settings.embeddings_model, settings.embedding_dim, 60.0
            )
        case _:
            return LocalEmbedder(
                settings.embeddings_model,
                settings.embedding_dim,
                settings.embeddings_cache_dir,
                settings.embeddings_batch_size,
            )
