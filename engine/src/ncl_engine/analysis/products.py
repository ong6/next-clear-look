"""Construct public analysis products from algorithm outputs.

The live service and fixture recorder deliberately meet here so policy fields,
sample accounting, and evidence wording cannot drift between execution modes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from ncl_engine.domain.models import (
    ClassCount,
    ExcludedEvidence,
    Likelihood,
    Opportunity,
    RasterStatistics,
    TrialEvidence,
)
from ncl_engine.domain.policies import LIKELIHOOD_ALGORITHM, LIKELIHOOD_INTERPRETATION
from ncl_engine.likelihood import (
    HistoryEvaluation,
    acquisition_trial_counts,
    clear_trial_counts,
    estimate_likelihood,
    seasonal_datatakes,
)
from ncl_engine.provenance.hashing import stable_id
from ncl_engine.raster.scl import (
    SCL_LABELS,
    VALID_CLASSES,
    SclCounts,
    surface_class_policy,
    surface_classes_for_preset,
)
from ncl_engine.raster.selection import Datatake

MINIMUM_CLEAR_PERCENT = 70.0
MINIMUM_VALID_COVERAGE_PERCENT = 95.0
HORIZON_DAYS = 14
MINIMUM_TRIALS = 20


def build_raster_statistics(
    *,
    scene_id: str,
    aoi_id: str,
    preset_slug: str | None,
    counts: SclCounts,
    source_resolution_m: float,
    overview_factor: int,
    computed_at: datetime,
    provenance_id: str,
) -> RasterStatistics:
    """Map one SCL analysis into the canonical statistics payload."""

    surface_classes = surface_classes_for_preset(preset_slug)
    return RasterStatistics(
        scene_id=scene_id,
        aoi_id=aoi_id,
        clear_percent=counts.clear_percent,
        valid_coverage_percent=counts.valid_coverage_percent,
        clear_pixels=counts.clear_pixels,
        valid_pixels=counts.valid_pixels,
        inside_aoi_pixels=counts.inside_aoi_pixels,
        invalid_pixels=counts.invalid_pixels,
        clear_scl_classes=sorted(surface_classes),
        valid_scl_classes=sorted(VALID_CLASSES),
        surface_class_policy=surface_class_policy(surface_classes),
        class_counts={
            str(value): ClassCount(label=SCL_LABELS[value], pixels=counts.class_counts[value])
            for value in range(12)
        },
        source_resolution_m=source_resolution_m,
        overview_factor=overview_factor,
        computed_at=computed_at,
        provenance_id=provenance_id,
    )


def build_likelihood(
    *,
    aoi_id: str,
    geometry_sha256: str,
    timezone_name: str,
    preset_slug: str | None,
    opportunities: Sequence[Opportunity],
    history_datatakes: list[Datatake],
    history_evaluations: list[HistoryEvaluation],
    history_start: datetime,
    history_end: datetime,
    computed_at: datetime,
    provenance_id: str | None = None,
) -> Likelihood:
    """Build likelihood and its audit evidence from one canonical set of trials."""

    acquisition_successes, acquisition_failures = acquisition_trial_counts(
        history_datatakes,
        history_start=history_start,
        history_end=history_end,
        timezone=timezone_name,
    )
    clear_successes, clear_failures, excluded = clear_trial_counts(history_evaluations)
    seasonal_count = len(
        seasonal_datatakes(history_datatakes, as_of=history_end, timezone=timezone_name)
    )
    excluded += max(0, seasonal_count - len(history_evaluations))

    future = [item for item in opportunities if item.closest_time >= history_end]
    timezone = ZoneInfo(timezone_name)
    future_counts = {
        days: (
            len(
                {
                    item.closest_time.astimezone(timezone).date()
                    for item in future
                    if item.closest_time < history_end + timedelta(days=days)
                }
            ),
            sum(item.closest_time < history_end + timedelta(days=days) for item in future),
        )
        for days in (7, HORIZON_DAYS)
    }
    acquisition, clear, horizons, seed = estimate_likelihood(
        aoi_hash=geometry_sha256,
        as_of=history_end,
        future_counts=future_counts,
        acquisition_successes=acquisition_successes,
        acquisition_failures=acquisition_failures,
        clear_successes=clear_successes,
        clear_failures=clear_failures,
        excluded=excluded,
    )
    enough = acquisition.sample_size >= MINIMUM_TRIALS and clear.sample_size >= MINIMUM_TRIALS
    quality: Literal["seasonal", "insufficient-data"] = (
        "seasonal" if enough else "insufficient-data"
    )
    policy = surface_class_policy(surface_classes_for_preset(preset_slug))
    return Likelihood(
        aoi_id=aoi_id,
        as_of=history_end,
        computed_at=computed_at,
        window_start=history_end,
        window_end=history_end + timedelta(days=HORIZON_DAYS),
        history_start=history_start,
        history_end=history_end,
        interpretation=LIKELIHOOD_INTERPRETATION,
        usable_definition={
            "minimum_aoi_clear_percent": MINIMUM_CLEAR_PERCENT,
            "minimum_valid_coverage_percent": MINIMUM_VALID_COVERAGE_PERCENT,
            "unit": "past looks",
        },
        surface_class_policy=policy,
        season={"window_days": 45, "tier": quality, "timezone": timezone_name},
        acquisition_posterior=acquisition,
        clear_posterior=clear,
        horizons=horizons,
        monte_carlo={
            "draws": 100000,
            "rng": "numpy-pcg64",
            "seed": seed,
            "model_version": LIKELIHOOD_ALGORITHM,
        },
        quality=quality,
        trial_evidence=[
            TrialEvidence(
                opportunity_id=(f"repeat-cycle-{evaluation.platform}-{evaluation.relative_orbit}"),
                date=evaluation.acquisition_time.astimezone(timezone).date().isoformat(),
                usable=(
                    evaluation.valid_coverage_percent >= MINIMUM_VALID_COVERAGE_PERCENT
                    and evaluation.clear_percent is not None
                    and evaluation.clear_percent >= MINIMUM_CLEAR_PERCENT
                ),
                reason=(
                    "Archive acquisition evaluated from a full-AOI coarse SCL mosaic "
                    f"at overview {evaluation.overview_factor}."
                ),
                scene_id=evaluation.datatake_id,
                clear_percent=evaluation.clear_percent,
            )
            for evaluation in history_evaluations
        ],
        excluded_evidence=[
            ExcludedEvidence(
                opportunity_id=f"archive-history-{index + 1}",
                reason="Historical acquisition has no AOI SCL evaluation.",
            )
            for index in range(excluded)
        ],
        provenance_id=provenance_id
        or stable_id("prv", aoi_id, history_end.isoformat(), LIKELIHOOD_ALGORITHM),
    )
