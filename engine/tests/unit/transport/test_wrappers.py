from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ncl_engine.sources.transport import (
    CacheTransport,
    CanonicalRequest,
    PoliteTransport,
    RecordingTransport,
    SnapshotOrigin,
    SourceId,
    SourcePolicyError,
    SourceSnapshot,
    UpstreamResponseError,
)


class FakeTransport:
    def __init__(self, body: bytes = b"payload", *, fail: bool = False) -> None:
        self.calls = 0
        self.body = body
        self.fail = fail

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline")
        return SourceSnapshot(
            request.source_id,
            request,
            datetime.now(UTC),
            200,
            {"content-type": "application/json"},
            self.body,
            SnapshotOrigin.NETWORK,
        )


@pytest.mark.asyncio
async def test_recording_uses_d18_blob_layout(tmp_path: Path) -> None:
    upstream = FakeTransport()
    recorder = RecordingTransport(upstream, tmp_path)
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    snapshot = await recorder.request(request)
    recorded = recorder.interactions[0]
    body = recorded["response"]["body"]
    digest = body["sha256"]
    assert body["path"] == f"sha256/{digest[:2]}/{digest}"
    assert (tmp_path / body["path"]).read_bytes() == b"payload"
    assert recorded["origin"] == "network"
    assert snapshot.interaction_id is not None


@pytest.mark.asyncio
async def test_recording_deduplicates_identical_requests_in_one_run(tmp_path: Path) -> None:
    upstream = FakeTransport()
    recorder = RecordingTransport(upstream, tmp_path)
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    snapshots = await asyncio.gather(*(recorder.request(request) for _ in range(4)))
    assert upstream.calls == 1
    assert len(recorder.interactions) == 1
    assert {snapshot.interaction_id for snapshot in snapshots} == {recorder.interactions[0]["id"]}


@pytest.mark.asyncio
async def test_cache_prevents_second_celestrak_fetch(tmp_path: Path) -> None:
    upstream = FakeTransport()
    cache = CacheTransport(upstream, tmp_path)
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    first = await cache.request(request)
    second = await cache.request(request)
    assert first.origin is SnapshotOrigin.NETWORK
    assert second.origin is SnapshotOrigin.CACHE
    assert upstream.calls == 1


@pytest.mark.asyncio
async def test_stale_cache_is_labelled_when_refresh_fails(tmp_path: Path) -> None:
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    initial = FakeTransport()
    cache = CacheTransport(initial, tmp_path, ttls={source: timedelta(0) for source in SourceId})
    await cache.request(request)
    failing = FakeTransport(fail=True)
    second_cache = CacheTransport(
        failing, tmp_path, ttls={source: timedelta(0) for source in SourceId}
    )
    snapshot = await second_cache.request(request)
    assert snapshot.origin is SnapshotOrigin.CACHE
    assert snapshot.headers["x-ncl-cache-stale"] == "true"


@pytest.mark.asyncio
async def test_resume_can_reuse_stale_cache_without_refresh(tmp_path: Path) -> None:
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    initial = FakeTransport()
    await CacheTransport(initial, tmp_path).request(request)
    forbidden = FakeTransport(fail=True)
    resumed = CacheTransport(
        forbidden,
        tmp_path,
        ttls={source: timedelta(0) for source in SourceId},
        refresh_stale=False,
    )
    snapshot = await resumed.request(request)
    assert snapshot.origin is SnapshotOrigin.CACHE
    assert snapshot.headers["x-ncl-cache-stale"] == "true"
    assert forbidden.calls == 0


@pytest.mark.asyncio
async def test_record_mode_bypasses_cache_but_keeps_celestrak_two_hour_guard(
    tmp_path: Path,
) -> None:
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    initial = FakeTransport()
    await CacheTransport(initial, tmp_path).request(request)
    record_upstream = FakeTransport(b"new")
    record_cache = CacheTransport(record_upstream, tmp_path, read_enabled=False)
    with pytest.raises(SourcePolicyError, match="less than two hours"):
        await record_cache.request(request)
    assert record_upstream.calls == 0


class ConcurrencyProbe:
    def __init__(self) -> None:
        self.active = 0
        self.high_water = 0

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        self.active += 1
        self.high_water = max(self.high_water, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return SourceSnapshot(
            request.source_id,
            request,
            datetime.now(UTC),
            200,
            {},
            b"ok",
            SnapshotOrigin.NETWORK,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "limit"),
    [(SourceId.CELESTRAK, 1), (SourceId.EARTH_SEARCH, 2), (SourceId.SENTINEL_COGS, 4)],
)
async def test_politeness_concurrency_is_enforced(source: SourceId, limit: int) -> None:
    probe = ConcurrencyProbe()
    polite = PoliteTransport(probe)
    requests = [
        CanonicalRequest(source, "GET", f"https://example.com/{index}") for index in range(8)
    ]
    await asyncio.gather(*(polite.request(request) for request in requests))
    assert probe.high_water == limit


@pytest.mark.asyncio
async def test_politeness_queue_does_not_starve_the_event_loop_executor() -> None:
    class ExecutorUsingProbe(ConcurrencyProbe):
        async def request(self, request: CanonicalRequest) -> SourceSnapshot:
            await asyncio.to_thread(lambda: None)
            return await super().request(request)

    probe = ExecutorUsingProbe()
    polite = PoliteTransport(probe)
    requests = [
        CanonicalRequest(SourceId.SENTINEL_COGS, "GET", f"https://example.com/{index}")
        for index in range(64)
    ]

    await asyncio.wait_for(
        asyncio.gather(*(polite.request(request) for request in requests)), timeout=3
    )

    assert probe.high_water == 4


class FlakyRangeTransport:
    def __init__(self, failures: int) -> None:
        self.calls = 0
        self.failures = failures

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        self.calls += 1
        if self.calls <= self.failures:
            raise UpstreamResponseError("connection reset")
        return SourceSnapshot(
            request.source_id,
            request,
            datetime.now(UTC),
            206,
            {"content-range": "bytes 0-0/1"},
            b"x",
            SnapshotOrigin.NETWORK,
        )


@pytest.mark.asyncio
async def test_politeness_retries_transient_cog_ranges() -> None:
    upstream = FlakyRangeTransport(failures=2)
    request = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif",
        headers={"Range": "bytes=0-0"},
    )
    snapshot = await PoliteTransport(upstream).request(request)
    assert snapshot.body == b"x"
    assert upstream.calls == 3


@pytest.mark.asyncio
async def test_politeness_never_retries_celestrak() -> None:
    upstream = FlakyRangeTransport(failures=1)
    request = CanonicalRequest(
        SourceId.CELESTRAK,
        "GET",
        "https://celestrak.org/NORAD/elements/gp.php",
    )
    with pytest.raises(UpstreamResponseError, match="connection reset"):
        await PoliteTransport(upstream).request(request)
    assert upstream.calls == 1
