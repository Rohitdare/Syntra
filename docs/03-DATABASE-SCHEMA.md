# Database Schema: PostgreSQL and Qdrant

Version 0.4 | Two stores. **PostgreSQL** is the system of record for application data. **Qdrant** (open source; local Docker or a cloud cluster) is the semantic search index and shared evidence memory for chunks and claims. This replaces the earlier single-collection design in which every record type, including projects, sources, verdicts and briefs, lived in Qdrant behind placeholder vectors. Section numbers 1-11 keep their earlier meaning; sections 12-14 are new.

## 1. Model

- Logical record types are unchanged: `project`, `source`, `chunk`, `claim`, `verdict`, `brief`. What changed is where each lives.
- Rule of thumb: if a record is searched by similarity it is in Qdrant (and, where it cannot be regenerated cheaply, also in PostgreSQL); everything else is only in PostgreSQL.

| Record | PostgreSQL | Qdrant | Why |
|---|---|---|---|
| project | System of record (`projects`) | no | Ownership, status, counters; no vector needed |
| source | System of record (`sources`) | no | Stage flags and tags need transactions; no vector needed |
| source text | System of record (`source_texts`) | no | Rebuild source for chunks; Analyst input; PDFs themselves are never stored |
| chunk | no (derived: re-chunk from `source_texts`) | Point with embedding and text payload | Searched by similarity; deterministic chunker means it can be regenerated |
| claim | System of record (`claims`) | Point with embedding and payload copy | LLM output is not reproducible, so keep it in PostgreSQL; Qdrant copy serves similarity search |
| verdict | System of record (`verdicts`) | no | Relationship between two claims; queried by label, confidence and claim keys; no vector needed |
| brief | System of record (`briefs`) | no | Stored answer; no vector needed |
| job, job event, usage, user, app metadata | System of record | no | Operational data |

- Because only chunks and claims are points, **placeholder vectors no longer exist.** The rule remains: every similarity search MUST filter on `type` and `projectId`.
- Qdrant payloads are denormalized for retrieval (claim points carry text, tag and source ID) so the Writer needs no joins for snippets. Hits are then validated against PostgreSQL (section 13).
- PostgreSQL rows that relate claims (verdicts) denormalize both claim texts and source tags, so the Conflicts view needs no joins beyond the project filter.

Verify against the official Qdrant docs and the Qdrant Python client docs before coding: creating collections and aliases, payload indexes (including any tenant-style index option), upsert with wait semantics, filtered query with `must` / `must_not`, `score_threshold`, batched queries, scroll, retrieve by ID with vectors, delete by filter, counting. Do not guess method names; the older "search" methods may be superseded in current client versions. Verify SQLAlchemy 2 async, Alembic and the PostgreSQL driver the same way.

## 2. Collection setup (Qdrant)

| Item | Value |
|---|---|
| Collection | `knowledge` (name from env `QDRANT_COLLECTION`), addressed through an alias so it can be swapped (section 3) |
| Vector size | 768 (`EMBEDDING_DIM`); cannot change later without re-embedding |
| Distance | Cosine. Search scores are cosine **similarity** (higher = closer). |
| Payload indexes | `type`, `projectId`, `sourceId`, all keyword type. (`label` is no longer a Qdrant field; verdicts are in PostgreSQL.) Create them in the migration script. Use the tenant-style option for `projectId` if the client version supports it (U14, spike S1/S3). |
| Placeholder vector | Not used |

`scripts/migrate_qdrant.py` creates the collection, indexes and alias if they do not exist (idempotent).

## 3. Embeddings

| Item | Value |
|---|---|
| Model | `gemini-embedding-001` via the Gemini API. Confirm the current ID in AI Studio. |
| Dimension | 768 (set the output dimensionality; must match the collection) |
| Task types | `RETRIEVAL_DOCUMENT` for chunks and claims; `RETRIEVAL_QUERY` for questions |
| What is embedded | Only `chunk.text` and `claim.text` |
| Batching | Many texts per request (find the maximum in spike S2) to protect the quota |
| Input limit | About 2,048 tokens per text; chunks stay well below |
| Pinning | `app_meta` stores `embedding_model`, `embedding_dim`, `qdrant_collection`, `qdrant_schema_version`; startup fails if configuration disagrees |
| Changing models | Create a new collection (for example `knowledge_v2`), re-embed from PostgreSQL (`source_texts` and `claims`) into it, switch the alias, retire the old collection. Never mix models in one collection. Every chunk and claim payload records `embeddingModel` to make mixed data detectable. |

## 4. IDs

- Readable **key** per record: `prj_<8hex>`, `src_<8hex>`, `chk_<src8>_<nnn>`, `clm_<src8>_<nn>`, `vrd_<8hex>`, `brf_<8hex>`. Keys are stored in PostgreSQL primary keys and in `payload.key`.
- `<8hex>` = first 8 hex characters of a SHA-1 of the stated input. Source keys hash `projectId + content hash` (same content in the same project = same source). Verdict keys hash the **sorted** pair of claim keys (each unordered pair judged once). Brief keys hash `projectId + normalized question` (trimmed, internal whitespace collapsed; same question in the same project overwrites the previous brief). Project keys are random 8-hex values generated on create; the insert retries on the rare unique-key conflict.
- **Uniqueness is per project (changed).** Except for `prj_`, keys are only unique within a project, so PostgreSQL primary keys are `(project_id, key)`. Qdrant point IDs must be unsigned integers or UUIDs, so **point ID = UUIDv5(fixed namespace UUID, `<projectId>:<key>`)**. Same project and key always give the same point ID, so every write is an idempotent upsert, and two projects can never overwrite each other's points even if 8-hex keys collide.
- Within one project the caps keep key counts small (at most 8 sources, 64 claims, 2,016 claim pairs), so 8 hex characters are adequate; if caps rise substantially, widen the hash (U13).
- Implement in `core/ids.py`: `short_hash`, `key_to_point_id(project_id, key)`, key builders, `pair_key`, `normalize_question`. Unit-test determinism and order independence.

## 5. Record types

Common to every record: `key`, `type`, `projectId`, `createdAt`, `createdBy` (`api`, `collector`, `analyst`, `critic`, `writer`), `schemaVersion` (1). In PostgreSQL these are columns (`id`, `project_id`, `created_at`, `created_by`, `schema_version` where useful); in Qdrant they are payload fields. Field names below use the wire/payload camelCase; PostgreSQL columns are snake_case.

### `project` (PostgreSQL `projects`)
`key` (id), `ownerId`, `name`, `description?`, `status` (`active`, `deleting`), `nextSourceTag` (counter, starts at 1), `createdAt`, `updatedAt`.

### `source` (PostgreSQL `sources`)
| Field | Notes |
|---|---|
| `sourceId` | same as `key` |
| `tag` | `S1`, `S2`... unique per project; allocated from `projects.nextSourceTag` under a row lock; never reused, even after a source is deleted |
| `kind` | `pdf`, `url`, `text` |
| `title`, `origin` | origin = filename, URL or `pasted` |
| `contentHash` | hash of cleaned text; unique per project |
| `charCount`, `pageCount?`, `chunkCount`, `claimCount` | numbers |
| `summary`, `topics[]` | written by the Analyst |
| `stageCollected`, `stageAnalyzed`, `stageCritiqued` | booleans (unchanged meaning; true only when all derived data in both stores is durable) |
| `lastError?` | user-safe code of the last failed stage, cleared on success |

### `source text` (PostgreSQL `source_texts`, new)
`sourceId`, `text` (cleaned), `pageOffsets[]` (start offset of each page in `text`; empty for non-PDF), `chunkerVersion`. Separate table so listing sources never loads large text.

### `chunk` (Qdrant point only)
Payload: `sourceId`, `chunkIndex`, `pageStart?`, `pageEnd?`, `text`, `embeddingModel`, `chunkerVersion`. Vector: embedding of `text`.

### `claim` (PostgreSQL `claims` and Qdrant point)
PostgreSQL: `sourceId`, `claimIndex`, `text`, `textHash`, `importance` (1-5), `pageHint?`, `embeddingModel`. Qdrant payload (copy): `sourceId`, `sourceTag`, `claimIndex`, `text`, `importance`, `pageHint?`, `embeddingModel`. Vector: embedding of `text`. PostgreSQL is authoritative; the Qdrant copy is written after the PostgreSQL row.

### `verdict` (PostgreSQL `verdicts`)
`claimKeyA`, `claimKeyB`, `sourceIdA`, `sourceIdB`, `sourceTagA`, `sourceTagB`, `claimTextA`, `claimTextB`, `label` (`supports`, `contradicts`, `nuances`, `unrelated`), `confidence` (0-1), `rationale`, `similarity`. A = claim from the newly critiqued source. Foreign keys to both claims with `ON DELETE CASCADE`, so removing or replacing a claim removes its verdicts.

### `brief` (PostgreSQL `briefs`)
`question`, `answerMarkdown`, `json` (validated Writer output as `jsonb`), `sourceIds[]`.

## 6. Who reads and writes what

| Type | Collector | Analyst | Critic | Writer | API routes |
|---|---|---|---|---|---|
| project | | | | | W (create), R, list, mark deleting, delete |
| source | W (PG) | update summary, topics, flags, counts (PG) | update flag (PG) | R (tags, titles, flags; PG) | R, delete |
| source text | W (PG) | R (PG) | | | |
| chunk | W (Qdrant) | | | R (similarity; Qdrant) | |
| claim | | W (PG, then Qdrant) | R (PG rows; own vectors and similarity from Qdrant) | R (similarity from Qdrant; validated against PG) | R (PG) |
| verdict | | | W, R (skip judged; PG) | R (PG) | R (PG) |
| brief | | | | W (PG) | R (PG) |
| job, job event, usage | | | | | W by job service and providers; R |

## 7. Query recipes

Qdrant filters use `must` / `must_not` / `should` with `match` conditions. Build filters and SQL only from validated IDs and fixed enums, never from raw user text. Every Qdrant call includes `projectId` (and `type`).

| # | Used by | Store | Operation |
|---|---|---|---|
| Q1 | Admin / reconcile | Qdrant | scroll points: `must` type = chunk, sourceId = S. Sort by `chunkIndex` in code. (The Analyst no longer needs this: it reads `source_texts` from PostgreSQL.) |
| Q2 | Critic | PostgreSQL + Qdrant | (a) load the source's claims from PostgreSQL; (b) fetch their vectors from Qdrant (scroll or retrieve by point ID, `with_vectors`); (c) ONE batched query request with one query per claim vector: `must` type = claim, projectId = P; `must_not` sourceId = S; limit `CRITIC_TOP_K`; score threshold = `CRITIC_MIN_SIMILARITY`. Hits are validated against PostgreSQL claims (hits with no PostgreSQL row are dropped). |
| Q3 | Critic | PostgreSQL | `SELECT key FROM verdicts WHERE project_id = :p AND key = ANY(:keys)` to find pairs already judged |
| Q4 | Writer | Qdrant | query with the question embedding: `must` type = chunk, projectId = P; limit `WRITER_TOP_CHUNKS`; then drop hits whose source is missing or not `stageCollected` in PostgreSQL |
| Q5 | Writer | Qdrant | same on type = claim; limit `WRITER_TOP_CLAIMS`; drop hits whose source is missing or not `stageAnalyzed`, or whose claim has no PostgreSQL row |
| Q6 | Writer | PostgreSQL | verdicts for project P with label in (`contradicts`, `nuances`); order by confidence; prefer verdicts whose claim keys appear in the Q5 results; keep `WRITER_MAX_CONFLICTS` |
| Q7 | API | PostgreSQL | list sources for project P ordered by tag number; the tag counter replaces "compute next tag by scanning" |
| Q8 | API | PostgreSQL | verdicts as Q6 with a larger limit for the Conflicts view; rows already contain both claim texts and tags |
| Q9 | API delete | PostgreSQL + Qdrant | mark project `deleting`; delete Qdrant points by filter projectId = P (and by sourceId for a single source); then delete PostgreSQL rows (cascade) |
| Q10 | any stage | PostgreSQL | update a few columns (stage flags, counts) in a transaction; Qdrant payload patches are not needed because Qdrant stores no mutable state |

Qdrant scroll returns pages; follow the next-page token until done.

## 8. Day-1 spikes (prove these before building on them)

Write scripts under `apps/api/scripts/` (`spike_db.py`, `spike_llm.py`, `spike_stream.py`) and record the answers at the bottom of this file. Spikes S1-S6 keep their earlier intent; S7-S10 are new.

| ID | Question | If "no" |
|---|---|---|
| S1 | Can we connect to PostgreSQL and Qdrant (local Compose and cloud), run Alembic migrations, create the Qdrant collection, payload indexes and alias? Is a tenant-style index available for `projectId`? | Fix URL/key; use local Compose for dev; check cluster status; fall back to a plain keyword index |
| S2 | Does `gemini-embedding-001` return 768 dimensions, and what is the maximum number of texts per request? | Reduce batch size; fall back to a local embedding model (changes the vector size) |
| S3 | Does filtered query with `must` + `must_not` + score threshold work, and does the batched query work with filters? | One query per claim with small concurrency |
| S4 | What cosine scores do related, contradicting and unrelated sentence pairs give? | Tune `CRITIC_MIN_SIMILARITY` on the demo corpus |
| S5 | Is upsert with a project-scoped UUIDv5 ID idempotent? Do scroll with filters, retrieve with vectors, count, and delete-by-filter work? | Adjust the adapter |
| S6 | What are the real embedding and LLM quotas in AI Studio? How much cluster memory/disk does a processed 10-page paper use? | Larger chunks, caps, per-user budgets from the measured values |
| S7 | Does Gemini structured output accept a schema derived from the Pydantic models, and how often does output still fail validation? | Simplify schemas, rely on prompt plus validation and retry, raise `LLM_MAX_RETRIES` |
| S8 | Which PDF extraction library gives acceptable text on 3 real papers (single and two-column), with page numbers, speed, memory and an acceptable licence? Does a thread suffice, or is a subprocess needed to time-box it? | Pick another library; use a subprocess with a hard timeout |
| S9 | Does an NDJSON stream with heartbeats survive the chosen hosts and proxies (no buffering, idle timeout), and does a detached job survive a client disconnect? | Shorter heartbeat, resumable polling endpoint, same-origin proxy settings, different host |
| S10 | Under concurrent requests, are source tags unique and gap-free per project, and does the active-job unique index stop duplicate jobs? | Adjust locking (row lock vs advisory lock) |

### Spike results (fill in)

```
S1:
S2:
S3:
S4:
S5:
S6:
S7:
S8:
S9:
S10:
```

## 9. Data lifecycle

- Deleting a project: PostgreSQL status `deleting` (hides it, blocks new jobs, cancels or lets finish running jobs), then Qdrant delete by `projectId` (Q9), then PostgreSQL delete with cascade. If a step fails the project stays `deleting` and `reconcile` completes it.
- Deleting a source: cascade removes its claims and verdicts in PostgreSQL; Qdrant points for that `sourceId` are deleted; its tag is not reused.
- Re-running a stage overwrites rows and points with the same IDs, then prunes stale higher-index points. Re-running `analyze` replaces claims and, by cascade, removes verdicts that referenced them; `stageCritiqued` becomes false until `critique` is run again (decision D13).
- PDFs are parsed in a temporary file or memory and discarded; only extracted text, embeddings and derived data are stored.
- `job_events` older than a retention period (value TBD, U15) are purged; `usage_ledger` is kept as long as budgets or billing need it.

## 10. Capacity and free-tier notes

- A 768-dimension float vector is about 3 KB (768 x 4 bytes, arithmetic). A typical project (up to 8 sources of about 30 chunks, plus up to 64 claims) is a few hundred vectors, roughly 1 MB of raw vectors before index overhead; measure real usage in S6. The number of projects is what grows; plan quantization or larger clusters only after measurements (`02-DESIGN-DOC.md` section 14, B9).
- Qdrant Cloud's free cluster is small (about 1 GB RAM, 4 GB disk, single node; confirm current limits in the Qdrant Cloud console).
- A free cluster may pause after a period of inactivity and need a manual resume. See the design doc for keep-alive options. Because Qdrant is rebuildable from PostgreSQL, losing it is an embedding-cost event, not a data-loss event.
- PostgreSQL volume is dominated by `source_texts` (up to `MAX_EXTRACTED_CHARS` per source). Large text lives in a separate table so list queries stay fast.
- Local Docker has no such limits and is the recommended development setup.

## 11. If you switch stores later

Everything outside `stores/vector.py` depends only on the `VectorStore` protocol, and everything outside `stores/repos/` depends only on the repository protocols (`02-DESIGN-DOC.md` section 5). A pgvector variant would implement `VectorStore` on PostgreSQL, replacing the Critic's batched query with a lateral-join query; PostgreSQL would then hold both roles. This is not planned.

## 12. PostgreSQL tables (sketch)

Exact types and indexes are fixed in the first Alembic migration (Stage 1) and the migration becomes the source of truth; update this section if they differ. Primary keys below; all `project_id` references cascade on project delete.

| Table | Primary key | Main columns and constraints |
|---|---|---|
| `users` | `id` uuid | `auth_subject` unique, optional `email` (store only what the provider requires; U1), `created_at` |
| `projects` | `id` text (`prj_...`) | `owner_id` fk users, `name`, `description`, `status` check (`active`,`deleting`), `next_source_tag` int default 1, timestamps; index on `owner_id` |
| `sources` | (`project_id`, `id`) | `tag`, `kind`, `title`, `origin`, `content_hash`, counts, `summary`, `topics` text[], three stage booleans, `last_error`, timestamps; unique (`project_id`,`tag`); unique (`project_id`,`content_hash`) |
| `source_texts` | (`project_id`, `source_id`) | `text`, `page_offsets` int[], `chunker_version`; fk to sources cascade |
| `claims` | (`project_id`, `id`) | `source_id`, `claim_index`, `text`, `text_hash`, `importance`, `page_hint`, `embedding_model`; fk (`project_id`,`source_id`) cascade; unique (`project_id`,`source_id`,`claim_index`) |
| `verdicts` | (`project_id`, `id`) | `claim_key_a`, `claim_key_b` (fks to claims, cascade), source ids and tags, both claim texts, `label` check, `confidence` check 0-1, `rationale`, `similarity`, timestamps; index (`project_id`,`label`,`confidence` desc) |
| `briefs` | (`project_id`, `id`) | `question`, `answer_markdown`, `json` jsonb, `source_ids` text[], timestamps |
| `jobs` | `id` uuid | `project_id`, `source_id` nullable, `user_id`, `stage`, `status` check (`queued`,`running`,`succeeded`,`failed`), `idempotency_key` (unique with `user_id` when present), `input_hash`, `attempt`, `error_code`, `error_message`, `result` jsonb, `worker_id`, `lease_expires_at`, `created_at`, `started_at`, `finished_at`; **partial unique index** on (`project_id`,`stage`,`coalesce(source_id,'')`,`input_hash`) where status in (`queued`,`running`) for single-flight; index on (`status`,`lease_expires_at`) for the recovery sweep |
| `job_events` | (`job_id`, `seq`) | `ts`, `stage`, `agent`, `type`, `message`, `data` jsonb; `seq` is a per-job counter |
| `usage_ledger` | `id` bigserial | `user_id`, `project_id`, `job_id`, `provider`, `model`, `kind` (`llm`,`embed`), `tokens_in`, `tokens_out`, `texts`, `created_at`; index (`user_id`,`created_at`) |
| `app_meta` | `key` text | `value` text; embedding model, dimension, Qdrant collection and schema version |

`jobs.input` is not stored; large inputs (pasted text, PDF bytes) never go into job rows. Small non-secret parameters (kind, title, URL without credentials) are recorded in `result` or `data` fields as needed.

## 13. Consistency between PostgreSQL and Qdrant

The two stores cannot share a transaction. The design avoids needing one.

### Invariants
- I1. PostgreSQL decides what exists. A Qdrant point is meaningful only if its project, source and (for claims) claim row exist in PostgreSQL.
- I2. A stage flag (`stageCollected`, `stageAnalyzed`) becomes true only after all derived data for that stage is durable in both stores.
- I3. Qdrant writes wait for acknowledgement (use the client's wait-for-result option; confirm in S5) before the flag is set.
- I4. Point IDs are deterministic and project-scoped, so repeating a write is harmless.
- I5. Deletes are tombstoned in PostgreSQL first.
- I6. Re-analysis invalidates dependent verdicts (cascade) in the same PostgreSQL transaction that replaces the claims.
- I7. Embedding model and dimension are pinned in `app_meta` and recorded in payloads.

### Write order per stage

| Stage | Order | Failure windows and result |
|---|---|---|
| collect | 1) PostgreSQL transaction: allocate tag (project row lock), upsert `sources` (flags false) and `source_texts`. 2) embed chunks. 3) upsert Qdrant chunk points. 4) prune chunk points with `chunkIndex` >= new count. 5) PostgreSQL: `chunkCount`, `stageCollected = true`. | Crash after 1: source exists with flags false; retry resumes the same source (same content hash). Crash after 3: points exist, flag false; retry overwrites. Source is not used by retrieval until the flag is true. |
| analyze | 1) read `source_texts`. 2) LLM call. 3) embed claims. 4) PostgreSQL transaction: replace claims (cascade verdicts), update summary, topics, title, set `stageAnalyzed = false`, `stageCritiqued = false`. 5) upsert Qdrant claim points; prune higher indexes. 6) PostgreSQL: `claimCount`, `stageAnalyzed = true`. | Crash after 4: PostgreSQL has new claims, Qdrant has old or partial points, flag false; retry completes. Retrieval ignores claims of sources whose flag is false (post-filter). |
| critique | read claims (PostgreSQL), vectors and neighbors (Qdrant), judged keys (PostgreSQL), LLM call, then ONE PostgreSQL transaction: upsert verdicts and `stageCritiqued = true`. Qdrant is read-only. | Crash before the transaction: nothing written; retry repeats the LLM call. Verdicts written by an earlier partial run are skipped on retry. |
| ask | read-only on Qdrant; write the brief to PostgreSQL. | Nothing partial. |
| delete project | 1) PostgreSQL `status = 'deleting'`. 2) Qdrant delete by `projectId`. 3) PostgreSQL delete (cascade). | Failure leaves `deleting`; reconcile finishes it. |
| delete source | 1) PostgreSQL delete in a transaction (cascades claims and verdicts) and keep the tag counter. 2) Qdrant delete by `sourceId`. | If step 2 fails, orphan points are invisible (post-filter) and removed by reconcile. |

### Retrieval post-filter (decision D16)
Writer and Critic discard Qdrant hits whose source or claim is absent in PostgreSQL, or whose source lacks the required stage flag. This makes half-finished or orphaned points harmless to users.

### Reconciliation (`scripts/reconcile.py`, Stage 7)
Safe to run repeatedly. It (a) completes projects stuck in `deleting`; (b) compares, per source, PostgreSQL `chunkCount` and `claimCount` with Qdrant counts and reports mismatches, optionally repairing by re-running the stage's write steps; (c) finds Qdrant points whose `projectId` or `sourceId` no longer exist in PostgreSQL and deletes them (method for enumerating project IDs in Qdrant is to be chosen from the client's capabilities; it can be slow and runs off-peak); (d) verifies `app_meta` against configuration.

### Rebuild (`rebuild_index`, procedure documented in Stage 8; implement only if needed)
For each source in PostgreSQL: re-chunk `source_texts` with the recorded `chunkerVersion`, embed, upsert, prune; for each claim row: embed, upsert. Costs embedding quota only. Use it after Qdrant loss, after restoring PostgreSQL to a different point in time, or for an embedding-model migration into a new collection.

## 14. Migrations and backups

- **PostgreSQL migrations:** Alembic, one linear history, reviewed. Expand/contract. A migration adding a constraint on existing data first backfills. Down-migrations are optional; prefer forward fixes. CI runs `upgrade head` on an empty database and checks that models and migrations agree.
- **Qdrant migrations:** `migrate_qdrant.py` is idempotent and only adds; destructive changes use a new collection plus alias swap. `schemaVersion` in payloads allows readers to handle older shapes.
- **Order during a release:** run PostgreSQL migration, run Qdrant migration if any, deploy the API, deploy the web app. Backward-compatible changes allow any of these to be rolled back independently.
- **Backups:** PostgreSQL automated backups with a restore test (`07-BUILD-PLAN-AND-CHECKLIST.md` section 7); Qdrant snapshots or rebuild-only (U9). Backups of `source_texts` contain user content; protect and expire them under the retention policy (U15).
