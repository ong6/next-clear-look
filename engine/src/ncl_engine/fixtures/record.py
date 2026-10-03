"""Orchestrate the engine pipeline while recording its real source requests."""

from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import json
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from ncl_engine.sources.transport import (
    AllowlistedHttpTransport,
    CacheTransport,
    LoopbackCogAdapter,
    PoliteTransport,
    RecordingTransport,
)
from ncl_engine.sources.transport.blobs import put_blob
from ncl_engine.sources.transport.models import canonical_json

from .check import check_repository

PipelineResult = Mapping[str, Any]
PipelineCallable = Callable[..., PipelineResult | Awaitable[PipelineResult]]


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("CLOCK must include a UTC offset")
    instant = parsed.astimezone(UTC)
    if instant > datetime.now(UTC):
        raise ValueError("CLOCK cannot be in the future")
    return instant


def _parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("pipeline timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _load_pipeline() -> PipelineCallable:
    target = os.environ.get("NCL_FIXTURE_PIPELINE", "ncl_engine.pipeline:record_fixture_set")
    module_name, separator, attribute = target.partition(":")
    if not separator:
        raise RuntimeError("NCL_FIXTURE_PIPELINE must be module:function")
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"engine fixture pipeline {target!r} is unavailable") from exc
    if not callable(function):
        raise RuntimeError(f"engine fixture pipeline {target!r} is not callable")
    return cast(PipelineCallable, function)


def latest_valid_frozen_at(
    recording_at: datetime,
    omm_epochs: Sequence[datetime],
    opportunity_times: Sequence[datetime],
) -> datetime:
    """Return the latest valid replay instant or raise when none exists."""

    if not omm_epochs:
        raise ValueError("clock selection requires at least one OMM epoch")
    lower = max(
        recording_at - timedelta(hours=72),
        max(epoch.astimezone(UTC) - timedelta(hours=48) for epoch in omm_epochs),
    )
    upper = min(
        recording_at,
        min(epoch.astimezone(UTC) + timedelta(hours=48) for epoch in omm_epochs),
    )
    if lower > upper:
        raise ValueError("no search interval lies within 48 hours of every OMM epoch")
    ordered = sorted({instant.astimezone(UTC) for instant in opportunity_times})
    candidates: list[datetime] = []
    for opportunity in ordered:
        candidate = min(upper, opportunity - timedelta(hours=2))
        gap = opportunity - candidate
        if candidate < lower or not timedelta(hours=2) <= gap <= timedelta(hours=4):
            continue
        next_opportunity = next((instant for instant in ordered if instant > candidate), None)
        if next_opportunity == opportunity:
            candidates.append(candidate)
    if not candidates:
        raise ValueError(
            "no frozen_at exists in the prior 72 hours with the next Tuas opportunity "
            "2-4 hours later and every OMM epoch within 48 hours"
        )
    return max(candidates)


async def _select_frozen_at(
    recording_at: datetime,
    singapore_feature: Mapping[str, Any],
    recording: RecordingTransport,
    ephemeris: Path,
) -> datetime:
    """Find the latest legal replay instant without a second OMM download."""

    sources_module = importlib.import_module("ncl_engine.sources")
    orbit_module = importlib.import_module("ncl_engine.orbit")
    illumination_module = importlib.import_module("ncl_engine.orbit.illumination")
    geometry_module = importlib.import_module("ncl_engine.domain.geometry")
    sources = sources_module.LiveSourceAdapters(recording)
    records = await sources.load_omm(recording_at)
    if not records:
        raise ValueError("CelesTrak returned no records for clock selection")

    lower = recording_at - timedelta(hours=72)

    raw_geometry = singapore_feature.get("geometry")
    if not isinstance(raw_geometry, Mapping):
        raise ValueError("Singapore preset must contain a GeoJSON geometry")
    normalized = geometry_module.normalize_aoi(dict(raw_geometry))
    propagator = orbit_module.OrbitPropagator()
    propagator.install(records)
    predictor = orbit_module.PassPredictor(
        propagator, illumination_module.De421Illumination(propagator, ephemeris)
    )
    opportunities = []
    for record in records:
        opportunities.extend(
            predictor.predict(
                record,
                str(singapore_feature["id"]),
                normalized.geometry,
                lower,
                recording_at + timedelta(hours=4),
            )
        )
    return latest_valid_frozen_at(
        recording_at,
        [record.epoch for record in records],
        [item.closest_time for item in opportunities],
    )


def _materialize_derived(
    name: str,
    value: Any,
    blob_root: Path,
    default_lineage: list[str],
) -> dict[str, Any]:
    """Turn JSON values and pipeline base64 PNGs into content-addressed artifacts."""

    metadata = dict(value) if isinstance(value, Mapping) else {"value": value}
    encoded = metadata.pop("body_base64", metadata.pop("png_base64", None))
    if encoded is not None:
        if not isinstance(encoded, str):
            raise ValueError(f"derived artifact {name} base64 payload must be text")
        try:
            body = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError(f"derived artifact {name} has invalid base64") from exc
        media_type = str(metadata.pop("media_type", "image/png"))
    elif "body" in metadata:
        return metadata
    else:
        body = canonical_json(metadata.pop("value", value))
        metadata = {}
        media_type = "application/json"
    digest, relative = put_blob(blob_root, body)
    metadata["body"] = {
        "media_type": media_type,
        "path": relative.as_posix(),
        "sha256": digest,
        "size": len(body),
    }
    existing_lineage = metadata.get("source_body_sha256", [])
    if isinstance(existing_lineage, str):
        existing_lineage = [existing_lineage]
    metadata["source_body_sha256"] = list(dict.fromkeys([*existing_lineage, *default_lineage]))
    return metadata


def _history_provenance(
    payload: dict[str, Any],
    interaction_by_id: Mapping[str, Mapping[str, Any]],
    bundled_ids: set[str],
) -> dict[str, Any]:
    raw = payload.pop("history_provenance", None)
    if not isinstance(raw, Mapping) or raw.get("bytes_bundled") is not False:
        raise ValueError("engine result lacks unbundled history_provenance")
    raw_ids = raw.get("interaction_ids")
    if not isinstance(raw_ids, list) or not all(isinstance(value, str) for value in raw_ids):
        raise ValueError("history_provenance.interaction_ids must be a string array")
    interaction_ids = list(dict.fromkeys(raw_ids))
    if len(interaction_ids) != len(raw_ids):
        raise ValueError("history_provenance.interaction_ids must be unique")
    raw_unbundled_ids = raw.get("unbundled_interaction_ids")
    if not isinstance(raw_unbundled_ids, list) or not all(
        isinstance(value, str) for value in raw_unbundled_ids
    ):
        raise ValueError("history_provenance.unbundled_interaction_ids must be a string array")
    unbundled_ids = list(dict.fromkeys(raw_unbundled_ids))
    if len(unbundled_ids) != len(raw_unbundled_ids):
        raise ValueError("history_provenance.unbundled_interaction_ids must be unique")
    if not set(unbundled_ids) <= set(interaction_ids):
        raise ValueError("unbundled history interactions must be part of used history provenance")
    if bundled_ids.intersection(unbundled_ids):
        raise ValueError("historical COG ranges must not be bundled")
    for identifier in interaction_ids:
        try:
            interaction = interaction_by_id[identifier]
        except KeyError as exc:
            raise ValueError(
                f"history provenance references an unknown interaction: {identifier}"
            ) from exc
        request = interaction.get("request")
        if (
            interaction.get("source_id") != "sentinel-cogs"
            or not isinstance(request, Mapping)
            or not str(request.get("url", "")).lower().endswith("/scl.tif")
        ):
            raise ValueError(f"history provenance is not an SCL range: {identifier}")
    return {
        "bytes_bundled": False,
        "interaction_ids": interaction_ids,
        "unbundled_interaction_ids": unbundled_ids,
    }


async def _publish_result(
    fixtures: Path,
    fixture_set: dict[str, Any],
    result: Mapping[str, Any],
    interactions: list[dict[str, Any]],
    preset_slugs: Sequence[str],
    frozen_at: datetime,
) -> list[Path]:
    preset_results = result.get("presets")
    if not isinstance(preset_results, Mapping):
        raise ValueError("engine record_fixture_set result must contain a presets mapping")
    recorded_at = max(
        (item["response"]["retrieved_at"] for item in interactions),
        default=_iso(datetime.now(UTC)),
    )
    shared = [item for item in interactions if item["source_id"] == "celestrak"]
    if len(shared) != 1:
        raise ValueError(
            f"fixture recording must make exactly one CelesTrak request, got {len(shared)}"
        )
    fixture_set["interactions"] = shared
    celestrak_body = dict(shared[0]["response"]["body"])
    celestrak_body["media_type"] = "application/json"
    fixture_set["sources"]["celestrak"] = celestrak_body
    if "ephemeris_provenance" in result:
        provenance = result["ephemeris_provenance"]
        if not isinstance(provenance, Mapping):
            raise ValueError("ephemeris_provenance must be an object")
        if provenance.get("sha256") != fixture_set["sources"]["ephemeris"]["body"]["sha256"]:
            raise ValueError("engine used an ephemeris other than the pinned fixture blob")
        fixture_set["sources"]["ephemeris"]["provenance"] = result["ephemeris_provenance"]
    fixture_set["frozen_at"] = _iso(frozen_at)
    fixture_set["recorded_at"] = recorded_at

    interaction_by_id = {item["id"]: item for item in interactions}
    manifests: dict[Path, dict[str, Any]] = {}
    for slug in preset_slugs:
        raw = preset_results.get(slug)
        if not isinstance(raw, Mapping):
            raise ValueError(f"engine result lacks preset output for {slug}")
        payload = dict(raw)
        interaction_ids = payload.pop("interaction_ids", None)
        if interaction_ids is None:
            if len(preset_slugs) != 1:
                raise ValueError("multi-preset output must provide interaction_ids per preset")
            selected = [item for item in interactions if item["source_id"] != "celestrak"]
        else:
            try:
                selected = [interaction_by_id[str(identifier)] for identifier in interaction_ids]
            except KeyError as exc:
                raise ValueError(f"{slug} references an unknown interaction: {exc}") from exc
            selected = [item for item in selected if item["source_id"] != "celestrak"]
        bundled_ids = {str(item["id"]) for item in selected}
        history_provenance = _history_provenance(payload, interaction_by_id, bundled_ids)
        # Fixtures commit only SCL range bytes. True-colour COG ranges are replaced by
        # the deterministic AOI-clipped PNG returned by the pipeline.
        selected = [
            item
            for item in selected
            if item["source_id"] != "sentinel-cogs"
            or item["request"]["url"].lower().endswith("/scl.tif")
        ]
        lineage = [item["response"]["body"]["sha256"] for item in selected]
        derived_values = payload.pop("derived", payload.pop("outputs", None))
        if not isinstance(derived_values, Mapping):
            raise ValueError(f"engine result lacks derived outputs for {slug}")
        aoi_output = derived_values.get("aoi.json")
        expected_aoi = json.loads(
            (fixtures / "presets" / slug / "aoi.geojson").read_text(encoding="utf-8")
        )
        if not isinstance(aoi_output, Mapping) or aoi_output.get("aoi_id") != expected_aoi["id"]:
            raise ValueError(f"engine output uses the wrong AOI ID for {slug}")
        scenes = derived_values.get("scenes.json")
        if not isinstance(scenes, list) or len(scenes) > 6:
            raise ValueError(f"engine output for {slug} must contain at most six scenes")
        for scene in scenes:
            if not isinstance(scene, Mapping):
                raise ValueError(f"engine scene output for {slug} must be an object")
            thumbnail = scene.get("thumbnail", {})
            if (
                isinstance(thumbnail, Mapping)
                and max(int(thumbnail.get("width", 0)), int(thumbnail.get("height", 0))) > 640
            ):
                raise ValueError(f"engine thumbnail for {slug} exceeds 640 px")
        if slug == "singapore-coast":
            opportunities = derived_values.get("opportunities.json")
            if not isinstance(opportunities, list) or not opportunities:
                raise ValueError("Singapore recording needs a future opportunity")
            opportunity_times = sorted(
                _parse_instant(str(item["closest_time"]))
                for item in opportunities
                if isinstance(item, Mapping)
                and _parse_instant(str(item["closest_time"])) >= frozen_at
            )
            if not opportunity_times:
                raise ValueError("Singapore recording needs a future opportunity")
            hours = (opportunity_times[0] - frozen_at).total_seconds() / 3600
            # Pass refinement is recomputed by the pipeline with a different
            # search boundary, so tolerate sub-second numerical movement at the edge.
            tolerance_hours = 1.0 / 3600.0
            if not 2 - tolerance_hours <= hours <= 4 + tolerance_hours:
                raise ValueError(
                    "Singapore's next opportunity must be 2-4 hours after frozen_at, "
                    f"got {hours:.2f}"
                )
        derived = {
            str(name): _materialize_derived(
                str(name),
                value,
                fixtures / "blobs",
                [] if str(name).startswith("history/") else lineage,
            )
            for name, value in derived_values.items()
        }
        query_window = payload.pop("query_window", None)
        if not isinstance(query_window, Mapping):
            raise ValueError(f"engine result lacks query_window for {slug}")
        if str(query_window["end"]) > _iso(frozen_at):
            raise ValueError(f"engine STAC query window extends past frozen_at for {slug}")
        manifest = {
            "aoi": f"presets/{slug}/aoi.geojson",
            "attributions": list(payload.pop("attributions", [])),
            "budget": dict(payload.pop("budget", {})),
            "derived": derived,
            "fixture_set": "ncl-showcase",
            "frozen_at": _iso(frozen_at),
            "history_provenance": history_provenance,
            "interactions": selected,
            "preset_slug": slug,
            "query_window": dict(query_window),
            "recorded_at": recorded_at,
            "schema": "ncl-fixture-manifest/v1",
        }
        path = fixtures / "presets" / slug / "manifest.json"
        manifests[path] = manifest
        for entry in fixture_set["presets"]:
            if entry["slug"] == slug:
                entry["manifest"] = str(path.relative_to(fixtures))
                break

    fixture_set["status"] = (
        "ready"
        if all(entry["manifest"] is not None for entry in fixture_set["presets"])
        else "pending-recording"
    )
    existing_manifests = []
    selected_paths = set(manifests)
    for entry in fixture_set["presets"]:
        if entry["manifest"] is None:
            continue
        path = fixtures / entry["manifest"]
        if path not in selected_paths:
            existing_manifests.append(json.loads(path.read_text(encoding="utf-8")))
    documents = [fixture_set, *existing_manifests, *manifests.values()]
    blobs: dict[str, int] = {}

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            if {"sha256", "size", "path"} <= set(value):
                blobs[str(value["sha256"])] = int(value["size"])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for document in documents:
        collect(document)
    recorded_interactions = [
        *fixture_set["interactions"],
        *(
            item
            for manifest in [*existing_manifests, *manifests.values()]
            for item in manifest["interactions"]
        ),
    ]
    catalogue_digests = {
        item["response"]["body"]["sha256"]
        for item in recorded_interactions
        if item["source_id"] == "earth-search"
    }
    scl_digests = {
        item["response"]["body"]["sha256"]
        for item in recorded_interactions
        if item["source_id"] == "sentinel-cogs"
    }
    png_digests = {
        artifact["body"]["sha256"]
        for manifest in [*existing_manifests, *manifests.values()]
        for artifact in manifest["derived"].values()
        if artifact["body"].get("media_type") == "image/png"
    }
    examples_bytes = sum(
        path.stat().st_size
        for base in (
            fixtures.parent / "contracts" / "examples",
            fixtures.parent / "engine" / "tests" / "golden",
        )
        if base.exists()
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".json", ".sse"}
    )
    fixture_set["budget"]["unique_referenced_bytes"] = sum(blobs.values())
    fixture_set["budget"]["orbital_ephemeris_bytes"] = sum(
        blobs[digest]
        for digest in {
            fixture_set["sources"]["celestrak"]["sha256"],
            fixture_set["sources"]["ephemeris"]["body"]["sha256"],
        }
    )
    fixture_set["budget"]["catalogue_json_bytes"] = sum(
        blobs[digest] for digest in catalogue_digests
    )
    fixture_set["budget"]["raw_scl_range_bytes"] = sum(blobs[digest] for digest in scl_digests)
    fixture_set["budget"]["derived_png_bytes"] = sum(blobs[digest] for digest in png_digests)
    fixture_set["budget"]["examples_goldens_sse_bytes"] = examples_bytes
    paths = [*manifests, fixtures / "fixture-set.json"]
    originals = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        documents_to_write = [*manifests.items(), (fixtures / "fixture-set.json", fixture_set)]
        for path, document in documents_to_write:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode() + b"\n")
            os.replace(temporary, path)
        await asyncio.to_thread(check_repository, fixtures.parent, allow_orphans=True)
        # Drop recorded visual COG ranges and superseded bodies only after every
        # published document is valid. True-colour COG bytes are never committed.
        for path in (fixtures / "blobs" / "sha256").glob("*/*"):
            if path.is_file() and path.name not in blobs:
                path.unlink()
        await asyncio.to_thread(check_repository, fixtures.parent)
    except Exception:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    return paths


async def record_fixture_set(
    root: Path,
    preset_slugs: Sequence[str],
    recording_at: datetime,
    *,
    resume: bool = False,
    frozen_at: datetime | None = None,
) -> dict[str, Any]:
    """Invoke engine-owned computation; this module owns transport and publication."""

    if os.environ.get("NCL_ALLOW_RECORD") != "1":
        raise RuntimeError("recording requires NCL_ALLOW_RECORD=1")
    fixtures = root / "fixtures"
    fixture_set_path = fixtures / "fixture-set.json"
    fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
    known = {item["slug"]: item for item in fixture_set["presets"]}
    if list(preset_slugs) == ["all"]:
        preset_slugs = list(known)
    elif "all" in preset_slugs:
        raise ValueError("PRESET=all cannot be combined with another preset")
    unknown = sorted(set(preset_slugs) - set(known))
    if unknown:
        raise ValueError(f"unknown preset(s): {', '.join(unknown)}")
    aois = {
        slug: json.loads((fixtures / known[slug]["aoi"]).read_text(encoding="utf-8"))
        for slug in preset_slugs
    }
    singapore = json.loads((fixtures / known["singapore-coast"]["aoi"]).read_text(encoding="utf-8"))
    blob_root = fixtures / "blobs"
    existing_blobs = {path.resolve() for path in (blob_root / "sha256").glob("*/*")}
    try:
        # Normal recording observes live bytes; resume mode can reuse validated cached bytes.
        policy_cache = CacheTransport(
            AllowlistedHttpTransport(),
            root / ".local" / "source-cache",
            read_enabled=resume,
            refresh_stale=not resume,
        )
        live = PoliteTransport(policy_cache)
        recording = RecordingTransport(live, blob_root)
        ephemeris = fixtures / "blobs" / fixture_set["sources"]["ephemeris"]["body"]["path"]
        if frozen_at is None:
            frozen_at = await _select_frozen_at(recording_at, singapore, recording, ephemeris)
        elif frozen_at > recording_at:
            raise ValueError("frozen_at cannot be after the recording instant")
        elif recording_at - frozen_at > timedelta(hours=72):
            raise ValueError("frozen_at must be within 72 hours of the recording instant")
        pipeline = _load_pipeline()
        result_or_awaitable = pipeline(
            aois=aois,
            frozen_at=frozen_at,
            transport=recording,
            cog_adapter_factory=LoopbackCogAdapter,
            ephemeris=ephemeris,
        )
        result = (
            await result_or_awaitable
            if inspect.isawaitable(result_or_awaitable)
            else result_or_awaitable
        )
        interactions = list(recording.interactions)
        outputs = await _publish_result(
            fixtures, fixture_set, dict(result), interactions, preset_slugs, frozen_at
        )
    except Exception:
        for path in (blob_root / "sha256").glob("*/*"):
            if path.resolve() not in existing_blobs:
                path.unlink()
        raise
    return {
        "frozen_at": _iso(frozen_at),
        "outputs": [str(path) for path in outputs],
        "presets": list(preset_slugs),
        "requests": len(interactions),
    }


def run_record(
    root: Path,
    presets: Sequence[str],
    clock: str,
    *,
    resume: bool = False,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        record_fixture_set(
            root.resolve(),
            presets,
            parse_utc(clock),
            resume=resume,
            frozen_at=parse_utc(frozen_at) if frozen_at is not None else None,
        )
    )
