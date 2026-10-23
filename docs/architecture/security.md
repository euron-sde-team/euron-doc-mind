# Security architecture

This page describes the security controls in Euron DocMind as implemented, with the file
that implements each one, and ends with a checklist for operators. The STRIDE analysis and
the residual risks are in [threat-model.md](threat-model.md). To report a vulnerability,
follow [SECURITY.md](../../SECURITY.md). Paths are relative to `apps/api/src/docmind/`
unless they start with the repository root.

Contents:

1. [Authentication](#authentication)
2. [API keys](#api-keys)
3. [Authorisation and workspace isolation](#authorisation-and-workspace-isolation)
4. [CSRF and CORS](#csrf-and-cors)
5. [Production boot guard](#production-boot-guard)
6. [HTTP hardening](#http-hardening)
7. [Untrusted files](#untrusted-files)
8. [Untrusted text and prompt injection](#untrusted-text-and-prompt-injection)
9. [Data protection](#data-protection)
10. [Model providers](#model-providers)
11. [Logging and privacy](#logging-and-privacy)
12. [Infrastructure](#infrastructure)
13. [Operator checklist](#operator-checklist)

## Authentication

Implemented in `core/security.py`, `services/auth.py` and `api/deps.py`.

| Control | Implementation |
| --- | --- |
| Password hashing | Argon2id (`argon2-cffi`), time cost 3, 64 MiB memory, parallelism 2 (the second recommended profile of RFC 9106), computed in a worker thread so the event loop stays responsive. Hashes are upgraded on the next sign-in when parameters change |
| Password policy | 10 to 256 characters, at least 4 distinct characters, not equal to the email address. Applied on sign-up and password change |
| Account lockout | 8 consecutive failures lock the account for 15 minutes; while locked, even the correct password is refused (`429`). A successful sign-in resets the counter |
| IP rate limit | `POST /auth/login` and `POST /auth/signup`: `RATE_LIMIT_LOGIN` requests per client IP per minute (10 by default), counted in Valkey and shared by every API task |
| Enumeration | Unknown emails are verified against a dummy Argon2 hash, so a miss costs as much as a wrong password; both return `401 invalid_credentials` with the same message |
| Sign-up | Open only for the very first account of a deployment, unless `ALLOW_SIGNUP=true`. Everyone else is added by a workspace owner |
| Session token | HS256 JWT signed with `SESSION_SECRET`; issuer `docmind`, audience `docmind-web`; claims `sub`, `sv` (session version), `jti`, `iat`, `exp`; lifetime `SESSION_TTL_HOURS` (7 days). `exp`, `iat`, `sub` and `jti` are required |
| Token transport | The web app uses the `docmind_session` cookie: `HttpOnly` (unreadable by scripts), `SameSite=Lax`, `Secure` with `COOKIE_SECURE=true`. API clients send the same token as `Authorization: Bearer` |
| Per-request reload | Every request reloads the user row; a deleted user or a token with an old `sv` is refused |
| Revocation | Sign-out puts the token's `jti` on a Valkey denylist for the token's remaining life. A password change increments `session_version`, which ends every other session at once, and returns a fresh token so the caller stays signed in |
| Temporary passwords | Created when an owner adds a member who has no account: 14 random characters from an unambiguous alphabet, returned once in the response and never stored in plain text |

## API keys

Implemented in `core/security.py` and `services/api_keys.py`.

| Control | Implementation |
| --- | --- |
| Format | `dmk_<prefix>_<secret>`: a 10-character base32 prefix and a 43-character secret from `secrets.token_urlsafe(32)` (256 bits) |
| Storage | The prefix and `HMAC-SHA256(API_KEY_PEPPER, secret)`. A copy of the database alone cannot be used against the API; the pepper lives in Secrets Manager |
| Verification | Lookup by the unique prefix, constant-time comparison (`hmac.compare_digest`), then revocation and expiry checks; every failure is `401 invalid_api_key` |
| Scope | One workspace, role `viewer` or `editor` (never owner). A key asking for another workspace gets `404`. Account endpoints refuse keys with `403` |
| Lifecycle | Optional expiry (30, 90 or 365 days in the UI, any 1 to 365 through the API); revocation takes effect on the next request; creation and revocation are audited |
| Display | The full key is shown once, at creation; lists show the prefix only |

## Authorisation and workspace isolation

| Control | Implementation |
| --- | --- |
| Roles | `viewer` < `editor` < `owner` (`models/enums.py`); each route declares its minimum with `ViewerDep`, `EditorDep` or `OwnerDep` (`api/deps.py`) |
| Non-members | `WorkspaceService.resolve` returns `404 Workspace not found` for non-members and for keys of other workspaces, so the existence of a workspace is not disclosed |
| Scoped queries | Every repository method that takes an id also takes the resolved `workspace_id`; a document, conversation or key id from another workspace finds nothing (`404`). Retrieval filters chunks by `workspace_id` in SQL, before ranking |
| Document scopes | Requested `document_ids` are intersected with the workspace's ready documents (`ChatService.validated_scope`); ids from elsewhere are dropped silently |
| Conversations | Private to the person who started them, even within a workspace |
| Last owner | The last owner cannot be demoted, removed or leave (`_keep_an_owner`) |
| Tests | `tests/integration/test_access.py` sweeps 23 workspace endpoints as an outsider (all `404`), checks ids from another workspace, role limits for viewers and editors, key scoping, revocation, sign-out, password change and the CSRF rule |

## CSRF and CORS

| Control | Implementation |
| --- | --- |
| Origin check | For cookie sessions, every method other than `GET`, `HEAD` and `OPTIONS` must come with an `Origin` (or `Referer`) in `CORS_ORIGINS` or equal to `WEB_URL`, else `403 csrf` (`api/deps.py`). Bearer tokens and API keys are not ambient credentials and skip the check |
| SameSite | The session cookie is `SameSite=Lax`, so cross-site subrequests do not carry it |
| CORS | Exactly the origins in `CORS_ORIGINS`, with credentials; production refuses `*` or an empty list |

## Production boot guard

`Settings.production_problems()` (`core/config.py`) runs at start-up with
`APP_ENV=production`, and the API refuses to start, listing every problem at once, when:

- `SESSION_SECRET` or `API_KEY_PEPPER` is the development default or shorter than 32
  characters, or the two are equal;
- `COOKIE_SECURE` is false;
- `CORS_ORIGINS` is empty or contains `*`;
- storage is not S3 with a bucket, or the queue is not SQS with a queue URL;
- `AWS_ENDPOINT_URL` is set (an emulator);
- `EMBEDDINGS_PROVIDER=hash` (lexical test vectors);
- a model provider is set without `LLM_MODEL`.

The demo seeder refuses to run with `APP_ENV=production`.

## HTTP hardening

| Control | Implementation |
| --- | --- |
| Response headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cross-Origin-Resource-Policy: same-site` on every API response; `Strict-Transport-Security` in production (`core/context.py`). The web app sends `nosniff`, `strict-origin-when-cross-origin`, `DENY` and a restrictive `Permissions-Policy` (`apps/web/next.config.ts`) |
| Request size | Bodies over 20 x `MAX_UPLOAD_MB` + 1 MiB are refused before the multipart parser buffers them, including chunked bodies; each file is checked against `MAX_UPLOAD_MB`; at most 20 files per request |
| Rate limits | Per principal for answers, search and uploads; per IP for sign-in and sign-up |
| Errors | One envelope; `500` responses never echo the exception; every response carries `X-Request-Id` for support |
| Request ids | An incoming `X-Request-Id` is accepted only if it matches `^[A-Za-z0-9._-]{1,64}$`, so it cannot inject into logs |
| Downloads | Originals are streamed by the API after the membership check, as `Content-Disposition: attachment` with `nosniff`, so an uploaded HTML file is never rendered in the API's origin |
| Snippets | Search highlights are control characters, not HTML; the web app renders answers and snippets as React text nodes through a small Markdown subset parser (`apps/web/src/lib/markdown.ts`) and never injects model or document text as HTML |

## Untrusted files

Every upload is hostile until proven otherwise.

| Control | Implementation |
| --- | --- |
| Type check | Extension and magic bytes must agree (`ingestion/sniff.py`); a renamed executable is refused with `415 content_mismatch` |
| Deduplication | SHA-256 per workspace; the same bytes are one document |
| Office archives | Before any XML is read: at most 10,000 entries, no encryption, total uncompressed size under `MAX_UNCOMPRESSED_MB`, compression ratio under 200, and the expected parts present (`ingestion/archive.py`) |
| XML | openpyxl parses through `defusedxml` (a runtime dependency); python-docx and python-pptx use lxml with entity resolution disabled |
| PDF | Encrypted PDFs are refused; at most `MAX_DOCUMENT_PAGES` pages |
| Spreadsheets | At most 50,000 rows per sheet |
| HTML | Parsed as data with BeautifulSoup; scripts, styles, forms and SVG removed; nothing is executed |
| Time | Parsing, chunking and embedding run inside `INGEST_TIMEOUT_S` (600 seconds); a timeout fails the document |
| Isolation | Parsing happens in the worker, not in the API process that serves requests |
| Storage keys | Built from ids only (`workspaces/{id}/documents/{id}/original.{ext}`), never from the filename; the local backend also rejects any key that would leave its root |

## Untrusted text and prompt injection

Document text is untrusted input to the answerer.

- The extractive answerer (the default) only selects and quotes sentences from the
  retrieved passages; there is no model to instruct.
- With a model, sources are fenced in a `<sources>` block, numbered, and the system prompt
  states that instructions inside them are data (`ai/prompts.py`).
- Citations are verified: a marker that points at a source the answer was not given is
  removed (`ai/citations.py`).
- Retrieval never crosses workspaces, so a planted document can only influence answers in
  the workspace it was uploaded to, read by people who can already read it.

Fencing narrows prompt injection; it is not a security boundary. See the residual risks in
[threat-model.md](threat-model.md#information-disclosure).

## Data protection

| Data | At rest | In transit |
| --- | --- | --- |
| Original files | S3, SSE-KMS with the deployment's customer-managed key, private, versioned, TLS-only bucket policy | HTTPS to S3 (gateway endpoint) |
| Database | RDS storage, snapshots and Performance Insights encrypted with the key | `rds.force_ssl = 1`; the application URL sets `ssl=require` |
| Cache | ElastiCache encrypted at rest with the key, auth token required | TLS (`rediss://`); the URL with the token reaches tasks only through Secrets Manager |
| Queue | SQS with the key (KMS data key reuse 5 minutes) | HTTPS |
| Secrets | Secrets Manager, encrypted with the key; injected into tasks, never in a task definition | HTTPS |
| Logs | CloudWatch log groups encrypted with the key | |

The API never hands out presigned URLs: it checks the caller, reads the object and streams
the bytes itself. The key rotates yearly. Deleting a document deletes its rows and its
object; deleting a workspace deletes every row in one cascade and then its objects.

## Model providers

With `LLM_PROVIDER=none` (the default) and local embeddings (the default), no document text
or question leaves the deployment. When a provider is configured:

| Setting | What leaves the deployment |
| --- | --- |
| `LLM_PROVIDER=openai` (any OpenAI-compatible endpoint) | The question, up to four previous turns of the conversation, and the retrieved passages (about `CONTEXT_TOKEN_BUDGET` tokens) for every answer that is not served from the cache |
| `LLM_PROVIDER=ollama` | The same, to your own Ollama server |
| `EMBEDDINGS_PROVIDER=openai` | Every chunk at indexing time and every question |

Owners can force the offline answerer for one workspace (`answer_mode: extractive`) when a
deployment has a model configured. The provider key is a Secrets Manager secret on AWS
(`llm_api_key_secret_arn`), never a plain environment value.

## Logging and privacy

- Log keys containing `password`, `secret`, `token`, `authorization`, `api_key` or `cookie`
  are replaced with `[redacted]` (`core/logging.py`). Request logs carry the method, the
  route template (not the raw path), the status and the duration.
- Questions and answers are stored in `messages`, the semantic cache and Valkey (for the
  cache TTL), and counted in `usage_events`; deleting a conversation deletes its messages.
- Model provider errors log the HTTP status and the first 300 characters of the provider's
  response, never the prompt.

## Infrastructure

| Control | Implementation |
| --- | --- |
| Network | Tasks, database and cache in private subnets with no public IP; security groups per service allow only the load balancer in and only HTTPS, the database and the cache out; VPC flow logs |
| Edge | ALB with `ELBSecurityPolicy-TLS13-1-2-2021-06`, HTTP redirected to HTTPS, unknown hosts get 404; optional WAF with AWS managed rule groups and a per-IP rate rule |
| IAM | Separate execution and task roles per service. The API may read, write and delete objects under `workspaces/*` and send to the queue; the worker may read objects and consume the queue; both may read only the database secret and use the key only through S3, SQS and Secrets Manager (`kms:ViaService`) |
| Containers | Non-root users (uid 10001 for the API image, `node` for the web image), read-only root filesystem with a writable `/tmp`, `tini` as PID 1, ARM64 |
| Images | Pinned base images; ECR with immutable tags and scan on push |
| Database | Managed master password in Secrets Manager, read per new connection; `idle_in_transaction_session_timeout` of 60 seconds; slow statement logging; deletion protection and a final snapshot in production |
| Detection | Alarms for 5xx responses, unhealthy targets, CPU, memory, ingestion backlog age, dead letters and database health, to an SNS topic |

## Operator checklist

- Keep `APP_ENV=production`; the boot guard then enforces the essentials above.
- Store Terraform state remotely, encrypted and private: it contains the generated secrets.
- Set `alarm_email` and confirm the subscription; watch the dead-letter queue alarm.
- Turn on `enable_waf` for internet-facing deployments.
- Keep `ALLOW_SIGNUP=false` unless the deployment is meant for self-service.
- Create the first account yourself (`make aws-cli ARGS="user create ..."`) before
  announcing the URL, because the first sign-up becomes the administrator.
- Decide deliberately whether to configure a model provider, and which workspaces may use
  it (see [Model providers](#model-providers)).
- Rotate `SESSION_SECRET` (signs everyone out) or `API_KEY_PEPPER` (invalidates every key)
  when you suspect exposure; see [operations.md](../guides/operations.md#rotating-secrets).
- Review the activity tab of sensitive workspaces and revoke unused API keys.
