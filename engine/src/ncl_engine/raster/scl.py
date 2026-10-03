"""AOI-level Sentinel-2 scene classification accounting."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ncl_engine.domain.models import SurfaceClassPolicy

# Vegetation, bare or built surface, water, and unclassified pixels are
# observable surface. Atmospheric obscuration, shadows, and snow or ice are
# excluded by default; an ice-focused preset can explicitly include SCL 11.
CLEAR_CLASSES = frozenset({4, 5, 6, 7})
VALID_CLASSES = frozenset(range(2, 12))
ICE_SURFACE_PRESETS = frozenset({"jakobshavn-ice-front"})
SCL_LABELS = (
    "No data",
    "Saturated or defective",
    "Dark area",
    "Cloud shadow",
    "Vegetation",
    "Not vegetated",
    "Water",
    "Unclassified",
    "Cloud medium probability",
    "Cloud high probability",
    "Thin cirrus",
    "Snow or ice",
)


@dataclass(frozen=True, slots=True)
class SclCounts:
    class_counts: tuple[int, ...]
    inside_aoi_pixels: int
    valid_pixels: int
    clear_pixels: int
    invalid_pixels: int
    valid_coverage_percent: float
    clear_percent: float | None


def surface_classes_for_preset(slug: str | None) -> frozenset[int]:
    if slug in ICE_SURFACE_PRESETS:
        return CLEAR_CLASSES | {11}
    return CLEAR_CLASSES


def surface_class_policy(surface_classes: Collection[int]) -> SurfaceClassPolicy:
    classes = sorted(set(surface_classes))
    return SurfaceClassPolicy(
        surface_scl_classes=classes,
        snow_ice_counted_as_surface=11 in classes,
    )


def count_scl(
    values: npt.NDArray[np.integer],
    inside: npt.NDArray[np.bool_],
    *,
    surface_classes: Collection[int] = CLEAR_CLASSES,
) -> SclCounts:
    if values.shape != inside.shape:
        raise ValueError("SCL values and AOI mask must have the same shape")
    if values.ndim != 2:
        raise ValueError("SCL values must be a two-dimensional band")
    selected = values[inside]
    counts = np.bincount(selected.astype(np.int64), minlength=12)[:12]
    inside_count = int(selected.size)
    valid_count = int(sum(int(counts[index]) for index in VALID_CLASSES))
    clear_count = int(sum(int(counts[index]) for index in surface_classes))
    invalid_count = inside_count - valid_count
    valid_coverage = 0.0 if inside_count == 0 else 100.0 * valid_count / inside_count
    clear_percent = None if valid_count == 0 else 100.0 * clear_count / valid_count
    return SclCounts(
        class_counts=tuple(int(value) for value in counts),
        inside_aoi_pixels=inside_count,
        valid_pixels=valid_count,
        clear_pixels=clear_count,
        invalid_pixels=invalid_count,
        valid_coverage_percent=valid_coverage,
        clear_percent=clear_percent,
    )
