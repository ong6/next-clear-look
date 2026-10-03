"""Offline fixture schema, lineage, replay and byte-budget verification."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
from collections.abc import Awaitable, Iterable, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ncl_engine.sources.transport import CanonicalRequest, FixtureTransport, SourceId

FIXTURE_LIMIT = 40 * 1024 * 1024
ORBITAL_EPHEMERIS_LIMIT = 512 * 1024
CATALOGUE_LIMIT = 12 * 1024 * 1024
SCL_PRESET_LIMIT = 2 * 1024 * 1024
PNG_PRESET_LIMIT = 3 * 1024 * 1024
EXAMPLES_LIMIT = 3 * 1024 * 1024


class FixtureCheckError(RuntimeError):
    """One or more fixture invariants failed."""


async def _await_result(value: Awaitable[object]) -> object:
    return await value


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureCheckError(f"cannot read JSON {path}: {exc}") from exc


def _validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = _read_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages = [error.message for error in validator.iter_errors(instance)]
    if messages:
        raise FixtureCheckError(f"{label} schema failed: {'; '.join(sorted(messages))}")


def _walk_blob_refs(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        keys = set(value)
        if {"sha256", "size", "path"} <= keys:
            yield value
        for child in value.values():
            yield from _walk_blob_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_blob_refs(child)


def _validate_blob(fixtures: Path, reference: Mapping[str, Any]) -> tuple[str, int]:
    digest = str(reference["sha256"])
    size = int(reference["size"])
    expected_path = f"sha256/{digest[:2]}/{digest}"
    if reference["path"] != expected_path:
        raise FixtureCheckError(f"blob {digest} violates the content-addressed path layout")
    path = fixtures / "blobs" / expected_path
    try:
        body = path.read_bytes()
    except FileNotFoundError as exc:
        raise FixtureCheckError(f"missing blob {path}") from exc
    if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
        raise FixtureCheckError(f"blob integrity failed: {path}")
    return digest, size


def _validate_aoi(path: Path, slug: str) -> None:
    feature = _read_json(path)
    try:
        properties = feature["properties"]
        geometry = feature["geometry"]
        ring = geometry["coordinates"][0]
        bbox = feature["bbox"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FixtureCheckError(f"invalid GeoJSON feature: {path}") from exc
    if feature.get("type") != "Feature" or geometry.get("type") != "Polygon":
        raise FixtureCheckError(f"preset must be a GeoJSON Polygon Feature: {path}")
    if properties.get("slug") != slug:
        raise FixtureCheckError(f"preset slug mismatch in {path}")
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise FixtureCheckError(f"preset ring is not closed: {path}")
    xs = [float(point[0]) for point in ring]
    ys = [float(point[1]) for point in ring]
    computed_bbox = [min(xs), min(ys), max(xs), max(ys)]
    if computed_bbox != bbox:
        raise FixtureCheckError(f"preset bbox does not match its polygon: {path}")


def _request_from_interaction(fixtures: Path, interaction: Mapping[str, Any]) -> CanonicalRequest:
    request = interaction["request"]
    body = b""
    if "body" in request:
        _validate_blob(fixtures, request["body"])
        body = (fixtures / "blobs" / request["body"]["path"]).read_bytes()
    canonical = CanonicalRequest(
        source_id=SourceId(interaction["source_id"]),
        method=request["method"],
        url=request["url"],
        headers=request["headers"],
        body=body,
    )
    if canonical.body_sha256 != request["body_sha256"]:
        raise FixtureCheckError(f"request body digest mismatch: {interaction['id']}")
    if canonical.key() != request["request_key_sha256"]:
        raise FixtureCheckError(f"request identity mismatch: {interaction['id']}")
    return canonical


async def _check_replay(fixtures: Path, fixture_set: Mapping[str, Any]) -> None:
    transport = FixtureTransport.from_path(fixtures / "fixture-set.json")
    interactions = list(fixture_set.get("interactions", []))
    for preset in fixture_set["presets"]:
        if preset["manifest"] is not None:
            manifest = _read_json(fixtures / preset["manifest"])
            interactions.extend(manifest["interactions"])
    for interaction in interactions:
        request = _request_from_interaction(fixtures, interaction)
        first = await transport.request(request)
        second = await transport.request(request)
        if (
            first.status,
            dict(first.headers),
            first.body,
        ) != (second.status, dict(second.headers), second.body):
            raise FixtureCheckError(f"non-deterministic replay: {interaction['id']}")


def _validate_interaction(fixtures: Path, interaction: Mapping[str, Any]) -> None:
    if interaction.get("origin") not in {"network", "cache", "fixture"}:
        raise FixtureCheckError(f"interaction has invalid origin: {interaction.get('id')}")
    request = _request_from_interaction(fixtures, interaction)
    response = interaction["response"]
    _validate_blob(fixtures, response["body"])
    if "range" not in request.headers:
        return
    if response["status"] != 206:
        raise FixtureCheckError(f"range interaction is not HTTP 206: {interaction['id']}")
    start, end = request.headers["range"][6:].split("-", 1)
    content_range = response["headers"].get("content-range", "")
    if not content_range.startswith(f"bytes {start}-{end}/"):
        raise FixtureCheckError(f"range response does not cover its request: {interaction['id']}")
    if not response["headers"].get("etag"):
        raise FixtureCheckError(f"range response has no ETag: {interaction['id']}")


def _orphan_blobs(fixtures: Path, referenced: set[str]) -> list[str]:
    blob_root = fixtures / "blobs" / "sha256"
    if not blob_root.exists():
        return []
    return sorted(
        path.name
        for path in blob_root.glob("*/*")
        if path.is_file() and path.name not in referenced
    )


def _verify_scl_statistics(
    fixtures: Path, fixture_set: Mapping[str, Any], manifests: list[Mapping[str, Any]]
) -> None:
    has_scl = any(
        interaction["source_id"] == SourceId.SENTINEL_COGS.value
        for manifest in manifests
        for interaction in manifest["interactions"]
    )
    if not has_scl:
        return
    try:
        module = importlib.import_module("ncl_engine.pipeline")
        verifier = module.verify_fixture_statistics
    except (ImportError, AttributeError) as exc:
        raise FixtureCheckError(
            "recorded SCL ranges require ncl_engine.pipeline:verify_fixture_statistics"
        ) from exc
    result = verifier(fixtures=fixtures, fixture_set=fixture_set, manifests=manifests)
    if inspect.isawaitable(result):
        result = asyncio.run(_await_result(result))
    if result is False:
        raise FixtureCheckError("rasterio SCL re-derivation did not match recorded statistics")


def check_repository(root: Path, *, allow_orphans: bool = False) -> dict[str, Any]:
    """Validate every fixture that currently exists, including incomplete sets."""

    root = root.resolve()
    fixtures = root / "fixtures"
    schemas = fixtures / "schemas"
    fixture_set = _read_json(fixtures / "fixture-set.json")
    _validate_schema(fixture_set, schemas / "fixture-set-v1.schema.json", "fixture set")
    if fixture_set["status"] == "ready":
        if fixture_set["frozen_at"] is None or fixture_set["recorded_at"] is None:
            raise FixtureCheckError("a ready fixture set requires frozen_at and recorded_at")
        if fixture_set["sources"]["celestrak"] is None:
            raise FixtureCheckError("a ready fixture set requires the shared CelesTrak response")

    manifests: list[Mapping[str, Any]] = []
    for preset in fixture_set["presets"]:
        aoi_path = fixtures / preset["aoi"]
        _validate_aoi(aoi_path, preset["slug"])
        manifest_relative = preset["manifest"]
        if manifest_relative is None:
            if fixture_set["status"] == "ready":
                raise FixtureCheckError(f"ready fixture set lacks {preset['slug']} manifest")
            continue
        manifest = _read_json(fixtures / manifest_relative)
        _validate_schema(manifest, schemas / "manifest-v1.schema.json", preset["slug"])
        if manifest["preset_slug"] != preset["slug"]:
            raise FixtureCheckError(f"manifest slug mismatch for {preset['slug']}")
        if manifest["fixture_set"] != fixture_set["fixture_set"]:
            raise FixtureCheckError(f"fixture-set mismatch for {preset['slug']}")
        if manifest["query_window"]["end"] > manifest["frozen_at"]:
            raise FixtureCheckError(f"STAC range extends past frozen_at for {preset['slug']}")
        manifests.append(manifest)

    all_documents = [fixture_set, *manifests]
    all_interactions = list(fixture_set.get("interactions", []))
    all_interactions.extend(
        interaction for manifest in manifests for interaction in manifest["interactions"]
    )
    references: dict[str, int] = {}
    for document in all_documents:
        for reference in _walk_blob_refs(document):
            digest, size = _validate_blob(fixtures, reference)
            previous = references.setdefault(digest, size)
            if previous != size:
                raise FixtureCheckError(f"blob {digest} has inconsistent sizes")
    for interaction in fixture_set.get("interactions", []):
        _validate_interaction(fixtures, interaction)
    for manifest in manifests:
        history_provenance = manifest.get("history_provenance")
        if not isinstance(history_provenance, Mapping):
            raise FixtureCheckError(f"{manifest['preset_slug']} lacks history provenance")
        history_ids = history_provenance.get("interaction_ids")
        unbundled_history_ids = history_provenance.get("unbundled_interaction_ids")
        if (
            history_provenance.get("bytes_bundled") is not False
            or not isinstance(history_ids, list)
            or not isinstance(unbundled_history_ids, list)
        ):
            raise FixtureCheckError(
                f"{manifest['preset_slug']} history provenance must be unbundled"
            )
        if not set(str(value) for value in unbundled_history_ids) <= set(
            str(value) for value in history_ids
        ):
            raise FixtureCheckError(
                f"{manifest['preset_slug']} unbundled history provenance was not used"
            )
        bundled_ids = {str(item["id"]) for item in manifest["interactions"]}
        if bundled_ids.intersection(str(value) for value in unbundled_history_ids):
            raise FixtureCheckError(
                f"{manifest['preset_slug']} bundles a historical COG interaction"
            )
        for interaction in manifest["interactions"]:
            _validate_interaction(fixtures, interaction)
        source_digests = {
            interaction["response"]["body"]["sha256"] for interaction in manifest["interactions"]
        }
        for name, artifact in manifest["derived"].items():
            missing = set(artifact["source_body_sha256"]) - source_digests
            if missing:
                raise FixtureCheckError(f"derived artifact {name} has missing lineage: {missing}")
            if not str(name).startswith("history/"):
                continue
            if artifact["source_body_sha256"]:
                raise FixtureCheckError(
                    f"history artifact {name} falsely claims bundled range lineage"
                )
            history = _read_json(fixtures / "blobs" / artifact["body"]["path"])
            ranges = history.get("source_range_sha256") if isinstance(history, Mapping) else None
            if (
                not isinstance(ranges, list)
                or not ranges
                or not all(
                    isinstance(digest, str)
                    and len(digest) == 64
                    and set(digest) <= set("0123456789abcdef")
                    for digest in ranges
                )
                or history.get("bytes_bundled") is not False
            ):
                raise FixtureCheckError(f"history artifact {name} lacks unbundled range provenance")

    unique_bytes = sum(references.values())
    if unique_bytes >= FIXTURE_LIMIT:
        raise FixtureCheckError(f"fixture bytes {unique_bytes} must be below {FIXTURE_LIMIT}")
    declared = fixture_set["budget"]["unique_referenced_bytes"]
    if declared != unique_bytes:
        raise FixtureCheckError(f"declared fixture bytes {declared} do not equal {unique_bytes}")
    orbital_digests = {
        interaction["response"]["body"]["sha256"]
        for interaction in all_interactions
        if interaction["source_id"] == SourceId.CELESTRAK.value
    }
    ephemeris_digest = fixture_set["sources"]["ephemeris"]["body"]["sha256"]
    orbital_digests.add(ephemeris_digest)
    orbital_bytes = sum(references[digest] for digest in orbital_digests)
    if orbital_bytes > ORBITAL_EPHEMERIS_LIMIT:
        raise FixtureCheckError("shared orbital elements and ephemeris exceed 0.5 MiB")
    catalogue_digests = {
        interaction["response"]["body"]["sha256"]
        for interaction in all_interactions
        if interaction["source_id"] == SourceId.EARTH_SEARCH.value
    }
    catalogue_bytes = sum(references[digest] for digest in catalogue_digests)
    if catalogue_bytes > CATALOGUE_LIMIT:
        raise FixtureCheckError("catalogue JSON exceeds 12 MiB")
    scl_digests: set[str] = set()
    png_digests: set[str] = set()
    for manifest in manifests:
        raw_scl_bytes = sum(
            int(interaction["response"]["body"]["size"])
            for interaction in manifest["interactions"]
            if interaction["source_id"] == SourceId.SENTINEL_COGS.value
        )
        if raw_scl_bytes > SCL_PRESET_LIMIT:
            raise FixtureCheckError(f"{manifest['preset_slug']} SCL ranges exceed 2 MiB")
        scl_digests.update(
            interaction["response"]["body"]["sha256"]
            for interaction in manifest["interactions"]
            if interaction["source_id"] == SourceId.SENTINEL_COGS.value
        )
        png_bytes = sum(
            int(artifact["body"]["size"])
            for artifact in manifest["derived"].values()
            if artifact["body"].get("media_type") == "image/png"
        )
        if png_bytes > PNG_PRESET_LIMIT:
            raise FixtureCheckError(f"{manifest['preset_slug']} derived PNGs exceed 3 MiB")
        png_digests.update(
            artifact["body"]["sha256"]
            for artifact in manifest["derived"].values()
            if artifact["body"].get("media_type") == "image/png"
        )
    examples_bytes = sum(
        path.stat().st_size
        for base in (root / "contracts" / "examples", root / "engine" / "tests" / "golden")
        if base.exists()
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".json", ".sse"}
    )
    if examples_bytes > EXAMPLES_LIMIT:
        raise FixtureCheckError("examples, goldens and SSE streams exceed 3 MiB")
    measured_budget = {
        "catalogue_json_bytes": catalogue_bytes,
        "derived_png_bytes": sum(references[digest] for digest in png_digests),
        "examples_goldens_sse_bytes": examples_bytes,
        "orbital_ephemeris_bytes": orbital_bytes,
        "raw_scl_range_bytes": sum(references[digest] for digest in scl_digests),
        "unique_referenced_bytes": unique_bytes,
    }
    for name, measured in measured_budget.items():
        if fixture_set["budget"][name] != measured:
            raise FixtureCheckError(
                f"declared {name} {fixture_set['budget'][name]} does not equal {measured}"
            )
    repository_fixture_bytes = examples_bytes + sum(
        path.stat().st_size for path in fixtures.rglob("*") if path.is_file()
    )
    if not allow_orphans and repository_fixture_bytes >= FIXTURE_LIMIT:
        raise FixtureCheckError(
            f"repository fixture material {repository_fixture_bytes} must be below {FIXTURE_LIMIT}"
        )
    orphans = _orphan_blobs(fixtures, set(references))
    if orphans and not allow_orphans:
        raise FixtureCheckError(f"unreferenced fixture blobs: {', '.join(orphans)}")
    asyncio.run(_check_replay(fixtures, fixture_set))
    _verify_scl_statistics(fixtures, fixture_set, manifests)
    return {
        "budget_bytes": FIXTURE_LIMIT,
        "fixture_set": fixture_set["fixture_set"],
        "catalogue_json_bytes": catalogue_bytes,
        "examples_goldens_sse_bytes": examples_bytes,
        "manifests": len(manifests),
        "orbital_ephemeris_bytes": orbital_bytes,
        "presets": len(fixture_set["presets"]),
        "repository_fixture_bytes": repository_fixture_bytes,
        "status": fixture_set["status"],
        "unique_blob_bytes": unique_bytes,
        "unique_blobs": len(references),
    }
