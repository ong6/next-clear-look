"""Cooperative cancellation token."""

from __future__ import annotations

import asyncio


class JobCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def request(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def checkpoint(self) -> None:
        if self.requested:
            raise JobCancelled("Cancelled by client.")
