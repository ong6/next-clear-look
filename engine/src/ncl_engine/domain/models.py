"""Pydantic models that implement the public OpenAPI contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Instant = Annotated[datetime, AwareDatetime]
Position = tuple[float, float]
Geometry = dict[str, object]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorObject(ContractModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(ContractModel):
    error: ErrorObject


class AoiPreset(ContractModel):
    slug: str
    locality: str
    story: str
    climate_tags: list[str]


class ReplayCoverage(ContractModel):
    opportunities: bool
    archive: bool
    likelihood: bool
    thumbnails: bool


class AoiCreate(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    geometry: Geometry
    timezone: str = Field(default="UTC", max_length=80)


class AoiPatch(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    geometry: Geometry | None = None
    timezone: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def at_least_one_value(self) -> Self:
        if self.name is None and self.geometry is None and self.timezone is None:
            raise ValueError("at least one field is required")
        return self


class Aoi(ContractModel):
    id: str
    name: str
    origin: Literal["preset", "user"]
    preset: AoiPreset | None
    geometry: Geometry
    centroid: dict[str, object]
    bbox: tuple[float, float, float, float]
    timezone: str
    area_km2: float
    geometry_sha256: str
    replay_coverage: ReplayCoverage
    created_at: Instant
    updated_at: Instant
    provenance_id: str


class PaginationMeta(ContractModel):
    count: int
    next_cursor: str | None
    as_of: Instant | None = None


class AoiPage(ContractModel):
    data: list[Aoi]
    meta: PaginationMeta


class Satellite(ContractModel):
    id: str
    name: str
    norad_catalog_id: int
    platform: Literal["sentinel-2a", "sentinel-2b", "sentinel-2c"]
    status: Literal["operational-observed", "catalogued", "stale", "retired"]
    omm_epoch: Instant
    omm_age_seconds: float
    provenance_id: str


class SatellitePage(ContractModel):
    data: list[Satellite]
    meta: PaginationMeta


class TrajectorySample(ContractModel):
    time: Instant
    latitude: float
    longitude: float
    altitude_m: float
    swath_left: Position
    swath_right: Position


class Trajectory(ContractModel):
    satellite_id: str
    frame: Literal["ITRS/WGS84 geodetic"] = "ITRS/WGS84 geodetic"
    sample_interval_seconds: int
    start_time: Instant
    end_time: Instant
    samples: list[TrajectorySample]
    algorithm_version: str = "sgp4-swath-v1"
    provenance_id: str


class Subpoint(ContractModel):
    latitude: float
    longitude: float
    altitude_m: float


class OpportunitySource(ContractModel):
    model_config = ConfigDict(extra="allow")
    omm_epoch: Instant
    omm_sha256: str
    propagation_model: Literal["SGP4"] = "SGP4"
    coarse_step_seconds: int = 20
    crossing_tolerance_seconds: float = 0.05


class Opportunity(ContractModel):
    id: str
    kind: Literal["geometric_opportunity"] = "geometric_opportunity"
    aoi_id: str
    satellite_id: str
    platform: str
    entry_time: Instant
    closest_time: Instant
    exit_time: Instant
    duration_seconds: float
    direction: Literal["descending", "ascending"]
    satellite_sunlit: bool
    aoi_sun_elevation_deg: float
    illumination: Literal["daylight", "low_sun"]
    element_age_seconds: float
    swath_width_km: float = 290.0
    swath_footprint: Geometry
    minimum_ground_track_distance_km: float
    closest_subpoint: Subpoint
    acquisition_status: Literal["unknown", "observed", "not_observed"] = "unknown"
    matched_scene_id: str | None = None
    truncated: bool = False
    caveat: str
    source: OpportunitySource
    provenance_id: str


class OpportunityPageMeta(PaginationMeta):
    as_of: Instant
    window_start: Instant
    window_end: Instant


class OpportunityPage(ContractModel):
    data: list[Opportunity]
    meta: OpportunityPageMeta


class SceneAnalysisState(StrEnum):
    QUEUED = "queued"
    READING = "reading"
    ANALYSING = "analysing"
    READY = "ready"
    FAILED = "failed"
    NOT_RECORDED = "not_recorded"


class ThumbnailStatus(StrEnum):
    READY = "ready"
    PENDING = "pending"
    NOT_BUNDLED = "not_bundled"
    FAILED = "failed"


class SceneSummary(ContractModel):
    id: str
    collection: Literal["sentinel-2-l2a"] = "sentinel-2-l2a"
    platform: str
    acquisition_time: Instant
    tile: str
    footprint: Geometry
    stac_self_url: str
    analysis_state: SceneAnalysisState
    analysis_error: ErrorObject | None
    aoi_coverage_percent: float | None
    tile_cloud_cover_percent: float | None
    aoi_clear_percent: float | None
    valid_pixels: int | None
    thumbnail_status: ThumbnailStatus
    thumbnail_url: str | None
    statistics_url: str | None
    provenance_id: str


class Scene(SceneSummary):
    assets: dict[str, str]


class ScenePageMeta(PaginationMeta):
    archive_state: Literal["searching", "ready", "empty", "not_recorded", "failed"]
    window_start: Instant
    window_end: Instant


class ScenePage(ContractModel):
    data: list[SceneSummary]
    meta: ScenePageMeta


class ClassCount(ContractModel):
    label: str
    pixels: int


class SurfaceClassPolicy(ContractModel):
    surface_scl_classes: list[int] = Field(min_length=1)
    snow_ice_counted_as_surface: bool

    @model_validator(mode="after")
    def snow_ice_flag_matches_classes(self) -> Self:
        if self.snow_ice_counted_as_surface != (11 in self.surface_scl_classes):
            raise ValueError("snow/ice flag must match the SCL 11 policy")
        return self


class RasterStatistics(ContractModel):
    scene_id: str
    aoi_id: str
    algorithm_version: str = "scl-aoi-v1"
    clear_percent: float | None
    valid_coverage_percent: float
    clear_pixels: int
    valid_pixels: int
    inside_aoi_pixels: int
    invalid_pixels: int
    clear_scl_classes: list[int]
    valid_scl_classes: list[int]
    surface_class_policy: SurfaceClassPolicy
    class_counts: dict[str, ClassCount]
    source_resolution_m: float
    overview_factor: int
    computed_at: Instant
    provenance_id: str


class ThumbnailMetadata(ContractModel):
    scene_id: str
    aoi_id: str
    url: str
    media_type: Literal["image/png"] = "image/png"
    width: int
    height: int
    byte_length: int
    sha256: str
    transparent_outside_aoi: bool = True
    provenance_id: str


class CredibleInterval(ContractModel):
    level: float = 0.9
    lower: float
    upper: float


class HorizonLikelihood(ContractModel):
    days: Literal[7, 14]
    opportunity_days: int
    opportunity_count: int
    probability: float | None
    credible_interval: CredibleInterval | None


class BetaPosterior(ContractModel):
    distribution: Literal["Beta"] = "Beta"
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    alpha: float
    beta: float
    sample_size: int
    success_count: int
    failure_count: int
    excluded_count: int


class TrialEvidence(ContractModel):
    opportunity_id: str
    date: str
    usable: bool
    reason: str
    scene_id: str | None = None
    clear_percent: float | None = None


class ExcludedEvidence(ContractModel):
    opportunity_id: str
    reason: str


class Likelihood(ContractModel):
    aoi_id: str
    as_of: Instant
    computed_at: Instant
    window_start: Instant
    window_end: Instant
    history_start: Instant
    history_end: Instant
    interpretation: str
    usable_definition: dict[str, object]
    surface_class_policy: SurfaceClassPolicy
    season: dict[str, object]
    acquisition_posterior: BetaPosterior
    clear_posterior: BetaPosterior
    horizons: list[HorizonLikelihood]
    monte_carlo: dict[str, object]
    quality: Literal[
        "seasonal", "all-season-fallback", "tile-fallback", "insufficient-data", "demo-only-sparse"
    ]
    trial_evidence: list[TrialEvidence]
    excluded_evidence: list[ExcludedEvidence]
    provenance_id: str


class ProvenanceNode(ContractModel):
    model_config = ConfigDict(extra="allow")
    id: str
    kind: Literal["raw_input", "derived", "request", "algorithm", "geometry"]
    label: str
    source_id: Literal["celestrak", "earth-search", "sentinel-cogs", "jpl-de421"] | None
    request_key_sha256: str | None
    fixture_interaction_id: str | None
    available_offline: bool
    origin: Literal["network", "cache", "fixture"] | None = None
    sha256: str | None = None
    source_url: str | None = None
    fetched_at: Instant | None = None
    algorithm_version: str | None = None


class ProvenanceEdge(ContractModel):
    from_: str = Field(alias="from")
    to: str
    relation: Literal["input_to", "generated_by", "describes", "derived_from"]


class ProvenanceGraph(ContractModel):
    id: str
    root_artifact_id: str
    created_at: Instant
    nodes: list[ProvenanceNode]
    edges: list[ProvenanceEdge]


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    FULL_ANALYSIS = "full_analysis"
    ORBIT_ONLY = "orbit_only"
    ARCHIVE_REFRESH = "archive_refresh"
    RASTER_SCENE = "raster_scene"
    LIKELIHOOD_ONLY = "likelihood_only"


class JobStage(StrEnum):
    CATALOGUE = "catalogue"
    ORBIT = "orbit"
    ARCHIVE = "archive"
    RASTER = "raster"
    LIKELIHOOD = "likelihood"
    FINALISE = "finalise"


class AnalysisJobCreate(ContractModel):
    type: JobType
    aoi_id: str | None = None
    scene_id: str | None = None
    from_: Instant | None = Field(default=None, alias="from")
    to: Instant | None = None
    force_refresh: bool = False

    @model_validator(mode="after")
    def target_present(self) -> Self:
        if self.aoi_id is None and self.scene_id is None:
            raise ValueError("aoi_id or scene_id is required")
        return self


class JobResult(ContractModel):
    model_config = ConfigDict(extra="allow")
    opportunity_count: int | None = None
    scene_count: int | None = None
    likelihood_url: str | None = None


class AnalysisJob(ContractModel):
    id: str
    type: JobType
    aoi_id: str | None
    scene_id: str | None
    state: JobState
    progress: float
    stage: JobStage
    created_at: Instant
    started_at: Instant | None
    finished_at: Instant | None
    cancel_requested_at: Instant | None
    result: JobResult | None
    error: ErrorObject | None
    events_url: str


class JobPage(ContractModel):
    data: list[AnalysisJob]
    meta: PaginationMeta


class UpstreamHealth(ContractModel):
    status: Literal["ok", "stale", "unavailable", "fixture", "disabled"]
    last_success_at: Instant | None
    reason: str | None


class Health(ContractModel):
    status: Literal["ok", "degraded", "unavailable"]
    version: str
    mode: Literal["live", "replay"]
    clock: Instant
    database: Literal["ok", "degraded", "unavailable"]
    cache: Literal["ok", "degraded", "unavailable"]
    upstreams: dict[str, UpstreamHealth]


class Mode(ContractModel):
    mode: Literal["live", "replay"]
    clock: Instant
    network_enabled: bool
    live_available: bool
    fixture_set: str | None
    fixture_recorded_at: Instant | None
    deterministic: bool


class ModeSwitchRequest(ContractModel):
    mode: Literal["live", "replay"]
    fixture_set: str | None = None


class Attribution(ContractModel):
    source: str
    display_text: str
    source_url: str
    terms_url: str


class AttributionList(ContractModel):
    data: list[Attribution]
