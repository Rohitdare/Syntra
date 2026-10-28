"""Pipeline orchestration, job execution, and event sinks."""

from research_desk.orchestrator.events import EventMessage, EventSink
from research_desk.orchestrator.jobs import JobService
from research_desk.orchestrator.pipeline import (
    PipelineOrchestrator,
    create_stage_callable,
    run_stage,
)
from research_desk.orchestrator.runner import InProcessRunner, JobRunner, StageCallable

__all__ = [
    "EventMessage",
    "EventSink",
    "InProcessRunner",
    "JobRunner",
    "JobService",
    "PipelineOrchestrator",
    "StageCallable",
    "create_stage_callable",
    "run_stage",
]
