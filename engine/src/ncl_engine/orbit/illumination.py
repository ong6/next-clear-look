"""Solar geometry driven exclusively by the bundled JPL DE421 excerpt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from skyfield.api import wgs84
from skyfield.jpllib import SpiceKernel

from .propagation import OrbitPropagator, OrbitState


@dataclass(frozen=True, slots=True)
class Illumination:
    satellite_sunlit: bool
    aoi_sun_elevation_deg: float
    label: Literal["daylight", "low_sun"]


class IlluminationProvider(Protocol):
    def evaluate(
        self,
        platform: str,
        state: OrbitState,
        aoi_latitude: float,
        aoi_longitude: float,
    ) -> Illumination | None: ...


class De421Illumination:
    """Use the committed 2023-2027 BSP excerpt; never invoke Skyfield download helpers."""

    def __init__(self, propagator: OrbitPropagator, ephemeris_path: Path) -> None:
        if not ephemeris_path.is_file():
            raise FileNotFoundError(f"pinned DE421 excerpt is missing: {ephemeris_path}")
        self.propagator = propagator
        self.ephemeris = SpiceKernel(str(ephemeris_path))

    def evaluate(
        self,
        platform: str,
        state: OrbitState,
        aoi_latitude: float,
        aoi_longitude: float,
    ) -> Illumination | None:
        time = self.propagator.timescale.from_datetime(state.time)
        position = self.propagator.satellite(platform).at(time)
        sunlit = bool(position.is_sunlit(self.ephemeris))
        earth = self.ephemeris["earth"]
        sun = self.ephemeris["sun"]
        observer = earth + wgs84.latlon(aoi_latitude, aoi_longitude)
        altitude = observer.at(time).observe(sun).apparent().altaz()[0]
        elevation = float(altitude.degrees)
        if not sunlit or elevation <= 0.0:
            return None
        # Below 15 degrees, long shadows and atmospheric path length make the
        # image materially different from normal daylight. Keep the pass, but
        # label that limitation; a Sun below the horizon is excluded above.
        label: Literal["daylight", "low_sun"] = "daylight" if elevation >= 15.0 else "low_sun"
        return Illumination(
            satellite_sunlit=sunlit,
            aoi_sun_elevation_deg=elevation,
            label=label,
        )
