from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ncl_engine.sources.transport import (
    AmbiguousFixture,
    CanonicalRequest,
    FixtureMiss,
    FixtureTransport,
    SnapshotOrigin,
    SourceId,
)
from ncl_engine.sources.transport.blobs import put_blob

RETRIEVED_AT = "2026-10-02T17:42:44Z"
COG_URL = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif"


def interaction(
    root: Path,
    identifier: str,
    request: CanonicalRequest,
    body: bytes,
    *,
    etag: str | None = None,
    total: int | None = None,
) -> dict[str, object]:
    digest, relative = put_blob(root, body)
    headers: dict[str, str] = {"content-length": str(len(body))}
    status = 200
    if "range" in request.headers:
        start, end = request.headers["range"][6:].split("-")
        headers["content-range"] = f"bytes {start}-{end}/{total or '*'}"
        headers["accept-ranges"] = "bytes"
        status = 206
    if etag is not None:
        headers["etag"] = etag
    return {
        "id": identifier,
        "source_id": request.source_id.value,
        "request": {**request.identity(), "request_key_sha256": request.key()},
        "response": {
            "status": status,
            "headers": headers,
            "retrieved_at": RETRIEVED_AT,
            "body": {"sha256": digest, "size": len(body), "path": relative.as_posix()},
        },
    }


@pytest.mark.asyncio
async def test_exact_json_request_and_miss(tmp_path: Path) -> None:
    request = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "POST",
        "https://earth-search.aws.element84.com/v1/search",
        {"Content-Type": "application/json"},
        b'{"limit":6}',
    )
    transport = FixtureTransport(tmp_path, [interaction(tmp_path, "search", request, b"{}")])
    snapshot = await transport.request(request)
    assert snapshot.body == b"{}"
    assert snapshot.origin is SnapshotOrigin.FIXTURE
    assert snapshot.retrieved_at == datetime(2026, 10, 2, 17, 42, 44, tzinfo=UTC)
    miss = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "POST",
        request.url,
        {"Content-Type": "application/json"},
        b'{"limit":5}',
    )
    with pytest.raises(FixtureMiss, match="network fallback is forbidden"):
        await transport.request(miss)


@pytest.mark.asyncio
async def test_range_is_served_when_union_is_fully_covered_by_one_etag(tmp_path: Path) -> None:
    first = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        COG_URL,
        {"Accept": "image/tiff", "Range": "bytes=0-4"},
    )
    second = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        COG_URL,
        {"Accept": "image/tiff", "Range": "bytes=5-9"},
    )
    transport = FixtureTransport(
        tmp_path,
        [
            interaction(tmp_path, "range-1", first, b"01234", etag='"v1"', total=10),
            interaction(tmp_path, "range-2", second, b"56789", etag='"v1"', total=10),
        ],
    )
    request = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        COG_URL,
        {"Accept": "image/tiff", "Range": "bytes=3-7"},
    )
    snapshot = await transport.request(request)
    assert snapshot.body == b"34567"
    assert snapshot.headers["content-range"] == "bytes 3-7/10"
    assert snapshot.interaction_id == "range-1+range-2"


@pytest.mark.asyncio
async def test_range_rejects_gaps_and_mixed_versions(tmp_path: Path) -> None:
    one = CanonicalRequest(SourceId.SENTINEL_COGS, "GET", COG_URL, {"Range": "bytes=0-4"})
    three = CanonicalRequest(SourceId.SENTINEL_COGS, "GET", COG_URL, {"Range": "bytes=6-9"})
    transport = FixtureTransport(
        tmp_path,
        [
            interaction(tmp_path, "v1-a", one, b"01234", etag='"v1"'),
            interaction(tmp_path, "v2-a", one, b"abcde", etag='"v2"'),
            interaction(tmp_path, "v1-b", three, b"6789", etag='"v1"'),
        ],
    )
    gap = CanonicalRequest(SourceId.SENTINEL_COGS, "GET", COG_URL, {"Range": "bytes=3-7"})
    with pytest.raises(FixtureMiss):
        await transport.request(gap)
    overlap = CanonicalRequest(SourceId.SENTINEL_COGS, "GET", COG_URL, {"Range": "bytes=1-2"})
    with pytest.raises(AmbiguousFixture):
        await transport.request(overlap)
