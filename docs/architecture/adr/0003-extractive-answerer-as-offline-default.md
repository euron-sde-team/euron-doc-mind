# ADR 0003: An extractive answerer as the offline default

## Status

Accepted.

## Context

DocMind must run, demo and pass its tests with no paid API key and no network, and many
teams that want private document chat cannot send their documents to a hosted model at
all. Yet the product promise is an answer with citations, not a list of search results.
Model-written answers read better, but they can state things the sources do not support,
they cost money per question, and they need a provider.

## Decision

- `LLM_PROVIDER=none` (the default) answers with the extractive answerer
  (`ai/extractive.py`): it splits the retrieved passages into sentences, list items and
  table records, scores them against the question (IDF-weighted coverage with credit for
  headings and titles, centred embedding similarity, number and source-rank boosts),
  answers comparison questions from table columns, returns whole sections when a heading
  matches the question, and composes the best units in document order with `[n]` citations.
- When nothing covers the question well enough, it says it could not find a clear answer and
  points at the closest passage instead of guessing.
- `LLM_PROVIDER=openai` (any OpenAI-compatible endpoint) or `ollama` swaps in a model
  through the same generator interface; both stream, both are cited and verified the same
  way, and owners can still force extractive answers per workspace.
- Every generator carries a version that is part of the answer-cache key, so improving the
  algorithm retires answers produced by the previous one.

## Consequences

Positive:

- The full product (answers, citations, caching, insights) works offline and
  deterministically; tests and screenshots are reproducible.
- Every sentence in an extractive answer is a sentence from the documents, so it cannot
  hallucinate; citations always point at the text they quote.
- Zero marginal cost per question and no data leaves the deployment.

Trade-offs:

- Answers are quotations, not syntheses: a question whose answer spans several documents
  gets the relevant sentences side by side rather than a summary.
- Phrasing is the documents' phrasing; tables come back as records ("Site: Rotterdam;
  Picks per hour: 455").
- The scoring is heuristic and tuned on English business documents.

## Alternatives considered

- **Require a hosted model.** Better prose, but breaks the offline promise and the privacy
  case, and makes tests depend on a provider.
- **Bundle a small local language model.** Offline, but large images, slow on CPUs, and
  still able to hallucinate; Ollama support covers teams that want this.
- **Show search results only.** Honest, but not the product people ask for.
