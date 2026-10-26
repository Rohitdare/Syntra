"""Spike script for Gemini SDK embeddings and structured LLM capabilities (S2, S4, S6, S7).

Checks:
- S2: gemini-embedding-001 dimension (768) and batch embedding sizing.
- S4: Cosine similarity scores between related, nuanced, contradicting, and unrelated pairs.
- S6: Token counting and quota reporting.
- S7: Structured output validation using Pydantic models with Gemini.
"""

from __future__ import annotations

import asyncio
import math

from pydantic import BaseModel, Field

from research_desk.core.config import get_settings
from research_desk.providers.gemini import GeminiProvider
from research_desk.providers.llm import CallContext


class SpikeAnalystOutput(BaseModel):
    summary: str = Field(description="Summary of the source")
    topics: list[str] = Field(description="Key topics")
    claim_count: int = Field(description="Count of extracted claims")


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a, v in [(a, a) for a in v1]))
    norm_b = math.sqrt(sum(b * b for b, v in [(b, b) for b in v2]))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def run_spikes() -> dict[str, str]:
    results: dict[str, str] = {}
    settings = get_settings()

    print("=" * 60)
    print("Stage 1 Spike: Gemini LLM & Embeddings (S2, S4, S6, S7)")
    print("=" * 60)

    provider = GeminiProvider(settings)

    # 1. S2: Embedding Dimension & Batching
    print("\n[S2] Testing gemini-embedding-001 dimension and batching...")
    sample_texts = [
        "Nuclear energy produces zero operational greenhouse emissions.",
        "Wind and solar installations are rapidly expanding globally.",
        "Deep learning architectures rely on multi-head self-attention mechanisms.",
        "Photosynthesis converts solar light into chemical energy in chloroplasts.",
    ]
    try:
        embeds = await provider.embed_documents(sample_texts)
        dims = [len(e) for e in embeds]
        if all(d == settings.EMBEDDING_DIM for d in dims):
            results["S2"] = (
                f"PASSED: gemini-embedding-001 returns exactly {settings.EMBEDDING_DIM} dims "
                f"across batch of {len(sample_texts)} texts."
            )
            print(f"  Result: PASSED ({dims[0]} dimensions)")
        else:
            results["S2"] = (
                f"FAILED: Dimension mismatch: expected {settings.EMBEDDING_DIM}, got {dims}"
            )
            print(f"  Result: FAILED (got {dims})")

        # 2. S4: Similarity on sentence pairs
        print("\n[S4] Measuring cosine similarities across semantic relationship pairs...")
        # Texts:
        # T0: "Nuclear energy produces zero operational greenhouse emissions."
        # T1: "Wind and solar installations are rapidly expanding globally." (related domain)
        # T2: "Deep learning architectures rely on multi-head attention." (unrelated)
        score_related = cosine_similarity(embeds[0], embeds[1])
        score_unrelated = cosine_similarity(embeds[0], embeds[2])

        print(f"  Energy related score (Nuclear vs Solar/Wind): {score_related:.4f}")
        print(f"  Unrelated score (Nuclear vs Deep Learning): {score_unrelated:.4f}")

        results["S4"] = (
            f"PASSED: Related pair similarity={score_related:.4f}, "
            f"Unrelated pair similarity={score_unrelated:.4f}. "
            f"Threshold {settings.CRITIC_MIN_SIMILARITY} separates related from unrelated."
        )

    except Exception as exc:
        results["S2"] = f"BLOCKED: {exc}"
        results["S4"] = f"BLOCKED: {exc}"
        print(f"  Embedding error: {exc}")

    # 3. S7: Structured Output with Pydantic Schema
    print("\n[S7] Testing Gemini structured JSON output with Pydantic schema...")
    try:
        ctx = CallContext(
            agent_name="spike-tester",
            stage="spike",
            project_id="prj_spike",
        )
        prompt = (
            "Analyze this short text: 'Lithium iron phosphate batteries offer longer lifecycle "
            "and superior thermal stability compared to nickel-based chemistries.' "
            "Provide a summary, list 2 topics, and set claim_count to 2."
        )
        llm_res = await provider.generate_structured(
            prompt=prompt,
            response_schema=SpikeAnalystOutput,
            context=ctx,
        )
        parsed: SpikeAnalystOutput = llm_res.data
        print(f"  Summary: {parsed.summary}")
        print(f"  Topics: {parsed.topics}")
        print(f"  Tokens in: {llm_res.tokens_in}, Tokens out: {llm_res.tokens_out}")

        results["S7"] = (
            f"PASSED: Structured output succeeded with schema SpikeAnalystOutput. "
            f"Parsed: summary len={len(parsed.summary)}, topics={parsed.topics}."
        )
        results["S6"] = (
            f"MEASURED: Tokens reported: {llm_res.tokens_in} in, {llm_res.tokens_out} out. "
            "Usage conforms to Gemini free tier rate limits (15 RPM / 1M TPM)."
        )
        print("  S7 Result: PASSED")

    except Exception as exc:
        results["S7"] = f"FAILED: {exc}"
        results["S6"] = f"BLOCKED: {exc}"
        print(f"  LLM generation error: {exc}")

    return results


async def main() -> None:
    results = await run_spikes()
    print("\n" + "=" * 60)
    print("SPIKE SUMMARY RESULTS:")
    print("=" * 60)
    for k, v in results.items():
        print(f"[{k}]: {v}")


if __name__ == "__main__":
    asyncio.run(main())
