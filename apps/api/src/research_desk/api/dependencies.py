"""Dependency injection providers for API routers."""

from __future__ import annotations

from fastapi import Depends

from research_desk.core.config import Settings, get_settings
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.jobs import JobService
from research_desk.orchestrator.pipeline import PipelineOrchestrator
from research_desk.orchestrator.runner import InProcessRunner, JobRunner
from research_desk.providers.embeddings import EmbeddingProvider
from research_desk.providers.gemini import GeminiProvider
from research_desk.providers.llm import LLMProvider
from research_desk.stores.db import DbSessionFactory, get_sessionmaker
from research_desk.stores.vector import QdrantVectorStore, VectorStore

_vector_store: VectorStore | None = None
_embedding_provider: EmbeddingProvider | None = None
_llm_provider: LLMProvider | None = None
_event_sink: EventSink | None = None
_job_service: JobService | None = None
_runner: JobRunner | None = None
_orchestrator: PipelineOrchestrator | None = None


def get_vector_store() -> VectorStore:
    """Return the configured VectorStore instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store


def get_embedding_provider(settings: Settings = Depends(get_settings)) -> EmbeddingProvider:
    """Return the configured EmbeddingProvider instance."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = GeminiProvider(settings=settings)
    return _embedding_provider


def get_llm_provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    """Return the configured LLMProvider instance."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = GeminiProvider(settings=settings)
    return _llm_provider


def get_db_sessionmaker(settings: Settings = Depends(get_settings)) -> DbSessionFactory:
    """Return the database sessionmaker initialized with active settings."""
    return get_sessionmaker(settings)


def get_event_sink(
    sessionmaker: DbSessionFactory = Depends(get_db_sessionmaker),
) -> EventSink:
    """Return the singleton EventSink instance."""
    global _event_sink
    if _event_sink is None:
        _event_sink = EventSink(sessionmaker=sessionmaker)
    return _event_sink


def get_job_service(
    sessionmaker: DbSessionFactory = Depends(get_db_sessionmaker),
) -> JobService:
    """Return the singleton JobService instance."""
    global _job_service
    if _job_service is None:
        _job_service = JobService(sessionmaker=sessionmaker)
    return _job_service


def get_runner(
    settings: Settings = Depends(get_settings),
    event_sink: EventSink = Depends(get_event_sink),
    sessionmaker: DbSessionFactory = Depends(get_db_sessionmaker),
) -> JobRunner:
    """Return the singleton JobRunner instance."""
    global _runner
    if _runner is None:
        _runner = InProcessRunner(
            sessionmaker=sessionmaker,
            event_sink=event_sink,
            active_cap=settings.MAX_ACTIVE_JOBS,
            stage_timeout_s=float(settings.STAGE_TIMEOUT_S),
            lease_seconds=settings.JOB_LEASE_S,
        )
    return _runner


def get_pipeline_orchestrator(
    settings: Settings = Depends(get_settings),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    job_service: JobService = Depends(get_job_service),
    runner: JobRunner = Depends(get_runner),
    event_sink: EventSink = Depends(get_event_sink),
    sessionmaker: DbSessionFactory = Depends(get_db_sessionmaker),
) -> PipelineOrchestrator:
    """Return the configured PipelineOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator(
            sessionmaker=sessionmaker,
            vectors=vector_store,
            embeddings=embedding_provider,
            job_service=job_service,
            runner=runner,
            event_sink=event_sink,
            llm=llm_provider,
            settings=settings,
        )
    return _orchestrator


def reset_dependencies() -> None:
    """Reset all cached dependencies for testing isolation."""
    global _vector_store, _embedding_provider, _llm_provider
    global _event_sink, _job_service, _runner, _orchestrator
    _vector_store = None
    _embedding_provider = None
    _llm_provider = None
    _event_sink = None
    _job_service = None
    _runner = None
    _orchestrator = None
