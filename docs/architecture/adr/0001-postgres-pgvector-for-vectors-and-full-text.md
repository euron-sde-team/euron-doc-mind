# ADR 0001: PostgreSQL with pgvector for records, vectors and full text

## Status

Accepted.

## Context

DocMind needs four kinds of storage for every workspace: relational records (people,
workspaces, documents, conversations, audit), the text of every section and chunk, a
nearest-neighbour index over chunk embeddings, and a keyword index over the same chunks.
Retrieval must always be filtered by workspace, and often by a handful of selected
documents, without ever leaking a passage across workspaces. Deleting a document or a
workspace must remove its index entries in the same transaction as its rows.

## Decision

- One PostgreSQL 16 database holds everything, with the `vector` extension (pgvector 0.8)
  for embeddings and the built-in full-text search for keywords.
- `chunks.embedding` is a `vector(EMBEDDING_DIM)` column with an HNSW index
  (`vector_cosine_ops`, `m = 16`, `ef_construction = 64`). Embeddings are L2-normalised.
- `chunks.tsv` is a stored generated `tsvector` over the heading and the text, with a GIN
  index.
- `chunks.workspace_id` is denormalised from the document so both searches filter in SQL
  without a join.
- Vector queries enable pgvector's iterative index scans (`hnsw.iterative_scan =
  relaxed_order`) and size `hnsw.ef_search` to the request, so workspace and document filters
  do not starve the result list the way post-filtering a fixed top list would.
- Every statement is static SQL with bound parameters (`repositories/search.py`).
- The semantic answer cache uses the same extension (`answer_cache.question_embedding`).

## Consequences

Positive:

- One store to provision, back up, encrypt, monitor and emulate locally; RDS supports the
  extension.
- Workspace isolation, document scopes and deletion are ordinary SQL with foreign keys and
  `ON DELETE CASCADE`: a deleted document cannot leave orphaned vectors behind.
- Hybrid retrieval needs no cross-system join: both candidate lists come from one database
  in one session.
- Index builds, transactions and backups follow the same rules as the rest of the data.

Trade-offs:

- Approximate search quality depends on HNSW parameters and `ef_search`; very large
  workspaces (tens of millions of chunks) would need tuning, partitioning or a dedicated
  engine.
- The embedding width is fixed per deployment by the migration; changing the model needs a
  migration and a reindex.
- Vector and keyword load competes with transactional load on the same instance; scale up
  or add a read replica when retrieval dominates.

## Alternatives considered

- **A dedicated vector database** (Qdrant, Weaviate, Milvus). Better at very large scale,
  but a second store to secure and keep consistent with Postgres on every upload and
  deletion, and workspace filters would be enforced in two places.
- **OpenSearch or Elasticsearch** for both vectors and BM25. Strong keyword ranking, but a
  heavier cluster to run and pay for, and again a second source of truth.
- **In-process indexes** (FAISS files per workspace). Fast, but they do not survive task
  replacement, do not scale across tasks and complicate deletion.
