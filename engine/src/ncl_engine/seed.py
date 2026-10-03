"""Seed the deterministic Tuas replay projection from contract examples."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ncl_engine.domain.clock import Clock
from ncl_engine.domain.geometry import normalize_aoi
from ncl_engine.domain.models import (
    Aoi,
    AoiPreset,
    Likelihood,
    Opportunity,
    RasterStatistics,
    ReplayCoverage,
    Satellite,
    Scene,
    SceneSummary,
    ThumbnailMetadata,
    Trajectory,
)
from ncl_engine.provenance.hashing import stable_id
from ncl_engine.raster.scl import CLEAR_CLASSES, surface_class_policy
from ncl_engine.storage import SQLiteStore

TUAS_GEOMETRY: dict[str, object] = {
    "type": "Polygon",
    "coordinates": [
        [[103.62, 1.24], [103.77, 1.24], [103.77, 1.36], [103.62, 1.36], [103.62, 1.24]]
    ],
}


def _examples_root() -> Path:
    return Path(__file__).resolve().parents[3] / "contracts" / "examples"


def _example(name: str) -> dict[str, Any]:
    value = json.loads((_examples_root() / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"contract example {name} must be an object")
    return value


def _placeholder_png(width: int = 640, height: int = 512) -> bytes:
    image = Image.new("RGBA", (width, height), (5, 22, 31, 0))
    draw = ImageDraw.Draw(image)
    for y in range(32, height - 32):
        water = int(70 + 70 * y / height)
        draw.line((32, y, width - 32, y), fill=(12, 88, water + 70, 255))
    draw.polygon(
        [(32, 100), (350, 72), (430, 190), (608, 170), (608, 32), (32, 32)],
        fill=(71, 92, 76, 255),
    )
    draw.line((32, 100, 350, 72, 430, 190, 608, 170), fill=(127, 225, 220, 255), width=3)
    buffer = BytesIO()
    image.save(buffer, format="PNG", compress_level=9, optimize=False)
    return buffer.getvalue()


def _provenance(identifier: str, label: str, clock: datetime) -> dict[str, object]:
    node_id = stable_id("prvnode", identifier)
    return {
        "id": identifier,
        "root_artifact_id": label,
        "created_at": clock.isoformat(),
        "nodes": [
            {
                "id": node_id,
                "kind": "derived",
                "label": label,
                "source_id": None,
                "request_key_sha256": None,
                "fixture_interaction_id": "seed-contract-examples",
                "available_offline": True,
                "origin": "fixture",
            }
        ],
        "edges": [],
    }


def _fixture_blob(fixtures: Path, artifact: dict[str, Any]) -> bytes:
    body = artifact["body"]
    path = fixtures / "blobs" / str(body["path"])
    payload = path.read_bytes()
    if len(payload) != int(body["size"]):
        raise ValueError(f"fixture blob size mismatch: {path}")
    if hashlib.sha256(payload).hexdigest() != body["sha256"]:
        raise ValueError(f"fixture blob SHA-256 mismatch: {path}")
    return payload


def _blob_references(value: object) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"path", "sha256", "size"} <= value.keys():
            output.append(value)
        for child in value.values():
            output.extend(_blob_references(child))
    elif isinstance(value, list):
        for child in value:
            output.extend(_blob_references(child))
    return output


def _verify_fixture_integrity(fixtures: Path, fixture_set: dict[str, Any]) -> None:
    documents: list[dict[str, Any]] = [fixture_set]
    for preset in fixture_set["presets"]:
        if preset.get("manifest") is None:
            raise ValueError(f"ready fixture set lacks manifest for {preset['slug']}")
        documents.append(
            json.loads((fixtures / str(preset["manifest"])).read_text(encoding="utf-8"))
        )
    for document in documents:
        for reference in _blob_references(document):
            _fixture_blob(fixtures, {"body": reference})


def import_recorded_replay(
    store: SQLiteStore, clock: Clock, fixtures: Path, thumbnail_dir: Path
) -> bool:
    del clock
    fixture_set_path = fixtures / "fixture-set.json"
    if not fixture_set_path.is_file():
        return False
    fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
    if fixture_set.get("status") != "ready":
        return False
    _verify_fixture_integrity(fixtures, fixture_set)
    frozen_at = datetime.fromisoformat(str(fixture_set["frozen_at"]).replace("Z", "+00:00"))
    for preset_entry in fixture_set["presets"]:
        manifest_relative = preset_entry.get("manifest")
        if manifest_relative is None:
            return False
        manifest = json.loads((fixtures / manifest_relative).read_text(encoding="utf-8"))
        feature = json.loads((fixtures / manifest["aoi"]).read_text(encoding="utf-8"))
        normalized = normalize_aoi(feature["geometry"])
        properties = feature["properties"]
        derived = manifest["derived"]
        aoi = Aoi(
            id=str(feature["id"]),
            name=str(properties["name"]),
            origin="preset",
            preset=AoiPreset(
                slug=str(properties["slug"]),
                locality=str(properties["locality"]),
                story=str(properties["story"]),
                climate_tags=[str(item) for item in properties.get("climate_tags", [])],
            ),
            geometry=normalized.geometry,
            centroid=normalized.centroid,
            bbox=normalized.bbox,
            timezone=str(properties.get("timezone", "UTC")),
            area_km2=normalized.area_km2,
            geometry_sha256=normalized.geometry_sha256,
            replay_coverage=ReplayCoverage(
                opportunities="opportunities.json" in derived,
                archive="scenes.json" in derived,
                likelihood="likelihood.json" in derived,
                thumbnails=any(str(name).endswith(".png") for name in derived),
            ),
            created_at=frozen_at,
            updated_at=frozen_at,
            provenance_id=stable_id("prv", str(feature["id"])),
        )
        store.put_resource("aoi", aoi.id, aoi, sort_key=aoi.name.lower())

        if "opportunities.json" in derived:
            values = json.loads(_fixture_blob(fixtures, derived["opportunities.json"]))
            for raw in values:
                opportunity = Opportunity.model_validate(raw)
                store.put_resource(
                    "opportunity",
                    opportunity.id,
                    opportunity,
                    parent_id=aoi.id,
                    sort_key=opportunity.closest_time.isoformat(),
                )
        scenes: list[SceneSummary] = []
        if "scenes.json" in derived:
            values = json.loads(_fixture_blob(fixtures, derived["scenes.json"]))
            for raw in values:
                raw_scene = dict(raw)
                assets = raw_scene.pop("assets", None)
                raw_scene.pop("relative_orbit", None)
                raw_scene.pop("datatake_items", None)
                summary = SceneSummary.model_validate(raw_scene)
                scenes.append(summary)
                store.put_resource(
                    "aoi_scene",
                    f"{aoi.id}|{summary.id}",
                    summary,
                    parent_id=aoi.id,
                    sort_key=summary.acquisition_time.isoformat(),
                )
                if assets is not None:
                    scene = Scene.model_validate({**raw_scene, "assets": assets})
                    store.put_resource(
                        "scene", scene.id, scene, sort_key=scene.acquisition_time.isoformat()
                    )
        for name, artifact in derived.items():
            if str(name).startswith("statistics/") and str(name).endswith(".json"):
                raw_statistics = json.loads(_fixture_blob(fixtures, artifact))
                if "surface_class_policy" not in raw_statistics:
                    raw_statistics["surface_class_policy"] = surface_class_policy(
                        raw_statistics.get("clear_scl_classes", CLEAR_CLASSES)
                    ).model_dump(mode="json")
                statistics = RasterStatistics.model_validate(raw_statistics)
                store.put_resource(
                    "statistics",
                    f"{aoi.id}|{statistics.scene_id}",
                    statistics,
                    parent_id=aoi.id,
                    sort_key=statistics.computed_at.isoformat(),
                )
            if str(name).startswith("thumbnails/") and str(name).endswith(".png"):
                scene_id = Path(str(name)).stem
                png = _fixture_blob(fixtures, artifact)
                thumbnail_dir.mkdir(parents=True, exist_ok=True)
                destination = thumbnail_dir / f"{scene_id}--{aoi.id}.png"
                destination.write_bytes(png)
                metadata = ThumbnailMetadata(
                    scene_id=scene_id,
                    aoi_id=aoi.id,
                    url=f"/v1/scenes/{scene_id}/thumbnails/{aoi.id}",
                    width=int(artifact.get("width", 640)),
                    height=int(artifact.get("height", 640)),
                    byte_length=len(png),
                    sha256=hashlib.sha256(png).hexdigest(),
                    provenance_id=stable_id("prv", scene_id, aoi.id, "thumbnail"),
                )
                store.put_resource("thumbnail", f"{aoi.id}|{scene_id}", metadata, parent_id=aoi.id)
                store.put_resource(
                    "thumbnail_path",
                    f"{aoi.id}|{scene_id}",
                    {"path": str(destination)},
                    parent_id=aoi.id,
                )
        if "likelihood.json" in derived:
            raw_likelihood = json.loads(_fixture_blob(fixtures, derived["likelihood.json"]))
            raw_likelihood.setdefault(
                "surface_class_policy",
                surface_class_policy(CLEAR_CLASSES).model_dump(mode="json"),
            )
            likelihood_start = datetime.fromisoformat(
                str(raw_likelihood["as_of"]).replace("Z", "+00:00")
            )
            raw_likelihood.setdefault("window_start", likelihood_start.isoformat())
            raw_likelihood.setdefault(
                "window_end", (likelihood_start + timedelta(days=14)).isoformat()
            )
            likelihood = Likelihood.model_validate(raw_likelihood)
            store.put_resource("likelihood", aoi.id, likelihood, parent_id=aoi.id)
        store.put_resource(
            "archive_state",
            aoi.id,
            {
                "archive_state": "ready" if scenes else "empty",
                "window_start": manifest["query_window"]["start"],
                "window_end": manifest["query_window"]["end"],
            },
            parent_id=aoi.id,
        )
    for kind, label in (
        ("aoi", "Preset AOI"),
        ("opportunity", "Geometric opportunity"),
        ("aoi_scene", "Archive scene"),
        ("statistics", "AOI SCL statistics"),
        ("thumbnail", "AOI thumbnail"),
        ("likelihood", "Historical likelihood"),
    ):
        for resource in store.list_resources(kind):
            provenance_id = resource.get("provenance_id")
            if isinstance(provenance_id, str):
                store.put_resource(
                    "provenance",
                    provenance_id,
                    _provenance(provenance_id, f"{label} {resource.get('id', '')}", frozen_at),
                )
    store.set_metadata("fixture_recorded_at", str(fixture_set["recorded_at"]))
    return True


def seed_replay(
    store: SQLiteStore,
    clock: Clock,
    thumbnail_dir: Path,
    fixtures: Path | None = None,
) -> None:
    now = clock.now()
    if fixtures is not None and import_recorded_replay(store, clock, fixtures, thumbnail_dir):
        return
    if store.get_resource("aoi", "aoi_sg_tuas_coast") is None:
        normalized = normalize_aoi(TUAS_GEOMETRY)
        aoi = Aoi(
            id="aoi_sg_tuas_coast",
            name="Tuas reclamation edge",
            origin="preset",
            preset=AoiPreset(
                slug="singapore-coast",
                locality="Tuas, Singapore",
                story="Monitor the changing reclamation edge and near-shore water.",
                climate_tags=["equatorial", "coastal", "convective-cloud"],
            ),
            geometry=normalized.geometry,
            centroid=normalized.centroid,
            bbox=normalized.bbox,
            timezone="Asia/Singapore",
            area_km2=normalized.area_km2,
            geometry_sha256=normalized.geometry_sha256,
            replay_coverage=ReplayCoverage(
                opportunities=True, archive=True, likelihood=True, thumbnails=True
            ),
            created_at=now,
            updated_at=now,
            provenance_id="prv_aoi_sg_tuas_coast",
        )
        store.put_resource("aoi", aoi.id, aoi, sort_key=aoi.name.lower())

    for raw in _example("satellites.json")["data"]:
        satellite = Satellite.model_validate(raw)
        store.put_resource("satellite", satellite.id, satellite, sort_key=satellite.id)

    trajectory = Trajectory.model_validate(_example("trajectory.json"))
    store.put_resource(
        "trajectory",
        stable_id("trajectory", trajectory.satellite_id, trajectory.start_time.isoformat()),
        trajectory,
        parent_id=trajectory.satellite_id,
        sort_key=trajectory.start_time.isoformat(),
    )

    for raw in _example("opportunities.json")["data"]:
        opportunity = Opportunity.model_validate(raw)
        store.put_resource(
            "opportunity",
            opportunity.id,
            opportunity,
            parent_id=opportunity.aoi_id,
            sort_key=opportunity.closest_time.isoformat(),
        )

    scene = Scene.model_validate(_example("scene.json"))
    store.put_resource("scene", scene.id, scene, sort_key=scene.acquisition_time.isoformat())
    summary = SceneSummary.model_validate(scene.model_dump(exclude={"assets"}))
    store.put_resource(
        "aoi_scene",
        f"aoi_sg_tuas_coast|{scene.id}",
        summary,
        parent_id="aoi_sg_tuas_coast",
        sort_key=scene.acquisition_time.isoformat(),
    )
    stats = _example("scene-statistics.json")
    store.put_resource(
        "statistics",
        f"aoi_sg_tuas_coast|{scene.id}",
        stats,
        parent_id="aoi_sg_tuas_coast",
        sort_key=scene.acquisition_time.isoformat(),
    )
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    png = _placeholder_png()
    png_path = thumbnail_dir / f"{scene.id}--aoi_sg_tuas_coast.png"
    png_path.write_bytes(png)
    metadata = ThumbnailMetadata.model_validate(
        {
            **_example("thumbnail-metadata.json"),
            "byte_length": len(png),
            "sha256": hashlib.sha256(png).hexdigest(),
        }
    )
    store.put_resource(
        "thumbnail",
        f"aoi_sg_tuas_coast|{scene.id}",
        metadata,
        parent_id="aoi_sg_tuas_coast",
    )
    store.put_resource(
        "thumbnail_path",
        f"aoi_sg_tuas_coast|{scene.id}",
        {"path": str(png_path)},
        parent_id="aoi_sg_tuas_coast",
    )
    likelihood = Likelihood.model_validate(_example("likelihood.json"))
    store.put_resource("likelihood", likelihood.aoi_id, likelihood, parent_id=likelihood.aoi_id)
    store.put_resource(
        "archive_state",
        "aoi_sg_tuas_coast",
        {
            "archive_state": "ready",
            "window_start": "2026-09-03T00:00:00Z",
            "window_end": "2026-10-03T00:00:00Z",
        },
        parent_id="aoi_sg_tuas_coast",
    )

    resource_ids = {
        "prv_aoi_sg_tuas_coast": "Tuas AOI",
        trajectory.provenance_id: "Sentinel-2C compact trajectory",
        scene.provenance_id: "Sentinel-2C archive scene",
        str(stats["provenance_id"]): "AOI SCL statistics",
        metadata.provenance_id: "AOI-clipped thumbnail",
        likelihood.provenance_id: "Historical clear-look likelihood",
    }
    for raw in _example("opportunities.json")["data"]:
        resource_ids[str(raw["provenance_id"])] = "Geometric opportunity"
    for identifier, label in resource_ids.items():
        store.put_resource("provenance", identifier, _provenance(identifier, label, now))
