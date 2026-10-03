from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ncl_engine.sources.live import LiveSourceAdapters, parse_stac_item
from ncl_engine.sources.transport import (
    CanonicalRequest,
    SnapshotOrigin,
    SourceSnapshot,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _raw_item(**property_updates: object) -> dict[str, Any]:
    properties = {
        "datetime": "2026-10-02T04:42:30Z",
        "platform": "sentinel-2a",
        "eo:cloud_cover": 12.5,
        "grid:code": "MGRS-48NUG",
        "sat:relative_orbit": 118,
        "s2:datatake_id": "GS2A_TEST",
        **property_updates,
    }
    return {
        "id": "S2A_TEST",
        "collection": "sentinel-2-l2a",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[103.6, 1.2], [103.8, 1.2], [103.8, 1.4], [103.6, 1.2]]],
        },
        "assets": {
            "scl": {"href": "https://example.test/SCL.tif"},
            "visual": {"href": "https://example.test/TCI.tif"},
        },
        "links": [{"rel": "self", "href": "https://example.test/items/S2A_TEST"}],
    }


def _snapshot(request: CanonicalRequest, payload: object) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=request.source_id,
        request=request,
        retrieved_at=NOW,
        status=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode(),
        origin=SnapshotOrigin.NETWORK,
    )


class Transport:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.requests: list[CanonicalRequest] = []

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        self.requests.append(request)
        return _snapshot(request, self.payloads.pop(0))


def test_parse_stac_item_datatake_assets_and_relative_orbit_fallback() -> None:
    item = parse_stac_item(_raw_item(), None)
    assert item.datatake_id == "GS2A_TEST"
    assert item.tile == "48NUG"
    assert item.relative_orbit == 118
    assert item.stac_self_url.endswith("S2A_TEST")

    raw = _raw_item(**{"sat:relative_orbit": None, "s2:product_uri": "X_R033_TEST"})
    raw["links"] = []
    item = parse_stac_item(raw, None)
    assert item.relative_orbit == 33
    assert "earth-search.aws.element84.com" in item.stac_self_url


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw.pop("properties"), "properties"),
        (lambda raw: raw.pop("geometry"), "geometry"),
        (lambda raw: raw["properties"].update(platform="landsat-8"), "unsupported"),
        (lambda raw: raw["assets"].pop("scl"), "missing the scl"),
    ],
)
def test_parse_stac_item_rejects_bad_catalogue_records(mutation: object, message: str) -> None:
    raw = _raw_item()
    mutation(raw)  # type: ignore[operator]
    with pytest.raises(ValueError, match=message):
        parse_stac_item(raw, None)


@pytest.mark.asyncio
async def test_search_scenes_follows_post_pagination_and_skips_bad_features() -> None:
    first = {
        "features": [_raw_item(), {"id": "bad"}],
        "links": [
            {
                "rel": "next",
                "href": "https://earth-search.aws.element84.com/v1/search",
                "method": "POST",
                "body": {"token": "next"},
            }
        ],
    }
    second = {"features": [_raw_item(datetime="2026-09-30T04:42:30Z")], "links": []}
    transport = Transport([first, second])
    items = await LiveSourceAdapters(transport).search_scenes(
        _raw_item()["geometry"], NOW - timedelta(days=30), NOW
    )
    assert len(items) == 2
    assert items[0].acquisition_time > items[1].acquisition_time
    assert len(transport.requests) == 2
    assert json.loads(transport.requests[1].body) == {"token": "next"}


@pytest.mark.asyncio
async def test_search_scenes_rejects_malformed_response_and_pagination_loop() -> None:
    adapter = LiveSourceAdapters(Transport([["not-an-object"]]))
    with pytest.raises(ValueError, match="must be an object"):
        await adapter.search_scenes(_raw_item()["geometry"], NOW - timedelta(days=1), NOW)

    next_link = {
        "rel": "next",
        "href": "https://earth-search.aws.element84.com/v1/search",
        "method": "GET",
    }
    transport = Transport(
        [
            {"features": [], "links": [next_link]},
            {"features": [], "links": [next_link]},
        ]
    )
    with pytest.raises(ValueError, match="pagination loop"):
        await LiveSourceAdapters(transport).search_scenes(
            _raw_item()["geometry"], NOW - timedelta(days=1), NOW
        )
