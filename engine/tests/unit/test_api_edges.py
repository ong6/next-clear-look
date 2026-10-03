from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ncl_engine.api.pagination import decode_cursor, encode_cursor


def test_pagination_helpers_and_invalid_api_cursors(client: TestClient) -> None:
    cursor = encode_cursor(1, 3)
    assert cursor is not None
    assert decode_cursor(cursor) == 1
    assert encode_cursor(3, 3) is None
    with pytest.raises(ValueError, match="invalid pagination"):
        decode_cursor("bad")
    assert client.get("/v1/aois", params={"cursor": "bad"}).status_code == 422
    assert client.get("/v1/analysis-jobs", params={"cursor": "bad"}).status_code == 422


def test_aoi_error_and_idempotency_paths(client: TestClient) -> None:
    body = {
        "name": "edge",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
        "timezone": "UTC",
    }
    first = client.post("/v1/aois", headers={"Idempotency-Key": "same"}, json=body)
    assert first.status_code == 201
    assert (
        client.post("/v1/aois", headers={"Idempotency-Key": "same"}, json=body).json()["id"]
        == first.json()["id"]
    )
    conflict = client.post(
        "/v1/aois",
        headers={"Idempotency-Key": "same"},
        json={**body, "name": "different"},
    )
    assert conflict.status_code == 409
    invalid = client.post(
        "/v1/aois",
        json={
            **body,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
            },
        },
    )
    assert invalid.status_code == 422
    assert client.get("/v1/aois/missing").status_code == 404
    assert client.patch("/v1/aois/missing", json={"name": "x"}).status_code == 404
    assert client.delete("/v1/aois/missing").status_code == 404


def test_resource_not_found_filter_and_validation_paths(client: TestClient) -> None:
    assert client.get("/v1/satellites/missing").status_code == 404
    assert (
        client.get(
            "/v1/satellites/missing/trajectory",
            params={
                "start": "2026-10-03T00:00:00Z",
                "end": "2026-10-03T00:03:00Z",
            },
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/v1/satellites/sentinel-2a/trajectory",
            params={
                "start": "2026-10-03T01:00:00Z",
                "end": "2026-10-03T00:00:00Z",
            },
        ).status_code
        == 422
    )
    assert client.get("/v1/scenes/missing").status_code == 404
    assert client.get("/v1/scenes/missing/statistics/missing").status_code == 404
    assert client.get("/v1/scenes/missing/thumbnails/missing").status_code == 404
    assert client.get("/v1/scenes/missing/thumbnails/missing/metadata").status_code == 404
    assert client.get("/v1/provenance/missing").status_code == 404
    assert (
        client.get(
            "/v1/aois/missing/opportunities",
            params={"from": "2026-10-03T00:00:00Z", "to": "2026-10-04T00:00:00Z"},
        ).status_code
        == 404
    )
    filtered = client.get(
        "/v1/aois/aoi_sg_tuas_coast/scenes",
        params={"minimum_aoi_clear_percent": 99.9},
    )
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["count"] == 0


def test_job_mode_and_event_error_paths(client: TestClient) -> None:
    assert client.put("/v1/mode", json={"mode": "live"}).status_code == 409
    assert client.get("/v1/events").text.startswith("id: live:1")
    assert client.post("/v1/analysis-jobs", json={"type": "orbit_only"}).status_code == 422
    assert client.get("/v1/analysis-jobs/missing").status_code == 404
    assert client.delete("/v1/analysis-jobs/missing").status_code == 404
    assert client.get("/v1/analysis-jobs/missing/events").status_code == 404

    created = client.post(
        "/v1/analysis-jobs",
        json={"type": "full_analysis", "aoi_id": "aoi_sg_tuas_coast"},
    ).json()
    for _ in range(100):
        job = client.get(f"/v1/analysis-jobs/{created['id']}").json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.005)
    assert job["state"] == "succeeded"
    assert client.delete(f"/v1/analysis-jobs/{created['id']}").status_code == 409
    assert (
        client.get(
            f"/v1/analysis-jobs/{created['id']}/events",
            headers={"Last-Event-ID": "wrong:1"},
        ).status_code
        == 410
    )
