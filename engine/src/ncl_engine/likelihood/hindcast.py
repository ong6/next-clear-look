"""Deterministic one-to-one matching of predicted opportunities to archive acquisitions."""

from __future__ import annotations

from datetime import timedelta

from ncl_engine.domain.models import Opportunity, SceneSummary


def match_opportunities_to_scenes(
    opportunities: list[Opportunity],
    scenes: list[SceneSummary],
    *,
    tolerance: timedelta = timedelta(minutes=15),
) -> dict[str, str]:
    candidates: list[tuple[float, str, str]] = []
    for opportunity in opportunities:
        for scene in scenes:
            if opportunity.platform != scene.platform:
                continue
            difference = abs((opportunity.closest_time - scene.acquisition_time).total_seconds())
            if difference <= tolerance.total_seconds():
                candidates.append((difference, opportunity.id, scene.id))
    used_opportunities: set[str] = set()
    used_scenes: set[str] = set()
    matches: dict[str, str] = {}
    for _, opportunity_id, scene_id in sorted(candidates):
        if opportunity_id in used_opportunities or scene_id in used_scenes:
            continue
        matches[opportunity_id] = scene_id
        used_opportunities.add(opportunity_id)
        used_scenes.add(scene_id)
    return matches
