from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ncl_engine.orbit.intersection import bisect_crossing, golden_minimum


@settings(max_examples=200, deadline=None)
@given(closest=st.floats(min_value=0.1, max_value=19.9, allow_nan=False, allow_infinity=False))
def test_coarse_phase_refinement_converges_below_tolerance(closest: float) -> None:
    minimum_at, value = golden_minimum(lambda offset: (offset - closest) ** 2, 0.0, 20.0, 0.05)
    assert abs(minimum_at - closest) <= 0.05
    assert value <= 0.05**2


@settings(max_examples=200, deadline=None)
@given(crossing=st.floats(min_value=0.1, max_value=19.9, allow_nan=False, allow_infinity=False))
def test_entry_bisection_converges_below_tolerance(crossing: float) -> None:
    result = bisect_crossing(lambda offset: crossing - offset, 0.0, 20.0, 0.05)
    assert abs(result - crossing) <= 0.05
