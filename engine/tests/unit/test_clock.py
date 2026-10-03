from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ncl_engine.domain.clock import FrozenClock


def test_frozen_clock_advances_only_forward() -> None:
    initial = datetime(2026, 10, 3, tzinfo=UTC)
    clock = FrozenClock(initial)
    assert clock.now() == initial
    clock.advance_to(initial + timedelta(seconds=1))
    assert clock.now() == initial + timedelta(seconds=1)
    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance_to(initial)


def test_frozen_clock_rejects_naive_instants() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 10, 3))
