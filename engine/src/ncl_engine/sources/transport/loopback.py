"""Loopback HTTP adapter through which GDAL/rasterio performs COG range reads."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import http.server
import os
import re
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import CancelledError, Future
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from .errors import TransportError
from .models import MAX_COG_RANGE_BYTES, CanonicalRequest, SourceId, parse_range
from .protocols import DataTransport

GDAL_ENVIRONMENT = {
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_INGESTED_BYTES_AT_OPEN": "16384",
}
_TOKEN_RE = re.compile(r"/[0-9a-f]{32}/[^/]+\.tif\Z")
_GDAL_ENVIRONMENT_LOCK = threading.RLock()
_GDAL_ENVIRONMENT_DEPTH = 0
_GDAL_ENVIRONMENT_PREVIOUS: dict[str, str | None] = {}


@contextlib.contextmanager
def gdal_environment() -> Iterator[dict[str, str]]:
    """Set all GDAL range-read policy in one place and restore the caller environment."""

    global _GDAL_ENVIRONMENT_DEPTH  # noqa: PLW0603
    with _GDAL_ENVIRONMENT_LOCK:
        if _GDAL_ENVIRONMENT_DEPTH == 0:
            _GDAL_ENVIRONMENT_PREVIOUS.clear()
            _GDAL_ENVIRONMENT_PREVIOUS.update(
                {key: os.environ.get(key) for key in GDAL_ENVIRONMENT}
            )
            os.environ.update(GDAL_ENVIRONMENT)
        _GDAL_ENVIRONMENT_DEPTH += 1
    try:
        yield dict(GDAL_ENVIRONMENT)
    finally:
        with _GDAL_ENVIRONMENT_LOCK:
            _GDAL_ENVIRONMENT_DEPTH -= 1
            if _GDAL_ENVIRONMENT_DEPTH == 0:
                for key, value in _GDAL_ENVIRONMENT_PREVIOUS.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                _GDAL_ENVIRONMENT_PREVIOUS.clear()


class LoopbackCogAdapter:
    """Expose registered COGs on 127.0.0.1 while forwarding only closed ranges."""

    def __init__(
        self, transport: DataTransport, *, max_range_bytes: int = MAX_COG_RANGE_BYTES
    ) -> None:
        self._transport = transport
        self._max_range_bytes = max_range_bytes
        self._assets: dict[str, str] = {}
        self._server: http.server.ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            self._owns_loop = True
        else:
            self._owns_loop = False
        self._loop_thread = (
            threading.Thread(target=self._loop.run_forever, daemon=True)
            if self._owns_loop
            else None
        )

    def register(self, remote_url: str) -> str:
        parsed = urlsplit(remote_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "sentinel-cogs.s3.us-west-2.amazonaws.com"
        ):
            raise ValueError("loopback COG URLs must map to the Sentinel COG allowlisted origin")
        token = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:32]
        filename = str(Path(parsed.path).name)
        if not filename.lower().endswith(".tif"):
            raise ValueError("loopback COG asset must end in .tif")
        path = f"/{token}/{quote(filename)}"
        self._assets[path] = remote_url
        if self._server is None:
            raise RuntimeError("start the loopback adapter before registering assets")
        host_value, port = self._server.server_address[:2]
        host = host_value.decode("ascii") if isinstance(host_value, bytes) else host_value
        return f"http://{host}:{port}{path}"

    def __enter__(self) -> LoopbackCogAdapter:
        adapter = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_HEAD(self) -> None:  # noqa: N802
                self._serve(head_only=True)

            def do_GET(self) -> None:  # noqa: N802
                self._serve(head_only=False)

            def _serve(self, *, head_only: bool) -> None:
                remote = adapter._assets.get(self.path)
                if remote is None or _TOKEN_RE.fullmatch(self.path) is None:
                    self.send_error(404)
                    return
                range_header = self.headers.get("Range")
                # GDAL commonly probes with HEAD. A one-byte range obtains authoritative size.
                requested_range = (
                    "bytes=0-0" if head_only and range_header is None else range_header
                )
                if requested_range is None:
                    self.send_error(400, "a closed Range header is required")
                    return
                try:
                    start, end = parse_range(requested_range)
                    if end - start + 1 > adapter._max_range_bytes:
                        self.send_error(416, "range exceeds adapter limit")
                        return
                    request = CanonicalRequest(
                        source_id=SourceId.SENTINEL_COGS,
                        method="GET",
                        url=remote,
                        headers={"Accept": "image/tiff", "Range": requested_range},
                    )
                    future: Future[Any] = asyncio.run_coroutine_threadsafe(
                        adapter._transport.request(request), adapter._loop
                    )
                    # The transport owns request timeouts and retries. A timeout here would also
                    # count time waiting behind the four-read semaphore, abandon live work, and
                    # make GDAL retry while the original range request was still in flight.
                    snapshot = future.result()
                except (CancelledError, TransportError, ValueError) as exc:
                    print(
                        f"loopback COG request failed: {remote} {requested_range} "
                        f"({type(exc).__name__}: {exc})",
                        file=sys.stderr,
                        flush=True,
                    )
                    self.send_error(502, str(exc))
                    return
                total = snapshot.headers.get("content-range", "bytes 0-0/*").rsplit("/", 1)[-1]
                if head_only:
                    self.send_response(200)
                    self.send_header("Content-Length", total if total.isdigit() else "0")
                    self.send_header("Accept-Ranges", "bytes")
                    if "etag" in snapshot.headers:
                        self.send_header("ETag", snapshot.headers["etag"])
                    self.end_headers()
                    return
                self.send_response(206)
                for name in (
                    "content-type",
                    "content-range",
                    "accept-ranges",
                    "etag",
                    "last-modified",
                ):
                    if name in snapshot.headers:
                        self.send_header(name.title(), snapshot.headers[name])
                self.send_header("Content-Length", str(len(snapshot.body)))
                self.end_headers()
                self.wfile.write(snapshot.body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        if self._loop_thread is not None:
            self._loop_thread.start()
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)
        if self._owns_loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            assert self._loop_thread is not None
            self._loop_thread.join(timeout=5)
            self._loop.close()
