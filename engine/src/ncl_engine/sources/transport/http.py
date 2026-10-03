"""Small allowlisted HTTP transport for explicit live/record modes."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .errors import SourcePolicyError, UpstreamResponseError
from .models import (
    MAX_COG_RANGE_BYTES,
    CanonicalRequest,
    SnapshotOrigin,
    SourceId,
    SourceSnapshot,
    parse_range,
)

SAFE_RESPONSE_HEADERS = frozenset(
    {
        "accept-ranges",
        "cache-control",
        "content-length",
        "content-range",
        "content-type",
        "date",
        "etag",
        "last-modified",
        "retry-after",
        "server",
    }
)
SOURCE_HOSTS: Mapping[SourceId, frozenset[str]] = {
    SourceId.CELESTRAK: frozenset({"celestrak.org"}),
    SourceId.EARTH_SEARCH: frozenset({"earth-search.aws.element84.com"}),
    SourceId.SENTINEL_COGS: frozenset({"sentinel-cogs.s3.us-west-2.amazonaws.com"}),
    SourceId.JPL_DE421: frozenset(),
}
SOURCE_MAX_BYTES: Mapping[SourceId, int] = {
    SourceId.CELESTRAK: 512 * 1024,
    SourceId.EARTH_SEARCH: 4 * 1024 * 1024,
    SourceId.SENTINEL_COGS: MAX_COG_RANGE_BYTES,
    SourceId.JPL_DE421: 0,
}
USER_AGENT = "NextClearLook/0.1 (+https://github.com/ong6/next-clear-look)"


def _safe_headers(headers: object) -> dict[str, str]:
    return {
        str(name).lower(): str(value).strip()
        for name, value in headers.items()  # type: ignore[attr-defined]
        if str(name).lower() in SAFE_RESPONSE_HEADERS
    }


class AllowlistedHttpTransport:
    """Perform one bounded request; retry policy belongs to typed adapters."""

    def __init__(self, *, timeout_seconds: float = 45.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        return await asyncio.to_thread(self._request_sync, request)

    def _request_sync(self, request: CanonicalRequest) -> SourceSnapshot:
        parsed = urlsplit(request.url)
        allowed = SOURCE_HOSTS[request.source_id]
        if parsed.scheme != "https" or parsed.hostname not in allowed:
            raise SourcePolicyError(
                f"{request.source_id.value} does not allow {parsed.scheme}://{parsed.hostname}"
            )
        outgoing = {
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
            **dict(request.headers),
        }
        raw_request = urllib.request.Request(
            request.url,
            data=request.body or None,
            headers=outgoing,
            method=request.method,
        )
        try:
            with urllib.request.urlopen(raw_request, timeout=self._timeout_seconds) as response:
                final = urlsplit(response.geturl())
                if final.scheme != "https" or final.hostname not in allowed:
                    raise SourcePolicyError("upstream redirect left the source allowlist")
                headers = _safe_headers(response.headers)
                declared = headers.get("content-length")
                limit = SOURCE_MAX_BYTES[request.source_id]
                if declared is not None and int(declared) > limit:
                    raise UpstreamResponseError(
                        f"declared response size {declared} exceeds {limit} bytes"
                    )
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise UpstreamResponseError(f"response exceeds {limit} bytes")
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raise UpstreamResponseError(
                f"{request.source_id.value} returned HTTP {exc.code}; no implicit retry"
            ) from exc
        except urllib.error.URLError as exc:
            raise UpstreamResponseError(
                f"{request.source_id.value} request failed; no implicit retry: {exc.reason}"
            ) from exc
        self._validate(request, status, headers, body)
        return SourceSnapshot(
            source_id=request.source_id,
            request=request,
            retrieved_at=datetime.now(UTC),
            status=status,
            headers=headers,
            body=body,
            origin=SnapshotOrigin.NETWORK,
        )

    @staticmethod
    def _validate(
        request: CanonicalRequest, status: int, headers: Mapping[str, str], body: bytes
    ) -> None:
        if "range" not in request.headers:
            if status != 200:
                raise UpstreamResponseError(f"expected HTTP 200, got {status}")
            return
        if status != 206:
            raise UpstreamResponseError(f"range request requires HTTP 206, got {status}")
        start, end = parse_range(request.headers["range"])
        expected_length = end - start + 1
        if len(body) != expected_length:
            raise UpstreamResponseError(
                f"range returned {len(body)} bytes, expected {expected_length}"
            )
        content_range = headers.get("content-range", "")
        if not content_range.startswith(f"bytes {start}-{end}/"):
            raise UpstreamResponseError(f"Content-Range does not match request: {content_range!r}")
