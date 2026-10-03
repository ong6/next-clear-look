"""Guarded coarse pass scan and sub-second AOI/swath refinement."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
from pyproj import CRS, Geod, Transformer
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry

from ncl_engine.domain.models import Opportunity, OpportunitySource, Subpoint
from ncl_engine.domain.policies import (
    COARSE_STEP_SECONDS,
    CROSSING_TOLERANCE_SECONDS,
    OPPORTUNITY_CAVEAT,
    SWATH_HALF_WIDTH_M,
)
from ncl_engine.provenance.hashing import stable_id

from .illumination import IlluminationProvider
from .omm import OmmRecord
from .propagation import OrbitPropagator, OrbitState
from .sensor import swath_footprint
from .trajectories import time_grid

GEOD = Geod(ellps="WGS84")


def golden_minimum(
    function: Callable[[float], float], left: float, right: float, tolerance: float
) -> tuple[float, float]:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = right - ratio * (right - left)
    d = left + ratio * (right - left)
    fc = function(c)
    fd = function(d)
    while right - left > tolerance:
        if fc < fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = function(c)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = function(d)
    result = (left + right) / 2.0
    return result, function(result)


def bisect_crossing(
    function: Callable[[float], float], left: float, right: float, tolerance: float
) -> float:
    left_value = function(left)
    right_value = function(right)
    if left_value <= 0:
        return left
    if right_value >= 0:
        return right
    while right - left > tolerance:
        middle = (left + right) / 2.0
        middle_value = function(middle)
        if middle_value <= 0:
            right = middle
        else:
            left = middle
    return (left + right) / 2.0


def _circular_longitude(longitudes: Sequence[float]) -> float:
    radians = np.radians(np.asarray(longitudes, dtype=float))
    angle = math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean()))
    return math.degrees(angle)


def _coordinates(geometry: BaseGeometry) -> list[tuple[float, float]]:
    if isinstance(geometry, Polygon):
        return [(float(x), float(y)) for x, y in geometry.exterior.coords]
    points: list[tuple[float, float]] = []
    if not isinstance(geometry, MultiPolygon):
        return points
    for polygon in geometry.geoms:
        points.extend((float(x), float(y)) for x, y in polygon.exterior.coords)
    return points


def _shift_near(longitude: float, center: float) -> float:
    value = longitude
    while value - center > 180.0:
        value -= 360.0
    while value - center < -180.0:
        value += 360.0
    return value


class LocalAoi:
    def __init__(self, geometry: dict[str, object]) -> None:
        raw = shape(geometry)
        if raw.is_empty or raw.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("AOI must be a non-empty Polygon or MultiPolygon")
        points = _coordinates(raw)
        self.longitude = _circular_longitude([point[0] for point in points])
        self.latitude = sum(point[1] for point in points) / len(points)
        shifted = transform_geometry(
            lambda x, y, z=None: (_shift_near(float(x), self.longitude), float(y)), raw
        )
        local_crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={self.latitude:.12f} +lon_0={self.longitude:.12f} "
            "+datum=WGS84 +units=m +no_defs"
        )
        self.transformer = Transformer.from_crs(
            "EPSG:4326", local_crs, always_xy=True, force_over=True
        )
        self.geometry = transform_geometry(self.transformer.transform, shifted)
        centroid = self.geometry.centroid
        self.centroid_xy = (float(centroid.x), float(centroid.y))
        self.parts = (
            tuple(self.geometry.geoms)
            if isinstance(self.geometry, MultiPolygon)
            else (self.geometry,)
        )
        self.radius_m = max(
            math.hypot(float(x), float(y)) for part in self.parts for x, y in part.exterior.coords
        )

    def point(self, state: OrbitState) -> Point:
        longitude = _shift_near(state.longitude, self.longitude)
        x, y = self.transformer.transform(longitude, state.latitude)
        return Point(float(x), float(y))

    def distance(self, state: OrbitState) -> float:
        return float(self.point(state).distance(self.geometry))

    def distance_to_part(self, state: OrbitState, part: Polygon) -> float:
        return float(self.point(state).distance(part))


class PassPredictor:
    def __init__(self, propagator: OrbitPropagator, illumination: IlluminationProvider) -> None:
        self.propagator = propagator
        self.illumination = illumination

    def predict(
        self,
        record: OmmRecord,
        aoi_id: str,
        geometry: dict[str, object],
        start: datetime,
        end: datetime,
        *,
        imaging_only: bool = True,
    ) -> list[Opportunity]:
        context = LocalAoi(geometry)
        instants = time_grid(start, end, COARSE_STEP_SECONDS)
        states = self.propagator.states_at(record.platform, instants)
        center_distances = np.asarray(
            [
                GEOD.inv(context.longitude, context.latitude, state.longitude, state.latitude)[2]
                for state in states
            ],
            dtype=float,
        )
        # Broad-phase guard: the subpoint moves about 137 km between 20-second
        # samples, so a crossing can sit up to half that (about 69 km) from the
        # nearest sample. 100 km covers that with margin; the refined swath
        # intersection below remains the only eligibility test.
        search_guard_m = 100_000.0
        threshold = SWATH_HALF_WIDTH_M + context.radius_m + search_guard_m
        candidates = np.flatnonzero(center_distances <= threshold)
        groups: list[list[int]] = []
        for raw_index in candidates:
            index = int(raw_index)
            if not groups or index != groups[-1][-1] + 1:
                groups.append([index])
            else:
                groups[-1].append(index)

        output: list[Opportunity] = []
        for group in groups:
            left_index = max(0, group[0] - 1)
            right_index = min(len(instants) - 1, group[-1] + 1)
            bracket_start = instants[left_index]
            bracket_end = instants[right_index]
            seconds = (bracket_end - bracket_start).total_seconds()

            def state_at(offset: float, base: datetime = bracket_start) -> OrbitState:
                return self.propagator.state_at(record.platform, base + timedelta(seconds=offset))

            refined: list[tuple[float, float, Polygon]] = []
            for part in context.parts:

                def part_distance(offset: float, selected: Polygon = part) -> float:
                    return context.distance_to_part(state_at(offset), selected)

                closest_offset, minimum_m = golden_minimum(
                    part_distance,
                    0.0,
                    seconds,
                    CROSSING_TOLERANCE_SECONDS,
                )
                refined.append((minimum_m, closest_offset, part))
            minimum_m, closest_offset, closest_part = min(refined)
            if minimum_m > SWATH_HALF_WIDTH_M:
                continue

            def distance_at(offset: float, selected: Polygon = closest_part) -> float:
                return context.distance_to_part(state_at(offset), selected)

            def signed_distance(offset: float) -> float:
                return distance_at(offset) - SWATH_HALF_WIDTH_M

            entry_offset = (
                0.0
                if signed_distance(0.0) <= 0
                else bisect_crossing(
                    signed_distance, 0.0, closest_offset, CROSSING_TOLERANCE_SECONDS
                )
            )
            exit_offset = (
                seconds
                if signed_distance(seconds) <= 0
                else bisect_crossing(
                    lambda value: -signed_distance(value),
                    closest_offset,
                    seconds,
                    CROSSING_TOLERANCE_SECONDS,
                )
            )
            entry = bracket_start + timedelta(seconds=entry_offset)
            closest = bracket_start + timedelta(seconds=closest_offset)
            exit_time = bracket_start + timedelta(seconds=exit_offset)
            truncated = (left_index == 0 and signed_distance(0.0) <= 0) or (
                right_index == len(instants) - 1 and signed_distance(seconds) <= 0
            )
            closest_state = state_at(closest_offset)
            before = state_at(max(0.0, closest_offset - 2.0))
            after = state_at(min(seconds, closest_offset + 2.0))
            direction: Literal["descending", "ascending"] = (
                "descending" if after.latitude < before.latitude else "ascending"
            )
            illumination = self.illumination.evaluate(
                record.platform, closest_state, context.latitude, context.longitude
            )
            if imaging_only and (direction != "descending" or illumination is None):
                continue
            if illumination is None:
                continue
            # Two-second centreline samples keep the wide strip well behaved near
            # high-latitude ground-track apices; each segment remains far below 25 km.
            strip_times = time_grid(entry, exit_time, 2)
            strip_states = self.propagator.states_at(record.platform, strip_times)
            footprint = swath_footprint(strip_states)
            mean_motion = float(record.values["MEAN_MOTION"])
            revolution_at_epoch = int(record.values.get("REV_AT_EPOCH", 0))
            revolution = revolution_at_epoch + math.floor(
                mean_motion * (closest - record.epoch).total_seconds() / 86_400.0
            )
            identifier = stable_id("opp", aoi_id, record.platform, str(revolution))
            output.append(
                Opportunity(
                    id=identifier,
                    aoi_id=aoi_id,
                    satellite_id=record.platform,
                    platform=record.platform,
                    entry_time=entry,
                    closest_time=closest,
                    exit_time=exit_time,
                    duration_seconds=(exit_time - entry).total_seconds(),
                    direction=direction,
                    satellite_sunlit=illumination.satellite_sunlit,
                    aoi_sun_elevation_deg=illumination.aoi_sun_elevation_deg,
                    illumination=illumination.label,
                    element_age_seconds=(closest - record.epoch).total_seconds(),
                    swath_footprint=footprint,
                    minimum_ground_track_distance_km=minimum_m / 1000.0,
                    closest_subpoint=Subpoint(
                        latitude=closest_state.latitude,
                        longitude=closest_state.longitude,
                        altitude_m=closest_state.altitude_m,
                    ),
                    caveat=OPPORTUNITY_CAVEAT,
                    source=OpportunitySource(
                        omm_epoch=record.epoch,
                        omm_sha256=record.sha256,
                    ),
                    truncated=truncated,
                    provenance_id=stable_id("prv", identifier),
                )
            )
        return sorted(output, key=lambda item: item.closest_time)
