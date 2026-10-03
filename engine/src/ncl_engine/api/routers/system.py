"""Health, mode, attribution, and global event routes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ncl_engine.api.dependencies import runtime
from ncl_engine.domain.models import AttributionList, Health, Mode, ModeSwitchRequest
from ncl_engine.jobs.events import iso_z
from ncl_engine.runtime import Runtime

router = APIRouter()


@router.get("/health", operation_id="getHealth", response_model=Health)
async def get_health(app: Annotated[Runtime, Depends(runtime)]) -> Health:
    return app.service.health()


@router.get("/mode", operation_id="getMode", response_model=Mode)
async def get_mode(app: Annotated[Runtime, Depends(runtime)]) -> Mode:
    return app.service.mode_payload()


@router.put("/mode", operation_id="switchMode", response_model=Mode)
async def switch_mode(body: ModeSwitchRequest, app: Annotated[Runtime, Depends(runtime)]) -> Mode:
    await app.switch_mode(body.mode, body.fixture_set)
    return app.service.mode_payload()


@router.get("/attributions", operation_id="listAttributions", response_model=AttributionList)
async def list_attributions(app: Annotated[Runtime, Depends(runtime)]) -> AttributionList:
    return app.service.attributions()


@router.get("/events", operation_id="streamLiveEvents")
async def stream_live_events(app: Annotated[Runtime, Depends(runtime)]) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        now = iso_z(app.clock.now())
        event = {
            "id": "live:1",
            "sequence": 1,
            "type": "live.clock",
            "stream": "live",
            "emitted_at": now,
            "mode": app.mode,
            "clock_time": now,
            "schema_version": "1.0",
            "data": {"speed": 0.0 if app.mode == "replay" else 1.0, "paused": app.mode == "replay"},
        }
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        yield f"id: live:1\nevent: live.clock\ndata: {payload}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
