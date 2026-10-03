"""Canonical source requests and immutable response snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import InvalidRequest

MAX_COG_RANGE_BYTES = 8 * 1024 * 1024

_IDENTITY_HEADERS = frozenset({"accept", "content-type", "range"})
_RANGE_RE = re.compile(r"bytes=(0|[1-9][0-9]*)-(0|[1-9][0-9]*)\Z", re.IGNORECASE)
_SIGNED_QUERY_NAMES = frozenset(
    {
        "x-amz-algorithm",
        "x-amz-credential",
        "x-amz-date",
        "x-amz-expires",
        "x-amz-security-token",
        "x-amz-signature",
        "sig",
        "signature",
        "token",
    }
)


class SourceId(StrEnum):
    """The only upstream identifiers used by Next Clear Look."""

    CELESTRAK = "celestrak"
    EARTH_SEARCH = "earth-search"
    SENTINEL_COGS = "sentinel-cogs"
    JPL_DE421 = "jpl-de421"


class SnapshotOrigin(StrEnum):
    NETWORK = "network"
    CACHE = "cache"
    FIXTURE = "fixture"


def canonical_json(value: Any) -> bytes:
    """Encode finite JSON deterministically."""

    def reject_constants(value: str) -> None:
        raise InvalidRequest(f"non-finite JSON number is forbidden: {value}")

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidRequest(f"request body is not canonical JSON: {exc}") from exc
    # Keep the decoder check explicit: it also rejects a custom encoder ever emitting NaN.
    json.loads(encoded, parse_constant=reject_constants)
    return encoded.encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidRequest("source URL must use http or https")
    if not parsed.hostname:
        raise InvalidRequest("source URL must contain a host")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidRequest("source URL must not contain user-info")
    if parsed.fragment:
        raise InvalidRequest("source URL must not contain a fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidRequest(f"invalid source URL port: {exc}") from exc
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (parsed.scheme.lower() == "https" and port == 443) or (
        parsed.scheme.lower() == "http" and port == 80
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=False)
    for name, _ in query_pairs:
        if name.lower() in _SIGNED_QUERY_NAMES:
            raise InvalidRequest(f"signed or secret query parameter is forbidden: {name}")
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", query, ""))


def normalize_range(value: str) -> str:
    match = _RANGE_RE.fullmatch(value.strip())
    if match is None:
        raise InvalidRequest("Range must be one closed byte range: bytes=<start>-<end>")
    start, end = (int(part) for part in match.groups())
    if end < start:
        raise InvalidRequest("Range end must be greater than or equal to its start")
    return f"bytes={start}-{end}"


def parse_range(value: str) -> tuple[int, int]:
    normalized = normalize_range(value)
    start_text, end_text = normalized[6:].split("-", 1)
    return int(start_text), int(end_text)


def _normalize_headers(headers: Mapping[str, str] | None) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for raw_name, raw_value in (headers or {}).items():
        name = raw_name.strip().lower()
        if name not in _IDENTITY_HEADERS:
            continue
        value = " ".join(raw_value.strip().split())
        if name == "range":
            value = normalize_range(value)
        normalized[name] = value
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    """A source request with one stable identity across live, record and replay."""

    source_id: SourceId
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def __post_init__(self) -> None:
        method = self.method.strip().upper()
        if not method or not re.fullmatch(r"[A-Z]+", method):
            raise InvalidRequest(f"invalid HTTP method: {self.method!r}")
        url = normalize_url(self.url)
        headers = _normalize_headers(self.headers)
        body = bytes(self.body)
        content_type = headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type in {"application/json", "application/geo+json"} and body:
            try:
                parsed = json.loads(body.decode("utf-8"), parse_constant=self._reject_constant)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InvalidRequest(f"JSON request body is invalid: {exc}") from exc
            body = canonical_json(parsed)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "headers", headers)
        object.__setattr__(self, "body", body)

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise InvalidRequest(f"non-finite JSON number is forbidden: {value}")

    @property
    def body_sha256(self) -> str:
        return sha256_bytes(self.body)

    def identity(self) -> dict[str, Any]:
        return {
            "body_sha256": self.body_sha256,
            "headers": dict(self.headers),
            "method": self.method,
            "url": self.url,
        }

    def key(self) -> str:
        """Return the canonical request-key digest."""

        return sha256_bytes(canonical_json(self.identity()))


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Validated immutable bytes returned by any transport implementation."""

    source_id: SourceId
    request: CanonicalRequest
    retrieved_at: datetime
    status: int
    headers: Mapping[str, str]
    body: bytes
    origin: SnapshotOrigin
    interaction_id: str | None = None
    body_path: str | None = None

    def __post_init__(self) -> None:
        instant = self.retrieved_at
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if not 100 <= self.status <= 599:
            raise ValueError(f"invalid HTTP status: {self.status}")
        headers = MappingProxyType(
            {str(name).lower(): str(value).strip() for name, value in self.headers.items()}
        )
        object.__setattr__(self, "retrieved_at", instant.astimezone(UTC))
        object.__setattr__(self, "headers", headers)
        object.__setattr__(self, "body", bytes(self.body))

    @property
    def request_key_sha256(self) -> str:
        return self.request.key()

    @property
    def body_sha256(self) -> str:
        return sha256_bytes(self.body)

    @property
    def body_size(self) -> int:
        return len(self.body)

    def with_origin(self, origin: SnapshotOrigin) -> SourceSnapshot:
        return SourceSnapshot(
            source_id=self.source_id,
            request=self.request,
            retrieved_at=self.retrieved_at,
            status=self.status,
            headers=self.headers,
            body=self.body,
            origin=origin,
            interaction_id=self.interaction_id,
            body_path=self.body_path,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_finite(value: float) -> float:
    """Small shared guard for metadata parsers."""

    if not math.isfinite(value):
        raise InvalidRequest("non-finite number")
    return value
