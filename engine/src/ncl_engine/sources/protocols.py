"""Typed domain-facing source protocols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ncl_engine.domain.models import Geometry
from ncl_engine.orbit.omm import OmmRecord
from ncl_engine.sources.transport import SourceSnapshot


@dataclass(frozen=True, slots=True)
class StacItem:
    id: str
    collection: str
    platform: str
    acquisition_time: datetime
    tile: str
    relative_orbit: int | None
    geometry: Geometry
    stac_self_url: str
    assets: Mapping[str, str]
    tile_cloud_cover_percent: float | None
    raw: Mapping[str, object]
    snapshot: SourceSnapshot | None
    datatake_id: str | None = None


class SourceAdapters(Protocol):
    async def load_omm(self, observed_at: datetime) -> list[OmmRecord]: ...

    async def search_scenes(
        self, geometry: Geometry, start: datetime, end: datetime
    ) -> list[StacItem]: ...
