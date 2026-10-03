"""Protocols shared by engine source adapters."""

from __future__ import annotations

from typing import Protocol

from .models import CanonicalRequest, SourceSnapshot


class DataTransport(Protocol):
    async def request(self, request: CanonicalRequest) -> SourceSnapshot: ...
