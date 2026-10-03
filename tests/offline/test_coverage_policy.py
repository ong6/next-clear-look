from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.check_coverage import CRITICAL_MODULES, check_report  # noqa: E402


def _write_report(path: Path, *, missing: bool = False) -> None:
    files = {
        module: {
            "missing_lines": [9] if missing and index == 0 else [],
            "missing_branches": [[10, 12]] if missing and index == 0 else [],
        }
        for index, module in enumerate(CRITICAL_MODULES)
    }
    path.write_text(json.dumps({"files": files}), encoding="utf-8")


def test_critical_coverage_accepts_complete_report(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    _write_report(report)
    assert check_report(report) == []


def test_critical_coverage_reports_missing_lines_and_branches(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    _write_report(report, missing=True)
    failures = check_report(report)
    assert len(failures) == 1
    assert "missing lines [9]" in failures[0]
    assert "missing branches [[10, 12]]" in failures[0]


def test_critical_coverage_requires_every_module(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text('{"files": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="coverage report is missing"):
        check_report(report)
