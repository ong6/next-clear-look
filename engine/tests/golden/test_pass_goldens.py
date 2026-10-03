from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import shape

from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.domain.models import SceneSummary
from ncl_engine.likelihood.hindcast import match_opportunities_to_scenes
from ncl_engine.orbit import OrbitPropagator, PassPredictor
from ncl_engine.orbit.illumination import De421Illumination
from ncl_engine.orbit.omm import OmmRecord
from ncl_engine.sources.replay import ReplaySourceAdapters


def _predictor(records: list[OmmRecord], repository_root: Path) -> PassPredictor:
    fixture_set = json.loads(
        (repository_root / "fixtures" / "fixture-set.json").read_text(encoding="utf-8")
    )
    ephemeris = fixture_set["sources"]["ephemeris"]["body"]["path"]
    propagator = OrbitPropagator()
    propagator.install(records)
    return PassPredictor(
        propagator,
        De421Illumination(propagator, repository_root / "fixtures" / "blobs" / ephemeris),
    )


CASES: dict[str, dict[str, object]] = {
    "tuas": {
        "type": "Polygon",
        "coordinates": [
            [[103.62, 1.24], [103.77, 1.24], [103.77, 1.36], [103.62, 1.36], [103.62, 1.24]]
        ],
    },
    "equatorial": {
        "type": "Polygon",
        "coordinates": [[[30, -0.1], [30.1, -0.1], [30.1, 0.1], [30, 0.1], [30, -0.1]]],
    },
    "antimeridian": {
        "type": "Polygon",
        "coordinates": [[[179.7, 10], [-179.7, 10], [-179.7, 10.2], [179.7, 10.2], [179.7, 10]]],
    },
    "high-latitude": {
        "type": "Polygon",
        "coordinates": [[[20, 79.8], [20.3, 79.8], [20.3, 80], [20, 80], [20, 79.8]]],
    },
    "no-intersection": {
        "type": "Polygon",
        "coordinates": [[[10, 88.5], [10.2, 88.5], [10.2, 88.7], [10, 88.7], [10, 88.5]]],
    },
}


@pytest.fixture(scope="module")
async def omm_records() -> list[OmmRecord]:
    return await ReplaySourceAdapters().load_omm(datetime(2026, 10, 3, tzinfo=UTC))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(CASES))
async def test_pass_golden(name: str, omm_records: list[OmmRecord], repository_root: Path) -> None:
    now = datetime(2026, 10, 3, tzinfo=UTC)
    predictor = _predictor(omm_records, repository_root)
    geometry = normalize_aoi(CASES[name]).geometry
    opportunities = []
    for record in omm_records:
        opportunities.extend(
            predictor.predict(
                record,
                "aoi_" + name.replace("-", "_"),
                geometry,
                now,
                now + timedelta(days=14),
            )
        )
    opportunities.sort(key=lambda item: item.closest_time)
    golden = json.loads((Path(__file__).with_name("pass_cases.json")).read_text(encoding="utf-8"))[
        name
    ]
    assert len(opportunities) == golden["count"]
    assert sorted({item.direction for item in opportunities}) == golden["directions"]
    assert sorted({item.illumination for item in opportunities}) == golden["illumination"]
    assert all(shape(item.swath_footprint).is_valid for item in opportunities)
    if not opportunities:
        assert golden["first"] is None
        return
    first = golden["first"]
    assert opportunities[0].id == first["id"]
    assert opportunities[0].satellite_id == first["satellite_id"]
    assert opportunities[0].closest_time.isoformat() == first["closest_time"]
    assert opportunities[0].source.omm_sha256 == first["source_sha256"]
    assert opportunities[-1].closest_time.isoformat() == golden["last_closest_time"]


@pytest.mark.asyncio
async def test_recorded_tuas_hindcast_recall_and_timing(
    omm_records: list[OmmRecord], repository_root: Path
) -> None:
    fixture = json.loads(
        (Path(__file__).with_name("hindcast_tuas.json")).read_text(encoding="utf-8")
    )
    start = datetime.fromisoformat(fixture["window_start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(fixture["window_end"].replace("Z", "+00:00"))
    predictor = _predictor(omm_records, repository_root)
    geometry = normalize_aoi(CASES["tuas"]).geometry
    opportunities = []
    for record in omm_records:
        opportunities.extend(predictor.predict(record, "aoi_tuas", geometry, start, end))
    scenes = [
        SceneSummary.model_construct(
            id=item["id"],
            platform=item["platform"],
            acquisition_time=datetime.fromisoformat(
                item["acquisition_time"].replace("Z", "+00:00")
            ),
        )
        for item in fixture["acquisitions"]
    ]
    matches = match_opportunities_to_scenes(opportunities, scenes)
    opportunities_by_id = {item.id: item for item in opportunities}
    scenes_by_id = {item.id: item for item in scenes}
    absolute_errors = [
        abs(
            (
                opportunities_by_id[opportunity_id].closest_time
                - scenes_by_id[scene_id].acquisition_time
            ).total_seconds()
        )
        for opportunity_id, scene_id in matches.items()
    ]
    assert len(matches) / len(scenes) == 1.0
    assert len(matches) / len(opportunities) == pytest.approx(5 / 6)
    assert float(np.median(absolute_errors)) == pytest.approx(0.27, abs=0.06)
    assert float(np.quantile(absolute_errors, 0.95)) < 1.8
