#!/usr/bin/env python3
"""Enforce the 100% coverage floor for critical deterministic policy modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CRITICAL_MODULES = (
    "engine/src/ncl_engine/domain/clock.py",
    "engine/src/ncl_engine/sources/transport/fixture.py",
    "engine/src/ncl_engine/sources/transport/polite.py",
)


def _module_coverage(report: dict[str, Any], module: str) -> dict[str, Any]:
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage report has no files mapping")
    details = files.get(module)
    if not isinstance(details, dict):
        raise ValueError(f"coverage report is missing {module}")
    return details


def check_report(path: Path) -> list[str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for module in CRITICAL_MODULES:
        details = _module_coverage(report, module)
        missing_lines = details.get("missing_lines", [])
        missing_branches = details.get("missing_branches", [])
        if missing_lines or missing_branches:
            failures.append(
                f"{module}: missing lines {missing_lines}; missing branches {missing_branches}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    failures = check_report(args.report)
    if failures:
        for failure in failures:
            print(f"coverage-policy: {failure}")
        return 1
    print(
        f"coverage-policy: {len(CRITICAL_MODULES)} critical modules at 100% branch coverage"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
