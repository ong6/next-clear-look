from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.resources import files

import pytest

from ncl_engine.orbit.omm import parse_omm_catalogue


def _payload() -> object:
    return json.loads(
        files("ncl_engine.resources").joinpath("sentinel-omm.json").read_text(encoding="utf-8")
    )


def test_parse_pinned_omm_catalogue() -> None:
    records = parse_omm_catalogue(_payload(), observed_at=datetime(2026, 10, 3, tzinfo=UTC))
    assert [record.platform for record in records] == [
        "sentinel-2a",
        "sentinel-2b",
        "sentinel-2c",
    ]
    assert all(len(record.sha256) == 64 for record in records)


def test_duplicate_omm_is_rejected() -> None:
    payload = _payload()
    assert isinstance(payload, list)
    with pytest.raises(ValueError, match="duplicate NORAD"):
        parse_omm_catalogue([payload[0], payload[0]], observed_at=datetime(2026, 10, 3, tzinfo=UTC))
