# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# API, ingestion worker, migration runner and operator CLI: one image.
#   docker build -f infra/docker/api.Dockerfile -t docmind-api .
#
#   api      uvicorn docmind.main:create_app --factory   (default command)
#   worker   python -m docmind.worker
#   cli      docmind migrate | docmind demo seed | docmind reindex
#
# The embedding model and the tokenizer are baked in at build time, so a running container
# never downloads anything to index or answer.
# ─────────────────────────────────────────────────────────────────────────────
ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.4

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
ARG EMBEDDINGS_MODEL=BAAI/bge-small-en-v1.5
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    EMBEDDINGS_CACHE_DIR=/app/models/fastembed TIKTOKEN_CACHE_DIR=/app/models/tiktoken
WORKDIR /src
# Dependencies first: this layer is reused until the lockfile changes.
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable
RUN /app/.venv/bin/python -c "import os, tiktoken; from fastembed import TextEmbedding; \
TextEmbedding('${EMBEDDINGS_MODEL}', cache_dir=os.environ['EMBEDDINGS_CACHE_DIR']); \
tiktoken.get_encoding('o200k_base')"

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC \
    EMBEDDINGS_CACHE_DIR=/app/models/fastembed TIKTOKEN_CACHE_DIR=/app/models/tiktoken \
    HF_HUB_OFFLINE=1 STORAGE_DIR=/tmp/docmind/files
# tini forwards SIGTERM so uvicorn drains requests and the worker finishes its documents.
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /app docmind
WORKDIR /app
COPY --from=build --chown=docmind:docmind /app/.venv /app/.venv
COPY --from=build --chown=docmind:docmind /app/models /app/models
# The demo seeder reads the sample documents from ./samples.
COPY --chown=docmind:docmind samples /app/samples
USER docmind
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "docmind.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "20", \
     "--no-access-log"]
