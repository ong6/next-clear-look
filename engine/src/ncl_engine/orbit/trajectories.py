"""Compact trajectory sampling for client-side interpolation."""

from __future__ import annotations

from datetime import datetime, timedelta

from ncl_engine.domain.models import Trajectory, TrajectorySample
from ncl_engine.domain.policies import ORBIT_ALGORITHM
from ncl_engine.provenance.hashing import stable_id

from .propagation import OrbitPropagator
from .sensor import swath_edges


def time_grid(start: datetime, end: datetime, step_seconds: int) -> list[datetime]:
    if end <= start:
        raise ValueError("end must be after start")
    if step_seconds <= 0:
        raise ValueError("step_seconds must be positive")
    count = int((end - start).total_seconds() // step_seconds)
    values = [start + timedelta(seconds=index * step_seconds) for index in range(count + 1)]
    if values[-1] < end:
        values.append(end)
    return values


def sample_trajectory(
    propagator: OrbitPropagator,
    platform: str,
    start: datetime,
    end: datetime,
    *,
    step_seconds: int = 60,
) -> Trajectory:
    states = propagator.states_at(platform, time_grid(start, end, step_seconds))
    edges = swath_edges(states)
    samples = [
        TrajectorySample(
            time=state.time,
            latitude=state.latitude,
            longitude=state.longitude,
            altitude_m=state.altitude_m,
            swath_left=edges[index][0],
            swath_right=edges[index][1],
        )
        for index, state in enumerate(states)
    ]
    provenance_id = stable_id("prv", platform, start.isoformat(), end.isoformat(), ORBIT_ALGORITHM)
    return Trajectory(
        satellite_id=platform,
        sample_interval_seconds=step_seconds,
        start_time=start,
        end_time=end,
        samples=samples,
        provenance_id=provenance_id,
    )
