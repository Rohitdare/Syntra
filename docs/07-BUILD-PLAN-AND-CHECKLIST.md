# Build Plan, Testing, Demo and Release Checklist

Version 0.3 | No external deadline. The plan is written in "Day N" units (about 5-6 hours each) so you can map it to your calendar. Thirteen days is the estimate for the Python architecture (it was ten before PostgreSQL, authentication, jobs and hardening were added); it is not a measured figure, so re-baseline after Stage 1 and compress only if the early days go smoothly.

## 1. Day-by-day plan

### Day 1: Stage 0 (scaffold, tooling, config)
- [ ] Install prerequisites: Node 20+, Python (confirm version), uv, Docker with Compose
- [ ] Create the Gemini API key in AI Studio; note real rate limits for the fast LLM, strong LLM and embedding models; copy exact model IDs
- [ ] Create the GitHub repo (public), add `AGENTS.md`, `GEMINI.md`, `README.md`, `docs/`, `.gitignore`
- [ ] Stage 0: monorepo, `docker-compose.yml` (postgres, qdrant), `apps/api` and `apps/web` skeletons, config, logging, error envelope, `contracts/`, boundary lint rule, CI
- [ ] Verify the Stage 0 checklist in section 7a; commit and push

### Day 2: Stage 1, part A (databases and spikes)
- [ ] Alembic first migration; `scripts/migrate_qdrant.py`
- [ ] Spikes S1-S10 (`spike_db.py`, `spike_llm.py`, `spike_stream.py`); fill in results in `03-DATABASE-SCHEMA.md`
- [ ] Decide the PDF library (S8); note licence in the README stack line

### Day 3: Stage 1, part B (adapters, jobs, auth skeleton)
- [ ] `ids.py`, `VectorStore`, repositories, embedding and LLM providers
- [ ] Job service, event sink, in-process runner, recovery sweep, dev-mode auth, `get_owned_project`
- [ ] `/api/health?db=1`; CI with PostgreSQL and Qdrant; commit and push

### Day 4: Collector (Stage 2)
- [ ] PDF text extraction with page numbers, cleaning, chunking, batched embeddings, write to both stores
- [ ] Pasted text path, then URL path with the SSRF guard
- [ ] Test with 3 real papers (single-column and two-column)

### Day 5: UI shell and pipeline runner (Stage 3)
- [ ] Sign-in (dev mode or chosen provider), Home and project pages, source cards with stage chips, trace drawer, NDJSON reader, reconnect, retry
- [ ] Pick the demo topic and collect 4-5 sources that really disagree (see section 4)

### Day 6: Analyst (Stage 4)
- [ ] Summary and claims, claim embeddings, write order and re-analysis cascade, Insights tab (summary + claims per source)

### Day 7: Critic, part 1 (Stage 5)
- [ ] Batched Qdrant query (other sources only, score threshold), PostgreSQL hit validation, batched LLM verdicts, skip already-judged pairs, per-project critique lock, write verdicts

### Day 8: Critic, part 2 (protect this day)
- [ ] Conflicts view with stance badges, rationale and filters
- [ ] Tune the prompt and `CRITIC_MIN_SIMILARITY` on the demo corpus; record false positives and fix the worst

### Day 9: Writer and Ask tab (Stage 6)
- [ ] Retrieval with post-filtering, tagged context, citation validation, briefing view, disagreement cards, gaps note
- [ ] Try off-topic and thin-evidence questions

### Day 10: Production hardening, part 1 (Stage 7)
- [ ] Rate limits, active-job caps, per-user budgets, kill switch, error map, retry buttons
- [ ] Concurrency and failure tests (duplicate submit, API killed mid-job, Qdrant down, PostgreSQL down, provider 429 storm)

### Day 11: Production hardening, part 2 and polish (Stage 7)
- [ ] Metrics and logging checks, `reconcile.py`, security REVIEW and fixes, bottleneck check against `02-DESIGN-DOC.md` section 14
- [ ] Empty and loading states, responsive layout, dark mode; five consecutive full runs on the demo corpus

### Day 12: Ship (Stage 8)
- [ ] Choose hosts (U2); deploy API container and web app; verify env vars, CORS, upload size, streaming (S9 on the real stack), graceful shutdown
- [ ] Backups configured and the restore drill done; keep-alive for the free vector database if applicable (or the friendly "search index unavailable" state)
- [ ] README with screenshots, architecture diagram and honest limits; `docs/DEMO-DATA.md`; secret scan and dependency audits

### Day 13: buffer and presentation
- [ ] Fix only what is broken
- [ ] Record a 2-3 minute demo video or a short GIF
- [ ] Write the portfolio description (section 6) and pin the repo on your GitHub profile

## 2. Cut order if you fall behind

1. Dark mode, Markdown export, trace panel polish
2. URL fetching (keep PDF and paste)
3. Clickable citation popovers
4. Verdict labels: reduce to a "similar claims" list (no contradicts/nuances) only if the Critic is unreliable
5. Production extras that are not security-critical: metrics dashboards and alerts (keep structured logs), `reconcile.py` repair mode (keep report mode), single-source delete (F16), usage display (F17)
6. Never cut: Collector (PDF + paste), Analyst, Writer with citations, a working end-to-end flow, tests for the core logic, **authentication and project ownership, SSRF protection, upload and page limits, timeouts, rate limits and per-user budgets, secrets hygiene, PostgreSQL backups and a restore drill**

## 3. Testing plan

### 3.1 Backend unit tests (Pytest)
| Area | What to test |
|---|---|
| `ingest/chunk.py` | size bounds, overlap, page ranges, empty input |
| `ingest/clean.py` | hyphenated line breaks, repeated headers/footers, references cut |
| `core/ids.py` | determinism, order independence of pair keys, project-scoped point IDs differ across projects for the same key, question normalization |
| `providers/embeddings.py` | batching splits correctly, retries on 429, output length equals input length, dimension check, timeout |
| `providers/llm.py` | validation retry with error appended, bounded retries, 429 backoff, typed error with retryable flag |
| `core/schemas.py` | valid and invalid Analyst, Critic and Writer outputs; camelCase aliases |
| `agents/citations.py` | unknown tags removed or flagged, zero-citation rejection |
| `ingest/ssrf.py` | localhost, 127.x, `::1`, 10.x, 172.16-31.x, 192.168.x, link-local, metadata IPs, IPv4-mapped IPv6, decimal and hex IP forms, userinfo tricks, redirect to private address, DNS answer that changes between lookups (fake resolver), non-http schemes |
| Upload and PDF limits | oversize body rejected while streaming, wrong magic bytes, encrypted PDF, over page limit, parse timeout, temp file removed after success and failure |
| `core/config.py` | missing variable produces a readable error; `AUTH_MODE=dev` refused outside local; secrets redacted in repr |
| Rate limiter and budgets | token bucket behavior, per-user vs per-IP, budget exceeded before any provider call, kill switch |
| Job service | single-flight, idempotency key replay and conflict, lease renewal, recovery sweep marks `INTERRUPTED`, stage timeout |
| Logging | redaction filter; logs never contain source text, prompts, model output or secrets |
| Module boundaries | the lint rule or test forbidding Qdrant, Gemini SDK and SQL imports outside their modules |

### 3.2 Database and consistency tests (Pytest, Docker Compose services)
Use a throwaway PostgreSQL database and a throwaway Qdrant collection per test run:
- Alembic upgrade from an empty database works; models and migrations agree.
- Qdrant migration is idempotent; upserts are idempotent (same project and key, same point ID); two projects with the same key do not overwrite each other.
- Tag allocation under concurrent add-source requests yields unique tags with no reuse; the active-job unique index stops duplicate jobs.
- Deleting a project removes all PostgreSQL rows and all Qdrant points; a Qdrant failure leaves the project `deleting` and a repeated delete finishes it; `reconcile` completes it.
- The Critic query never returns claims from the same source, respects the minimum similarity, and never returns chunk points.
- Re-analysis replaces claims, cascades verdict removal, clears `stageCritiqued`.
- Crash windows from `03-DATABASE-SCHEMA.md` section 13 (fail after the PostgreSQL write, after the Qdrant write, before the flag): retry converges, retrieval ignores incomplete sources.
- Cross-user isolation: user B cannot read, list, ask, delete, stream events of, or fetch jobs and briefs of user A's project (all 404).

### 3.3 Frontend unit tests (Vitest)
| Area | What to test |
|---|---|
| NDJSON reader | events split across chunks, partial last line, blank lines, invalid JSON line, unknown event type ignored, heartbeats hidden |
| Pipeline runner | success chain, error mid-chain with retry, reconnect with `after=lastSeq`, re-attach from `activeJobs`, 401 handling, idempotency key reuse |
| Zod schemas | every fixture in `contracts/` validates; invalid variants are rejected |
| Error-message mapping | every error code has a message; retry-after displayed when present |
| Components | stance badge shows color plus icon plus text; empty, loading, failed, reconnecting, signed-out states render |

### 3.4 Contract tests
Every file in `contracts/` is validated by Pydantic in Pytest and by Zod in Vitest. A change to an endpoint, error or event that does not change the fixture and both schemas fails CI. CI also checks that the committed `apps/api/openapi.json` is current.

### 3.5 Manual end-to-end script (run before every deploy)
1. Sign in; create a new project.
2. Upload PDF 1: stages complete, source card shows chunks and claims.
3. Upload PDF 2 and PDF 3: Critic finds cross-source pairs.
4. Open Conflicts: at least 3 sensible contradicts/nuances items.
5. Ask 3 questions: citations valid, disagreements present, gaps honest.
6. Try a scanned or empty PDF: friendly error. Try an oversize file and a non-PDF: specific messages.
7. Try a blocked URL such as `http://localhost`: blocked with a friendly error.
8. Reload the page mid-stage: trace and result reappear. Reload after: data persists.
9. Click Retry on a stage after stopping Qdrant briefly: clear error, retry succeeds.
10. Sign in as a second user: the first user's project is not visible and its URL shows "not found".
11. Delete one source: its claims and conflicts disappear. Delete the project: records removed from PostgreSQL and Qdrant (check with a script).

### 3.6 Quality check for the Critic
Take 15 pairs from the demo corpus, label them yourself, compare with the model's labels. Aim for no obvious false `contradicts`. If there are many: raise `CRITIC_MIN_SIMILARITY`, make the prompt stricter, or require confidence above 0.6 for `contradicts` in the UI.

### 3.7 Load and capacity smoke checks (Stage 7; measure, do not assume)
- With fake providers, run N concurrent pipelines (choose N from the active-job caps) and record event-loop lag, PostgreSQL pool wait, memory and time to completion. Record the numbers in `docs/02-DESIGN-DOC.md` section 14 as the baseline for scale-out triggers.
- With real providers, run one full pipeline and record per-stage durations and token usage to set per-user budgets (U4, S6).

## 4. Demo corpus
- Pick one debated topic where credible sources really disagree or differ in scope.
- 4-5 sources: 2-3 PDFs (papers or reports) and 1-2 articles.
- Pre-test that the Critic finds at least 3 meaningful conflicts or nuances and that 3 questions give good briefings.
- Save the list and the questions in `docs/DEMO-DATA.md`.

## 5. Demo video outline (about 2:30)

| Time | Content |
|---|---|
| 0:00-0:20 | Problem: reading several sources and missing where they disagree |
| 0:20-1:10 | Add 3 sources and narrate the trace: Collector, Analyst, Critic |
| 1:10-1:40 | Conflicts view: one contradiction and one nuance with the rationale |
| 1:40-2:10 | Ask a question: cited briefing, click a citation, "where sources disagree" |
| 2:10-2:30 | Architecture in one sentence: four Python agents sharing a Qdrant vector memory with a PostgreSQL system of record; link to the repo |

Tips: rehearse once, record twice; clean browser profile, zoom 110-125%; pre-load a processed project as a fallback for the briefing segment.

## 6. Portfolio and resume

README essentials: what it does (one paragraph), a GIF or screenshots, the architecture diagram, the agents table, why Qdrant plus PostgreSQL, how to run locally, known limits, live link.

Resume bullet templates (replace the brackets with your real numbers once you have them; do not claim metrics you have not measured):
- Built Research Desk, a multi-agent research assistant (Next.js, TypeScript, FastAPI, PostgreSQL, Qdrant, Gemini) that ingests PDFs and articles, compares claims across sources, and produces cited briefings.
- Designed a four-agent Python pipeline communicating through a shared evidence memory; implemented similarity search with relational filters to detect agreement and contradictions between sources.
- Engineered for reliability and cost: persisted jobs with resumable NDJSON streaming, idempotent writes across PostgreSQL and Qdrant, schema-validated model output, SSRF-hardened fetching, per-user budgets and rate limiting; [N] backend tests, [N] frontend tests, [N]-source demo corpus.
- Documented bottlenecks and scale-out triggers (worker split, shared limiter, index scaling) with measured baselines [fill in after Stage 7].

## 7. Release checklist

### 7a. Stage 0 acceptance (foundation for implementation)
- [ ] `docker compose up -d postgres qdrant` starts both with passing healthchecks; ports bound to 127.0.0.1
- [ ] `apps/api`: `uv sync` works from a clean checkout; the API starts; `GET /api/health` returns booleans and no secret values
- [ ] A missing required setting prints a readable list and exits; `AUTH_MODE=dev` with `APP_ENV` other than `local` is refused
- [ ] Error envelope and request IDs work for a validation error and an unexpected error; no stack trace in responses
- [ ] Module boundary rule is active and fails when a forbidden import is added
- [ ] `apps/web`: `npm install` works; the home page shows API reachable or an error state
- [ ] `contracts/health.json` and `contracts/error.json` validate in both Pytest and Vitest
- [ ] Backend checks pass (`ruff check`, `ruff format --check`, `mypy src`, `pytest`) and frontend checks pass (`typecheck`, `lint`, `test`)
- [ ] CI runs both jobs green; `.gitignore` excludes `.env*` except examples; three `.env.example` files exist with empty values
- [ ] AGENTS.md status updated; commit `stage0: ...` exists

### 7b. Repo
- [ ] Public repository with a clear README and the `docs/` folder
- [ ] `.env.example` files present; **no real keys or database URLs anywhere in files or git history**
- [ ] Fresh clone + README steps works
- [ ] Tests pass in CI with a documented command; dependency audits run (`pip-audit` or equivalent, `npm audit`) and findings triaged

### 7c. Product
- [ ] Full flow works 5 of 5 times on the demo corpus
- [ ] Error states friendly; no stack traces visible
- [ ] Live demo link works, with a note that provider quotas can run out and a paused vector database may need to wake up

### 7d. Production readiness (from `02-DESIGN-DOC.md` section 13)
Each item is done, or recorded as an accepted gap with a reason.
- [ ] Authentication enforced on every route except health; provider decision U1 resolved; dev auth impossible in production
- [ ] Ownership: cross-user isolation tests pass (M7); other users' resources return 404
- [ ] Secrets: only in host secret store or environment; settings redact; secret scan clean; rotation procedure written; least-privilege database role
- [ ] Input validation: Pydantic on every input, Zod on every response and event, ID pattern checks
- [ ] SSRF: all cases in section 3.1 pass; API has no unnecessary network access to internal services
- [ ] File limits: upload size enforced while streaming, page and character limits, parse timeout, temp files cleaned
- [ ] Rate limiting and active-job caps verified with a test; limits documented in the UI error copy
- [ ] Retries and timeouts: every outbound call has a timeout; retries bounded with jitter; stage timeout verified
- [ ] Idempotency: duplicate submit and `Idempotency-Key` behavior verified; re-run of every stage creates no duplicates
- [ ] Logging: structured JSON with request and job IDs; redaction test passes; no source text in logs
- [ ] Monitoring: metrics exported; alerts defined for provider errors, job failures, interrupted jobs, pool exhaustion, store outages, budget burn (thresholds from the baseline in section 3.7)
- [ ] Migrations: Alembic applied through the release step; expand/contract rule followed; Qdrant migration idempotent; rollback path noted
- [ ] Backups: PostgreSQL backups enabled; **restore drill completed (M8)**; Qdrant snapshot vs rebuild decision recorded (U9); rebuild procedure written and, if rebuild-only, timed
- [ ] Cost controls: per-user daily budgets set from measured usage; kill switch tested; global concurrency limit set from real quota (U4)
- [ ] Privacy: UI and README state that text is sent to Gemini; current data-use terms confirmed (U16); retention and deletion promises stated (U15)
- [ ] CORS limited to the exact web origin(s); TLS on all public endpoints and to PostgreSQL
- [ ] Graceful shutdown tested: deploy during a running job leaves a retryable `INTERRUPTED` state
- [ ] Streaming verified through the real hosts (S9): heartbeats, no buffering, reconnect works

### 7e. Presentation
- [ ] Demo video or GIF linked in the README
- [ ] Repo pinned on GitHub; project added to resume and LinkedIn

## 8. Risk watchlist

| Risk | Early warning sign | Response |
|---|---|---|
| LLM or embedding quota | 429 errors during testing; `LLM_QUOTA` events | Lower call volume, bigger chunks, tighten budgets, fallback provider or local embeddings behind the adapters |
| Critic quality | Many false conflicts | Stricter prompt, higher similarity threshold, show confidence |
| PDF extraction | Garbled two-column text; slow or memory-heavy parses | Improve cleaning, test other libraries (S8), subprocess isolation, use paste for the demo corpus |
| Vector database paused or unreachable | `VECTOR_DB_ERROR` after a quiet week | Resume in the console; set up the keep-alive job; rebuild index from PostgreSQL if lost |
| PostgreSQL and Qdrant drift | `reconcile` reports mismatches; briefs miss known sources | Run `reconcile`; check write order and post-filter; investigate crash windows |
| Streams cut by hosts | Streams end without `stage_end`; reconnect events | Heartbeats, reconnect endpoint, change host or proxy settings (S9) |
| Event loop blocked | Lag metric rises during uploads; slow health checks | Move processing to a subprocess; lower limits; consider a worker (`02-DESIGN-DOC.md` section 14.1) |
| Database connection exhaustion | Pool wait time rises; "too many connections" | Shorter transactions, pool sizing, connection pooler |
| Cost runaway or abuse | Budget burn alerts; sudden usage from one user | Lower budgets, kill switch, review rate limits |
| Host limits | Upload or timeout failures | Smaller PDFs for the demo; confirm limits on Day 12 at the latest, earlier in S9 |
| Scope creep and premature infrastructure | New services or queues proposed without measurements | Require the measurement named in section 14 of the design doc; apply the cut order |
| Burnout or time | Behind by more than a day | Apply the cut order immediately |
