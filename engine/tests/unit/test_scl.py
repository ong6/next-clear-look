from __future__ import annotations

import numpy as np

from ncl_engine.raster.scl import count_scl, surface_class_policy, surface_classes_for_preset


def test_scl_taxonomy_counts_unclassified_as_clear_and_excludes_zero_one() -> None:
    values = np.arange(12, dtype=np.uint8).reshape(3, 4)
    inside = np.ones((3, 4), dtype=np.bool_)
    result = count_scl(values, inside)
    assert result.class_counts == (1,) * 12
    assert result.inside_aoi_pixels == 12
    assert result.invalid_pixels == 2
    assert result.valid_pixels == 10
    assert result.clear_pixels == 4
    assert result.clear_percent == 40.0


def test_scl_all_invalid_has_null_clear_percent() -> None:
    values = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    result = count_scl(values, np.ones_like(values, dtype=np.bool_))
    assert result.valid_pixels == 0
    assert result.clear_percent is None


def test_ice_subject_policy_counts_snow_as_clear_surface() -> None:
    values = np.array([[11, 9]], dtype=np.uint8)
    inside = np.ones_like(values, dtype=np.bool_)
    surface_classes = surface_classes_for_preset("jakobshavn-ice-front")
    result = count_scl(values, inside, surface_classes=surface_classes)
    policy = surface_class_policy(surface_classes)
    assert result.clear_pixels == 1
    assert result.clear_percent == 50.0
    assert policy.snow_ice_counted_as_surface is True
    assert policy.surface_scl_classes == [4, 5, 6, 7, 11]
