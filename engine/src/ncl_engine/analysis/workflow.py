"""Stage-oriented execution of an analysis job."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

from ncl_engine.domain.models import (
    AnalysisJobCreate,
    Aoi,
    JobResult,
    JobStage,
    JobType,
    Likelihood,
    Opportunity,
    Scene,
    SceneSummary,
)
from ncl_engine.domain.policies import ARCHIVE_DAYS, LIKELIHOOD_ALGORITHM
from ncl_engine.jobs import JobContext
from ncl_engine.jobs.stages import overall_progress
from ncl_engine.likelihood import HistoryEvaluation, seasonal_datatakes
from ncl_engine.orbit import OmmRecord, PassPredictor
from ncl_engine.orbit.illumination import De421Illumination
from ncl_engine.provenance.hashing import stable_id
from ncl_engine.provenance.lineage import derived_graph
from ncl_engine.raster import Datatake, RasterAnalyzer, group_datatakes, select_scene_cover
from ncl_engine.raster.scl import surface_classes_for_preset

from .products import build_likelihood

if TYPE_CHECKING:
    from ncl_engine.service import EngineService

MAX_CONCURRENT_RASTER_ANALYSES = 4
FORECAST_DAYS = 14


@dataclass(frozen=True, slots=True)
class OrbitStageOutput:
    now: datetime
    records: list[OmmRecord]
    predictor: PassPredictor
    predicted: list[Opportunity]
    window_start: datetime
    window_end: datetime


class AnalysisWorkflow:
    """Run one job as small, independently readable stages."""

    def __init__(self, service: EngineService) -> None:
        self.service = service

    async def run(self, context: JobContext, request: AnalysisJobCreate) -> JobResult:
        aoi = self._resolve_aoi(request)
        replay_result = self._prepare_replay(aoi, request)
        if replay_result is not None:
            return replay_result

        records = await self._catalogue_stage(context)
        orbit = await self._orbit_stage(context, request, aoi, records)
        if request.type is JobType.ORBIT_ONLY:
            return JobResult(
                opportunity_count=len(orbit.predicted),
                scene_count=None,
                likelihood_url=None,
            )

        horizon = await self._default_horizon(aoi, orbit)
        if self.service.mode == "replay" and aoi.origin == "user":
            return await self._unrecorded_replay(context, request, aoi, orbit, horizon)

        scene_pairs = await self._archive_stage(context, aoi, orbit.now)
        await self._raster_stage(context, aoi, scene_pairs)
        if request.type in {JobType.ARCHIVE_REFRESH, JobType.RASTER_SCENE}:
            return JobResult(
                opportunity_count=None,
                scene_count=len(scene_pairs),
                likelihood_url=None,
            )

        await self._likelihood_stage(context, aoi, orbit.now, horizon)
        return JobResult(
            opportunity_count=len(orbit.predicted),
            scene_count=len(scene_pairs),
            likelihood_url=f"/v1/aois/{aoi.id}/likelihood",
        )

    def _resolve_aoi(self, request: AnalysisJobCreate) -> Aoi:
        aoi_id = request.aoi_id
        if aoi_id is None and request.scene_id is not None:
            candidates = self.service.store.list_resources("aoi_scene")
            aoi_id = next(
                (
                    str(item.get("aoi_id"))
                    for item in candidates
                    if item.get("id") == request.scene_id
                ),
                None,
            )
        if aoi_id is None:
            raise ValueError("job has no AOI target")
        aoi = self.service.get_aoi(aoi_id)
        if aoi is None:
            raise ValueError(f"AOI {aoi_id} does not exist")
        return aoi

    def _prepare_replay(self, aoi: Aoi, request: AnalysisJobCreate) -> JobResult | None:
        if self.service.mode == "replay" and aoi.origin == "user":
            now = self.service.clock.now()
            self.service.store.put_resource(
                "archive_state",
                aoi.id,
                {
                    "archive_state": "not_recorded",
                    "window_start": (now - timedelta(days=ARCHIVE_DAYS)).isoformat(),
                    "window_end": now.isoformat(),
                },
                parent_id=aoi.id,
            )
        if self.service.mode == "replay" and aoi.origin == "preset" and not request.force_refresh:
            return JobResult(
                opportunity_count=len(
                    self.service.store.list_resources("opportunity", parent_id=aoi.id)
                ),
                scene_count=len(self.service.store.list_resources("aoi_scene", parent_id=aoi.id)),
                likelihood_url=f"/v1/aois/{aoi.id}/likelihood",
            )
        return None

    async def _catalogue_stage(self, context: JobContext) -> list[OmmRecord]:
        context.checkpoint()
        started = time.perf_counter()
        await context.stage_started(
            JobStage.CATALOGUE,
            total_units=None,
            message="Loading current Sentinel-2 orbital elements.",
        )
        records = await self.service.sources.load_omm(self.service.clock.now())
        self.service._install_records(records)
        await context.progress(
            JobStage.CATALOGUE,
            stage_progress=1.0,
            overall_progress=overall_progress(JobStage.CATALOGUE, 1.0),
            message="Catalogue inputs are ready.",
            completed_units=len(records),
            total_units=len(records),
        )
        await context.stage_completed(
            JobStage.CATALOGUE,
            duration_seconds=time.perf_counter() - started,
            completed_units=len(records),
            total_units=len(records),
        )
        return records

    async def _orbit_stage(
        self,
        context: JobContext,
        request: AnalysisJobCreate,
        aoi: Aoi,
        records: list[OmmRecord],
    ) -> OrbitStageOutput:
        context.checkpoint()
        started = time.perf_counter()
        await context.stage_started(
            JobStage.ORBIT,
            total_units=len(records),
            message="Predicting geometric opportunities and swaths.",
        )
        if self.service.ephemeris_path is None:
            raise ValueError("PINNED_EPHEMERIS_UNAVAILABLE")
        predictor = PassPredictor(
            self.service.propagator,
            De421Illumination(self.service.propagator, self.service.ephemeris_path),
        )
        now = self.service.clock.now()
        window_start = request.from_ or now
        window_end = request.to or now + timedelta(days=FORECAST_DAYS)
        self.service.store.delete_resources("opportunity", parent_id=aoi.id)
        predicted: list[Opportunity] = []
        for index, record in enumerate(records, 1):
            context.checkpoint()
            values = await asyncio.to_thread(
                predictor.predict,
                record,
                aoi.id,
                aoi.geometry,
                window_start,
                window_end,
            )
            for opportunity in values:
                self.service.store.put_resource(
                    "opportunity",
                    opportunity.id,
                    opportunity,
                    parent_id=aoi.id,
                    sort_key=opportunity.closest_time.isoformat(),
                )
                await context.result(
                    "opportunity",
                    f"/v1/aois/{aoi.id}/opportunities",
                    cast(dict[str, object], opportunity.model_dump(mode="json")),
                    opportunity.provenance_id,
                )
            predicted.extend(values)
            await context.progress(
                JobStage.ORBIT,
                stage_progress=index / len(records),
                overall_progress=overall_progress(JobStage.ORBIT, index / len(records)),
                message=f"Predicted {index} of {len(records)} satellite tracks.",
                completed_units=index,
                total_units=len(records),
            )
        await context.stage_completed(
            JobStage.ORBIT,
            duration_seconds=time.perf_counter() - started,
            completed_units=len(records),
            total_units=len(records),
        )
        self.service._mark_opportunity_window(aoi.id, window_start, window_end)
        return OrbitStageOutput(
            now=now,
            records=records,
            predictor=predictor,
            predicted=predicted,
            window_start=window_start,
            window_end=window_end,
        )

    async def _default_horizon(self, aoi: Aoi, orbit: OrbitStageOutput) -> list[Opportunity]:
        default_end = orbit.now + timedelta(days=FORECAST_DAYS)
        if orbit.window_start == orbit.now and orbit.window_end == default_end:
            return list(orbit.predicted)
        output: list[Opportunity] = []
        for record in orbit.records:
            output.extend(
                await asyncio.to_thread(
                    orbit.predictor.predict,
                    record,
                    aoi.id,
                    aoi.geometry,
                    orbit.now,
                    default_end,
                )
            )
        return output

    async def _unrecorded_replay(
        self,
        context: JobContext,
        request: AnalysisJobCreate,
        aoi: Aoi,
        orbit: OrbitStageOutput,
        horizon: list[Opportunity],
    ) -> JobResult:
        likelihood_url = None
        if request.type in {JobType.FULL_ANALYSIS, JobType.LIKELIHOOD_ONLY}:
            likelihood = self._build_likelihood(
                aoi,
                horizon,
                [],
                [],
                orbit.now - timedelta(days=3 * 365),
                orbit.now,
            )
            self.service.store.put_resource("likelihood", aoi.id, likelihood, parent_id=aoi.id)
            await context.result(
                "likelihood",
                f"/v1/aois/{aoi.id}/likelihood",
                cast(dict[str, object], likelihood.model_dump(mode="json")),
                likelihood.provenance_id,
            )
            likelihood_url = f"/v1/aois/{aoi.id}/likelihood"
        return JobResult(
            opportunity_count=len(orbit.predicted),
            scene_count=0,
            likelihood_url=likelihood_url,
        )

    async def _archive_stage(
        self, context: JobContext, aoi: Aoi, now: datetime
    ) -> list[tuple[Datatake, Scene]]:
        context.checkpoint()
        started = time.perf_counter()
        await context.stage_started(
            JobStage.ARCHIVE,
            total_units=None,
            message="Searching Earth Search without a tile-cloud filter.",
        )
        archive_start = now - timedelta(days=ARCHIVE_DAYS)
        items = await self.service.sources.search_scenes(aoi.geometry, archive_start, now)
        selected = select_scene_cover(aoi.geometry, items)[:6]
        self.service.store.put_resource(
            "archive_state",
            aoi.id,
            {
                "archive_state": "ready" if selected else "empty",
                "window_start": archive_start.isoformat(),
                "window_end": now.isoformat(),
            },
            parent_id=aoi.id,
        )
        scene_pairs: list[tuple[Datatake, Scene]] = []
        for datatake, coverage in selected:
            representative = datatake.items[0]
            provenance_id = stable_id("prv", datatake.id, aoi.geometry_sha256)
            summary_data = {
                "id": datatake.id,
                "collection": representative.collection,
                "platform": datatake.platform,
                "acquisition_time": datatake.acquisition_time,
                "tile": ",".join(datatake.tiles),
                "footprint": datatake.footprint,
                "stac_self_url": representative.stac_self_url,
                "analysis_state": "queued",
                "analysis_error": None,
                "aoi_coverage_percent": coverage * 100.0,
                "tile_cloud_cover_percent": (
                    representative.tile_cloud_cover_percent if len(datatake.items) == 1 else None
                ),
                "aoi_clear_percent": None,
                "valid_pixels": None,
                "thumbnail_status": "pending",
                "thumbnail_url": None,
                "statistics_url": None,
                "provenance_id": provenance_id,
            }
            scene = Scene.model_validate(
                {**summary_data, "assets": self.service._datatake_assets(datatake)}
            )
            summary = SceneSummary.model_validate(summary_data)
            self.service.store.put_resource(
                "scene", scene.id, scene, sort_key=scene.acquisition_time.isoformat()
            )
            self.service.store.put_resource(
                "aoi_scene",
                f"{aoi.id}|{scene.id}",
                summary,
                parent_id=aoi.id,
                sort_key=scene.acquisition_time.isoformat(),
            )
            await context.result(
                "scene",
                f"/v1/scenes/{scene.id}",
                cast(dict[str, object], summary.model_dump(mode="json")),
                summary.provenance_id,
            )
            scene_pairs.append((datatake, scene))
        await context.progress(
            JobStage.ARCHIVE,
            stage_progress=1.0,
            overall_progress=overall_progress(JobStage.ARCHIVE, 1.0),
            message=f"Selected {len(scene_pairs)} archive scenes.",
            completed_units=len(scene_pairs),
            total_units=len(scene_pairs),
        )
        await context.stage_completed(
            JobStage.ARCHIVE,
            duration_seconds=time.perf_counter() - started,
            completed_units=len(scene_pairs),
            total_units=len(scene_pairs),
        )
        return scene_pairs

    async def _raster_stage(
        self,
        context: JobContext,
        aoi: Aoi,
        scene_pairs: list[tuple[Datatake, Scene]],
    ) -> int:
        context.checkpoint()
        started = time.perf_counter()
        await context.stage_started(
            JobStage.RASTER,
            total_units=len(scene_pairs),
            message="Reading AOI windows from SCL and true-colour COGs.",
        )
        ready_scenes: list[SceneSummary] = []
        if self.service.transport is None:
            await context.warning(
                "RASTER_SOURCE_UNAVAILABLE", "No ranged-asset transport is configured."
            )
        else:
            analyzer = RasterAnalyzer(
                self.service.transport,
                thumbnail_long_edge=self.service.settings.thumbnail_long_edge,
            )
            raster_limit = asyncio.Semaphore(MAX_CONCURRENT_RASTER_ANALYSES)
            completed_scenes = 0

            async def analyze_recent(datatake: Datatake, scene: Scene) -> None:
                nonlocal completed_scenes
                async with raster_limit:
                    if context.token.requested:
                        return
                    ready = await self.service._analyze_recent_scene(
                        context, analyzer, aoi, datatake, scene
                    )
                if ready is not None:
                    ready_scenes.append(ready)
                completed_scenes += 1
                await context.progress(
                    JobStage.RASTER,
                    stage_progress=completed_scenes / max(1, len(scene_pairs)),
                    overall_progress=overall_progress(
                        JobStage.RASTER, completed_scenes / max(1, len(scene_pairs))
                    ),
                    message=f"Processed {completed_scenes} of {len(scene_pairs)} scenes.",
                    completed_units=completed_scenes,
                    total_units=len(scene_pairs),
                )

            async with asyncio.TaskGroup() as raster_tasks:
                for datatake, scene in scene_pairs:
                    raster_tasks.create_task(
                        analyze_recent(datatake, scene), name=f"ncl-recent-{scene.id}"
                    )
            context.checkpoint()
        await context.stage_completed(
            JobStage.RASTER,
            duration_seconds=time.perf_counter() - started,
            completed_units=len(ready_scenes),
            total_units=len(scene_pairs),
        )
        return len(ready_scenes)

    async def _likelihood_stage(
        self,
        context: JobContext,
        aoi: Aoi,
        now: datetime,
        horizon: list[Opportunity],
    ) -> Likelihood:
        context.checkpoint()
        started = time.perf_counter()
        await context.stage_started(
            JobStage.LIKELIHOOD,
            total_units=2,
            message="Estimating acquisition and AOI-clear posteriors.",
        )
        history_start = now - timedelta(days=3 * 365)
        history_items = await self.service.sources.search_scenes(aoi.geometry, history_start, now)
        history_datatakes = group_datatakes(history_items)
        seasonal_history = seasonal_datatakes(history_datatakes, as_of=now, timezone=aoi.timezone)
        ordered_evaluations: list[HistoryEvaluation | None] = [None] * len(seasonal_history)
        if self.service.transport is not None:
            history_analyzer = RasterAnalyzer(self.service.transport)
            surface_classes = surface_classes_for_preset(
                aoi.preset.slug if aoi.preset is not None else None
            )
            history_limit = asyncio.Semaphore(MAX_CONCURRENT_RASTER_ANALYSES)
            completed_history = 0

            async def evaluate_history(index: int, datatake: Datatake) -> None:
                nonlocal completed_history
                async with history_limit:
                    if context.token.requested:
                        return
                    try:
                        try:
                            history_result = await history_analyzer.analyze_scl(
                                datatake,
                                aoi.geometry,
                                coarse=True,
                                surface_classes=surface_classes,
                            )
                        except Exception:
                            history_result = await history_analyzer.analyze_scl(
                                datatake,
                                aoi.geometry,
                                coarse=True,
                                surface_classes=surface_classes,
                            )
                    except Exception:
                        await context.warning(
                            "HISTORY_RASTER_FAILED",
                            f"Seasonal SCL history failed for {datatake.id}.",
                            retryable=True,
                            details={"datatake_id": datatake.id},
                        )
                    else:
                        ordered_evaluations[index] = HistoryEvaluation(
                            datatake_id=datatake.id,
                            platform=datatake.platform,
                            relative_orbit=datatake.relative_orbit,
                            acquisition_time=datatake.acquisition_time,
                            clear_percent=history_result.counts.clear_percent,
                            valid_coverage_percent=(history_result.counts.valid_coverage_percent),
                            overview_factor=history_result.overview_factor,
                        )
                    completed_history += 1
                    await context.progress(
                        JobStage.LIKELIHOOD,
                        stage_progress=completed_history / max(1, len(seasonal_history)),
                        overall_progress=overall_progress(
                            JobStage.LIKELIHOOD,
                            completed_history / max(1, len(seasonal_history)),
                        ),
                        message=(
                            f"Evaluated {completed_history} of {len(seasonal_history)} "
                            "seasonal datatakes."
                        ),
                        completed_units=completed_history,
                        total_units=len(seasonal_history),
                    )

            async with asyncio.TaskGroup() as history_tasks:
                for index, datatake in enumerate(seasonal_history):
                    history_tasks.create_task(
                        evaluate_history(index, datatake),
                        name=f"ncl-history-{datatake.id}",
                    )
            context.checkpoint()
        history_evaluations = [
            evaluation for evaluation in ordered_evaluations if evaluation is not None
        ]
        likelihood = self._build_likelihood(
            aoi,
            horizon,
            history_datatakes,
            history_evaluations,
            history_start,
            now,
        )
        self.service.store.put_resource("likelihood", aoi.id, likelihood, parent_id=aoi.id)
        likelihood_graph = derived_graph(
            artifact_id=aoi.id,
            label="Historical clear-look likelihood",
            algorithm_version=LIKELIHOOD_ALGORITHM,
            created_at=self.service.clock.now(),
            inputs=[],
            available_offline=False,
        ).model_dump(mode="json", by_alias=True)
        likelihood_graph["id"] = likelihood.provenance_id
        for node in likelihood_graph["nodes"]:
            if node["kind"] == "algorithm":
                node["seasonal_history_overviews"] = [
                    {
                        "datatake_id": evaluation.datatake_id,
                        "overview_factor": evaluation.overview_factor,
                    }
                    for evaluation in history_evaluations
                ]
        self.service.store.put_resource("provenance", likelihood.provenance_id, likelihood_graph)
        await context.result(
            "likelihood",
            f"/v1/aois/{aoi.id}/likelihood",
            cast(dict[str, object], likelihood.model_dump(mode="json")),
            likelihood.provenance_id,
        )
        await context.progress(
            JobStage.LIKELIHOOD,
            stage_progress=1.0,
            overall_progress=overall_progress(JobStage.LIKELIHOOD, 1.0),
            message="Likelihood model complete.",
            completed_units=2,
            total_units=2,
        )
        await context.stage_completed(
            JobStage.LIKELIHOOD,
            duration_seconds=time.perf_counter() - started,
            completed_units=2,
            total_units=2,
        )
        return likelihood

    def _build_likelihood(
        self,
        aoi: Aoi,
        opportunities: list[Opportunity],
        history_datatakes: list[Datatake],
        history_evaluations: list[HistoryEvaluation],
        history_start: datetime,
        history_end: datetime,
    ) -> Likelihood:
        return build_likelihood(
            aoi_id=aoi.id,
            geometry_sha256=aoi.geometry_sha256,
            timezone_name=aoi.timezone,
            preset_slug=aoi.preset.slug if aoi.preset is not None else None,
            opportunities=opportunities,
            history_datatakes=history_datatakes,
            history_evaluations=history_evaluations,
            history_start=history_start,
            history_end=history_end,
            computed_at=self.service.clock.now(),
        )
