"""Answers, citations, follow-ups, streaming and search over the indexed sample corpus."""

from __future__ import annotations

import re

import httpx
import pytest

from tests.integration.conftest import Corpus
from tests.integration.support import ask, parse_sse

pytestmark = pytest.mark.integration

# (question, a fact the answer must state, the document it must cite)
GROUNDED = [
    (
        "How many days of annual leave do employees get?",
        "24 working days",
        "Northwind Employee Handbook 2026",
    ),
    (
        "What is the daily meal allowance when travelling?",
        "$75",
        "Northwind Employee Handbook 2026",
    ),
    ("What was revenue in Q3 2026?", "$18.4M", "Q3 2026 Board Update"),
    (
        "Who do I page for a SEV1 incident?",
        "incident commander",
        "Security Incident Response Runbook",
    ),
    ("What payload must Atlas v2 carry?", "35 kg", "Atlas v2 Product Requirements"),
    ("Which warehouse pilot had the best pick rate?", "Rotterdam", "warehouse-pilot-results"),
    (
        "How much notice is needed to terminate the Globex agreement?",
        "90 days",
        "Globex Master Services Agreement",
    ),
    ("What does the warranty cover?", "24-month warranty", "Atlas Customer Support FAQ"),
]


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize(("question", "fact", "title"), GROUNDED)
async def test_answers_state_the_fact_and_cite_its_document(
    client: httpx.AsyncClient, corpus: Corpus, question: str, fact: str, title: str
) -> None:
    message = await ask(client, corpus.owner.headers, corpus.workspace, question)

    assert fact in message["content"]
    assert title in {c["document_title"] for c in message["citations"]}
    assert message["usage"]["generator"].startswith("extractive")
    # Retrieval sends a fraction of the library to the answerer, never all of it.
    assert 0 < message["usage"]["context_tokens"] < message["usage"]["baseline_tokens"]


async def test_every_citation_points_at_the_passage_it_quotes(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    message = await ask(
        client, corpus.owner.headers, corpus.workspace, "What is the parental leave policy?"
    )
    assert message["citations"]
    for citation in message["citations"]:
        assert f"[{citation['n']}]" in message["content"]
        document = (
            await client.get(
                f"/api/v1/workspaces/{corpus.workspace}/documents/{citation['document_id']}",
                headers=corpus.owner.headers,
            )
        ).json()
        section = document["sections"][citation["section_ordinal"]]
        passage = section["text"][citation["char_start"] : citation["char_end"]]
        assert _squash(citation["quote"].removesuffix("...")) in _squash(passage)


async def test_a_question_the_documents_cannot_answer_says_so(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    message = await ask(
        client, corpus.owner.headers, corpus.workspace, "What is the capital of France?"
    )
    assert message["content"].startswith("I could not find a clear answer")


async def test_scoping_to_one_document_only_cites_that_document(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    runbook = corpus.document_id("Security Incident Response Runbook.md")
    message = await ask(
        client,
        corpus.owner.headers,
        corpus.workspace,
        "How quickly must an incident be acknowledged?",
        document_ids=[runbook],
    )
    assert message["citations"]
    assert {c["document_id"] for c in message["citations"]} == {runbook}


async def test_follow_up_questions_use_the_conversation(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    base = f"/api/v1/workspaces/{corpus.workspace}/conversations"
    conversation = (
        await client.post(base, json={"title": "Parental leave"}, headers=corpus.owner.headers)
    ).json()
    url = f"{base}/{conversation['id']}/messages"

    first = await client.post(
        url, json={"question": "What is the parental leave policy?"}, headers=corpus.owner.headers
    )
    follow_up = await client.post(
        url, json={"question": "How long does it last?"}, headers=corpus.owner.headers
    )

    assert "26 weeks" in first.json()["message"]["content"]
    assert "26 weeks" in follow_up.json()["message"]["content"]
    messages = (await client.get(url, headers=corpus.owner.headers)).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    listed = (await client.get(base, headers=corpus.owner.headers)).json()
    assert any(c["id"] == conversation["id"] and c["message_count"] == 4 for c in listed)


async def test_streamed_answers_send_sources_then_text_then_done(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{corpus.workspace}/ask/stream",
        json={"question": "When can I book business class?"},
        headers=corpus.owner.headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]

    assert names[0] == "sources"
    assert names[-1] == "done"
    assert "delta" in names
    streamed = "".join(data["text"] for name, data in events if name == "delta")
    done = events[-1][1]["message"]
    assert _squash(streamed) == _squash(done["content"])
    assert done["citations"]


async def test_search_ranks_the_right_passage_and_marks_matches_safely(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{corpus.workspace}/search",
        json={"query": "parental leave weeks", "limit": 5},
        headers=corpus.owner.headers,
    )
    assert response.status_code == 200
    hits = response.json()["hits"]

    assert hits
    assert hits[0]["document_title"] == "Northwind Employee Handbook 2026"
    assert "\x01" in hits[0]["snippet"]
    assert "\x02" in hits[0]["snippet"]
    assert "<b>" not in hits[0]["snippet"]
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)
