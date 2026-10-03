from __future__ import annotations

import time
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient


def _wait(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(2_000):
        response = client.get(f"/v1/analysis-jobs/{job_id}")
        body = response.json()
        if body["state"] in {"succeeded", "failed", "cancelled"}:
            return body  # type: ignore[no-any-return]
        time.sleep(0.01)
    raise AssertionError("job did not terminate")


def test_orbit_only_preserves_likelihood_and_not_recorded_archive(client: TestClient) -> None:
    aoi = client.post(
        "/v1/aois",
        json={
            "name": "drawn Tuas",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [103.62, 1.24],
                        [103.77, 1.24],
                        [103.77, 1.36],
                        [103.62, 1.36],
                        [103.62, 1.24],
                    ]
                ],
            },
            "timezone": "Asia/Singapore",
        },
    ).json()
    updated_geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [103.62, 1.24],
                [103.78, 1.24],
                [103.78, 1.36],
                [103.62, 1.36],
                [103.62, 1.24],
            ]
        ],
    }
    assert (
        client.patch(f"/v1/aois/{aoi['id']}", json={"geometry": updated_geometry}).status_code
        == 200
    )
    full = client.post(
        "/v1/analysis-jobs", json={"type": "full_analysis", "aoi_id": aoi["id"]}
    ).json()
    assert _wait(client, full["id"])["state"] == "succeeded"
    scenes = client.get(f"/v1/aois/{aoi['id']}/scenes").json()
    assert scenes["meta"]["archive_state"] == "not_recorded"
    before = client.get(f"/v1/aois/{aoi['id']}/likelihood").json()["horizons"]

    response = client.get(
        f"/v1/aois/{aoi['id']}/opportunities",
        params={"from": "2026-10-03T10:00:00Z", "to": "2026-10-03T11:00:00Z"},
    )
    assert response.status_code == 202
    job = _wait(client, response.json()["id"])
    assert job["state"] == "succeeded"
    assert job["type"] == "orbit_only"
    after = client.get(f"/v1/aois/{aoi['id']}/likelihood").json()["horizons"]
    assert after == before

    settled = client.get(
        f"/v1/aois/{aoi['id']}/opportunities",
        params={"from": "2026-10-03T10:00:00Z", "to": "2026-10-03T11:00:00Z"},
    )
    assert settled.status_code == 200
    assert settled.json()["data"] == []


def test_identical_trajectory_request_is_served_from_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    parameters: dict[str, str | int] = {
        "start": "2026-10-03T00:00:00Z",
        "end": "2026-10-03T03:00:00Z",
        "step_seconds": 20,
    }
    first = client.get("/v1/satellites/sentinel-2c/trajectory", params=parameters)
    assert first.status_code == 200
    runtime = cast(Any, client.app).state.runtime

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(runtime.service.propagator, "states_at", fail)
    second = client.get("/v1/satellites/sentinel-2c/trajectory", params=parameters)
    assert second.status_code == 200
    assert second.json() == first.json()
