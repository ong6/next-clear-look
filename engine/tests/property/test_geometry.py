from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hypothesis import example, given, settings
from hypothesis import strategies as st
from shapely.geometry import shape

from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.domain.models import Geometry
from ncl_engine.orbit.intersection import LocalAoi
from ncl_engine.orbit.propagation import OrbitState
from ncl_engine.orbit.sensor import swath_footprint


def _wrap(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


@settings(max_examples=200, deadline=None)
@given(
    longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
    latitude=st.floats(min_value=-82, max_value=82, allow_nan=False, allow_infinity=False),
    width=st.floats(min_value=0.00001, max_value=1.0, allow_nan=False, allow_infinity=False),
    height=st.floats(min_value=0.00001, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@example(longitude=179.9, latitude=10.0, width=0.4, height=0.2)
@example(longitude=0.0, latitude=81.5, width=0.2, height=0.1)
@example(longitude=103.7, latitude=1.3, width=0.00001, height=0.00001)
def test_rectangles_normalize_to_finite_valid_geometry(
    longitude: float, latitude: float, width: float, height: float
) -> None:
    west = _wrap(longitude - width / 2)
    east = _wrap(longitude + width / 2)
    south = max(-89.9, latitude - height / 2)
    north = min(89.9, latitude + height / 2)
    geometry: Geometry = {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }
    result = normalize_aoi(geometry)
    rendered = shape(result.geometry)
    assert rendered.is_valid
    assert not rendered.is_empty
    assert result.area_km2 > 0
    assert all(math.isfinite(value) for value in result.bbox)
    assert len(result.geometry_sha256) == 64


def test_concave_aoi_is_preserved() -> None:
    geometry: Geometry = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [0.4, 0.0], [0.4, 0.4], [0.2, 0.2], [0.0, 0.4], [0.0, 0.0]]],
    }
    result = normalize_aoi(geometry)
    assert shape(result.geometry).is_valid
    assert result.vertex_count == 6


@settings(max_examples=200, deadline=None)
@given(
    base_longitude=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
    base_latitude=st.floats(min_value=-80, max_value=80, allow_nan=False, allow_infinity=False),
)
@example(base_longitude=179.8, base_latitude=10.0)
@example(base_longitude=20.0, base_latitude=79.8)
def test_swath_is_valid_at_antimeridian_and_high_latitude(
    base_longitude: float, base_latitude: float
) -> None:
    start = datetime(2026, 10, 3, tzinfo=UTC)
    states = [
        OrbitState(
            time=start + timedelta(seconds=index * 2),
            latitude=max(-89.0, min(89.0, base_latitude - index * 0.03)),
            longitude=_wrap(base_longitude + index * 0.08),
            altitude_m=786_000.0,
            inertial_position_km=(7000.0, 0.0, 0.0),
        )
        for index in range(5)
    ]
    footprint = shape(swath_footprint(states))
    assert footprint.is_valid
    assert not footprint.is_empty
    assert footprint.bounds[0] >= -180.0
    assert footprint.bounds[2] <= 180.0


@settings(max_examples=40, deadline=None)
@given(separation=st.floats(min_value=1.0, max_value=12.0, allow_nan=False))
def test_multipolygon_coarse_radius_contains_every_part(separation: float) -> None:
    geometry: Geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2], [0.0, 0.0]]],
            [
                [
                    [separation, 0.0],
                    [separation + 0.2, 0.0],
                    [separation + 0.2, 0.2],
                    [separation, 0.2],
                    [separation, 0.0],
                ]
            ],
        ],
    }
    context = LocalAoi(geometry)
    maximum = max(
        math.hypot(float(x), float(y)) for part in context.parts for x, y in part.exterior.coords
    )
    assert context.radius_m == maximum


@settings(max_examples=40, deadline=None)
@given(vertex_count=st.integers(min_value=2, max_value=200))
def test_uneven_vertex_density_does_not_shrink_coarse_radius(vertex_count: int) -> None:
    west = [[0.0, 1.0 - index / vertex_count] for index in range(vertex_count + 1)]
    geometry: Geometry = {
        "type": "Polygon",
        "coordinates": [west + [[4.0, 0.0], [4.0, 1.0], [0.0, 1.0]]],
    }
    context = LocalAoi(geometry)
    far_x, far_y = context.transformer.transform(4.0, 1.0)
    assert context.radius_m >= math.hypot(float(far_x), float(far_y)) - 1e-6


def test_antimeridian_split_parts_are_inside_coarse_radius() -> None:
    normalized = normalize_aoi(
        {
            "type": "Polygon",
            "coordinates": [
                [[179.6, -17.0], [-179.6, -17.0], [-179.6, -16.4], [179.6, -16.4], [179.6, -17.0]]
            ],
        }
    )
    context = LocalAoi(normalized.geometry)
    assert len(context.parts) == 2
    assert context.radius_m < 100_000.0
