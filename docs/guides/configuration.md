# Configuration reference

Every setting the API, the worker, the CLI, the web app and the local Compose stack read,
with defaults and meaning. The API settings come from `apps/api/src/docmind/core/config.py`
(pydantic-settings): each field is read from the environment variable of the same name in
upper case, validated once at start-up, and shared by the whole process. An invalid value
stops the process with a message naming the field.

**Production** marks what the boot guard checks when `APP_ENV=production` (the API refuses
to start and lists every problem at once; see
[security.md](../architecture/security.md#production-boot-guard)). On AWS, the Terraform in
`infra/terraform/modules/deployment` sets every one of them for you.

## API, worker and CLI

### Application

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `APP_ENV` | `development` | `production` | `development`, `test` or `production`. Production turns on the boot guard and HSTS, and blocks the demo seeder |
| `PRODUCT_NAME` | `Euron DocMind` | | Title of the API reference and of the web app |
| `LOG_LEVEL` | `info` | | `debug`, `info`, `warning` or `error` |
| `LOG_FORMAT` | `json` | | `json` (one object per line) or `console` (readable, for a terminal). The CLI always logs to the console |

### HTTP

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:3110,http://127.0.0.1:3110` | required, no `*` | Comma-separated browser origins allowed to call the API with credentials. Also the allowlist for the CSRF origin check on cookie sessions |
| `WEB_URL` | `http://localhost:3110` | | The web app's URL; printed by the demo and accepted by the CSRF check |
| `API_URL` | `http://localhost:8110` | | The API's public URL; printed in the demo's `curl` example |

### PostgreSQL

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://docmind:docmind@localhost:5451/docmind` | | SQLAlchemy async URL. On AWS it carries no password and ends in `?ssl=require` |
| `DATABASE_SECRET_ARN` | unset | | When set, the password for each new connection is read from this RDS-managed secret (its `password` key), cached for a minute, so a rotation needs no redeploy |
| `DATABASE_POOL_SIZE` | `10` | | Connections kept per process (1 to 100) |
| `DATABASE_MAX_OVERFLOW` | `10` | | Extra connections allowed under load (0 to 100) |
| `DATABASE_ECHO` | `false` | | Log every SQL statement (development only) |
| `MIGRATE_ON_BOOT` | `false` | | Apply pending migrations when the API or the worker starts, under an advisory lock. Compose and Terraform set it for the API |

### Valkey (or Redis)

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6411/0` | | Exact answer cache, embedding cache, rate limits, signed-out sessions. `rediss://` with an auth token on AWS, injected from Secrets Manager |

### Sessions and API keys

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `SESSION_SECRET` | a development value | required, 32+ characters, not the default | HS256 key for session tokens. Changing it signs everyone out |
| `SESSION_TTL_HOURS` | `168` | | Session lifetime (1 to 2160 hours) |
| `API_KEY_PEPPER` | a development value | required, 32+ characters, different from `SESSION_SECRET` | HMAC key for stored API key hashes. Changing it invalidates every API key |
| `COOKIE_SECURE` | `false` | `true` | Mark the session cookie `Secure` (HTTPS only) |
| `COOKIE_DOMAIN` | unset | | Cookie domain, when the web app and the API share a parent domain and you want the cookie on both |
| `ALLOW_SIGNUP` | `false` | | Let anyone create an account. The very first account of a deployment can always sign up and becomes the administrator |

### Original files

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | `local` | `s3` | Where originals are kept |
| `STORAGE_DIR` | `data/files` (the image sets `/tmp/docmind/files`) | | Root directory for `local` |
| `S3_BUCKET` | unset | required | Bucket for `s3` |
| `S3_KMS_KEY_ID` | unset | | KMS key id, ARN or alias for SSE-KMS; without it, the bucket's default encryption applies |
| `AWS_REGION` | `us-east-1` | | Region for S3, SQS and Secrets Manager |
| `AWS_ENDPOINT_URL` | unset | must be unset | An emulator endpoint (Floci); also switches S3 to path-style addressing |
| `MAX_UPLOAD_MB` | `50` | | Largest file accepted (1 to 1024). A request may carry 20 files |
| `MAX_DOCUMENT_PAGES` | `2000` | | Largest PDF accepted, in pages |
| `MAX_UNCOMPRESSED_MB` | `400` | | Largest total uncompressed size of an Office file (decompression bomb guard) |

### Ingestion queue

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `QUEUE_BACKEND` | `inline` | `sqs` | `inline` ingests inside the API process (development); `sqs` sends jobs to the worker |
| `SQS_QUEUE_URL` | unset | required | The ingestion queue |
| `WORKER_CONCURRENCY` | `2` | | Documents one worker process handles at once (1 to 32) |
| `INGEST_TIMEOUT_S` | `600` | | Time allowed to parse, chunk and embed one document before it fails |
| `STALE_PROCESSING_MINUTES` | `15` | | After this long unfinished, the reaper re-sends a document (or fails it when it is out of attempts) |

### Chunking

Workspace settings can override both for their own documents.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CHUNK_TOKENS` | `320` | Target chunk size in tokens (64 to 2048) |
| `CHUNK_OVERLAP_TOKENS` | `48` | Overlap between consecutive chunks, in whole sentences up to this many tokens (0 to 512, capped at half the target) |

### Embeddings

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `EMBEDDINGS_PROVIDER` | `local` | not `hash` | `local` (fastembed, in process), `openai` (any OpenAI-compatible `/embeddings`), `ollama` (`/api/embed`), `hash` (tests only) |
| `EMBEDDINGS_MODEL` | `BAAI/bge-small-en-v1.5` | | Model name for the provider. The API image bakes this one in |
| `EMBEDDING_DIM` | `384` | | Vector width (32 to 4096). Fixed when the first migration runs; a different width needs a migration and `docmind reindex` |
| `EMBEDDINGS_BATCH_SIZE` | `64` | | Batch size for the local model |
| `EMBEDDINGS_CACHE_DIR` | unset (the image sets `/app/models/fastembed`) | | Where fastembed keeps model files |
| `EMBEDDINGS_API_BASE` | `https://api.openai.com/v1` | | Base URL for `openai` |
| `EMBEDDINGS_API_KEY` | unset | | Key for `openai` |

### Answer generation

| Variable | Default | Production | Meaning |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | `none` | | `none` (the offline extractive answerer), `openai` (any OpenAI-compatible Chat Completions API: OpenAI, Groq, Together, Mistral, DeepSeek, OpenRouter, vLLM, LM Studio and others) or `ollama` |
| `LLM_MODEL` | empty | required when a provider is set | Model name, for example `gpt-4.1-mini` or `llama3.2` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | | Base URL for `openai` |
| `LLM_API_KEY` | unset | | Key for `openai`. On AWS, a Secrets Manager reference (`llm_api_key_secret_arn`) |
| `OLLAMA_URL` | `http://localhost:11434` | | Ollama server, for `ollama` answers and embeddings |
| `LLM_TEMPERATURE` | `0.1` | | 0 to 2 |
| `LLM_MAX_TOKENS` | `700` | | Longest answer (16 to 8192) |
| `LLM_TIMEOUT_S` | `90` | | Request timeout; connecting is limited to 10 seconds |

### Retrieval

| Variable | Default | Meaning |
| --- | --- | --- |
| `RETRIEVAL_CANDIDATES` | `30` | Candidates taken from each of the vector and keyword searches before fusion (4 to 200) |
| `CONTEXT_TOKEN_BUDGET` | `1800` | Most tokens of passages given to the answerer (200 to 32000). Workspaces can override it |

### Caching

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANSWER_CACHE_TTL_S` | `604800` (7 days) | Lifetime of cached answers; `0` stops caching answers |
| `SEMANTIC_CACHE_THRESHOLD` | `0.95` | Cosine similarity at which a previous question counts as the same question (0.5 to 1.0) |
| `EMBEDDING_CACHE_TTL_S` | `2592000` (30 days) | Lifetime of cached embeddings; `0` keeps them without expiry |

### Rate limits

Requests per minute, counted in Valkey across every task.

| Variable | Default | Applies to |
| --- | --- | --- |
| `RATE_LIMIT_CHAT` | `30` | Answers (JSON and streamed) and search, per user or API key |
| `RATE_LIMIT_LOGIN` | `10` | Sign-in and sign-up, per client IP |
| `RATE_LIMIT_UPLOAD` | `60` | Upload requests, per user or API key |

### Other

| Variable | Default | Meaning |
| --- | --- | --- |
| `TOKENIZER` | `tiktoken` | `tiktoken` (o200k_base) or `heuristic` (four characters per token) |
| `DEMO_PASSWORD` | unset | Password for every demo account created by `docmind demo seed` |
| `WORKER_METRICS_PORT` | unset | Worker only: serve Prometheus metrics on this port (Compose sets 9100 and uses it as the health check) |
| `TIKTOKEN_CACHE_DIR`, `HF_HUB_OFFLINE` | set by the image | Point the tokenizer and fastembed at the files baked into the image, and forbid downloads at runtime |

## Web app

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_URL` | `http://localhost:8110` | The API as the browser reaches it, served in `/env.js` at request time |
| `PRODUCT_NAME` | `Euron DocMind` | Shown in the app |
| `PORT`, `HOSTNAME` | `8080`, `0.0.0.0` in the image | Where the Next.js server listens |

## Workspace settings

Owners change these in Settings, Answering, or with `PATCH /api/v1/workspaces/{ws}`
(`settings`). They are stored in `workspaces.settings`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `answer_mode` | `auto` | `auto` uses the deployment's answerer; `extractive` always answers offline, even when a model is configured |
| `top_k` | `6` | Passages given to the answerer (1 to 12) |
| `context_token_budget` | deployment value | Overrides `CONTEXT_TOKEN_BUDGET` (200 to 32000) |
| `chunk_tokens`, `chunk_overlap_tokens` | deployment values | Override chunking for documents indexed from now on; use Reprocess to apply them to existing ones |
| `cache_enabled` | `true` | Use and fill the answer cache |

## Local Compose stack

`deploy/compose/.env` (generated by `make env`, git-ignored; see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `DOCMIND_SESSION_SECRET`, `DOCMIND_API_KEY_PEPPER` | generated | Local secrets passed to the API and the worker |
| `DOCMIND_DEMO_PASSWORD` | generated | Password of every demo account; also read by `make e2e`, `make qa` and `make screenshots` |
| `DOCMIND_LLM_PROVIDER`, `DOCMIND_LLM_MODEL`, `DOCMIND_LLM_BASE_URL`, `DOCMIND_LLM_API_KEY`, `DOCMIND_OLLAMA_URL` | `none`, empty, OpenAI, empty, `http://host.docker.internal:11434` | Optional model answers |
| `DOCMIND_PRODUCT_NAME`, `DOCMIND_LOG_LEVEL` | `Euron DocMind`, `info` | |
| `DOCMIND_WEB_PORT`, `DOCMIND_API_PORT`, `DOCMIND_PG_PORT`, `DOCMIND_REDIS_PORT`, `DOCMIND_FLOCI_PORT` | `3110`, `8110`, `5451`, `6411`, `4611` | Host ports |

`deploy/compose/.env.aws` (for `make up-aws`, from `.env.aws.example`) holds `AWS_REGION`,
`S3_BUCKET`, `S3_KMS_KEY_ID` and `SQS_QUEUE_URL` of real AWS resources.

## Integration tests

| Variable | Default | Meaning |
| --- | --- | --- |
| `TEST_DATABASE_ADMIN_URL` | `postgresql://docmind:docmind@localhost:5451/docmind` | Server where the suite recreates its own `docmind_test` database |
| `TEST_REDIS_URL` | `redis://localhost:6411/15` | Valkey database the suite flushes and uses |
| `TEST_AWS_ENDPOINT_URL` | `http://localhost:4611` | Emulator for the suite's own bucket, key and queues |
