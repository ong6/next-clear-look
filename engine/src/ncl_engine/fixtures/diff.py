"""Semantic fixture diff suitable for human review."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture manifest must be an object: {path}")
    return cast(dict[str, Any], value)


def _from_git(root: Path, relative: Path) -> Mapping[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative.as_posix()}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"committed fixture manifest must be an object: {relative}")
    return cast(dict[str, Any], value)


def _summary(manifest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    interactions = manifest.get("interactions", [])
    derived = manifest.get("derived", {})
    return {
        "attributions": manifest.get("attributions", []),
        "budget": manifest.get("budget", {}),
        "derived": {
            name: {
                "sha256": value.get("body", {}).get("sha256"),
                "size": value.get("body", {}).get("size"),
                "source_body_sha256": value.get("source_body_sha256", []),
            }
            for name, value in sorted(derived.items())
        },
        "frozen_at": manifest.get("frozen_at"),
        "history_provenance": manifest.get("history_provenance"),
        "requests": [
            {
                "id": item.get("id"),
                "range": item.get("request", {}).get("headers", {}).get("range"),
                "request_key_sha256": item.get("request", {}).get("request_key_sha256"),
                "response_sha256": item.get("response", {}).get("body", {}).get("sha256"),
                "source_id": item.get("source_id"),
            }
            for item in interactions
        ],
    }


def fixture_diff(root: Path, preset: str) -> dict[str, Any]:
    relative = Path("fixtures") / "presets" / preset / "manifest.json"
    current_path = root / relative
    current = _load(current_path) if current_path.exists() else None
    previous = _from_git(root, relative)
    return {"current": _summary(current), "previous": _summary(previous), "preset": preset}
