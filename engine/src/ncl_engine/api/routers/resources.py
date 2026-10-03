"""Satellite, opportunity, scene, likelihood, and provenance routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from ncl_engine.api.dependencies import runtime
from ncl_engine.api.errors import NclApiError
from ncl_engine.domain.models import (
    AnalysisJobCreate,
    JobType,
    Likelihood,
    OpportunityPage,
    OpportunityPageMeta,
    PaginationMeta,
    ProvenanceGraph,
    RasterStatistics,
    Satellite,
    SatellitePage,
    Scene,
    ScenePage,
    ThumbnailMetadata,
    Trajectory,
)
from ncl_engine.runtime import Runtime

router = APIRouter()


def accepted(job: object) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content=job.model_dump(mode="json", by_alias=True),  # type: ignore[attr-defined]
        headers={"Location": f"/v1/analysis-jobs/{job.id}"},  # type: ignore[attr-defined]
    )


@router.get("/satellites", operation_id="listSatellites", response_model=SatellitePage)
async def list_satellites(app: Annotated[Runtime, Depends(runtime)]) -> SatellitePage:
    values = app.service.list_satellites()
    return SatellitePage(
        data=values, meta=PaginationMeta(count=len(values), next_cursor=None, as_of=app.clock.now())
    )


@router.get("/satellites/{satellite_id}", operation_id="getSatellite", response_model=Satellite)
async def get_satellite(satellite_id: str, app: Annotated[Runtime, Depends(runtime)]) -> Satellite:
    value = app.service.get_satellite(satellite_id)
    if value is None:
        raise NclApiError(404, "NOT_FOUND", f"Satellite {satellite_id} does not exist.")
    return value


@router.get(
    "/satellites/{satellite_id}/trajectory", operation_id="getTrajectory", response_model=Trajectory
)
async def get_trajectory(
    satellite_id: str,
    response: Response,
    app: Annotated[Runtime, Depends(runtime)],
    start: datetime,
    end: datetime,
    step_seconds: Annotated[int, Query(ge=10, le=600)] = 60,
) -> Trajectory:
    try:
        value = app.service.trajectory(satellite_id, start, end, step_seconds)
    except KeyError as exc:
        raise NclApiError(404, "NOT_FOUND", f"Satellite {satellite_id} does not exist.") from exc
    except ValueError as exc:
        raise NclApiError(422, "INVALID_TIME_RANGE", str(exc)) from exc
    response.headers["X-Provenance-Id"] = value.provenance_id
    return value


@router.get("/aois/{aoi_id}/opportunities", operation_id="listOpportunities", response_model=None)
async def list_opportunities(
    aoi_id: str,
    app: Annotated[Runtime, Depends(runtime)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    satellite_id: str | None = None,
) -> OpportunityPage | JSONResponse:
    if app.service.get_aoi(aoi_id) is None:
        raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
    if (from_ is None) != (to is None):
        raise NclApiError(422, "INVALID_TIME_RANGE", "from and to must be supplied together.")
    start = from_ or app.clock.now()
    end = to or start + timedelta(days=14)
    values = app.service.opportunities(aoi_id, start, end, satellite_id)
    if not values and not app.service.opportunity_window_complete(aoi_id, start, end, satellite_id):
        job = await app.jobs.create(
            AnalysisJobCreate.model_validate(
                {"type": JobType.ORBIT_ONLY, "aoi_id": aoi_id, "from": start, "to": end}
            )
        )
        return accepted(job)
    return OpportunityPage(
        data=values,
        meta=OpportunityPageMeta(
            count=len(values),
            next_cursor=None,
            as_of=app.clock.now(),
            window_start=start,
            window_end=end,
        ),
    )


@router.get("/aois/{aoi_id}/scenes", operation_id="listScenes", response_model=None)
async def list_scenes(
    aoi_id: str,
    app: Annotated[Runtime, Depends(runtime)],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    minimum_aoi_clear_percent: Annotated[float | None, Query(ge=0, le=100)] = None,
) -> ScenePage | JSONResponse:
    if app.service.get_aoi(aoi_id) is None:
        raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
    end = to or app.clock.now()
    start = from_ or end - timedelta(days=30)
    page = app.service.scenes(aoi_id, start, end)
    if page is None:
        job = await app.jobs.create(AnalysisJobCreate(type=JobType.ARCHIVE_REFRESH, aoi_id=aoi_id))
        return accepted(job)
    if minimum_aoi_clear_percent is not None:
        page.data = [
            scene
            for scene in page.data
            if scene.aoi_clear_percent is not None
            and scene.aoi_clear_percent >= minimum_aoi_clear_percent
        ]
        page.meta.count = len(page.data)
    return page


@router.get("/scenes/{scene_id}", operation_id="getScene", response_model=Scene)
async def get_scene(scene_id: str, app: Annotated[Runtime, Depends(runtime)]) -> Scene:
    value = app.service.get_scene(scene_id)
    if value is None:
        raise NclApiError(404, "NOT_FOUND", f"Scene {scene_id} does not exist.")
    return value


@router.get(
    "/scenes/{scene_id}/statistics/{aoi_id}", operation_id="getSceneStatistics", response_model=None
)
async def get_scene_statistics(
    scene_id: str, aoi_id: str, response: Response, app: Annotated[Runtime, Depends(runtime)]
) -> RasterStatistics | JSONResponse:
    value = app.service.get_statistics(scene_id, aoi_id)
    if value is None:
        if app.service.get_scene(scene_id) is None or app.service.get_aoi(aoi_id) is None:
            raise NclApiError(404, "NOT_FOUND", "Scene or AOI does not exist.")
        job = await app.jobs.create(
            AnalysisJobCreate(type=JobType.RASTER_SCENE, aoi_id=aoi_id, scene_id=scene_id)
        )
        return accepted(job)
    response.headers["X-Provenance-Id"] = value.provenance_id
    return value


@router.get(
    "/scenes/{scene_id}/thumbnails/{aoi_id}", operation_id="getSceneThumbnail", response_model=None
)
async def get_scene_thumbnail(
    scene_id: str, aoi_id: str, app: Annotated[Runtime, Depends(runtime)]
) -> FileResponse | JSONResponse:
    path = app.service.get_thumbnail_path(scene_id, aoi_id)
    metadata = app.service.get_thumbnail_metadata(scene_id, aoi_id)
    if path is None or metadata is None or not path.exists():
        if app.service.get_scene(scene_id) is None or app.service.get_aoi(aoi_id) is None:
            raise NclApiError(404, "NOT_FOUND", "Scene or AOI does not exist.")
        job = await app.jobs.create(
            AnalysisJobCreate(type=JobType.RASTER_SCENE, aoi_id=aoi_id, scene_id=scene_id)
        )
        return accepted(job)
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "ETag": f'"{metadata.sha256}"',
            "X-Provenance-Id": metadata.provenance_id,
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.get(
    "/scenes/{scene_id}/thumbnails/{aoi_id}/metadata",
    operation_id="getSceneThumbnailMetadata",
    response_model=ThumbnailMetadata,
)
async def get_scene_thumbnail_metadata(
    scene_id: str, aoi_id: str, app: Annotated[Runtime, Depends(runtime)]
) -> ThumbnailMetadata:
    value = app.service.get_thumbnail_metadata(scene_id, aoi_id)
    if value is None:
        raise NclApiError(404, "NOT_FOUND", "Thumbnail metadata does not exist.")
    return value


@router.get("/aois/{aoi_id}/likelihood", operation_id="getLikelihood", response_model=None)
async def get_likelihood(
    aoi_id: str,
    response: Response,
    app: Annotated[Runtime, Depends(runtime)],
    as_of: datetime | None = None,
) -> Likelihood | JSONResponse:
    del as_of
    value = app.service.get_likelihood(aoi_id)
    if value is None:
        if app.service.get_aoi(aoi_id) is None:
            raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
        job = await app.jobs.create(AnalysisJobCreate(type=JobType.LIKELIHOOD_ONLY, aoi_id=aoi_id))
        return accepted(job)
    response.headers["X-Provenance-Id"] = value.provenance_id
    return value


@router.get(
    "/provenance/{provenance_id}",
    operation_id="getProvenance",
    response_model=ProvenanceGraph,
)
async def get_provenance(
    provenance_id: str, app: Annotated[Runtime, Depends(runtime)]
) -> ProvenanceGraph:
    value = app.service.get_provenance(provenance_id)
    if value is None:
        raise NclApiError(404, "NOT_FOUND", f"Provenance {provenance_id} does not exist.")
    return ProvenanceGraph.model_validate(value)
