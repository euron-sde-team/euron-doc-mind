# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-23

First public release.

### Added

- Private, cited chat over PDF, Word (`.docx`), Excel (`.xlsx`), CSV, PowerPoint (`.pptx`),
  text, Markdown and HTML files, as JSON or streamed with server-sent events, with
  conversations, follow-up questions and per-question or per-conversation document scopes.
- Ingestion with file type sniffing, Office archive guards, structure-aware parsers (PDF
  layout and tables, Word headings and tables, spreadsheet records with number formats,
  slides with speaker notes, Markdown and HTML sections), a chunker that keeps exact
  offsets, and contextual embeddings; deduplication by content hash.
- Hybrid retrieval in PostgreSQL: pgvector HNSW with iterative scans and full-text search,
  fused with Reciprocal Rank Fusion, diversified with MMR and packed into a token budget.
- An offline extractive answerer (the default) and model answers through any
  OpenAI-compatible API or Ollama; local embeddings with fastembed, or OpenAI-compatible and
  Ollama embeddings.
- Verified citations that open the cited passage highlighted in a document viewer.
- A two-level answer cache (exact in Valkey, semantic in pgvector) keyed by corpus version,
  scope and generator version, and an embedding cache.
- Hybrid search with safe highlighting; insights with tokens saved, cache hit rate,
  latency percentiles and the most cited documents.
- Workspaces with owner, editor and viewer roles, members, an audit trail, per-workspace
  answering settings, and workspace-scoped API keys stored as peppered HMACs.
- Argon2id passwords, JWT sessions with version-based revocation and a sign-out denylist,
  account lockout, rate limits in Valkey, a CSRF origin check, and a production boot guard.
- An SQS ingestion worker with visibility heartbeats, retries, a dead-letter queue and a
  backlog-aware stale-document reaper.
- Web app (Next.js) with chat, library, viewer, search, insights and settings, light and
  dark themes, and runtime configuration from `/env.js`.
- Terraform for AWS (VPC, RDS PostgreSQL with pgvector, ElastiCache Valkey, S3, SQS, KMS,
  Secrets Manager, ECR, ECS Fargate behind one ALB, optional WAF, alarms and a dashboard)
  and a local stack on the Floci AWS emulator provisioned by the same modules.
- Unit, integration (real Postgres, Valkey and Floci), browser end-to-end and QA crawl test
  suites, and a seeded demo (`make demo`).
