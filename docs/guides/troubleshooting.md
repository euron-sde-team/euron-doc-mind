# Troubleshooting

Symptoms, their causes and fixes, drawn from the checks and messages in the code. Messages
are quoted as the API returns or logs them. Every API response carries `X-Request-Id`;
searching the logs for it (`make logs SERVICE=api` locally, CloudWatch on AWS) shows
everything that happened in that request.

## The local stack

| Symptom | Cause | Fix |
| --- | --- | --- |
| `make up` fails with `port is already allocated` | Another process uses 3110, 8110, 5451, 6411 or 4611 | Set `DOCMIND_*_PORT` in `deploy/compose/.env` (see [quickstart-local.md](quickstart-local.md#port-clashes)) |
| `make up` stops at `required variable DOCMIND_SESSION_SECRET is missing` | `deploy/compose/.env` is missing or incomplete | `make env` (or delete the file and run it again) |
| `make up` waits, then `terraform` exits with an error | The one-shot provisioning of the emulator failed | `make logs SERVICE=terraform`; then `make down && make up` to start from a clean emulator and state |
| The `worker` never becomes healthy | It starts after the API is healthy; the API waits for the database migrations and Terraform | `make logs SERVICE=api`, then `make logs SERVICE=worker` |
| The first build is slow | The API image downloads the embedding model and the tokenizer once | Later builds reuse the layer |
| Containers are killed, builds fail with exit code 137 | Docker ran out of memory | Give Docker at least 4 GB; stop other stacks |
| `make demo` says `set DEMO_PASSWORD (make env generates one)` | Run outside `make` without the variable | Use `make demo`, or pass `DEMO_PASSWORD=...` |
| `make demo` ends with `documents were not indexed in time` | The worker is not consuming the queue | `make logs SERVICE=worker`; check `make ps` shows it healthy |
| Everything should start over | | `make down` deletes the database, the emulator state and the Terraform state; `make up && make demo` rebuilds them |

## Boot and configuration

| Symptom | Cause | Fix |
| --- | --- | --- |
| The API exits with `Refusing to start in production:` and a list | `APP_ENV=production` with development or unsafe settings | Fix every listed item: secrets of 32+ characters that differ, `COOKIE_SECURE=true`, explicit `CORS_ORIGINS`, `STORAGE_BACKEND=s3` with `S3_BUCKET`, `QUEUE_BACKEND=sqs` with `SQS_QUEUE_URL`, no `AWS_ENDPOINT_URL`, no `hash` embeddings, `LLM_MODEL` when a provider is set |
| `S3_BUCKET is required for STORAGE_BACKEND=s3` or `SQS_QUEUE_URL is required for QUEUE_BACKEND=sqs` | The backend is selected without its resource | Set the variable, or use `local` and `inline` for development |
| The worker exits with `The worker needs QUEUE_BACKEND=sqs` | The worker started with the inline queue | Set `QUEUE_BACKEND=sqs`; with `inline` the API ingests by itself and no worker is needed |
| A validation error naming a setting at start-up | A value outside its range or of the wrong type | See [configuration.md](configuration.md) for the allowed values |
| Log line `tokenizer_fallback` | The tiktoken file could not be loaded (outside the image, offline) | Token counts use four characters per token; set `TIKTOKEN_CACHE_DIR` to a directory holding the cached file, or accept the estimate |
| `GET /readyz` returns `503` with `"redis": "failing"` | Valkey is unreachable | Sign-in checks and rate limits need it; fix `REDIS_URL` or start Valkey |

## Signing in

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Email or password is incorrect.` | Wrong email or password (the message is the same for both on purpose) | Check both; a person added by an owner signs in with the temporary password the owner passed on |
| `Too many failed sign-ins. Try again in N minute(s).` | Eight failures locked the account for 15 minutes | Wait; the lock ends by itself |
| `Too many sign-in attempts. Wait a minute and try again.` | More than `RATE_LIMIT_LOGIN` attempts from one address in a minute | Wait a minute |
| `Sign-up is closed on this deployment. Ask a workspace owner to add you.` | The deployment already has accounts and `ALLOW_SIGNUP` is false | An owner adds you from Settings, Members |
| Signed in, but every action fails with `403` `csrf` (`Cross-site request blocked.`) | The page's origin is not in `CORS_ORIGINS` and is not `WEB_URL`; for example the app opened at `http://127.0.0.1:3110` when only `localhost` is allowed, or a custom port | Open the app at an allowed origin, or add it to `CORS_ORIGINS` |
| Signing in appears to work but the next page asks again | `COOKIE_SECURE=true` over plain HTTP, so the browser drops the cookie; or `COOKIE_DOMAIN` does not match the API host | Use HTTPS, or `COOKIE_SECURE=false` locally; fix `COOKIE_DOMAIN` |
| `Your session has ended. Sign in again.` | The password was changed in another session | Sign in with the new password |
| `This needs a signed-in person, not an API key.` | An API key used on an account endpoint | Use a session token for `/auth/*` |

## Uploads and indexing

| Symptom | Cause | Fix |
| --- | --- | --- |
| Rejected: `.xyz is not supported` | Only PDF, `.docx`, `.xlsx`, CSV, `.pptx`, text, Markdown and HTML are accepted | Convert the file (legacy `.doc`, `.xls` and `.ppt` must be saved in the newer formats) |
| Rejected: `The file's content does not match its .pdf extension.` (`content_mismatch`) | The bytes are not what the extension claims (a renamed file, an HTML error page saved as PDF) | Upload the real file |
| Rejected: `The file is larger than 50 MB.` | Above `MAX_UPLOAD_MB` | Split the file or raise the limit |
| Listed under duplicates | The workspace already has a file with the same bytes | Nothing to do; the existing document is returned |
| Failed: `No readable text was found. Scanned PDFs need OCR before they can be searched.` | The PDF is images only | Run OCR first (many scanners and PDF tools can), then upload the result |
| Warning: `N page(s) had no extractable text and were skipped` | Some pages are scans | The other pages are indexed; OCR the file to include them |
| Failed: `This PDF is password-protected. Remove the password and retry.` (or the same for Office files) | Encrypted files cannot be read | Remove the password and upload again |
| Failed: `... expands to more data than DocMind processes safely.` | An Office file over `MAX_UNCOMPRESSED_MB` uncompressed, or compressed more than 200 to 1 | Split the file, or raise `MAX_UNCOMPRESSED_MB` if it is legitimate |
| Failed: `This PDF has N pages; the limit is 2000.` | Above `MAX_DOCUMENT_PAGES` | Split the file or raise the limit |
| Failed: `Processing took too long and was stopped.` | Above `INGEST_TIMEOUT_S` | Raise the timeout or split the file |
| Failed: `Processing failed. Try reprocessing the document.` | An unexpected error on the third attempt | The worker logs (`ingest_error`) have the traceback for that `document_id`; reprocess from the actions menu |
| Documents stay `Queued` | No worker is consuming (stopped, crashing, or wrong `SQS_QUEUE_URL`) | Worker logs; `GET /readyz` shows the queue check; the reaper re-sends documents after 15 minutes once the queue is empty |
| A worker log line `... produces N dims; EMBEDDING_DIM is M` | The embedding model's width differs from the database column | Use a model of the configured width, or change the width with a migration and reindex ([operations.md](operations.md#changing-the-embedding-model)) |

## Answers and search

| Symptom | Cause | Fix |
| --- | --- | --- |
| `There are no ready documents to answer from yet.` | Nothing in scope is ready | Wait for indexing, or upload files |
| `I could not find a clear answer to that in your documents.` | No passage covers the question well enough | Rephrase with the words the documents use, or check the closest passage it points to; search shows what matches |
| `422` `empty_scope`: `None of the selected documents are ready yet.` | Every selected document is still indexing or failed, or belongs to another workspace | Select ready documents, or ask the whole workspace |
| `502` `upstream_error`: `The model provider returned HTTP 401.` (or timed out, could not be reached) | The model provider refused the key, the model name, or did not answer | Check `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` and `LLM_TIMEOUT_S`; the API log line `llm_error` holds the provider's message |
| `Ollama could not be reached.` from containers | `OLLAMA_URL` points at `localhost`, which inside a container is the container itself | Use `http://host.docker.internal:11434` (the Compose default) |
| An answer is stale after editing a file outside DocMind | The original in storage is what was indexed | Upload the new version (a new file) or reprocess after replacing it |
| The same answer for a paraphrased question | The semantic cache matched it (the answer says `semantic`) | Expected; raise `SEMANTIC_CACHE_THRESHOLD`, or turn the cache off for the workspace |
| `429` `rate_limited` while asking | More than `RATE_LIMIT_CHAT` answers or searches a minute for one person or key | Wait for `Retry-After` seconds, or raise the limit |

## Infrastructure

| Symptom | Cause | Fix |
| --- | --- | --- |
| `make aws-deploy` fails at the push with `tag invalid` or `already exists` | ECR tags are immutable | Commit (the tag is the commit hash) or pass a new `TAG` |
| Services never become stable after a deploy | Tasks fail their health checks; the circuit breaker rolls back | ECS service events and the task logs; `GET /readyz` from a task names the failing dependency |
| The `ingest-dead-letters` alarm fires | A document's message was never completed three times | [operations.md](operations.md#ingest-dead-letters) |
| `terraform validate` fails on a provider download | No network access to the registry | Run `make tf-validate` with network access once; the provider cache volume keeps it |
