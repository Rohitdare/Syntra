"""Source ingestion and management API routes."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse

from research_desk.agents.collector import CollectorInput
from research_desk.api.auth import get_current_user, get_owned_project
from research_desk.api.dependencies import (
    get_event_sink,
    get_pipeline_orchestrator,
    get_vector_store,
)
from research_desk.core.config import Settings, get_settings
from research_desk.core.errors import AppError
from research_desk.core.schemas import (
    DeleteSourceResponse,
    ProjectSourceItem,
    SourceDetailResponse,
    SourceStages,
)
from research_desk.orchestrator.events import EventSink
from research_desk.orchestrator.pipeline import PipelineOrchestrator
from research_desk.stores.db import DbSession, get_db
from research_desk.stores.models import Project, User
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.vector import VectorStore

router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


def _validate_idempotency_key(key: str | None) -> str | None:
    """Validate that the idempotency key contains 1-100 visible ASCII characters."""
    if key is None:
        return None
    k = key.strip()
    if not (1 <= len(k) <= 100) or not all(33 <= ord(c) <= 126 for c in k):
        raise AppError(
            code="BAD_REQUEST",
            message="Idempotency-Key must contain 1-100 visible ASCII characters",
            http_status=400,
            retryable=False,
        )
    return k


@router.post("", status_code=status.HTTP_200_OK)
async def ingest_source(
    project_id: str,
    request: Request,
    project: Project = Depends(get_owned_project),
    current_user: User = Depends(get_current_user),
    session: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    orchestrator: PipelineOrchestrator = Depends(get_pipeline_orchestrator),
    event_sink: EventSink = Depends(get_event_sink),
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Ingest a new source into evidence memory with live NDJSON event streaming."""
    idempotency_key = _validate_idempotency_key(idempotency_key_header)

    # Enforce maximum source limit per project
    source_repo = SourceRepo(session)
    source_count = await source_repo.count_by_project(project.id)
    if source_count >= settings.MAX_SOURCES_PER_PROJECT:
        raise AppError(
            code="LIMIT_REACHED",
            message=(
                f"Project has reached the maximum limit of "
                f"{settings.MAX_SOURCES_PER_PROJECT} sources"
            ),
            http_status=409,
            retryable=False,
        )

    content_type = request.headers.get("content-type", "")

    # 1. Handle multipart/form-data PDF upload
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_file: Any = form.get("file")
        if not upload_file or not hasattr(upload_file, "read"):
            raise AppError(
                code="BAD_REQUEST",
                message="Multipart form must provide a 'file' field",
                http_status=400,
            )

        title_raw = form.get("title")
        title = str(title_raw).strip() if title_raw else None

        chunk_size = 64 * 1024
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        total_bytes = 0
        magic_bytes = b""
        hasher = hashlib.sha256()

        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            while chunk := await upload_file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise AppError(
                        code="PAYLOAD_TOO_LARGE",
                        message=f"Upload exceeds maximum size of {settings.MAX_UPLOAD_MB}MB",
                        http_status=413,
                        retryable=False,
                    )
                if len(magic_bytes) < 5:
                    magic_bytes += chunk[: 5 - len(magic_bytes)]
                hasher.update(chunk)
                temp_file.write(chunk)
            temp_file.flush()
        except Exception:
            temp_file.close()
            if os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
            raise
        finally:
            temp_file.close()

        if not magic_bytes.startswith(b"%PDF"):
            if os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
            raise AppError(
                code="UNSUPPORTED_MEDIA_TYPE",
                message="Uploaded file is not a valid PDF document",
                http_status=415,
                retryable=False,
            )

        input_hash = hasher.hexdigest()
        orig_filename = getattr(upload_file, "filename", "upload.pdf") or "upload.pdf"
        collector_input = CollectorInput(
            project_id=project.id,
            kind="pdf",
            title=title or orig_filename,
            pdf_path=temp_file.name,
        )

    # 2. Handle application/json URL or pasted text
    elif "application/json" in content_type:
        try:
            body_dict = await request.json()
        except Exception as exc:
            raise AppError(
                code="BAD_REQUEST",
                message=f"Invalid JSON payload: {exc}",
                http_status=400,
            ) from exc

        url = body_dict.get("url")
        text = body_dict.get("text")
        title = body_dict.get("title")

        if url:
            url_str = str(url).strip()
            if not (url_str.startswith("http://") or url_str.startswith("https://")):
                raise AppError(
                    code="FETCH_BLOCKED",
                    message="URL must use http or https scheme",
                    http_status=422,
                )
            input_hash = hashlib.sha256(url_str.encode("utf-8")).hexdigest()
            collector_input = CollectorInput(
                project_id=project.id,
                kind="url",
                title=str(title).strip() if title else url_str,
                url=url_str,
            )
        elif text:
            text_str = str(text)
            if len(text_str) > settings.MAX_PASTE_CHARS:
                raise AppError(
                    code="BAD_REQUEST",
                    message=(
                        f"Pasted text exceeds maximum length of "
                        f"{settings.MAX_PASTE_CHARS} characters"
                    ),
                    http_status=400,
                )

            input_hash = hashlib.sha256(text_str.encode("utf-8")).hexdigest()
            collector_input = CollectorInput(
                project_id=project.id,
                kind="text",
                title=str(title).strip() if title else "Pasted Text",
                text=text_str,
            )
        else:
            raise AppError(
                code="BAD_REQUEST",
                message="JSON body must provide 'url' or 'text'",
                http_status=400,
            )
    else:
        raise AppError(
            code="BAD_REQUEST",
            message="Content-Type must be multipart/form-data or application/json",
            http_status=400,
        )

    # Run detached collector pipeline job
    try:
        job, is_new = await orchestrator.run_job(
            stage="collect",
            project_id=project.id,
            user_id=current_user.id,
            inp=collector_input,
            input_hash=input_hash,
            source_id=None,
            idempotency_key=idempotency_key,
        )
    except Exception:
        if collector_input.pdf_path and os.path.exists(collector_input.pdf_path):
            try:
                os.unlink(collector_input.pdf_path)
            except OSError:
                pass
        raise

    # Clean up redundant temporary file if replaying an existing job
    if not is_new and collector_input.pdf_path and os.path.exists(collector_input.pdf_path):
        try:
            os.unlink(collector_input.pdf_path)
        except OSError:
            pass

    async def event_generator() -> AsyncGenerator[str, None]:
        async for msg in event_sink.subscribe(job.id, since_seq=0):
            yield msg.to_ndjson() + "\n"

    req_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:24]}"
    headers = {
        "X-Request-Id": req_id,
        "X-Job-Id": str(job.id),
    }

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers=headers,
    )


@router.get("/{source_id}", status_code=status.HTTP_200_OK, response_model=SourceDetailResponse)
async def get_source(
    source_id: str,
    project: Project = Depends(get_owned_project),
    session: DbSession = Depends(get_db),
) -> SourceDetailResponse:
    """Fetch detail view for a specific source."""
    source_repo = SourceRepo(session)
    source = await source_repo.get(project.id, source_id)
    if source is None:
        raise AppError(
            code="NOT_FOUND",
            message="Source not found",
            http_status=404,
            retryable=False,
        )

    return SourceDetailResponse(
        source=ProjectSourceItem(
            id=source.id,
            tag=source.tag,
            kind=source.kind,
            title=source.title,
            origin=source.origin,
            chunk_count=source.chunk_count,
            claim_count=source.claim_count,
            stages=SourceStages(
                collected=source.stage_collected,
                analyzed=source.stage_analyzed,
                critiqued=source.stage_critiqued,
            ),
            last_error=source.last_error,
        ),
        summary=source.summary,
        claims=[],
        verdicts=[],
    )


@router.delete("/{source_id}", status_code=status.HTTP_200_OK, response_model=DeleteSourceResponse)
async def delete_source(
    source_id: str,
    project: Project = Depends(get_owned_project),
    session: DbSession = Depends(get_db),
    vectors: VectorStore = Depends(get_vector_store),
) -> DeleteSourceResponse:
    """Delete a source and its chunks/claims from evidence memory."""
    source_repo = SourceRepo(session)
    source = await source_repo.get(project.id, source_id)
    if source is None:
        raise AppError(
            code="NOT_FOUND",
            message="Source not found",
            http_status=404,
            retryable=False,
        )

    job_repo = JobRepo(session)
    if await job_repo.has_active_for_source(project.id, source_id):
        raise AppError(
            code="JOB_ACTIVE",
            message="A stage is still running for this source.",
            http_status=409,
            retryable=True,
        )

    # 1. Purge points from Qdrant
    try:
        await vectors.delete_source(project.id, source_id)
    except Exception as exc:
        raise AppError(
            code="VECTOR_DB_ERROR",
            message=f"Vector database failed to delete source points: {exc}",
            http_status=503,
            retryable=True,
        ) from exc

    # 2. Delete source record from PostgreSQL (cascades claims, texts, verdicts)
    await source_repo.delete(project.id, source_id)
    await session.commit()

    return DeleteSourceResponse(deleted=True)
