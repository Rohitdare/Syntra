# Research Desk

A team of AI agents that reads your sources (PDFs, URLs, pasted text), remembers them in a **Qdrant** vector database with a **PostgreSQL** system of record, finds where the sources agree or disagree, and writes a cited briefing that answers your research question.

> **Implementation status (2026-10-30):** The root `AGENTS.md` marks stages 0–3 complete. Collector and Analyst code, project/source APIs, and the research workspace UI are present. Analyst is implemented and verified. Critic agent core is implemented (Stage 5A/5B), with orchestrator pipeline and UI integration in progress. Writer/Ask remains to be implemented.

## What it does

1. Sign in and create a research project (private to you).
2. Add 3-8 sources (PDF upload, URL, or pasted text).
3. Watch the agents work in a live trace panel:
   - the **Collector** extracts, cleans, chunks, embeds and stores the text,
   - the **Analyst** writes a summary and extracts key claims,
   - the **Critic** compares each new claim with similar claims from *other* sources and labels the pair as supports, contradicts, nuances or unrelated.
4. Browse summaries, claims and a conflicts view.
5. Ask a question. The **Writer** retrieves the most relevant chunks, claims and conflicts and produces a briefing with citations and a "where sources disagree" section.

## The agents

Each agent is a separate Python module in the FastAPI backend (`apps/api/src/research_desk/agents/`).

| Agent | Calls an LLM? | Reads | Writes |
|---|---|---|---|
| Collector | No (uses the embedding provider) | - | sources, source text (PostgreSQL); chunks (Qdrant) |
| Analyst | Yes (fast model) | source text | claims (PostgreSQL and Qdrant), source summary |
| Critic | Yes (fast model) | claims (similarity search in Qdrant), verdicts | verdicts (PostgreSQL) |
| Writer | Yes (strong model) | chunks and claims (similarity search), verdicts | briefs (PostgreSQL) |

## How the data is stored

**PostgreSQL** is the system of record: users, projects, sources, extracted text, claims, verdicts, briefs, jobs, job events and usage. **Qdrant** is the shared evidence memory: one collection holds 768-dimension embeddings for chunks and claims with filterable payloads. Agents read each other's work through filtered similarity search such as "the three most similar claims, from a different source, in this project", and through SQL for relationships. If Qdrant is lost it can be rebuilt from PostgreSQL. See `docs/03-DATABASE-SCHEMA.md`.

## Architecture at a glance

```
Browser (Next.js UI, NDJSON reader, Zod)
   | Bearer token, JSON and NDJSON over HTTP
   v
FastAPI (apps/api): auth, validation, jobs, orchestrator -> agents -> providers / stores
   |-> PostgreSQL (system of record, jobs, events)
   |-> Qdrant (chunk and claim vectors)
   `-> Gemini API (LLM and embeddings, behind provider adapters)
```

One backend process runs all four agents in v1. Interfaces for a job runner, rate limiter, event sink and providers allow background workers and other model providers later, only when measured load justifies them (`docs/02-DESIGN-DOC.md` section 14).

## Tech stack

- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind CSS, Zod, Vitest, npm
- **Backend:** Python 3.12, FastAPI, Pydantic, Pytest, venv, pip
- **AI:** Google Gemini API (key from Google AI Studio): Flash-class models for the agents and `gemini-embedding-001` for embeddings, behind `providers/llm.py` and `providers/embeddings.py`
- **Vector database:** Qdrant (local Docker or a cloud cluster) behind `stores/vector.py`
- **Application database:** PostgreSQL behind repositories, with Alembic migrations
- **Document processing:** Python libraries for PDF text extraction and safe public-article extraction (listed here once chosen; see spike S8)
- **Streaming:** NDJSON over HTTP
- **Infrastructure:** Docker Compose for local development; frontend and backend deploy independently

Development and the demo target free tiers where they exist; see `docs/02-DESIGN-DOC.md` sections 11 and 16 for what is and is not verified.

## Getting started

Prerequisites: Node 20+, Python 3.12, Docker with Compose, and a Gemini API key from Google AI Studio.

Local development commands:

```bash
# 1. infrastructure
cp .env.example .env                          # compose settings; fill in the values
docker compose up -d postgres qdrant

# 2. backend
cd apps/api
cp .env.example .env                          # then fill in the values
python -m venv .venv                          # create virtual environment
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1  |  macOS/Linux: source .venv/bin/activate
# Install the repository-pinned development requirements; do not upgrade dependencies implicitly.
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head                   # PostgreSQL schema
python scripts/migrate_qdrant.py                 # Qdrant collection, indexes, alias
python scripts/spike_db.py                       # one-time database/provider check
python -m uvicorn research_desk.main:app --reload --port 8000

# 3. frontend (new terminal)
cd apps/web
cp .env.example .env.local                    # then fill in the values
npm install
npm run dev                                   # http://localhost:3000
```

### Environment variables

Three example files are committed with empty values: `.env.example` (Compose), `apps/api/.env.example`, `apps/web/.env.example`. Any constant in `docs/02-DESIGN-DOC.md` section 7 can also be set as an environment variable of the same name.

`.env.example` (repository root, used by Docker Compose):

```bash
POSTGRES_USER=
POSTGRES_PASSWORD=          # local development value of your choice
POSTGRES_DB=
```

`apps/api/.env.example`:

```bash
# App
APP_ENV=local                 # local | staging | production
LOG_LEVEL=INFO
CORS_ALLOWED_ORIGINS=http://localhost:3000

# Auth (provider undecided; see docs/02-DESIGN-DOC.md section 16, U1)
AUTH_MODE=dev                 # dev works only when APP_ENV=local; use jwt elsewhere
AUTH_ISSUER=
AUTH_AUDIENCE=
AUTH_JWKS_URL=

# PostgreSQL (server-side only)
DATABASE_URL=                 # postgresql+<driver>://user:password@host:5432/dbname (driver confirmed in Stage 1)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5

# Gemini (Google AI Studio)
GEMINI_API_KEY=
GEMINI_MODEL_FAST=            # exact ID from AI Studio
GEMINI_MODEL_STRONG=          # exact ID from AI Studio
GEMINI_EMBEDDING_MODEL=gemini-embedding-001   # confirm current ID in AI Studio
EMBEDDING_DIM=768             # must equal the Qdrant collection vector size
GEMINI_MAX_CONCURRENCY=2
LLM_MIN_INTERVAL_MS=2000      # tune from the limits shown in AI Studio
EMBED_MIN_INTERVAL_MS=700
LLM_ENABLED=true              # global kill switch

# Qdrant (server-side only; API key can be empty for local Docker)
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=knowledge
```

`apps/web/.env.example`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000    # public, contains no secret
# Auth library settings (names depend on the provider chosen in U1); server-only, never NEXT_PUBLIC_
AUTH_SECRET=
```

Never commit `.env`, `.env.local` or any file with real values. Only the `.env.example` files (with empty values) belong in the repo. Provider keys, database URLs and the Qdrant key exist only on the API side.

### Everyday commands

| Where | Command | Purpose |
|---|---|---|
| `apps/api` | `python -m uvicorn research_desk.main:app --reload --port 8000` | run the API |
| `apps/api` | `python -m ruff check . && python -m ruff format --check .` | lint and format check |
| `apps/api` | `python -m mypy src` | type check (checker choice is an assumption, U11) |
| `apps/api` | `python -m pytest` | backend tests (integration tests need `docker compose up -d postgres qdrant`) |
| `apps/api` | `python -m alembic upgrade head` | apply PostgreSQL migrations |
| `apps/web` | `npm run dev` | run the frontend |
| `apps/web` | `npm run typecheck` / `npm run lint` / `npm test` | frontend checks (Vitest) |
| repository root | `docker compose up -d postgres qdrant` | start local data services |

## Project structure

```
apps/
  web/                         # Next.js frontend
    src/app/                   # pages and layouts (no API routes for business logic)
    src/components/            # UI components
    src/lib/                   # api client, ndjson reader, runner, trace store, zod schemas, config
    tests/                     # Vitest
  api/                         # FastAPI backend
    pyproject.toml requirements.txt requirements-dev.txt # pip dependencies
    alembic/                   # PostgreSQL migrations
    src/research_desk/
      main.py                  # app factory
      api/                     # routers, dependencies (auth, ownership), error handlers, middleware
      core/                    # config, ids, schemas (Pydantic), errors, logging
      agents/                  # collector.py analyst.py critic.py writer.py prompts.py citations.py
      orchestrator/            # pipeline.py jobs.py runner.py events.py
      ingest/                  # pdf.py url.py ssrf.py text.py clean.py chunk.py
      providers/               # llm.py embeddings.py gemini.py limits.py
      stores/                  # vector.py (Qdrant), db.py, repos/ (PostgreSQL)
    scripts/                   # migrate_qdrant.py spike_db.py spike_llm.py spike_stream.py reconcile.py
    tests/                     # Pytest
contracts/                     # shared JSON fixtures validated by Pytest and Vitest
docs/                          # all planning documents
docker-compose.yml             # postgres, qdrant (and optional api, web profile)
AGENTS.md  GEMINI.md           # always-on context for the coding agent
```

## Deployment

Frontend and backend deploy independently; the API is a container. Hosts are not chosen yet. See `docs/02-DESIGN-DOC.md` section 11 (deployment) and section 13 (production requirements) and the release checklist in `docs/07-BUILD-PLAN-AND-CHECKLIST.md`.

## Documentation

| File | Purpose |
|---|---|
| `AGENTS.md` | Always-loaded project context and rules for Antigravity |
| `docs/01-PRD.md` | What we are building and why, scope, acceptance criteria |
| `docs/02-DESIGN-DOC.md` | Architecture, diagrams, adapter contracts, config, security, UI spec, deployment, production requirements, bottleneck register, decision log, open decisions |
| `docs/03-DATABASE-SCHEMA.md` | PostgreSQL and Qdrant design, IDs, query recipes, consistency, Day-1 spikes |
| `docs/04-AGENT-SPECS.md` | Each agent's module contract, algorithm, prompts and Pydantic schemas |
| `docs/05-API-SPEC.md` | Endpoints, errors, streaming event format, jobs and recovery |
| `docs/06-ANTIGRAVITY-INSTRUCTIONS.md` | Stage-by-stage prompts for the coding agent |
| `docs/07-BUILD-PLAN-AND-CHECKLIST.md` | Day plan, testing, demo, production readiness and release checklist |
| `docs/08-MIGRATION-SUMMARY.md` | What changed in the move to the Python architecture, decisions, conflicts, open questions |

## Known limits

- Scanned PDFs without a text layer are not supported (use "paste text" instead).
- Two-column PDFs can extract with imperfect reading order.
- Gemini quotas limit how many sources can be processed per day, and limits are per API instance in v1.
- v1 runs one API instance; horizontal scaling needs the steps in `docs/02-DESIGN-DOC.md` section 14.
- A free Qdrant cluster may pause when idle and need to be resumed; the index can be rebuilt from PostgreSQL.
- Conflict labels are produced by an LLM and can be wrong; the UI shows the rationale so you can judge.
- Source text is sent to Google's Gemini API; confirm the current data-use terms for your tier.
