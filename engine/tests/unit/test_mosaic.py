from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from ncl_engine.raster.cog import _mosaic_scl, _mosaic_thumbnail
from ncl_engine.raster.thumbnails import encode_rgba_png


def _geometry(west: float, south: float, east: float, north: float) -> dict[str, object]:
    transformer = Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)
    points = [
        transformer.transform(west, south),
        transformer.transform(east, south),
        transformer.transform(east, north),
        transformer.transform(west, north),
        transformer.transform(west, south),
    ]
    return {"type": "Polygon", "coordinates": [points]}


def _write(path: Path, west: float, north: float, value: int) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=50,
        height=50,
        count=1,
        dtype="uint8",
        crs="EPSG:32645",
        transform=from_origin(west, north, 20.0, 20.0),
        tiled=True,
    ) as dataset:
        dataset.write(np.full((50, 50), value, dtype=np.uint8), 1)


def test_partial_tile_uses_full_aoi_mask_as_denominator(tmp_path: Path) -> None:
    path = tmp_path / "west.tif"
    _write(path, 500_000.0, 1_000.0, 4)
    aoi = _geometry(500_000.0, 0.0, 502_000.0, 1_000.0)
    with rasterio.open(path) as dataset:
        result = _mosaic_scl([dataset], aoi, coarse=False)
    assert result.counts.inside_aoi_pixels > result.counts.valid_pixels
    assert 45.0 < result.counts.valid_coverage_percent < 55.0
    assert result.counts.clear_percent == 100.0


def test_multi_tile_scl_is_mosaicked_on_one_aoi_grid(tmp_path: Path) -> None:
    west = tmp_path / "west.tif"
    east = tmp_path / "east.tif"
    _write(west, 500_000.0, 1_000.0, 4)
    _write(east, 501_000.0, 1_000.0, 9)
    aoi = _geometry(500_000.0, 0.0, 502_000.0, 1_000.0)
    with rasterio.open(west) as west_dataset, rasterio.open(east) as east_dataset:
        result = _mosaic_scl([west_dataset, east_dataset], aoi, coarse=False)
    assert result.counts.valid_coverage_percent > 99.0
    assert 48.0 < (result.counts.clear_percent or 0.0) < 52.0


def test_history_reads_pixels_from_the_selected_overview(tmp_path: Path) -> None:
    path = tmp_path / "history.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=400,
        height=400,
        count=1,
        dtype="uint8",
        crs="EPSG:32645",
        transform=from_origin(500_000.0, 8_000.0, 20.0, 20.0),
        tiled=True,
    ) as dataset:
        dataset.write(np.full((400, 400), 9, dtype=np.uint8), 1)
        dataset.build_overviews([2, 4], Resampling.nearest)
        # Rewrite only the base layer. The intentionally stale overview remains
        # cloudy, making it observable whether the analysis really opens it.
        dataset.write(np.full((400, 400), 4, dtype=np.uint8), 1)
    aoi = _geometry(500_000.0, 0.0, 508_000.0, 8_000.0)
    with rasterio.open(path) as dataset:
        assert int(dataset.read(1)[0, 0]) == 4
        with rasterio.open(path, overview_level=1) as overview:
            assert int(overview.read(1)[0, 0]) == 9
        result = _mosaic_scl([dataset], aoi, coarse=True)
    assert result.overview_factor == 4
    assert result.counts.inside_aoi_pixels >= 5_000
    assert result.counts.class_counts[9] == result.counts.valid_pixels
    assert result.counts.clear_percent == 0.0


def test_multi_tile_thumbnail_mosaic_is_clipped_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "visual.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=100,
        height=50,
        count=3,
        dtype="uint8",
        crs="EPSG:32645",
        transform=from_origin(500_000.0, 1_000.0, 20.0, 20.0),
    ) as dataset:
        dataset.write(np.full((3, 50, 100), 120, dtype=np.uint8))
    aoi = _geometry(500_000.0, 0.0, 502_000.0, 1_000.0)
    with rasterio.open(path) as dataset:
        png, width, height = _mosaic_thumbnail([dataset], aoi, 64)
    assert max(width, height) <= 64
    assert Image.open(BytesIO(png)).mode == "RGBA"


def test_thumbnail_encoder_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="RGB data"):
        encode_rgba_png(np.zeros((2, 2), dtype=np.uint8), np.zeros((2, 2), dtype=np.bool_))
    with pytest.raises(ValueError, match="mask must match"):
        encode_rgba_png(np.zeros((3, 2, 2), dtype=np.uint8), np.zeros((1, 1), dtype=np.bool_))


def test_thumbnail_encoder_lets_pillow_infer_rgba_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Image.fromarray

    def fromarray(array: np.ndarray, *args: object, **kwargs: object) -> Image.Image:
        assert args == ()
        assert "mode" not in kwargs
        return original(array)

    monkeypatch.setattr("ncl_engine.raster.thumbnails.Image.fromarray", fromarray)
    png = encode_rgba_png(
        np.full((3, 2, 2), 10, dtype=np.uint8),
        np.ones((2, 2), dtype=np.bool_),
    )
    assert Image.open(BytesIO(png)).mode == "RGBA"
