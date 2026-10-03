"""Deterministic Monte Carlo combination of acquisition and clear Beta posteriors."""

from __future__ import annotations

import hashlib
from datetime import datetime

import numpy as np

from ncl_engine.domain.models import BetaPosterior, CredibleInterval, HorizonLikelihood


def deterministic_seed(aoi_hash: str, as_of: datetime, model_version: str) -> int:
    material = f"{aoi_hash}|{as_of.isoformat()}|{model_version}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=False)


def posterior(successes: int, failures: int, excluded: int = 0) -> BetaPosterior:
    if min(successes, failures, excluded) < 0:
        raise ValueError("posterior counts cannot be negative")
    return BetaPosterior(
        alpha=1.0 + successes,
        beta=1.0 + failures,
        sample_size=successes + failures,
        success_count=successes,
        failure_count=failures,
        excluded_count=excluded,
    )


def estimate_likelihood(
    *,
    aoi_hash: str,
    as_of: datetime,
    future_counts: dict[int, tuple[int, int]],
    acquisition_successes: int,
    acquisition_failures: int,
    clear_successes: int,
    clear_failures: int,
    excluded: int = 0,
    minimum_trials: int = 20,
    draws: int = 100_000,
    model_version: str = "seasonal-beta-acquisition-clear-v1",
) -> tuple[BetaPosterior, BetaPosterior, list[HorizonLikelihood], int]:
    acquisition = posterior(acquisition_successes, acquisition_failures)
    clear = posterior(clear_successes, clear_failures, excluded)
    seed = deterministic_seed(aoi_hash, as_of, model_version)
    enough_data = acquisition.sample_size >= minimum_trials and clear.sample_size >= minimum_trials
    generator = np.random.Generator(np.random.PCG64(seed))
    acquisition_draws = generator.beta(acquisition.alpha, acquisition.beta, draws)
    clear_draws = generator.beta(clear.alpha, clear.beta, draws)
    per_opportunity_day = acquisition_draws * clear_draws
    horizons: list[HorizonLikelihood] = []
    for days in (7, 14):
        opportunity_days, opportunity_count = future_counts.get(days, (0, 0))
        if not enough_data:
            probability = None
            interval: CredibleInterval | None = None
        elif opportunity_days == 0:
            probability = 0.0
            interval = CredibleInterval(lower=0.0, upper=0.0)
        else:
            outcomes = 1.0 - np.power(1.0 - per_opportunity_day, opportunity_days)
            probability = float(np.mean(outcomes))
            lower, upper = np.quantile(outcomes, [0.05, 0.95])
            interval = CredibleInterval(lower=float(lower), upper=float(upper))
        horizons.append(
            HorizonLikelihood(
                days=days,
                opportunity_days=opportunity_days,
                opportunity_count=opportunity_count,
                probability=probability,
                credible_interval=interval,
            )
        )
    return acquisition, clear, horizons, seed
