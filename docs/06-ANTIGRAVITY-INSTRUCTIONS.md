# Instructions for Antigravity (coding agent)

Version 0.3 | How to use: put the whole `docs/` folder plus the root `README.md`, `AGENTS.md` and `GEMINI.md` in the repo first. `AGENTS.md` carries the always-on context and rules, so you normally only need to paste **one stage prompt** from Section 3 at a time (Section 1 below is a copy of the core rules in case you want to paste them manually). Do not paste several stages at once.

## 1. Operating rules (paste first, every session)

```
You are helping me build "Research Desk", a multi-agent research assistant (solo portfolio project, free-first).
Stack: Next.js + React + TypeScript + Tailwind (apps/web); Python + FastAPI (apps/api); Gemini API; Qdrant; PostgreSQL;
Pydantic (backend) and Zod (frontend); Pytest and Vitest; uv and npm; Docker Compose.

Before writing code, read these files fully: README.md and docs/01-PRD.md through docs/05-API-SPEC.md.
They are the source of truth. If code and docs disagree, tell me and propose which to change.

Rules:
1. Work on ONE stage at a time. Do only what the current stage asks. No extra features, dependencies, services or folders.
2. Do not guess library APIs (the Qdrant Python client, the Gemini SDK, SQLAlchemy, Alembic, FastAPI, PDF and article libraries).
   Open the official docs and follow them. If you cannot confirm something, write a clear TODO behind
   the adapter and tell me.
3. Module boundaries: Qdrant client only in stores/vector.py; Gemini SDK only in providers/gemini.py; SQL only in
   stores/db.py and stores/repos/. Agents use the Protocols. Build Qdrant filters and SQL only from validated IDs and enums.
   Every Qdrant search must filter on type and projectId.
4. Never put secrets in code, logs, images, or commits. Read config only from core/config.py.
   Keep .env files out of git. Only .env.example files are committed.
5. Every LLM response must be validated with Pydantic (core/schemas.py). Every outbound call has a timeout.
6. Use deterministic project-scoped IDs from core/ids.py so every write is an idempotent upsert, and follow the write
   order and retrieval post-filter in docs/03 section 13.
7. Every route except GET /api/health needs authentication; project routes use get_owned_project; other users' data is 404.
8. Do not block the event loop: CPU-bound work goes to a thread or subprocess with a timeout.
9. After each stage run all checks for the area you changed:
   backend (apps/api): uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ; uv run pytest
   frontend (apps/web): npm run typecheck ; npm run lint ; npm test
   Fix failures before finishing.
10. Keep code small and readable: short functions, clear names, comments only where intent is not obvious.
11. Show user-safe error messages in the UI and API. Never show stack traces. Never log source text, prompts, model output, or secrets.
12. Do not claim anything is implemented, fast or verified unless you ran it.
13. When finished, give me: (a) what you built, (b) files changed, (c) how I verify it manually,
    (d) anything uncertain or assumed, (e) a suggested git commit message. Then stop.
```

## 2. Definition of done for every stage

- Lint, type check and tests pass for every area touched (backend and/or frontend).
- The stage's manual check (listed in each prompt) works.
- The docs and the `contracts/` fixtures are updated if the implementation changed a contract (schema, API, config).
- A git commit exists with a clear message. Commit after every stage.

## 3. Stage prompts

### Stage 0: Scaffold, tooling and config

Goal: a repository where both apps start, every check command works, CI runs, and the cross-cutting foundations (config, logging, error envelope, contract fixtures, module boundary rule) exist before any feature. Stage 0 touches no database, Qdrant or Gemini code; those arrive in Stage 1.

```
STAGE 0: Scaffold, tooling and config.
Read README.md, docs/02-DESIGN-DOC.md sections 4, 7, 9, 11, 12, 13.10 and docs/05-API-SPEC.md section 1.

1) Repository root. Create .gitignore (Node, Next.js, Python, .venv, __pycache__, .env* except .env.example files,
   a development LLM cache folder, editor files). Create the root .env.example (empty values: POSTGRES_USER,
   POSTGRES_PASSWORD, POSTGRES_DB). Create docker-compose.yml with services postgres and qdrant (official images, named
   volumes, healthchecks, ports bound to 127.0.0.1, credentials from .env). Do NOT add api/web services yet unless trivial;
   if added, put them behind a compose profile named "full". Confirm image names and healthcheck commands in the official docs.

2) apps/api. Initialize with uv (pyproject.toml, uv.lock). Python version: confirm with me; assume 3.12+.
   Dependencies for THIS stage only: fastapi, uvicorn, pydantic, pydantic-settings, and dev tools pytest, pytest-asyncio
   (or the anyio pytest plugin), httpx (test client), ruff, mypy. Do not add database, Qdrant, Gemini, PDF or SQLAlchemy
   packages yet (Stage 1 and 2 add them).
   Create the package src/research_desk with the folders from README.md "Project structure" (empty modules with a short
   docstring are fine): api, core, agents, orchestrator, ingest, providers, stores/repos.
   - core/config.py: pydantic-settings Settings with all constants from docs/02 section 7 and the env names from README.md;
     fail fast with a readable message listing missing variables; redact secrets in repr; refuse to start when
     AUTH_MODE=dev and APP_ENV is not local.
   - core/schemas.py: CamelModel base (camelCase aliases, populate_by_name).
   - core/errors.py: error types, the single user-message map, and the error envelope from docs/05 section 1
     (code, message, requestId, retryable, retryAfterSeconds). Register exception handlers so validation errors and
     unexpected errors use the envelope with no stack traces.
   - core/logging.py: structured JSON logging with request_id, a redaction filter for secrets, and a rule that source text,
     prompts and model output are never logged.
   - api middleware: request ID (accept or generate, return X-Request-Id), CORS from CORS_ALLOWED_ORIGINS.
   - GET /api/health returning { ok, configured: { gemini, postgres, qdrant } } as booleans only (no secret values).
     The ?db=1 option returns 501 for now; it is implemented in Stage 1.
   - Module boundary rule: configure Ruff banned-api (or import-linter; tell me which) so that qdrant_client may be imported
     only in stores/vector.py, the Gemini SDK only in providers/gemini.py, and SQLAlchemy only in stores/. Add a test or
     lint config proving it is active (it can reference modules that do not exist yet).

3) apps/web. Create with create-next-app: App Router, TypeScript strict, Tailwind, ESLint. Add zod and vitest (confirm
   package names and current setup in their docs). src/lib/config.ts parses env with Zod: NEXT_PUBLIC_API_BASE_URL only
   (public, no secrets). A home page that calls GET /api/health on the API and shows "API reachable" or an error state.
   npm scripts: dev, build, typecheck, lint, test.

4) contracts/. Create contracts/README.md (what the folder is for, naming rule) and the first fixture health.json
   (a valid health response) and error.json (a valid error envelope). Add one Pytest test that validates each fixture against
   the Pydantic models, and one Vitest test that validates the same files against Zod schemas in apps/web/src/lib/api/schemas.ts.

5) .env.example files: apps/api/.env.example and apps/web/.env.example exactly as README.md lists them (empty values).

6) CI: .github/workflows/ci.yml with two jobs. api: install uv, uv sync, ruff check, ruff format --check, mypy, pytest.
   web: setup Node 20, npm ci, typecheck, lint, test. No service containers yet (Stage 1 adds them). Pin action versions;
   confirm current versions in their docs.

7) Update AGENTS.md status (tick stage 0) and README.md only if a command differs from what is written.

Manual check: docker compose up -d postgres qdrant shows both healthy; from apps/api: uv run uvicorn research_desk.main:app
--port 8000 and curl http://localhost:8000/api/health returns booleans with no secrets; a bad config (missing required variable)
prints a readable list and exits; from apps/web: npm run dev shows the home page reaching the API; all check commands in
operating rule 9 pass; the CI workflow file passes a local lint of its syntax (or run it on a branch).
```

### Stage 1: Databases, jobs, providers and adapters

```
STAGE 1: PostgreSQL, Qdrant, Gemini providers, jobs and auth skeleton.
Read docs/03-DATABASE-SCHEMA.md fully (especially sections 8, 12, 13) and docs/02-DESIGN-DOC.md sections 5, 13.1, 13.7-13.9.
Add dependencies now (say why for each; confirm package names in the official docs): SQLAlchemy 2 (async) with a PostgreSQL
driver, Alembic, qdrant-client, the official Google Gen AI SDK for Python, a UUID v5 helper if the standard library is not enough.

1) Alembic: create the first migration from docs/03 section 12 (users, projects, sources, source_texts, claims, verdicts,
   briefs, jobs with the partial unique index, job_events, usage_ledger, app_meta). Models and migration must agree.
2) scripts/migrate_qdrant.py: create the collection (size EMBEDDING_DIM, cosine), payload indexes (type, projectId, sourceId;
   tenant-style option for projectId if supported), and the alias, idempotently. Store embedding model, dimension, collection
   and schema version in app_meta; make startup fail when configuration disagrees.
3) Spikes: write scripts/spike_db.py, spike_llm.py and spike_stream.py that prove S1-S10 from docs/03 section 8 against my real
   local Compose services and Gemini key, and print a results table. Use the official docs; do not guess method names.
   Append the answers to the bottom of docs/03. If a spike disproves a design assumption, STOP and ask before changing docs or code.
4) Based on the results implement: core/ids.py (keys, short hashes, project-scoped UUIDv5 point IDs, pair keys, normalized
   question) with unit tests; stores/vector.py (VectorStore per docs/02 section 5); stores/db.py and stores/repos/* (repository
   protocols and PostgreSQL implementations; short transactions; tag allocation under a project row lock);
   providers/embeddings.py + providers/gemini.py (batching, bounded retries with jittered backoff, timeouts, dimension check,
   usage ledger rows, global concurrency semaphore and minimum interval); providers/llm.py (structured output, Pydantic
   validation, retry with the validation error appended, 429 backoff, typed ProviderError with user-safe message and retryable flag).
5) orchestrator: jobs.py (create job, single-flight via the partial unique index, Idempotency-Key handling, lease and heartbeat,
   startup recovery sweep marking expired running jobs INTERRUPTED), events.py (EventSink persisting to job_events with local
   fan-out), runner.py (JobRunner protocol + InProcessRunner: detached asyncio task, active-job caps, stage timeout, graceful shutdown).
   Add a trivial fake stage to prove the runner, streaming tail and recovery; remove or keep it only as a test fixture.
6) Auth skeleton: api dependency get_current_user (AUTH_MODE=dev fixed local user when APP_ENV=local; jwt mode verifies a bearer
   token against AUTH_JWKS_URL, AUTH_ISSUER, AUTH_AUDIENCE with the provider-independent interface; the provider itself is undecided, U1),
   users upsert, and get_owned_project returning 404 for missing or foreign projects.
7) GET /api/health?db=1 now checks PostgreSQL and Qdrant. CI gets service containers (or compose) for PostgreSQL and Qdrant and runs
   migrations on an empty database, plus a check that models and migrations agree.
8) Tests (Pytest): ids; embedding batching and dimension check (fake client); LLM retry logic (fake client); repositories against a
   throwaway database; VectorStore against a throwaway collection (idempotent upsert, filtered query never returns other projects,
   delete by project); job single-flight and recovery; concurrent tag allocation; cross-user 404.
Manual check: migrations apply to an empty database; migrate_qdrant creates the collection; spike scripts print sensible results and
the docs/03 results block is filled; /api/health?db=1 reports both services up and reports down when you stop one; the fake stage
streams events, survives a client disconnect, and is marked INTERRUPTED after killing and restarting the API mid-run.
```

### Stage 2: Collector (PDF first, then text and URL)

```
STAGE 2: Collector.
Implement the Collector per docs/04-AGENT-SPECS.md section 1 and the collect endpoint per docs/05-API-SPEC.md.
Order: (a) PDF text extraction with page numbers, (b) pasted text, (c) URL with the SSRF guard.
Use the PDF library chosen in spike S8 and a maintained article extraction library (confirm names and licences; tell me before adding).
Implement ingest/{pdf,text,url,ssrf,clean,chunk}.py, agents/collector.py, and the 'collect' branch of orchestrator/pipeline.py.
Create POST /api/projects, GET /api/projects, GET /api/projects/:id, DELETE /api/projects/:id (tombstone, Qdrant delete, PostgreSQL delete),
DELETE /api/projects/:id/sources/:sid, and POST /api/projects/:id/sources as an NDJSON stream using the job runner
(heartbeats, X-Job-Id), plus GET /api/jobs/:id and GET /api/jobs/:id/events.
Upload handling: enforce MAX_UPLOAD_MB while reading the body (not after), check %PDF magic bytes, spool to a temp file, delete it when the job ends,
reject encrypted PDFs and PDFs over MAX_PDF_PAGES, run extraction off the event loop with PDF_PARSE_TIMEOUT_S.
SSRF guard: resolve once, reject loopback/private/link-local/multicast/reserved/metadata addresses (IPv4, IPv6, IPv4-mapped), connect to the
validated IP through a custom transport, re-validate every redirect, enforce URL_* limits.
Add contract fixtures for every new request, response and event shape.
Unit tests: chunker (sizes, overlap, page ranges), cleaner (hyphen joins, header/footer removal, references cut), SSRF guard (all cases in
docs/02 section 13.4, using a fake resolver for rebinding), upload limit enforcement, PDF page and time limits, collect idempotency and tag allocation.
Manual check (curl or a minimal test page): upload a real 8-10 page PDF, see events stream, and confirm the source row, source_text row and chunk
points exist (768-dimension vectors) via a script. A scanned/empty PDF returns NO_TEXT. http://localhost and a redirect to a private address are blocked.
Close the connection mid-stream and confirm the job still finishes.
```

### Stage 3: UI shell and pipeline runner

```
STAGE 3: UI shell.
Build sign-in (against the provider chosen for U1; if undecided, implement dev-mode sign-in only and say so), the Home page (project list with create
form, using GET /api/projects) and the Project page with tabs Sources / Insights / Ask and a Trace drawer, following docs/02-DESIGN-DOC.md section 10.
For now only the Sources tab is functional: PDF drop zone, Add URL, Paste text, source cards with stage chips and delete.
Implement the browser pipeline runner from docs/05-API-SPEC.md section 4: NDJSON reader (partial lines, Zod validation, unknown events ignored,
heartbeats hidden), trace store, retry on failure, reconnect via GET /api/jobs/:id/events?after=seq, re-attach from activeJobs on page load,
Idempotency-Key per user action, 401 handling. Stages analyze and critique can be stubbed until their stages are built.
All API calls go to the FastAPI base URL; the frontend never calls Gemini, PostgreSQL or Qdrant.
Design: clean and spacious, light/dark support, agent colors Collector gray / Analyst blue / Critic amber / Writer green.
Include empty, loading, failed, retry, reconnecting, signed-out and service-unavailable states.
Vitest: NDJSON reader (chunk boundaries, partial lines, unknown event), runner state machine (success, error, reconnect, 401), error-message mapping,
fixture validation with Zod.
Manual check: sign in, create a project, add a PDF, see events appear live in the trace, see the source card; reload mid-stage and see the trace
and result reappear; open the project as a second user and get "not found".
```

### Stage 4: Analyst

```
STAGE 4: Analyst.
Implement agents/analyst.py, prompts and Pydantic schemas exactly per docs/04-AGENT-SPECS.md section 2, the analyze branch of orchestrator/pipeline.py,
and POST /api/projects/:id/sources/:sid/analyze (NDJSON via the job runner). Follow the write order in docs/03 section 13 (PostgreSQL replace with flags false,
Qdrant upsert and prune, flag true). Add GET /api/projects/:id/sources/:sid.
Update the UI: runner calls analyze after collect; the Insights tab shows the summary and claims per source; update source stage chips and claim counts.
Unit tests (fake providers): schema validation (valid, invalid, too many claims), text-truncation helper (first 50k + last 30k), re-analysis replaces claims
and cascades verdict deletion and clears stageCritiqued, crash-after-PostgreSQL-write recovery.
Manual check: after adding a PDF you see a 3-5 sentence summary and up to 8 self-contained claims. Check that claim rows exist in PostgreSQL, claim points exist
in Qdrant with embeddings and matching keys, and the source row has the summary and topics, as in the schema doc.
```

### Stage 5: Critic

```
STAGE 5: Critic. (Highest-risk stage: be careful and test thoroughly.)
Implement agents/critic.py per docs/04-AGENT-SPECS.md section 3: claim vectors from Qdrant, ONE batched query for claims from other sources
(must_not sourceId, score threshold), validation of hits against PostgreSQL, pair deduplication by deterministic verdict key, skipping already-judged
pairs (SQL), ONE batched LLM call (split by CRITIC_MAX_PAIRS_PER_CALL only if needed), a follow-up call only for missing pair IDs, ONE PostgreSQL
transaction to upsert verdicts and set stageCritiqued. Enforce one critique per project at a time (advisory lock or equivalent) and tell me which you used.
Add the critique branch and POST /api/projects/:id/sources/:sid/critique (NDJSON via the job runner).
UI: runner calls critique after analyze; Insights tab gets a Conflicts view with side-by-side claim cards, stance badge (color + icon + text), confidence,
rationale, and a filter (contradicts / nuances / supports).
Unit tests: pair key is order-independent, already-judged pairs are skipped, schema validation, handling of missing pair IDs, hits without PostgreSQL rows
are dropped, concurrent critiques in one project do not double-judge, re-analysis invalidation forces re-critique.
Manual check: add 3 sources on one debated topic one after another; the Conflicts view shows meaningful contradicts/nuances pairs. List any false positives
you notice so we can tune the prompt and CRITIC_MIN_SIMILARITY.
```

### Stage 6: Writer and Ask tab

```
STAGE 6: Writer.
Implement agents/writer.py and agents/citations.py per docs/04-AGENT-SPECS.md section 4: retrieval (Q4, Q5 with post-filtering against PostgreSQL, Q6 as SQL),
context building with source tags S1..Sn and a legend, one LLM call, citation-tag validation (remove/flag unknown tags; retry once if there are no valid citations),
write the brief row. Add POST /api/projects/:id/ask (NDJSON via the job runner) and GET /api/projects/:id/briefs/:briefId.
UI: Ask tab with a question box, example questions, a briefing view where [S#] tags are clickable (show source title and the supporting claim), disagreement
cards, and a "gaps" note. Render Markdown safely (no raw HTML).
Unit tests: citation validator, context builder (tags and legend), schema validation, retrieval post-filter drops hits from missing or incomplete sources.
Manual check: ask 3 questions on the demo corpus; every factual sentence has a valid tag; disagreements appear where the Critic found conflicts; an off-topic
question yields an honest "gaps" answer.
```

### Stage 7: Polish, robustness and production hardening

```
STAGE 7: Polish, robustness and production hardening.
Implement, in this order, and tell me which items you could not finish:
1) Rate limiting: RateLimiter protocol with the in-process token-bucket implementation, per-user on POST routes and per-IP on health; 429 RATE_LIMITED with
   Retry-After; active-job caps (429 per user, 503 OVERLOADED global).
2) Cost controls: per-user daily budgets from usage_ledger (values from spike S6), LLM_ENABLED kill switch, GET /api/me usage, QUOTA_EXCEEDED before any provider call.
3) Error mapping: every error code in docs/05 section 1 has one message in the backend map and the same text in the frontend map; "Retry stage" for failed and interrupted stages.
4) Caps and limits verified end to end (sources per project, upload size, pages, paste size, question length, URL limits).
5) Observability: metrics from docs/02 section 13.10 (names as suggested; backend per U8, OpenTelemetry-compatible), log sampling for step events, a test that logs never contain
   source text, prompts or secrets.
6) scripts/reconcile.py per docs/03 section 13 (complete deleting projects, compare counts, remove orphan points, verify app_meta) with tests.
7) Concurrency and failure tests: duplicate submit attaches to the active job; kill the API mid-job (INTERRUPTED then retry succeeds); Qdrant down mid-stage; PostgreSQL down mid-stage;
   Gemini 429 storm with the fake provider.
8) A small development-only LLM response cache (gitignored folder, keyed by prompt hash), disabled outside APP_ENV=local.
9) Security review: run the REVIEW prompt in section 4 against docs/02 section 13 and fix the high-priority items.
10) UI polish: trace panel (agent colors, counts, durations), empty states, skeleton loaders, keyboard focus, responsive layout, dark mode if not done yet.
Run through all error paths in docs/02-DESIGN-DOC.md section 8 and confirm each shows a helpful message.
Manual check: 5 consecutive full runs on the demo corpus succeed (metric M1 in the PRD); cross-user isolation tests pass (M7).
```

### Stage 8: Deploy, README, demo prep

```
STAGE 8: Ship.
Ask me which hosts to use for the web app, the API, PostgreSQL and Qdrant if I have not said (decision U2). Do not assume any provider limit or free-tier behavior: verify
each in the provider's documentation and tell me what you could not verify.
1) API container: apps/api/Dockerfile (non-root user, no secrets baked in, uv-based install, one uvicorn worker). Release step that runs alembic upgrade head (separately from
   app start) and scripts/migrate_qdrant.py. Web build and deployment config with NEXT_PUBLIC_API_BASE_URL.
2) Verify on the real hosts: env vars, CORS origins, upload size limits, streaming responses with heartbeats and idle timeouts (spike S9 on the real stack), graceful shutdown
   behavior on deploy (INTERRUPTED jobs are retryable), TLS to PostgreSQL.
3) Add the keep-alive job for a pausing free Qdrant cluster if applicable (GET /api/health?db=1; confirm it counts as activity) or document the "search index unavailable" state.
4) Backups: configure PostgreSQL backups with the host's capabilities, run the restore drill (restore into a scratch database, start the API against it, run reconcile), and decide
   the Qdrant policy (snapshots vs rebuild) from measured rebuild time; record the result in docs/02 section 16 (U9).
5) Production readiness checklist in docs/07 section 7: complete every item or mark it as an accepted gap with a reason.
6) Update README.md (screenshot placeholders, accurate setup steps, known limits), remove dead code, run a secret scan over the repo and git history, check .gitignore and dependency
   audits (pip-audit or an equivalent for Python, npm audit for the frontend). Add docs/DEMO-DATA.md listing the demo sources and the questions to ask.
Manual check: fresh clone + README steps works locally; the deployed app completes the full demo flow; the restore drill is documented as done.
```

## 4. Prompts for fixing problems

Use these when something goes wrong.

```
BUG REPORT: <what you did> -> <what happened> -> <what you expected>.
First explain the most likely cause based on the code and docs. Then make the smallest fix.
Add or update a test that would have caught it. Do not refactor unrelated code.
```

```
REVIEW: Review the code from the last stage against docs/0X-*.md. List mismatches, missing error handling,
security issues (secrets, SSRF, unvalidated input, missing ownership checks, logged sensitive data), blocking calls in async code, missing timeouts,
and places where an LLM output is used without Pydantic validation.
Do not change code yet; give me a prioritized list.
```

```
DOC SYNC: Compare the current implementation with docs/02, 03, 04 and 05 and the fixtures in contracts/. Update the docs and fixtures to match what the code
now does, and list every contract that changed.
```

```
BOTTLENECK CHECK: Compare the current behavior with docs/02 section 14. For each register item B1-B17, say whether the stage you just finished affects it,
what you measured (if anything), and whether an early-warning signal is visible. Do not add infrastructure; propose changes only as a prioritized list with the evidence.
```

## 5. Tips for working with the agent

- Keep each stage in a fresh, short session and re-paste the operating rules.
- If the agent invents an SDK method, stop it and point it to the docs section; do not accept "probably works".
- Commit after each stage. If a stage goes wrong, revert instead of piling fixes on top.
- Never paste real API keys into chat prompts; keep them in untracked `.env` files.
- If the agent proposes a queue, worker, cache or new service, ask for the measurement that justifies it (`docs/02` section 14.1).
- If you fall behind, follow the cut order in `07-BUILD-PLAN-AND-CHECKLIST.md`.
