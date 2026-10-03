"""Analysis job CRUD and durable SSE route."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from ncl_engine.api.dependencies import runtime
from ncl_engine.api.errors import NclApiError
from ncl_engine.api.pagination import decode_cursor, encode_cursor
from ncl_engine.domain.models import (
    AnalysisJob,
    AnalysisJobCreate,
    JobPage,
    JobState,
    PaginationMeta,
)
from ncl_engine.runtime import Runtime

router = APIRouter()


@router.get("/analysis-jobs", operation_id="listAnalysisJobs", response_model=JobPage)
async def list_jobs(
    app: Annotated[Runtime, Depends(runtime)],
    state: JobState | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> JobPage:
    try:
        offset = decode_cursor(cursor)
    except ValueError as exc:
        raise NclApiError(422, "INVALID_CURSOR", str(exc)) from exc
    values = [job for job in app.jobs.list() if state is None or job.state is state]
    page = values[offset : offset + limit]
    return JobPage(
        data=page,
        meta=PaginationMeta(
            count=len(page),
            next_cursor=encode_cursor(offset + len(page), len(values)),
            as_of=app.clock.now(),
        ),
    )


@router.post(
    "/analysis-jobs", operation_id="createAnalysisJob", response_model=AnalysisJob, status_code=202
)
async def create_job(
    body: AnalysisJobCreate, response: Response, app: Annotated[Runtime, Depends(runtime)]
) -> AnalysisJob:
    try:
        job = await app.jobs.create(body)
    except RuntimeError as exc:
        if str(exc) == "JOB_QUEUE_FULL":
            raise NclApiError(
                429, "JOB_QUEUE_FULL", "The bounded analysis queue is full.", True
            ) from exc
        raise
    response.headers["Location"] = f"/v1/analysis-jobs/{job.id}"
    return job


@router.get("/analysis-jobs/{job_id}", operation_id="getAnalysisJob", response_model=AnalysisJob)
async def get_job(job_id: str, app: Annotated[Runtime, Depends(runtime)]) -> AnalysisJob:
    job = app.jobs.get(job_id)
    if job is None:
        raise NclApiError(404, "NOT_FOUND", f"Job {job_id} does not exist.")
    return job


@router.delete(
    "/analysis-jobs/{job_id}",
    operation_id="cancelAnalysisJob",
    response_model=AnalysisJob,
    status_code=202,
)
async def cancel_job(job_id: str, app: Annotated[Runtime, Depends(runtime)]) -> AnalysisJob:
    try:
        return await app.jobs.cancel(job_id)
    except KeyError as exc:
        raise NclApiError(404, "NOT_FOUND", f"Job {job_id} does not exist.") from exc
    except RuntimeError as exc:
        raise NclApiError(409, "JOB_TERMINAL", "The job has already completed.") from exc


@router.get("/analysis-jobs/{job_id}/events", operation_id="streamAnalysisJobEvents")
async def stream_job_events(
    job_id: str,
    request: Request,
    app: Annotated[Runtime, Depends(runtime)],
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id: str | None = None,
) -> StreamingResponse:
    if app.jobs.get(job_id) is None:
        raise NclApiError(404, "NOT_FOUND", f"Job {job_id} does not exist.")
    selected = last_event_id_header or last_event_id
    sequence = 0
    if selected:
        try:
            prefix, raw_sequence = selected.rsplit(":", 1)
            if prefix != job_id:
                raise ValueError
            sequence = int(raw_sequence)
        except ValueError as exc:
            raise NclApiError(
                410, "EVENT_HISTORY_GONE", "The requested event cursor is invalid."
            ) from exc

    async def stream() -> AsyncIterator[bytes]:
        async for chunk in app.jobs.stream(job_id, sequence):
            if await request.is_disconnected():
                return
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
