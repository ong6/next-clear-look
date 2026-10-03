from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ncl_engine.domain.models import Geometry
from ncl_engine.raster.selection import Datatake, group_datatakes, select_scene_cover
from ncl_engine.sources.protocols import StacItem


def _item(identifier: str, when: datetime, tile: str, west: float, east: float) -> StacItem:
    geometry: Geometry = {
        "type": "Polygon",
        "coordinates": [[[west, 0.0], [east, 0.0], [east, 1.0], [west, 1.0], [west, 0.0]]],
    }
    return StacItem(
        id=identifier,
        collection="sentinel-2-l2a",
        platform="sentinel-2a",
        acquisition_time=when,
        tile=tile,
        relative_orbit=33,
        geometry=geometry,
        stac_self_url=f"https://example.test/{identifier}",
        assets={"scl": f"https://example.test/{identifier}/scl.tif", "visual": "x"},
        tile_cloud_cover_percent=12.0,
        raw={},
        snapshot=None,
        datatake_id="GS2A_20261003T000000_012345_N05.11",
    )


def test_tiles_with_realistic_timestamp_skew_form_one_datatake_mosaic() -> None:
    start = datetime(2026, 10, 3, tzinfo=UTC)
    items = [
        _item("tile-west", start, "45QZE", 0.0, 1.0),
        _item("tile-east", start + timedelta(seconds=13), "46QBF", 1.0, 2.0),
    ]
    grouped = group_datatakes(items)
    assert len(grouped) == 1
    assert grouped[0].id == "GS2A_20261003T000000_012345_N05.11"
    assert grouped[0].tiles == ("45QZE", "46QBF")
    assert grouped[0].acquisition_time == start

    aoi: Geometry = {
        "type": "Polygon",
        "coordinates": [[[0.25, 0.1], [1.75, 0.1], [1.75, 0.9], [0.25, 0.9], [0.25, 0.1]]],
    }
    selected = select_scene_cover(aoi, items)
    assert len(selected) == 1
    datatake, coverage = selected[0]
    assert isinstance(datatake, Datatake)
    assert coverage > 0.999
