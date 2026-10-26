# API Specification

Version 0.2 | All routes are FastAPI route handlers under the `/api` prefix in `apps/api`. Request and response models are Pydantic models in `core/schemas.py`; the wire format is camelCase. All responses are JSON unless marked as a stream. Every route except `GET /api/health` requires authentication (section 6). The earlier endpoint set, event format and runner behavior are preserved; additions are marked "(new in 0.2)".

## 1. Conventions

- Authentication: `Authorization: Bearer <token>` (see `02-DESIGN-DOC.md` section 13.1). Missing or invalid token returns `401`.
- Request validation with Pydantic; invalid input returns `400` (`BAD_REQUEST`). FastAPI's default 422 validation body is replaced by the error envelope.
- Ownership: a project, source, job or brief that does not exist or belongs to another user returns `404 NOT_FOUND`.
- Every response carries `X-Request-Id`. Stream responses also carry `X-Job-Id`.
- Error body for non-stream responses:

```json
{ "error": { "code": "NO_TEXT", "message": "No readable text found. If this is a scanned PDF, paste the text instead.", "requestId": "req_01...", "retryable": false, "retryAfterSeconds": null } }
```

- Error codes and HTTP status:

| Code | HTTP | Meaning | Retryable |
|---|---|---|---|
| `BAD_REQUEST` | 400 | Invalid input | no |
| `UNAUTHENTICATED` (new) | 401 | Missing, invalid or expired token | after sign-in |
| `NOT_FOUND` | 404 | Missing or not yours | no |
| `PAYLOAD_TOO_LARGE` (new) | 413 | Upload over `MAX_UPLOAD_MB` | no |
| `UNSUPPORTED_MEDIA_TYPE` (new) | 415 | Not a PDF (type or magic bytes), or an encrypted PDF | no |
| `LIMIT_REACHED` | 409 | A cap such as `MAX_SOURCES_PER_PROJECT` or `MAX_PDF_PAGES` | no |
| `IDEMPOTENCY_CONFLICT` (new) | 409 | Same `Idempotency-Key` with different input | no |
| `JOB_ACTIVE` (new) | 409 | Action blocked because a stage is running for the target | yes, when the job ends |
| `NO_TEXT` | 422 | No readable text | no |
| `FETCH_BLOCKED` | 422 | URL not allowed | no |
| `FETCH_FAILED` | 422 | URL fetch or extraction failed | maybe |
| `RATE_LIMITED` (new) | 429 | Per-user or per-IP request limit | yes, after `Retry-After` |
| `QUOTA_EXCEEDED` (new) | 429 | Per-user daily budget or kill switch | after reset |
| `LLM_QUOTA` | 503 | Provider rate or quota limit after bounded backoff | yes |
| `LLM_INVALID` | 502 | Model output invalid after retries | yes |
| `TIMEOUT` (new) | 504 | Stage exceeded its time limit | yes |
| `INTERRUPTED` (new) | 503 | Job lost to an API restart (seen on job status and stream) | yes |
| `OVERLOADED` (new) | 503 | Active-job cap reached | yes, after `Retry-After` |
| `DB_ERROR` | 503 | PostgreSQL unavailable | yes |
| `VECTOR_DB_ERROR` (new) | 503 | Qdrant unavailable | yes |
| `INTERNAL` | 500 | Unexpected error; quote `requestId` | maybe |

- Streaming routes return `Content-Type: application/x-ndjson`. Each line is one event (section 3). The stream always ends with a `stage_end` event. If an error happens after streaming has started, an `error` event is sent before `stage_end` instead of changing the HTTP status. Errors detected before streaming starts (auth, validation, ownership, caps, rate limits) use normal HTTP status and the JSON envelope.
- POST stage routes accept an optional `Idempotency-Key` header (1-100 visible ASCII characters). See section 6.

## 2. Endpoints

### `GET /api/health`
No authentication. Returns `{ ok: true, configured: { gemini: true, postgres: true, qdrant: true } }` (booleans only; `configured` reports that settings exist, not that services respond). With `?db=1` it also makes cheap calls to PostgreSQL and Qdrant (for example `SELECT 1` and reading the collection info) and returns `{ ok, db: { postgres: "up"|"down", qdrant: "up"|"down" } }` with status 503 if either is down; this is the readiness and keep-alive target. Rate limited per IP. Never returns secret values.

### `GET /api/me` (new in 0.2)
Returns `{ "user": { "id": "...", "usage": { "windowStart": "...", "llmCalls": 0, "embeddedTexts": 0, "limits": { "llmCalls": null, "embeddedTexts": null } } } }`. Limits are `null` when not configured. Used by the UI to show the "limit reached" state (F17).

### `GET /api/projects` (new in 0.2; fills a gap, since F1 requires listing)
Response `200`: `{ "projects": [ { "id": "prj_...", "name": "...", "description": "...", "sourceCount": 3, "updatedAt": "..." } ] }` for the current user, newest first. Projects with status `deleting` are omitted.

### `POST /api/projects`
Body: `{ "name": string (1-80), "description"?: string }`
Response `201`: `{ "projectId": "prj_xxxxxxxx" }`

### `GET /api/projects/:projectId`
Response `200`:

```json
{
  "project": { "id": "prj_...", "name": "...", "description": "..." },
  "sources": [
    { "id": "src_...", "tag": "S1", "kind": "pdf", "title": "...", "origin": "paper.pdf",
      "chunkCount": 24, "claimCount": 7,
      "stages": { "collected": true, "analyzed": true, "critiqued": true },
      "lastError": null }
  ],
  "conflicts": [
    { "id": "vrd_...", "label": "contradicts", "confidence": 0.82, "rationale": "...",
      "a": { "claimId": "clm_...", "sourceTag": "S1", "text": "..." },
      "b": { "claimId": "clm_...", "sourceTag": "S3", "text": "..." } }
  ],
  "briefs": [ { "id": "brf_...", "question": "...", "createdAt": "..." } ],
  "activeJobs": [ { "jobId": "...", "stage": "analyze", "sourceId": "src_...", "status": "running", "lastSeq": 12 } ]
}
```

`lastError` and `activeJobs` are new in 0.2 (F15).

### `DELETE /api/projects/:projectId`
Marks the project `deleting`, deletes its Qdrant points, then its PostgreSQL rows. Response `200`: `{ "deleted": 123 }` (number of deleted records across both stores). If the vector deletion fails, the response is `503 VECTOR_DB_ERROR` and the project remains hidden and is completed by retry or by reconcile; a repeated `DELETE` is safe.

### `POST /api/projects/:projectId/sources` (stream)
Stage: `collect`. Accepts one of:
- `multipart/form-data` with field `file` (PDF), optional `title`
- `application/json`: `{ "url": "https://..." }`
- `application/json`: `{ "title": "...", "text": "..." }`

Streams events; the `result` event data:

```json
{ "sourceId": "src_...", "tag": "S2", "title": "...", "kind": "pdf", "chunkCount": 31, "charCount": 41234, "alreadyExisted": false }
```

Errors: `LIMIT_REACHED`, `NO_TEXT`, `FETCH_BLOCKED`, `FETCH_FAILED`, `BAD_REQUEST`, `PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`.

### `POST /api/projects/:projectId/sources/:sourceId/analyze` (stream)
Stage: `analyze`. No body. Requires `stages.collected`. `result` data: `{ "claimCount": 7, "topics": ["..."] }`. Side effect: existing claims of the source and all verdicts that reference them are removed, and `stages.critiqued` becomes false.

### `POST /api/projects/:projectId/sources/:sourceId/critique` (stream)
Stage: `critique`. No body. Requires `stages.analyzed`. `result` data:

```json
{ "pairsJudged": 12, "supports": 4, "contradicts": 2, "nuances": 3, "unrelated": 3, "skippedExisting": 0 }
```

### `GET /api/projects/:projectId/sources/:sourceId`
Returns `{ source, summary, claims: [...], verdicts: [...] }` for the source detail view.

### `DELETE /api/projects/:projectId/sources/:sourceId` (new in 0.2; F16)
Deletes the source with its text, claims and verdicts (and its Qdrant points). If a job for the source is running, the response is `409 JOB_ACTIVE` with message "A stage is still running for this source." Response `200`: `{ "deleted": true }`. The source's tag is not reused.

### `POST /api/projects/:projectId/ask` (stream)
Body: `{ "question": string (5-500) }`. `result` data:

```json
{
  "briefId": "brf_...",
  "title": "...",
  "answerMarkdown": "... [S1] ... [S2]",
  "disagreements": [ { "topic": "...", "positions": [ { "tag": "S1", "position": "..." }, { "tag": "S3", "position": "..." } ], "note": "..." } ],
  "gaps": "...",
  "legend": [ { "tag": "S1", "sourceId": "src_...", "title": "..." } ]
}
```

### `GET /api/projects/:projectId/briefs/:briefId`
Returns a stored brief (same shape as the `ask` result).

### `GET /api/jobs/:jobId` (new in 0.2)
Returns `{ "jobId": "...", "projectId": "prj_...", "sourceId": "src_..." | null, "stage": "analyze", "status": "queued"|"running"|"succeeded"|"failed", "errorCode": null, "result": { } | null, "lastSeq": 12, "startedAt": "...", "finishedAt": "..." | null }`. Only the job's owner can read it.

### `GET /api/jobs/:jobId/events?after=<seq>` (stream, new in 0.2)
Streams the job's persisted events with `seq` greater than `after` (default 0), then continues live until the job ends with `stage_end`. Used to re-attach after a reload or a dropped connection. For a finished job it replays and ends.

## 3. Stream event format

One JSON object per line:

```json
{ "jobId": "9f2c...", "seq": 3, "ts": "2026-10-25T10:00:00.000Z", "stage": "analyze", "agent": "analyst", "type": "step", "message": "Reading 24 chunks", "data": { } }
```

| Field | Values |
|---|---|
| `jobId` (new) | UUID of the job |
| `seq` (new) | integer, strictly increasing per job starting at 1; `heartbeat` events do not consume a `seq` and carry `seq` of the last real event |
| `stage` | `collect`, `analyze`, `critique`, `ask` |
| `agent` | `collector`, `analyst`, `critic`, `writer`, `system` |
| `type` | `stage_start`, `step`, `doc_read`, `doc_write`, `llm_call`, `warning`, `error`, `result`, `stage_end`, `heartbeat` (new) |
| `message` | short human-readable sentence for the trace panel (user-safe: no stack traces, secrets or source text) |
| `data` | optional object, for example `{ "count": 24, "docType": "chunk" }` or `{ "tier": "fast", "ms": 4200 }`. For `error`: `{ "code": "LLM_QUOTA", "retryable": true, "retryAfterSeconds": 30 }`. For `stage_end`: `{ "status": "succeeded" | "failed" }` |

Unknown event types and unknown `data` fields must be ignored by clients (forward compatibility). `docType` values: `source`, `chunk`, `claim`, `verdict`, `brief`.

Example sequence for `critique`:

```
stage_start  critic   "Comparing claims from S3 with other sources"
doc_read     critic   "Searching similar claims" {count: 7}
step         critic   "Found 12 candidate pairs (4 already judged)"
llm_call     critic   "Judging 8 pairs" {tier:"fast"}
doc_write    critic   "Saved 8 verdicts" {docType:"verdict", count:8}
result       critic   "Done" { ...result data... }
stage_end    system   "critique finished" {status:"succeeded"}
```

## 4. Browser pipeline runner contract

`runPipeline(projectId, input)` calls the stages in order and updates UI state:

```
collect -> analyze -> critique
```

- Reads the NDJSON stream line by line (`fetch` + `ReadableStream`), buffers partial lines, validates each event with Zod, ignores unknown event types, drops `heartbeat` from the trace, and appends events to the trace store.
- Sends the `Authorization` header on every call. On `401` it refreshes or re-establishes the session once, then retries the call (the server single-flight and idempotency rules make this safe); if that fails it shows the signed-out state.
- On an `error` event or non-OK response: stop, mark the stage chip as failed, show the message and a Retry button for that stage. If the error has `retryAfterSeconds`, show it.
- On `result` of `collect`, remember `sourceId` for the following stages.
- **Reconnect (new):** if the stream ends without `stage_end` (network drop), call `GET /api/jobs/:jobId/events?after=<lastSeq>`, up to 3 attempts with backoff, before showing an error. On page load, if `GET /api/projects/:id` lists `activeJobs`, re-attach the same way. A reload during `collect`, `analyze` or `critique` therefore continues the chain from the stage that is running or next.
- Retry sends a new request; because single-flight and idempotent writes apply, a retry never creates duplicates. The runner generates one `Idempotency-Key` per user action and reuses it for automatic reconnect-triggered resubmits.

## 5. Rate limiting and limits

- Per-user in-process token-bucket limit on all POST routes (default example: 30 requests per 10 minutes) and per-IP limit on health and unauthenticated traffic, to protect the LLM quota. In-process means per API instance (`02-DESIGN-DOC.md` section 14). Rejections return `429 RATE_LIMITED` with `Retry-After`.
- Active-job caps (`MAX_ACTIVE_JOBS`, `MAX_ACTIVE_JOBS_PER_USER`): excess returns `429` (per user) or `503 OVERLOADED` (global) with `Retry-After`.
- Per-user daily usage budgets return `429 QUOTA_EXCEEDED` before any provider call.
- `MAX_SOURCES_PER_PROJECT`, `MAX_UPLOAD_MB`, `MAX_PDF_PAGES`, `MAX_PASTE_CHARS`, question length and URL rules are enforced server-side.
- URL fetch: `http`/`https` only; blocked hosts and private ranges; DNS resolved once and the connection pinned to the validated IP; max redirects 3 (each hop re-validated); max response size 5 MB; timeout 10 s.

## 6. Authentication, idempotency, jobs and recovery (new in 0.2)

### Authentication
- Token verification, user mapping and ownership are described in `02-DESIGN-DOC.md` section 13.1. The identity provider is open (U1).
- CORS: exact allowed origins from `CORS_ALLOWED_ORIGINS`; allowed headers include `Authorization`, `Content-Type`, `Idempotency-Key`; exposed headers include `X-Request-Id`, `X-Job-Id`, `Retry-After`.

### Idempotency and single-flight
- A POST stage request creates a job unless an active job with the same (project, stage, source, input hash) exists; in that case the request attaches to the existing job's event stream (same `jobId`), and the response is not an error.
- With `Idempotency-Key`: the first request creates the job and remembers the key per user; a repeat with the same key and the same input returns the same job (stream replay or, if finished, replay and `stage_end`); the same key with different input returns `409 IDEMPOTENCY_CONFLICT`.
- Input hash: for uploads, the content hash of the file bytes; for URLs, the normalized URL; for text, the content hash; for stages, none beyond project, stage and source; for `ask`, the normalized question.

### Job states
`queued` -> `running` -> `succeeded` | `failed`. In v1 the in-process runner moves a job from `queued` to `running` immediately. A running job holds a lease (`JOB_LEASE_S`) renewed every `JOB_HEARTBEAT_S`.

Source stage state (visible in `stages` and `lastError`): `collected`, `analyzed`, `critiqued` booleans plus `lastError`. These are the user-facing processing states; job status is operational detail.

### Recovery behavior

| Situation | Behavior |
|---|---|
| Client disconnects mid-stream | The job continues; the client re-attaches with the events endpoint |
| API restarts or deploys mid-job | On startup a sweep marks running jobs with expired leases `failed` with `INTERRUPTED` and writes an `error` plus `stage_end` event; the UI shows "Retry stage" |
| Graceful shutdown (SIGTERM) | Stop accepting new jobs, wait up to `SHUTDOWN_GRACE_S`, then mark remaining jobs `INTERRUPTED` |
| Provider rate limit | Bounded backoff inside the stage, then `error` `LLM_QUOTA` with `retryAfterSeconds` when known |
| Qdrant or PostgreSQL down | Stage fails with `VECTOR_DB_ERROR` or `DB_ERROR`; flags are only set after durable writes, so retry resumes safely |
| Duplicate submit or double click | Attaches to the active job (single-flight) |
| Stage exceeds `STAGE_TIMEOUT_S` | Job `failed` with `TIMEOUT`, retryable |
| Source stuck with `stages.collected = false` | UI shows "Retry collect" (re-send the same input) or "Delete source" (F16) |
| Retry of a failed stage | Allowed whenever no active job exists for it; idempotent writes apply |

## 7. Contracts and versioning (new in 0.2)

- All paths are under `/api` and unversioned while the product is pre-release. A breaking change must update this document, the fixtures in `contracts/`, the Pydantic models and the Zod schemas in the same change.
- `contracts/` holds one JSON example per response, request body, error and event type. Pytest validates every fixture against the Pydantic models; Vitest validates every fixture against the Zod schemas.
- FastAPI generates an OpenAPI document; CI exports it to `apps/api/openapi.json` as a reference and fails if the committed copy is stale. Code generation from it is not used (decision D11).
