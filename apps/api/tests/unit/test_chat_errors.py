"""Answer errors keep their HTTP meaning in the JSON (non-streaming) endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from docmind.api.routes.chat import _collect
from docmind.core.errors import NotFoundError, UnprocessableError, UpstreamError
from docmind.services.chat import ChatEvent


async def _stream(*events: ChatEvent) -> AsyncIterator[ChatEvent]:
    for event in events:
        yield event


async def test_an_error_event_raises_the_error_behind_it() -> None:
    failure = ChatEvent.failure(UnprocessableError("Nothing is ready.", code="empty_scope"))

    with pytest.raises(UnprocessableError) as caught:
        await _collect(_stream(ChatEvent("sources", {"sources": []}), failure))

    assert caught.value.status_code == 422
    assert caught.value.code == "empty_scope"


async def test_a_stream_that_ends_without_an_answer_is_an_upstream_error() -> None:
    with pytest.raises(UpstreamError):
        await _collect(_stream(ChatEvent("sources", {"sources": []})))


def test_error_events_carry_the_standard_envelope() -> None:
    event = ChatEvent.failure(NotFoundError("Conversation not found."))

    assert event.event == "error"
    assert event.data["error"]["code"] == "not_found"
    assert event.data["error"]["message"] == "Conversation not found."

