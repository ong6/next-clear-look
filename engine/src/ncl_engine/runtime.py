"""Mutable application runtime used for explicit live/replay mode switching."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ncl_engine.api.errors import NclApiError
from ncl_engine.config import Settings
from ncl_engine.domain.clock import Clock, FrozenClock, SystemClock
from ncl_engine.jobs import JobManager
from ncl_engine.service import EngineService
from ncl_engine.sources import LiveSourceAdapters, ReplaySourceAdapters, SourceAdapters
from ncl_engine.sources.transport import (
    AllowlistedHttpTransport,
    CacheTransport,
    DataTransport,
    FixtureTransport,
    PoliteTransport,
)
from ncl_engine.storage import SQLiteStore


class Runtime:
    def __init__(
        self,
        settings: Settings,
        *,
        sources: SourceAdapters | None = None,
        transport: DataTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings
        self.mode: Literal["live", "replay"] = settings.default_mode  # type: ignore[assignment]
        self._provided_sources = sources
        self._provided_transport = transport
        self._provided_clock = clock
        self.clock: Clock
        self.store: SQLiteStore
        self.service: EngineService
        self.jobs: JobManager
        self._configure(self.mode)

    def _live_transport(self) -> DataTransport:
        if self._provided_transport is not None:
            return self._provided_transport
        http = AllowlistedHttpTransport(timeout_seconds=45.0)
        cached = CacheTransport(http, self.settings.cache_dir)
        return PoliteTransport(cached)

    def _configure(self, mode: Literal["live", "replay"]) -> None:
        self.mode = mode
        if self._provided_clock is not None:
            clock = self._provided_clock
        elif mode == "live":
            clock = SystemClock()
        else:
            clock = FrozenClock(self._replay_instant())
        transport: DataTransport | None
        if self._provided_sources is not None:
            sources = self._provided_sources
            transport = self._provided_transport
        elif mode == "live":
            transport = self._live_transport()
            sources = LiveSourceAdapters(transport)
        else:
            fixture_set_path = self.settings.fixture_root / "fixture-set.json"
            if self._fixture_ready(fixture_set_path):
                transport = FixtureTransport.from_path(fixture_set_path)
                sources = LiveSourceAdapters(transport)
            else:
                transport = None
                sources = ReplaySourceAdapters()
        database_name = (
            "live.sqlite" if mode == "live" else f"replay-{self.settings.fixture_set}.sqlite"
        )
        database_path = self.settings.data_dir / database_name
        if mode == "replay":
            # Replay is a projection of immutable fixtures, never persistent
            # application state, so rebuild it on every process or mode boot.
            for candidate in (
                database_path,
                Path(f"{database_path}-wal"),
                Path(f"{database_path}-shm"),
            ):
                candidate.unlink(missing_ok=True)
        self.clock = clock
        self.store = SQLiteStore(database_path)
        self.service = EngineService(
            self.settings,
            self.store,
            clock,
            sources,
            mode=mode,
            transport=transport,
            ephemeris_path=self._ephemeris_path(),
        )
        self.jobs = JobManager(
            self.store,
            clock,
            lambda: self.mode,
            self.service.run_job,
            maximum_jobs=self.settings.maximum_jobs,
            maximum_running=self.settings.maximum_running_jobs,
        )

    def _ephemeris_path(self) -> Path | None:
        fixture_set_path = self.settings.fixture_root / "fixture-set.json"
        if not fixture_set_path.is_file():
            return None
        value = json.loads(fixture_set_path.read_text(encoding="utf-8"))
        try:
            relative = str(value["sources"]["ephemeris"]["body"]["path"])
        except (KeyError, TypeError):
            return None
        path = self.settings.fixture_root / "blobs" / relative
        return path if path.is_file() else None

    def _replay_instant(self) -> datetime:
        fixture_set_path = self.settings.fixture_root / "fixture-set.json"
        if fixture_set_path.is_file():
            value = json.loads(fixture_set_path.read_text(encoding="utf-8"))
            frozen_at = value.get("frozen_at")
            if value.get("status") == "ready" and isinstance(frozen_at, str):
                return datetime.fromisoformat(frozen_at.replace("Z", "+00:00")).astimezone(UTC)
        # An incomplete fixture has no published clock. The generated contract example
        # keeps startup deterministic until a ready fixture supplies the authoritative value.
        example = (
            Path(__file__).resolve().parents[3] / "contracts" / "examples" / "mode-replay.json"
        )
        value = json.loads(example.read_text(encoding="utf-8"))
        return datetime.fromisoformat(str(value["clock"]).replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _fixture_ready(fixture_set_path: Path) -> bool:
        if not fixture_set_path.is_file():
            return False
        value = json.loads(fixture_set_path.read_text(encoding="utf-8"))
        return bool(value.get("status") == "ready")

    async def initialize(self) -> None:
        await self.service.initialize()

    async def switch_mode(self, mode: Literal["live", "replay"], fixture_set: str | None) -> None:
        del fixture_set
        if mode == self.mode:
            return
        if mode == "live" and not self.settings.allow_live:
            raise NclApiError(
                409, "LIVE_DISABLED", "Set NCL_ALLOW_LIVE=1 before switching to live mode."
            )
        if self.jobs.has_active():
            raise NclApiError(409, "JOBS_ACTIVE", "Mode cannot change while a job is active.")
        aois = self.service.list_aois()
        await self.jobs.shutdown()
        self.store.close()
        self._provided_sources = None
        self._provided_clock = None
        self._configure(mode)
        await self.initialize()
        for aoi in aois:
            if self.service.get_aoi(aoi.id) is not None:
                continue
            carried = aoi.model_copy(
                update={
                    "replay_coverage": aoi.replay_coverage.model_copy(
                        update={
                            "archive": mode == "live",
                            "likelihood": mode == "live",
                            "thumbnails": mode == "live",
                        }
                    ),
                    "updated_at": self.clock.now(),
                }
            )
            self.store.put_resource("aoi", carried.id, carried, sort_key=carried.name.lower())
            if mode == "replay" and carried.origin == "user":
                self.store.put_resource(
                    "archive_state",
                    carried.id,
                    {
                        "archive_state": "not_recorded",
                        "window_start": self.clock.now().isoformat(),
                        "window_end": self.clock.now().isoformat(),
                    },
                    parent_id=carried.id,
                )

    async def shutdown(self) -> None:
        await self.jobs.shutdown()
        self.store.close()
