"""Answer generators: the offline extractive answerer and chat models.

Every generator streams text deltas and fills in a `Usage` as it goes, so the chat service
handles all of them the same way.

Model clients speak two wire formats: the OpenAI-compatible Chat Completions API (OpenAI,
Groq, Together, Mistral, DeepSeek, OpenRouter, vLLM, LM Studio and others) and Ollama's
native /api/chat.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import orjson

from docmind.ai.embeddings import Embedder
from docmind.ai.extractive import answer_units, extractive_answer
from docmind.ai.prompts import Turn, answer_messages
from docmind.ai.sources import Source
from docmind.ai.tokens import TokenCounter
from docmind.core.config import Settings
from docmind.core.errors import UpstreamError
from docmind.core.logging import get_logger

log = get_logger("docmind.generation")


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(slots=True)
class GenerationRequest:
    question: str
    sources: list[Source]
    history: list[Turn] = field(default_factory=list)


class ChatClient(Protocol):
    provider: str
    model: str

    def stream(self, messages: list[dict[str, str]], usage: Usage) -> AsyncIterator[str]: ...

    async def complete(self, messages: list[dict[str, str]], max_tokens: int = 120) -> str: ...

    async def aclose(self) -> None: ...


class Generator(Protocol):
    label: str
    uses_model: bool
    # Bumped whenever answering changes (algorithm or prompt); part of the answer-cache key,
    # so an upgrade never serves answers produced by the previous version.
    version: str

    def stream(self, request: GenerationRequest, usage: Usage) -> AsyncIterator[str]: ...


class ExtractiveGenerator:
    label = "extractive"
    uses_model = False
    version = "4"

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder

    async def stream(self, request: GenerationRequest, usage: Usage) -> AsyncIterator[str]:
        units = answer_units(request.sources)
        similarities = None
        if self.embedder is not None and units:
            try:
                vectors = await self.embedder.embed_documents([unit.text for unit in units])
                similarities = vectors @ await self.embedder.embed_query(request.question)
            except Exception:
                log.warning("extractive_semantic_scoring_unavailable")
        answer = extractive_answer(
            request.question, request.sources, units=units, similarities=similarities
        )
        # Emit line by line so the client renders this path like a model stream.
        for index, part in enumerate(answer.text.split("\n")):
            yield part if index == 0 else "\n" + part
            await asyncio.sleep(0)


class ModelGenerator:
    uses_model = True
    version = "3"

    def __init__(self, client: ChatClient, counter: TokenCounter) -> None:
        self.client = client
        self.counter = counter
        self.label = f"{client.provider}:{client.model}"

    async def stream(self, request: GenerationRequest, usage: Usage) -> AsyncIterator[str]:
        messages = answer_messages(request.question, request.sources, request.history)
        produced: list[str] = []
        async for delta in self.client.stream(messages, usage):
            produced.append(delta)
            yield delta
        # Some servers do not report usage on streams; count it ourselves when missing.
        if not usage.prompt_tokens:
            usage.prompt_tokens = sum(self.counter.count(m["content"]) for m in messages)
        if not usage.completion_tokens:
            usage.completion_tokens = self.counter.count("".join(produced))


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"authorization": f"Bearer {key}"} if key else {},
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def stream(self, messages: list[dict[str, str]], usage: Usage) -> AsyncIterator[str]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as response:
                if response.status_code >= 400:
                    detail = (await response.aread())[:300].decode(errors="replace")
                    log.warning("llm_error", status=response.status_code, detail=detail)
                    raise UpstreamError(f"The model provider returned HTTP {response.status_code}.")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    event = orjson.loads(payload)
                    if event.get("usage"):
                        usage.prompt_tokens = event["usage"].get("prompt_tokens", 0)
                        usage.completion_tokens = event["usage"].get("completion_tokens", 0)
                    for choice in event.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise UpstreamError("The model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The model provider could not be reached.") from exc

    async def complete(self, messages: list[dict[str, str]], max_tokens: int = 120) -> str:
        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The model provider request failed.") from exc
        content: str = response.json()["choices"][0]["message"]["content"] or ""
        return content.strip()

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaClient:
    provider = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.llm_model
        self._options = {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_tokens,
        }
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def stream(self, messages: list[dict[str, str]], usage: Usage) -> AsyncIterator[str]:
        body = {"model": self.model, "messages": messages, "stream": True, "options": self._options}
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as response:
                if response.status_code >= 400:
                    raise UpstreamError(f"Ollama returned HTTP {response.status_code}.")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = orjson.loads(line)
                    delta = (event.get("message") or {}).get("content")
                    if delta:
                        yield delta
                    if event.get("done"):
                        usage.prompt_tokens = event.get("prompt_eval_count", 0)
                        usage.completion_tokens = event.get("eval_count", 0)
        except httpx.TimeoutException as exc:
            raise UpstreamError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("Ollama could not be reached.") from exc

    async def complete(self, messages: list[dict[str, str]], max_tokens: int = 120) -> str:
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": max_tokens},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The Ollama request failed.") from exc
        content: str = response.json()["message"]["content"]
        return content.strip()

    async def aclose(self) -> None:
        await self._client.aclose()


def build_chat_client(settings: Settings) -> ChatClient | None:
    if settings.llm_provider == "openai":
        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "ollama":
        return OllamaClient(settings)
    return None
