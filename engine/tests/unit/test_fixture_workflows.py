from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ncl_engine.domain.clock import FrozenClock
from ncl_engine.fixtures import cli
from ncl_engine.fixtures.check import (
    FixtureCheckError,
    _read_json,
    _validate_aoi,
    _validate_schema,
    check_repository,
)
from ncl_engine.fixtures.diff import _summary, fixture_diff
from ncl_engine.fixtures.record import (
    _load_pipeline,
    _materialize_derived,
    _publish_result,
    latest_valid_frozen_at,
    parse_utc,
)
from ncl_engine.fixtures.record import (
    record_fixture_set as orchestrate_record,
)
from ncl_engine.healthcheck import main as healthcheck_main
from ncl_engine.seed import import_recorded_replay
from ncl_engine.sources.transport.blobs import put_blob
from ncl_engine.storage import SQLiteStore

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _blob_reference(blob_root: Path, body: bytes, media_type: str) -> dict[str, object]:
    digest, relative = put_blob(blob_root, body)
    return {
        "media_type": media_type,
        "path": relative.as_posix(),
        "sha256": digest,
        "size": len(body),
    }


def test_fixture_repository_is_self_consistent(tmp_path: Path, repository_root: Path) -> None:
    shutil.copytree(repository_root / "fixtures", tmp_path / "fixtures")
    fixture_set_path = tmp_path / "fixtures/fixture-set.json"
    fixture_set = json.loads(fixture_set_path.read_text(encoding="utf-8"))
    fixture_set["budget"]["examples_goldens_sse_bytes"] = 0
    fixture_set_path.write_text(json.dumps(fixture_set), encoding="utf-8")
    result = check_repository(tmp_path)
    assert result["status"] in {"pending-recording", "ready"}
    assert result["presets"] == 5


def test_recording_clock_and_pipeline_loader_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert parse_utc("2024-10-03T00:00:00Z") == datetime(2024, 10, 3, tzinfo=UTC)
    with pytest.raises(ValueError, match="UTC offset"):
        parse_utc("2026-10-03T00:00:00")
    epoch = NOW - timedelta(hours=1)
    opportunity = NOW + timedelta(hours=3)
    assert latest_valid_frozen_at(NOW, [epoch], [opportunity]) == NOW
    with pytest.raises(ValueError, match="at least one OMM"):
        latest_valid_frozen_at(NOW, [], [opportunity])
    with pytest.raises(ValueError, match="no frozen_at"):
        latest_valid_frozen_at(NOW, [epoch], [])

    monkeypatch.setenv("NCL_FIXTURE_PIPELINE", "missing-separator")
    with pytest.raises(RuntimeError, match="module:function"):
        _load_pipeline()
    monkeypatch.setenv("NCL_FIXTURE_PIPELINE", "ncl_engine.pipeline:record_fixture_set")
    assert callable(_load_pipeline())


def test_materialize_derived_json_png_and_existing_body(tmp_path: Path) -> None:
    blob_root = tmp_path / "blobs"
    json_artifact = _materialize_derived("value.json", {"a": 1}, blob_root, ["source"])
    assert json_artifact["body"]["media_type"] == "application/json"
    png_artifact = _materialize_derived(
        "image.png",
        {"png_base64": "cG5n", "media_type": "image/png", "source_body_sha256": "own"},
        blob_root,
        ["source"],
    )
    assert png_artifact["source_body_sha256"] == ["own", "source"]
    existing = {"body": {"path": "x", "sha256": "y", "size": 1}}
    assert _materialize_derived("existing", existing, blob_root, []) == existing
    with pytest.raises(ValueError, match="base64 payload must be text"):
        _materialize_derived("bad", {"png_base64": 1}, blob_root, [])


@pytest.mark.asyncio
async def test_publish_result_materializes_manifest_and_budgets(
    tmp_path: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = tmp_path / "fixtures"
    shutil.copytree(repository_root / "fixtures", fixtures)
    fixture_set = json.loads((fixtures / "fixture-set.json").read_text(encoding="utf-8"))
    celestrak_body = _blob_reference(fixtures / "blobs", b"[]", "application/json")
    earth_body = _blob_reference(fixtures / "blobs", b'{"features":[]}', "application/json")

    def interaction(identifier: str, source_id: str, body: dict[str, object]) -> dict[str, Any]:
        return {
            "id": identifier,
            "source_id": source_id,
            "request": {"url": f"https://example.test/{identifier}"},
            "response": {"retrieved_at": NOW.isoformat(), "body": body},
        }

    interactions = [
        interaction("celestrak", "celestrak", celestrak_body),
        interaction("earth", "earth-search", earth_body),
    ]
    opportunity_time = NOW + timedelta(hours=3)
    result = {
        "ephemeris_provenance": {"sha256": fixture_set["sources"]["ephemeris"]["body"]["sha256"]},
        "presets": {
            "singapore-coast": {
                "interaction_ids": ["celestrak", "earth"],
                "history_provenance": {
                    "bytes_bundled": False,
                    "interaction_ids": [],
                    "unbundled_interaction_ids": [],
                },
                "derived": {
                    "aoi.json": {"aoi_id": "aoi_sg_tuas_coast"},
                    "scenes.json": [],
                    "opportunities.json": [{"closest_time": opportunity_time.isoformat()}],
                },
                "query_window": {
                    "start": (NOW - timedelta(days=1)).isoformat(),
                    "end": NOW.isoformat(),
                },
                "attributions": ["test"],
                "budget": {},
            }
        },
    }
    monkeypatch.setattr("ncl_engine.fixtures.record.check_repository", lambda *args, **kwargs: {})
    paths = await _publish_result(
        fixtures,
        fixture_set,
        result,
        interactions,
        ["singapore-coast"],
        NOW,
    )
    assert (fixtures / "presets/singapore-coast/manifest.json") in paths
    published = json.loads((fixtures / "fixture-set.json").read_text(encoding="utf-8"))
    assert published["sources"]["celestrak"]["sha256"] == celestrak_body["sha256"]
    assert published["budget"]["unique_referenced_bytes"] > 0


def test_import_recorded_replay_projects_all_derived_resources(
    tmp_path: Path, repository_root: Path
) -> None:
    fixtures = tmp_path / "fixtures"
    blob_root = fixtures / "blobs"
    preset_dir = fixtures / "presets" / "singapore-coast"
    preset_dir.mkdir(parents=True)
    shutil.copy(
        repository_root / "fixtures/presets/singapore-coast/aoi.geojson",
        preset_dir / "aoi.geojson",
    )
    examples = repository_root / "contracts" / "examples"
    scene = json.loads((examples / "scene.json").read_text(encoding="utf-8"))
    scene_id = str(scene["id"])
    derived = {
        "opportunities.json": _materialize_derived(
            "opportunities.json",
            json.loads((examples / "opportunities.json").read_text(encoding="utf-8"))["data"],
            blob_root,
            [],
        ),
        "scenes.json": _materialize_derived(
            "scenes.json", [{**scene, "relative_orbit": 118}], blob_root, []
        ),
        f"statistics/{scene_id}.json": _materialize_derived(
            "statistics.json",
            json.loads((examples / "scene-statistics.json").read_text(encoding="utf-8")),
            blob_root,
            [],
        ),
        f"thumbnails/{scene_id}.png": _materialize_derived(
            "thumbnail.png",
            {"body_base64": "cG5n", "media_type": "image/png", "width": 1, "height": 1},
            blob_root,
            [],
        ),
        "likelihood.json": _materialize_derived(
            "likelihood.json",
            json.loads((examples / "likelihood.json").read_text(encoding="utf-8")),
            blob_root,
            [],
        ),
    }
    manifest = {
        "aoi": "presets/singapore-coast/aoi.geojson",
        "derived": derived,
        "query_window": {
            "start": "2026-09-03T00:00:00Z",
            "end": "2026-10-03T00:00:00Z",
        },
    }
    (preset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    fixture_set = {
        "status": "ready",
        "frozen_at": "2026-10-03T00:00:00Z",
        "recorded_at": "2026-10-03T00:00:00Z",
        "presets": [
            {
                "slug": "singapore-coast",
                "manifest": "presets/singapore-coast/manifest.json",
            }
        ],
    }
    (fixtures / "fixture-set.json").write_text(json.dumps(fixture_set), encoding="utf-8")
    store = SQLiteStore(tmp_path / "replay.sqlite")
    assert import_recorded_replay(
        store,
        FrozenClock(NOW),
        fixtures,
        tmp_path / "thumbnails",
    )
    assert store.get_resource("aoi", "aoi_sg_tuas_coast") is not None
    assert store.get_resource("scene", scene_id) is not None
    assert store.get_resource("likelihood", "aoi_sg_tuas_coast") is not None
    store.close()


def test_fixture_diff_cli_and_healthcheck_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {
        "frozen_at": NOW.isoformat(),
        "interactions": [],
        "derived": {},
        "budget": {},
        "attributions": [],
    }
    assert _summary(manifest) is not None
    root = tmp_path
    current = root / "fixtures/presets/test/manifest.json"
    current.parent.mkdir(parents=True)
    current.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("ncl_engine.fixtures.diff._from_git", lambda *args: None)
    assert fixture_diff(root, "test")["current"] is not None

    monkeypatch.setattr(cli, "check_repository", lambda path: {"checked": str(path)})
    monkeypatch.setattr(sys, "argv", ["fixtures", "--root", str(root), "check"])
    assert cli.main() == 0
    assert "checked" in capsys.readouterr().out
    monkeypatch.setattr(
        cli, "check_repository", lambda path: (_ for _ in ()).throw(ValueError("bad"))
    )
    assert cli.main() == 1
    assert "error: bad" in capsys.readouterr().err

    response = SimpleNamespace(status=200, read=lambda: b'{"status":"ok"}')

    class Connection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def request(self, *args: object) -> None:
            del args

        def getresponse(self) -> object:
            return response

        def close(self) -> None:
            return None

    monkeypatch.setattr("ncl_engine.healthcheck.HTTPConnection", Connection)
    assert healthcheck_main() == 0
    monkeypatch.setattr("ncl_engine.healthcheck.HTTPConnection", lambda *args, **kwargs: 1 / 0)
    assert healthcheck_main() == 1


def test_fixture_check_error_helpers(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(FixtureCheckError, match="cannot read JSON"):
        _read_json(missing)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(FixtureCheckError, match="cannot read JSON"):
        _read_json(invalid)

    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object", "required": ["required"]}), encoding="utf-8")
    with pytest.raises(FixtureCheckError, match="schema failed"):
        _validate_schema({}, schema, "test")

    bad_aoi = tmp_path / "aoi.json"
    bad_aoi.write_text(json.dumps({"type": "Feature"}), encoding="utf-8")
    with pytest.raises(FixtureCheckError, match="invalid GeoJSON"):
        _validate_aoi(bad_aoi, "test")
    bad_aoi.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"slug": "wrong"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                },
                "bbox": [0, 0, 1, 1],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixtureCheckError, match="slug mismatch"):
        _validate_aoi(bad_aoi, "test")


@pytest.mark.asyncio
async def test_record_workflow_success_with_injected_pipeline(
    tmp_path: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(repository_root / "fixtures", tmp_path / "fixtures")

    class FakeRecording:
        interactions = [
            {
                "id": "celestrak",
                "source_id": "celestrak",
                "response": {
                    "retrieved_at": NOW.isoformat(),
                    "body": {"sha256": "a" * 64},
                },
            }
        ]

    async def choose(*args: object) -> datetime:
        del args
        return NOW

    async def pipeline(**kwargs: object) -> dict[str, object]:
        del kwargs
        return {"presets": {}}

    async def publish(*args: object) -> list[Path]:
        del args
        return [tmp_path / "fixtures/fixture-set.json"]

    recording = FakeRecording()
    monkeypatch.setenv("NCL_ALLOW_RECORD", "1")
    monkeypatch.setattr("ncl_engine.fixtures.record.AllowlistedHttpTransport", lambda: object())
    monkeypatch.setattr("ncl_engine.fixtures.record.CacheTransport", lambda *a, **k: object())
    monkeypatch.setattr("ncl_engine.fixtures.record.PoliteTransport", lambda value: value)
    monkeypatch.setattr("ncl_engine.fixtures.record.RecordingTransport", lambda *args: recording)
    monkeypatch.setattr("ncl_engine.fixtures.record._select_frozen_at", choose)
    monkeypatch.setattr("ncl_engine.fixtures.record._load_pipeline", lambda: pipeline)
    monkeypatch.setattr("ncl_engine.fixtures.record._publish_result", publish)
    result = await orchestrate_record(tmp_path, ["singapore-coast"], NOW)
    assert result["frozen_at"] == "2026-10-03T00:00:00Z"
    assert result["requests"] == 1

    monkeypatch.delenv("NCL_ALLOW_RECORD")
    with pytest.raises(RuntimeError, match="requires NCL_ALLOW_RECORD"):
        await orchestrate_record(tmp_path, ["singapore-coast"], NOW)


@pytest.mark.asyncio
async def test_record_workflow_accepts_validated_frozen_time(
    tmp_path: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(repository_root / "fixtures", tmp_path / "fixtures")
    reviewed_clock = NOW - timedelta(hours=24)

    class FakeRecording:
        interactions: list[dict[str, object]] = []

    async def pipeline(**kwargs: object) -> dict[str, object]:
        assert kwargs["frozen_at"] == reviewed_clock
        return {"presets": {}}

    async def publish(*args: object) -> list[Path]:
        assert args[-1] == reviewed_clock
        return [tmp_path / "fixtures/fixture-set.json"]

    monkeypatch.setenv("NCL_ALLOW_RECORD", "1")
    monkeypatch.setattr("ncl_engine.fixtures.record.AllowlistedHttpTransport", lambda: object())
    monkeypatch.setattr("ncl_engine.fixtures.record.CacheTransport", lambda *a, **k: object())
    monkeypatch.setattr("ncl_engine.fixtures.record.PoliteTransport", lambda value: value)
    monkeypatch.setattr(
        "ncl_engine.fixtures.record.RecordingTransport", lambda *args: FakeRecording()
    )
    monkeypatch.setattr("ncl_engine.fixtures.record._load_pipeline", lambda: pipeline)
    monkeypatch.setattr("ncl_engine.fixtures.record._publish_result", publish)

    result = await orchestrate_record(
        tmp_path,
        ["singapore-coast"],
        NOW,
        frozen_at=reviewed_clock,
    )
    assert result["frozen_at"] == "2026-10-02T00:00:00Z"

    with pytest.raises(ValueError, match="cannot be after"):
        await orchestrate_record(
            tmp_path,
            ["singapore-coast"],
            NOW,
            frozen_at=NOW + timedelta(seconds=1),
        )

    with pytest.raises(ValueError, match="within 72 hours"):
        await orchestrate_record(
            tmp_path,
            ["singapore-coast"],
            NOW,
            frozen_at=NOW - timedelta(hours=73),
        )
