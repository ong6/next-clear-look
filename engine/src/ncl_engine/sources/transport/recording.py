"""Recording wrapper that preserves exact response bytes and request identities."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC
from pathlib import Path
from typing import Any

from .blobs import put_blob
from .models import CanonicalRequest, SourceSnapshot
from .protocols import DataTransport


class RecordingTransport:
    """Wrap the live transport directly; callers must not put a read cache beneath it."""

    def __init__(self, upstream: DataTransport, blob_root: Path) -> None:
        self._upstream = upstream
        self._blob_root = blob_root
        self._interactions: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._completed: dict[str, SourceSnapshot] = {}
        self._failures: dict[str, BaseException] = {}
        self._inflight: dict[str, threading.Event] = {}

    @property
    def interactions(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(self._interactions)

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        key = request.key()
        with self._lock:
            completed = self._completed.get(key)
            if completed is not None:
                return completed
            failure = self._failures.get(key)
            if failure is not None:
                raise failure
            event = self._inflight.get(key)
            leader = event is None
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
        if not leader:
            await asyncio.to_thread(event.wait)
            with self._lock:
                failure = self._failures.get(key)
                if failure is not None:
                    raise failure
                return self._completed[key]
        try:
            snapshot = await self._upstream.request(request)
            recorded = self._record(request, snapshot)
        except BaseException as exc:
            with self._lock:
                self._failures[key] = exc
                self._inflight.pop(key).set()
            raise
        with self._lock:
            self._completed[key] = recorded
            self._inflight.pop(key).set()
        return recorded

    def _record(self, request: CanonicalRequest, snapshot: SourceSnapshot) -> SourceSnapshot:
        digest, relative = put_blob(self._blob_root, snapshot.body)
        request_body: dict[str, object] | None = None
        if request.body:
            request_digest, request_relative = put_blob(self._blob_root, request.body)
            request_body = {
                "path": request_relative.as_posix(),
                "sha256": request_digest,
                "size": len(request.body),
            }
        with self._lock:
            index = len(self._interactions) + 1
            identifier = f"{request.source_id.value}-{index:04d}-{request.key()[:12]}"
            self._interactions.append(
                {
                    "id": identifier,
                    "origin": snapshot.origin.value,
                    "source_id": request.source_id.value,
                    "request": {
                        **request.identity(),
                        **({"body": request_body} if request_body is not None else {}),
                        "request_key_sha256": request.key(),
                    },
                    "response": {
                        "body": {
                            "path": relative.as_posix(),
                            "sha256": digest,
                            "size": len(snapshot.body),
                        },
                        "headers": dict(snapshot.headers),
                        "retrieved_at": snapshot.retrieved_at.astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "status": snapshot.status,
                    },
                }
            )
        return SourceSnapshot(
            source_id=snapshot.source_id,
            request=request,
            retrieved_at=snapshot.retrieved_at,
            status=snapshot.status,
            headers=snapshot.headers,
            body=snapshot.body,
            origin=snapshot.origin,
            interaction_id=identifier,
            body_path=str(self._blob_root / relative),
        )
