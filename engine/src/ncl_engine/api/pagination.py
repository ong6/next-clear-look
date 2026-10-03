"""Opaque offset cursors for bounded local collections."""

from __future__ import annotations

import base64


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"===").decode("ascii")
        prefix, value = raw.split(":", 1)
        if prefix != "offset" or int(value) < 0:
            raise ValueError
        return int(value)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid pagination cursor") from exc


def encode_cursor(offset: int, total: int) -> str | None:
    if offset >= total:
        return None
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode().rstrip("=")
