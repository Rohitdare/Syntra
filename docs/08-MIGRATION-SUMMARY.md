# Migration Summary: Python-Based, Scalable Architecture

Version 1.0 | Scope: documentation only. No application code was written or changed, and no infrastructure files (for example `docker-compose.yml`) were created; they are specified for Stage 0. No library, SDK, provider limit or hosting behavior was checked against external documentation during this migration, so every such item is marked "confirm" or sits in a spike (S1-S10) or an open decision (U1-U18).

## 1. Input reviewed

The two uploaded archives contained one document set (11 files, plus identical nested copies): `README.md`, `AGENTS.md`, `GEMINI.md`, `docs/01` to `docs/07`. The loose copies of `02-DESIGN-DOC.md`, `03-DATABASE-SCHEMA.md` and `AGENTS.md` were byte-identical to the nested ones. No other deployment document existed; deployment content lived in `02-DESIGN-DOC.md` section 11 and the Stage 8 prompt.

## 2. Changed documents

| Document | Version | Change |
|---|---|---|
| `README.md` | rewritten sections | New stack, env files per service, commands, monorepo structure, agents table by store, known limits, doc index (adds 08) |
| `AGENTS.md` | rewritten sections | Python and FastAPI rules, module boundaries, PostgreSQL plus Qdrant model, auth and ownership, event-loop and timeout rules, commands, stage list renamed, "Never" list updated; section numbers 0-11 kept |
| `GEMINI.md` | unchanged | Only points to `AGENTS.md`; no stale content |
| `docs/01-PRD.md` | 0.2 to 0.3 | Auth and ownership in scope, new features F14-F17 and user stories US-8/US-9, new NFR rows, metrics M7/M8, risks, open questions; product vision, F1-F13, US-1 to US-7 and their acceptance criteria preserved (US-2, US-3, US-7 gained criteria) |
| `docs/02-DESIGN-DOC.md` | 0.3 to 0.4 | Sections 1-12 keep their numbers and are rewritten for the new stack; new sections 13 (production requirements), 14 (scalability and bottleneck register), 15 (decision log), 16 (open decisions and assumptions) |
| `docs/03-DATABASE-SCHEMA.md` | 0.3 to 0.4 | Sections 1-11 keep their numbers (storage split, IDs, record types, Q1-Q10, spikes now S1-S10); new sections 12 (PostgreSQL tables), 13 (consistency and recovery), 14 (migrations and backups) |
| `docs/04-AGENT-SPECS.md` | 0.2 to 0.3 | Module contract added; zod schemas become Pydantic; prompts unchanged word for word; Analyst input source and write orders changed |
| `docs/05-API-SPEC.md` | 0.1 to 0.2 | FastAPI, auth, error envelope and codes, new endpoints, event `jobId`/`seq`/`heartbeat`, reconnect, idempotency, recovery, contract versioning; existing endpoint behavior preserved |
| `docs/06-ANTIGRAVITY-INSTRUCTIONS.md` | 0.2 to 0.3 | Operating rules and all stage prompts rewritten (stage order and names preserved); Stage 0 is detailed enough to execute; added BOTTLENECK CHECK prompt |
| `docs/07-BUILD-PLAN-AND-CHECKLIST.md` | 0.2 to 0.3 | 13-day plan, cut order protects security items, Pytest/Vitest/contract/consistency/concurrency tests, Stage 0 acceptance checklist, production readiness checklist |
| `docs/08-MIGRATION-SUMMARY.md` | new | This file (follows the numbered naming convention) |

## 3. Major architectural decisions

Full table with rationale: `docs/02-DESIGN-DOC.md` section 15.

- D1 Monorepo: `apps/web` (Next.js), `apps/api` (FastAPI, uv), `docs/`, `contracts/`.
- D2 The browser calls FastAPI directly (CORS, Bearer token) for API, uploads and streams; Next.js does UI and session.
- D3 PostgreSQL is the system of record; Qdrant keeps only `chunk` and `claim` points and is rebuildable. `project`, `source`, `verdict`, `brief` moved to PostgreSQL; placeholder vectors disappear. `claim` is stored in both stores.
- D4 Keys are unique per project; Qdrant point ID = UUIDv5 of `<projectId>:<key>`. Key formats, hashing inputs and idempotent upserts are preserved.
- D5 Jobs and job events persisted from the start; in-process `JobRunner` behind an interface; jobs detached from requests; NDJSON streams tail persisted events and can resume.
- D6/D14 One API instance and worker in v1; no Redis, broker, cache, object storage or microservices. Scale-out ladder with triggers is documented instead.
- D7 `LLMProvider` and `EmbeddingProvider` Protocols with one Gemini implementation that centralizes limits, retries, structured output and usage accounting.
- D8 Bearer-token auth verified by FastAPI; provider undecided; dev mode refuses to start outside `APP_ENV=local`.
- D9 Cleaned source text stored in PostgreSQL (PDFs still never stored).
- D10-D11 camelCase wire format via Pydantic aliases; contracts verified by shared JSON fixtures in Pytest and Vitest.
- D12 Alembic for PostgreSQL; idempotent script plus alias for Qdrant; migrations as a release step.
- D13 Re-running `analyze` cascades deletion of dependent verdicts.
- D16 Retrieval hits are post-filtered against PostgreSQL.

## 4. Conflicts and gaps found, and how each was resolved

| # | Finding | Resolution |
|---|---|---|
| C1 | PRD non-goal "no user account system, projects identified by unguessable ID" contradicts the required authentication and project ownership | Lightweight sign-in and ownership moved in scope (PRD, API, design); teams, sharing, billing stay out |
| C2 | `AGENTS.md` forbade "another database or paid service"; PostgreSQL is now required | Rule rewritten: PostgreSQL, Qdrant and Gemini allowed; any other store, queue, cache or paid service needs approval |
| C3 | "Everything must run on free tiers" cannot be promised for a long-running Python API plus PostgreSQL | Changed to free-first; hosting and free-tier limits marked unverified (U2) |
| C4 | `AGENTS.md` forbade dependencies the stage does not need, but the old Stage 0 installed the Qdrant and Gemini SDKs | Stage 0 installs only what it uses; SDKs and database packages arrive in Stage 1, PDF and article libraries in Stage 2 |
| C5 | PRD F1 requires listing projects; the API spec had no list endpoint | Added `GET /api/projects` |
| C6 | Re-running a stage (F11) with "skip pairs already judged" could keep verdicts that point to claims whose text changed after re-analysis | D13: re-analysis replaces claims and cascades verdict removal; `stageCritiqued` resets |
| C7 | 8-hex keys as global primary keys would collide across many projects and silently overwrite data | D4: project-scoped uniqueness; project key insert retries on conflict; width review noted (U13) |
| C8 | Chunk text existed only in Qdrant, so losing Qdrant lost the source content (PDFs are not stored) | D9: `source_texts` in PostgreSQL enables rebuild; Analyst now reads it (removes chunk-overlap duplication) |
| C9 | Error code `DB_ERROR` meant "Qdrant unreachable"; there are now two stores | `DB_ERROR` is PostgreSQL; new `VECTOR_DB_ERROR` is Qdrant |
| C10 | The stage-per-request rationale was serverless timeouts; the backend is now a long-lived container | One stage per job kept (the browser still chains stages), rationale rewritten: detached jobs, recovery, timeouts |
| C11 | Per-IP in-memory rate limiting does not fit authenticated multi-user traffic or more than one instance | Per-user and per-IP limits, active-job caps and budgets; in-process limits are the stated reason v1 is single-instance |
| C12 | Old Day 1 packed scaffold, spikes, databases and adapters into one day | Split across Days 1-3; plan raised from 10 to 13 days (estimate) |
| C13 | Old agent doc said agents communicate "only through Qdrant" | Now "only through persisted records" (PostgreSQL and Qdrant) |

## 5. Enhancements beyond the brief (accept or drop)

These came from the request to anticipate bottlenecks and strengthen the plan. Each is small and traceable; drop any by removing the matching decision or section.

- Bottleneck register B1-B17 and scale-out ladder with triggers (`02-DESIGN-DOC.md` section 14).
- Persisted job events with `seq`, a resumable events endpoint, heartbeats, lease and recovery sweep (reload-safe progress, F15).
- Single-flight jobs and optional `Idempotency-Key`.
- DNS-pinned SSRF defence; PDF page and parse-time limits; streamed upload size enforcement.
- Per-user budgets, usage ledger, `LLM_ENABLED` kill switch, global Gemini concurrency limit.
- Qdrant collection alias and pinned embedding model for zero-downtime re-embedding; `reconcile` and rebuild procedure.
- Spikes S7-S10 (structured output, PDF library and licence, streaming through hosts, concurrent tag allocation).
- New features F14-F17 (auth, reconnect, delete a source, usage limits) and `GET /api/me`.
- Concurrency, failure-injection, isolation and load-baseline tests; Stage 0 acceptance checklist.

## 6. Unresolved questions

Full list with defaults: `docs/02-DESIGN-DOC.md` section 16 (U1-U18). Decide these first:

1. U1 Authentication provider and token type.
2. U2 Hosts for web, API, PostgreSQL and Qdrant, and whether usable free tiers exist for them.
3. U3 / S8 PDF library: quality, speed and licence (some libraries are copyleft).
4. U4 / S2 / S6 Real Gemini model IDs, quotas and embedding batch limit.
5. U6 / S7 How Gemini structured output accepts Pydantic-derived schemas.
6. U7 / S9 Whether the chosen hosts allow long-lived NDJSON streams.
7. U9 PostgreSQL backup capabilities and the Qdrant snapshot-versus-rebuild policy.
8. U11 Python version and type checker (3.12+ and mypy are assumptions).

## 7. Final verification

Searched all project documents for: TypeScript backend file names and commands (`*.ts`, `npx tsx`, `lib/db`, `lib/embed`, `lib/llm`, `callLLM`, `runStage`), the Qdrant JS client, Next.js API routes, serverless assumptions, placeholder vectors, other database products, and zod or Vitest used for backend work. Remaining matches are intentional: Zod, Vitest and TypeScript in the frontend, `src/lib/config.ts` in `apps/web`, "pgvector" as an unplanned alternative in `03` section 11, and "placeholder vectors" only where explaining their removal.

Also checked: section-number cross-references between documents resolve to existing sections; environment variable names agree between `README.md`, `AGENTS.md`, `02` section 7 and the Stage 0 prompt; health response keys agree between `05`, `README.md` and Stage 0; error codes in `05` match the behaviors in `02` section 8 and `04` section 6.

Not verified (by design, listed so nothing is mistaken for fact): that the named libraries and APIs behave as assumed, Gemini and Qdrant limits, free-tier availability, performance targets, and the 13-day estimate.
