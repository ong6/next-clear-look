"""SSE envelope creation and encoding."""

from __future__ import annotations

import json
from datetime import UTC, datetime


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def encode_sse(event: dict[str, object]) -> bytes:
    payload = json.dumps(event, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n".encode()
