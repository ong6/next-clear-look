"""Bounded job execution with persist-before-publish SSE semantics."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from ncl_engine.domain.clock import Clock
from ncl_engine.domain.models import (
    AnalysisJob,
    AnalysisJobCreate,
    ErrorObject,
    JobResult,
    JobStage,
    JobState,
)
from ncl_engine.provenance.hashing import JsonValue, canonical_json, sha256_bytes, stable_id
from ncl_engine.storage import SQLiteStore

from .cancellation import CancellationToken, JobCancelled
from .events import encode_sse, iso_z

ModeName = Literal["live", "replay"]
Runner = Callable[["JobContext", AnalysisJobCreate], Awaitable[JobResult]]


class JobContext:
    def __init__(self, manager: JobManager, job_id: str, token: CancellationToken) -> None:
        self.manager = manager
        self.job_id = job_id
        self.token = token

    def checkpoint(self) -> None:
        self.token.checkpoint()

    async def stage_started(
        self, stage: JobStage, *, total_units: int | None, message: str
    ) -> None:
        await self.manager.update_job(self.job_id, stage=stage)
        await self.manager.emit(
            self.job_id,
            "job.stage.started",
            {"stage": stage.value, "total_units": total_units, "message": message},
        )

    async def progress(
        self,
        stage: JobStage,
        *,
        stage_progress: float,
        overall_progress: float,
        message: str,
        completed_units: int,
        total_units: int | None,
    ) -> None:
        await self.manager.update_job(
            self.job_id, stage=stage, progress=max(0.0, min(0.999, overall_progress))
        )
        await self.manager.emit(
            self.job_id,
            "job.progress",
            {
                "stage": stage.value,
                "stage_progress": stage_progress,
                "overall_progress": overall_progress,
                "message": message,
                "completed_units": completed_units,
                "total_units": total_units,
            },
        )

    async def result(
        self,
        result_type: str,
        resource_url: str,
        resource: dict[str, object] | None,
        provenance_id: str,
    ) -> None:
        await self.manager.emit(
            self.job_id,
            "job.result",
            {
                "result_type": result_type,
                "resource_url": resource_url,
                "resource": resource,
                "provenance_id": provenance_id,
            },
        )

    async def warning(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        await self.manager.emit(
            self.job_id,
            "job.warning",
            {"code": code, "message": message, "retryable": retryable, "details": details or {}},
        )

    async def stage_completed(
        self,
        stage: JobStage,
        *,
        duration_seconds: float,
        completed_units: int,
        total_units: int | None,
    ) -> None:
        duration = 0.0 if self.manager.mode() == "replay" else duration_seconds
        await self.manager.emit(
            self.job_id,
            "job.stage.completed",
            {
                "stage": stage.value,
                "duration_seconds": duration,
                "completed_units": completed_units,
                "total_units": total_units,
            },
        )


class JobManager:
    def __init__(
        self,
        store: SQLiteStore,
        clock: Clock,
        mode: Callable[[], ModeName],
        runner: Runner,
        *,
        maximum_jobs: int = 64,
        maximum_running: int = 2,
    ) -> None:
        self.store = store
        self.clock = clock
        self.mode = mode
        self.runner = runner
        self.maximum_jobs = maximum_jobs
        self._semaphore = asyncio.Semaphore(maximum_running)
        self._tokens: dict[str, CancellationToken] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._recover_orphaned_jobs()

    def _recover_orphaned_jobs(self) -> None:
        for raw in self.store.list_jobs():
            job = self._parse(raw)
            if job.state not in {JobState.QUEUED, JobState.RUNNING}:
                continue
            error = ErrorObject(
                code="ENGINE_RESTARTED",
                message="The engine restarted before this job reached a terminal state.",
                retryable=True,
                details={},
                request_id=stable_id("req", job.id, "engine-restarted"),
            )
            recovered = job.model_copy(
                update={
                    "state": JobState.FAILED,
                    "finished_at": self.clock.now(),
                    "error": error,
                }
            )
            self.store.put_job(self._fingerprint_for(job.id), recovered)
            sequence = self.store.event_count(job.id) + 1
            self.store.append_event(
                job.id,
                {
                    "id": f"{job.id}:{sequence}",
                    "sequence": sequence,
                    "type": "job.failed",
                    "stream": "job",
                    "job_id": job.id,
                    "emitted_at": iso_z(self.clock.now()),
                    "mode": self.mode(),
                    "clock_time": iso_z(self.clock.now()),
                    "schema_version": "1.0",
                    "data": {
                        "error": error.model_dump(mode="json"),
                        "partial_result_urls": [],
                    },
                },
            )

    def _parse(self, value: dict[str, Any]) -> AnalysisJob:
        return AnalysisJob.model_validate(value)

    def get(self, job_id: str) -> AnalysisJob | None:
        value = self.store.get_job(job_id)
        return None if value is None else self._parse(value)

    def list(self) -> list[AnalysisJob]:
        return [self._parse(item) for item in self.store.list_jobs()]

    def has_active(self) -> bool:
        return any(job.state in {JobState.QUEUED, JobState.RUNNING} for job in self.list())

    async def create(self, request: AnalysisJobCreate) -> AnalysisJob:
        active = sum(job.state in {JobState.QUEUED, JobState.RUNNING} for job in self.list())
        if active >= self.maximum_jobs:
            raise RuntimeError("JOB_QUEUE_FULL")
        fingerprint_value: dict[str, JsonValue] = {
            "request": request.model_dump(mode="json", by_alias=True),
            "mode": self.mode(),
        }
        if self.mode() == "replay":
            fingerprint_value["clock"] = iso_z(self.clock.now())
        fingerprint = sha256_bytes(canonical_json(fingerprint_value))
        existing = self.store.find_job(fingerprint)
        if existing is not None:
            parsed = self._parse(existing)
            if parsed.state in {JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED}:
                return parsed
            self.store.retire_job_fingerprint(parsed.id)
        # The ID depends only on this request and how many times it has been retried, so the same
        # request yields the same job ID and SSE stream however many other jobs exist.
        job_id = stable_id("job", fingerprint, str(self.store.count_job_attempts(fingerprint) + 1))
        job = AnalysisJob(
            id=job_id,
            type=request.type,
            aoi_id=request.aoi_id,
            scene_id=request.scene_id,
            state=JobState.QUEUED,
            progress=0.0,
            stage=JobStage.CATALOGUE,
            created_at=self.clock.now(),
            started_at=None,
            finished_at=None,
            cancel_requested_at=None,
            result=None,
            error=None,
            events_url=f"/v1/analysis-jobs/{job_id}/events",
        )
        self.store.put_job(fingerprint, job)
        self._tokens[job_id] = CancellationToken()
        self._conditions[job_id] = asyncio.Condition()
        await self.emit(
            job_id,
            "job.accepted",
            {
                "job_type": request.type.value,
                "aoi_id": request.aoi_id,
                "scene_id": request.scene_id,
                "queue_position": active,
            },
        )
        task = asyncio.create_task(self._execute(job_id, request), name=f"ncl-{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job_id, None))
        return job

    async def _execute(self, job_id: str, request: AnalysisJobCreate) -> None:
        token = self._tokens[job_id]
        async with self._semaphore:
            try:
                token.checkpoint()
                await self.update_job(
                    job_id,
                    state=JobState.RUNNING,
                    started_at=self.clock.now(),
                )
                await self.emit(
                    job_id,
                    "job.started",
                    {
                        "job_type": request.type.value,
                        "aoi_id": request.aoi_id,
                        "scene_id": request.scene_id,
                    },
                )
                result = await self.runner(JobContext(self, job_id, token), request)
                token.checkpoint()
                await self.update_job(
                    job_id,
                    state=JobState.SUCCEEDED,
                    progress=1.0,
                    stage=JobStage.FINALISE,
                    finished_at=self.clock.now(),
                    result=result,
                )
                await self.emit(
                    job_id,
                    "job.completed",
                    {
                        "opportunity_count": result.opportunity_count or 0,
                        "scene_count": result.scene_count or 0,
                        "likelihood_url": result.likelihood_url,
                        "partial_failure_count": 0,
                    },
                )
            except JobCancelled as exc:
                await self.update_job(
                    job_id,
                    state=JobState.CANCELLED,
                    finished_at=self.clock.now(),
                )
                await self.emit(
                    job_id,
                    "job.cancelled",
                    {
                        "reason": str(exc),
                        "partial_result_urls": [],
                        "cancelled_at": iso_z(self.clock.now()),
                    },
                )
            except asyncio.CancelledError:
                error = ErrorObject(
                    code="ENGINE_RESTARTED",
                    message="The engine stopped before this job reached a terminal state.",
                    retryable=True,
                    details={},
                    request_id=stable_id("req", job_id, "engine-stopped"),
                )
                await self.update_job(
                    job_id,
                    state=JobState.FAILED,
                    finished_at=self.clock.now(),
                    error=error,
                )
                await self.emit(
                    job_id,
                    "job.failed",
                    {"error": error.model_dump(mode="json"), "partial_result_urls": []},
                )
                raise
            except Exception as exc:
                error = ErrorObject(
                    code="ANALYSIS_FAILED",
                    message=str(exc),
                    retryable=False,
                    details={},
                    request_id=stable_id("req", job_id),
                )
                await self.update_job(
                    job_id,
                    state=JobState.FAILED,
                    finished_at=self.clock.now(),
                    error=error,
                )
                await self.emit(
                    job_id,
                    "job.failed",
                    {"error": error.model_dump(mode="json"), "partial_result_urls": []},
                )

    async def update_job(self, job_id: str, **changes: object) -> AnalysisJob:
        current = self.get(job_id)
        if current is None:
            raise KeyError(job_id)
        updated = current.model_copy(update=changes)
        fingerprint = self._fingerprint_for(job_id)
        self.store.put_job(fingerprint, updated)
        return updated

    def _fingerprint_for(self, job_id: str) -> str:
        with self.store._lock:  # noqa: SLF001 - one repository-level atomic identity read
            row = self.store._connection.execute(  # noqa: SLF001
                "SELECT fingerprint FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return str(row[0])

    async def emit(
        self, job_id: str, event_type: str, data: dict[str, object]
    ) -> dict[str, object]:
        sequence = self.store.event_count(job_id) + 1
        emitted = self.clock.now()
        event: dict[str, object] = {
            "id": f"{job_id}:{sequence}",
            "sequence": sequence,
            "type": event_type,
            "stream": "job",
            "job_id": job_id,
            "emitted_at": iso_z(emitted),
            "mode": self.mode(),
            "clock_time": iso_z(self.clock.now()),
            "schema_version": "1.0",
            "data": data,
        }
        self.store.append_event(job_id, event)
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        async with condition:
            condition.notify_all()
        return event

    async def cancel(self, job_id: str) -> AnalysisJob:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.state is JobState.CANCELLED:
            return job
        if job.state in {JobState.SUCCEEDED, JobState.FAILED}:
            raise RuntimeError("JOB_TERMINAL")
        token = self._tokens.setdefault(job_id, CancellationToken())
        if not token.requested:
            token.request()
            await self.update_job(job_id, cancel_requested_at=self.clock.now())
            await self.emit(
                job_id,
                "job.cancellation_requested",
                {"requested_at": iso_z(self.clock.now())},
            )
        current = self.get(job_id)
        assert current is not None
        return current

    async def stream(self, job_id: str, after_sequence: int = 0) -> AsyncIterator[bytes]:
        if self.get(job_id) is None:
            raise KeyError(job_id)
        sequence = after_sequence
        condition = self._conditions.setdefault(job_id, asyncio.Condition())
        while True:
            events = self.store.list_events(job_id, sequence)
            for event in events:
                sequence = int(event["sequence"])
                yield encode_sse(event)
            job = self.get(job_id)
            if job is None or job.state in {
                JobState.SUCCEEDED,
                JobState.FAILED,
                JobState.CANCELLED,
            }:
                final_events = self.store.list_events(job_id, sequence)
                if final_events:
                    for event in final_events:
                        sequence = int(event["sequence"])
                        yield encode_sse(event)
                    continue
                return
            try:
                async with condition:

                    def has_update(after: int = sequence) -> bool:
                        current = self.get(job_id)
                        return self.store.event_count(job_id) > after or (
                            current is None
                            or current.state
                            in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
                        )

                    await asyncio.wait_for(
                        condition.wait_for(has_update),
                        timeout=15.0,
                    )
            except TimeoutError:
                yield f": heartbeat {iso_z(self.clock.now())}\n\n".encode()

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in list(self._tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
