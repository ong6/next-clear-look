"""AOI validation, antimeridian normalization, metrics, and stable hashing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

from pyproj import Geod
from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from ncl_engine.domain.models import Geometry
from ncl_engine.domain.policies import MAX_AOI_AREA_KM2, MAX_AOI_VERTICES
from ncl_engine.provenance.hashing import JsonValue, canonical_json, sha256_bytes

GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True, slots=True)
class NormalizedAoi:
    geometry: Geometry
    centroid: dict[str, object]
    bbox: tuple[float, float, float, float]
    area_km2: float
    geometry_sha256: str
    vertex_count: int


def _number(value: object, *, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("coordinates must be numbers")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ValueError(f"coordinate {result} is outside [{minimum}, {maximum}]")
    return round(result, 9)


def _unwrap_ring(raw_ring: object) -> list[tuple[float, float]]:
    if not isinstance(raw_ring, list) or len(raw_ring) < 4:
        raise ValueError("each linear ring must contain at least four positions")
    output: list[tuple[float, float]] = []
    for raw_position in raw_ring:
        if not isinstance(raw_position, list) or len(raw_position) != 2:
            raise ValueError("positions must contain exactly longitude and latitude")
        longitude = _number(raw_position[0], minimum=-180.0, maximum=180.0)
        latitude = _number(raw_position[1], minimum=-90.0, maximum=90.0)
        if output:
            while longitude - output[-1][0] > 180.0:
                longitude -= 360.0
            while longitude - output[-1][0] < -180.0:
                longitude += 360.0
        output.append((longitude, latitude))
    if output[0] != output[-1]:
        output.append(output[0])
    return output


def _polygon(raw: object) -> Polygon:
    if not isinstance(raw, list) or not raw:
        raise ValueError("a Polygon must contain at least one ring")
    rings = [_unwrap_ring(ring) for ring in raw]
    return Polygon(rings[0], rings[1:])


def _parts(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        output: list[Polygon] = []
        for child in geometry.geoms:
            output.extend(_parts(child))
        return output
    return []


def _wrap(geometry: BaseGeometry) -> BaseGeometry:
    world = box(-180.0, -90.0, 180.0, 90.0)
    pieces: list[Polygon] = []
    for shift in (-360.0, 0.0, 360.0):
        shifted = affinity.translate(geometry, xoff=shift)
        pieces.extend(part for part in _parts(shifted.intersection(world)) if part.area > 0)
    unique = {part.normalize().wkb: part.normalize() for part in pieces}
    values = list(unique.values())
    if not values:
        raise ValueError("AOI is outside the WGS84 coordinate domain")
    return values[0] if len(values) == 1 else MultiPolygon(values).normalize()


def normalize_aoi(raw: Geometry) -> NormalizedAoi:
    geometry_type = raw.get("type")
    coordinates = raw.get("coordinates")
    if geometry_type == "Polygon":
        unwrapped: BaseGeometry = _polygon(coordinates)
    elif geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("a MultiPolygon must contain at least one Polygon")
        unwrapped = MultiPolygon([_polygon(item) for item in coordinates])
    else:
        raise ValueError("AOI geometry must be Polygon or MultiPolygon")
    if unwrapped.is_empty or not unwrapped.is_valid:
        raise ValueError(f"invalid AOI geometry: {explain_validity(unwrapped)}")
    parts = _parts(unwrapped)
    vertex_count = sum(len(part.exterior.coords) for part in parts)
    vertex_count += sum(len(ring.coords) for part in parts for ring in part.interiors)
    if vertex_count > MAX_AOI_VERTICES:
        raise ValueError(f"AOI has {vertex_count} vertices; maximum is {MAX_AOI_VERTICES}")
    area_m2 = sum(abs(GEOD.geometry_area_perimeter(part)[0]) for part in parts)
    area_km2 = area_m2 / 1_000_000.0
    if area_km2 <= 0 or area_km2 > MAX_AOI_AREA_KM2:
        raise ValueError(f"AOI area {area_km2:.3f} km2 is outside the supported range")
    wrapped = _wrap(unwrapped)
    normalized_mapping = cast(dict[str, Any], mapping(wrapped))
    normalized: Geometry = {str(key): value for key, value in normalized_mapping.items()}
    centroid = unwrapped.centroid
    longitude = (float(centroid.x) + 180.0) % 360.0 - 180.0
    centroid_json: dict[str, object] = {
        "type": "Point",
        "coordinates": [round(longitude, 9), round(float(centroid.y), 9)],
    }
    min_lon, min_lat, max_lon, max_lat = wrapped.bounds
    digest = sha256_bytes(canonical_json(cast(JsonValue, normalized)))
    return NormalizedAoi(
        geometry=normalized,
        centroid=centroid_json,
        bbox=(float(min_lon), float(min_lat), float(max_lon), float(max_lat)),
        area_km2=area_km2,
        geometry_sha256=digest,
        vertex_count=vertex_count,
    )
