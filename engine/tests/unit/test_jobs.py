from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from ncl_engine.domain.clock import FrozenClock
from ncl_engine.domain.models import (
    AnalysisJob,
    AnalysisJobCreate,
    JobResult,
    JobStage,
    JobState,
    JobType,
)
from ncl_engine.jobs import JobContext, JobManager
from ncl_engine.storage import SQLiteStore

CLOCK = FrozenClock(datetime(2026, 10, 3, tzinfo=UTC))


async def _wait_terminal(manager: JobManager, job_id: str) -> AnalysisJob:
    for _ in range(200):
        job = manager.get(job_id)
        assert job is not None
        if job.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
            return job
        await asyncio.sleep(0.001)
    raise AssertionError("job did not terminate")


async def test_sse_final_drain_always_delivers_completed(tmp_path: Path) -> None:
    async def runner(context: JobContext, request: AnalysisJobCreate) -> JobResult:
        del request
        for index in range(3):
            await context.result("opportunity", "/x", {"i": index}, f"prv-{index}")
            await asyncio.sleep(0)
        return JobResult(opportunity_count=3, scene_count=0, likelihood_url=None)

    store = SQLiteStore(tmp_path / "jobs.sqlite")
    manager = JobManager(store, CLOCK, lambda: "replay", runner)
    for index in range(10):
        job = await manager.create(
            AnalysisJobCreate(type=JobType.ORBIT_ONLY, aoi_id=f"aoi-{index}")
        )
        delivered: list[str] = []
        async for chunk in manager.stream(job.id):
            text = chunk.decode()
            if text.startswith("id:"):
                delivered.append(text.split("\n")[1].removeprefix("event: "))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        assert delivered[-1] == "job.completed"


async def test_sse_wait_predicate_prevents_missed_wakeup(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def runner(context: JobContext, request: AnalysisJobCreate) -> JobResult:
        del request
        await context.result("opportunity", "/x", {"i": 0}, "prv-0")
        await context.result("opportunity", "/x", {"i": 1}, "prv-1")
        await gate.wait()
        return JobResult(opportunity_count=2, scene_count=0, likelihood_url=None)

    store = SQLiteStore(tmp_path / "wake.sqlite")
    manager = JobManager(store, CLOCK, lambda: "replay", runner)
    job = await manager.create(AnalysisJobCreate(type=JobType.ORBIT_ONLY, aoi_id="aoi"))

    async def read_four_events() -> list[str]:
        seen: list[str] = []
        async for chunk in manager.stream(job.id):
            text = chunk.decode()
            if text.startswith("id:"):
                seen.append(text.split("\n")[1])
            if len(seen) == 4:
                return seen
            await asyncio.sleep(0)
        return seen

    seen = await asyncio.wait_for(read_four_events(), timeout=0.25)
    assert len(seen) == 4
    gate.set()
    await _wait_terminal(manager, job.id)


async def test_cancelled_job_is_not_reused(tmp_path: Path) -> None:
    async def runner(context: JobContext, request: AnalysisJobCreate) -> JobResult:
        del request
        while True:
            context.checkpoint()
            await asyncio.sleep(0.001)

    store = SQLiteStore(tmp_path / "cancel.sqlite")
    manager = JobManager(store, CLOCK, lambda: "replay", runner)
    request = AnalysisJobCreate(type=JobType.FULL_ANALYSIS, aoi_id="aoi")
    first = await manager.create(request)
    await asyncio.sleep(0.01)
    await manager.cancel(first.id)
    assert (await _wait_terminal(manager, first.id)).state is JobState.CANCELLED
    second = await manager.create(request)
    assert second.id != first.id
    await manager.shutdown()


def test_manager_marks_persisted_active_job_as_restarted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "restart.sqlite")
    job = AnalysisJob(
        id="job-orphan",
        type=JobType.FULL_ANALYSIS,
        aoi_id="aoi",
        scene_id=None,
        state=JobState.RUNNING,
        progress=0.5,
        stage=JobStage.RASTER,
        created_at=CLOCK.now(),
        started_at=CLOCK.now(),
        finished_at=None,
        cancel_requested_at=None,
        result=None,
        error=None,
        events_url="/v1/analysis-jobs/job-orphan/events",
    )
    store.put_job("fingerprint", job)

    async def runner(context: JobContext, request: AnalysisJobCreate) -> JobResult:
        raise AssertionError((context, request))

    manager = JobManager(store, CLOCK, lambda: "replay", runner)
    recovered = manager.get(job.id)
    assert recovered is not None
    assert recovered.state is JobState.FAILED
    assert recovered.error is not None
    assert recovered.error.code == "ENGINE_RESTARTED"
    assert not manager.has_active()


async def test_replay_stream_does_not_depend_on_unrelated_jobs(tmp_path: Path) -> None:
    async def runner(context: JobContext, request: AnalysisJobCreate) -> JobResult:
        await context.result("opportunity", "/x", {"aoi": request.aoi_id}, "prv-0")
        return JobResult(opportunity_count=1, scene_count=0, likelihood_url=None)

    async def stream_for(manager: JobManager, aoi_id: str) -> bytes:
        job = await manager.create(AnalysisJobCreate(type=JobType.ORBIT_ONLY, aoi_id=aoi_id))
        return b"".join([chunk async for chunk in manager.stream(job.id)])

    fresh = JobManager(SQLiteStore(tmp_path / "fresh.sqlite"), CLOCK, lambda: "replay", runner)
    busy = JobManager(SQLiteStore(tmp_path / "busy.sqlite"), CLOCK, lambda: "replay", runner)
    await stream_for(busy, "aoi-other")

    assert await stream_for(fresh, "aoi-tuas") == await stream_for(busy, "aoi-tuas")
    await fresh.shutdown()
    await busy.shutdown()
