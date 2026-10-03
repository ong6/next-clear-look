"""Fail-closed fixture replay with exact JSON and coverage-based COG ranges."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .blobs import read_blob
from .errors import AmbiguousFixture, FixtureIntegrityError, FixtureMiss
from .models import (
    CanonicalRequest,
    SnapshotOrigin,
    SourceId,
    SourceSnapshot,
    normalize_range,
    normalize_url,
    parse_range,
)


@dataclass(frozen=True, slots=True)
class _StoredRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body_sha256: str
    request_key_sha256: str


@dataclass(frozen=True, slots=True)
class _Interaction:
    identifier: str
    source_id: SourceId
    request: _StoredRequest
    retrieved_at: datetime
    status: int
    response_headers: Mapping[str, str]
    body_sha256: str
    body_size: int

    @property
    def etag(self) -> str | None:
        return self.response_headers.get("etag")


def _parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixtureIntegrityError(f"fixture timestamp lacks a timezone: {value}")
    return parsed.astimezone(UTC)


def _load_interaction(raw: Mapping[str, Any]) -> _Interaction:
    request_data = raw["request"]
    method = str(request_data["method"])
    url = str(request_data["url"])
    headers = {str(k).lower(): str(v) for k, v in request_data.get("headers", {}).items()}
    if method != method.upper() or normalize_url(url) != url:
        raise FixtureIntegrityError(
            f"interaction {raw.get('id', '<unknown>')} request is not canonical"
        )
    if "range" in headers and normalize_range(headers["range"]) != headers["range"]:
        raise FixtureIntegrityError(
            f"interaction {raw.get('id', '<unknown>')} range is not canonical"
        )
    body_digest = str(request_data["body_sha256"])
    request_key = str(request_data["request_key_sha256"])
    for label, digest in (("body", body_digest), ("request", request_key)):
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise FixtureIntegrityError(
                f"interaction {raw.get('id', '<unknown>')} has an invalid {label} digest"
            )
    source_id = SourceId(raw["source_id"])
    request = _StoredRequest(method, url, headers, body_digest, request_key)
    response = raw["response"]
    body_ref = response["body"]
    return _Interaction(
        identifier=str(raw["id"]),
        source_id=source_id,
        request=request,
        retrieved_at=_parse_instant(response["retrieved_at"]),
        status=int(response["status"]),
        response_headers={str(k).lower(): str(v) for k, v in response["headers"].items()},
        body_sha256=str(body_ref["sha256"]),
        body_size=int(body_ref["size"]),
    )


class FixtureTransport:
    """Read snapshots from checked-in manifests without a network fallback."""

    def __init__(self, blob_root: Path, interactions: Iterable[Mapping[str, Any]]) -> None:
        self._blob_root = blob_root
        self._interactions = tuple(_load_interaction(raw) for raw in interactions)
        identifiers = [item.identifier for item in self._interactions]
        if len(identifiers) != len(set(identifiers)):
            raise FixtureIntegrityError("fixture interaction IDs must be unique")

    @classmethod
    def from_path(cls, fixture_set_path: Path) -> FixtureTransport:
        fixture_set_path = fixture_set_path.resolve()
        root = fixture_set_path.parent
        fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
        interactions: list[Mapping[str, Any]] = list(fixture_set.get("interactions", []))
        for preset in fixture_set.get("presets", []):
            if preset["manifest"] is None:
                continue
            manifest_path = root / preset["manifest"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            interactions.extend(manifest.get("interactions", []))
        return cls(root / "blobs", interactions)

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        if "range" in request.headers:
            return self._range_request(request)
        matches = [
            item
            for item in self._interactions
            if item.source_id == request.source_id
            and item.request.request_key_sha256 == request.key()
        ]
        if not matches:
            raise FixtureMiss(
                f"fixture miss; network fallback is forbidden: {request.method} {request.url} "
                f"({request.key()})"
            )
        if len(matches) != 1:
            raise AmbiguousFixture(f"multiple exact responses for request {request.key()}")
        return self._snapshot(matches[0], request)

    def _snapshot(self, interaction: _Interaction, request: CanonicalRequest) -> SourceSnapshot:
        body = read_blob(self._blob_root, interaction.body_sha256, interaction.body_size)
        return SourceSnapshot(
            source_id=interaction.source_id,
            request=request,
            retrieved_at=interaction.retrieved_at,
            status=interaction.status,
            headers=interaction.response_headers,
            body=body,
            origin=SnapshotOrigin.FIXTURE,
            interaction_id=interaction.identifier,
            body_path=str(
                self._blob_root / "sha256" / interaction.body_sha256[:2] / interaction.body_sha256
            ),
        )

    def _range_request(self, request: CanonicalRequest) -> SourceSnapshot:
        requested_start, requested_end = parse_range(request.headers["range"])
        candidates = [
            item
            for item in self._interactions
            if item.source_id == request.source_id
            and item.request.method == request.method
            and item.request.url == request.url
            and item.request.headers.get("accept") == request.headers.get("accept")
            and "range" in item.request.headers
            and item.status == 206
            and item.etag
        ]
        by_etag: dict[str, list[_Interaction]] = {}
        for item in candidates:
            assert item.etag is not None
            by_etag.setdefault(item.etag, []).append(item)

        covered: list[tuple[str, bytes, list[_Interaction], int | None]] = []
        for etag, version_items in by_etag.items():
            result = self._assemble_range(version_items, requested_start, requested_end)
            if result is not None:
                body, used, total = result
                covered.append((etag, body, used, total))
        if not covered:
            raise FixtureMiss(
                f"recorded bytes do not cover {request.headers['range']} for {request.url}; "
                "network fallback is forbidden"
            )
        if len(covered) != 1:
            raise AmbiguousFixture(
                f"more than one recorded ETag covers {request.headers['range']} for {request.url}"
            )
        etag, body, used, total = covered[0]
        newest = max(used, key=lambda item: item.retrieved_at)
        headers = dict(newest.response_headers)
        headers["etag"] = etag
        headers["content-length"] = str(len(body))
        total_text = str(total) if total is not None else "*"
        headers["content-range"] = f"bytes {requested_start}-{requested_end}/{total_text}"
        return SourceSnapshot(
            source_id=request.source_id,
            request=request,
            retrieved_at=newest.retrieved_at,
            status=206,
            headers=headers,
            body=body,
            origin=SnapshotOrigin.FIXTURE,
            interaction_id="+".join(item.identifier for item in used),
        )

    def _assemble_range(
        self, items: list[_Interaction], requested_start: int, requested_end: int
    ) -> tuple[bytes, list[_Interaction], int | None] | None:
        segments: list[tuple[int, int, bytes, _Interaction, int | None]] = []
        for item in items:
            start, end = parse_range(item.request.headers["range"])
            body = read_blob(self._blob_root, item.body_sha256, item.body_size)
            if len(body) != end - start + 1:
                raise FixtureIntegrityError(
                    f"range body length mismatch for interaction {item.identifier}"
                )
            content_range = item.response_headers.get("content-range", "")
            total: int | None = None
            if "/" in content_range and content_range.rsplit("/", 1)[1] != "*":
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError as exc:
                    raise FixtureIntegrityError(
                        f"invalid Content-Range in interaction {item.identifier}"
                    ) from exc
            segments.append((start, end, body, item, total))
        segments.sort(key=lambda segment: (segment[0], segment[1]))
        cursor = requested_start
        chunks: list[bytes] = []
        used: list[_Interaction] = []
        totals: set[int] = set()
        while cursor <= requested_end:
            options = [segment for segment in segments if segment[0] <= cursor <= segment[1]]
            if not options:
                return None
            # Prefer the segment extending furthest, which minimizes joins deterministically.
            start, end, body, item, total = max(options, key=lambda segment: segment[1])
            take_end = min(end, requested_end)
            chunks.append(body[cursor - start : take_end - start + 1])
            if item not in used:
                used.append(item)
            if total is not None:
                totals.add(total)
            cursor = take_end + 1
        if len(totals) > 1:
            raise FixtureIntegrityError("recorded ranges disagree on total object length")
        combined = b"".join(chunks)
        return combined, used, next(iter(totals), None)
