# Product Requirements Document: Research Desk

Version 0.3 | Solo builder | Status: draft. The hackathon is no longer a constraint; this is a standalone portfolio project. Version 0.3 moves the target architecture to a Python backend (FastAPI) with PostgreSQL and Qdrant, and adds the authentication, ownership and operational requirements needed to run it for real users. Product vision, agent roles and acceptance criteria are unchanged unless marked "(changed in 0.3)" or "(new in 0.3)".

## 1. Summary

Research Desk is a web app where a small team of AI agents reads the sources you give it (PDFs, URLs, pasted text), stores what it learns in a shared evidence memory (Qdrant for semantic retrieval, PostgreSQL for the system of record), finds where the sources agree or disagree, and writes a cited briefing that answers your question.

## 2. Problem

When you read several papers or articles on one topic, two things are hard: remembering what each source actually claims, and noticing where sources quietly disagree (different results, different scope, different conclusions). Chat tools summarize one document at a time and rarely compare claims across documents with evidence you can check.

## 3. Target users

- **Primary:** students and early researchers reading 3-8 papers for an assignment, literature review or project.
- **Secondary:** analysts or curious readers comparing several articles on a debated topic.

## 4. Goals and non-goals

### Goals
- G1. Turn 3-8 sources into a searchable shared memory in minutes.
- G2. Surface agreements and conflicts across sources, with a short rationale for each.
- G3. Produce a briefing that cites its sources and states where they disagree and what is missing.
- G4. Make the agents' work visible (live trace) so the system is understandable and demo-able.
- G5. Run on free tiers during development and demo, and be easy to deploy. (changed in 0.3: free-first, not free-only; see section 5.)
- G6. Be a strong portfolio project: clean architecture, tests, clear README, live demo.
- G7. (new in 0.3) Be safe to run for more than one user: authenticated users, private projects, bounded cost, and a documented path to scale when load justifies it.

### Non-goals (v1)
- Multi-user collaboration, sharing, or team workspaces. (Projects are private to one owner.)
- Social login breadth, roles, organizations, billing or subscription plans. (changed in 0.3: a lightweight sign-in and project ownership are now IN scope; a full account-management system is not.)
- OCR for scanned PDFs.
- Citation formatting styles (APA etc.), reference manager integration.
- Fine-tuning or hosting our own LLM.
- A native mobile app (responsive web is enough).
- Microservices, a message broker or a separate worker fleet in v1. The architecture leaves seams for them (see `02-DESIGN-DOC.md` section 14); they are added only when measured load justifies them. (new in 0.3)

## 5. Constraints

- **Free-first:** development and the public demo target free tiers where they exist: local Docker for PostgreSQL and Qdrant, Gemini API free tier (LLM and embeddings), and free host tiers if a suitable one exists. Design for the limits (caps, batching, caching). (changed in 0.3: the architecture now needs a host for a long-running Python API and a PostgreSQL database. Free-tier availability and limits for those are NOT verified; see open question 4 and `02-DESIGN-DOC.md` section 16.)
- Stack is fixed: Next.js, React, TypeScript and Tailwind for the frontend; Python and FastAPI for the backend; Gemini API for LLM and embeddings; Qdrant for vectors; PostgreSQL for application data; Pydantic and Zod for validation; npm and uv for dependencies; Docker Compose for local development. (new in 0.3)
- Solo build, no fixed external deadline. Suggested target for v1: about 13 working days at 5-6 hours per day (estimate; re-baseline after Stage 1). (changed in 0.3: was about 10 days; PostgreSQL, authentication, jobs and security hardening add work.)
- Public GitHub repository intended as a portfolio piece.

## 6. Features and priority

| ID | Feature | Priority |
|---|---|---|
| F1 | Create / list / delete research projects | P0 |
| F2 | Add source by PDF upload | P0 |
| F3 | Add source by pasted text | P0 |
| F4 | Add source by URL (article extraction) | P1 |
| F5 | Per-source summary + key claims (Analyst) | P0 |
| F6 | Cross-source claim comparison with labels and rationale (Critic) | P0 |
| F7 | Conflicts view (contradicts / nuances) | P0 |
| F8 | Ask a question, get a cited briefing (Writer) | P0 |
| F9 | Live agent trace panel | P0 |
| F10 | Click a citation to see the source and the supporting claim | P1 |
| F11 | Re-run a stage for a source | P1 |
| F12 | Export the briefing as Markdown | P2 |
| F13 | Dark mode | P2 |
| F14 | Sign in; every project is private to its owner (new in 0.3) | P0 |
| F15 | Reload or reconnect during a running stage and still see its progress and result (new in 0.3) | P1 |
| F16 | Delete a single source, including its claims and conflicts (new in 0.3) | P1 |
| F17 | Per-user usage limits with a clear "limit reached" message (new in 0.3) | P1 |

## 7. User stories and acceptance criteria

**US-1 Create a project.** As a user I can create a project with a name so my sources are grouped.
- AC: after creating, I land on an empty project page with an "Add source" area.

**US-2 Add a PDF.** As a user I can upload a PDF paper.
- AC: PDFs up to the configured size limit are accepted; a text-based paper produces chunks and a source card within the time target.
- AC: a PDF with no extractable text shows a clear error and a "paste text instead" suggestion.
- AC: (new in 0.3) a file that is too large, not a PDF, password-protected, or over the page limit is rejected with a specific message before heavy processing.

**US-3 Add pasted text or a URL.**
- AC: pasted text of at least 500 characters is accepted with a user-provided title.
- AC: a public article URL is fetched server-side and its main text extracted; failures show a clear error with the paste fallback.

**US-4 See what the source says.** As a user I can open a source and read its summary and list of claims.
- AC: summary is 3-5 sentences; up to 8 claims, each understandable on its own.

**US-5 See conflicts.** As a user I can open a Conflicts view listing claim pairs from different sources labelled contradicts or nuances.
- AC: each item shows both claims, their sources, the label, a confidence value and a one-sentence rationale.
- AC: supports and unrelated pairs are hidden by default but viewable with a filter.

**US-6 Ask a question.** As a user I can ask a research question about my sources.
- AC: the briefing cites sources with tags (for example S1, S2) for every factual statement; unknown tags never appear.
- AC: it includes a "where sources disagree" section when relevant conflicts exist, and a "gaps" note when the sources do not fully answer the question.

**US-7 Watch the agents.** As a user I see a live feed of agent activity while a stage runs.
- AC: each event shows the agent name, what it did, and counts of records read or written; errors are shown in plain language.
- AC: (new in 0.3) if I reload the page or lose the connection while a stage runs, the trace and the stage result reappear without starting the stage again.

**US-8 Sign in and keep my work private.** (new in 0.3) As a user I sign in and see only my own projects.
- AC: requests without a valid session are rejected; opening another user's project, source or brief returns "not found", never its content.
- AC: deleting my project removes its data from PostgreSQL and Qdrant.

**US-9 Stay within limits.** (new in 0.3) As a user I am told clearly when I hit a size, count, rate or daily usage limit, and what to do next.
- AC: limit errors name the limit and, where relevant, when I can try again.

## 8. Main UX flow

Sign in -> Home (project list) -> Project page -> Add source (PDF / URL / text) -> pipeline runs stage by stage with trace -> source card appears -> repeat -> open Insights (claims and conflicts) -> Ask tab -> briefing.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | One 10-page PDF fully processed (collect, analyze, critique) in under 90 seconds; briefing in under 30 seconds (targets; depend on Gemini quotas; not yet measured) |
| Reliability | Every stage is idempotent (deterministic IDs, upserts); a failed stage can be retried without duplicating data; stage state survives an API restart |
| Consistency | PostgreSQL is the system of record; Qdrant is a rebuildable search index; documented write order and a reconciliation procedure keep them aligned (`03-DATABASE-SCHEMA.md` section 13) |
| Cost control | Hard caps on sources, claims and neighbors; batched LLM and embedding calls; per-user daily budgets; a global switch to disable LLM calls |
| Security | Authentication on every route except health; project ownership checked on every project route; secrets server-side only; `.env*` ignored by git; Qdrant filters and SQL built only from validated values; URL fetcher resistant to SSRF including DNS rebinding and redirects; upload type, size and page count validated; PDF parsing time-boxed |
| Privacy | Warn users that text is sent to Google's Gemini API; free-tier content may be used by Google to improve products (confirm current terms). Source text and prompts are never written to logs |
| Scalability | v1 runs as one API instance; scale-out is gated on measured signals and documented in `02-DESIGN-DOC.md` section 14 |
| Observability | Structured JSON logs with request and job IDs; metrics for stage duration, provider errors, queue depth and cost; health endpoints |
| Recoverability | Automated PostgreSQL backups, Qdrant snapshots or index rebuild from PostgreSQL, tested restore (see `07-BUILD-PLAN-AND-CHECKLIST.md` section 7) |
| Accessibility | Keyboard-usable controls, visible focus, colour is never the only signal for conflict labels |
| Error handling | No raw stack traces in the UI; every error maps to a message and a next step |

## 10. Success metrics

| ID | Metric | Target |
|---|---|---|
| M1 | Full flow works on the demo corpus in consecutive runs | 5 of 5 |
| M2 | Critic surfaces genuine contradictions or nuances on the demo corpus | at least 3 |
| M3 | Briefing statements carry valid citations | 100% of factual sentences |
| M4 | Fresh clone runs locally by following the README | works first try |
| M5 | Secrets in the repo or git history | 0 |
| M6 | Live demo reachable and a 2-3 minute demo video or GIF recorded | done |
| M7 | Cross-user isolation tests (read, delete, ask, stream another user's data) | 100% pass (new in 0.3) |
| M8 | Restore drill: PostgreSQL restored from backup and the search index reconciled or rebuilt | completed once before release (new in 0.3) |

## 11. Portfolio value

| What a reviewer sees | Evidence in the project |
|---|---|
| Multi-agent design, not just a chat wrapper | Four Python agent modules with explicit inputs and outputs, communicating through a shared evidence memory |
| Practical vector search | Qdrant filtered similarity search (claims from other sources, per project) with score thresholds and batch queries |
| Engineering quality | Typed provider adapters, Pydantic-validated LLM output, idempotent writes, contract tests shared by Pytest and Vitest, rate-limit handling |
| Production thinking | Auth and ownership, SSRF defence, cost caps, job and event persistence, documented bottlenecks and scale-out triggers |
| Product thinking | Conflict-aware research, live trace, honest "gaps" in answers |
| Deployability | Docker Compose locally; independently deployable frontend and backend with a documented path to production |

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM or embedding free-tier quota exhausted | Demo fails | Batch calls, central provider adapter with shared limiter, per-user budgets, check real limits in AI Studio on day 1, keep an alternative provider possible behind the adapters, option of a local embedding model |
| False conflicts from the Critic | Loses trust | Conservative prompt, `nuances` label for scope differences, show rationale and confidence, tune on the demo corpus |
| PDF extraction quality (columns, noise) | Poor claims | Clean text, strip references, test 2-3 real papers early, allow paste fallback |
| Hostile or oversized PDF or URL | Resource exhaustion, SSRF | Size, page and time limits; parse off the event loop; SSRF guard with pinned IPs |
| Free Qdrant cluster pauses when idle or fills up | App looks broken | Keep-alive job or clear "database unavailable" message; local Docker for development; cap sources; index can be rebuilt from PostgreSQL |
| PostgreSQL and Qdrant drift apart | Missing or ghost evidence | Write order, post-filtering of retrieval hits against PostgreSQL, reconcile script (new in 0.3) |
| Long-running stages tied to HTTP requests | Lost work on disconnect or restart | Jobs run detached from the request; state and events persisted; interrupted jobs are marked and retryable (new in 0.3) |
| Cost runaway from abuse or bugs | Unexpected bill, quota exhaustion | Auth, rate limits, per-user daily budgets, global kill switch (new in 0.3) |
| Scope creep, including premature infrastructure | Unfinished app | Cut order defined in `07-BUILD-PLAN-AND-CHECKLIST.md`; scale-out only on measured triggers |

## 13. Open questions (resolve in the first spikes)

1. Do the Qdrant Python client, filters, batched queries and score thresholds behave as the schema doc assumes (spikes S1, S3, S5)?
2. What are the real embedding and LLM limits shown in AI Studio, and what is the maximum batch size for embeddings (S2, S6)?
3. What similarity threshold separates related from unrelated claims for the chosen embedding model (S4)?
4. Which hosts will run the frontend, the API and PostgreSQL, what do they cost, and what are their upload-size, idle-timeout and streaming behaviors (S9)?
5. Which authentication provider will issue sessions or tokens (`02-DESIGN-DOC.md` section 16, U1)?
6. Which PDF extraction library gives acceptable quality, speed and licence terms (S8)?
7. Does Gemini structured output honour the Pydantic-derived schemas reliably enough (S7)?
