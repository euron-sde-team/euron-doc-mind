# ADR 0005: Ingestion through SQS and a separate worker, with a dead-letter queue

## Status

Accepted.

## Context

Indexing a document means reading it from storage, parsing an untrusted file, chunking it
and computing hundreds of embeddings: seconds to minutes of CPU per file, with memory spikes
on large PDFs and spreadsheets. Doing that inside the API would compete with interactive
requests and put the riskiest code (parsers of hostile files) in the process that holds
sessions. Uploads arrive in bursts (a team importing a folder), and a document must never
be lost or processed twice in parallel, even when a task dies mid-way.

## Decision

- The API stores the original, commits the `documents` row as `queued`, then sends an SQS
  message with only the workspace and document ids.
- A separate worker service (`python -m docmind.worker`, same image) long-polls the queue
  with bounded concurrency (`WORKER_CONCURRENCY`), and extends a message's visibility while
  it works on it (a heartbeat every 150 seconds).
- Processing is idempotent: the worker locks and re-reads the row; a missing (deleted) or
  already `ready` document completes without work; content is replaced, not appended.
- Unreadable files fail at once with a message for the user; unexpected errors are retried
  with growing back-off; the third attempt marks the document failed.
- The queue redrives a message received three times without completion to a dead-letter
  queue (kept 14 days), and an alarm fires on any message there.
- A reaper, run by one worker at a time (a Valkey lock), re-sends documents left unfinished
  for 15 minutes, re-sending queued ones only while the queue is empty, so a backlog is never
  multiplied.
- For development and tests, `QUEUE_BACKEND=inline` runs the same processing as a
  background task in the API process.

## Consequences

Positive:

- The API stays responsive during bulk uploads; ingestion scales independently (worker
  tasks autoscale on CPU).
- Parsers run in a process with narrower IAM permissions than the API (read objects,
  consume the queue).
- Crashes lose nothing: unacknowledged messages come back; poison documents end in the
  dead-letter queue instead of looping.
- Locally, the same code path runs against Floci's SQS ([ADR 0006](0006-floci-for-local-aws.md)).

Trade-offs:

- One more service and one more AWS resource to run and monitor.
- Indexing is asynchronous: the UI polls until documents are ready.
- SQS delivers at least once; correctness relies on the idempotent processing described
  above.

## Alternatives considered

- **Background tasks in the API process.** Simplest, kept for development, but couples
  ingestion to request serving and loses work on restart.
- **A Postgres-backed job table.** One less service, but polling load on the primary
  database and no managed dead-letter handling.
- **Celery or RQ on Redis.** Mature, but adds a broker with its own durability semantics
  where Valkey is deliberately a rebuildable cache.
