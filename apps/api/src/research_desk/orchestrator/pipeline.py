"""Pipeline orchestrator dispatching stages to agents and managing jobs.

Per docs/02-DESIGN-DOC.md Section 4 and docs/04-AGENT-SPECS.md:
- run_stage(stage, inp, deps, emit, ctx) dispatches to the stage's agent.
- create_stage_callable constructs the detached task executed by the runner.
- PipelineOrchestrator ties together JobService, InProcessRunner, EventSink, and Agents.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from research_desk.agents import collector
from research_desk.agents.collector import AgentDeps, CollectorInput, CollectorRepos
from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.jobs import JobService
from research_desk.orchestrator.runner import JobRunner, StageCallable
from research_desk.providers.embeddings import EmbeddingProvider
from research_desk.providers.llm import CallContext, LLMProvider
from research_desk.stores.db import DbSessionFactory
from research_desk.stores.models import Job
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import VectorStore

logger = logging.getLogger(__name__)

AgentEmit = Callable[[str, dict[str, Any] | None, str | None], Coroutine[Any, Any, None]]


async def run_stage(
    stage: str,
    inp: Any,
    deps: AgentDeps,
    emit: AgentEmit,
    ctx: CallContext,
) -> dict[str, Any]:
    """Dispatch and execute a single pipeline stage.

    The orchestrator is the only caller of agents.
    Agents never call each other directly.
    """
    if stage == "collect":
        if isinstance(inp, dict):
            collector_in = CollectorInput.model_validate(inp)
        elif isinstance(inp, CollectorInput):
            collector_in = inp
        else:
            raise AppError(
                "BAD_REQUEST",
                f"Invalid input type for collect stage: {type(inp).__name__}",
            )

        try:
            output = await collector.run(collector_in, deps, emit, ctx)
            return output.model_dump(by_alias=True)
        finally:
            if collector_in.pdf_path and os.path.exists(collector_in.pdf_path):
                try:
                    os.unlink(collector_in.pdf_path)
                except OSError as exc:
                    logger.warning(
                        "Failed to remove temporary PDF file '%s': %s",
                        collector_in.pdf_path,
                        exc,
                    )

    elif stage == "analyze":
        source_id = getattr(inp, "source_id", None) or (
            inp.get("source_id") if isinstance(inp, dict) else None
        )
        project_id = (
            ctx.project_id
            or getattr(inp, "project_id", None)
            or (inp.get("project_id") if isinstance(inp, dict) else None)
        )
        if not source_id or not project_id:
            raise AppError("BAD_REQUEST", "project_id and source_id are required for analyze stage")
        source = await deps.repos.sources.get(project_id, source_id)
        if not source or not source.stage_collected:
            raise AppError("BAD_REQUEST", f"Source '{source_id}' must be collected before analysis")
        raise AppError("NOT_IMPLEMENTED", "Stage 'analyze' will be implemented in Stage 4")

    elif stage == "critique":
        source_id = getattr(inp, "source_id", None) or (
            inp.get("source_id") if isinstance(inp, dict) else None
        )
        project_id = (
            ctx.project_id
            or getattr(inp, "project_id", None)
            or (inp.get("project_id") if isinstance(inp, dict) else None)
        )
        if not source_id or not project_id:
            raise AppError(
                "BAD_REQUEST",
                "project_id and source_id are required for critique stage",
            )
        source = await deps.repos.sources.get(project_id, source_id)
        if not source or not source.stage_analyzed:
            raise AppError("BAD_REQUEST", f"Source '{source_id}' must be analyzed before critique")
        raise AppError("NOT_IMPLEMENTED", "Stage 'critique' will be implemented in Stage 5")

    elif stage == "ask":
        project_id = (
            ctx.project_id
            or getattr(inp, "project_id", None)
            or (inp.get("project_id") if isinstance(inp, dict) else None)
        )
        if not project_id:
            raise AppError("BAD_REQUEST", "project_id is required for ask stage")
        raise AppError("NOT_IMPLEMENTED", "Stage 'ask' will be implemented in Stage 6")

    else:
        raise AppError("BAD_REQUEST", f"Unknown pipeline stage '{stage}'")


def create_stage_callable(
    stage: str,
    inp: Any,
    ctx: CallContext,
    sessionmaker: DbSessionFactory,
    vectors: VectorStore,
    embeddings: EmbeddingProvider,
    llm: LLMProvider | None = None,
    cfg: Settings | None = None,
) -> StageCallable:
    """Create a detached stage callable suitable for InProcessRunner."""

    async def stage_coro(event_sink: EventSink) -> dict[str, Any]:
        async with sessionmaker() as session:
            repos = CollectorRepos(
                projects=ProjectRepo(session),
                sources=SourceRepo(session),
            )
            deps = AgentDeps(
                repos=repos,
                vectors=vectors,
                embeddings=embeddings,
                llm=llm,
                cfg=cfg,
            )

            async def agent_emit(
                type_: str, data: dict[str, Any] | None, message: str | None
            ) -> None:
                # Map internal agent types to API specification types
                wire_type = type_
                if type_ == "start":
                    wire_type = "stage_start"
                elif type_ == "status":
                    wire_type = "step"
                elif type_ == "complete":
                    return

                agent_name = "collector" if stage == "collect" else stage
                if ctx.job_id is not None:
                    await event_sink.emit(
                        job_id=ctx.job_id,
                        stage=stage,
                        agent=agent_name,
                        type_=wire_type,
                        message=message,
                        data=data,
                    )

            return await run_stage(stage, inp, deps, agent_emit, ctx)

    return stage_coro


class PipelineOrchestrator:
    """Orchestrates research desk pipeline execution through JobService, Runner, and Agents."""

    def __init__(
        self,
        sessionmaker: DbSessionFactory,
        vectors: VectorStore,
        embeddings: EmbeddingProvider,
        job_service: JobService,
        runner: JobRunner,
        event_sink: EventSink,
        llm: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.vectors = vectors
        self.embeddings = embeddings
        self.job_service = job_service
        self.runner = runner
        self.event_sink = event_sink
        self.llm = llm
        self.settings = settings or get_settings()

    async def run_job(
        self,
        *,
        stage: str,
        project_id: str,
        user_id: uuid.UUID,
        inp: Any,
        input_hash: str,
        source_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[Job, bool]:
        """Create or join a single-flight job and submit to runner if newly created."""
        job, is_new = await self.job_service.create_or_join_job(
            project_id=project_id,
            user_id=user_id,
            stage=stage,
            input_hash=input_hash,
            source_id=source_id,
            idempotency_key=idempotency_key,
            lease_seconds=self.settings.JOB_LEASE_S,
        )

        if is_new:
            ctx = CallContext(
                user_id=user_id,
                project_id=project_id,
                job_id=job.id,
            )
            stage_coro = create_stage_callable(
                stage=stage,
                inp=inp,
                ctx=ctx,
                sessionmaker=self.sessionmaker,
                vectors=self.vectors,
                embeddings=self.embeddings,
                llm=self.llm,
                cfg=self.settings,
            )
            await self.runner.submit(job.id, stage_coro)

        return job, is_new
