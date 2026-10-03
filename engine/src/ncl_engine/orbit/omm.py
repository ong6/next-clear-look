"""CelesTrak OMM validation and Sentinel platform reconciliation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ncl_engine.provenance.hashing import canonical_json, sha256_bytes

REQUIRED_FIELDS = frozenset(
    {
        "OBJECT_NAME",
        "NORAD_CAT_ID",
        "EPOCH",
        "MEAN_MOTION",
        "ECCENTRICITY",
        "INCLINATION",
        "RA_OF_ASC_NODE",
        "ARG_OF_PERICENTER",
        "MEAN_ANOMALY",
        "BSTAR",
        "MEAN_MOTION_DOT",
        "MEAN_MOTION_DDOT",
        "EPHEMERIS_TYPE",
    }
)
PLATFORMS = {
    "SENTINEL-2A": "sentinel-2a",
    "SENTINEL-2B": "sentinel-2b",
    "SENTINEL-2C": "sentinel-2c",
}


def parse_omm_instant(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class OmmRecord:
    platform: str
    name: str
    norad_catalog_id: int
    epoch: datetime
    values: Mapping[str, Any]
    sha256: str


def parse_omm_catalogue(
    payload: object, *, observed_at: datetime, maximum_future: timedelta = timedelta(minutes=5)
) -> list[OmmRecord]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        raise ValueError("CelesTrak OMM response must be a JSON array")
    seen: set[int] = set()
    records: list[OmmRecord] = []
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise ValueError("each OMM record must be an object")
        missing = REQUIRED_FIELDS - raw.keys()
        if missing:
            raise ValueError(f"OMM record is missing fields: {sorted(missing)}")
        name = str(raw["OBJECT_NAME"]).upper().replace("_", "-")
        if name not in PLATFORMS:
            continue
        catalog_id = int(raw["NORAD_CAT_ID"])
        if catalog_id in seen:
            raise ValueError(f"duplicate NORAD catalogue ID: {catalog_id}")
        if int(raw["EPHEMERIS_TYPE"]) != 0:
            raise ValueError(f"unsupported ephemeris type for {name}")
        epoch = parse_omm_instant(raw["EPOCH"])
        if epoch > observed_at.astimezone(UTC) + maximum_future:
            raise ValueError(f"OMM epoch is unexpectedly in the future for {name}")
        normalized = {str(key): value for key, value in raw.items()}
        records.append(
            OmmRecord(
                platform=PLATFORMS[name],
                name=name,
                norad_catalog_id=catalog_id,
                epoch=epoch,
                values=normalized,
                sha256=sha256_bytes(canonical_json(normalized)),
            )
        )
        seen.add(catalog_id)
    if not records:
        raise ValueError("OMM response contains no Sentinel-2A/B/C records")
    return sorted(records, key=lambda record: record.norad_catalog_id)
