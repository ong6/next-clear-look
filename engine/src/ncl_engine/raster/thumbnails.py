"""Deterministic transparent PNG encoding for AOI-clipped true colour."""

from __future__ import annotations

from io import BytesIO

import numpy as np
import numpy.typing as npt
from PIL import Image


def encode_rgba_png(rgb: npt.NDArray[np.uint8], inside: npt.NDArray[np.bool_]) -> bytes:
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("RGB data must have shape (3, height, width)")
    if inside.shape != rgb.shape[1:]:
        raise ValueError("thumbnail AOI mask must match RGB dimensions")
    alpha = np.where(inside & np.any(rgb != 0, axis=0), 255, 0).astype(np.uint8)
    rgba = np.concatenate((np.moveaxis(rgb, 0, -1), alpha[..., None]), axis=2)
    buffer = BytesIO()
    Image.fromarray(rgba).save(
        buffer,
        format="PNG",
        optimize=False,
        compress_level=9,
    )
    return buffer.getvalue()
