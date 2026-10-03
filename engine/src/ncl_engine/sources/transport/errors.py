"""Failures at the record/replay transport boundary."""


class TransportError(RuntimeError):
    """Base error for a source transport failure."""


class InvalidRequest(TransportError, ValueError):
    """A request cannot be represented by the canonical v1 identity."""


class FixtureMiss(TransportError, LookupError):
    """No recorded response can satisfy a replay request."""


class FixtureIntegrityError(TransportError):
    """A fixture body or manifest does not match its recorded digest."""


class AmbiguousFixture(TransportError):
    """More than one fixture version could satisfy a request."""


class SourcePolicyError(TransportError):
    """An upstream request violates an allowlist or politeness rule."""


class UpstreamResponseError(TransportError):
    """An upstream response is unsafe or inconsistent with the request."""
