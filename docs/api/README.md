# API reference

[`openapi.json`](openapi.json) is the OpenAPI 3.1 document of the DocMind API, exported from
the application itself, so it always matches the routes, request bodies and responses in
the code. Regenerate it after changing a route:

```bash
make openapi        # runs `docmind openapi` from apps/api
```

A running API also serves an interactive reference at `/docs` (locally
<http://localhost:8110/docs>), where you can authorise with a token or a key and try every
endpoint. Load `openapi.json` into any OpenAPI tool to generate a client.

## Authentication

| Credential | How to send it | Use it for |
| --- | --- | --- |
| Workspace API key `dmk_...` | `Authorization: Bearer dmk_...` | Your own applications: asking, searching and (with an editor key) uploading in one workspace. Owners create keys in Settings, API keys |
| Session token | `Authorization: Bearer <token>`, the `token` returned by `POST /api/v1/auth/login` | Scripts acting as a person, including account endpoints |
| Session cookie `docmind_session` | Set by sign-in; sent by browsers | The web app. Writes must come from an allowed origin (CSRF check) |

Workspace-scoped paths take `{workspace}` as the workspace's slug (for example
`northwind-robotics`) or its id. Somebody who is not a member, or a key of another
workspace, gets `404`.

## Conventions

| Topic | Behaviour |
| --- | --- |
| Errors | Always `{"error": {"code", "message", "request_id", "details?"}}` with a meaningful status: `401` sign in, `403` role or CSRF, `404` not found or not yours, `409` conflict, `413` too large, `415` unsupported file, `422` invalid input (with `details`), `429` rate limited, `502` model provider failed, `503` dependency down |
| Request ids | Every response carries `X-Request-Id`; send your own (letters, digits, `.`, `_`, `-`, up to 64) to correlate with your logs |
| Rate limits | `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset` on answers, search and uploads; `429` with `Retry-After` when exceeded |
| Pagination | `limit` and `offset` query parameters on lists that grow (documents, conversations, audit); the document library returns `{items, total, limit, offset}` |
| Time | ISO 8601 timestamps in UTC |

## Endpoints

| Area | Endpoints |
| --- | --- |
| System | `GET /api/v1/system/info` |
| Auth | `POST /api/v1/auth/login`, `POST /api/v1/auth/signup`, `POST /api/v1/auth/logout`, `GET` and `PATCH /api/v1/auth/me`, `POST /api/v1/auth/password` |
| Workspaces | `GET` and `POST /api/v1/workspaces`; `GET`, `PATCH` and `DELETE /api/v1/workspaces/{workspace}`; members (`GET`, `POST .../members`, `PATCH` and `DELETE .../members/{user_id}`); `GET .../audit` |
| Documents | `GET` and `POST .../documents` (multipart `files`, up to 20), `GET .../documents/stats`, `GET`, `PATCH` and `DELETE .../documents/{document_id}`, `GET .../documents/{document_id}/file`, `POST .../documents/{document_id}/reprocess` |
| Chat | `GET` and `POST .../conversations`; `GET`, `PATCH` and `DELETE .../conversations/{conversation_id}`; `GET` and `POST .../conversations/{conversation_id}/messages`; `POST .../messages/stream`; `POST .../ask` and `POST .../ask/stream` |
| Search | `POST .../search` |
| Insights | `GET .../insights?days=14` |
| API keys | `GET` and `POST .../api-keys`, `DELETE .../api-keys/{key_id}` |

Health and metrics live outside `/api/v1`: `GET /livez`, `GET /readyz`, `GET /metrics`.

## Examples

Ask a question with a key:

```bash
curl -s https://api.docmind.example.com/api/v1/workspaces/northwind-robotics/ask \
  -H "authorization: Bearer $DOCMIND_KEY" -H 'content-type: application/json' \
  -d '{"question": "What is the parental leave policy?"}'
```

```json
{
  "conversation_id": null,
  "message": {
    "id": "0193...",
    "role": "assistant",
    "content": "Primary caregivers receive 26 weeks of fully paid parental leave. [1]",
    "citations": [
      {
        "n": 1,
        "chunk_id": "0193...",
        "document_id": "0193...",
        "document_title": "Northwind Employee Handbook 2026",
        "location": "Page 4",
        "section_ordinal": 3,
        "char_start": 812,
        "char_end": 1904,
        "quote": "Primary caregivers receive 26 weeks of fully paid parental leave."
      }
    ],
    "sources": ["... every passage the answerer was given ..."],
    "usage": {
      "generator": "extractive",
      "cache": "miss",
      "context_tokens": 1630,
      "prompt_tokens": 0,
      "completion_tokens": 0,
      "baseline_tokens": 18240,
      "saved_tokens": 16610,
      "saved_ratio": 0.9106,
      "latency_ms": 184
    },
    "created_at": "2026-10-23T12:00:00Z"
  }
}
```

The numbers above are illustrative. `char_start` and `char_end` are offsets into the text of
the section `section_ordinal` of `GET .../documents/{document_id}`, which is how the web app
highlights a citation.

Limit a question to some documents with `"document_ids": ["<id>", ...]`.

Stream the same answer as server-sent events:

```bash
curl -N https://api.docmind.example.com/api/v1/workspaces/northwind-robotics/ask/stream \
  -H "authorization: Bearer $DOCMIND_KEY" -H 'content-type: application/json' \
  -d '{"question": "What is the parental leave policy?"}'
```

| Event | Data |
| --- | --- |
| `user_message` | Conversation streams only: the stored question |
| `sources` | `{"sources": [...]}`: the passages the answer will use |
| `delta` | `{"text": "..."}`: the next piece of the answer; concatenate them |
| `done` | The same body as the JSON endpoint |
| `error` | The error envelope; the stream ends |

Upload files with an editor key:

```bash
curl -s https://api.docmind.example.com/api/v1/workspaces/northwind-robotics/documents \
  -H "authorization: Bearer $DOCMIND_EDITOR_KEY" \
  -F files=@handbook.pdf -F files=@budget.xlsx
```

The response lists `created`, `duplicates` (same bytes already in the workspace) and
`rejected` (with a code and a reason per file). Poll `GET .../documents/{id}` until
`status` is `ready` (or `failed`, with `error`).

Search without generating an answer:

```bash
curl -s https://api.docmind.example.com/api/v1/workspaces/northwind-robotics/search \
  -H "authorization: Bearer $DOCMIND_KEY" -H 'content-type: application/json' \
  -d '{"query": "parental leave", "limit": 5}'
```

In each hit's `snippet`, matches are wrapped in the control characters U+0001 (start) and
U+0002 (end), never HTML: split on them and render plain text.
