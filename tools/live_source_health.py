#!/usr/bin/env python3
"""One bounded Earth Search probe for the non-blocking scheduled workflow."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from ncl_engine.sources.transport import (
    AllowlistedHttpTransport,
    CanonicalRequest,
    PoliteTransport,
    SourceId,
)
from ncl_engine.sources.transport.models import canonical_json


async def probe() -> dict[str, object]:
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(days=1)
    body = canonical_json(
        {
            "collections": ["sentinel-2-l2a"],
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "fields": {"include": ["id", "assets.scl.href"]},
            "intersects": {
                "coordinates": [
                    [
                        [103.62, 1.24],
                        [103.77, 1.24],
                        [103.77, 1.36],
                        [103.62, 1.36],
                        [103.62, 1.24],
                    ]
                ],
                "type": "Polygon",
            },
            "limit": 1,
        }
    )
    request = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "POST",
        "https://earth-search.aws.element84.com/v1/search",
        {"Accept": "application/geo+json", "Content-Type": "application/json"},
        body,
    )
    response = await PoliteTransport(AllowlistedHttpTransport()).request(request)
    payload = json.loads(response.body)
    features = payload.get("features", [])
    cog_status: int | None = None
    if features:
        cog_request = CanonicalRequest(
            SourceId.SENTINEL_COGS,
            "GET",
            features[0]["assets"]["scl"]["href"],
            {"Accept": "image/tiff", "Range": "bytes=0-0"},
        )
        cog = await PoliteTransport(AllowlistedHttpTransport()).request(cog_request)
        cog_status = cog.status
    return {"cog_status": cog_status, "items": len(features), "status": response.status}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(probe()), sort_keys=True))
