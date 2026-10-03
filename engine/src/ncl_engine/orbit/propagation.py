"""SGP4 propagation with Skyfield's TEME-to-ITRS/WGS84 frame chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sgp4.api import jday
from skyfield.api import EarthSatellite, load, wgs84

from ncl_engine.domain.clock import require_utc

from .omm import OmmRecord


@dataclass(frozen=True, slots=True)
class OrbitState:
    time: datetime
    latitude: float
    longitude: float
    altitude_m: float
    inertial_position_km: tuple[float, float, float]


class OrbitPropagator:
    """Own one packaged-data Skyfield timescale and deterministic satellite objects."""

    def __init__(self) -> None:
        self.timescale = load.timescale(builtin=True)
        self._satellites: dict[str, EarthSatellite] = {}

    def install(self, records: list[OmmRecord]) -> None:
        self._satellites = {
            record.platform: EarthSatellite.from_omm(self.timescale, dict(record.values))
            for record in records
        }

    def platforms(self) -> list[str]:
        return sorted(self._satellites)

    def satellite(self, platform: str) -> EarthSatellite:
        try:
            return self._satellites[platform]
        except KeyError as exc:
            raise KeyError(f"no OMM is loaded for {platform}") from exc

    def state_at(self, platform: str, instant: datetime) -> OrbitState:
        when = require_utc(instant)
        position = self.satellite(platform).at(self.timescale.from_datetime(when))
        message = position.message
        if message:
            raise ValueError(f"SGP4 propagation failed for {platform}: {message}")
        subpoint = wgs84.geographic_position_of(position)
        vector = np.asarray(position.position.km, dtype=float)
        return OrbitState(
            time=when,
            latitude=float(subpoint.latitude.degrees),
            longitude=float(subpoint.longitude.degrees),
            altitude_m=float(subpoint.elevation.m),
            inertial_position_km=(float(vector[0]), float(vector[1]), float(vector[2])),
        )

    def states_at(self, platform: str, instants: list[datetime]) -> list[OrbitState]:
        if not instants:
            return []
        values = [require_utc(value) for value in instants]
        position = self.satellite(platform).at(self.timescale.from_datetimes(values))
        message: Any = position.message
        if message is not None:
            messages = np.asarray(message, dtype=object).reshape(-1)
            failures = [str(item) for item in messages if item]
            if failures:
                raise ValueError(f"SGP4 propagation failed for {platform}: {failures[0]}")
        subpoints = wgs84.geographic_position_of(position)
        latitudes = np.asarray(subpoints.latitude.degrees, dtype=float).reshape(-1)
        longitudes = np.asarray(subpoints.longitude.degrees, dtype=float).reshape(-1)
        altitudes = np.asarray(subpoints.elevation.m, dtype=float).reshape(-1)
        inertial = np.asarray(position.position.km, dtype=float)
        return [
            OrbitState(
                time=value,
                latitude=float(latitudes[index]),
                longitude=float(longitudes[index]),
                altitude_m=float(altitudes[index]),
                inertial_position_km=(
                    float(inertial[0, index]),
                    float(inertial[1, index]),
                    float(inertial[2, index]),
                ),
            )
            for index, value in enumerate(values)
        ]


def reference_vectors(
    propagator: OrbitPropagator, platform: str, instant: datetime
) -> dict[str, object]:
    """Expose auditable Skyfield/SGP4 vectors for pinned golden tests."""

    state = propagator.state_at(platform, instant)
    satellite = propagator.satellite(platform)
    when = require_utc(instant)
    julian_day, fraction = jday(
        when.year,
        when.month,
        when.day,
        when.hour,
        when.minute,
        when.second + when.microsecond / 1_000_000.0,
    )
    error, teme_position, teme_velocity = satellite.model.sgp4(julian_day, fraction)
    if error:
        raise ValueError(f"SGP4 error {error}")
    return {
        "teme_position_km": tuple(float(value) for value in teme_position),
        "teme_velocity_km_s": tuple(float(value) for value in teme_velocity),
        "gcrs_position_km": state.inertial_position_km,
        "wgs84": (state.longitude, state.latitude, state.altitude_m),
    }
