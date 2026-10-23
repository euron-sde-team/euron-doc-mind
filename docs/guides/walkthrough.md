# Walkthrough: a tour of the demo

This tour uses the demo data to show every part of DocMind, as each of the three demo people,
and names the code behind each step so you can find your way before you change something.
Paths are relative to `apps/api/src/docmind/` unless they start with `apps/web/`.

Start the stack and seed it first:

```bash
make up && make demo
grep DOCMIND_DEMO_PASSWORD deploy/compose/.env   # the password of every demo account
```

Open <http://localhost:3110>.

## 1. Ava asks a question (owner)

Sign in as `ava.martin@northwind.example`. You land in the chat of **Northwind Robotics**,
the workspace with all nine sample files. The sidebar lists the conversations the demo
created over the past two weeks.

Ask:

> How many days of annual leave do employees get?

The answer streams in: "Every full-time employee receives 24 working days of paid annual
leave per year, accrued at two days per month." followed by a citation chip `[1]`.

- Click the chip: the preview shows the sentence the claim rests on, from *Northwind
  Employee Handbook 2026*, and its page.
- Under the answer, the token meter compares the tokens of passages the answerer used with
  the tokens of every document in the workspace (what pasting everything into a chat would
  have cost), with the share saved, the answerer (*Local extractive*) and the time taken.
- The source cards list the passages the answerer was given: cited ones first, the others
  dashed; *All N sources* shows the rest. Each card opens the viewer at its passage.

Click **Open in document** in the preview: the viewer opens the handbook at the cited
section with the passage highlighted.

Under the hood: `api/routes/chat.py` streams the events produced by `services/chat.py`;
`services/retrieval.py` and `repositories/search.py` find the passages; `ai/extractive.py`
writes the answer; `ai/citations.py` verifies the `[1]`. In the web app,
`apps/web/src/lib/chat-stream.ts` consumes the stream and
`apps/web/src/components/chat/citation-chip.tsx` renders the chip.

### More questions to try

| Question | What it shows |
| --- | --- |
| What is the parental leave policy? then *How long does it last?* | A follow-up: the second question is rewritten with the subject of the first (`ai/prompts.py`) |
| What was revenue in Q3 2026? | A table on a slide of the board deck: "Q3 2026 revenue: $18.4M" |
| Which warehouse pilot had the best pick rate? | A comparison across CSV rows: "Rotterdam has the highest picks per hour: 455" |
| How much notice is needed to terminate the Globex agreement? | Targeting the named document (the services agreement PDF): 90 days' written notice |
| Who do I page for a SEV1 incident? | A row of a Markdown table in the runbook |
| What payload must Atlas v2 carry? | A requirements table in a Word document: 35 kg |
| What does the warranty cover? | A whole FAQ section returned as a list, from the HTML help page |
| What is the capital of France? | An honest "I could not find a clear answer", with the closest passage |

Now ask the first question again, then a paraphrase:

> How many annual leave days do employees get?

The first repeat is marked **Cached answer** and the paraphrase **Similar question,
cached**: the exact cache in Valkey, then the semantic cache in Postgres
(`services/answer_cache.py`). Neither sent any passage to the answerer.

## 2. Search, insights and settings

**Search** finds passages without writing an answer. Try `parental leave`: results are ranked
by meaning and keywords together, matches are highlighted, and each result opens the viewer
at its passage (`services/search.py`).

**Insights** shows the last 14 days (switch to 7, 30 or 90): questions answered, tokens
saved against the paste-everything baseline, the cache hit rate, latency percentiles,
questions per day and the most cited documents (`services/insights.py`). The demo spread its
questions over two weeks so the charts have a shape.

**Settings** (owners see every tab):

| Tab | What to try |
| --- | --- |
| General | Rename the workspace or change its description |
| Answering | Passages per answer, the context budget, passage size, the answer cache, and whether answers come from the configured model or always from the offline answerer |
| Members | Add someone by email; a new account gets a temporary password shown once |
| API keys | The demo created *Demo integration* (viewer). Create a key: the full key is shown once |
| Activity | The audit trail: uploads, renames, members, keys, settings |

## 3. Leo uploads a document (editor)

Sign out (account menu) and sign in as `leo.chen@northwind.example`.

On **Documents**, drop a file on the upload area (or **browse**). It appears as `Queued`, then
`Indexing`, then `Ready`; the library refreshes on its own while anything is still in
progress. Behind it: the API stored the original in the emulated S3 bucket and sent a message
to the SQS queue; the worker (`worker.py`, `services/ingestion.py`) parsed, chunked and
embedded it. Follow it with `make logs SERVICE=worker`.

Upload the same file again: it is listed as a duplicate, not stored twice. Upload a renamed
image or an unsupported file: it is refused with the reason.

Open a document to see its sections (pages, slides, sheets) and press **Ask about this**: a
new conversation limited to that one document, so every answer cites only it.

The actions menu of each document offers **Download original**, **Rename**, **Reprocess**
and **Delete**. Deleting a ready document removes it from search immediately and retires the
workspace's cached answers.

Leo also owns the second workspace, **Atlas engineering**; switch to it from the workspace
switcher. Its three documents are separate: questions there never see Northwind's files.

## 4. Maya reads and asks (viewer)

Sign in as `maya.patel@northwind.example`. Maya can ask, search, read and download, but the
upload area is gone, the document menus offer only **Download original**, and Settings shows
no API keys or Activity tabs. The API enforces the same rules: a viewer's upload request is
refused with `403`, whatever the client.

## 5. Your own application (API key)

`make demo` printed a viewer key for Northwind Robotics. Ask over HTTP:

```bash
KEY=dmk_...   # from the make demo output
curl -s http://localhost:8110/api/v1/workspaces/northwind-robotics/ask \
  -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"question": "What is the parental leave policy?"}'
```

The response is the answer message with `content`, `citations` (document, location, offsets,
quote), `sources` and `usage`. Stream it instead:

```bash
curl -N http://localhost:8110/api/v1/workspaces/northwind-robotics/ask/stream \
  -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"question": "Who do I page for a SEV1 incident?"}'
```

You receive `event: sources`, then `event: delta` lines with the text, then `event: done`
with the full message. Search works the same way (`POST .../search` with
`{"query": "..."}`). The interactive reference is at <http://localhost:8110/docs>, and
[docs/api](../api/README.md) explains the OpenAPI document.

## 6. Answer with a model (optional)

Set `DOCMIND_LLM_PROVIDER` and `DOCMIND_LLM_MODEL` in `deploy/compose/.env` (Ollama on your
machine works) and run `make up` again. Ask the same questions: answers are now written by
the model, still cited and verified, and cached under the model's own key, so the extractive
answers you cached earlier are not reused for it. An owner can keep a workspace on the
offline answerer in Settings, Answering.
