from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ncl_engine.config import Settings
from ncl_engine.domain.clock import FrozenClock
from ncl_engine.domain.models import AnalysisJobCreate, AoiCreate, Geometry, JobStage, JobType
from ncl_engine.fixtures.record import _materialize_derived
from ncl_engine.jobs import JobContext
from ncl_engine.jobs.cancellation import CancellationToken
from ncl_engine.orbit.omm import OmmRecord
from ncl_engine.pipeline import record_fixture_set, verify_fixture_statistics
from ncl_engine.raster.cog import RasterAnalysis, SclAnalysis
from ncl_engine.raster.scl import SclCounts
from ncl_engine.service import EngineService
from ncl_engine.sources import SourceAdapters
from ncl_engine.sources.protocols import StacItem
from ncl_engine.sources.replay import ReplaySourceAdapters
from ncl_engine.sources.transport import (
    CanonicalRequest,
    DataTransport,
    LoopbackCogAdapter,
    RecordingTransport,
    SnapshotOrigin,
    SourceId,
    SourceSnapshot,
)
from ncl_engine.storage import SQLiteStore

NOW = datetime(2026, 10, 3, tzinfo=UTC)
GEOMETRY: Geometry = {
    "type": "Polygon",
    "coordinates": [
        [[103.62, 1.24], [103.77, 1.24], [103.77, 1.36], [103.62, 1.36], [103.62, 1.24]]
    ],
}
COUNTS = SclCounts(
    class_counts=(0, 0, 0, 0, 4_000, 1_000, 0, 0, 0, 0, 0, 0),
    inside_aoi_pixels=5_000,
    valid_pixels=5_000,
    clear_pixels=5_000,
    invalid_pixels=0,
    valid_coverage_percent=100.0,
    clear_percent=100.0,
)
EPHEMERIS_DIGEST = "fb18986a9f2a5bf510b597f5c446c9c257c8e2fc79396060e881a24897243af1"
EPHEMERIS_RELATIVE = Path("blobs") / "sha256" / "fb" / EPHEMERIS_DIGEST


def _items() -> list[StacItem]:
    instants = [
        NOW - timedelta(days=year * 365 + offset)
        for year in range(3)
        for offset in range(-40, 41, 10)
        if NOW - timedelta(days=year * 365 + offset) < NOW
    ]
    return [
        StacItem(
            id=f"item-{index}",
            collection="sentinel-2-l2a",
            platform="sentinel-2a",
            acquisition_time=instant,
            tile="48NUG",
            relative_orbit=118,
            geometry=GEOMETRY,
            stac_self_url=f"https://example.test/item-{index}",
            assets={
                "scl": "https://example.test/SCL.tif",
                "visual": "https://example.test/TCI.tif",
            },
            tile_cloud_cover_percent=10.0,
            raw={},
            snapshot=None,
            datatake_id=f"datatake-{index}",
        )
        for index, instant in enumerate(instants)
    ]


class FakeSources:
    def __init__(self, records: list[OmmRecord], items: list[StacItem]) -> None:
        self.records = records
        self.items = items

    async def load_omm(self, observed_at: datetime) -> list[OmmRecord]:
        del observed_at
        return self.records

    async def search_scenes(
        self, geometry: Geometry, start: datetime, end: datetime
    ) -> list[StacItem]:
        del geometry
        return [item for item in self.items if start <= item.acquisition_time < end]


class FakeAnalyzer:
    def __init__(self, transport: object, **kwargs: object) -> None:
        self.transport = transport
        del kwargs

    async def _touch_range(self) -> None:
        request_method = getattr(self.transport, "request", None)
        if request_method is None:
            return
        await request_method(
            CanonicalRequest(
                SourceId.SENTINEL_COGS,
                "GET",
                "https://sentinel-cogs.s3.us-west-2.amazonaws.com/test/SCL.tif",
                {"Range": "bytes=0-2"},
            )
        )

    async def analyze(
        self, datatake: object, geometry: Geometry, **kwargs: object
    ) -> RasterAnalysis:
        del datatake, geometry, kwargs
        await self._touch_range()
        return RasterAnalysis(COUNTS, 20.0, 1, b"png", 1, 1)

    async def analyze_scl(
        self, datatake: object, geometry: Geometry, *, coarse: bool = False, **kwargs: object
    ) -> SclAnalysis:
        del datatake, geometry, coarse, kwargs
        await self._touch_range()
        return SclAnalysis(COUNTS, 20.0, 4)


class ConcurrentHistoryAnalyzer(FakeAnalyzer):
    instances: list[ConcurrentHistoryAnalyzer] = []

    def __init__(self, transport: object, **kwargs: object) -> None:
        super().__init__(transport, **kwargs)
        self.active_recent = 0
        self.high_water_recent = 0
        self.active_scl = 0
        self.high_water_scl = 0
        self.instances.append(self)

    async def analyze(
        self, datatake: object, geometry: Geometry, **kwargs: object
    ) -> RasterAnalysis:
        self.active_recent += 1
        self.high_water_recent = max(self.high_water_recent, self.active_recent)
        try:
            await asyncio.sleep(0.01)
            return await super().analyze(datatake, geometry, **kwargs)
        finally:
            self.active_recent -= 1

    async def analyze_scl(
        self, datatake: object, geometry: Geometry, *, coarse: bool = False, **kwargs: object
    ) -> SclAnalysis:
        self.active_scl += 1
        self.high_water_scl = max(self.high_water_scl, self.active_scl)
        try:
            await asyncio.sleep(0.01)
            return await super().analyze_scl(
                datatake,
                geometry,
                coarse=coarse,
                **kwargs,
            )
        finally:
            self.active_scl -= 1


class FakeContext:
    def __init__(self) -> None:
        self.results: list[str] = []
        self.token = CancellationToken()

    def checkpoint(self) -> None:
        return None

    async def stage_started(
        self, stage: JobStage, *, total_units: int | None, message: str
    ) -> None:
        del stage, total_units, message

    async def progress(self, stage: JobStage, **kwargs: object) -> None:
        del stage, kwargs

    async def stage_completed(self, stage: JobStage, **kwargs: object) -> None:
        del stage, kwargs

    async def result(
        self,
        result_type: str,
        resource_url: str,
        resource: dict[str, object] | None,
        provenance_id: str,
    ) -> None:
        del resource_url, resource, provenance_id
        self.results.append(result_type)

    async def warning(self, code: str, message: str, **kwargs: object) -> None:
        raise AssertionError((code, message, kwargs))


@pytest.mark.asyncio
async def test_live_full_analysis_exercises_every_stage_and_scene_sse(
    tmp_path: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ConcurrentHistoryAnalyzer.instances.clear()
    records = await ReplaySourceAdapters().load_omm(NOW)
    sources = FakeSources(records, _items())
    store = SQLiteStore(tmp_path / "live.sqlite")
    monkeypatch.setattr("ncl_engine.analysis.workflow.RasterAnalyzer", ConcurrentHistoryAnalyzer)
    service = EngineService(
        Settings(data_dir=tmp_path, fixture_root=repository_root / "fixtures"),
        store,
        FrozenClock(NOW),
        cast(SourceAdapters, sources),
        mode="live",
        transport=cast(DataTransport, object()),
        ephemeris_path=repository_root / "fixtures" / EPHEMERIS_RELATIVE,
    )
    aoi = service.create_aoi(
        AoiCreate(name="Tuas", geometry=GEOMETRY, timezone="Asia/Singapore"), None
    )
    context = FakeContext()
    result = await service.run_job(
        cast(JobContext, context), AnalysisJobCreate(type=JobType.FULL_ANALYSIS, aoi_id=aoi.id)
    )
    assert result.scene_count == 3
    assert context.results.count("scene") == 3
    assert "scene_statistics" in context.results
    assert "thumbnail_metadata" in context.results
    assert context.results[-1] == "likelihood"
    opportunity_indexes = [
        index for index, result_type in enumerate(context.results) if result_type == "opportunity"
    ]
    scene_indexes = [
        index for index, result_type in enumerate(context.results) if result_type == "scene"
    ]
    recent_indexes = [
        index
        for index, result_type in enumerate(context.results)
        if result_type in {"scene_statistics", "thumbnail_metadata"}
    ]
    assert max(opportunity_indexes) < min(scene_indexes)
    assert max(scene_indexes) < min(recent_indexes)
    assert max(recent_indexes) < context.results.index("likelihood")
    assert max(analyzer.high_water_recent for analyzer in ConcurrentHistoryAnalyzer.instances) > 1
    assert max(analyzer.high_water_scl for analyzer in ConcurrentHistoryAnalyzer.instances) == 4
    assert service.get_likelihood(aoi.id) is not None
    store.close()


@pytest.mark.asyncio
async def test_recorder_callback_derives_recent_and_seasonal_outputs(
    repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = await ReplaySourceAdapters().load_omm(NOW)
    sources = FakeSources(records, _items())

    class FakeLiveAdapters:
        def __init__(self, transport: object) -> None:
            del transport

        async def load_omm(self, observed_at: datetime) -> list[OmmRecord]:
            return await sources.load_omm(observed_at)

        async def search_scenes(
            self, geometry: Geometry, start: datetime, end: datetime
        ) -> list[StacItem]:
            return await sources.search_scenes(geometry, start, end)

    class FakeTransport:
        def __init__(self) -> None:
            self.interactions = [
                {
                    "id": "celestrak-1",
                    "source_id": "celestrak",
                    "response": {
                        "retrieved_at": NOW.isoformat(),
                        "body": {"sha256": "a" * 64},
                    },
                }
            ]

        async def request(self, request: CanonicalRequest) -> SourceSnapshot:
            if len(self.interactions) == 1:
                self.interactions.append(
                    {
                        "id": "sentinel-cogs-reused",
                        "source_id": "sentinel-cogs",
                        "response": {"body": {"sha256": "unused-by-test"}},
                    }
                )
            return SourceSnapshot(
                source_id=SourceId.SENTINEL_COGS,
                request=request,
                retrieved_at=NOW,
                status=206,
                headers={"content-range": "bytes 0-2/3", "etag": '"v1"'},
                body=b"abc",
                origin=SnapshotOrigin.NETWORK,
                interaction_id="sentinel-cogs-reused",
            )

    monkeypatch.setattr("ncl_engine.pipeline.LiveSourceAdapters", FakeLiveAdapters)
    monkeypatch.setattr("ncl_engine.pipeline.RasterAnalyzer", FakeAnalyzer)
    transport = FakeTransport()
    result = await record_fixture_set(
        aois={
            "jakobshavn-ice-front": {
                "type": "Feature",
                "id": "aoi_sg_tuas_coast",
                "properties": {"timezone": "Asia/Singapore"},
                "geometry": GEOMETRY,
            }
        },
        frozen_at=NOW,
        transport=cast(RecordingTransport, transport),
        cog_adapter_factory=cast(Callable[[DataTransport], LoopbackCogAdapter], object()),
        ephemeris=repository_root / "fixtures" / EPHEMERIS_RELATIVE,
    )
    preset = cast(
        dict[str, object],
        cast(dict[str, object], result["presets"])["jakobshavn-ice-front"],
    )
    derived = cast(dict[str, object], preset["derived"])
    assert len([name for name in derived if name.startswith("history/")]) >= 20
    assert all(
        cast(dict[str, object], value)["source_range_sha256"]
        for name, value in derived.items()
        if name.startswith("history/")
    )
    assert len(cast(list[object], derived["scenes.json"])) == 3
    likelihood = cast(dict[str, object], derived["likelihood.json"])
    assert likelihood["quality"] == "seasonal"
    assert cast(dict[str, object], likelihood["season"])["tier"] == likelihood["quality"]
    assert likelihood["surface_class_policy"] == {
        "surface_scl_classes": [4, 5, 6, 7, 11],
        "snow_ice_counted_as_surface": True,
    }
    assert datetime.fromisoformat(cast(str, likelihood["window_end"])) - datetime.fromisoformat(
        cast(str, likelihood["window_start"])
    ) == timedelta(days=14)
    statistics = cast(
        dict[str, object],
        next(value for name, value in derived.items() if name.startswith("statistics/")),
    )
    assert statistics["clear_scl_classes"] == [4, 5, 6, 7, 11]
    assert statistics["surface_class_policy"] == likelihood["surface_class_policy"]
    provenance = cast(dict[str, object], preset["history_provenance"])
    assert provenance["interaction_ids"] == ["sentinel-cogs-reused"]
    assert provenance["unbundled_interaction_ids"] == []


@pytest.mark.asyncio
async def test_fixture_statistics_verifier_replays_recorded_datatake_mosaic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = tmp_path / "fixtures"
    aoi_path = fixtures / "presets/test/aoi.geojson"
    aoi_path.parent.mkdir(parents=True)
    aoi_path.write_text(
        json.dumps({"type": "Feature", "id": "aoi_test", "geometry": GEOMETRY}),
        encoding="utf-8",
    )
    (fixtures / "fixture-set.json").write_text("{}", encoding="utf-8")
    scenes = [
        {
            "id": "datatake-test",
            "collection": "sentinel-2-l2a",
            "platform": "sentinel-2a",
            "acquisition_time": NOW.isoformat(),
            "tile": "48NUG",
            "relative_orbit": 118,
            "footprint": GEOMETRY,
            "stac_self_url": "https://example.test/item",
            "assets": {"scl": "https://example.test/SCL.tif"},
        }
    ]
    statistics = {
        "scene_id": "datatake-test",
        "class_counts": {
            str(index): {"pixels": value} for index, value in enumerate(COUNTS.class_counts)
        },
        "inside_aoi_pixels": COUNTS.inside_aoi_pixels,
        "valid_pixels": COUNTS.valid_pixels,
        "clear_pixels": COUNTS.clear_pixels,
        "invalid_pixels": COUNTS.invalid_pixels,
        "overview_factor": 4,
        "clear_percent": COUNTS.clear_percent,
    }
    derived = {
        "scenes.json": _materialize_derived("scenes.json", scenes, fixtures / "blobs", []),
        "statistics/datatake-test.json": _materialize_derived(
            "statistics.json", statistics, fixtures / "blobs", []
        ),
    }
    monkeypatch.setattr(
        "ncl_engine.pipeline.FixtureTransport.from_path", lambda path: cast(DataTransport, object())
    )
    monkeypatch.setattr("ncl_engine.pipeline.RasterAnalyzer", FakeAnalyzer)
    assert await verify_fixture_statistics(
        fixtures=fixtures,
        fixture_set={"fixture_set": "ncl-showcase"},
        manifests=[
            {
                "aoi": "presets/test/aoi.geojson",
                "preset_slug": "test",
                "derived": derived,
            }
        ],
    )
