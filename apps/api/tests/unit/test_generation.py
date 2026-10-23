import httpx
import pytest
import respx

from docmind.ai.generation import (
    ExtractiveGenerator,
    GenerationRequest,
    ModelGenerator,
    OllamaClient,
    OpenAICompatibleClient,
    Usage,
)
from docmind.ai.tokens import TokenCounter
from docmind.core.config import Settings
from docmind.core.errors import UpstreamError
from tests.unit.helpers import source

OPENAI = Settings(
    llm_provider="openai",
    llm_model="small-model",
    llm_base_url="https://llm.example/v1",
    llm_api_key="sk-test",
)
OLLAMA = Settings(llm_provider="ollama", llm_model="qwen3:4b", ollama_url="http://ollama:11434")


def _sse(*events: str) -> bytes:
    return "".join(f"data: {e}\n\n" for e in events).encode()


@respx.mock
async def test_openai_compatible_streaming_and_usage() -> None:
    respx.post("https://llm.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=_sse(
                '{"choices":[{"delta":{"content":"Leave is "}}]}',
                '{"choices":[{"delta":{"content":"24 days [1]."}}]}',
                '{"choices":[],"usage":{"prompt_tokens":120,"completion_tokens":9}}',
                "[DONE]",
            ),
            headers={"content-type": "text/event-stream"},
        )
    )
    client = OpenAICompatibleClient(OPENAI)
    usage = Usage()
    parts = [p async for p in client.stream([{"role": "user", "content": "q"}], usage)]
    assert "".join(parts) == "Leave is 24 days [1]."
    assert (usage.prompt_tokens, usage.completion_tokens) == (120, 9)
    await client.aclose()


@respx.mock
async def test_provider_errors_become_upstream_errors() -> None:
    respx.post("https://llm.example/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    client = OpenAICompatibleClient(OPENAI)
    with pytest.raises(UpstreamError, match="429"):
        _ = [p async for p in client.stream([{"role": "user", "content": "q"}], Usage())]
    await client.aclose()


@respx.mock
async def test_ollama_streaming_reads_ndjson() -> None:
    body = b'{"message":{"content":"Hello"}}\n{"message":{"content":" there"},"done":true,"prompt_eval_count":30,"eval_count":2}\n'
    respx.post("http://ollama:11434/api/chat").mock(return_value=httpx.Response(200, content=body))
    client = OllamaClient(OLLAMA)
    usage = Usage()
    assert (
        "".join([p async for p in client.stream([{"role": "user", "content": "hi"}], usage)])
        == "Hello there"
    )
    assert (usage.prompt_tokens, usage.completion_tokens) == (30, 2)
    await client.aclose()


@respx.mock
async def test_model_generator_counts_tokens_when_the_server_does_not() -> None:
    respx.post("https://llm.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, content=_sse('{"choices":[{"delta":{"content":"Answer [1]."}}]}', "[DONE]")
        )
    )
    generator = ModelGenerator(OpenAICompatibleClient(OPENAI), TokenCounter("heuristic"))
    usage = Usage()
    request = GenerationRequest("What?", [source("Some fact.", n=1)])
    assert "".join([p async for p in generator.stream(request, usage)]) == "Answer [1]."
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0
    assert generator.label == "openai:small-model"


async def test_extractive_generator_streams_line_by_line_without_a_model() -> None:
    generator = ExtractiveGenerator()
    sources = [
        source(
            "Key risks\n\n\N{BULLET} Supply risk one here\n\n\N{BULLET} Demand risk two here", n=1
        )
    ]
    parts = [
        p
        async for p in generator.stream(
            GenerationRequest("What are the key risks?", sources), Usage()
        )
    ]
    assert len(parts) == 2
    assert parts[1].startswith("\n- ")
    assert generator.uses_model is False
