# ADR 0002: Hybrid retrieval fused with Reciprocal Rank Fusion

## Status

Accepted.

## Context

Questions about company documents mix two kinds of need. Paraphrases ("how much time off
do we get?" for a section titled "Annual leave") are found by meaning. Exact terms (a
contract name, "SEV1", "FR-1", a release number) are found by keywords, and small embedding
models often miss them. Vector similarity and keyword rank are on unrelated scales, so
adding the scores needs per-corpus calibration nobody maintains.

## Decision

- For every question, retrieve two candidate lists from Postgres
  ([ADR 0001](0001-postgres-pgvector-for-vectors-and-full-text.md)): the nearest chunks by
  cosine similarity, and the best chunks by `ts_rank_cd` for an OR query over the question's
  stemmed content words (`RETRIEVAL_CANDIDATES` from each, 30 by default).
- Merge them with Reciprocal Rank Fusion (`k = 60`): each chunk scores the sum of
  `1 / (60 + rank)` over the lists it appears in. Ranks, not scores, are combined.
- Diversify the fused list with Maximal Marginal Relevance (diversity 0.3) so near-duplicate
  passages (overlapping chunks, repeated boilerplate) do not crowd out others.
- Pack the result greedily into the context token budget (`CONTEXT_TOKEN_BUDGET`, or the
  workspace override) up to `top_k` sources, numbered for citation.
- Embed each chunk with its document title and heading path (contextual embeddings), so a
  short chunk still carries what it is about.
- Search uses the same candidates and fusion, with Postgres headlines for the snippets.

## Consequences

Positive:

- Questions that need an exact identifier and questions that need a paraphrase both
  succeed, and a chunk that both systems rank highly rises to the top.
- No score calibration or learned weights to maintain; behaviour is the same for every
  corpus and embedding model.
- The pipeline is pure functions after the two queries (`ai/retrieval.py`), unit tested
  without a database.

Trade-offs:

- Two queries per question instead of one (both indexed; together a few milliseconds on the
  sample corpus).
- RRF ignores how much better the top result is than the second; a cross-encoder reranker
  would order the final few more precisely at the cost of latency (roadmap).
- The keyword side is English (`to_tsvector('english', ...)`); other languages rely on the
  vector side until per-workspace text search configurations are added.

## Alternatives considered

- **Vector search only.** Simpler, but misses exact terms and codes, which are common in
  company documents.
- **Weighted score sum.** Needs per-corpus normalisation and tuning.
- **A reranking model on every question.** Better precision, but adds a model call (or a
  heavy local model) to every answer, against the offline, low-latency default.
