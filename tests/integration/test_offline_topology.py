from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

BASE_URL = os.environ.get("NCL_INTEGRATION_BASE_URL")
pytestmark = pytest.mark.skipif(
    BASE_URL is None,
    reason="the integration runner supplies the offline compose URL",
)


def _response(path: str) -> Iterator[tuple[int, dict[str, str], bytes]]:
    assert BASE_URL is not None
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        yield (
            response.status,
            {name.lower(): value for name, value in response.headers.items()},
            response.read(),
        )


def _get(path: str) -> tuple[int, dict[str, str], bytes]:
    return next(_response(path))


def _json(path: str) -> dict[str, Any]:
    status, _, body = _get(path)
    assert status == 200
    payload = json.loads(body)
    assert isinstance(payload, dict)
    return payload


def test_web_and_real_api_share_the_offline_origin() -> None:
    status, headers, body = _get("/")
    assert status == 200
    assert "text/html" in headers["content-type"]
    assert b'id="root"' in body

    health = _json("/v1/health")
    assert health["status"] == "ok"
    assert health["database"] == "ok"
    assert health["cache"] == "ok"
    assert health["mode"] == "replay"
    assert {entry["status"] for entry in health["upstreams"].values()} == {"fixture"}

    mode = _json("/v1/mode")
    assert mode["mode"] == "replay"
    assert mode["fixture_set"] == "ncl-showcase"
    assert mode["deterministic"] is True
    assert mode["network_enabled"] is False
    assert mode["fixture_recorded_at"] is not None


def test_recorded_presets_and_derived_resources_are_imported() -> None:
    aoi_page = _json("/v1/aois?limit=20")
    aois = aoi_page["data"]
    assert len(aois) == 5
    assert {aoi["preset"]["slug"] for aoi in aois} == {
        "singapore-coast",
        "rotterdam-port",
        "atacama-works",
        "sundarbans-delta",
        "jakobshavn-ice-front",
    }
    tuas = next(aoi for aoi in aois if aoi["id"] == "aoi_sg_tuas_coast")
    assert tuas["replay_coverage"] == {
        "opportunities": True,
        "archive": True,
        "likelihood": True,
        "thumbnails": True,
    }

    scenes = _json("/v1/aois/aoi_sg_tuas_coast/scenes")
    assert 1 <= len(scenes["data"]) <= 6
    scene = scenes["data"][0]
    assert scene["analysis_state"] == "ready"
    assert scene["thumbnail_status"] == "ready"
    statistics = _json(f"/v1/scenes/{scene['id']}/statistics/aoi_sg_tuas_coast")
    assert statistics["valid_pixels"] > 0
    assert statistics["inside_aoi_pixels"] >= statistics["valid_pixels"]
    assert statistics["provenance_id"]

    likelihood = _json("/v1/aois/aoi_sg_tuas_coast/likelihood")
    assert likelihood["clear_posterior"]["sample_size"] >= 20
    assert {horizon["days"] for horizon in likelihood["horizons"]} == {7, 14}


def test_sqlite_is_wal_backed_and_contains_the_fixture_import() -> None:
    probe = """
import json, sqlite3
db = sqlite3.connect('/var/lib/ncl/replay-ncl-showcase.sqlite')
result = {
    'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0],
    'quick_check': db.execute('PRAGMA quick_check').fetchone()[0],
    'aoi_count': db.execute("SELECT count(*) FROM resources WHERE kind='aoi'").fetchone()[0],
    'resource_count': db.execute('SELECT count(*) FROM resources').fetchone()[0],
    'fixture_recorded_at': db.execute(
        "SELECT value FROM metadata WHERE key='fixture_recorded_at'"
    ).fetchone()[0],
}
print(json.dumps(result))
"""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "ncl-platform",
            "-f",
            "docker-compose.yml",
            "-f",
            "tests/compose.offline.yml",
            "exec",
            "-T",
            "engine",
            "python",
            "-c",
            probe,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["journal_mode"] == "wal"
    assert payload["quick_check"] == "ok"
    assert payload["aoi_count"] == 5
    assert payload["resource_count"] > 25
    assert payload["fixture_recorded_at"]


def test_sse_survives_the_nginx_compose_topology() -> None:
    status, headers, body = _get("/v1/events?aoi_id=aoi_sg_tuas_coast")
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers.get("x-accel-buffering") in {None, "no"}
    text = body.decode("utf-8")
    assert "id: live:1\n" in text
    assert "event: live.clock\n" in text
    data_line = next(line for line in text.splitlines() if line.startswith("data: "))
    event = json.loads(data_line[6:])
    assert event["type"] == "live.clock"
    assert event["mode"] == "replay"
    assert event["data"]["paused"] is True
