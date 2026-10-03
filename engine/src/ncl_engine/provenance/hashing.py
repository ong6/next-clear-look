"""Canonical hashes and stable public identifiers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]


def canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    digest = sha256_bytes("|".join(parts).encode("utf-8"))[:length]
    return f"{prefix}_{digest}"
