from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ncl_engine.orbit import OrbitPropagator
from ncl_engine.orbit.illumination import De421Illumination
from ncl_engine.sources.replay import ReplaySourceAdapters


@pytest.mark.asyncio
async def test_content_addressed_de421_path_loads_when_fixture_is_present() -> None:
    fixture_set_path = Path(__file__).resolve().parents[3] / "fixtures" / "fixture-set.json"
    if not fixture_set_path.exists():
        pytest.skip("platform fixture set is merged during integration")
    fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
    reference = fixture_set["sources"]["ephemeris"]["body"]
    path = fixture_set_path.parent / "blobs" / reference["path"]
    if not path.exists():
        pytest.skip("platform ephemeris blob is pending integration")
    now = datetime(2026, 10, 3, tzinfo=UTC)
    records = await ReplaySourceAdapters().load_omm(now)
    propagator = OrbitPropagator()
    propagator.install(records)
    provider = De421Illumination(propagator, path)
    state = propagator.state_at("sentinel-2a", now)
    result = provider.evaluate("sentinel-2a", state, 1.3, 103.7)
    assert result is None or result.label in {"daylight", "low_sun"}
