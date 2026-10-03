from __future__ import annotations

import asyncio
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ncl_engine.sources.transport import (
    CanonicalRequest,
    LoopbackCogAdapter,
    PoliteTransport,
    RecordingTransport,
    SnapshotOrigin,
    SourceSnapshot,
)


class RangeTransport:
    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        start, end = (int(part) for part in request.headers["range"][6:].split("-"))
        body = bytes(range(10))[start : end + 1]
        return SourceSnapshot(
            request.source_id,
            request,
            datetime.now(UTC),
            206,
            {
                "accept-ranges": "bytes",
                "content-range": f"bytes {start}-{end}/10",
                "content-type": "image/tiff",
                "etag": '"fixture-v1"',
            },
            body,
            SnapshotOrigin.FIXTURE,
        )


class LargeRangeTransport:
    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        start, end = (int(part) for part in request.headers["range"][6:].split("-"))
        body = b"x" * (end - start + 1)
        return SourceSnapshot(
            request.source_id,
            request,
            datetime.now(UTC),
            206,
            {
                "accept-ranges": "bytes",
                "content-range": f"bytes {start}-{end}/{end + 1}",
                "content-type": "image/tiff",
                "etag": '"fixture-large"',
            },
            body,
            SnapshotOrigin.FIXTURE,
        )


def test_loopback_serves_only_requested_cog_range() -> None:
    remote = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif"
    with LoopbackCogAdapter(RangeTransport()) as adapter:
        local = adapter.register(remote)
        request = urllib.request.Request(local, headers={"Range": "bytes=3-6"})
        with urllib.request.urlopen(request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 3-6/10"
            assert response.read() == bytes([3, 4, 5, 6])


def test_loopback_can_use_cross_thread_recording_transport(tmp_path: Path) -> None:
    remote = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif"
    recorder = RecordingTransport(PoliteTransport(RangeTransport()), tmp_path)
    with LoopbackCogAdapter(recorder) as adapter:
        local = adapter.register(remote)
        request = urllib.request.Request(local, headers={"Range": "bytes=1-3"})
        with urllib.request.urlopen(request) as response:
            assert response.read() == bytes([1, 2, 3])
    assert len(recorder.interactions) == 1


def test_loopback_accepts_bounded_merged_range_above_two_mib() -> None:
    remote = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/TCI.tif"
    end = 2 * 1024 * 1024
    with LoopbackCogAdapter(LargeRangeTransport()) as adapter:
        local = adapter.register(remote)
        request = urllib.request.Request(local, headers={"Range": f"bytes=0-{end}"})
        with urllib.request.urlopen(request) as response:
            assert response.status == 206
            assert len(response.read()) == end + 1


@pytest.mark.asyncio
async def test_concurrent_loopbacks_dispatch_on_the_calling_event_loop() -> None:
    class LoopBoundRangeTransport(RangeTransport):
        def __init__(self) -> None:
            self.loop_ids: set[int] = set()
            self.lock = asyncio.Lock()

        async def request(self, request: CanonicalRequest) -> SourceSnapshot:
            async with self.lock:
                self.loop_ids.add(id(asyncio.get_running_loop()))
                await asyncio.sleep(0.01)
                return await super().request(request)

    transport = LoopBoundRangeTransport()
    calling_loop_id = id(asyncio.get_running_loop())
    remote = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif"

    async def read_range(index: int) -> bytes:
        with LoopbackCogAdapter(transport) as adapter:
            local = adapter.register(remote)

            def read() -> bytes:
                request = urllib.request.Request(local, headers={"Range": f"bytes={index}-{index}"})
                with urllib.request.urlopen(request) as response:
                    return bytes(response.read())

            return await asyncio.to_thread(read)

    values = await asyncio.wait_for(
        asyncio.gather(*(read_range(index) for index in range(4))), timeout=5
    )

    assert values == [bytes([index]) for index in range(4)]
    assert transport.loop_ids == {calling_loop_id}
