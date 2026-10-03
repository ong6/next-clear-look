"""Content-addressed derived artifact writer."""

from __future__ import annotations

import os
from pathlib import Path

from .hashing import sha256_bytes


def put_bytes(root: Path, value: bytes) -> tuple[str, Path]:
    digest = sha256_bytes(value)
    destination = root / "sha256" / digest[:2] / digest
    if destination.exists():
        return digest, destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, destination)
    return digest, destination
