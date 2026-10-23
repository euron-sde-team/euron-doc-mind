# DocMind API and worker

FastAPI service for Euron DocMind, plus the ingestion worker that runs from the same image
with a different command.

```bash
uv sync                                  # Python 3.12 and every dependency
uv run uvicorn docmind.main:app --reload --port 8110
uv run python -m docmind.worker          # ingestion worker (QUEUE_BACKEND=sqs)
uv run docmind --help                    # CLI: migrations, users, demo data, reindex
uv run pytest tests/unit                 # unit tests, no services needed
```

## Layout

```text
src/docmind/
├── main.py            app factory: middleware, routers, lifespan (pools, migrations, providers)
├── worker.py          SQS consumer: parse, chunk, embed, publish; graceful shutdown
├── cli.py             typer CLI
├── core/              config, logging, errors, request context, security, rate limits, metrics
├── db/                engine, session, declarative base
├── models/            SQLAlchemy models, one module per aggregate
├── schemas/           Pydantic request and response models
├── repositories/      the only code that touches the database
├── services/          business rules, transactions, cache invalidation
├── api/               routes and dependencies (authentication, workspace roles, rate limits)
├── ingestion/         file sniffing, archive guards, parsers per format, structure-aware chunker
├── ai/                token counting, embeddings, retrieval fusion, answer generation, citations
├── integrations/      S3 or local file storage, SQS or inline queue
└── demo/              demo seed used by `make demo`
```

## The rules

| Layer | May import | Must not |
| --- | --- | --- |
| `api/routes` | schemas, services, `api/deps` | touch a session, a repository or Redis directly |
| `services` | repositories, `ai`, `ingestion`, `integrations`, `core` | import FastAPI or return ORM objects to routes it does not own |
| `repositories` | models, `db` | commit, call another service, or skip the `workspace_id` filter |
| `ai`, `ingestion` | `core` only | do I/O against the database; they are pure and unit tested |

**Workspace isolation.** Every repository method that reads workspace data takes
`workspace_id` as a required argument. The `WorkspaceAccess` dependency in `api/deps.py`
resolves the caller's role first and answers 404 to non-members, so a workspace's existence
is not revealed either.

**Transactions.** A service method that writes opens and commits its own transaction.
Routes never commit.

**Errors.** Raise the typed errors in `core/errors.py`. The handlers turn them into the one
envelope every response uses:
`{"error": {"code", "message", "request_id", "details?"}}`.

## A reference resource

API keys are the smallest complete slice of the stack. Read them in this order:

1. `api/routes/api_keys.py`: URL, role dependency, request and response models
2. `services/api_keys.py`: generation, hashing with the pepper, audit event, commit
3. `repositories/api_keys.py`: workspace-scoped queries
4. `tests/integration/test_api_keys.py`: the behaviour, including a non-member sweep

## Tests

| Suite | Needs | Run |
| --- | --- | --- |
| `tests/unit` | nothing | `uv run pytest tests/unit` |
| `tests/integration` | Postgres with pgvector, Valkey, the AWS emulator | `make test-integration` from the repo root |
