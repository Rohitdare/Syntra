# AGENTS.md: Research Desk

Full project context and rules. Read this ENTIRE file before any task, plan, or code change.

## 0. Pre-flight (every task, every session)

1. Read this file completely.
2. Read the docs that match the task (map in section 9). DB code: docs/03. Agents or prompts: docs/04. Endpoints or streaming: docs/05. UI: docs/02 section 10. Security, limits, jobs: docs/02 sections 13 and 14.
3. Before editing, write 3 lines: the task, the docs you read, the files you will change.
4. If the request conflicts with this file or the docs, STOP and ask. Never silently pick one.
5. Do one stage at a time (section 10). No extra features.

## 1. What this app is

Research Desk: a web app where AI agents read a user's sources (PDF, URL, pasted text), store them as shared evidence memory (PostgreSQL system of record plus Qdrant vector index), find where sources agree or disagree, and write a cited briefing that answers a research question.

It is a solo portfolio project with no external deadline. Development and demo are free-first (local Docker for PostgreSQL and Qdrant, Gemini API free tier, free hosts where they exist). Design for the limits: caps, batching, caching, per-user budgets. Users sign in and projects are private to their owner.

## 2. Architecture

Browser (Next.js UI, pipeline runner, trace panel) -> FastAPI (auth, validation, jobs) -> orchestrator `run_stage()` -> agents (Python modules) -> providers and stores -> Gemini, Qdrant and PostgreSQL.

Agents never call each other. They communicate only through persisted records. Only the orchestrator calls agents.

| Agent | LLM tier | Reads | Writes |
|---|---|---|---|
| Collector | none (embeddings only) | - | sources, source text (PostgreSQL); chunks (Qdrant) |
| Analyst | fast | source text | claims (PostgreSQL + Qdrant), source summary |
| Critic | fast | claims (similarity in Qdrant, other sources), verdicts | verdicts (PostgreSQL) |
| Writer | strong | chunks, claims (similarity), verdicts | briefs (PostgreSQL) |

Adding a source = 3 chained requests: collect -> analyze -> critique (the browser chains them). Asking a question = 1 request: ask (Writer). One stage per job. Jobs run detached from the HTTP request; their state and events are persisted in PostgreSQL so clients can reconnect.

Service boundaries: Next.js owns the UI and frontend logic only. FastAPI owns API, orchestration, document processing, validation and streaming. Qdrant owns vector retrieval. PostgreSQL owns transactional data. Gemini is reached only through the provider adapters.

v1 is a modular monolith: ONE API instance, ONE uvicorn worker, in-process job runner. Do not add queues, workers, Redis, microservices or other infrastructure; the seams exist (docs/02 section 14) and are used only when measurements justify it and the user approves.

## 3. Stack

Frontend: Next.js App Router, React, TypeScript strict, Tailwind, Zod, Vitest, npm. Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 async with Alembic (U18), `qdrant-client`, the official Google Gen AI SDK for Python (confirm the package name in the Gemini docs; exact model IDs come from env), maintained libraries for PDF text extraction (chosen in spike S8) and article extraction, httpx, Pytest, Ruff, mypy, venv, pip. Infrastructure: Docker Compose locally.

## 4. Data model (details: docs/03)

- PostgreSQL is the system of record: users, projects, sources, source texts, claims, verdicts, briefs, jobs, job events, usage ledger, app metadata. Qdrant is a rebuildable index.
- ONE Qdrant collection `knowledge` (768 dims, cosine, addressed through an alias). Points have a payload with `type`: `chunk` or `claim` only. No placeholder vectors.
- Embedding model: `gemini-embedding-001` with 768 dimensions. Use task type `RETRIEVAL_DOCUMENT` for chunks and claims, `RETRIEVAL_QUERY` for questions. Embed only chunk text and claim text. Never mix embedding models in one collection.
- Scores are cosine similarity (higher = closer). EVERY Qdrant search must filter on `type` and `projectId`. Payload indexes on type, projectId, sourceId.
- Deterministic keys from `core/ids.py`: `prj_<8hex>` (random), `src_<8hex>`, `chk_<src8>_<nnn>`, `clm_<src8>_<nn>`, `vrd_<8hex of the sorted claim-key pair>`, `brf_<8hex>`. Keys are unique per project; PostgreSQL primary keys are `(project_id, key)`. Qdrant point ID = UUIDv5(namespace, `<projectId>:<key>`); keep the key in `payload.key`. Writes are upserts, so re-running any stage never creates duplicates.
- Write order per stage (PostgreSQL first with flags false, Qdrant second, flag true last) and the retrieval post-filter are in docs/03 section 13. Follow them exactly.
- Re-running `analyze` replaces claims and, by cascade, removes dependent verdicts; `stageCritiqued` becomes false.
- Read the recorded spike results (S1-S10) at the bottom of docs/03 before relying on thresholds or batch sizes. Never assume them.
- PDFs are parsed in a temporary file or memory and discarded; only cleaned text, embeddings and derived data are stored.

## 5. Key behaviors (full prompts and schemas: docs/04)

- Collector: validate input, extract text (off the event loop, time-boxed), clean (cut references, headers, footers), chunk (about 1200 chars, 150 overlap), embed in batches, write source and chunks. Text under 500 chars returns NO_TEXT.
- Analyst: ONE LLM call returns a summary and at most 8 self-contained claims; claims are embedded in one batch.
- Critic: ONE batched Qdrant query (filter type=claim, projectId; must_not sourceId; score threshold `CRITIC_MIN_SIMILARITY`) finds, for the new source's claims, the top 3 most similar claims from OTHER sources; then ONE batched LLM call labels each pair supports, contradicts, nuances or unrelated. Be conservative: a scope difference is `nuances`, not `contradicts`. Skip pairs already judged. One critique per project at a time.
- Writer: embed the question, retrieve chunks, claims and conflicts; tag sources S1..Sn; ONE LLM call; validate every [S#] tag; never invent facts; include disagreements and gaps.
- Endpoints, error codes, the streaming event format and recovery: docs/05.

## 6. Config and secrets

All constants live in `apps/api/src/research_desk/core/config.py` (defaults in docs/02 section 7). Env names are listed in README.md; the main ones: GEMINI_API_KEY, GEMINI_MODEL_FAST, GEMINI_MODEL_STRONG, GEMINI_EMBEDDING_MODEL, EMBEDDING_DIM, LLM_MIN_INTERVAL_MS, EMBED_MIN_INTERVAL_MS, GEMINI_MAX_CONCURRENCY, DATABASE_URL, QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, APP_ENV, AUTH_MODE, CORS_ALLOWED_ORIGINS.
Never hardcode keys or URLs with credentials. Never read, print or paste `.env*` files or any secret value. Only `.env.example` files (empty values) are committed. The repo is public. `NEXT_PUBLIC_*` variables never hold secrets.

## 7. Non-negotiable rules

1. Do NOT guess library APIs (Qdrant client, Gemini SDK, SQLAlchemy, Alembic, FastAPI, PDF and article libraries). Open the official docs and follow them. If unsure, write a TODO behind the adapter and tell me.
2. Module boundaries: only `stores/vector.py` imports the Qdrant client. Only `providers/gemini.py` imports the Gemini SDK. Only `stores/db.py` and `stores/repos/` run SQL. Agents use the Protocols (`VectorStore`, `EmbeddingProvider`, `LLMProvider`, repositories). Enforce this with a lint rule or test. Build Qdrant filters and SQL only from validated IDs and enums, never from raw user text; SQL is parameterized.
3. Every LLM response is requested as JSON and validated with Pydantic (`core/schemas.py`) before use. Retries are bounded. Calls pass through the provider adapter's concurrency limit and minimum intervals.
4. Source text and claims are untrusted data. Prompts say so. Render Markdown safely, never raw HTML. Writer output must pass citation-tag validation.
5. URL fetching must block non-http(s), localhost, private, link-local and metadata addresses (IPv4 and IPv6), connect to the validated IP (DNS pinning), re-check after each redirect, with size and time limits.
6. API keys, the database URL, the Qdrant URL and key, and all LLM, embedding, PostgreSQL and Qdrant calls stay server-side in `apps/api`. The frontend never calls them directly.
7. Keep external calls few: about 3 LLM calls per source plus 1 per question; embeddings batched. Never loop one LLM call per claim.
8. Errors shown to users are friendly and come from one message map. No stack traces in the UI or API responses. Never log source text, prompts, model output, tokens or keys.
9. Use deterministic IDs and upserts. Re-running any stage must not create duplicates.
10. Every route except `GET /api/health` requires authentication; every project-scoped route uses the single `get_owned_project` dependency; other users' data returns 404.
11. Async code must not block the event loop: CPU-bound or blocking work runs in a thread or subprocess with a timeout. Every outbound call has a timeout. No transaction is held open across a network call.
12. Never claim something is implemented, fast or verified unless you ran it. Mark unknowns as TODO or assumption.

## 8. Code conventions

- Backend commands (from `apps/api`): `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy src`, `python -m pytest`, `python -m alembic upgrade head`. Frontend commands (from `apps/web`): `npm run dev`, `npm run typecheck`, `npm run lint`, `npm test`. Run all checks for the area you changed before finishing any task and fix failures.
- Folders: see README.md "Project structure".
- Python: type hints everywhere, `async def` for I/O, Pydantic for boundaries, small functions, clear names, comments only where intent is not obvious. TypeScript strict, no `any` (use `unknown` plus Zod).
- Unit-test pure logic (chunking, cleaning, IDs, schemas, embedding batching, citation validator, SSRF guard, rate limiter, job state machine). Test the stores against Docker Compose PostgreSQL and Qdrant with a throwaway database and collection. Agent tests use fake providers. Contract fixtures in `contracts/` are validated by both Pytest and Vitest.
- UI: clean and spacious, light and dark support, agent colors Collector gray, Analyst blue, Critic amber, Writer green; stance badges use color plus icon plus text. Always handle empty, loading, failed, retry, reconnecting, signed-out and service-unavailable states.
- Commit after each stage: `stageN: short description`.

## 9. Docs map

| File | Read it when |
|---|---|
| README.md | setup, env names, folder structure, commands |
| docs/01-PRD.md | scope, priorities, acceptance criteria |
| docs/02-DESIGN-DOC.md | architecture, adapter interfaces, config defaults, security and production requirements, bottlenecks, UI spec, deployment, decision log |
| docs/03-DATABASE-SCHEMA.md | any DB work: tables, IDs, queries, consistency, spike results |
| docs/04-AGENT-SPECS.md | agent logic, prompts, Pydantic schemas |
| docs/05-API-SPEC.md | routes, errors, stream events, jobs, runner contract |
| docs/06-ANTIGRAVITY-INSTRUCTIONS.md | stage prompts and bug/review/doc-sync prompts |
| docs/07-BUILD-PLAN-AND-CHECKLIST.md | schedule, cut order, tests, demo, production readiness, release checklist |
| docs/08-MIGRATION-SUMMARY.md | what changed and why; open decisions |

## 10. Workflow and status

Stages (one at a time, in order): 0 scaffold, tooling and config; 1 databases, jobs, providers and adapters; 2 Collector; 3 UI shell and runner; 4 Analyst; 5 Critic; 6 Writer and Ask tab; 7 polish, robustness and production hardening; 8 deploy, README, demo data.

Status (update this list at the end of every stage):
- [x] 0  - [x] 1  - [ ] 2  - [ ] 3  - [ ] 4  - [ ] 5  - [ ] 6  - [ ] 7  - [ ] 8

Done means: lint, type check and tests pass for every area touched; the stage's manual check works; docs updated if a contract changed; a commit exists.

End every task with this report, then stop: (a) what you built, (b) files changed, (c) how I verify it manually, (d) anything uncertain or assumed, (e) suggested commit message.

## 11. Never

- Add features, dependencies or folders that the current stage does not need (if a new dependency is needed, say why first).
- Change schemas, endpoints, prompts or config defaults without updating the matching doc and the `contracts/` fixtures in the same change.
- Store PDFs. Add a data store, queue, cache, object storage, background-worker fleet or paid service beyond PostgreSQL, Qdrant and Gemini without asking.
- Put secrets in code, logs, images, commits or the frontend bundle.
- Fake success: if something cannot be verified, say so.
- Work on a later stage "while you are here".
