"""Seasonal past-look trial construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class HistoricalTrial:
    opportunity_id: str
    local_date: date
    acquired: bool
    clear: bool | None
    scene_id: str | None = None
    clear_percent: float | None = None
    excluded_reason: str | None = None


def cyclic_day_distance(left: date, right: date) -> int:
    # Use one leap-year calendar for month/day comparison. A fixed 366-day
    # cycle preserves February 29 and keeps New Year's Eve exactly one day
    # from New Year's Day regardless of the input years.
    left_day = date(2000, left.month, left.day).timetuple().tm_yday
    right_day = date(2000, right.month, right.day).timetuple().tm_yday
    difference = abs(left_day - right_day)
    return min(difference, 366 - difference)


def seasonal_trials(
    trials: list[HistoricalTrial], *, as_of: date, window_days: int = 45
) -> list[HistoricalTrial]:
    return [
        trial for trial in trials if cyclic_day_distance(trial.local_date, as_of) <= window_days
    ]


def group_by_opportunity_day(trials: list[HistoricalTrial]) -> list[HistoricalTrial]:
    by_date: dict[date, list[HistoricalTrial]] = {}
    for trial in trials:
        by_date.setdefault(trial.local_date, []).append(trial)
    output: list[HistoricalTrial] = []
    for local_date, values in sorted(by_date.items()):
        acquired = any(value.acquired for value in values)
        known_clear = [value for value in values if value.clear is not None]
        excluded = next((value.excluded_reason for value in values if value.excluded_reason), None)
        clear = any(value.clear is True for value in known_clear) if known_clear else None
        output.append(
            HistoricalTrial(
                opportunity_id=values[0].opportunity_id,
                local_date=local_date,
                acquired=acquired,
                clear=clear,
                scene_id=next((value.scene_id for value in values if value.scene_id), None),
                clear_percent=max(
                    (value.clear_percent for value in values if value.clear_percent is not None),
                    default=None,
                ),
                excluded_reason=excluded,
            )
        )
    return output
