from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pyproj import Geod
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.orbit import OrbitPropagator, PassPredictor
from ncl_engine.orbit.illumination import Illumination
from ncl_engine.orbit.omm import OmmRecord
from ncl_engine.orbit.propagation import OrbitState, reference_vectors
from ncl_engine.orbit.sensor import (
    _densify,
    _densify_xy,
    _polygon_parts,
    _unwrap,
    _wrap_geometry,
    _wrapped_polygon,
    swath_edge,
    swath_edges,
    swath_footprint,
)
from ncl_engine.orbit.trajectories import time_grid
from ncl_engine.sources.replay import ReplaySourceAdapters

GEOD = Geod(ellps="WGS84")
NOW = datetime(2026, 10, 3, tzinfo=UTC)
TUAS = normalize_aoi(
    {
        "type": "Polygon",
        "coordinates": [
            [[103.62, 1.24], [103.77, 1.24], [103.77, 1.36], [103.62, 1.36], [103.62, 1.24]]
        ],
    }
).geometry


class AlwaysDaylight:
    def evaluate(
        self, platform: str, state: OrbitState, aoi_latitude: float, aoi_longitude: float
    ) -> Illumination:
        del platform, state, aoi_latitude, aoi_longitude
        return Illumination(True, 45.0, "daylight")


async def _predictor() -> tuple[PassPredictor, OmmRecord]:
    records = await ReplaySourceAdapters().load_omm(NOW)
    propagator = OrbitPropagator()
    propagator.install(records)
    return PassPredictor(propagator, AlwaysDaylight()), records[0]


async def test_opportunity_id_is_stable_across_shifted_search_grids() -> None:
    predictor, record = await _predictor()
    first = predictor.predict(record, "aoi_tuas", TUAS, NOW, NOW + timedelta(days=14))
    shifted = predictor.predict(
        record,
        "aoi_tuas",
        TUAS,
        NOW + timedelta(seconds=7),
        NOW + timedelta(days=14, seconds=7),
    )
    assert {item.id for item in first} == {item.id for item in shifted}


async def test_window_starting_mid_pass_is_marked_truncated() -> None:
    predictor, record = await _predictor()
    full = predictor.predict(record, "aoi_tuas", TUAS, NOW, NOW + timedelta(days=14))[0]
    cut = predictor.predict(
        record, "aoi_tuas", TUAS, full.closest_time, full.closest_time + timedelta(days=1)
    )
    matching = min(
        cut, key=lambda item: abs((item.closest_time - full.closest_time).total_seconds())
    )
    assert matching.truncated
    assert matching.entry_time == full.closest_time


async def test_swath_heading_is_accurate_at_high_latitude() -> None:
    records = await ReplaySourceAdapters().load_omm(NOW)
    propagator = OrbitPropagator()
    propagator.install(records)
    platform = records[0].platform
    states = propagator.states_at(platform, time_grid(NOW, NOW + timedelta(hours=3), 60))
    edges = swath_edges(states)
    worst = 0.0
    for index in range(1, len(states) - 1):
        before = propagator.state_at(platform, states[index].time - timedelta(seconds=0.5))
        after = propagator.state_at(platform, states[index].time + timedelta(seconds=0.5))
        azimuth = GEOD.inv(before.longitude, before.latitude, after.longitude, after.latitude)[0]
        expected = GEOD.fwd(
            states[index].longitude, states[index].latitude, azimuth - 90.0, 145_000.0
        )[:2]
        worst = max(worst, GEOD.inv(*expected, *edges[index][0])[2])
    assert worst < 1_000.0


async def test_pinned_teme_reference_vector_uses_sgp4_error_position_velocity_order() -> None:
    records = await ReplaySourceAdapters().load_omm(NOW)
    propagator = OrbitPropagator()
    propagator.install(records)
    vectors = reference_vectors(propagator, "sentinel-2a", NOW)
    # The last bits of SGP4's floating-point output differ between platforms, so the pin
    # allows a micrometre in position and a nanometre per second in velocity.
    assert vectors["teme_position_km"] == pytest.approx(
        (-3597.5478805783423, -267.749715505227, 6185.589629020584), abs=1e-9
    )
    assert vectors["teme_velocity_km_s"] == pytest.approx(
        (-6.306370836954031, 1.7428948628426149, -3.584413088059598), abs=1e-12
    )


def test_sensor_geometry_helpers_cover_wrapping_densification_and_errors() -> None:
    assert _unwrap([]) == []
    assert _unwrap([179.0, -179.0, 179.0]) == [179.0, 181.0, 179.0]
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    multi = MultiPolygon([polygon, Polygon([(2, 0), (3, 0), (3, 1), (2, 0)])])
    assert len(list(_polygon_parts(polygon))) == 1
    assert len(list(_polygon_parts(multi))) == 2
    assert len(list(_polygon_parts(GeometryCollection([polygon])))) == 1
    assert _wrapped_polygon([(179, 0), (-179, 0), (-179, 1), (179, 0)]).is_valid
    with pytest.raises(ValueError, match="invalid polygon"):
        _wrapped_polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert _densify((0, 0), (0.01, 0.0)) == [(0, 0)]
    assert len(_densify((0, 0), (1, 0))) > 2
    assert _wrap_geometry(polygon) == polygon
    with pytest.raises(ValueError, match="outside"):
        _wrap_geometry(Polygon())
    assert _densify_xy((0, 0), (100_000, 0))[-1][0] < 100_000

    now = datetime(2026, 10, 3, tzinfo=UTC)
    first = OrbitState(now, 10.0, 179.8, 786_000, (0, 0, 0))
    second = OrbitState(now + timedelta(seconds=1), 9.9, -179.9, 786_000, (0, 0, 0))
    left, right = swath_edge(first, first, second)
    assert -180.0 <= left[0] <= 180.0
    assert -180.0 <= right[0] <= 180.0
    with pytest.raises(ValueError, match="at least two"):
        swath_edges([first])
    stationary = OrbitState(now + timedelta(seconds=2), 10.0, 179.8, 786_000, (0, 0, 0))
    with pytest.raises(ValueError, match="do not span an area"):
        swath_footprint([first, stationary])
