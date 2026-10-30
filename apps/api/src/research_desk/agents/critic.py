"""Critic agent implementation.

Per docs/04-AGENT-SPECS.md Section 3 and docs/09-STAGE-5-CRITIC-IMPLEMENTATION-PLAN.md:
- Precondition: source.stage_analyzed == True.
- Retrieves claim vectors from Qdrant for the analyzed source.
- Batched vector search (Q2) finds candidate similar claims from OTHER sources (must_not sourceId).
- Strict PostgreSQL post-filtering (D16): drops hits whose claim or source is missing or unanalyzed.
- Deduplication: generates order-independent pair keys (pair_id),
  filters out already-judged pairs (Q3).
- Zero candidates handling: sets stage_critiqued=True cleanly without calling LLM.
- 24-pair bound: evaluates top pairs by similarity up to CRITIC_MAX_PAIRS_PER_CALL.
- Strict LLM call: uses fast tier, validates pair IDs, drops fabricated/duplicate IDs.
- Single bounded retry: retries only missing pair IDs once.
- Partial failure: if pairs remain unevaluated or omitted, preserves valid verdicts and leaves
  stage_critiqued=False with PARTIAL_CRITIQUE error.
- Persists verdicts to PostgreSQL in atomic upsert.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from research_desk.agents.prompts import (
    CRITIC_SYSTEM_PROMPT,
    build_critic_user_prompt,
)
from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.core.ids import pair_id
from research_desk.core.schemas import (
    CriticCandidatePair,
    CriticInput,
    CriticOutput,
    CriticOutputSchema,
    CriticVerdict,
)
from research_desk.providers.llm import CallContext, LLMProvider
from research_desk.stores.models import Verdict
from research_desk.stores.repos.claims import ClaimRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.repos.verdicts import VerdictRepo
from research_desk.stores.vector import VectorStore


@dataclass(frozen=True)
class CriticRepos:
    """Repositories required by the Critic agent."""

    sources: SourceRepo
    claims: ClaimRepo
    verdicts: VerdictRepo


@dataclass(frozen=True)
class CriticDeps:
    """Injected dependencies for the Critic agent."""

    repos: Any  # Supports CriticRepos or any object with .sources, .claims, .verdicts
    vectors: VectorStore
    llm: LLMProvider
    cfg: Settings | None = None


Emit = Callable[[str, dict[str, Any] | None, str | None], Awaitable[None]]


@dataclass(frozen=True)
class _CandidatePairInfo:
    """Internal representation of a candidate pair connecting two claims."""

    candidate_pair: CriticCandidatePair
    claim_key_a: str
    claim_key_b: str
    source_id_a: str
    source_id_b: str
    source_tag_a: str
    source_tag_b: str
    claim_text_a: str
    claim_text_b: str
    similarity: float


async def run(
    inp: CriticInput,
    deps: CriticDeps,
    emit: Emit,
    ctx: CallContext,
) -> CriticOutput:
    """Execute the Critic agent workflow."""
    cfg = deps.cfg or get_settings()

    await emit("stage_start", None, "Starting cross-source claim critique...")

    # 1. Verify source existence and analysis completion
    source = await deps.repos.sources.get(inp.project_id, inp.source_id)
    if source is None:
        raise AppError(
            "NOT_FOUND",
            f"Source '{inp.source_id}' not found in project '{inp.project_id}'.",
        )
    if not source.stage_analyzed:
        raise AppError(
            "BAD_REQUEST",
            f"Source '{inp.source_id}' must be analyzed before critique.",
        )

    # 2. Retrieve the source's claims from PostgreSQL
    source_claims = await deps.repos.claims.list_by_source(inp.project_id, inp.source_id)
    if not source_claims:
        await deps.repos.sources.update_stage_flags(
            project_id=inp.project_id,
            source_id=inp.source_id,
            stage_critiqued=True,
            last_error=None,
        )
        if hasattr(deps.repos.sources, "session"):
            await deps.repos.sources.session.commit()
        await emit("step", None, "No claims extracted for this source; skipping critique.")
        output = CriticOutput(
            pairs_judged=0,
            supports=0,
            contradicts=0,
            nuances=0,
            unrelated=0,
            skipped_existing=0,
        )
        await emit("result", output.model_dump(by_alias=True), "Done")
        return output

    # 3. Retrieve claim vectors from Qdrant
    claim_vectors = await deps.vectors.get_claim_vectors(inp.project_id, inp.source_id)
    if not claim_vectors:
        await deps.repos.sources.update_stage_flags(
            project_id=inp.project_id,
            source_id=inp.source_id,
            stage_critiqued=True,
            last_error=None,
        )
        if hasattr(deps.repos.sources, "session"):
            await deps.repos.sources.session.commit()
        await emit("step", None, "No claim vectors indexed in vector store; skipping critique.")
        output = CriticOutput(
            pairs_judged=0,
            supports=0,
            contradicts=0,
            nuances=0,
            unrelated=0,
            skipped_existing=0,
        )
        await emit("result", output.model_dump(by_alias=True), "Done")
        return output

    # 4. Search for similar claims from other sources in ONE batched query (Query Q2)
    await emit("doc_read", {"count": len(claim_vectors)}, "Searching similar claims...")
    neighbors_list = await deps.vectors.find_similar_claims_from_other_sources(
        project_id=inp.project_id,
        source_id=inp.source_id,
        claims=claim_vectors,
        top_k=cfg.CRITIC_TOP_K,
        min_similarity=cfg.CRITIC_MIN_SIMILARITY,
    )

    # 5. Strict PostgreSQL Post-Filtering (Decision D16)
    all_project_claims = await deps.repos.claims.list_by_project(inp.project_id)
    claims_by_id = {c.id: c for c in all_project_claims}

    all_project_sources = await deps.repos.sources.list_by_project(inp.project_id)
    sources_by_id = {s.id: s for s in all_project_sources}

    # 6. Construct and deduplicate candidate pairs
    candidates: dict[str, _CandidatePairInfo] = {}

    for cn in neighbors_list:
        src_claim = claims_by_id.get(cn.claim_key)
        if src_claim is None:
            continue

        for hit in cn.neighbors:
            neighbor_claim = claims_by_id.get(hit.key)
            if neighbor_claim is None:
                # Discard hits not present in PostgreSQL claims
                continue

            if neighbor_claim.source_id == inp.source_id:
                # Discard claims from same source
                continue

            neighbor_source = sources_by_id.get(neighbor_claim.source_id)
            if neighbor_source is None or not neighbor_source.stage_analyzed:
                # Discard hits whose source is missing or unanalyzed
                continue

            # Deterministic ordering: claim_a.id <= claim_b.id
            if src_claim.id <= neighbor_claim.id:
                c_a, c_b = src_claim, neighbor_claim
                s_a, s_b = source, neighbor_source
            else:
                c_a, c_b = neighbor_claim, src_claim
                s_a, s_b = neighbor_source, source

            pid = pair_id(c_a.id, c_b.id)
            hit_score = float(hit.score)

            if pid in candidates:
                # Keep highest similarity if pair is hit from both directions
                if hit_score > candidates[pid].similarity:
                    candidates[pid] = _CandidatePairInfo(
                        candidate_pair=candidates[pid].candidate_pair,
                        claim_key_a=c_a.id,
                        claim_key_b=c_b.id,
                        source_id_a=s_a.id,
                        source_id_b=s_b.id,
                        source_tag_a=s_a.tag,
                        source_tag_b=s_b.tag,
                        claim_text_a=c_a.text,
                        claim_text_b=c_b.text,
                        similarity=hit_score,
                    )
            else:
                candidates[pid] = _CandidatePairInfo(
                    candidate_pair=CriticCandidatePair(
                        pair_id=pid,
                        source_tag_a=s_a.tag,
                        claim_text_a=c_a.text,
                        source_tag_b=s_b.tag,
                        claim_text_b=c_b.text,
                    ),
                    claim_key_a=c_a.id,
                    claim_key_b=c_b.id,
                    source_id_a=s_a.id,
                    source_id_b=s_b.id,
                    source_tag_a=s_a.tag,
                    source_tag_b=s_b.tag,
                    claim_text_a=c_a.text,
                    claim_text_b=c_b.text,
                    similarity=hit_score,
                )

    # 7. Deduplicate against already-judged pairs in PostgreSQL (Query Q3)
    candidate_pids = list(candidates.keys())
    judged_pids = await deps.repos.verdicts.get_judged_pair_keys(inp.project_id, candidate_pids)
    unjudged_candidates = [cand for pid, cand in candidates.items() if pid not in judged_pids]
    skipped_existing = len(judged_pids)

    await emit(
        "step",
        {
            "candidateCount": len(candidates),
            "unjudgedCount": len(unjudged_candidates),
            "skippedExisting": skipped_existing,
        },
        f"Found {len(candidates)} candidate pairs ({skipped_existing} already judged)",
    )

    # 8. Zero unjudged candidates handling
    if not unjudged_candidates:
        await deps.repos.sources.update_stage_flags(
            project_id=inp.project_id,
            source_id=inp.source_id,
            stage_critiqued=True,
            last_error=None,
        )
        if hasattr(deps.repos.sources, "session"):
            await deps.repos.sources.session.commit()

        msg = "No comparable claims found yet" if not candidates else "Done"
        output = CriticOutput(
            pairs_judged=0,
            supports=0,
            contradicts=0,
            nuances=0,
            unrelated=0,
            skipped_existing=skipped_existing,
        )
        await emit("result", output.model_dump(by_alias=True), msg)
        return output

    # 9. Enforce CRITIC_MAX_PAIRS_PER_CALL bound
    # Prioritize pairs with highest semantic similarity
    sorted_unjudged = sorted(unjudged_candidates, key=lambda c: c.similarity, reverse=True)
    max_pairs = cfg.CRITIC_MAX_PAIRS_PER_CALL
    if len(sorted_unjudged) > max_pairs:
        batch_to_evaluate = sorted_unjudged[:max_pairs]
        excess_candidates = sorted_unjudged[max_pairs:]
    else:
        batch_to_evaluate = sorted_unjudged
        excess_candidates = []

    # 10. Call fast-tier LLM for structured verdicts
    await emit(
        "llm_call",
        {"tier": "fast", "count": len(batch_to_evaluate)},
        f"Judging {len(batch_to_evaluate)} pairs...",
    )

    user_prompt = build_critic_user_prompt([c.candidate_pair for c in batch_to_evaluate])
    llm_result = await deps.llm.call(
        tier="fast",
        system=CRITIC_SYSTEM_PROMPT,
        user=user_prompt,
        schema=CriticOutputSchema,
        temperature=0.2,
        ctx=ctx,
    )
    llm_data: CriticOutputSchema = llm_result.data

    # 11. Validate model outputs and filter fabricated or duplicate pair IDs
    requested_pids = {c.candidate_pair.pair_id for c in batch_to_evaluate}
    received_verdicts: dict[str, CriticVerdict] = {}

    for v in llm_data.verdicts:
        if v.pair_id in requested_pids and v.pair_id not in received_verdicts:
            received_verdicts[v.pair_id] = v

    # 12. Retry missing pair IDs exactly once
    missing_pids = requested_pids - set(received_verdicts.keys())
    if missing_pids:
        missing_candidates = [
            c for c in batch_to_evaluate if c.candidate_pair.pair_id in missing_pids
        ]
        retry_prompt = build_critic_user_prompt([c.candidate_pair for c in missing_candidates])
        retry_result = await deps.llm.call(
            tier="fast",
            system=CRITIC_SYSTEM_PROMPT,
            user=retry_prompt,
            schema=CriticOutputSchema,
            temperature=0.2,
            ctx=ctx,
        )
        for v in retry_result.data.verdicts:
            if v.pair_id in missing_pids and v.pair_id not in received_verdicts:
                received_verdicts[v.pair_id] = v

    still_missing_count = len(requested_pids) - len(received_verdicts)
    excess_count = len(excess_candidates)

    # 13. Build and persist validated verdicts into PostgreSQL
    db_verdicts: list[Verdict] = []
    for pid, v in received_verdicts.items():
        cand = candidates[pid]
        db_verdicts.append(
            Verdict(
                project_id=inp.project_id,
                id=pid,
                claim_key_a=cand.claim_key_a,
                claim_key_b=cand.claim_key_b,
                source_id_a=cand.source_id_a,
                source_id_b=cand.source_id_b,
                source_tag_a=cand.source_tag_a,
                source_tag_b=cand.source_tag_b,
                claim_text_a=cand.claim_text_a,
                claim_text_b=cand.claim_text_b,
                label=v.label,
                confidence=v.confidence,
                rationale=v.rationale,
                similarity=cand.similarity,
            )
        )

    if db_verdicts:
        await deps.repos.verdicts.upsert_verdicts(inp.project_id, db_verdicts)
        await emit(
            "doc_write",
            {"docType": "verdict", "count": len(db_verdicts)},
            f"Saved {len(db_verdicts)} verdicts",
        )

    # 14. Partial failure vs Full completion handling
    if still_missing_count > 0 or excess_count > 0:
        total_remaining = still_missing_count + excess_count
        await deps.repos.sources.update_stage_flags(
            project_id=inp.project_id,
            source_id=inp.source_id,
            stage_critiqued=False,
            last_error="PARTIAL_CRITIQUE",
        )
        if hasattr(deps.repos.sources, "session"):
            await deps.repos.sources.session.commit()

        err_msg = (
            f"Critique partially completed: {len(db_verdicts)} verdicts saved, "
            f"{total_remaining} pairs remain unevaluated."
        )
        await emit(
            "error",
            {
                "code": "PARTIAL_CRITIQUE",
                "verdictsSaved": len(db_verdicts),
                "remainingPairs": total_remaining,
            },
            err_msg,
        )
        raise AppError("PARTIAL_CRITIQUE", err_msg, retryable=True)

    # 15. Full success completion
    await deps.repos.sources.update_stage_flags(
        project_id=inp.project_id,
        source_id=inp.source_id,
        stage_critiqued=True,
        last_error=None,
    )
    if hasattr(deps.repos.sources, "session"):
        await deps.repos.sources.session.commit()

    supports_count = sum(1 for v in db_verdicts if v.label == "supports")
    contradicts_count = sum(1 for v in db_verdicts if v.label == "contradicts")
    nuances_count = sum(1 for v in db_verdicts if v.label == "nuances")
    unrelated_count = sum(1 for v in db_verdicts if v.label == "unrelated")

    output = CriticOutput(
        pairs_judged=len(db_verdicts),
        supports=supports_count,
        contradicts=contradicts_count,
        nuances=nuances_count,
        unrelated=unrelated_count,
        skipped_existing=skipped_existing,
    )
    await emit("result", output.model_dump(by_alias=True), "Done")
    return output
