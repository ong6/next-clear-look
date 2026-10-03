from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ncl_engine.config import Settings
from ncl_engine.runtime import Runtime


def test_pending_fixture_clock_is_not_replay_authoritative(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "fixture-set.json").write_text(
        json.dumps(
            {
                "status": "pending-recording",
                "frozen_at": "2026-10-01T00:00:00Z",
                "sources": {},
            }
        )
    )
    settings = Settings(data_dir=tmp_path / "state", fixture_root=fixtures)
    runtime = Runtime(settings)
    assert runtime.clock.now() == datetime(2026, 10, 3, tzinfo=UTC)
    runtime.store.close()


def test_replay_database_is_rebuilt_on_boot(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "state", fixture_root=tmp_path / "fixtures")
    first = Runtime(settings)
    first.store.put_resource("marker", "stale", {"value": True})
    first.store.close()

    second = Runtime(settings)
    assert second.store.get_resource("marker", "stale") is None
    second.store.close()


def test_mode_switch_carries_aois_into_fresh_live_database(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "state",
        fixture_root=tmp_path / "fixtures",
        allow_live=True,
    )
    runtime = Runtime(settings)

    async def exercise() -> None:
        await runtime.initialize()
        before = {aoi.id for aoi in runtime.service.list_aois()}
        assert "aoi_sg_tuas_coast" in before
        await runtime.switch_mode("live", None)
        after = {aoi.id for aoi in runtime.service.list_aois()}
        assert after == before
        await runtime.shutdown()

    import asyncio

    asyncio.run(exercise())
