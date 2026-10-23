# Low-level design

How the API, the worker and the answering pipeline work, module by module, with the file
that implements each part. The system view is in [HLD.md](HLD.md); tables and indexes in
[data-model.md](data-model.md). Paths are relative to `apps/api/src/docmind/` unless they
start with the repository root.

Contents:

1. [Layering](#1-layering)
2. [Requests, errors and context](#2-requests-errors-and-context)
3. [Identity and access](#3-identity-and-access)
4. [Ingestion pipeline](#4-ingestion-pipeline)
5. [Retrieval](#5-retrieval)
6. [Answering](#6-answering)
7. [Citations](#7-citations)
8. [Caches](#8-caches)
9. [The worker](#9-the-worker)
10. [Rate limits](#10-rate-limits)
11. [Observability](#11-observability)
12. [Database access](#12-database-access)

## 1. Layering

| Layer | Folder | Rule |
| --- | --- | --- |
| Routes | `api/routes/` | URL, request and response schema, the auth and role dependency, the rate limit. No business logic |
| Services | `services/` | Business rules, transactions (`commit`), audit records, cache invalidation by corpus version, queueing |
| Repositories | `repositories/` | The only code that builds SQL. Every query that takes an id also takes the `workspace_id`, so an id from another workspace finds nothing |
| Pure logic | `ai/`, `ingestion/`, `core/text.py` | No I/O: retrieval math, the extractive answerer, citations, parsers, the chunker. Unit tested without services |
| Integrations | `integrations/`, `ai/embeddings.py`, `ai/generation.py` | S3, SQS, Secrets Manager, embedding and model providers behind small protocols |

`services/container.py` builds one `Container` per process: settings, `Database`, the Valkey
client, storage, queue, the embedder (always wrapped in `CachedEmbedder`), the base
embedder, the token counter, the generator, the extractive generator (kept even when a model
is configured, for workspaces in extractive mode), the chat client and the rate limiter.
Routes receive it through `request.app.state.container`.

## 2. Requests, errors and context

Middleware order, outermost first (`main.py`):

| Middleware | Behaviour |
| --- | --- |
| `RequestContextMiddleware` (`core/context.py`) | Accepts an incoming `X-Request-Id` when it matches `^[A-Za-z0-9._-]{1,64}$`, otherwise generates one; binds it to every log line; adds it to every response with `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cross-Origin-Resource-Policy: same-site`, and HSTS in production; records request metrics by route template. A plain ASGI middleware, so streamed answers pass through unbuffered |
| `BodySizeLimitMiddleware` | Refuses bodies over `MAX_UPLOAD_MB` x 20 + 1 MiB before the multipart parser buffers them: checks `Content-Length` up front and counts chunked bodies as they arrive |
| `CORSMiddleware` | Exactly `CORS_ORIGINS`, credentials allowed, methods `GET POST PATCH DELETE OPTIONS`, exposes the request id, rate-limit headers and `Content-Disposition` |

Every error, from any layer, is one envelope (`core/errors.py`):

```json
{"error": {"code": "not_found", "message": "Document not found.", "request_id": "6f1c...", "details": null}}
```

| Class | Status | Default code |
| --- | --- | --- |
| `UnauthorizedError` | 401 | `unauthorized` (also `invalid_credentials`, `invalid_api_key`) |
| `ForbiddenError` | 403 | `forbidden` (also `csrf`) |
| `NotFoundError` | 404 | `not_found` |
| `ConflictError` | 409 | `conflict` |
| `PayloadTooLargeError` | 413 | `payload_too_large` |
| `UnsupportedMediaTypeError` | 415 | `unsupported_media_type` (also `content_mismatch`) |
| `UnprocessableError` | 422 | `validation_failed` (also `empty_scope`); request validation errors list `details[].loc` |
| `RateLimitedError` | 429 | `rate_limited`, with `Retry-After` and the `X-RateLimit-*` headers |
| `UpstreamError` | 502 | `upstream_error` (the model or embedding provider failed) |
| `ServiceUnavailableError` | 503 | `service_unavailable` |
| `InternalError` and any unhandled exception | 500 | `internal_error`; the message never echoes the exception, the traceback is logged under the same request id |

Answer endpoints produce a stream of `ChatEvent`s. The SSE endpoints send them as they
come (`sources`, `delta`..., `done`, or `error` with the same envelope). The JSON endpoints
collect them and raise the error behind an `error` event, so `/ask` keeps the real status
code (404, 422, 502). Both close the answer generator explicitly (`contextlib.aclosing`), so a
disconnected client or an early error returns the database connection at once.

## 3. Identity and access

### Principals (`api/deps.py`, `services/principal.py`)

| Credential | Accepted as | Resolved by |
| --- | --- | --- |
| `Authorization: Bearer dmk_...` | Workspace API key | `ApiKeyService.resolve` |
| `Authorization: Bearer <JWT>` | Session (scripts and API clients use the `token` from `POST /auth/login`) | `AuthService.resolve` |
| Cookie `docmind_session` | Session (the web app) | `AuthService.resolve`, plus the CSRF origin check below |

A bearer header wins over the cookie. For a cookie session, every method other than `GET`,
`HEAD` and `OPTIONS` must carry an `Origin` (or `Referer`) that is in `CORS_ORIGINS` or
equal to `WEB_URL`; anything else is `403 csrf`. The cookie is `HttpOnly`, `SameSite=Lax`,
`Secure` when `COOKIE_SECURE=true`, scoped to `COOKIE_DOMAIN` when set.

### Sessions (`core/security.py`, `services/auth.py`)

- Passwords: Argon2id (time cost 3, 64 MiB, parallelism 2), run in a worker thread. Policy:
  10 to 256 characters, at least 4 distinct characters, not the email address. Hashes are
  upgraded on sign-in when the parameters change.
- Unknown emails are verified against a dummy hash, so a miss costs as much as a wrong
  password and timing does not reveal which accounts exist. Both get
  `401 invalid_credentials`.
- Eight consecutive failures lock the account for 15 minutes (`429`), checked before the
  password.
- Tokens: HS256 JWT signed with `SESSION_SECRET`, issuer `docmind`, audience
  `docmind-web`, claims `sub` (user id), `sv` (the user's `session_version`), `jti`, `iat`,
  `exp`, lifetime `SESSION_TTL_HOURS` (168 by default).
- Each request reloads the user: a token whose `sv` differs from the row is refused, so a
  password change (which increments `session_version` and returns a fresh token for the
  caller) ends every other session at once.
- Sign-out writes `session:revoked:{jti}` to Valkey with a TTL equal to the token's
  remaining life; resolution refuses listed ids.

### API keys (`core/security.py`, `services/api_keys.py`)

- Format `dmk_<prefix>_<secret>`: a 10-character base32 prefix (unique, indexed) and a
  43-character URL-safe secret from `secrets.token_urlsafe(32)`.
- Stored: the prefix and `HMAC-SHA256(API_KEY_PEPPER, secret)`. A database leak alone
  cannot be replayed; verification uses `hmac.compare_digest`.
- Revoked or expired keys get `401 invalid_api_key`. `last_used_at` is written at most once
  a minute per key (a Valkey `SET NX EX 60` gate), so busy keys do not write on every call.
- A key belongs to one workspace with role `viewer` or `editor`. Account endpoints
  (`/auth/me`, password, profile) need a person and return `403` for keys.

### Workspaces and roles (`services/workspaces.py`, `models/enums.py`)

`WorkspaceAccess(minimum)` resolves `{workspace}` (a slug or an id) and the caller's role,
then requires at least `minimum`:

| Role | Can |
| --- | --- |
| `viewer` | Read the library and documents, download originals, ask, search, see insights and the member list, leave the workspace |
| `editor` | Everything a viewer can, plus upload, rename, reprocess and delete documents |
| `owner` | Everything, plus workspace settings, members and roles, API keys, the audit trail and deleting the workspace |

Non-members, and keys of other workspaces, get `404 Workspace not found`. Only owners remove
other members; anyone can leave. The last owner cannot be demoted, removed or leave. Adding
a member by an email with no account creates the account with a generated temporary
password, returned once in the response.

## 4. Ingestion pipeline

### Upload (`services/documents.py`)

For each file: reject empty files (`empty_file`) and files over `MAX_UPLOAD_MB`
(`payload_too_large`); detect the kind (`ingestion/sniff.py`); compute SHA-256 and return
the existing document if the workspace already has those bytes (`UNIQUE (workspace_id,
sha256)`); store the original; insert the row as `queued` with an audit event; commit; then
enqueue. Enqueueing after the commit guarantees the worker can read the row it is told
about; if the enqueue itself is lost, the reaper re-sends the document.

### Type detection (`ingestion/sniff.py`)

The extension picks the parser and the bytes must agree: `%PDF-` within the first KiB for
PDF, a ZIP local header for `.docx`, `.xlsx` and `.pptx`, and no NUL bytes in the first
8 KiB for CSV, text, Markdown and HTML (UTF-16 byte-order marks excepted). A renamed
executable is refused with `content_mismatch` before any parser sees it.

### Office archive guards (`ingestion/archive.py`)

Before any XML is read, from the ZIP central directory: at most 10,000 entries, no
encrypted entries, total uncompressed size under `MAX_UNCOMPRESSED_MB` (400 by default), a
compression ratio under 200 (a decompression bomb), and `[Content_Types].xml` plus the part
the extension promises (`word/`, `xl/`, `ppt/`).

### Parsers (`ingestion/parsers/`)

| Format | Sections | Notes |
| --- | --- | --- |
| PDF (`pdf.py`, pypdf) | One per page, `Page N` | Layout extraction keeps table rows on one line; pages without text are skipped and reported as a warning; a PDF with no text at all fails with an OCR hint; password-protected PDFs fail; at most `MAX_DOCUMENT_PAGES` pages |
| Word (`docx.py`) | A new section at each heading (the text before the first one is `Introduction`) | Heading levels from paragraph styles (`Title`, `Heading N`); tables become `Column: value` records |
| Excel and CSV (`sheets.py`) | One per sheet | Header detection, one `Column: value; Column: value` record per row so a retrieved row reads as a fact, Excel number formats honoured, at most 50,000 rows per sheet |
| PowerPoint (`pptx.py`) | One per slide, `Slide N: title` | Title, body text, tables and speaker notes, cited as that slide |
| Text, Markdown, HTML (`text.py`) | New section at every level 1 or 2 heading | Markdown tables become records; HTML parsed with BeautifulSoup with `script`, `style`, `noscript`, `nav`, `header`, `footer`, `svg` and `form` removed, nothing executed |

openpyxl parses its XML through `defusedxml` when it is installed, and it is a runtime
dependency; python-docx and python-pptx parse with lxml with entity resolution disabled. The
archive guards run first, so a decompression bomb is refused before any XML parser sees it.

### Chunking (`ingestion/chunker.py`)

- Chunks never cross a section boundary, so every citation points at one page, slide,
  sheet or section.
- Within a section, blocks are packed up to `CHUNK_TOKENS` (320, o200k tokens); a long
  block is split at sentences, a long sentence into word windows of 70 percent of the
  target.
- Consecutive chunks overlap by whole sentences up to `CHUNK_OVERLAP_TOKENS` (48, capped at
  half the target). A heading never ends a chunk: it moves forward to the text it
  introduces, and the heading path (`Benefits > Parental leave`) is stored with the chunk.
- Each chunk's text is an exact slice of its section's text (`char_start`, `char_end`),
  which is what lets the viewer highlight a cited passage.
- A workspace can override the target and the overlap; they apply the next time a document
  is indexed.

### Indexing (`services/ingestion.py`)

1. Lock the row (`SELECT ... FOR UPDATE`); a missing row (deleted while queued) or a
   `ready` one (duplicate delivery) completes the job without work.
2. Mark it `processing`, increment `attempts`, commit.
3. Inside `anyio.fail_after(INGEST_TIMEOUT_S)`: read the original, parse and chunk in a
   worker thread, embed.
4. Embeddings are contextual: each chunk is embedded as `title \n heading \n text`, so "what
   is new in release 4.2" finds the "New" section of the 4.2 release notes. Batches of 256
   go through the embedding cache.
5. Replace the document's sections and chunks in one transaction (with a SHA-256 per chunk
   text), set `ready`, counts and warnings, adopt the title from the file's metadata when the
   current title is still the one derived from the filename, and increment the workspace's
   `corpus_version`.

`ParseError` and timeouts mark the document `failed` with a user-facing message and are not
retried. Anything else is retried (`queued` again) unless it was the final attempt.

## 5. Retrieval

### Candidates (`repositories/search.py`)

Both searches are static SQL with bound parameters, filtered by `workspace_id` and an
optional document list (`NULL` means every document in the workspace).

| Search | SQL | Detail |
| --- | --- | --- |
| Vector | `ORDER BY embedding <=> :query LIMIT :limit` on the HNSW index (`vector_cosine_ops`, `m = 16`, `ef_construction = 64`) | Before the query, `set_config('hnsw.ef_search', max(40, 2 x limit), true)` and `set_config('hnsw.iterative_scan', 'relaxed_order', true)`: pgvector 0.8 keeps scanning the graph until enough rows pass the workspace and document filters, instead of post-filtering a fixed top list. Relaxed order can return near-ties out of order, so the results are re-sorted by score |
| Keyword | `ts_rank_cd(tsv, q, 32)` with `tsv @@ q` on the GIN index | `q` is an OR `to_tsquery` over up to 24 distinct stemmed content words of the question. `websearch_to_tsquery` would AND every word, which is right for a search box and wrong for a natural-language question |

`RETRIEVAL_CANDIDATES` (30) is taken from each.

### Fusion, diversity, packing (`ai/retrieval.py`, `services/retrieval.py`)

1. Reciprocal Rank Fusion with `k = 60`: `score(c) = sum over lists of 1 / (60 + rank)`. It
   needs no calibration between cosine similarity and `ts_rank_cd`.
2. The fused top list is hydrated in one query (text, location, offsets, embedding).
3. Maximal Marginal Relevance picks up to `2 x top_k` sources, trading relevance
   (min-max-scaled fused score) against redundancy (cosine similarity to sources already
   chosen) with a diversity weight of 0.3.
4. Greedy packing into the context budget (`CONTEXT_TOKEN_BUDGET`, 1800, or the workspace
   override) up to `top_k` sources (6 by default); a source that does not fit is skipped and
   a smaller one may still fit. Packed sources are numbered from 1 for citation.

Search uses steps 1 and 2 only (no MMR, no packing), and adds `ts_headline` snippets.

## 6. Answering

### Flow (`services/chat.py`)

1. Choose the generator: the configured one, or the extractive answerer when the workspace's
   `answer_mode` is `extractive`.
2. Resolve the scope: the conversation's documents, or the request's `document_ids`
   (only `ready` documents of this workspace survive; none left is `422 empty_scope`).
3. In a conversation, store the user message and load the last six messages; the first
   question names a new conversation.
4. Standalone question: a follow-up is detected when it opens with a connector ("and",
   "what about"), refers back with a pronoun ("it", "they"), or has fewer than two content
   words. With a model, the model rewrites it (`CONDENSE_PROMPT`); without one, the content
   words of the previous question are appended.
5. Embed the standalone question, compute the baseline (the tokens of every ready document
   in scope plus the question), build the cache key and look up both cache levels.
6. On a miss: retrieve, emit `sources`, stream the generator's deltas, extract citations,
   store both cache levels (only answers with citations that are not "not found").
7. Store the assistant message (conversations) and a usage event; emit `done` with the
   message, citations, sources and usage (`generator`, `cache`, `context_tokens`,
   `prompt_tokens`, `completion_tokens`, `baseline_tokens`, `saved_tokens`, `saved_ratio`,
   `latency_ms`).

With no ready documents in scope the answer says so; with documents but no retrieved
passage it says it could not find an answer.

### The extractive answerer (`ai/extractive.py`)

Offline, deterministic, no model ([ADR 0003](adr/0003-extractive-answerer-as-offline-default.md)):

1. Retrieved passages are split into answer units: sentences, list items and table records.
   Short heading-like blocks become context for the units below them, not candidates.
2. Each unit is scored by IDF-weighted coverage of the question's stemmed content words (with
   half credit for words in its heading and a quarter for words in its document title), plus
   half the centred cosine similarity between the unit and the question, a boost for numbers
   when the question asks for one, a small boost by source rank, and a penalty for very long
   units. Words that name a document ("the Globex agreement") weigh less and instead target
   that document's units.
3. Superlative questions ("which site had the best pick rate?") compare one numeric column
   across table records and lead with the winner.
4. A heading that matches the question returns its whole section; otherwise the best unit is
   joined by up to four more that carry an informative question word and are not near
   duplicates, kept in document order and cited.
5. When no unit covers at least a quarter of the question, the answer is "I could not find a
   clear answer" with a pointer to the closest passage.

The generator emits the answer line by line so the client renders it like a model stream.

### Model generation (`ai/generation.py`, `ai/prompts.py`)

- Clients: OpenAI-compatible Chat Completions (`LLM_BASE_URL`, streaming with
  `stream_options.include_usage`) and Ollama `/api/chat`. Errors become `502
  upstream_error`; the provider's response body is logged, never returned.
- Prompt: a system prompt that allows only the numbered sources, requires `[n]` citations,
  and says that instructions inside sources are data. Sources are fenced in `<sources>`
  blocks with their title and location; the last four turns of history (2,000 characters
  each) are included.
- When a server does not report usage on a stream, prompt and completion tokens are counted
  with the same tokenizer.

### Generator versions

Each generator has a `version` (extractive `2`, model `1`) that is part of the cache key as
`label#version` (for example `extractive#2`, `openai:gpt-4.1-mini#1`), so an upgrade of the
algorithm or the prompt never serves answers produced by the previous one.

### Token counting (`ai/tokens.py`)

tiktoken `o200k_base`, baked into the image. Without it (an air-gapped host missing the
file, or `TOKENIZER=heuristic`) the counter falls back to four characters per token and logs
that once.

## 7. Citations

`ai/citations.py`, applied to every answer, model or extractive:

1. Markers `[n]`, `[1][3]` and `[1, 3]` are parsed; numbers that point at a source the answer
   was not given are removed, so a citation is never a dead link.
2. For each cited source, the first sentence that cites it is the claim, and the quote is the
   source sentence sharing the most content words with it (at most 320 characters).
3. A citation carries the chunk and document ids, the document title, the location, the
   section ordinal and the chunk's character offsets, which the viewer uses to open the
   document at the passage and highlight it.

## 8. Caches

### Answer cache (`services/answer_cache.py`, [ADR 0004](adr/0004-two-level-answer-cache.md))

| Level | Store | Key | Lookup |
| --- | --- | --- | --- |
| Exact | Valkey | `ans:{workspace}:{corpus_version}:{generator#version}:{scope}:{sha256(normalised question)}` | One `GET`. Normalisation lower-cases, collapses whitespace and strips trailing `?`, `.` and `!` |
| Semantic | `answer_cache` table | Same workspace, scope hash, corpus version and generator, not expired | Nearest question embedding by cosine distance; accepted at `SEMANTIC_CACHE_THRESHOLD` (0.95) or above; `hits` and `last_hit_at` recorded |

The scope is `all`, or the first 32 hex characters of the SHA-256 of the sorted document
ids. Every upload that becomes ready, and every deletion of a ready document, increments
the workspace's `corpus_version`, which retires every entry at once without a purge.
Entries live `ANSWER_CACHE_TTL_S` (seven days); `0` disables storing. Owners can turn the
cache off per workspace (`cache_enabled`).

### Embedding cache (`ai/embeddings.py`)

Read-through Valkey cache keyed `emb:{model}:{dim}:{doc|query}:{sha256(text)}`, holding raw
float32 bytes, one `MGET` per batch and one pipelined write for the misses, TTL
`EMBEDDING_CACHE_TTL_S` (30 days). Re-uploading a file, the same paragraph in two documents
or a popular question cost a cache round trip instead of a model call. Cache errors are
logged and fall through to the model.

### Other Valkey keys

| Key | Purpose | Lifetime |
| --- | --- | --- |
| `rl:{bucket}:{principal}:{window}` | Rate-limit counter | 61 seconds |
| `session:revoked:{jti}` | Signed-out session | The token's remaining life |
| `apikey:touched:{key_id}` | `last_used_at` write throttle | 60 seconds |
| `lock:reaper` | One reaper per deployment | 55 seconds |
| `insights:{workspace}:{days}` | Insights overview | 30 seconds |

## 9. The worker

`worker.py`, one process per task:

| Aspect | Behaviour |
| --- | --- |
| Receive | Long poll with 10-second waits, up to `min(10, free slots)` messages, visibility 300 seconds, `ApproximateReceiveCount` requested |
| Concurrency | `WORKER_CONCURRENCY` documents at once (2 by default); when full, waits for one to finish |
| Heartbeat | Every 150 seconds, extends the message's visibility by 300 seconds while the document is processed |
| Outcome | Done: delete the message. Retry: leave it and push its visibility out by `30 s x receive count`. The third receive is the final attempt: a failure marks the document failed and deletes the message |
| Dead letters | SQS moves a message received three times without being deleted (a worker that keeps dying on it) to the dead-letter queue (`maxReceiveCount = 3`, 14-day retention); an alarm fires on any message there |
| Malformed messages | Logged and deleted |
| Reaper | Every 60 seconds the worker holding `lock:reaper` re-sends documents unfinished for `STALE_PROCESSING_MINUTES` (15): processing ones always, queued ones only while the queue is empty, because with a backlog their message is most likely still waiting. Each re-sent document restarts its clock, so it is re-sent at most once per window; documents out of attempts are marked failed. The same pass deletes expired semantic cache rows |
| Shutdown | `SIGTERM` or `SIGINT` stops receiving, waits up to 120 seconds for in-flight documents, closes the container |
| Metrics | `WORKER_METRICS_PORT` starts a Prometheus endpoint, also used as the container health check locally |

The worker refuses to start unless `QUEUE_BACKEND=sqs`. With `inline`, the API runs the
same `IngestionService.process` as a background task, for development and tests.

## 10. Rate limits

`core/ratelimit.py`: fixed one-minute windows in Valkey, one `INCR` and one `EXPIRE NX` per
request in a single round trip, shared by every task. A short burst is possible at a window
boundary, an accepted trade for O(1) memory per caller.

| Bucket | Routes | Keyed by | Limit |
| --- | --- | --- | --- |
| `login` | `POST /auth/login`, `POST /auth/signup` | Client IP | `RATE_LIMIT_LOGIN` (10 per minute) |
| `chat` | Every answer endpoint and search | User or API key | `RATE_LIMIT_CHAT` (30 per minute) |
| `upload` | `POST /documents` | User or API key | `RATE_LIMIT_UPLOAD` (60 per minute) |

Answer, search and upload responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset`, and a refused request gets `429` with `Retry-After`. A refused sign-in
gets `429 rate_limited` with a plain message.

## 11. Observability

| Signal | Implementation |
| --- | --- |
| Logs | structlog, JSON lines (`LOG_FORMAT=json`) or console; standard-library loggers (uvicorn, SQLAlchemy, botocore) routed through the same pipeline; every line carries the request id; keys containing `password`, `secret`, `token`, `authorization`, `api_key` or `cookie` are replaced with `[redacted]`. One `request` line per HTTP request (method, route template, status, duration), except health and metrics paths |
| Metrics | `docmind_http_requests_total` and `docmind_http_request_duration_seconds` by method, route template and status; `docmind_ingested_documents_total` by kind and outcome; `docmind_ingest_duration_seconds`; `docmind_retrieval_duration_seconds`; `docmind_generation_duration_seconds` by provider; `docmind_tokens_total` by kind (context, prompt, completion, baseline, saved); `docmind_answer_cache_total` and `docmind_embedding_cache_total` by result |
| Usage | `usage_events` per answer and search, aggregated by `GET /workspaces/{ws}/insights?days=` (1 to 90, 14 by default) into totals, a daily series, latency percentiles and the most cited documents |
| Audit | `audit_events` for workspace, member, document and API key changes, readable by owners |

## 12. Database access

`db/session.py`:

- One async engine per process: pool of `DATABASE_POOL_SIZE` (10) plus
  `DATABASE_MAX_OVERFLOW` (10), pre-ping, connections recycled after 30 minutes,
  `application_name=docmind`, `jit=off` (JIT costs more than it saves on short queries).
- The pgvector codec is registered on every connection, so embeddings travel as binary
  numpy arrays, not text.
- With `DATABASE_SECRET_ARN` (AWS), the password is not in `DATABASE_URL`: a `do_connect`
  hook reads it from the RDS-managed secret for each new connection, cached for 60 seconds,
  so a password rotation needs no redeploy.
- Timestamps generated by the database are fetched with `RETURNING` on insert and update
  (`eager_defaults`), so an updated row can be returned without a lazy load.

`db/migrate.py` runs Alembic programmatically on a pool-less engine (without the vector
codec, because on a fresh database the type does not exist until the first migration
creates the extension), inside `pg_advisory_xact_lock(0x646F636D696E64)`: replicas booting
together wait for one another and then find nothing to do. Migrations live in
`migrations/versions/` inside the package, so the image carries them.
