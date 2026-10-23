"""Prometheus metrics, exposed at GET /metrics.

One API process per container (scale out with containers, not uvicorn workers), so the
default registry is accurate without multiprocess mode.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "docmind_http_requests_total", "HTTP requests by route template.", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "docmind_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
INGESTED_DOCUMENTS = Counter(
    "docmind_ingested_documents_total", "Documents processed by the worker.", ["kind", "outcome"]
)
INGEST_DURATION = Histogram(
    "docmind_ingest_duration_seconds",
    "Parse, chunk and embed time per document.",
    ["kind"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)
RETRIEVAL_DURATION = Histogram(
    "docmind_retrieval_duration_seconds",
    "Hybrid retrieval latency (embedding the query, both searches, fusion).",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
GENERATION_DURATION = Histogram(
    "docmind_generation_duration_seconds",
    "Answer generation latency by provider.",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
TOKENS = Counter(
    "docmind_tokens_total",
    "Tokens by kind: context sent, prompt, completion, the all-documents baseline, and saved.",
    ["kind"],
)
ANSWER_CACHE = Counter("docmind_answer_cache_total", "Answer cache lookups by result.", ["result"])
EMBEDDING_CACHE = Counter(
    "docmind_embedding_cache_total", "Embedding cache lookups by result.", ["result"]
)
