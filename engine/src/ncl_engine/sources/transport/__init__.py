"""One transport seam for live, recorded and offline source bytes."""

from .cache import CacheTransport
from .errors import (
    AmbiguousFixture,
    FixtureIntegrityError,
    FixtureMiss,
    InvalidRequest,
    SourcePolicyError,
    TransportError,
    UpstreamResponseError,
)
from .fixture import FixtureTransport
from .http import AllowlistedHttpTransport
from .loopback import GDAL_ENVIRONMENT, LoopbackCogAdapter, gdal_environment
from .models import CanonicalRequest, SnapshotOrigin, SourceId, SourceSnapshot
from .polite import PoliteTransport
from .protocols import DataTransport
from .recording import RecordingTransport

__all__ = [
    "GDAL_ENVIRONMENT",
    "AllowlistedHttpTransport",
    "AmbiguousFixture",
    "CacheTransport",
    "CanonicalRequest",
    "DataTransport",
    "FixtureIntegrityError",
    "FixtureMiss",
    "FixtureTransport",
    "InvalidRequest",
    "LoopbackCogAdapter",
    "PoliteTransport",
    "RecordingTransport",
    "SnapshotOrigin",
    "SourceId",
    "SourcePolicyError",
    "SourceSnapshot",
    "TransportError",
    "UpstreamResponseError",
    "gdal_environment",
]
