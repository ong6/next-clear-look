"""HTTP route groups."""

from .aois import router as aois_router
from .jobs import router as jobs_router
from .resources import router as resources_router
from .system import router as system_router

__all__ = ["aois_router", "jobs_router", "resources_router", "system_router"]
