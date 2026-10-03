"""AOI CRUD routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from ncl_engine.api.dependencies import runtime
from ncl_engine.api.errors import NclApiError
from ncl_engine.api.pagination import decode_cursor, encode_cursor
from ncl_engine.domain.models import Aoi, AoiCreate, AoiPage, AoiPatch, PaginationMeta
from ncl_engine.runtime import Runtime

router = APIRouter()


@router.get("/aois", operation_id="listAois", response_model=AoiPage)
async def list_aois(
    app: Annotated[Runtime, Depends(runtime)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> AoiPage:
    try:
        offset = decode_cursor(cursor)
    except ValueError as exc:
        raise NclApiError(422, "INVALID_CURSOR", str(exc)) from exc
    values = app.service.list_aois()
    page = values[offset : offset + limit]
    return AoiPage(
        data=page,
        meta=PaginationMeta(
            count=len(page),
            next_cursor=encode_cursor(offset + len(page), len(values)),
            as_of=app.clock.now(),
        ),
    )


@router.post("/aois", operation_id="createAoi", response_model=Aoi, status_code=201)
async def create_aoi(
    body: AoiCreate,
    response: Response,
    app: Annotated[Runtime, Depends(runtime)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Aoi:
    try:
        aoi = app.service.create_aoi(body, idempotency_key)
    except ValueError as exc:
        code = "IDEMPOTENCY_CONFLICT" if str(exc) == "IDEMPOTENCY_CONFLICT" else "INVALID_AOI"
        status = 409 if code == "IDEMPOTENCY_CONFLICT" else 422
        raise NclApiError(status, code, str(exc)) from exc
    response.headers["Location"] = f"/v1/aois/{aoi.id}"
    return aoi


@router.get("/aois/{aoi_id}", operation_id="getAoi", response_model=Aoi)
async def get_aoi(aoi_id: str, app: Annotated[Runtime, Depends(runtime)]) -> Aoi:
    value = app.service.get_aoi(aoi_id)
    if value is None:
        raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
    return value


@router.patch("/aois/{aoi_id}", operation_id="updateAoi", response_model=Aoi)
async def update_aoi(aoi_id: str, body: AoiPatch, app: Annotated[Runtime, Depends(runtime)]) -> Aoi:
    try:
        value = app.service.update_aoi(aoi_id, body)
    except ValueError as exc:
        raise NclApiError(422, "INVALID_AOI", str(exc)) from exc
    if value is None:
        raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
    return value


@router.delete("/aois/{aoi_id}", operation_id="deleteAoi", status_code=204)
async def delete_aoi(aoi_id: str, app: Annotated[Runtime, Depends(runtime)]) -> Response:
    if not app.service.delete_aoi(aoi_id):
        raise NclApiError(404, "NOT_FOUND", f"AOI {aoi_id} does not exist.")
    return Response(status_code=204)
