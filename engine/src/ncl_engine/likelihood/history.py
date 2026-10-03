"""Historical acquisition and AOI-clear trials for the clear-look likelihood."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ncl_engine.likelihood.trials import cyclic_day_distance
from ncl_engine.raster.selection import Datatake

REPEAT_CYCLE_DAYS = 10
REPEAT_MATCH_TOLERANCE_DAYS = REPEAT_CYCLE_DAYS // 2
SEASON_WINDOW_DAYS = 45


@dataclass(frozen=True, slots=True)
class HistoryEvaluation:
    datatake_id: str
    platform: str
    relative_orbit: int | None
    acquisition_time: datetime
    clear_percent: float | None
    valid_coverage_percent: float
    overview_factor: int


def local_date(instant: datetime, timezone: str) -> date:
    return instant.astimezone(ZoneInfo(timezone)).date()


def is_seasonal(instant: datetime, as_of: datetime, timezone: str) -> bool:
    return (
        cyclic_day_distance(local_date(instant, timezone), local_date(as_of, timezone))
        <= SEASON_WINDOW_DAYS
    )


def seasonal_datatakes(
    datatakes: list[Datatake], *, as_of: datetime, timezone: str
) -> list[Datatake]:
    return [
        datatake
        for datatake in datatakes
        if is_seasonal(datatake.acquisition_time, as_of, timezone)
    ]


def acquisition_trial_counts(
    datatakes: list[Datatake],
    *,
    history_start: datetime,
    history_end: datetime,
    timezone: str,
) -> tuple[int, int]:
    """Enumerate each platform/orbit's 10-day cycles and match acquisitions once."""

    by_path: dict[tuple[str, int], list[date]] = {}
    for datatake in datatakes:
        if datatake.relative_orbit is None:
            continue
        key = (datatake.platform, datatake.relative_orbit)
        by_path.setdefault(key, []).append(local_date(datatake.acquisition_time, timezone))

    start_date = local_date(history_start, timezone)
    end_date = local_date(history_end, timezone)
    successes = 0
    failures = 0
    for observed_dates in by_path.values():
        observed = sorted(set(observed_dates))
        expected: list[date] = []
        candidate = observed[0]
        while candidate < end_date:
            if (
                candidate >= start_date
                and cyclic_day_distance(candidate, end_date) <= SEASON_WINDOW_DAYS
            ):
                expected.append(candidate)
            candidate += timedelta(days=REPEAT_CYCLE_DAYS)

        unmatched = {
            value
            for value in observed
            if start_date <= value < end_date
            and cyclic_day_distance(value, end_date) <= SEASON_WINDOW_DAYS
        }
        for opportunity_date in expected:
            match = min(
                (
                    value
                    for value in unmatched
                    if abs((value - opportunity_date).days) <= REPEAT_MATCH_TOLERANCE_DAYS
                ),
                key=lambda value: abs((value - opportunity_date).days),
                default=None,
            )
            if match is None:
                failures += 1
            else:
                successes += 1
                unmatched.remove(match)
    return successes, failures


def clear_trial_counts(
    evaluations: list[HistoryEvaluation],
    *,
    minimum_clear_percent: float = 70.0,
    minimum_valid_coverage_percent: float = 95.0,
) -> tuple[int, int, int]:
    successes = 0
    failures = 0
    excluded = 0
    for evaluation in evaluations:
        if (
            evaluation.clear_percent is None
            or evaluation.valid_coverage_percent < minimum_valid_coverage_percent
        ):
            excluded += 1
        elif evaluation.clear_percent >= minimum_clear_percent:
            successes += 1
        else:
            failures += 1
    return successes, failures, excluded
