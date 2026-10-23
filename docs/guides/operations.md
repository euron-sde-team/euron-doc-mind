# Operations

Day-two tasks for a DocMind deployment on AWS: where to look, what to do when an alarm
fires, and the routine procedures (reindexing, secrets, backups, scaling, upgrades). The
deployment itself is covered in [deploy-aws.md](deploy-aws.md).

## Where to look

| Signal | Where |
| --- | --- |
| Logs | CloudWatch log groups `/docmind/<name_prefix>/api`, `/worker`, `/web` and `/cli`. JSON lines; filter by `request_id` to follow one request (it is also in every response's `X-Request-Id` header) |
| Health | `GET https://api.<domain>/readyz` names the failing dependency (`database`, `redis`, `storage`, `queue`) with a `503` |
| Metrics | `GET /metrics` on each API task (Prometheus format); the CloudWatch dashboard `<name_prefix>` for load balancer, ECS, SQS and RDS metrics |
| Usage | Each workspace's Insights page: questions, cache hit rate, tokens, latency percentiles |
| Changes | Each workspace's Settings, Activity tab (owners): members, documents, keys and settings, with who did it |

Useful CloudWatch Logs Insights queries:

```text
# Slowest requests of the last hour
fields @timestamp, route, status, duration_ms
| filter event = "request"
| sort duration_ms desc
| limit 20

# Why documents failed
fields @timestamp, document_id, reason
| filter event = "ingest_failed"
| sort @timestamp desc
```

## When an alarm fires

### `ingest-dead-letters`

A document's message was received three times without the worker completing it, usually
because the worker task died while processing it (out of memory on a very large file, or a
crash in a parser).

1. Find the document: read the message in the SQS console (dead-letter queue
   `<name_prefix>-ingest-dlq`) or with
   `aws sqs receive-message --queue-url "$(terraform -chdir=infra/terraform/envs/<env> output -raw ingest_dlq_url)"`.
   The body is `{"workspace_id": ..., "document_id": ...}`.
2. Check the worker logs around the time for that `document_id` (`OutOfMemory` and task
   stops show in the ECS service events).
3. Fix the cause (raise `worker_memory`, lower `worker_concurrency`, or ask the uploader for
   a smaller or repaired file).
4. Redrive: in the SQS console, "Start DLQ redrive" back to the source queue, or
   `aws sqs start-message-move-task --source-arn <dlq arn>`. Alternatively delete the
   message and let the user press Reprocess on the document.

### `ingest-backlog`

The oldest queued document has waited more than 10 minutes.

- A burst of uploads: the worker service scales out on CPU up to `worker_max_count`; raise
  it (and `worker_concurrency` if CPU is low) for bigger imports.
- Workers not consuming: check the worker service's running count and logs
  (`queue_receive_failed`), and that its task role can still receive from the queue.

The reaper does not re-send waiting documents while the queue has a backlog, so a backlog
never grows by itself.

### `api-5xx`, `web-5xx`, `*-unhealthy`

Look up a failing request's `request_id` in the API logs (`unhandled_error` lines carry the
traceback). `GET /readyz` tells you whether a dependency is down. A deployment that made
tasks unhealthy is rolled back by the circuit breaker; ECS service events show it.

### `*-cpu`, `*-memory`, `db-*`

Scale the service (task counts, task size) or the database (`db_instance_class`); for
`db-connections`, every task holds up to 20 connections (`DATABASE_POOL_SIZE` 10 plus
`DATABASE_MAX_OVERFLOW` 10), so more tasks need a larger instance or a smaller pool.

## Routine procedures

### Reindex

After changing chunking settings, upgrading the embedding model or restoring files:

```bash
make aws-cli ENV=aws-prod ARGS="reindex --workspace <slug>"   # one workspace
make aws-cli ENV=aws-prod ARGS="reindex"                      # every workspace
```

Documents go back to `queued` and the worker processes them; answers are unaffected until
each document is ready again, and the corpus version then retires cached answers. A single
document can be reprocessed from its actions menu.

### Changing the embedding model

The vector width is fixed by the first migration (`EMBEDDING_DIM`). A model with the same
width (another 384-dimension model) only needs `EMBEDDINGS_MODEL` changed (and the image
rebuilt, because the model is baked in) followed by a full reindex. A different width needs
a new migration that alters `chunks.embedding` and `answer_cache.question_embedding` and
rebuilds the HNSW index, then a full reindex.

### Rotating secrets

| Secret | How | Effect |
| --- | --- | --- |
| Database password | RDS manages it in Secrets Manager and rotates it on its schedule (seven days by default); you can also rotate it on demand in the console | None: the API and the worker read the password for each new connection, cached for a minute |
| `SESSION_SECRET` | Put a new random value (32+ characters) in the `<name_prefix>/app` secret, then force a new deployment of the `api` and `worker` services | Everyone is signed out |
| `API_KEY_PEPPER` | Same secret and procedure | Every API key stops working; owners create new ones |
| Valkey auth token | `terraform apply -replace=module.docmind.module.cache.random_password.auth`, then force a new deployment of `api` and `worker` | The replication group and the `REDIS_URL` secret get the new token; caches survive |
| `LLM_API_KEY` | Update your secret, then force a new deployment | None |

```bash
aws ecs update-service --cluster <name_prefix> --service <name_prefix>-api --force-new-deployment
aws ecs update-service --cluster <name_prefix> --service <name_prefix>-worker --force-new-deployment
```

The session secret and the pepper are separate on purpose (the boot guard refuses equal
values), so you can rotate one without the other.

### Backups and restore

| Data | Protection | Restore |
| --- | --- | --- |
| Database | Automated backups (3 days in `aws-dev`, 14 in `aws-prod`) with point-in-time recovery; a final snapshot on deletion in `aws-prod` | Restore to a new instance, point `DATABASE_URL` and the secret at it, or swap it in by renaming |
| Original files | Bucket versioning; previous versions kept 90 days | Restore an object version in the console; then reprocess the document |
| Cache | Not backed up; everything in it is rebuilt on demand | None needed |

A restored database may reference files deleted since; their downloads return `404`, and
reprocessing them ends with the document marked failed after its retries.

### Auditing access to originals

The bucket has no server access logging by default (it would need a separate log bucket of
your choice). To audit every read of an original, enable CloudTrail data events for the
documents bucket (`s3:GetObject` on `<bucket>/workspaces/*`). Downloads through the web app
are also visible in the API's request logs (`GET .../documents/{document_id}/file`).

### Scaling

| Knob | Where | When |
| --- | --- | --- |
| `api_min_count`, `api_max_count`, `api_cpu`, `api_memory` | `envs/<env>/main.tf` | Many concurrent askers; streamed answers hold a connection for their duration |
| `worker_min_count`, `worker_max_count`, `worker_cpu`, `worker_memory`, `worker_concurrency` | same | Large or frequent imports |
| `db_instance_class`, `db_multi_az` | same | Retrieval latency or connection count |
| `cache_node_type`, `cache_replicas` | same | Large embedding caches |
| `CONTEXT_TOKEN_BUDGET`, `top_k` | settings, workspace settings | Answer quality against model cost |

### Upgrading

Commit, then `make aws-deploy ENV=<env>`. Migrations run when the new API tasks boot,
under an advisory lock. Read the [CHANGELOG](../../CHANGELOG.md) for migrations and
settings that changed.

## Locally

The same procedures work on the local stack: `make reindex WORKSPACE=<slug>`,
`make logs SERVICE=worker`, and the emulator's queues at `http://localhost:4611` with any
AWS CLI (`--endpoint-url http://localhost:4611`, credentials `test`/`test`).
