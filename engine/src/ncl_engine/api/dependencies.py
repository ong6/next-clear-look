"""Request access to the initialized application runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import Request

if TYPE_CHECKING:
    from ncl_engine.runtime import Runtime


def runtime(request: Request) -> Runtime:
    return cast("Runtime", request.app.state.runtime)
