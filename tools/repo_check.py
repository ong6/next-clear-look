#!/usr/bin/env python3
"""Repository-shape and supply-chain checks for the platform gate."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))

from ncl_engine.fixtures import check_repository  # noqa: E402

REQUIRED_PLATFORM_PATHS = (
    ".dockerignore",
    ".editorconfig",
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".github/workflows/live-source-health.yml",
    ".gitignore",
    ".nvmrc",
    ".python-version",
    "Dockerfile.engine",
    "Dockerfile.web",
    "LICENSE",
    "Makefile",
    "README.md",
    "docker-compose.yml",
    "engine/pyproject.toml",
    "engine/uv.lock",
    "fixtures/fixture-set.json",
    "fixtures/schemas/fixture-set-v1.schema.json",
    "fixtures/schemas/manifest-v1.schema.json",
    "tests/e2e/playwright.config.ts",
)
LOCAL_PROTOCOL = re.compile(r"^(?:file|link):", re.IGNORECASE)
PNPM_LOCAL_VALUE = re.compile(
    r"(?:specifier|version|resolution):\s*['\"]?(?:file|link):", re.IGNORECASE
)
ABSOLUTE_PATH = re.compile(r"^(?:/|[A-Za-z]:\\\\)")
MACOS_HOME_PREFIX = "/" + "Users" + "/"
FORBIDDEN_SOURCE_CLIENTS = frozenset({"aiohttp", "httpx", "requests", "urllib.request"})


class RepoCheckError(RuntimeError):
    pass


def _is_local_reference(value: object) -> bool:
    return isinstance(value, str) and bool(
        LOCAL_PROTOCOL.match(value.strip()) or ABSOLUTE_PATH.match(value.strip())
    )


def _check_local_dependencies() -> None:
    for package_json in ROOT.rglob("package.json"):
        if ".venv" in package_json.parts or "node_modules" in package_json.parts:
            continue
        package = json.loads(package_json.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            for name, value in package.get(section, {}).items():
                if _is_local_reference(value):
                    raise RepoCheckError(
                        f"local dependency {name!r} in {package_json.relative_to(ROOT)}"
                    )
    for pyproject in ROOT.rglob("pyproject.toml"):
        if ".venv" in pyproject.parts:
            continue
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        dependency_groups = [project.get("project", {}).get("dependencies", [])]
        dependency_groups.extend(project.get("dependency-groups", {}).values())
        for dependency in (item for group in dependency_groups for item in group):
            if " @ " in dependency and _is_local_reference(
                dependency.split(" @ ", 1)[1]
            ):
                raise RepoCheckError(
                    f"local dependency {dependency!r} in {pyproject.relative_to(ROOT)}"
                )
    for lockfile in ROOT.rglob("pnpm-lock.yaml"):
        if "node_modules" in lockfile.parts:
            continue
        for number, line in enumerate(
            lockfile.read_text(encoding="utf-8").splitlines(), 1
        ):
            if PNPM_LOCAL_VALUE.search(line) or MACOS_HOME_PREFIX in line:
                raise RepoCheckError(
                    f"local dependency in {lockfile.relative_to(ROOT)}:{number}"
                )
    for lockfile in ROOT.rglob("uv.lock"):
        if ".venv" in lockfile.parts:
            continue
        lock = tomllib.loads(lockfile.read_text(encoding="utf-8"))
        for package in lock.get("package", []):
            source = package.get("source", {})
            local = (
                source.get("path") or source.get("directory") or source.get("editable")
            )
            if local and not (package.get("name") == "ncl-engine" and local == "."):
                raise RepoCheckError(
                    f"local dependency {package.get('name')!r} in {lockfile.relative_to(ROOT)}"
                )


def _check_license_metadata() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("MIT License\n"):
        raise RepoCheckError("LICENSE is not the MIT license")
    if "Copyright (c) 2026 Ong Jun Xiong" not in license_text:
        raise RepoCheckError("LICENSE is missing the repository owner's copyright line")

    for package_path in (ROOT / "package.json", ROOT / "web" / "package.json"):
        package = json.loads(package_path.read_text(encoding="utf-8"))
        if package.get("license") != "MIT":
            raise RepoCheckError(
                f"{package_path.relative_to(ROOT)} must declare the MIT license"
            )

    engine_metadata = tomllib.loads(
        (ROOT / "engine" / "pyproject.toml").read_text(encoding="utf-8")
    )
    if engine_metadata.get("project", {}).get("license") != "MIT":
        raise RepoCheckError("engine/pyproject.toml must declare the MIT license")


def _check_source_boundaries() -> None:
    source = ROOT / "engine" / "src" / "ncl_engine"
    if not source.exists():
        return
    allowed = source / "sources" / "transport"
    for path in source.rglob("*.py"):
        if path.is_relative_to(allowed):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        if any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in FORBIDDEN_SOURCE_CLIENTS
        ):
            raise RepoCheckError(
                f"direct HTTP client outside transport: {path.relative_to(ROOT)}"
            )


def _check_generated_contracts() -> None:
    validator = ROOT / "contracts" / "validate.py"
    if not validator.exists():
        return
    result = subprocess.run([sys.executable, str(validator)], cwd=ROOT, check=False)
    if result.returncode:
        raise RepoCheckError("contract examples or generated artifacts are stale")


def main() -> int:
    try:
        missing = [
            path for path in REQUIRED_PLATFORM_PATHS if not (ROOT / path).exists()
        ]
        if missing:
            raise RepoCheckError(f"missing required paths: {', '.join(missing)}")
        if (ROOT / "web" / "package.json").exists() and not (
            ROOT / "pnpm-lock.yaml"
        ).exists():
            raise RepoCheckError(
                "web exists but the required root pnpm-lock.yaml is missing"
            )
        _check_license_metadata()
        _check_local_dependencies()
        _check_source_boundaries()
        _check_generated_contracts()
        fixtures = check_repository(ROOT)
    except (OSError, RepoCheckError, RuntimeError, ValueError) as exc:
        print(f"repo-check: {exc}", file=sys.stderr)
        return 1
    result: dict[str, Any] = {
        "fixture_bytes": fixtures["unique_blob_bytes"],
        "status": "ok",
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
