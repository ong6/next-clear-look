from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from ncl_engine.analysis import build_likelihood
from ncl_engine.domain.models import Opportunity, SceneSummary
from ncl_engine.likelihood.beta import estimate_likelihood, posterior
from ncl_engine.likelihood.hindcast import match_opportunities_to_scenes
from ncl_engine.likelihood.history import (
    HistoryEvaluation,
    acquisition_trial_counts,
    clear_trial_counts,
    local_date,
)
from ncl_engine.likelihood.trials import (
    HistoricalTrial,
    cyclic_day_distance,
    group_by_opportunity_day,
    seasonal_trials,
)
from ncl_engine.raster.selection import Datatake


def test_beta_posterior_counts() -> None:
    value = posterior(12, 7, 2)
    assert (value.alpha, value.beta, value.sample_size) == (13.0, 8.0, 19)
    assert value.excluded_count == 2
    with pytest.raises(ValueError, match="cannot be negative"):
        posterior(-1, 0)


def test_monte_carlo_is_deterministic() -> None:
    def estimate() -> object:
        return estimate_likelihood(
            aoi_hash="a" * 64,
            as_of=datetime(2026, 10, 3, tzinfo=UTC),
            future_counts={7: (2, 3), 14: (5, 7)},
            acquisition_successes=30,
            acquisition_failures=10,
            clear_successes=25,
            clear_failures=15,
            draws=10_000,
        )

    first = estimate_likelihood(
        aoi_hash="a" * 64,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
        future_counts={7: (2, 3), 14: (5, 7)},
        acquisition_successes=30,
        acquisition_failures=10,
        clear_successes=25,
        clear_failures=15,
        draws=10_000,
    )
    second = estimate()
    assert first == second
    assert first[2][0].probability is not None


def test_multiple_passes_on_one_day_are_one_likelihood_draw() -> None:
    _, _, repeated_passes, _ = estimate_likelihood(
        aoi_hash="f" * 64,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
        future_counts={7: (2, 6), 14: (2, 6)},
        acquisition_successes=30,
        acquisition_failures=10,
        clear_successes=25,
        clear_failures=15,
        draws=10_000,
    )
    _, _, one_pass_per_day, _ = estimate_likelihood(
        aoi_hash="f" * 64,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
        future_counts={7: (2, 2), 14: (2, 2)},
        acquisition_successes=30,
        acquisition_failures=10,
        clear_successes=25,
        clear_failures=15,
        draws=10_000,
    )
    assert [item.probability for item in repeated_passes] == [
        item.probability for item in one_pass_per_day
    ]
    assert [item.credible_interval for item in repeated_passes] == [
        item.credible_interval for item in one_pass_per_day
    ]
    assert repeated_passes[0].opportunity_count == 6


def test_insufficient_data_stays_null_even_with_zero_opportunities() -> None:
    _, _, horizons, _ = estimate_likelihood(
        aoi_hash="b" * 64,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
        future_counts={7: (1, 1), 14: (0, 0)},
        acquisition_successes=1,
        acquisition_failures=1,
        clear_successes=1,
        clear_failures=1,
        draws=100,
    )
    assert horizons[0].probability is None
    assert horizons[0].credible_interval is None
    assert horizons[1].probability is None
    assert horizons[1].credible_interval is None


def test_zero_opportunities_is_zero_only_after_data_is_sufficient() -> None:
    _, _, horizons, _ = estimate_likelihood(
        aoi_hash="d" * 64,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
        future_counts={7: (0, 0), 14: (0, 0)},
        acquisition_successes=20,
        acquisition_failures=0,
        clear_successes=20,
        clear_failures=0,
        draws=100,
    )
    assert all(horizon.probability == 0.0 for horizon in horizons)
    assert all(horizon.credible_interval is not None for horizon in horizons)


def test_ten_day_repeat_history_with_every_expected_acquisition_is_near_one() -> None:
    end = datetime(2026, 10, 3, tzinfo=UTC)
    start = end - timedelta(days=3 * 365)
    acquisitions = [
        Datatake(
            id=f"dt-{index}",
            platform="sentinel-2a",
            acquisition_time=start + timedelta(days=10 * index),
            relative_orbit=33,
            items=(),
            footprint={"type": "Polygon", "coordinates": []},
        )
        for index in range(110)
        if start + timedelta(days=10 * index) < end
    ]
    successes, failures = acquisition_trial_counts(
        acquisitions,
        history_start=start,
        history_end=end,
        timezone="Asia/Singapore",
    )
    value = posterior(successes, failures)
    assert successes >= 20
    assert failures == 0
    assert value.alpha / (value.alpha + value.beta) > 0.95


def test_full_seasonal_scl_history_makes_likelihood_computable() -> None:
    as_of = datetime(2026, 10, 3, tzinfo=UTC)
    evaluations = [
        HistoryEvaluation(
            datatake_id=f"dt-{index}",
            platform="sentinel-2a",
            relative_orbit=33,
            acquisition_time=as_of - timedelta(days=10 * index),
            clear_percent=80.0 if index % 2 == 0 else 60.0,
            valid_coverage_percent=100.0,
            overview_factor=4,
        )
        for index in range(24)
    ]
    clear_successes, clear_failures, excluded = clear_trial_counts(evaluations)
    _, clear, horizons, _ = estimate_likelihood(
        aoi_hash="c" * 64,
        as_of=as_of,
        future_counts={7: (2, 2), 14: (5, 5)},
        acquisition_successes=22,
        acquisition_failures=2,
        clear_successes=clear_successes,
        clear_failures=clear_failures,
        excluded=excluded,
        draws=1_000,
    )
    assert clear.sample_size == 24
    assert all(horizon.probability is not None for horizon in horizons)


def test_opportunity_day_uses_aoi_timezone_not_server_timezone() -> None:
    instant = datetime(2026, 10, 3, 16, 30, tzinfo=UTC)
    assert local_date(instant, "UTC").isoformat() == "2026-10-03"
    assert local_date(instant, "Asia/Singapore").isoformat() == "2026-10-04"


def test_hindcast_matches_each_opportunity_and_scene_at_most_once() -> None:
    start = datetime(2026, 10, 3, tzinfo=UTC)
    opportunities = cast(
        list[Opportunity],
        [
            SimpleNamespace(id="opp-1", platform="sentinel-2a", closest_time=start),
            SimpleNamespace(
                id="opp-2", platform="sentinel-2a", closest_time=start + timedelta(minutes=10)
            ),
            SimpleNamespace(id="opp-b", platform="sentinel-2b", closest_time=start),
        ],
    )
    scenes = cast(
        list[SceneSummary],
        [
            SimpleNamespace(
                id="scene-1",
                platform="sentinel-2a",
                acquisition_time=start + timedelta(minutes=4),
            ),
            SimpleNamespace(
                id="scene-far",
                platform="sentinel-2a",
                acquisition_time=start + timedelta(hours=2),
            ),
        ],
    )
    assert match_opportunities_to_scenes(opportunities, scenes) == {"opp-1": "scene-1"}


def test_seasonal_and_opportunity_day_trial_grouping() -> None:
    as_of = datetime(2026, 10, 3, tzinfo=UTC).date()
    trials = [
        HistoricalTrial("one", as_of, True, False, "scene-1", 60.0),
        HistoricalTrial("two", as_of, True, True, "scene-2", 90.0),
        HistoricalTrial("three", as_of - timedelta(days=1), False, None, excluded_reason="missing"),
        HistoricalTrial("old", as_of - timedelta(days=100), True, True),
    ]
    assert cyclic_day_distance(as_of, as_of) == 0
    assert len(seasonal_trials(trials, as_of=as_of)) == 3
    grouped = group_by_opportunity_day(trials[:3])
    assert len(grouped) == 2
    assert grouped[0].acquired is False
    assert grouped[0].excluded_reason == "missing"
    assert grouped[1].acquired is True
    assert grouped[1].clear is True
    assert grouped[1].clear_percent == 90.0


def test_cyclic_day_distance_across_leap_year_new_year() -> None:
    assert (
        cyclic_day_distance(
            datetime(2024, 12, 31, tzinfo=UTC).date(),
            datetime(2025, 1, 1, tzinfo=UTC).date(),
        )
        == 1
    )
    assert (
        cyclic_day_distance(
            datetime(2024, 12, 30, tzinfo=UTC).date(),
            datetime(2025, 1, 1, tzinfo=UTC).date(),
        )
        == 2
    )


def test_shared_likelihood_builder_keeps_tier_and_exclusions_consistent() -> None:
    as_of = datetime(2026, 10, 3, tzinfo=UTC)
    datatake = Datatake(
        id="missing-scl",
        platform="sentinel-2a",
        acquisition_time=as_of - timedelta(days=10),
        relative_orbit=33,
        items=(),
        footprint={"type": "Polygon", "coordinates": []},
    )
    likelihood = build_likelihood(
        aoi_id="aoi-test",
        geometry_sha256="e" * 64,
        timezone_name="UTC",
        preset_slug=None,
        opportunities=[],
        history_datatakes=[datatake],
        history_evaluations=[],
        history_start=as_of - timedelta(days=365),
        history_end=as_of,
        computed_at=as_of,
    )
    assert likelihood.quality == "insufficient-data"
    assert likelihood.season["tier"] == likelihood.quality
    assert likelihood.clear_posterior.excluded_count == 1
    assert len(likelihood.excluded_evidence) == 1
