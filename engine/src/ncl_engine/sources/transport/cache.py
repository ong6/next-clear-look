"""Durable content-addressed response cache with CelesTrak's two-hour floor."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .blobs import put_blob, read_blob
from .errors import SourcePolicyError
from .models import CanonicalRequest, SnapshotOrigin, SourceId, SourceSnapshot, canonical_json
from .protocols import DataTransport

DEFAULT_TTLS: Mapping[SourceId, timedelta] = {
    SourceId.CELESTRAK: timedelta(hours=2),
    SourceId.EARTH_SEARCH: timedelta(minutes=15),
    # Validated COG versions are immutable; cache them without a time expiry.
    SourceId.SENTINEL_COGS: timedelta.max,
    SourceId.JPL_DE421: timedelta.max,
}


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class CacheTransport:
    """Return validated cache entries and atomically populate misses."""

    def __init__(
        self,
        upstream: DataTransport,
        cache_dir: Path,
        *,
        ttls: Mapping[SourceId, timedelta] | None = None,
        read_enabled: bool = True,
        refresh_stale: bool = True,
    ) -> None:
        self._upstream = upstream
        self._root = cache_dir
        self._entries = cache_dir / "entries"
        self._blobs = cache_dir / "blobs"
        self._locks = cache_dir / "locks"
        self._ttls = dict(DEFAULT_TTLS if ttls is None else ttls)
        self._read_enabled = read_enabled
        self._refresh_stale = refresh_stale
        self._process_locks: dict[str, threading.Lock] = {}
        self._celestrak_failed = False

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        key = request.key()
        lock = self._process_locks.setdefault(key, threading.Lock())
        await asyncio.to_thread(lock.acquire)
        try:
            # The file lock extends across the fetch so separate workers cannot double-fetch.
            with _exclusive_file_lock(self._locks / f"{key}.lock"):
                cached = self._read(request)
                if cached is not None and self._is_fresh(cached):
                    if self._read_enabled:
                        return cached
                    if request.source_id is SourceId.CELESTRAK:
                        raise SourcePolicyError(
                            "CelesTrak recording refused: the canonical query succeeded "
                            "less than two hours ago"
                        )
                if cached is not None and self._read_enabled and not self._refresh_stale:
                    return self._as_stale(cached)
                if request.source_id is SourceId.CELESTRAK and self._celestrak_failed:
                    if cached is not None and self._read_enabled:
                        return self._as_stale(cached)
                    raise RuntimeError("CelesTrak refresh already failed in this process")
                try:
                    network = await self._upstream.request(request)
                except Exception:
                    if request.source_id is SourceId.CELESTRAK:
                        self._celestrak_failed = True
                    if cached is not None and self._read_enabled:
                        return self._as_stale(cached)
                    raise
                self._write(network)
                return network
        finally:
            lock.release()

    def _entry_path(self, key: str) -> Path:
        return self._entries / key[:2] / f"{key}.json"

    def _is_fresh(self, snapshot: SourceSnapshot) -> bool:
        ttl = self._ttls[snapshot.source_id]
        return datetime.now(UTC) - snapshot.retrieved_at < ttl

    @staticmethod
    def _as_stale(snapshot: SourceSnapshot) -> SourceSnapshot:
        headers = dict(snapshot.headers)
        headers["x-ncl-cache-stale"] = "true"
        return SourceSnapshot(
            source_id=snapshot.source_id,
            request=snapshot.request,
            retrieved_at=snapshot.retrieved_at,
            status=snapshot.status,
            headers=headers,
            body=snapshot.body,
            origin=SnapshotOrigin.CACHE,
            body_path=snapshot.body_path,
        )

    def _read(self, request: CanonicalRequest) -> SourceSnapshot | None:
        entry_path = self._entry_path(request.key())
        if not entry_path.exists():
            return None
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        if entry["request_key_sha256"] != request.key():
            return None
        body = read_blob(self._blobs, entry["body_sha256"], int(entry["body_size"]))
        return SourceSnapshot(
            source_id=SourceId(entry["source_id"]),
            request=request,
            retrieved_at=datetime.fromisoformat(entry["retrieved_at"].replace("Z", "+00:00")),
            status=int(entry["status"]),
            headers=entry["headers"],
            body=body,
            origin=SnapshotOrigin.CACHE,
            body_path=str(self._blobs / entry["body_path"]),
        )

    def _write(self, snapshot: SourceSnapshot) -> None:
        digest, relative = put_blob(self._blobs, snapshot.body)
        entry = {
            "body_path": relative.as_posix(),
            "body_sha256": digest,
            "body_size": len(snapshot.body),
            "headers": dict(snapshot.headers),
            "request_key_sha256": snapshot.request.key(),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
            "source_id": snapshot.source_id.value,
            "status": snapshot.status,
        }
        destination = self._entry_path(snapshot.request.key())
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        temporary.write_bytes(canonical_json(entry) + b"\n")
        os.replace(temporary, destination)
