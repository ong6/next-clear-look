"""Stable problem+json errors."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class NclApiError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message
