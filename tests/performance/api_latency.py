#!/usr/bin/env python3
"""Measure replay API p50/p95 against the per-endpoint architecture budgets."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _read_json(url: str) -> tuple[dict[str, Any], int]:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} did not return a JSON object")
    return payload, len(body)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round(len(ordered) * percentile) - 1))]


def _measure(url: str, samples: int) -> tuple[list[float], int]:
    for _ in range(5):
        _read_json(url)
    timings: list[float] = []
    payload_bytes = 0
    for _ in range(samples):
        started = time.perf_counter()
        _, payload_bytes = _read_json(url)
        timings.append((time.perf_counter() - started) * 1_000)
    return timings, payload_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:4173")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument(
        "--report", type=Path, default=Path(".local/reports/api-latency.json")
    )
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    mode, _ = _read_json(f"{args.base_url}/v1/mode")
    clock = datetime.fromisoformat(
        str(mode["clock"]).replace("Z", "+00:00")
    ).astimezone(UTC)
    end_14d = clock + timedelta(days=14)
    trajectory_end = clock + timedelta(minutes=180)
    query = urllib.parse.urlencode
    endpoints = (
        ("health", "/v1/health", 50, None),
        ("mode", "/v1/mode", 50, None),
        ("aoi-list", "/v1/aois?limit=20", 100, None),
        ("aoi-detail", "/v1/aois/aoi_sg_tuas_coast", 100, None),
        (
            "opportunities",
            "/v1/aois/aoi_sg_tuas_coast/opportunities?"
            + query({"from": clock.isoformat(), "to": end_14d.isoformat()}),
            150,
            None,
        ),
        ("scenes", "/v1/aois/aoi_sg_tuas_coast/scenes", 150, None),
        ("likelihood", "/v1/aois/aoi_sg_tuas_coast/likelihood", 150, None),
        (
            "trajectory",
            "/v1/satellites/sentinel-2c/trajectory?"
            + query(
                {
                    "start": clock.isoformat(),
                    "end": trajectory_end.isoformat(),
                    "step_seconds": 60,
                }
            ),
            200,
            250 * 1024,
        ),
    )
    reports: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, path, p95_budget_ms, payload_budget in endpoints:
        timings, payload_bytes = _measure(f"{args.base_url}{path}", args.samples)
        maximum_ms = max(timings)
        p95_ms = _percentile(timings, 0.95)
        report = {
            "endpoint": name,
            "max_ms": maximum_ms,
            "p50_ms": statistics.median(timings),
            "p95_ms": p95_ms,
            "p95_budget_ms": p95_budget_ms,
            "payload_bytes": payload_bytes,
            "payload_budget_bytes": payload_budget,
            "raw_samples_ms": timings,
        }
        reports.append(report)
        if p95_ms > p95_budget_ms:
            failures.append(f"{name} p95 {p95_ms:.2f} ms > {p95_budget_ms} ms")
        if maximum_ms > 250:
            failures.append(f"{name} max {maximum_ms:.2f} ms > 250 ms")
        if payload_budget is not None and payload_bytes > payload_budget:
            failures.append(
                f"{name} payload {payload_bytes} bytes > {payload_budget} bytes"
            )

    output = {
        "samples_per_endpoint": args.samples,
        "endpoints": reports,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    return 0 if args.report_only or not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
