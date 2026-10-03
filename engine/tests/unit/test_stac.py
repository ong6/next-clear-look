from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ncl_engine.raster.stac import stac_search_body
from ncl_engine.seed import TUAS_GEOMETRY


def test_stac_search_uses_intersects_fields_and_no_cloud_filter() -> None:
    end = datetime(2026, 10, 3, tzinfo=UTC)
    body = stac_search_body(TUAS_GEOMETRY, end - timedelta(days=30), end)
    assert body["intersects"] == TUAS_GEOMETRY
    fields = body["fields"]
    assert isinstance(fields, dict)
    includes = fields["include"]
    assert isinstance(includes, list)
    assert "properties.sat:relative_orbit" in includes
    assert "properties.s2:product_uri" in includes
    assert "properties.s2:datatake_id" in includes
    excludes = fields["exclude"]
    assert isinstance(excludes, list)
    assert "assets.blue" in excludes
    assert "assets.scl" not in excludes
    assert "assets.visual" not in excludes
    serialized = repr(body).lower()
    assert "query" not in body
    assert "cloud_cover" in serialized  # Included as evidence, never used as a filter.
