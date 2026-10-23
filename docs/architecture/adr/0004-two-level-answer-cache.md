# ADR 0004: A two-level answer cache keyed by corpus version

## Status

Accepted.

## Context

In a team workspace the same questions come back again and again ("how many days of leave
do we get?"), often reworded. Answering each from scratch costs retrieval, and with a model
it costs tokens and seconds. A cache must never serve an answer that the current documents
would not give: after an upload or a deletion, after a scope change, or after the answering
algorithm or model changes. Purging caches on every change is error-prone.

## Decision

- **Exact level**, in Valkey: the key is
  `ans:{workspace}:{corpus_version}:{generator#version}:{scope}:{sha256(normalised question)}`,
  where normalisation lower-cases, collapses whitespace and strips trailing punctuation.
- **Semantic level**, in Postgres: the `answer_cache` table stores the standalone question's
  embedding with the answer, citations and sources; a lookup takes the nearest question with
  the same workspace, scope hash, corpus version and generator, and accepts it at
  `SEMANTIC_CACHE_THRESHOLD` (0.95 cosine similarity) or above.
- **Invalidation by key, not by purge**: every document that becomes ready, and every
  deletion of a ready document, increments `workspaces.corpus_version`. Old entries simply
  stop matching and expire (`ANSWER_CACHE_TTL_S`, seven days; the worker deletes expired
  rows).
- Only answers with at least one citation that are not "not found" are stored.
- Follow-ups are cached by their standalone form, so "and how long does it last?" in one
  conversation can hit the answer to "how long does parental leave last?" from another.
- Owners can switch the cache off per workspace; usage events record `miss`, `exact` or
  `semantic`, and the insights page shows the hit rate and the tokens saved.

## Consequences

Positive:

- Repeats cost one Valkey `GET`; paraphrases one indexed query over a handful of rows.
- Correctness does not depend on remembering to purge: the key cannot match after the
  corpus, the scope or the generator changes.
- The cache is visible to users: every answer says whether it came from the cache.

Trade-offs:

- Any upload retires every cached answer in the workspace, including unrelated ones; busy
  workspaces see lower hit rates.
- A threshold of 0.95 is conservative; lowering it raises hits and the risk of answering a
  subtly different question.
- Cached answers keep the document titles they were produced with until the corpus changes.

## Alternatives considered

- **Exact cache only.** Simple, misses most real repeats, which are paraphrases.
- **TTL-only invalidation.** Serves stale answers until expiry after a document changes.
- **Purging by document on change.** Requires tracking which answers used which documents
  and still misses scope and generator changes.
