"""FastAPI application factory; importing this module performs no I/O."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ncl_engine import __version__
from ncl_engine.api.errors import NclApiError
from ncl_engine.api.routers import aois_router, jobs_router, resources_router, system_router
from ncl_engine.config import Settings
from ncl_engine.domain.clock import Clock
from ncl_engine.provenance.hashing import stable_id
from ncl_engine.runtime import Runtime
from ncl_engine.sources import SourceAdapters
from ncl_engine.sources.transport import DataTransport


def _problem(error: NclApiError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        media_type="application/problem+json",
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": error.details,
                "request_id": request_id,
            }
        },
    )


def create_app(
    settings: Settings | None = None,
    *,
    sources: SourceAdapters | None = None,
    transport: DataTransport | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    application_runtime = Runtime(configured, sources=sources, transport=transport, clock=clock)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = application_runtime
        await application_runtime.initialize()
        try:
            yield
        finally:
            await application_runtime.shutdown()

    app = FastAPI(
        title="Next Clear Look Engine API",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID"],
        expose_headers=["Location", "ETag", "X-Provenance-Id"],
    )

    @app.exception_handler(NclApiError)
    async def ncl_error_handler(request: Request, error: NclApiError) -> JSONResponse:
        return _problem(error, stable_id("req", request.method, request.url.path))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details: dict[str, Any] = {
            "violations": json.loads(json.dumps(error.errors(), default=str))
        }
        return _problem(
            NclApiError(422, "VALIDATION_ERROR", "Request validation failed.", details=details),
            stable_id("req", request.method, request.url.path),
        )

    prefix = "/v1"
    app.include_router(system_router, prefix=prefix)
    app.include_router(aois_router, prefix=prefix)
    app.include_router(resources_router, prefix=prefix)
    app.include_router(jobs_router, prefix=prefix)
    return app
