"""Job-stage progress weights."""

from __future__ import annotations

from ncl_engine.domain.models import JobStage

FULL_ANALYSIS_WEIGHTS: dict[JobStage, float] = {
    JobStage.CATALOGUE: 0.05,
    JobStage.ORBIT: 0.25,
    JobStage.ARCHIVE: 0.10,
    JobStage.RASTER: 0.45,
    JobStage.LIKELIHOOD: 0.10,
    JobStage.FINALISE: 0.05,
}


def overall_progress(stage: JobStage, stage_progress: float) -> float:
    completed = 0.0
    for candidate, weight in FULL_ANALYSIS_WEIGHTS.items():
        if candidate is stage:
            return min(0.999, completed + weight * max(0.0, min(1.0, stage_progress)))
        completed += weight
    return min(0.999, completed)
