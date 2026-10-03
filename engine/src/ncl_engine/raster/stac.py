"""Canonical Earth Search queries without tile-wide cloud filtering."""

from __future__ import annotations

from datetime import UTC, datetime

from ncl_engine.domain.models import Geometry

_UNUSED_SENTINEL_ASSETS = (
    "aot",
    "aot-jp2",
    "blue",
    "blue-jp2",
    "cloud",
    "coastal",
    "coastal-jp2",
    "granule_metadata",
    "green",
    "green-jp2",
    "nir",
    "nir-jp2",
    "nir08",
    "nir08-jp2",
    "nir09",
    "nir09-jp2",
    "product_metadata",
    "red",
    "red-jp2",
    "rededge1",
    "rededge1-jp2",
    "rededge2",
    "rededge2-jp2",
    "rededge3",
    "rededge3-jp2",
    "scl-jp2",
    "snow",
    "swir16",
    "swir16-jp2",
    "swir22",
    "swir22-jp2",
    "thumbnail",
    "tileinfo_metadata",
    "visual-jp2",
    "wvp",
    "wvp-jp2",
)


def stac_search_body(geometry: Geometry, start: datetime, end: datetime) -> dict[str, object]:
    if end <= start:
        raise ValueError("STAC end must be after start")
    return {
        "collections": ["sentinel-2-l2a"],
        "intersects": geometry,
        "datetime": f"{start.astimezone(UTC).isoformat().replace('+00:00', 'Z')}/"
        f"{end.astimezone(UTC).isoformat().replace('+00:00', 'Z')}",
        "limit": 100,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        "fields": {
            "include": [
                "id",
                "collection",
                "geometry",
                "properties.datetime",
                "properties.platform",
                "properties.eo:cloud_cover",
                "properties.sat:relative_orbit",
                "properties.grid:code",
                "properties.s2:mgrs_tile",
                "properties.s2:datatake_id",
                "properties.s2:product_uri",
                "assets.scl.href",
                "assets.visual.href",
            ],
            "exclude": [
                "bbox",
                *[f"assets.{name}" for name in _UNUSED_SENTINEL_ASSETS],
                "assets.scl.proj:shape",
                "assets.scl.proj:transform",
                "assets.scl.roles",
                "assets.scl.gsd",
                "assets.scl.type",
                "assets.scl.title",
                "assets.scl.raster:bands",
                "assets.visual.proj:shape",
                "assets.visual.proj:transform",
                "assets.visual.roles",
                "assets.visual.eo:bands",
                "assets.visual.gsd",
                "assets.visual.type",
                "assets.visual.title",
                "assets.visual.raster:bands",
            ],
        },
    }
