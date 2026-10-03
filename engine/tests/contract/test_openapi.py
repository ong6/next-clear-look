from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from ncl_engine.domain.models import (
    AnalysisJob,
    Aoi,
    Health,
    Likelihood,
    Mode,
    Opportunity,
    ProvenanceGraph,
    RasterStatistics,
    SceneSummary,
    ThumbnailMetadata,
    TrajectorySample,
)


def _spec(repository_root: Path) -> dict[str, Any]:
    value = yaml.safe_load((repository_root / "contracts" / "openapi.yaml").read_text())
    assert isinstance(value, dict)
    return value


def _resolve(spec: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        current: Any = spec
        for part in value["$ref"][2:].split("/"):
            current = current[part]
        value = current
    return value


def _validate_response(
    spec: dict[str, Any], path: str, method: str, response: object, status: int
) -> None:
    operation = spec["paths"][path][method]
    response_schema = _resolve(spec, operation["responses"][str(status)])
    media = response_schema.get("content", {}).get("application/json")
    if media is None:
        media = response_schema.get("content", {}).get("application/problem+json")
    if media is None:
        return
    wrapped = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": spec["components"],
        "allOf": [media["schema"]],
    }
    Draft202012Validator(wrapped).validate(response)


def test_static_contract_validator(repository_root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(repository_root / "contracts" / "validate.py")],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "validated 26 operations" in completed.stdout


def test_replay_api_responses_validate_against_openapi(
    client: TestClient, repository_root: Path
) -> None:
    spec = _spec(repository_root)
    checks = [
        ("/v1/health", "/health", "get", 200),
        ("/v1/mode", "/mode", "get", 200),
        ("/v1/attributions", "/attributions", "get", 200),
        ("/v1/aois", "/aois", "get", 200),
        ("/v1/aois/aoi_sg_tuas_coast", "/aois/{aoi_id}", "get", 200),
        ("/v1/satellites", "/satellites", "get", 200),
        ("/v1/satellites/sentinel-2c", "/satellites/{satellite_id}", "get", 200),
        (
            "/v1/aois/aoi_sg_tuas_coast/opportunities?from=2026-10-03T00:00:00Z&to=2026-10-04T00:00:00Z",
            "/aois/{aoi_id}/opportunities",
            "get",
            200,
        ),
        (
            "/v1/aois/aoi_sg_tuas_coast/scenes",
            "/aois/{aoi_id}/scenes",
            "get",
            200,
        ),
        (
            "/v1/aois/aoi_sg_tuas_coast/likelihood",
            "/aois/{aoi_id}/likelihood",
            "get",
            200,
        ),
        ("/v1/analysis-jobs", "/analysis-jobs", "get", 200),
    ]
    for url, path, method, expected_status in checks:
        response = client.get(url)
        assert response.status_code == expected_status, (url, response.text)
        _validate_response(spec, path, method, response.json(), response.status_code)

    aoi = client.get("/v1/aois/aoi_sg_tuas_coast").json()
    provenance = client.get(f"/v1/provenance/{aoi['provenance_id']}")
    assert provenance.status_code == 200
    _validate_response(spec, "/provenance/{provenance_id}", "get", provenance.json(), 200)

    scene_id = client.get("/v1/aois/aoi_sg_tuas_coast/scenes").json()["data"][0]["id"]
    dynamic_checks = [
        (f"/v1/scenes/{scene_id}", "/scenes/{scene_id}"),
        (
            f"/v1/scenes/{scene_id}/statistics/aoi_sg_tuas_coast",
            "/scenes/{scene_id}/statistics/{aoi_id}",
        ),
        (
            f"/v1/scenes/{scene_id}/thumbnails/aoi_sg_tuas_coast/metadata",
            "/scenes/{scene_id}/thumbnails/{aoi_id}/metadata",
        ),
    ]
    for url, path in dynamic_checks:
        response = client.get(url)
        assert response.status_code == 200, (url, response.text)
        _validate_response(spec, path, "get", response.json(), 200)

    trajectory = client.get(
        "/v1/satellites/sentinel-2c/trajectory",
        params={
            "start": "2026-10-03T00:00:00Z",
            "end": "2026-10-03T00:03:00Z",
            "step_seconds": 60,
        },
    )
    assert trajectory.status_code == 200
    _validate_response(
        spec,
        "/satellites/{satellite_id}/trajectory",
        "get",
        trajectory.json(),
        200,
    )


def test_aoi_crud_jobs_sse_and_binary_thumbnail(client: TestClient, repository_root: Path) -> None:
    create = client.post(
        "/v1/aois",
        headers={"Idempotency-Key": "contract-create-001"},
        json={
            "name": "Contract AOI",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[103.7, 1.2], [103.71, 1.2], [103.71, 1.21], [103.7, 1.21], [103.7, 1.2]]
                ],
            },
            "timezone": "Asia/Singapore",
        },
    )
    assert create.status_code == 201
    aoi_id = create.json()["id"]
    patch = client.patch(f"/v1/aois/{aoi_id}", json={"name": "Renamed contract AOI"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Renamed contract AOI"

    job_response = client.post(
        "/v1/analysis-jobs", json={"type": "full_analysis", "aoi_id": "aoi_sg_tuas_coast"}
    )
    assert job_response.status_code == 202
    job_id = job_response.json()["id"]
    for _ in range(50):
        job = client.get(f"/v1/analysis-jobs/{job_id}")
        if job.json()["state"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.json()["state"] == "succeeded"
    event_response = client.get(f"/v1/analysis-jobs/{job_id}/events")
    assert event_response.status_code == 200
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in event_response.text.splitlines()
        if line.startswith("data: ")
    ]
    event_schemas = repository_root / "contracts" / "events"
    envelope = json.loads((event_schemas / "envelope.schema.json").read_text())
    for payload in payloads:
        schema = json.loads((event_schemas / f"{payload['type']}.schema.json").read_text())
        Draft202012Validator({"allOf": [envelope, schema["allOf"][1]]}).validate(payload)
        assert payload["emitted_at"] == payload["clock_time"]

    scene_id = client.get("/v1/aois/aoi_sg_tuas_coast/scenes").json()["data"][0]["id"]
    thumbnail = client.get(f"/v1/scenes/{scene_id}/thumbnails/aoi_sg_tuas_coast")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/png"
    assert len(thumbnail.content) > 1000
    assert client.delete(f"/v1/aois/{aoi_id}").status_code == 204


def _contract_properties(spec: dict[str, Any], name: str) -> set[str]:
    schema = spec["components"]["schemas"][name]
    properties = set(schema.get("properties", {}))
    for item in schema.get("allOf", []):
        if "$ref" in item:
            properties |= _contract_properties(spec, item["$ref"].rsplit("/", 1)[1])
        else:
            properties |= set(item.get("properties", {}))
    return properties


def test_pydantic_response_models_match_openapi_fields(repository_root: Path) -> None:
    spec = _spec(repository_root)
    models: dict[str, type[BaseModel]] = {
        "Aoi": Aoi,
        "TrajectorySample": TrajectorySample,
        "Opportunity": Opportunity,
        "SceneSummary": SceneSummary,
        "RasterStatistics": RasterStatistics,
        "ThumbnailMetadata": ThumbnailMetadata,
        "Likelihood": Likelihood,
        "ProvenanceGraph": ProvenanceGraph,
        "AnalysisJob": AnalysisJob,
        "Health": Health,
        "Mode": Mode,
    }
    for name, model in models.items():
        pydantic_properties = set(model.model_json_schema(by_alias=True).get("properties", {}))
        assert pydantic_properties == _contract_properties(spec, name), name


def test_replay_exposes_all_spacecraft_on_one_honest_pass_window(client: TestClient) -> None:
    satellites = client.get("/v1/satellites").json()["data"]
    identifiers = {item["id"] for item in satellites}
    assert identifiers == {"sentinel-2a", "sentinel-2b", "sentinel-2c"}
    for satellite in satellites:
        assert client.get(f"/v1/provenance/{satellite['provenance_id']}").status_code == 200
    parameters: dict[str, str | int] = {
        "start": "2026-10-03T02:24:00Z",
        "end": "2026-10-03T02:40:00Z",
        "step_seconds": 20,
    }
    timestamps: list[list[str]] = []
    for identifier in sorted(identifiers):
        response = client.get(f"/v1/satellites/{identifier}/trajectory", params=parameters)
        assert response.status_code == 200
        samples = response.json()["samples"]
        assert len(samples) >= 6
        assert all(
            len(sample["swath_left"]) == len(sample["swath_right"]) == 2 for sample in samples
        )
        assert client.get(f"/v1/provenance/{response.json()['provenance_id']}").status_code == 200
        timestamps.append([sample["time"] for sample in samples])
    assert timestamps[0] == timestamps[1] == timestamps[2]


def test_default_opportunity_list_matches_likelihood_window(client: TestClient) -> None:
    opportunities = client.get("/v1/aois/aoi_sg_tuas_coast/opportunities")
    likelihood = client.get("/v1/aois/aoi_sg_tuas_coast/likelihood")
    assert opportunities.status_code == likelihood.status_code == 200
    opportunity_body = opportunities.json()
    likelihood_body = likelihood.json()
    assert opportunity_body["meta"]["window_start"] == likelihood_body["window_start"]
    assert opportunity_body["meta"]["window_end"] == likelihood_body["window_end"]
    assert all(
        opportunity_body["meta"]["window_start"]
        <= item["closest_time"]
        < opportunity_body["meta"]["window_end"]
        for item in opportunity_body["data"]
    )
    assert (
        client.get(
            "/v1/aois/aoi_sg_tuas_coast/opportunities",
            params={"from": opportunity_body["meta"]["window_start"]},
        ).status_code
        == 422
    )
