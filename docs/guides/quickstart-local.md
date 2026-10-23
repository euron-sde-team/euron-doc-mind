# Quickstart: run Euron DocMind locally

This guide starts the complete stack on your machine: the web app, the API, the ingestion
worker, PostgreSQL with pgvector, Valkey, and an AWS emulator provisioned by the same
Terraform modules that build production. You need no AWS account and no API key: documents
are embedded and answered locally.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Docker with Compose v2 | `make up` uses `docker compose ... up --wait` |
| GNU Make and `openssl` | `make env` generates local secrets with `openssl rand` |
| About 6 GB of free disk and 4 GB of memory for Docker | The API image carries the embedding model and the tokenizer |
| Free host ports | 3110, 8110, 5451, 6411, 4611 (all bound to `127.0.0.1`; see [Port clashes](#port-clashes)) |
| Python 3.12 with `uv`, Node 22 with pnpm 9 | Only to run tests or the apps outside Docker. The repository pins Python in `.python-version`, Node in `.nvmrc` and `pnpm@9.15.9` in `package.json` |

## Start the stack

From the repository root:

```bash
make up
```

This does three things:

1. `make env` writes `deploy/compose/.env` with random, local-only secrets
   (`DOCMIND_SESSION_SECRET`, `DOCMIND_API_KEY_PEPPER`, `DOCMIND_DEMO_PASSWORD`), once; it
   never overwrites an existing file.
2. Builds the `api` and `web` images (the worker uses the API image) and starts every
   service.
3. A one-shot `terraform` container applies `infra/terraform/envs/local-floci` to the
   emulator: the KMS key `alias/docmind-local`, the documents bucket
   `docmind-local-documents` with SSE-KMS, the ingestion queue `docmind-local-ingest` with
   its dead-letter queue, and the application secrets. Then the API starts and applies the
   database migrations, and the worker starts once the API is healthy.

The first build downloads the embedding model into the image and takes a few minutes; later
builds reuse the layers. When it finishes it prints the URLs. Then seed the demo:

```bash
make demo
```

`make demo` uploads the nine sample documents in `samples/` through the real pipeline (S3,
SQS, the worker), waits until they are indexed, asks a few weeks' worth of sample questions
so the insights charts have a shape, creates an API key, and prints the logins, the shared
password and a `curl` example. The password is `DOCMIND_DEMO_PASSWORD` from
`deploy/compose/.env`:

```bash
grep DOCMIND_DEMO_PASSWORD deploy/compose/.env
```

Running `make demo` again is safe: existing accounts, workspaces, files and conversations are
reused. It refuses to run with `APP_ENV=production`.

## Sign in

Open <http://localhost:3110>.

| Person | Email | Northwind Robotics | Atlas engineering |
| --- | --- | --- | --- |
| Ava Martin (administrator) | `ava.martin@northwind.example` | owner | editor |
| Leo Chen | `leo.chen@northwind.example` | editor | owner |
| Maya Patel | `maya.patel@northwind.example` | viewer | |

Northwind Robotics holds all nine sample files (an employee handbook PDF, a board update
deck, an operating budget workbook, a services agreement PDF, product requirements in Word,
a support FAQ in HTML, a runbook in Markdown, release notes and a CSV of pilot results).
Atlas engineering holds three of them. [walkthrough.md](walkthrough.md) is a guided tour.

## What runs where

| Service | URL or port | What it is |
| --- | --- | --- |
| web | <http://localhost:3110> | The web app |
| api | <http://localhost:8110> | The API; interactive reference at <http://localhost:8110/docs>, `GET /livez`, `GET /readyz` |
| worker | no port | Parses, chunks and embeds uploads from the emulated SQS queue |
| postgres | `localhost:5451` | PostgreSQL 16 with pgvector, database, user and password `docmind` |
| valkey | `localhost:6411` | Valkey 8: caches, rate limits, signed-out sessions |
| floci | <http://localhost:4611> | AWS emulator: S3, KMS, SQS, Secrets Manager |

Useful commands:

| Command | Does |
| --- | --- |
| `make ps` | Service status |
| `make logs SERVICE=worker` | Follow one service's logs (`api`, `worker`, `web`, `postgres`, `valkey`, `floci`, `terraform`) |
| `make reindex WORKSPACE=northwind-robotics` | Parse and index every document of a workspace again (all workspaces without `WORKSPACE`) |
| `make down` | Stop everything and delete the volumes (database, emulator state, Terraform state) |

## Answer with a model (optional)

DocMind answers offline by default. To have a model write the answers, set the provider in
`deploy/compose/.env` and run `make up` again:

```bash
# Ollama running on this machine (ollama pull llama3.2 first)
DOCMIND_LLM_PROVIDER=ollama
DOCMIND_LLM_MODEL=llama3.2

# or any OpenAI-compatible API
DOCMIND_LLM_PROVIDER=openai
DOCMIND_LLM_MODEL=gpt-4.1-mini
DOCMIND_LLM_BASE_URL=https://api.openai.com/v1
DOCMIND_LLM_API_KEY=...
```

Containers reach Ollama on the host through `host.docker.internal` (mapped for you in
Compose). Answers from a model are cached separately from extractive answers, and owners
can keep a workspace on extractive answers in Settings, Answering.

## Run the apps outside Docker

For quick iteration on the code, run the API and the web app on the host against the
Compose databases. The settings' defaults already point at them.

```bash
scripts/test-deps.sh                 # Postgres, Valkey and Floci only
# If the full stack is running, free ports 8110 and 3110 first:
docker compose --env-file deploy/compose/.env -f deploy/compose/compose.yaml \
  -f deploy/compose/compose.floci.yaml stop api worker web

cd apps/api
uv sync
uv run docmind migrate
uv run uvicorn docmind.main:create_app --factory --port 8110 --reload
```

Outside Docker the API uses local file storage (`data/files`) and ingests in process
(`QUEUE_BACKEND=inline`), so no worker is needed. Seed it with:

```bash
DEMO_PASSWORD='Choose-a-demo-password-1' uv run docmind demo seed --samples ../../samples
```

In another terminal:

```bash
pnpm install
pnpm dev                              # http://localhost:3110, API at http://localhost:8110
```

## Port clashes

Every host port can be changed in `deploy/compose/.env`:

```bash
DOCMIND_WEB_PORT=3110
DOCMIND_API_PORT=8110
DOCMIND_PG_PORT=5451
DOCMIND_REDIS_PORT=6411
DOCMIND_FLOCI_PORT=4611
```

Changing `DOCMIND_WEB_PORT` or `DOCMIND_API_PORT` also updates `CORS_ORIGINS`, `WEB_URL`
and the web app's `API_URL`, which Compose derives from them.

## Next steps

- A guided tour of the demo: [walkthrough.md](walkthrough.md)
- Every setting: [configuration.md](configuration.md)
- Tests: [testing.md](testing.md)
- Something not working: [troubleshooting.md](troubleshooting.md)
