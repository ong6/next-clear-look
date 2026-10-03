"""Fixture recording through the same derivation code used by live analysis."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from ncl_engine.analysis import build_likelihood, build_raster_statistics
from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.domain.models import (
    Geometry,
    SceneAnalysisState,
    SceneSummary,
    ThumbnailStatus,
)
from ncl_engine.likelihood import HistoryEvaluation, seasonal_datatakes
from ncl_engine.orbit import OmmRecord, OrbitPropagator, PassPredictor
from ncl_engine.orbit.illumination import De421Illumination
from ncl_engine.provenance.hashing import JsonValue, canonical_json
from ncl_engine.raster import Datatake, RasterAnalyzer, group_datatakes, select_scene_cover
from ncl_engine.raster.scl import (
    CLEAR_CLASSES,
    surface_classes_for_preset,
)
from ncl_engine.sources import LiveSourceAdapters
from ncl_engine.sources.protocols import StacItem
from ncl_engine.sources.transport import (
    CanonicalRequest,
    DataTransport,
    FixtureTransport,
    LoopbackCogAdapter,
    RecordingTransport,
    SourceSnapshot,
)


class _TrackingTransport:
    """Record every consumed snapshot, including memoized recording hits."""

    def __init__(self, upstream: DataTransport) -> None:
        self.upstream = upstream
        self.snapshots: list[SourceSnapshot] = []

    async def request(self, request: CanonicalRequest) -> SourceSnapshot:
        snapshot = await self.upstream.request(request)
        self.snapshots.append(snapshot)
        return snapshot


def _artifact_json(fixtures: Path, artifact: Mapping[str, object]) -> object:
    body = artifact["body"]
    if not isinstance(body, Mapping):
        raise ValueError("derived artifact body reference is invalid")
    path = fixtures / "blobs" / str(body["path"])
    payload = path.read_bytes()
    if len(payload) != int(body["size"]):
        raise ValueError(f"derived artifact size mismatch: {path}")
    if hashlib.sha256(payload).hexdigest() != body["sha256"]:
        raise ValueError(f"derived artifact digest mismatch: {path}")
    return json.loads(payload)


async def verify_fixture_statistics(
    *,
    fixtures: Path,
    fixture_set: Mapping[str, object],
    manifests: list[Mapping[str, object]],
) -> bool:
    """Re-read recorded SCL ranges through rasterio and require identical statistics."""

    if fixture_set.get("fixture_set") != "ncl-showcase":
        raise ValueError("unsupported fixture set")
    transport = FixtureTransport.from_path(fixtures / "fixture-set.json")
    analyzer = RasterAnalyzer(transport)
    verified = 0
    for manifest in manifests:
        aoi_relative = manifest.get("aoi")
        derived = manifest.get("derived")
        if not isinstance(aoi_relative, str) or not isinstance(derived, Mapping):
            raise ValueError("fixture manifest lacks AOI or derived artifacts")
        feature = json.loads((fixtures / aoi_relative).read_text(encoding="utf-8"))
        geometry = _aoi(feature, str(manifest.get("preset_slug", "unknown")))[1]
        scenes_artifact = derived.get("scenes.json")
        if not isinstance(scenes_artifact, Mapping):
            continue
        scenes_value = _artifact_json(fixtures, scenes_artifact)
        if not isinstance(scenes_value, list):
            raise ValueError("recorded scenes.json must be an array")
        scenes_by_id = {
            str(scene["id"]): scene
            for scene in scenes_value
            if isinstance(scene, Mapping) and "id" in scene
        }
        for name, artifact in derived.items():
            if not str(name).startswith("statistics/") or not str(name).endswith(".json"):
                continue
            if not isinstance(artifact, Mapping):
                raise ValueError(f"invalid statistics artifact {name}")
            expected = _artifact_json(fixtures, artifact)
            if not isinstance(expected, Mapping):
                raise ValueError(f"statistics artifact {name} must contain an object")
            scene_id = str(expected["scene_id"])
            scene = scenes_by_id.get(scene_id)
            if not isinstance(scene, Mapping):
                raise ValueError(f"statistics artifact has no matching scene: {scene_id}")
            assets = scene.get("assets")
            if not isinstance(assets, Mapping):
                raise ValueError(f"recorded scene lacks assets: {scene_id}")
            raw_items = scene.get("datatake_items")
            item_values = raw_items if isinstance(raw_items, list) else [scene]
            items: list[StacItem] = []
            for raw_item in item_values:
                if not isinstance(raw_item, Mapping):
                    raise ValueError(f"recorded datatake item is invalid: {scene_id}")
                raw_assets = raw_item.get("assets", assets)
                if not isinstance(raw_assets, Mapping):
                    raise ValueError(f"recorded scene lacks item assets: {scene_id}")
                items.append(
                    StacItem(
                        id=str(raw_item.get("id", scene_id)),
                        collection=str(scene.get("collection", "sentinel-2-l2a")),
                        platform=str(scene["platform"]),
                        acquisition_time=datetime.fromisoformat(
                            str(
                                raw_item.get("acquisition_time", scene["acquisition_time"])
                            ).replace("Z", "+00:00")
                        ),
                        tile=str(raw_item.get("tile", scene["tile"])),
                        relative_orbit=(
                            int(scene["relative_orbit"])
                            if scene.get("relative_orbit") is not None
                            else None
                        ),
                        geometry=cast(Geometry, raw_item.get("footprint", scene["footprint"])),
                        stac_self_url=str(raw_item.get("stac_self_url", scene["stac_self_url"])),
                        assets={
                            "scl": str(raw_assets["scl"]),
                            "visual": str(raw_assets.get("visual", raw_assets["scl"])),
                        },
                        tile_cloud_cover_percent=None,
                        raw={},
                        snapshot=None,
                        datatake_id=scene_id,
                    )
                )
            raw_policy = expected.get("surface_class_policy")
            policy_classes = (
                cast(Mapping[str, object], raw_policy).get("surface_scl_classes")
                if isinstance(raw_policy, Mapping)
                else expected.get("clear_scl_classes", CLEAR_CLASSES)
            )
            if not isinstance(policy_classes, (list, tuple, set, frozenset)):
                raise ValueError(f"statistics surface policy is invalid: {scene_id}")
            actual = await analyzer.analyze_scl(
                items,
                geometry,
                surface_classes={int(value) for value in policy_classes},
            )
            expected_counts = expected["class_counts"]
            if not isinstance(expected_counts, Mapping):
                raise ValueError(f"statistics class counts are invalid: {scene_id}")
            recorded = tuple(
                int(str(cast(Mapping[str, object], expected_counts[str(value)])["pixels"]))
                for value in range(12)
            )
            if actual.counts.class_counts != recorded:
                raise ValueError(f"SCL class-count mismatch for {scene_id}")
            scalar_checks = {
                "inside_aoi_pixels": actual.counts.inside_aoi_pixels,
                "valid_pixels": actual.counts.valid_pixels,
                "clear_pixels": actual.counts.clear_pixels,
                "invalid_pixels": actual.counts.invalid_pixels,
                "overview_factor": actual.overview_factor,
            }
            for field, value in scalar_checks.items():
                if int(expected[field]) != value:
                    raise ValueError(f"SCL {field} mismatch for {scene_id}")
            expected_clear = expected.get("clear_percent")
            if expected_clear is None:
                if actual.counts.clear_percent is not None:
                    raise ValueError(f"SCL clear_percent mismatch for {scene_id}")
            elif (
                actual.counts.clear_percent is None
                or abs(float(expected_clear) - actual.counts.clear_percent) > 1e-9
            ):
                raise ValueError(f"SCL clear_percent mismatch for {scene_id}")
            verified += 1
    if verified == 0:
        raise ValueError("sentinel-cogs interactions exist but no SCL statistics were verified")
    return True


def _aoi(value: object, slug: str) -> tuple[str, Geometry]:
    if not isinstance(value, Mapping):
        raise ValueError("preset AOI must be a GeoJSON object")
    is_feature = value.get("type") == "Feature"
    candidate = value.get("geometry") if is_feature else value
    if not isinstance(candidate, Mapping):
        raise ValueError("GeoJSON Feature must contain a geometry")
    identifier = value.get("id") if is_feature else None
    if is_feature and (not isinstance(identifier, str) or not identifier.startswith("aoi_")):
        raise ValueError(f"preset {slug} GeoJSON Feature must preserve a valid aoi_ id")
    aoi_id = str(identifier) if identifier is not None else "aoi_" + slug.replace("-", "_")
    return aoi_id, {str(key): item for key, item in candidate.items()}


def _aoi_timezone(value: object) -> str:
    if not isinstance(value, Mapping):
        return "UTC"
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        return "UTC"
    return str(properties.get("timezone", "UTC"))


def _datatake_assets(datatake: Datatake) -> dict[str, str]:
    if len(datatake.items) == 1:
        return dict(datatake.items[0].assets)
    return {
        f"{asset}:{item.tile}": url for item in datatake.items for asset, url in item.assets.items()
    }


def _recorded_datatake_items(datatake: Datatake) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "acquisition_time": item.acquisition_time.isoformat(),
            "tile": item.tile,
            "footprint": item.geometry,
            "stac_self_url": item.stac_self_url,
            "assets": dict(item.assets),
        }
        for item in datatake.items
    ]


def _validate_frozen_omm(records: list[OmmRecord], frozen_at: datetime) -> None:
    for record in records:
        if abs((record.epoch - frozen_at).total_seconds()) > 48 * 60 * 60:
            raise ValueError(f"frozen_at is more than 48 hours from {record.platform} OMM epoch")


async def record_fixture_set(
    *,
    aois: dict[str, object],
    frozen_at: datetime,
    transport: RecordingTransport,
    cog_adapter_factory: Callable[[DataTransport], LoopbackCogAdapter],
    ephemeris: Path,
) -> Mapping[str, object]:
    """Return JSON-serializable derived artifacts for the platform recorder."""

    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        raise ValueError("frozen_at must be timezone-aware")
    frozen_at = frozen_at.astimezone(UTC)
    if not ephemeris.is_file():
        raise ValueError(f"pinned ephemeris excerpt does not exist: {ephemeris}")
    ephemeris_sha256 = hashlib.sha256(ephemeris.read_bytes()).hexdigest()
    sources = LiveSourceAdapters(transport)
    records = await sources.load_omm(frozen_at)
    _validate_frozen_omm(records, frozen_at)
    common_interaction_ids = [str(item["id"]) for item in transport.interactions]
    celestrak_interaction = next(
        item for item in transport.interactions if item["source_id"] == "celestrak"
    )
    celestrak_retrieved = datetime.fromisoformat(
        str(celestrak_interaction["response"]["retrieved_at"]).replace("Z", "+00:00")
    )
    propagator = OrbitPropagator()
    propagator.install(records)
    predictor = PassPredictor(propagator, De421Illumination(propagator, ephemeris))
    raster = RasterAnalyzer(
        transport,
        thumbnail_long_edge=640,
        cog_adapter_factory=cog_adapter_factory,
    )
    presets: dict[str, object] = {}
    for slug, raw_aoi in sorted(aois.items()):
        interaction_count_before = len(transport.interactions)
        aoi_id, geometry = _aoi(raw_aoi, slug)
        timezone_name = _aoi_timezone(raw_aoi)
        normalized = normalize_aoi(geometry)
        surface_classes = surface_classes_for_preset(slug)
        opportunities = []
        for record in records:
            opportunities.extend(
                predictor.predict(
                    record,
                    aoi_id,
                    normalized.geometry,
                    frozen_at,
                    frozen_at + timedelta(days=14),
                )
            )
        history_start = frozen_at - timedelta(days=3 * 365)
        items = await sources.search_scenes(normalized.geometry, history_start, frozen_at)
        datatakes = group_datatakes(items)
        recent_items = [
            item for item in items if item.acquisition_time >= frozen_at - timedelta(days=30)
        ]
        selected = select_scene_cover(normalized.geometry, recent_items)[:6]
        scenes: list[dict[str, object]] = []
        statistics_outputs: dict[str, object] = {}
        thumbnails: dict[str, object] = {}
        for datatake, coverage in selected:
            representative = datatake.items[0]
            analysis = await raster.analyze(
                datatake,
                normalized.geometry,
                surface_classes=surface_classes,
            )
            statistics = build_raster_statistics(
                scene_id=datatake.id,
                aoi_id=aoi_id,
                preset_slug=slug,
                counts=analysis.counts,
                source_resolution_m=analysis.source_resolution_m,
                overview_factor=analysis.overview_factor,
                computed_at=frozen_at,
                provenance_id=f"prv_stats_{hashlib.sha256(f'{aoi_id}|{datatake.id}'.encode()).hexdigest()[:16]}",
            )
            summary = SceneSummary(
                id=datatake.id,
                platform=datatake.platform,
                acquisition_time=datatake.acquisition_time,
                tile=",".join(datatake.tiles),
                footprint=datatake.footprint,
                stac_self_url=representative.stac_self_url,
                analysis_state=SceneAnalysisState.READY,
                analysis_error=None,
                aoi_coverage_percent=coverage * 100.0,
                tile_cloud_cover_percent=(
                    representative.tile_cloud_cover_percent if len(datatake.items) == 1 else None
                ),
                aoi_clear_percent=statistics.clear_percent,
                valid_pixels=statistics.valid_pixels,
                thumbnail_status=ThumbnailStatus.READY,
                thumbnail_url=f"/v1/scenes/{datatake.id}/thumbnails/{aoi_id}",
                statistics_url=f"/v1/scenes/{datatake.id}/statistics/{aoi_id}",
                provenance_id=(
                    f"prv_scene_{hashlib.sha256(datatake.id.encode()).hexdigest()[:16]}"
                ),
            )
            scenes.append(
                {
                    **summary.model_dump(mode="json"),
                    "assets": _datatake_assets(datatake),
                    "relative_orbit": datatake.relative_orbit,
                    "datatake_items": _recorded_datatake_items(datatake),
                }
            )
            statistics_outputs[f"statistics/{datatake.id}.json"] = statistics.model_dump(
                mode="json"
            )
            source_body_sha256 = (
                representative.snapshot.body_sha256
                if representative.snapshot is not None
                else hashlib.sha256(datatake.id.encode()).hexdigest()
            )
            thumbnails[f"thumbnails/{datatake.id}.png"] = {
                "png_base64": base64.b64encode(analysis.thumbnail_png).decode("ascii"),
                "media_type": "image/png",
                "source_body_sha256": source_body_sha256,
                "width": analysis.thumbnail_width,
                "height": analysis.thumbnail_height,
            }

        history_used_interaction_ids: set[str] = set()
        history_only_interaction_ids: set[str] = set()
        history_outputs: dict[str, object] = {}
        history_evaluations: list[HistoryEvaluation] = []
        seasonal_history = seasonal_datatakes(datatakes, as_of=frozen_at, timezone=timezone_name)
        for datatake in seasonal_history:
            range_start = len(transport.interactions)
            tracking = _TrackingTransport(transport)
            history_raster = RasterAnalyzer(
                tracking,
                thumbnail_long_edge=640,
                cog_adapter_factory=cog_adapter_factory,
            )
            history_analysis = await history_raster.analyze_scl(
                datatake,
                normalized.geometry,
                coarse=True,
                surface_classes=surface_classes,
            )
            range_interactions = transport.interactions[range_start:]
            history_only_interaction_ids.update(str(item["id"]) for item in range_interactions)
            history_used_interaction_ids.update(
                str(snapshot.interaction_id)
                for snapshot in tracking.snapshots
                if snapshot.interaction_id is not None
            )
            range_hashes = sorted(
                {
                    snapshot.body_sha256
                    for snapshot in tracking.snapshots
                    if snapshot.source_id.value == "sentinel-cogs"
                }
            )
            evaluation = HistoryEvaluation(
                datatake_id=datatake.id,
                platform=datatake.platform,
                relative_orbit=datatake.relative_orbit,
                acquisition_time=datatake.acquisition_time,
                clear_percent=history_analysis.counts.clear_percent,
                valid_coverage_percent=history_analysis.counts.valid_coverage_percent,
                overview_factor=history_analysis.overview_factor,
            )
            history_evaluations.append(evaluation)
            history_outputs[f"history/{datatake.id}.json"] = {
                "datatake_id": datatake.id,
                "acquisition_time": datatake.acquisition_time.isoformat(),
                "platform": datatake.platform,
                "relative_orbit": datatake.relative_orbit,
                "class_counts": list(history_analysis.counts.class_counts),
                "inside_aoi_pixels": history_analysis.counts.inside_aoi_pixels,
                "valid_pixels": history_analysis.counts.valid_pixels,
                "clear_pixels": history_analysis.counts.clear_pixels,
                "invalid_pixels": history_analysis.counts.invalid_pixels,
                "valid_coverage_percent": history_analysis.counts.valid_coverage_percent,
                "clear_percent": history_analysis.counts.clear_percent,
                "overview_factor": history_analysis.overview_factor,
                "source_range_sha256": range_hashes,
                "bytes_bundled": False,
            }
        likelihood = build_likelihood(
            aoi_id=aoi_id,
            geometry_sha256=normalized.geometry_sha256,
            timezone_name=timezone_name,
            preset_slug=slug,
            opportunities=opportunities,
            history_datatakes=datatakes,
            history_evaluations=history_evaluations,
            history_start=history_start,
            history_end=frozen_at,
            computed_at=frozen_at,
            provenance_id=f"prv_likelihood_{hashlib.sha256(f'{aoi_id}|{frozen_at.isoformat()}'.encode()).hexdigest()[:16]}",
        )
        derived: dict[str, object] = {
            "aoi.json": {
                "aoi_id": aoi_id,
                "geometry": normalized.geometry,
                "geometry_sha256": normalized.geometry_sha256,
                "area_km2": normalized.area_km2,
            },
            "opportunities.json": [item.model_dump(mode="json") for item in opportunities],
            "scenes.json": scenes,
            "likelihood.json": likelihood.model_dump(mode="json"),
            **statistics_outputs,
            **history_outputs,
            **thumbnails,
        }
        json_bytes = sum(
            len(canonical_json(cast(JsonValue, value)))
            for name, value in derived.items()
            if not name.endswith(".png")
        )
        png_bytes = sum(
            len(base64.b64decode(cast(dict[str, str], value)["png_base64"]))
            for name, value in derived.items()
            if name.endswith(".png")
        )
        new_interactions = transport.interactions[interaction_count_before:]
        bundled_interactions = [
            item for item in new_interactions if str(item["id"]) not in history_only_interaction_ids
        ]
        presets[slug] = {
            "query_window": {
                "start": history_start.isoformat().replace("+00:00", "Z"),
                "end": frozen_at.isoformat().replace("+00:00", "Z"),
            },
            "derived": derived,
            "interaction_ids": common_interaction_ids
            + [str(item["id"]) for item in bundled_interactions],
            "history_provenance": {
                "interaction_ids": sorted(history_used_interaction_ids),
                "unbundled_interaction_ids": sorted(history_only_interaction_ids),
                "bytes_bundled": False,
            },
            "attributions": [
                "Orbital elements: [CelesTrak](https://celestrak.org), "
                f"retrieved {celestrak_retrieved.date().isoformat()} UTC.",
                "Catalogue: [Earth Search by Element 84]"
                "(https://earth-search.aws.element84.com/v1).",
                f"Contains modified Copernicus Sentinel data {frozen_at.year}.",
                "Solar geometry: JPL DE421 ephemeris excerpt.",
            ],
            "budget": {
                "derived_json_bytes": json_bytes,
                "thumbnail_bytes": png_bytes,
                "derived_total_bytes": json_bytes + png_bytes,
                "scene_count": len(scenes),
            },
        }
    return cast(
        Mapping[str, object],
        {
            "fixture_set": "ncl-showcase",
            "frozen_at": frozen_at.isoformat().replace("+00:00", "Z"),
            "ephemeris_provenance": {
                "path": ephemeris.name,
                "sha256": ephemeris_sha256,
                "bytes_bundled": True,
            },
            "omm": [
                {
                    "platform": record.platform,
                    "norad_catalog_id": record.norad_catalog_id,
                    "epoch": record.epoch.isoformat().replace("+00:00", "Z"),
                    "sha256": record.sha256,
                }
                for record in records
            ],
            "presets": presets,
        },
    )
