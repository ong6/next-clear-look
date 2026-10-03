"""Deterministic Sentinel-2 datatake grouping and AOI coverage."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from ncl_engine.domain.models import Geometry
from ncl_engine.sources.protocols import StacItem


@dataclass(frozen=True, slots=True)
class Datatake:
    """One acquisition, potentially split across several MGRS tiles."""

    id: str
    platform: str
    acquisition_time: datetime
    relative_orbit: int | None
    items: tuple[StacItem, ...]
    footprint: Geometry

    @property
    def tiles(self) -> tuple[str, ...]:
        return tuple(sorted({item.tile for item in self.items}))


def datatake_key(item: StacItem) -> str:
    """Return the provider identity, failing closed to a single-item acquisition."""

    return item.datatake_id or item.id


def group_datatakes(items: list[StacItem]) -> list[Datatake]:
    """Group tiles by ``s2:datatake_id`` despite their per-tile timestamps."""

    groups: dict[str, list[StacItem]] = defaultdict(list)
    for item in items:
        groups[datatake_key(item)].append(item)

    output: list[Datatake] = []
    for identifier, values in groups.items():
        ordered = tuple(sorted(values, key=lambda value: (value.tile, value.id)))
        platforms = {item.platform for item in ordered}
        orbits = {item.relative_orbit for item in ordered if item.relative_orbit is not None}
        if len(platforms) != 1 or len(orbits) > 1:
            raise ValueError(f"inconsistent Sentinel-2 datatake {identifier}")
        footprint = mapping(unary_union([shape(item.geometry) for item in ordered]))
        output.append(
            Datatake(
                id=identifier,
                platform=ordered[0].platform,
                acquisition_time=min(item.acquisition_time for item in ordered),
                relative_orbit=next(iter(orbits), None),
                items=ordered,
                footprint={str(key): value for key, value in footprint.items()},
            )
        )
    return sorted(output, key=lambda value: (value.acquisition_time, value.id), reverse=True)


def _longitude_center(geometry: BaseGeometry) -> float:
    """Choose an antimeridian-safe longitude for a local equal-area projection."""

    coordinates: list[float] = []

    def collect(value: object) -> None:
        if isinstance(value, (tuple, list)):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                coordinates.append(float(value[0]))
                return
            for child in value:
                collect(child)

    collect(mapping(geometry).get("coordinates"))
    if not coordinates:
        return float(geometry.centroid.x)
    import math

    x = sum(math.cos(math.radians(value)) for value in coordinates)
    y = sum(math.sin(math.radians(value)) for value in coordinates)
    return math.degrees(math.atan2(y, x))


def local_equal_area_crs(geometry: Geometry) -> CRS:
    raw = shape(geometry)
    longitude = _longitude_center(raw)
    latitude = float(raw.centroid.y)
    return CRS.from_proj4(
        f"+proj=laea +lat_0={latitude:.12f} +lon_0={longitude:.12f} +datum=WGS84 +units=m"
    )


def _projected(geometry: Geometry, crs: CRS) -> BaseGeometry:
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True, force_over=True)
    return transform(transformer.transform, shape(geometry))


def coverage_fraction(aoi: Geometry, footprint: Geometry) -> float:
    crs = local_equal_area_crs(aoi)
    projected_aoi = _projected(aoi, crs)
    projected_footprint = _projected(footprint, crs)
    if projected_aoi.area <= 0:
        return 0.0
    return max(
        0.0,
        min(1.0, float(projected_aoi.intersection(projected_footprint).area / projected_aoi.area)),
    )


def select_scene_cover(aoi: Geometry, items: list[StacItem]) -> list[tuple[Datatake, float]]:
    """Return one full tile mosaic per datatake, newest acquisitions first."""

    return [
        (datatake, coverage_fraction(aoi, datatake.footprint))
        for datatake in group_datatakes(items)
        if coverage_fraction(aoi, datatake.footprint) > 0.0
    ]
