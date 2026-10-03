"""Deterministic typed replay source used before/without a recorded transport manifest."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files

from ncl_engine.domain.models import Geometry
from ncl_engine.orbit.omm import OmmRecord, parse_omm_catalogue
from ncl_engine.sources.protocols import StacItem


class ReplaySourceAdapters:
    def __init__(self, items: list[StacItem] | None = None) -> None:
        resource = files("ncl_engine.resources").joinpath("sentinel-omm.json")
        self._omm_payload: object = json.loads(resource.read_text(encoding="utf-8"))
        self._items = list(items or [])

    async def load_omm(self, observed_at: datetime) -> list[OmmRecord]:
        return parse_omm_catalogue(self._omm_payload, observed_at=observed_at)

    async def search_scenes(
        self, geometry: Geometry, start: datetime, end: datetime
    ) -> list[StacItem]:
        del geometry
        return [item for item in self._items if start <= item.acquisition_time < end]
