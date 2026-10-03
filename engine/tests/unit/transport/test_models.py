from __future__ import annotations

import pytest

from ncl_engine.sources.transport import CanonicalRequest, InvalidRequest, SourceId


def test_request_key_normalizes_url_headers_and_json() -> None:
    first = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "post",
        "HTTPS://EARTH-SEARCH.AWS.ELEMENT84.COM:443/v1/search?z=2&a=1",
        {"Content-Type": "application/json", "Accept": " application/geo+json "},
        b'{"z":2,"a":1}',
    )
    second = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "POST",
        "https://earth-search.aws.element84.com/v1/search?a=1&z=2",
        {"accept": "application/geo+json", "content-type": "application/json"},
        b'{ "a": 1, "z": 2 }',
    )
    assert first.key() == second.key()
    assert first.body == b'{"a":1,"z":2}'
    assert len(first.key()) == 64


@pytest.mark.parametrize(
    "url",
    [
        "https://user@example.com/a",
        "https://example.com/a#fragment",
        "ftp://example.com/a",
        "https://example.com/a?X-Amz-Signature=secret",
    ],
)
def test_request_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(InvalidRequest):
        CanonicalRequest(SourceId.EARTH_SEARCH, "GET", url)


@pytest.mark.parametrize("value", ["bytes=1-", "bytes=-5", "bytes=5-4", "bytes=1-2,4-5"])
def test_request_rejects_unsupported_ranges(value: str) -> None:
    with pytest.raises(InvalidRequest):
        CanonicalRequest(
            SourceId.SENTINEL_COGS,
            "GET",
            "https://sentinel-cogs.s3.us-west-2.amazonaws.com/a.tif",
            {"Range": value},
        )


def test_non_identity_headers_do_not_change_key() -> None:
    base = CanonicalRequest(SourceId.CELESTRAK, "GET", "https://celestrak.org/data")
    noisy = CanonicalRequest(
        SourceId.CELESTRAK,
        "GET",
        "https://celestrak.org/data",
        {"Authorization": "never-record-this", "User-Agent": "different"},
    )
    assert base.key() == noisy.key()
