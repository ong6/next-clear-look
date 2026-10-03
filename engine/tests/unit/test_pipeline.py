from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from ncl_engine.orbit.omm import OmmRecord
from ncl_engine.pipeline import (
    _aoi,
    _validate_frozen_omm,
    record_fixture_set,
    verify_fixture_statistics,
)


def test_recorder_callback_signature_is_platform_contract() -> None:
    assert list(inspect.signature(record_fixture_set).parameters) == [
        "aois",
        "frozen_at",
        "transport",
        "cog_adapter_factory",
        "ephemeris",
    ]
    assert inspect.iscoroutinefunction(record_fixture_set)
    assert inspect.iscoroutinefunction(verify_fixture_statistics)


def test_recorder_preserves_feature_id() -> None:
    identifier, geometry = _aoi(
        {
            "type": "Feature",
            "id": "aoi_sg_tuas_coast",
            "geometry": {"type": "Polygon", "coordinates": []},
        },
        "singapore-coast",
    )
    assert identifier == "aoi_sg_tuas_coast"
    assert geometry["type"] == "Polygon"


def test_recording_clock_must_stay_within_48_hours_of_every_omm() -> None:
    epoch = datetime(2026, 10, 3, tzinfo=UTC)
    record = OmmRecord(
        platform="sentinel-2a",
        name="SENTINEL-2A",
        norad_catalog_id=40697,
        epoch=epoch,
        values={},
        sha256="a" * 64,
    )
    _validate_frozen_omm([record], epoch - timedelta(hours=48))
    with pytest.raises(ValueError, match="more than 48 hours"):
        _validate_frozen_omm([record], epoch - timedelta(hours=48, seconds=1))
