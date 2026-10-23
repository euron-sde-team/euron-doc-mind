import fakeredis
import httpx
import numpy as np
import pytest
import respx

from docmind.ai.embeddings import CachedEmbedder, HashEmbedder, OllamaEmbedder, OpenAIEmbedder
from docmind.core.errors import UpstreamError


async def test_hash_embeddings_are_deterministic_normalised_and_lexical() -> None:
    embedder = HashEmbedder(128)
    a, b, c = await embedder.embed_documents(
        ["annual leave policy", "annual leave policy", "robot payload"]
    )
    assert np.allclose(a, b)
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5
    query = await embedder.embed_query("leave policy")
    assert float(query @ a) > float(query @ c)


class CountingEmbedder(HashEmbedder):
    def __init__(self) -> None:
        super().__init__(64)
        self.calls = 0

    async def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        self.calls += len(texts)
        return await super().embed_documents(texts)


async def test_cache_serves_repeats_without_calling_the_model() -> None:
    inner = CountingEmbedder()
    cached = CachedEmbedder(inner, fakeredis.FakeAsyncRedis(), ttl_s=60)
    first = await cached.embed_documents(["one", "two"])
    second = await cached.embed_documents(["two", "one", "three"])
    assert inner.calls == 3
    assert np.allclose(first[0], second[1])
    assert np.allclose(first[1], second[0])


@respx.mock
async def test_openai_embeddings_request_the_configured_width() -> None:
    route = respx.post("https://llm.example/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 2.0]},
                    {"index": 0, "embedding": [3.0, 4.0]},
                ]
            },
        )
    )
    embedder = OpenAIEmbedder("https://llm.example/v1", "sk-test", "text-embedding-3-small", 2, 5.0)
    vectors = await embedder.embed_documents(["a", "b"])
    assert route.calls.last.request.read().count(b'"dimensions":2') == 1
    assert np.allclose(vectors[0], [0.6, 0.8])
    assert np.allclose(vectors[1], [0.0, 1.0])
    await embedder.aclose()


@respx.mock
async def test_ollama_width_mismatch_is_reported() -> None:
    respx.post("http://ollama:11434/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[1.0, 0.0, 0.0]]})
    )
    embedder = OllamaEmbedder("http://ollama:11434", "nomic-embed-text", 2, 5.0)
    with pytest.raises(UpstreamError, match="dims"):
        await embedder.embed_documents(["a"])
    await embedder.aclose()
