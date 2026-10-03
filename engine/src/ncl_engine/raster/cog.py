"""Full-AOI raster mosaics read through the platform loopback COG adapter."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Collection, Sequence
from contextlib import ExitStack
from dataclasses import dataclass

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.mask import raster_geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_geom
from rasterio.windows import Window
from shapely.geometry import mapping, shape
from shapely.ops import transform

from ncl_engine.domain.models import Geometry
from ncl_engine.domain.policies import MAX_RASTER_PIXELS
from ncl_engine.sources.protocols import StacItem
from ncl_engine.sources.transport import DataTransport, LoopbackCogAdapter, gdal_environment

from .scl import CLEAR_CLASSES, SclCounts, count_scl
from .selection import Datatake, local_equal_area_crs
from .thumbnails import encode_rgba_png

MIN_HISTORY_AOI_PIXELS = 5_000


@dataclass(frozen=True, slots=True)
class SclAnalysis:
    counts: SclCounts
    source_resolution_m: float
    overview_factor: int


@dataclass(frozen=True, slots=True)
class RasterAnalysis:
    counts: SclCounts
    source_resolution_m: float
    overview_factor: int
    thumbnail_png: bytes
    thumbnail_width: int
    thumbnail_height: int


@dataclass(frozen=True, slots=True)
class _Grid:
    crs: object
    transform: Affine
    width: int
    height: int
    inside: np.ndarray


def _items(value: Datatake | StacItem | Sequence[StacItem]) -> tuple[StacItem, ...]:
    if isinstance(value, Datatake):
        return value.items
    if isinstance(value, StacItem):
        return (value,)
    output = tuple(value)
    if not output:
        raise ValueError("a datatake mosaic requires at least one STAC item")
    return output


def _grid(geometry: Geometry, resolution: float) -> _Grid:
    crs = local_equal_area_crs(geometry)
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True, force_over=True)
    projected = transform(transformer.transform, shape(geometry))
    min_x, min_y, max_x, max_y = projected.bounds
    west = math.floor(min_x / resolution) * resolution
    south = math.floor(min_y / resolution) * resolution
    east = math.ceil(max_x / resolution) * resolution
    north = math.ceil(max_y / resolution) * resolution
    width = max(1, int(round((east - west) / resolution)))
    height = max(1, int(round((north - south) / resolution)))
    affine = from_origin(west, north, resolution, resolution)
    inside = geometry_mask(
        [mapping(projected)],
        out_shape=(height, width),
        transform=affine,
        all_touched=False,
        invert=True,
    )
    return _Grid(crs=crs, transform=affine, width=width, height=height, inside=inside)


def _source_resolution(datasets: Sequence[rasterio.io.DatasetReader]) -> float:
    resolutions = [
        min(abs(float(dataset.res[0])), abs(float(dataset.res[1]))) for dataset in datasets
    ]
    return min(resolutions)


def _overview_factor(
    datasets: Sequence[rasterio.io.DatasetReader], geometry: Geometry, base_resolution: float
) -> tuple[int, _Grid]:
    common = set(datasets[0].overviews(1))
    for dataset in datasets[1:]:
        common.intersection_update(dataset.overviews(1))
    candidates = sorted({1, *common}, reverse=True)
    fallback = _grid(geometry, base_resolution)
    for factor in candidates:
        candidate = _grid(geometry, base_resolution * factor)
        if int(candidate.inside.sum()) >= MIN_HISTORY_AOI_PIXELS:
            return factor, candidate
    return 1, fallback


def _mosaic_scl(
    datasets: Sequence[rasterio.io.DatasetReader],
    geometry: Geometry,
    *,
    coarse: bool,
    surface_classes: Collection[int] = CLEAR_CLASSES,
) -> SclAnalysis:
    resolution = _source_resolution(datasets)
    if coarse:
        factor, grid = _overview_factor(datasets, geometry, resolution)
    else:
        factor, grid = 1, _grid(geometry, resolution)

    class_counts = np.zeros(12, dtype=np.int64)
    inside_count = 0
    valid_count = 0
    clear_count = 0
    invalid_count = 0
    with ExitStack() as overview_stack:
        read_datasets = list(datasets)
        if factor > 1:
            read_datasets = [
                overview_stack.enter_context(
                    rasterio.open(
                        dataset.name,
                        overview_level=dataset.overviews(1).index(factor),
                    )
                )
                for dataset in datasets
            ]
        block_side = max(1, int(math.sqrt(MAX_RASTER_PIXELS)))
        for row in range(0, grid.height, block_side):
            for column in range(0, grid.width, block_side):
                height = min(block_side, grid.height - row)
                width = min(block_side, grid.width - column)
                values = np.zeros((height, width), dtype=np.uint8)
                window = Window(column, row, width, height)
                block_transform = rasterio.windows.transform(window, grid.transform)
                for dataset in read_datasets:
                    tile = np.zeros_like(values)
                    reproject(
                        source=rasterio.band(dataset, 1),
                        destination=tile,
                        src_transform=dataset.transform,
                        src_crs=dataset.crs,
                        src_nodata=0,
                        dst_transform=block_transform,
                        dst_crs=grid.crs,
                        dst_nodata=0,
                        resampling=Resampling.nearest,
                    )
                    # Prefer an actual classified pixel where tiles overlap. Class 1 is
                    # retained as excluded evidence only when no valid class covers it.
                    values[(values <= 1) & (tile >= 2)] = tile[(values <= 1) & (tile >= 2)]
                    values[(values == 0) & (tile == 1)] = 1
                block = count_scl(
                    values,
                    grid.inside[row : row + height, column : column + width],
                    surface_classes=surface_classes,
                )
                class_counts += np.asarray(block.class_counts, dtype=np.int64)
                inside_count += block.inside_aoi_pixels
                valid_count += block.valid_pixels
                clear_count += block.clear_pixels
                invalid_count += block.invalid_pixels
    counts = SclCounts(
        class_counts=tuple(int(value) for value in class_counts),
        inside_aoi_pixels=inside_count,
        valid_pixels=valid_count,
        clear_pixels=clear_count,
        invalid_pixels=invalid_count,
        valid_coverage_percent=0.0 if inside_count == 0 else 100.0 * valid_count / inside_count,
        clear_percent=None if valid_count == 0 else 100.0 * clear_count / valid_count,
    )
    return SclAnalysis(
        counts=counts,
        source_resolution_m=resolution,
        overview_factor=factor,
    )


def _mosaic_thumbnail(
    datasets: Sequence[rasterio.io.DatasetReader], geometry: Geometry, long_edge: int
) -> tuple[bytes, int, int]:
    native_grid = _grid(geometry, 20.0)
    scale = max(native_grid.width, native_grid.height) / long_edge
    resolution = 20.0 * max(1.0, scale)
    grid = _grid(geometry, resolution)
    rgb = np.zeros((3, grid.height, grid.width), dtype=np.uint8)
    for dataset in datasets:
        projected = transform_geom("EPSG:4326", dataset.crs, geometry, antimeridian_cutting=True)
        _, _, window = raster_geometry_mask(dataset, [projected], crop=True, all_touched=False)
        window = window.round_offsets().round_lengths()
        source_width = max(1, int(window.width))
        source_height = max(1, int(window.height))
        source_scale = min(1.0, long_edge / max(source_width, source_height))
        read_width = max(1, int(round(source_width * source_scale)))
        read_height = max(1, int(round(source_height * source_scale)))
        source = dataset.read(
            [1, 2, 3],
            window=window,
            out_shape=(3, read_height, read_width),
            resampling=Resampling.bilinear,
        ).astype(np.uint8)
        source_transform = dataset.window_transform(window) @ Affine.scale(
            source_width / read_width, source_height / read_height
        )
        tile = np.zeros_like(rgb)
        for band in range(3):
            reproject(
                source=source[band],
                destination=tile[band],
                src_transform=source_transform,
                src_crs=dataset.crs,
                src_nodata=0,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=0,
                resampling=Resampling.bilinear,
            )
        available = np.any(tile != 0, axis=0)
        rgb[:, available] = tile[:, available]
    return encode_rgba_png(rgb, grid.inside), grid.width, grid.height


class RasterAnalyzer:
    def __init__(
        self,
        transport: DataTransport,
        *,
        thumbnail_long_edge: int = 640,
        cog_adapter_factory: Callable[[DataTransport], LoopbackCogAdapter] = LoopbackCogAdapter,
    ) -> None:
        self.transport = transport
        self.thumbnail_long_edge = thumbnail_long_edge
        self.cog_adapter_factory = cog_adapter_factory

    async def analyze(
        self,
        datatake: Datatake | StacItem | Sequence[StacItem],
        geometry: Geometry,
        *,
        surface_classes: Collection[int] = CLEAR_CLASSES,
    ) -> RasterAnalysis:
        loopback = self.cog_adapter_factory(self.transport)
        return await asyncio.to_thread(
            self._analyze_sync,
            datatake,
            geometry,
            loopback,
            surface_classes=frozenset(surface_classes),
        )

    async def analyze_scl(
        self,
        datatake: Datatake | StacItem | Sequence[StacItem],
        geometry: Geometry,
        *,
        coarse: bool = False,
        surface_classes: Collection[int] = CLEAR_CLASSES,
    ) -> SclAnalysis:
        loopback = self.cog_adapter_factory(self.transport)
        return await asyncio.to_thread(
            self._analyze_scl_sync,
            datatake,
            geometry,
            loopback,
            coarse=coarse,
            surface_classes=frozenset(surface_classes),
        )

    def _analyze_scl_sync(
        self,
        datatake: Datatake | StacItem | Sequence[StacItem],
        geometry: Geometry,
        loopback: LoopbackCogAdapter,
        *,
        coarse: bool = False,
        surface_classes: Collection[int] = CLEAR_CLASSES,
    ) -> SclAnalysis:
        with (
            loopback,
            gdal_environment(),
            ExitStack() as stack,
        ):
            datasets = [
                stack.enter_context(rasterio.open(loopback.register(item.assets["scl"])))
                for item in _items(datatake)
            ]
            return _mosaic_scl(
                datasets,
                geometry,
                coarse=coarse,
                surface_classes=surface_classes,
            )

    def _analyze_sync(
        self,
        datatake: Datatake | StacItem | Sequence[StacItem],
        geometry: Geometry,
        loopback: LoopbackCogAdapter,
        *,
        surface_classes: Collection[int] = CLEAR_CLASSES,
    ) -> RasterAnalysis:
        items = _items(datatake)
        with (
            loopback,
            gdal_environment(),
            ExitStack() as stack,
        ):
            scl_datasets = [
                stack.enter_context(rasterio.open(loopback.register(item.assets["scl"])))
                for item in items
            ]
            visual_datasets = [
                stack.enter_context(rasterio.open(loopback.register(item.assets["visual"])))
                for item in items
            ]
            scl = _mosaic_scl(
                scl_datasets,
                geometry,
                coarse=False,
                surface_classes=surface_classes,
            )
            thumbnail, width, height = _mosaic_thumbnail(
                visual_datasets, geometry, self.thumbnail_long_edge
            )
        return RasterAnalysis(
            counts=scl.counts,
            source_resolution_m=scl.source_resolution_m,
            overview_factor=scl.overview_factor,
            thumbnail_png=thumbnail,
            thumbnail_width=width,
            thumbnail_height=height,
        )
