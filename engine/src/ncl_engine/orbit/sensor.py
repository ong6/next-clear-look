"""Nominal Sentinel-2 MSI swath geometry."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from pyproj import CRS, Geod, Transformer
from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPoint, MultiPolygon, Polygon, box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry
from shapely.ops import unary_union
from shapely.validation import explain_validity

from ncl_engine.domain.models import Geometry, Position
from ncl_engine.domain.policies import SWATH_HALF_WIDTH_M

from .propagation import OrbitState

GEOD = Geod(ellps="WGS84")


def _vertex_heading(previous: OrbitState, current: OrbitState, following: OrbitState) -> float:
    """Estimate heading in the current vertex's tangent plane."""

    previous_azimuth, _, previous_distance = GEOD.inv(
        current.longitude,
        current.latitude,
        previous.longitude,
        previous.latitude,
    )
    following_azimuth, _, following_distance = GEOD.inv(
        current.longitude,
        current.latitude,
        following.longitude,
        following.latitude,
    )
    previous_east = previous_distance * math.sin(math.radians(previous_azimuth))
    previous_north = previous_distance * math.cos(math.radians(previous_azimuth))
    following_east = following_distance * math.sin(math.radians(following_azimuth))
    following_north = following_distance * math.cos(math.radians(following_azimuth))
    eastward = following_east - previous_east
    northward = following_north - previous_north
    return math.degrees(math.atan2(eastward, northward))


def _wrap_longitude(value: float) -> float:
    wrapped = (value + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 and value > 0 else wrapped


def _unwrap(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    result = [values[0]]
    for value in values[1:]:
        candidate = value
        while candidate - result[-1] > 180.0:
            candidate -= 360.0
        while candidate - result[-1] < -180.0:
            candidate += 360.0
        result.append(candidate)
    return result


def swath_edge(
    previous: OrbitState, current: OrbitState, following: OrbitState
) -> tuple[Position, Position]:
    azimuth = _vertex_heading(previous, current, following)
    # Sentinel-2 MSI covers a nominal 290 km ground swath. This 145 km value
    # is geodesic distance across Earth's surface from the nadir track, not a
    # look angle or a slant distance from the spacecraft.
    left_lon, left_lat, _ = GEOD.fwd(
        current.longitude,
        current.latitude,
        azimuth - 90.0,
        SWATH_HALF_WIDTH_M,
    )
    right_lon, right_lat, _ = GEOD.fwd(
        current.longitude,
        current.latitude,
        azimuth + 90.0,
        SWATH_HALF_WIDTH_M,
    )
    return (_wrap_longitude(left_lon), left_lat), (_wrap_longitude(right_lon), right_lat)


def swath_edges(states: Sequence[OrbitState]) -> list[tuple[Position, Position]]:
    if len(states) < 2:
        raise ValueError("at least two states are needed for a swath")
    output: list[tuple[Position, Position]] = []
    for index, current in enumerate(states):
        previous = states[max(0, index - 1)]
        following = states[min(len(states) - 1, index + 1)]
        if previous is following:
            raise ValueError("swath states must span time")
        azimuth = _vertex_heading(previous, current, following)
        # Offset each track sample by the ground half-width on WGS84 so the
        # boundary stays a surface footprint at every latitude.
        left_lon, left_lat, _ = GEOD.fwd(
            current.longitude, current.latitude, azimuth - 90.0, SWATH_HALF_WIDTH_M
        )
        right_lon, right_lat, _ = GEOD.fwd(
            current.longitude, current.latitude, azimuth + 90.0, SWATH_HALF_WIDTH_M
        )
        left = (_wrap_longitude(left_lon), left_lat)
        right = (_wrap_longitude(right_lon), right_lat)
        if output:
            previous_left, previous_right = output[-1]
            same = GEOD.inv(*previous_left, *left)[2] + GEOD.inv(*previous_right, *right)[2]
            swapped = GEOD.inv(*previous_left, *right)[2] + GEOD.inv(*previous_right, *left)[2]
            if swapped < same:
                left, right = right, left
        output.append((left, right))
    return output


def _polygon_parts(geometry: BaseGeometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    elif isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def _wrapped_polygon(coordinates: list[Position]) -> BaseGeometry:
    longitudes = _unwrap([point[0] for point in coordinates])
    raw = Polygon(
        [(longitude, coordinates[index][1]) for index, longitude in enumerate(longitudes)]
    )
    if not raw.is_valid:
        raise ValueError(f"swath construction produced an invalid polygon: {explain_validity(raw)}")
    world = box(-180.0, -90.0, 180.0, 90.0)
    pieces: list[Polygon] = []
    for shift in (-360.0, 0.0, 360.0):
        candidate = affinity.translate(raw, xoff=shift)
        pieces.extend(
            part for part in _polygon_parts(candidate.intersection(world)) if not part.is_empty
        )
    unique: dict[bytes, Polygon] = {part.normalize().wkb: part for part in pieces}
    if not unique:
        raise ValueError("swath does not intersect the WGS84 longitude domain")
    values = list(unique.values())
    return values[0] if len(values) == 1 else MultiPolygon(values)


def _densify(start: Position, end: Position, maximum_segment_m: float = 25_000.0) -> list[Position]:
    _, _, distance = GEOD.inv(start[0], start[1], end[0], end[1])
    intermediate_count = max(0, int(distance // maximum_segment_m))
    if intermediate_count == 0:
        return [start]
    intermediate = GEOD.npts(start[0], start[1], end[0], end[1], intermediate_count)
    return [start, *((float(lon), float(lat)) for lon, lat in intermediate)]


def _wrap_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_valid and geometry.bounds[0] >= -180.0 and geometry.bounds[2] <= 180.0:
        return geometry
    world = box(-180.0, -90.0, 180.0, 90.0)
    pieces: list[Polygon] = []
    for shift in (-360.0, 0.0, 360.0):
        candidate = affinity.translate(geometry, xoff=shift)
        pieces.extend(part for part in _polygon_parts(candidate.intersection(world)) if part.area)
    if not pieces:
        raise ValueError("swath lies outside the WGS84 longitude domain")
    return unary_union(pieces)


def _densify_xy(
    start: tuple[float, float], end: tuple[float, float], maximum_segment_m: float = 25_000.0
) -> list[tuple[float, float]]:
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    count = max(1, math.ceil(distance / maximum_segment_m))
    return [
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count)
    ]


def swath_footprint(states: Sequence[OrbitState]) -> Geometry:
    edges = swath_edges(states)
    unwrapped = _unwrap([state.longitude for state in states])
    center_lon = sum(unwrapped) / len(unwrapped)
    center_lat = sum(state.latitude for state in states) / len(states)
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", local, always_xy=True, force_over=True)
    inverse = Transformer.from_crs(local, "EPSG:4326", always_xy=True, force_over=True)

    def local_point(point: Position) -> tuple[float, float]:
        longitude = point[0]
        while longitude - center_lon > 180.0:
            longitude -= 360.0
        while longitude - center_lon < -180.0:
            longitude += 360.0
        x, y = forward.transform(longitude, point[1])
        return float(x), float(y)

    local_edges = [(local_point(left), local_point(right)) for left, right in edges]
    envelope = MultiPoint([point for edge in local_edges for point in edge]).convex_hull
    if not isinstance(envelope, Polygon) or envelope.is_empty:
        raise ValueError("swath boundary samples do not span an area")
    boundary = list(envelope.exterior.coords)
    ring: list[tuple[float, float]] = []
    for index in range(len(boundary) - 1):
        ring.extend(_densify_xy(boundary[index], boundary[index + 1]))
    ring.append(boundary[0])
    local_strip = Polygon(ring)
    if local_strip.is_empty or not local_strip.is_valid:
        raise ValueError(
            f"swath strip is invalid in local projection: {explain_validity(local_strip)}"
        )
    geographic = transform_geometry(inverse.transform, local_strip)
    wrapped = _wrap_geometry(geographic)
    if wrapped.is_empty or not wrapped.is_valid:
        raise ValueError(f"swath strip union is invalid: {explain_validity(wrapped)}")
    geometry = mapping(wrapped)
    return {str(key): value for key, value in geometry.items()}
