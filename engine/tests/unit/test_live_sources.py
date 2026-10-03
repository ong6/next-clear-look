from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime, timedelta
from email.message import Message

import pytest

from ncl_engine.sources.live import LiveSourceAdapters
from ncl_engine.sources.transport import (
    CanonicalRequest,
    SnapshotOrigin,
    SourceSnapshot,
    UpstreamResponseError,
)


class SequenceTransport:
    def __init__(self, outcomes: list[SourceSnapshot | Exception]) -> None:
        self.outcomes = outcomes
        self.requests: list[CanonicalRequest] = []

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def snapshot(request: CanonicalRequest, body: bytes, retrieved_at: datetime) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=request.source_id,
        request=request,
        retrieved_at=retrieved_at,
        status=200,
        headers={"content-type": "application/json"},
        body=body,
        origin=SnapshotOrigin.NETWORK,
    )


def http_error(code: int, retry_after: str | None = None) -> UpstreamResponseError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    cause = urllib.error.HTTPError("https://example.test", code, "error", headers, None)
    try:
        raise cause
    except urllib.error.HTTPError as caught:
        try:
            raise UpstreamResponseError(f"HTTP {code}") from caught
        except UpstreamResponseError as wrapped:
            return wrapped


@pytest.mark.asyncio
async def test_omm_epoch_is_validated_against_retrieval_not_back_selected_clock() -> None:
    request = CanonicalRequest(
        source_id="celestrak",  # type: ignore[arg-type]
        method="GET",
        url="https://celestrak.org/NORAD/elements/gp.php?NAME=SENTINEL-2&FORMAT=JSON",
        headers={"Accept": "application/json"},
    )
    payload = json.dumps(
        [
            {
                "OBJECT_NAME": "SENTINEL-2A",
                "NORAD_CAT_ID": 40697,
                "EPOCH": "2026-10-03T00:00:00",
                "MEAN_MOTION": 14.3,
                "ECCENTRICITY": 0.0001,
                "INCLINATION": 98.5,
                "RA_OF_ASC_NODE": 2.0,
                "ARG_OF_PERICENTER": 3.0,
                "MEAN_ANOMALY": 4.0,
                "BSTAR": 0.0,
                "MEAN_MOTION_DOT": 0.0,
                "MEAN_MOTION_DDOT": 0.0,
                "EPHEMERIS_TYPE": 0,
            }
        ]
    ).encode()
    retrieved = datetime(2026, 10, 3, 0, 1, tzinfo=UTC)
    transport = SequenceTransport([snapshot(request, payload, retrieved)])
    records = await LiveSourceAdapters(transport).load_omm(retrieved - timedelta(hours=24))
    assert records[0].epoch == datetime(2026, 10, 3, tzinfo=UTC)


@pytest.mark.asyncio
async def test_earth_search_retries_503_and_includes_trimmed_fields() -> None:
    request = CanonicalRequest(
        source_id="earth-search",  # type: ignore[arg-type]
        method="POST",
        url="https://earth-search.aws.element84.com/v1/search",
        headers={"Accept": "application/geo+json", "Content-Type": "application/json"},
        body=b"{}",
    )
    response = snapshot(request, b'{"features":[],"links":[]}', datetime.now(UTC))
    transport = SequenceTransport([http_error(503, "0"), response])
    adapter = LiveSourceAdapters(transport)
    end = datetime(2026, 10, 3, tzinfo=UTC)
    assert (
        await adapter.search_scenes(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            end - timedelta(days=1),
            end,
        )
        == []
    )
    assert len(transport.requests) == 2
    body = json.loads(transport.requests[0].body)
    assert "fields" in body
    assert "query" not in body


@pytest.mark.asyncio
async def test_earth_search_does_not_retry_400() -> None:
    transport = SequenceTransport([http_error(400)])
    adapter = LiveSourceAdapters(transport)
    end = datetime(2026, 10, 3, tzinfo=UTC)
    with pytest.raises(UpstreamResponseError):
        await adapter.search_scenes(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            end - timedelta(days=1),
            end,
        )
    assert len(transport.requests) == 1
