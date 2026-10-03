"""Live CelesTrak and Earth Search adapters over DataTransport."""

from __future__ import annotations

import asyncio
import json
import random
import re
import urllib.error
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

from ncl_engine.domain.models import Geometry
from ncl_engine.orbit.omm import OmmRecord, parse_omm_catalogue
from ncl_engine.raster.stac import stac_search_body
from ncl_engine.sources.protocols import StacItem
from ncl_engine.sources.transport import (
    CanonicalRequest,
    DataTransport,
    SourceId,
    SourceSnapshot,
    UpstreamResponseError,
)

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?NAME=SENTINEL-2&FORMAT=JSON"
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"


def _instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"STAC datetime lacks timezone: {value}")
    return parsed.astimezone(UTC)


def _self_url(item: Mapping[str, Any]) -> str:
    for link in item.get("links", []):
        if isinstance(link, Mapping) and link.get("rel") == "self":
            return str(link["href"])
    return (
        f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/{item['id']}"
    )


def _asset_href(item: Mapping[str, Any], name: str) -> str:
    assets = item.get("assets")
    if not isinstance(assets, Mapping) or name not in assets:
        raise ValueError(f"STAC Item {item.get('id')} is missing the {name} asset")
    asset = assets[name]
    if not isinstance(asset, Mapping) or not isinstance(asset.get("href"), str):
        raise ValueError(f"STAC Item {item.get('id')} has an invalid {name} asset")
    return str(asset["href"])


def parse_stac_item(raw: Mapping[str, Any], snapshot: SourceSnapshot | None) -> StacItem:
    properties = raw.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("STAC Item properties must be an object")
    geometry = raw.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ValueError("STAC Item geometry must be an object")
    platform = str(properties.get("platform", "")).lower()
    if platform not in {"sentinel-2a", "sentinel-2b", "sentinel-2c"}:
        raise ValueError(f"unsupported STAC platform: {platform}")
    tile = str(properties.get("mgrs:utm_zone", ""))
    grid = properties.get("grid:code")
    if isinstance(grid, str) and grid:
        tile = grid.removeprefix("MGRS-")
    if not tile:
        tile = str(properties.get("s2:mgrs_tile", "unknown"))
    cloud = properties.get("eo:cloud_cover")
    relative_orbit = properties.get("sat:relative_orbit")
    if relative_orbit is None:
        product_uri = properties.get("s2:product_uri")
        match = re.search(r"_R([0-9]{3})_", str(product_uri)) if product_uri else None
        relative_orbit = int(match.group(1)) if match else None
    return StacItem(
        id=str(raw["id"]),
        collection=str(raw.get("collection", "sentinel-2-l2a")),
        platform=platform,
        acquisition_time=_instant(properties["datetime"]),
        tile=tile,
        relative_orbit=int(relative_orbit) if relative_orbit is not None else None,
        geometry={str(key): value for key, value in geometry.items()},
        stac_self_url=_self_url(raw),
        assets={"scl": _asset_href(raw, "scl"), "visual": _asset_href(raw, "visual")},
        tile_cloud_cover_percent=float(cloud) if cloud is not None else None,
        raw=cast(Mapping[str, object], raw),
        snapshot=snapshot,
        datatake_id=(
            str(properties["s2:datatake_id"])
            if properties.get("s2:datatake_id") is not None
            else None
        ),
    )


class LiveSourceAdapters:
    def __init__(self, transport: DataTransport) -> None:
        self.transport = transport

    async def load_omm(self, observed_at: datetime) -> list[OmmRecord]:
        request = CanonicalRequest(
            source_id=SourceId.CELESTRAK,
            method="GET",
            url=CELESTRAK_URL,
            headers={"Accept": "application/json"},
        )
        snapshot = await self.transport.request(request)
        payload = json.loads(snapshot.body)
        # A recording may deliberately choose a frozen clock before the
        # network retrieval. OMM publication sanity is checked against the
        # snapshot retrieval; the pipeline separately enforces ±48 h to frozen_at.
        return parse_omm_catalogue(payload, observed_at=max(observed_at, snapshot.retrieved_at))

    async def _earth_search(self, request: CanonicalRequest) -> SourceSnapshot:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await self.transport.request(request)
            except UpstreamResponseError as exc:
                last_error = exc
                if attempt == 2:
                    break
                cause = exc.__cause__
                retry_after: float | None = None
                if isinstance(cause, urllib.error.HTTPError):
                    if cause.code != 429 and not 500 <= cause.code <= 599:
                        raise
                    raw_retry_after = cause.headers.get("Retry-After")
                    if raw_retry_after:
                        try:
                            retry_after = float(raw_retry_after)
                        except ValueError:
                            target = parsedate_to_datetime(raw_retry_after).astimezone(UTC)
                            retry_after = max(0.0, (target - datetime.now(UTC)).total_seconds())
                elif not isinstance(cause, urllib.error.URLError):
                    raise
                delay = min(
                    5.0,
                    retry_after if retry_after is not None else 0.25 * (2**attempt),
                )
                await asyncio.sleep(delay * (0.8 + 0.4 * random.random()))
        assert last_error is not None
        raise last_error

    async def search_scenes(
        self, geometry: Geometry, start: datetime, end: datetime
    ) -> list[StacItem]:
        body = stac_search_body(geometry, start, end)
        request = CanonicalRequest(
            source_id=SourceId.EARTH_SEARCH,
            method="POST",
            url=EARTH_SEARCH_URL,
            headers={"Accept": "application/geo+json", "Content-Type": "application/json"},
            body=json.dumps(body).encode("utf-8"),
        )
        output: list[StacItem] = []
        seen_pages: set[str] = set()
        while True:
            if request.key() in seen_pages:
                raise ValueError("Earth Search pagination loop detected")
            seen_pages.add(request.key())
            snapshot = await self._earth_search(request)
            response = json.loads(snapshot.body)
            if not isinstance(response, Mapping):
                raise ValueError("Earth Search response must be an object")
            features = response.get("features", [])
            if not isinstance(features, list):
                raise ValueError("Earth Search features must be an array")
            for raw in features:
                if not isinstance(raw, Mapping):
                    raise ValueError("Earth Search feature must be an object")
                try:
                    output.append(parse_stac_item(raw, snapshot))
                except ValueError:
                    continue
            next_link: Mapping[str, Any] | None = None
            for link in response.get("links", []):
                if isinstance(link, Mapping) and link.get("rel") == "next":
                    next_link = link
                    break
            if next_link is None:
                break
            method = str(next_link.get("method", "GET")).upper()
            next_body = next_link.get("body")
            request = CanonicalRequest(
                source_id=SourceId.EARTH_SEARCH,
                method=method,
                url=str(next_link["href"]),
                headers={
                    "Accept": "application/geo+json",
                    **({"Content-Type": "application/json"} if next_body is not None else {}),
                },
                body=json.dumps(next_body).encode("utf-8") if next_body is not None else b"",
            )
        output.sort(key=lambda item: (item.acquisition_time, item.id), reverse=True)
        return output
