"""Global source concurrency and retry limits."""

from __future__ import annotations

import asyncio

from .errors import UpstreamResponseError
from .models import CanonicalRequest, SourceId, SourceSnapshot
from .protocols import DataTransport

COG_ATTEMPTS = 3


class PoliteTransport:
    """Bound concurrent catalogue and COG work; CelesTrak is single-flight."""

    def __init__(self, upstream: DataTransport) -> None:
        self._upstream = upstream
        self._limits = {
            SourceId.CELESTRAK: asyncio.Semaphore(1),
            SourceId.EARTH_SEARCH: asyncio.Semaphore(2),
            SourceId.SENTINEL_COGS: asyncio.Semaphore(4),
            SourceId.JPL_DE421: asyncio.Semaphore(1),
        }

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        semaphore = self._limits[request.source_id]
        async with semaphore:
            attempts = COG_ATTEMPTS if request.source_id is SourceId.SENTINEL_COGS else 1
            attempt = 0
            while True:
                try:
                    return await self._upstream.request(request)
                except UpstreamResponseError:
                    attempt += 1
                    if attempt == attempts:
                        raise
                    await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
