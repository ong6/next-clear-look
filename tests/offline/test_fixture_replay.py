from __future__ import annotations

import hashlib
import json
import os
import socket
import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ncl_engine.fixtures import check_repository
from ncl_engine.fixtures.record import _materialize_derived, latest_valid_frozen_at
from ncl_engine.sources.transport import (
    CanonicalRequest,
    FixtureMiss,
    FixtureTransport,
    SourceId,
)

ROOT = Path(__file__).resolve().parents[2]


def test_fixture_check_needs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("non-loopback network attempted during fixture check")

    monkeypatch.setattr(socket.socket, "connect", denied)
    report = check_repository(ROOT)
    assert report["status"] == "ready"
    assert report["manifests"] == 5
    assert report["presets"] == 5
    assert report["unique_blob_bytes"] < report["budget_bytes"]


@pytest.mark.asyncio
async def test_fixture_miss_does_not_use_dead_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    transport = FixtureTransport.from_path(ROOT / "fixtures" / "fixture-set.json")
    request = CanonicalRequest(
        SourceId.EARTH_SEARCH,
        "GET",
        "https://earth-search.aws.element84.com/v1/not-recorded",
    )
    with pytest.raises(FixtureMiss, match="network fallback is forbidden"):
        await transport.request(request)
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"


def test_ephemeris_excerpt_is_the_declared_spk_blob() -> None:
    fixture_set = json.loads((ROOT / "fixtures" / "fixture-set.json").read_text())
    reference = fixture_set["sources"]["ephemeris"]["body"]
    body = (ROOT / "fixtures" / "blobs" / reference["path"]).read_bytes()
    assert body.startswith(b"DAF/SPK")
    assert len(body) == reference["size"]
    assert hashlib.sha256(body).hexdigest() == reference["sha256"]


def test_tuas_polygon_is_the_d13_geometry() -> None:
    feature = json.loads(
        (ROOT / "fixtures" / "presets" / "singapore-coast" / "aoi.geojson").read_text()
    )
    assert feature["id"] == "aoi_sg_tuas_coast"
    assert feature["bbox"] == [103.62, 1.24, 103.77, 1.36]


def test_recorder_materializes_base64_png_as_a_blob(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\nfixture"
    artifact = _materialize_derived(
        "thumbnail",
        {"body_base64": base64.b64encode(png).decode(), "media_type": "image/png"},
        tmp_path,
        ["a" * 64],
    )
    reference = artifact["body"]
    assert reference["media_type"] == "image/png"
    assert (tmp_path / reference["path"]).read_bytes() == png
    assert artifact["source_body_sha256"] == ["a" * 64]


def test_recorder_materializes_json_without_duplicating_it_inline(
    tmp_path: Path,
) -> None:
    artifact = _materialize_derived(
        "opportunities.json",
        {"items": [{"id": "opp_1"}]},
        tmp_path,
        ["b" * 64],
    )
    assert set(artifact) == {"body", "source_body_sha256"}
    assert artifact["body"]["media_type"] == "application/json"
    body = (tmp_path / artifact["body"]["path"]).read_bytes()
    assert json.loads(body) == {"items": [{"id": "opp_1"}]}


def test_d12_selects_latest_legal_frozen_time() -> None:
    recording_at = datetime(2026, 10, 2, 19, tzinfo=UTC)
    epochs = [
        datetime(2026, 10, 2, 4, tzinfo=UTC),
        datetime(2026, 10, 2, 6, tzinfo=UTC),
    ]
    earlier = datetime(2026, 10, 1, 3, 38, tzinfo=UTC)
    too_late = datetime(2026, 10, 3, 3, 38, tzinfo=UTC)
    frozen = latest_valid_frozen_at(recording_at, epochs, [earlier, too_late])
    assert frozen == earlier - timedelta(hours=2)


def test_d12_rejects_opportunity_outside_epoch_window() -> None:
    recording_at = datetime(2026, 10, 3, tzinfo=UTC)
    epochs = [datetime(2026, 10, 3, tzinfo=UTC)]
    with pytest.raises(ValueError, match="no frozen_at"):
        latest_valid_frozen_at(
            recording_at,
            epochs,
            [datetime(2026, 9, 29, 3, tzinfo=UTC)],
        )
