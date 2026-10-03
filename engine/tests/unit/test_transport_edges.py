from __future__ import annotations

import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from ncl_engine.sources.transport import (
    AllowlistedHttpTransport,
    AmbiguousFixture,
    CanonicalRequest,
    FixtureIntegrityError,
    FixtureTransport,
    SourceId,
    SourcePolicyError,
    UpstreamResponseError,
)
from ncl_engine.sources.transport.blobs import put_blob


def _interaction(
    root: Path,
    identifier: str,
    request: CanonicalRequest,
    body: bytes,
    *,
    etag: str | None = None,
    total: str = "*",
    retrieved_at: str = "2026-10-03T00:00:00Z",
) -> dict[str, Any]:
    digest, relative = put_blob(root, body)
    headers: dict[str, str] = {"content-length": str(len(body))}
    status = 200
    if "range" in request.headers:
        start, end = request.headers["range"].removeprefix("bytes=").split("-")
        headers["content-range"] = f"bytes {start}-{end}/{total}"
        status = 206
    if etag:
        headers["etag"] = etag
    return {
        "id": identifier,
        "source_id": request.source_id.value,
        "request": {**request.identity(), "request_key_sha256": request.key()},
        "response": {
            "status": status,
            "headers": headers,
            "retrieved_at": retrieved_at,
            "body": {"sha256": digest, "size": len(body), "path": relative.as_posix()},
        },
    }


def test_fixture_transport_integrity_and_ambiguity_edges(tmp_path: Path) -> None:
    exact = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "POST",
        "https://earth-search.aws.element84.com/v1/search",
        {"Content-Type": "application/json"},
        b"{}",
    )
    raw = _interaction(tmp_path, "one", exact, b"{}")
    with pytest.raises(FixtureIntegrityError, match="unique"):
        FixtureTransport(tmp_path, [raw, raw])
    with pytest.raises(AmbiguousFixture):
        import asyncio

        asyncio.run(FixtureTransport(tmp_path, [raw, {**raw, "id": "two"}]).request(exact))

    bad = json.loads(json.dumps(raw))
    bad["request"]["method"] = "post"
    with pytest.raises(FixtureIntegrityError, match="not canonical"):
        FixtureTransport(tmp_path, [bad])
    bad = json.loads(json.dumps(raw))
    bad["request"]["headers"]["range"] = " bytes=0-2 "
    with pytest.raises(FixtureIntegrityError, match="range is not canonical"):
        FixtureTransport(tmp_path, [bad])
    bad = json.loads(json.dumps(raw))
    bad["request"]["body_sha256"] = "x"
    with pytest.raises(FixtureIntegrityError, match="invalid body digest"):
        FixtureTransport(tmp_path, [bad])
    bad = json.loads(json.dumps(raw))
    bad["response"]["retrieved_at"] = "2026-10-03T00:00:00"
    with pytest.raises(FixtureIntegrityError, match="timezone"):
        FixtureTransport(tmp_path, [bad])


def test_fixture_transport_from_path_and_bad_range_metadata(tmp_path: Path) -> None:
    request = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif",
        {"Range": "bytes=0-2"},
    )
    raw = _interaction(tmp_path / "blobs", "range", request, b"abc", etag='"v"', total="3")
    manifest = tmp_path / "preset.json"
    manifest.write_text(json.dumps({"interactions": [raw]}), encoding="utf-8")
    fixture_set = tmp_path / "fixture-set.json"
    fixture_set.write_text(
        json.dumps(
            {
                "interactions": [],
                "presets": [{"manifest": None}, {"manifest": "preset.json"}],
            }
        ),
        encoding="utf-8",
    )
    transport = FixtureTransport.from_path(fixture_set)
    assert len(transport._interactions) == 1  # noqa: SLF001

    wrong_length = _interaction(tmp_path / "blobs", "short", request, b"ab", etag='"v"', total="3")
    with pytest.raises(FixtureIntegrityError, match="length mismatch"):
        FixtureTransport(tmp_path / "blobs", [wrong_length])._range_request(request)  # noqa: SLF001

    bad_total = _interaction(tmp_path / "blobs", "total", request, b"abc", etag='"v"')
    bad_total["response"]["headers"]["content-range"] = "bytes 0-2/nope"
    with pytest.raises(FixtureIntegrityError, match="invalid Content-Range"):
        FixtureTransport(tmp_path / "blobs", [bad_total])._range_request(request)  # noqa: SLF001

    second = CanonicalRequest(
        request.source_id, request.method, request.url, {"Range": "bytes=3-5"}
    )
    disagree = [
        _interaction(tmp_path / "blobs", "a", request, b"abc", etag='"v"', total="6"),
        _interaction(tmp_path / "blobs", "b", second, b"def", etag='"v"', total="7"),
    ]
    union = CanonicalRequest(request.source_id, request.method, request.url, {"Range": "bytes=0-5"})
    with pytest.raises(FixtureIntegrityError, match="disagree"):
        FixtureTransport(tmp_path / "blobs", disagree)._range_request(union)  # noqa: SLF001


def test_fixture_range_deduplicates_same_interaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ncl_engine.sources.transport.fixture as fixture_module

    request = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/example/SCL.tif",
        {"Range": "bytes=0-1"},
    )
    raw = _interaction(tmp_path, "same", request, b"ab", etag='"v"', total="4")
    transport = FixtureTransport(tmp_path, [raw])
    item = transport._interactions[0]  # noqa: SLF001
    ranges = iter([(0, 1), (2, 3)])
    monkeypatch.setattr(fixture_module, "parse_range", lambda value: next(ranges))
    body, used, total = transport._assemble_range([item, item], 0, 3) or (b"", [], None)  # noqa: SLF001
    assert body == b"abab"
    assert used == [item]
    assert total == 4


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        url: str = "https://celestrak.org/data",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.url = url
        self.headers = headers or {"Content-Length": str(len(body)), "X-Secret": "hidden"}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def geturl(self) -> str:
        return self.url

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


def test_allowlisted_http_success_policy_and_response_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = AllowlistedHttpTransport(timeout_seconds=1)
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Response(b"{}"))
    snapshot = transport._request_sync(request)  # noqa: SLF001
    assert snapshot.body == b"{}"
    assert "x-secret" not in snapshot.headers

    with pytest.raises(SourcePolicyError):
        transport._request_sync(
            CanonicalRequest(SourceId.CELESTRAK, "GET", "http://celestrak.org/data")
        )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: _Response(b"{}", url="https://example.test/redirect"),
    )
    with pytest.raises(SourcePolicyError, match="redirect"):
        transport._request_sync(request)  # noqa: SLF001
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: _Response(b"{}", headers={"Content-Length": "999999"}),
    )
    with pytest.raises(UpstreamResponseError, match="declared response size"):
        transport._request_sync(request)  # noqa: SLF001


def test_allowlisted_http_error_and_range_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = AllowlistedHttpTransport()
    request = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.HTTPError(request.url, 503, "bad", Message(), None)
        ),
    )
    with pytest.raises(UpstreamResponseError, match="HTTP 503"):
        transport._request_sync(request)  # noqa: SLF001
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(UpstreamResponseError, match="offline"):
        transport._request_sync(request)  # noqa: SLF001

    with pytest.raises(UpstreamResponseError, match="expected HTTP 200"):
        transport._validate(request, 201, {}, b"")  # noqa: SLF001
    ranged = CanonicalRequest(
        SourceId.SENTINEL_COGS,
        "GET",
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/a.tif",
        {"Range": "bytes=0-2"},
    )
    with pytest.raises(UpstreamResponseError, match="requires HTTP 206"):
        transport._validate(ranged, 200, {}, b"abc")  # noqa: SLF001
    with pytest.raises(UpstreamResponseError, match="expected 3"):
        transport._validate(ranged, 206, {"content-range": "bytes 0-2/3"}, b"ab")  # noqa: SLF001
    with pytest.raises(UpstreamResponseError, match="does not match"):
        transport._validate(ranged, 206, {"content-range": "bad"}, b"abc")  # noqa: SLF001
    transport._validate(ranged, 206, {"content-range": "bytes 0-2/3"}, b"abc")  # noqa: SLF001
