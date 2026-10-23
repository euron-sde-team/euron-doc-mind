# Testing

Euron DocMind has six layers of automated checks. Each one proves something different;
this page says what, and how to run it.

| Layer | Command | Needs | Proves |
| --- | --- | --- | --- |
| Static checks | `make lint typecheck` | Python 3.12 with uv, Node 22 with pnpm | Style and types: ruff, ruff format, mypy (strict) on the API; ESLint, Prettier and tsc on the web app and the e2e package |
| Unit tests | `make test` | Same | Pure logic without services: parsers, chunking, retrieval math, the extractive answerer, citations, security primitives, configuration, the HTTP layer, front-end helpers |
| Integration tests | `make test-integration` | Docker (Postgres with pgvector, Valkey, Floci) | The real API in process against real services: answers, caches, documents in S3, the SQS worker, access control, migrations |
| Browser end-to-end | `make e2e` | The local stack with demo data, Playwright Chromium | User journeys through the real web app, API, worker and emulator |
| Browser QA crawl | `make qa` | Same | Every page at desktop and mobile widths: no console errors, failed requests, sideways scrolling, broken links or serious accessibility violations |
| Infrastructure | `make tf-fmt tf-validate tf-lint tf-security sanitize` | Docker (or local tools) | Terraform formatting, validity, lint and policy; no credentials or account identifiers in the tree |

Install dependencies once:

```bash
cd apps/api && uv sync && cd ../..
corepack enable
pnpm install
```

## Unit tests

```bash
make test        # pytest tests/unit, then Vitest for the web app
```

No database, no network, no model download (tests that need embeddings use the
deterministic hash embedder, and provider tests mock HTTP). API unit tests live in
`apps/api/tests/unit` (111 tests):

| Suite | Tests | Covers |
| --- | --- | --- |
| `test_parsers.py` | 22 | PDF pages, headings (numbered and wrapped) and tables, PDFs without text (the OCR hint), encrypted PDFs, the page limit; Word sections, tables and lists; Excel sheets and number formats; CSV records and the row limit; slides with tables and speaker notes; Markdown and HTML sections, with page chrome and scripts never indexed; plain-text headings, hyphenation and bullets; empty files |
| `test_sniff_and_archive.py` | 15 | Every supported format detected; unknown extensions and content that does not match its extension refused; titles from filenames; the archive guard accepts real files and refuses a decompression bomb, the wrong kind of Office file and garbage |
| `test_extractive.py` | 8 | The best sentence answers and is cited; "not found" when the documents do not cover the question; list items travel with their siblings; a matching heading returns its section; superlatives compare a numeric column; naming a document targets it; meaning breaks lexical ties; headings are context, not answers |
| `test_infrastructure.py` | 8 | UUIDv7 layout and ordering; answer-cache keys ignore case, spacing and punctuation; local storage round trip and refusal of unsafe keys; the inline queue runs and drains |
| `test_security.py` | 8 | Argon2 round trip and unknown users; the password policy; session round trip and refusal of tampered, expired and foreign-audience tokens; API key parsing and verification with the pepper |
| `test_text.py` | 6 | Normalisation, sentence splitting around abbreviations and decimals, spans that slice the original text, consistent stemming, content terms, word-boundary truncation |
| `test_chunker.py` | 5 | Chunks are exact slices, never cross sections, respect targets and overlap; a heading never ends a chunk; huge sentences fall back to word windows |
| `test_generation.py` | 5 | OpenAI-compatible streaming and usage, provider errors as `upstream_error`, Ollama's NDJSON stream (all against mocked HTTP with `respx`); token counting when the server reports none; the extractive generator streams line by line |
| `test_http_layer.py` | 5 | Typed errors in the envelope with a request id; unexpected errors hide internals; validation errors list every field; invalid request ids are replaced; oversized bodies are refused before parsing |
| `test_retrieval_math.py` | 5 | Reciprocal rank fusion (agreement and weights), MMR diversity, context packing (budget, numbering, always the best passage) |
| `test_chat_errors.py` | 4 | Answer errors keep their status code in JSON responses; a stream without an answer is an upstream error; streams are closed on errors |
| `test_config.py` | 4 | Development defaults refused in production; a real production configuration passes; secrets must differ and hash embeddings are test-only; generator labels |
| `test_embeddings.py` | 4 | Hash embeddings are deterministic, normalised and lexical; the cache serves repeats without the model; OpenAI requests the configured width; an Ollama width mismatch is reported |
| `test_citations.py` | 3 | Valid markers become citations and invalid ones disappear; grouped markers are split and deduplicated; the quote is the supporting sentence |
| `test_prompts.py` | 3 | Sources are fenced and recent history kept; follow-up detection; standalone rewriting without a model |
| `test_ratelimit.py` | 2 | Fixed windows allow then block; limits are per key |

The web app's Vitest suites (`apps/web/src/lib/*.test.ts`, 23 tests in 7 files) cover the
API client's error mapping, the SSE parser (split chunks, CRLF, keep-alives), the answer
Markdown subset (which never produces markup from model output), snippet highlighting
(document HTML stays text), formatting, the `/env.js` serialiser (it cannot close its own
script tag) and which workspace to open after sign-in.

## Integration tests

```bash
make test-integration
```

`scripts/test-deps.sh` starts Postgres (pgvector), Valkey and Floci from the Compose file
(they are left running for the next run), then pytest runs `tests/integration` with
`-m integration` (41 tests). The suite never touches development data:

| Resource | What the suite does |
| --- | --- |
| Database | Drops and recreates `docmind_test` on the Compose Postgres, then migrates it |
| Valkey | Uses database 15 and flushes it first |
| Floci | Creates its own KMS key, bucket `docmind-it-<run>`, queue and dead-letter queue |
| Embeddings | The real local model (fastembed), downloaded once into the user cache on first run |
| The application | `create_app()` with its real lifespan, called in process through `httpx.ASGITransport`; ingestion runs inline except in the worker suite |

A session fixture uploads the nine sample documents once and waits until they are indexed;
the answer suites ask against that corpus.

| Suite | Tests | Covers |
| --- | --- | --- |
| `test_answers.py` | 14 | Eight grounded questions across every format must state the fact and cite the right document; every citation's quote is found at its offsets; "not found"; scoping to one document; follow-ups in a conversation; the SSE event order; hybrid search ranking and safe highlights |
| `test_access.py` | 7 | An outsider gets `404` on 23 workspace endpoints; ids from another workspace resolve to nothing; viewer and editor limits; member removal; API key scope, last use and revocation; sign-out and password change; the CSRF rule for cookie sessions; closed sign-up |
| `test_platform.py` | 6 | S3 round trip and missing objects; Valkey rate limits; per-IP sign-in limits over HTTP; the database password from Secrets Manager; three concurrent migrations on a fresh database; readiness |
| `test_documents.py` | 5 | Rejections and duplicates; originals stored with SSE-KMS and downloaded byte for byte; sections and counts; rename, reprocess and delete (the document leaves search); library filters |
| `test_worker.py` | 5 | Uploads through SQS to the index with a real worker; unreadable files fail once and leave the queue; the reaper re-sends a lost message, leaves waiting documents alone during a backlog and fails documents out of attempts |
| `test_cache.py` | 4 | Exact, semantic and reset-on-upload; the scope in the cache key; turning the cache off; insights totals |

Point the suite elsewhere with `TEST_DATABASE_ADMIN_URL`, `TEST_REDIS_URL` and
`TEST_AWS_ENDPOINT_URL` (see [configuration.md](configuration.md#integration-tests)). Plain
`pytest` deselects integration tests (`-m 'not integration'` in `pyproject.toml`).

## Browser tests

The browser suites run against the local stack and sign in as the demo accounts, so start
it first:

```bash
make up && make demo
pnpm exec playwright install chromium   # once
make e2e
```

`make e2e`, `make qa` and `make screenshots` read the demo password from
`deploy/compose/.env`. The Playwright configuration is `e2e/playwright.config.ts`; the suites
share one database, so they run in one worker, in file order.

### End-to-end (`e2e/tests`, 14 tests)

| Spec | Journeys |
| --- | --- |
| `auth.spec.ts` | A wrong password is refused; signing in opens the workspace and signing out ends the session; a signed-out visit returns to the requested page after sign-in |
| `chat.spec.ts` | An answer streams in with a citation that opens the cited passage highlighted in the viewer; a follow-up uses the conversation; an unanswerable question says so |
| `documents.spec.ts` | An editor uploads a Markdown file, watches it become ready, opens it, renames and deletes it; filtering the library; a viewer cannot change the library |
| `search-insights.spec.ts` | Search highlights matches and opens the document; insights show the totals and charts |
| `settings.spec.ts` | The owner adds a member and sees the temporary password once; creates an API key shown once; viewers see neither keys nor activity |

### QA crawl (`e2e/qa`)

```bash
make qa
```

For desktop (1440 x 900) and mobile (390 x 844), signed out and signed in as the owner, it
visits the sign-in page, chat, a conversation, the library, a document, search (with
results), insights and every settings tab. A page fails on console errors, uncaught
exceptions, failed or 4xx/5xx requests, sideways scrolling, broken internal links and
serious or critical axe violations (WCAG 2 A and AA). A full-page capture of every page is
written to `e2e/.qa/` for a visual review.

### Screenshots and the tour

```bash
make screenshots
```

Captures the README screenshots at 1440 x 900 and 2x pixel density into
`docs/assets/screenshots/`, from the seeded demo (a live question is asked while capturing),
and assembles `docs/assets/tour.gif` from tour frames without ffmpeg.

## Infrastructure and repository checks

```bash
make tf-fmt tf-validate    # every environment, no credentials needed
make tf-lint               # tflint (pinned container)
make tf-security           # checkov (pinned container); skips are justified inline
make sanitize              # no AWS keys, private keys, account ids or committed env files
```

## Continuous integration

`.github/workflows/checks.yml` runs on every push and pull request: ruff, mypy, the API unit
tests, ESLint, tsc, Vitest, `terraform fmt` and `validate` for every environment, and the
sanitization scan. The complete pipeline (integration tests on service containers, image
builds, browser tests on the full stack, gitleaks, CodeQL, tflint and checkov) is in
`.github/workflows-full/`; see its README to enable it in a fork.
