"""Injected domain clock. Operational waits always use asyncio's monotonic clock."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock values must be timezone-aware")
    return value.astimezone(UTC)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    def __init__(self, instant: datetime) -> None:
        self._instant = require_utc(instant)

    def now(self) -> datetime:
        return self._instant

    def advance_to(self, instant: datetime) -> None:
        candidate = require_utc(instant)
        if candidate < self._instant:
            raise ValueError("a frozen replay clock cannot move backwards")
        self._instant = candidate
