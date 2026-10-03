"""Content-addressed blob storage shared by fixtures and runtime cache."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import FixtureIntegrityError
from .models import sha256_bytes


def blob_relative_path(digest: str) -> Path:
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"invalid SHA-256 digest: {digest!r}")
    # Keep the full digest as the filename so identity is visible and collision-resistant.
    return Path("sha256") / digest[:2] / digest


def put_blob(blob_root: Path, body: bytes) -> tuple[str, Path]:
    digest = sha256_bytes(body)
    relative = blob_relative_path(digest)
    destination = blob_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != body:
            raise FixtureIntegrityError(f"digest collision at {destination}")
        return digest, relative
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_bytes(body)
    os.replace(temporary, destination)
    return digest, relative


def read_blob(blob_root: Path, digest: str, expected_size: int | None = None) -> bytes:
    path = blob_root / blob_relative_path(digest)
    try:
        body = path.read_bytes()
    except FileNotFoundError as exc:
        raise FixtureIntegrityError(f"missing fixture blob: {path}") from exc
    if expected_size is not None and len(body) != expected_size:
        raise FixtureIntegrityError(
            f"fixture blob size mismatch for {digest}: expected {expected_size}, got {len(body)}"
        )
    if sha256_bytes(body) != digest:
        raise FixtureIntegrityError(f"fixture blob digest mismatch: {path}")
    return body
