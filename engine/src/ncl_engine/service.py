"""Application service coordinating sources, algorithms, persistence, and jobs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from ncl_engine.analysis import build_raster_statistics
from ncl_engine.analysis.workflow import AnalysisWorkflow
from ncl_engine.config import Settings
from ncl_engine.domain.clock import Clock
from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.domain.models import (
    AnalysisJobCreate,
    Aoi,
    AoiCreate,
    AoiPatch,
    Attribution,
    AttributionList,
    Health,
    JobResult,
    Likelihood,
    Mode,
    Opportunity,
    ProvenanceNode,
    RasterStatistics,
    ReplayCoverage,
    Satellite,
    Scene,
    SceneAnalysisState,
    ScenePage,
    ScenePageMeta,
    SceneSummary,
    ThumbnailMetadata,
    ThumbnailStatus,
    Trajectory,
    UpstreamHealth,
)
from ncl_engine.domain.policies import (
    ARCHIVE_DAYS,
    SCL_ALGORITHM,
)
from ncl_engine.jobs import JobContext
from ncl_engine.orbit import OmmRecord, OrbitPropagator, sample_trajectory
from ncl_engine.provenance.cache import put_bytes
from ncl_engine.provenance.hashing import JsonValue, canonical_json, sha256_bytes, stable_id
from ncl_engine.provenance.lineage import derived_graph, source_node
from ncl_engine.raster import Datatake, RasterAnalyzer
from ncl_engine.raster.scl import surface_classes_for_preset
from ncl_engine.seed import seed_replay
from ncl_engine.sources import SourceAdapters
from ncl_engine.sources.transport import DataTransport
from ncl_engine.storage import SQLiteStore


class EngineService:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        clock: Clock,
        sources: SourceAdapters,
        *,
        mode: Literal["live", "replay"],
        transport: DataTransport | None,
        ephemeris_path: Path | None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.clock = clock
        self.sources = sources
        self.mode = mode
        self.transport = transport
        self.propagator = OrbitPropagator()
        self.ephemeris_path = ephemeris_path
        self.omm_records: dict[str, OmmRecord] = {}
        self.fixture_recorded_at = clock.now() if mode == "replay" else None

    async def initialize(self) -> None:
        if self.mode == "replay":
            seed_replay(
                self.store,
                self.clock,
                self.settings.thumbnail_dir,
                self.settings.fixture_root,
            )
            recorded_at = self.store.get_metadata("fixture_recorded_at")
            if recorded_at is not None:
                self.fixture_recorded_at = datetime.fromisoformat(
                    recorded_at.replace("Z", "+00:00")
                )
            records = await self.sources.load_omm(self.clock.now())
            self._install_records(records)

    def _install_records(self, records: list[OmmRecord]) -> None:
        self.omm_records = {record.platform: record for record in records}
        self.propagator.install(records)
        now = self.clock.now()
        for record in records:
            satellite = Satellite(
                id=record.platform,
                name=record.name.title(),
                norad_catalog_id=record.norad_catalog_id,
                platform=cast(Any, record.platform),
                status="operational-observed"
                if (now - record.epoch) < timedelta(days=1)
                else "stale",
                omm_epoch=record.epoch,
                omm_age_seconds=(now - record.epoch).total_seconds(),
                provenance_id=stable_id("prv", record.platform, record.sha256),
            )
            self.store.put_resource("satellite", satellite.id, satellite, sort_key=satellite.id)
            graph = derived_graph(
                artifact_id=satellite.id,
                label=f"{satellite.name} catalogue state",
                algorithm_version="omm-catalogue-reconciliation-v1",
                created_at=self.clock.now(),
                inputs=[self._omm_provenance_node(record)],
                available_offline=self.mode == "replay",
            ).model_copy(update={"id": satellite.provenance_id})
            self.store.put_resource("provenance", satellite.provenance_id, graph)

    def _omm_provenance_node(self, record: OmmRecord) -> ProvenanceNode:
        return ProvenanceNode(
            id=stable_id("prvnode", record.platform, record.sha256),
            kind="raw_input",
            label=f"CelesTrak OMM for {record.name}",
            source_id="celestrak",
            request_key_sha256=None,
            fixture_interaction_id=None,
            available_offline=self.mode == "replay",
            origin="fixture" if self.mode == "replay" else "network",
            sha256=record.sha256,
            source_url=("https://celestrak.org/NORAD/elements/gp.php?NAME=SENTINEL-2&FORMAT=JSON"),
        )

    def mode_payload(self) -> Mode:
        return Mode(
            mode=self.mode,
            clock=self.clock.now(),
            network_enabled=self.mode == "live",
            live_available=self.settings.allow_live,
            fixture_set=self.settings.fixture_set if self.mode == "replay" else None,
            fixture_recorded_at=self.fixture_recorded_at,
            deterministic=self.mode == "replay",
        )

    def health(self) -> Health:
        status: Literal["fixture", "ok"] = "fixture" if self.mode == "replay" else "ok"
        last = self.fixture_recorded_at if self.mode == "replay" else self.clock.now()
        upstreams = {
            source: UpstreamHealth(status=status, last_success_at=last, reason=None)
            for source in ("celestrak", "earth-search", "sentinel-cogs", "jpl-de421")
        }
        database_ok = self.store.health()
        return Health(
            status="ok" if database_ok else "unavailable",
            version="1.0.0",
            mode=self.mode,
            clock=self.clock.now(),
            database="ok" if database_ok else "unavailable",
            cache="ok",
            upstreams=upstreams,
        )

    def attributions(self) -> AttributionList:
        recorded = self._recorded_attribution_text()
        year = self.clock.now().year
        celestrak_text = (
            recorded.get("celestrak")
            or "Orbital elements: [CelesTrak](https://celestrak.org), "
            f"retrieved {self.clock.now().date().isoformat()} UTC."
        )
        return AttributionList(
            data=[
                Attribution(
                    source="celestrak",
                    display_text=celestrak_text,
                    source_url="https://celestrak.org/",
                    terms_url="https://celestrak.org/NORAD/documentation/gp-data-formats.php",
                ),
                Attribution(
                    source="earth-search",
                    display_text=recorded.get("earth-search")
                    or "Catalogue: [Earth Search by Element 84]"
                    "(https://earth-search.aws.element84.com/v1).",
                    source_url="https://earth-search.aws.element84.com/v1",
                    terms_url="https://github.com/Element84/earth-search",
                ),
                Attribution(
                    source="sentinel-cogs",
                    display_text=recorded.get("sentinel-cogs")
                    or f"Contains modified Copernicus Sentinel data {year}.",
                    source_url="https://registry.opendata.aws/sentinel-2-l2a-cogs/",
                    terms_url="https://dataspace.copernicus.eu/terms-and-conditions",
                ),
                Attribution(
                    source="jpl-de421",
                    display_text="Solar geometry: JPL DE421 ephemeris excerpt.",
                    source_url="https://ssd.jpl.nasa.gov/planets/eph_export.html",
                    terms_url="https://www.jpl.nasa.gov/jpl-image-use-policy",
                ),
            ]
        )

    def _recorded_attribution_text(self) -> dict[str, str]:
        fixture_set_path = self.settings.fixture_root / "fixture-set.json"
        if self.mode != "replay" or not fixture_set_path.is_file():
            return {}
        fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
        values: list[str] = []
        for preset in fixture_set.get("presets", []):
            manifest = preset.get("manifest")
            if manifest is None:
                continue
            document = json.loads(
                (self.settings.fixture_root / str(manifest)).read_text(encoding="utf-8")
            )
            values.extend(str(item) for item in document.get("attributions", []))
        output: dict[str, str] = {}
        for value in values:
            if "CelesTrak" in value:
                output["celestrak"] = value
            elif "Earth Search" in value:
                output["earth-search"] = value
            elif "Copernicus" in value:
                output["sentinel-cogs"] = value
        return output

    def list_aois(self) -> list[Aoi]:
        return [Aoi.model_validate(raw) for raw in self.store.list_resources("aoi")]

    def get_aoi(self, aoi_id: str) -> Aoi | None:
        raw = self.store.get_resource("aoi", aoi_id)
        return None if raw is None else Aoi.model_validate(raw)

    def create_aoi(self, request: AoiCreate, idempotency_key: str | None) -> Aoi:
        normalized = normalize_aoi(request.geometry)
        identifier = stable_id("aoi", normalized.geometry_sha256, request.name)
        body_hash = sha256_bytes(canonical_json(cast(JsonValue, request.model_dump(mode="json"))))
        if idempotency_key:
            matches, existing_id = self.store.claim_idempotency(
                idempotency_key, body_hash, "aoi", identifier
            )
            if not matches:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            if existing_id:
                existing = self.get_aoi(existing_id)
                if existing is not None:
                    return existing
        now = self.clock.now()
        coverage = ReplayCoverage(
            opportunities=True,
            archive=self.mode == "live",
            likelihood=self.mode == "live",
            thumbnails=self.mode == "live",
        )
        aoi = Aoi(
            id=identifier,
            name=request.name,
            origin="user",
            preset=None,
            geometry=normalized.geometry,
            centroid=normalized.centroid,
            bbox=normalized.bbox,
            timezone=request.timezone,
            area_km2=normalized.area_km2,
            geometry_sha256=normalized.geometry_sha256,
            replay_coverage=coverage,
            created_at=now,
            updated_at=now,
            provenance_id=stable_id("prv", identifier),
        )
        self.store.put_resource("aoi", aoi.id, aoi, sort_key=aoi.name.lower())
        if self.mode == "replay":
            self.store.put_resource(
                "archive_state",
                aoi.id,
                {
                    "archive_state": "not_recorded",
                    "window_start": (now - timedelta(days=ARCHIVE_DAYS)).isoformat(),
                    "window_end": now.isoformat(),
                },
                parent_id=aoi.id,
            )
        return aoi

    def update_aoi(self, aoi_id: str, patch: AoiPatch) -> Aoi | None:
        current = self.get_aoi(aoi_id)
        if current is None:
            return None
        normalized = normalize_aoi(patch.geometry) if patch.geometry is not None else None
        updated = current.model_copy(
            update={
                "name": patch.name if patch.name is not None else current.name,
                "timezone": patch.timezone if patch.timezone is not None else current.timezone,
                "geometry": normalized.geometry if normalized else current.geometry,
                "centroid": normalized.centroid if normalized else current.centroid,
                "bbox": normalized.bbox if normalized else current.bbox,
                "area_km2": normalized.area_km2 if normalized else current.area_km2,
                "geometry_sha256": normalized.geometry_sha256
                if normalized
                else current.geometry_sha256,
                "updated_at": self.clock.now(),
            }
        )
        self.store.put_resource("aoi", updated.id, updated, sort_key=updated.name.lower())
        if normalized:
            self.store.delete_children(aoi_id)
        return updated

    def delete_aoi(self, aoi_id: str) -> bool:
        self.store.delete_children(aoi_id)
        return self.store.delete_resource("aoi", aoi_id)

    def list_satellites(self) -> list[Satellite]:
        return [Satellite.model_validate(raw) for raw in self.store.list_resources("satellite")]

    def get_satellite(self, satellite_id: str) -> Satellite | None:
        raw = self.store.get_resource("satellite", satellite_id)
        return None if raw is None else Satellite.model_validate(raw)

    def trajectory(self, satellite_id: str, start: Any, end: Any, step_seconds: int) -> Trajectory:
        if satellite_id not in self.omm_records:
            raise KeyError(satellite_id)
        identifier = stable_id(
            "trajectory",
            satellite_id,
            start.isoformat(),
            end.isoformat(),
            str(step_seconds),
        )
        cached = self.store.get_resource("trajectory", identifier)
        if cached is not None:
            return Trajectory.model_validate(cached)
        trajectory = sample_trajectory(
            self.propagator, satellite_id, start, end, step_seconds=step_seconds
        )
        self.store.put_resource(
            "trajectory",
            identifier,
            trajectory,
            parent_id=satellite_id,
            sort_key=start.isoformat(),
        )
        record = self.omm_records[satellite_id]
        graph = derived_graph(
            artifact_id=identifier,
            label=f"{satellite_id} compact trajectory",
            algorithm_version=trajectory.algorithm_version,
            created_at=self.clock.now(),
            inputs=[self._omm_provenance_node(record)],
            available_offline=self.mode == "replay",
        ).model_copy(update={"id": trajectory.provenance_id})
        self.store.put_resource("provenance", trajectory.provenance_id, graph)
        return trajectory

    def opportunities(
        self, aoi_id: str, start: Any, end: Any, satellite_id: str | None
    ) -> list[Opportunity]:
        values = [
            Opportunity.model_validate(raw)
            for raw in self.store.list_resources("opportunity", parent_id=aoi_id)
        ]
        return [
            item
            for item in values
            if start <= item.closest_time < end
            and (satellite_id is None or item.satellite_id == satellite_id)
        ]

    def opportunity_window_complete(
        self, aoi_id: str, start: datetime, end: datetime, satellite_id: str | None
    ) -> bool:
        aoi = self.get_aoi(aoi_id)
        if self.mode == "replay" and aoi is not None and aoi.origin == "preset":
            return True
        identifier = stable_id(
            "opp-window",
            aoi_id,
            start.isoformat(),
            end.isoformat(),
            satellite_id or "all",
        )
        return self.store.get_resource("opportunity_window", identifier) is not None

    def _mark_opportunity_window(
        self, aoi_id: str, start: datetime, end: datetime, satellite_id: str | None = None
    ) -> None:
        identifier = stable_id(
            "opp-window",
            aoi_id,
            start.isoformat(),
            end.isoformat(),
            satellite_id or "all",
        )
        self.store.put_resource(
            "opportunity_window",
            identifier,
            {
                "aoi_id": aoi_id,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "satellite_id": satellite_id,
            },
            parent_id=aoi_id,
        )

    def scenes(self, aoi_id: str, start: Any, end: Any) -> ScenePage | None:
        state = self.store.get_resource("archive_state", aoi_id)
        if state is None:
            return None
        values = [
            SceneSummary.model_validate(raw)
            for raw in self.store.list_resources("aoi_scene", parent_id=aoi_id, descending=True)
        ]
        filtered = [scene for scene in values if start <= scene.acquisition_time < end]
        return ScenePage(
            data=filtered,
            meta=ScenePageMeta(
                count=len(filtered),
                next_cursor=None,
                as_of=self.clock.now(),
                archive_state=cast(Any, state["archive_state"]),
                window_start=start,
                window_end=end,
            ),
        )

    def get_scene(self, scene_id: str) -> Scene | None:
        raw = self.store.get_resource("scene", scene_id)
        return None if raw is None else Scene.model_validate(raw)

    def get_statistics(self, scene_id: str, aoi_id: str) -> RasterStatistics | None:
        raw = self.store.get_resource("statistics", f"{aoi_id}|{scene_id}")
        return None if raw is None else RasterStatistics.model_validate(raw)

    def get_thumbnail_metadata(self, scene_id: str, aoi_id: str) -> ThumbnailMetadata | None:
        raw = self.store.get_resource("thumbnail", f"{aoi_id}|{scene_id}")
        return None if raw is None else ThumbnailMetadata.model_validate(raw)

    def get_thumbnail_path(self, scene_id: str, aoi_id: str) -> Path | None:
        raw = self.store.get_resource("thumbnail_path", f"{aoi_id}|{scene_id}")
        return None if raw is None else Path(str(raw["path"]))

    def get_likelihood(self, aoi_id: str) -> Likelihood | None:
        raw = self.store.get_resource("likelihood", aoi_id)
        return None if raw is None else Likelihood.model_validate(raw)

    def get_provenance(self, provenance_id: str) -> dict[str, Any] | None:
        return self.store.get_resource("provenance", provenance_id)

    @staticmethod
    def _datatake_assets(datatake: Datatake) -> dict[str, str]:
        if len(datatake.items) == 1:
            return dict(datatake.items[0].assets)
        return {
            f"{asset}:{item.tile}": url
            for item in datatake.items
            for asset, url in item.assets.items()
        }

    async def _analyze_recent_scene(
        self,
        context: JobContext,
        analyzer: RasterAnalyzer,
        aoi: Aoi,
        datatake: Datatake,
        scene: Scene,
    ) -> SceneSummary | None:
        surface_classes = surface_classes_for_preset(
            aoi.preset.slug if aoi.preset is not None else None
        )
        try:
            try:
                result = await analyzer.analyze(
                    datatake,
                    aoi.geometry,
                    surface_classes=surface_classes,
                )
            except Exception:
                await context.warning(
                    "RASTER_RETRY",
                    f"Retrying the idempotent raster read for {scene.id} once.",
                    retryable=True,
                    details={"scene_id": scene.id, "attempt": 2},
                )
                result = await analyzer.analyze(
                    datatake,
                    aoi.geometry,
                    surface_classes=surface_classes,
                )
            stats_id = f"{aoi.id}|{scene.id}"
            stats_provenance = stable_id("prv", stats_id, SCL_ALGORITHM)
            statistics = build_raster_statistics(
                scene_id=scene.id,
                aoi_id=aoi.id,
                preset_slug=aoi.preset.slug if aoi.preset is not None else None,
                counts=result.counts,
                source_resolution_m=result.source_resolution_m,
                overview_factor=result.overview_factor,
                computed_at=self.clock.now(),
                provenance_id=stats_provenance,
            )
            self.store.put_resource(
                "statistics",
                stats_id,
                statistics,
                parent_id=aoi.id,
                sort_key=scene.acquisition_time.isoformat(),
            )
            digest, blob_path = put_bytes(self.settings.thumbnail_dir, result.thumbnail_png)
            thumbnail_provenance = stable_id("prv", stats_id, digest)
            metadata = ThumbnailMetadata(
                scene_id=scene.id,
                aoi_id=aoi.id,
                url=f"/v1/scenes/{scene.id}/thumbnails/{aoi.id}",
                width=result.thumbnail_width,
                height=result.thumbnail_height,
                byte_length=len(result.thumbnail_png),
                sha256=digest,
                provenance_id=thumbnail_provenance,
            )
            self.store.put_resource("thumbnail", stats_id, metadata, parent_id=aoi.id)
            self.store.put_resource(
                "thumbnail_path", stats_id, {"path": str(blob_path)}, parent_id=aoi.id
            )
            ready = SceneSummary.model_validate(
                {
                    **scene.model_dump(mode="json", exclude={"assets"}),
                    "analysis_state": SceneAnalysisState.READY,
                    "aoi_clear_percent": statistics.clear_percent,
                    "valid_pixels": statistics.valid_pixels,
                    "thumbnail_status": ThumbnailStatus.READY,
                    "thumbnail_url": metadata.url,
                    "statistics_url": f"/v1/scenes/{scene.id}/statistics/{aoi.id}",
                }
            )
            self.store.put_resource(
                "aoi_scene",
                stats_id,
                ready,
                parent_id=aoi.id,
                sort_key=scene.acquisition_time.isoformat(),
            )
            snapshots = [item.snapshot for item in datatake.items if item.snapshot is not None]
            if snapshots:
                graph = derived_graph(
                    artifact_id=stats_id,
                    label="AOI SCL statistics",
                    algorithm_version=SCL_ALGORITHM,
                    created_at=self.clock.now(),
                    inputs=[
                        source_node(snapshot, "Earth Search catalogue response")
                        for snapshot in snapshots
                    ],
                    available_offline=False,
                )
                graph = graph.model_copy(update={"id": stats_provenance})
                self.store.put_resource("provenance", stats_provenance, graph)
            await context.result(
                "scene_statistics",
                f"/v1/scenes/{scene.id}/statistics/{aoi.id}",
                cast(dict[str, object], statistics.model_dump(mode="json")),
                statistics.provenance_id,
            )
            await context.result(
                "thumbnail_metadata",
                f"/v1/scenes/{scene.id}/thumbnails/{aoi.id}/metadata",
                cast(dict[str, object], metadata.model_dump(mode="json")),
                metadata.provenance_id,
            )
            return ready
        except Exception as exc:
            failed = SceneSummary.model_validate(
                {
                    **scene.model_dump(mode="json", exclude={"assets"}),
                    "analysis_state": SceneAnalysisState.FAILED,
                    "analysis_error": {
                        "code": "RASTER_FAILED",
                        "message": str(exc),
                        "retryable": True,
                        "details": {},
                        "request_id": stable_id("req", scene.id),
                    },
                    "thumbnail_status": ThumbnailStatus.FAILED,
                }
            )
            self.store.put_resource(
                "aoi_scene",
                f"{aoi.id}|{scene.id}",
                failed,
                parent_id=aoi.id,
                sort_key=scene.acquisition_time.isoformat(),
            )
            await context.warning(
                "RASTER_FAILED",
                f"Raster analysis failed for {scene.id}.",
                retryable=True,
                details={"scene_id": scene.id},
            )
            return None

    async def run_job(self, context: JobContext, request: AnalysisJobCreate) -> JobResult:
        return await AnalysisWorkflow(self).run(context, request)
