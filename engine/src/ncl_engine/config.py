"""Environment-backed engine configuration with explicit live-mode gating."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    fixture_root: Path
    fixture_set: str = "ncl-showcase"
    default_mode: str = "replay"
    allow_live: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    maximum_jobs: int = 64
    maximum_running_jobs: int = 2
    thumbnail_long_edge: int = 640

    @classmethod
    def from_env(cls) -> Settings:
        repository_root = Path(__file__).resolve().parents[3]
        data_dir = Path(os.environ.get("NCL_STATE_DIR", repository_root / ".ncl-data"))
        fixture_root = Path(os.environ.get("NCL_FIXTURES_DIR", repository_root / "fixtures"))
        mode = os.environ.get("NCL_MODE", "replay").strip().lower()
        if mode not in {"live", "replay"}:
            raise ValueError("NCL_MODE must be live or replay")
        allow_live = _truthy(os.environ.get("NCL_ALLOW_LIVE"))
        if mode == "live" and not allow_live:
            raise ValueError("NCL_MODE=live requires NCL_ALLOW_LIVE=1")
        return cls(
            data_dir=data_dir,
            fixture_root=fixture_root,
            fixture_set=os.environ.get("NCL_FIXTURE_SET", "ncl-showcase"),
            default_mode=mode,
            allow_live=allow_live,
            host=os.environ.get("NCL_HOST", "127.0.0.1"),
            port=int(os.environ.get("NCL_PORT", "8000")),
        )

    @property
    def database_path(self) -> Path:
        filename = (
            "live.sqlite" if self.default_mode == "live" else f"replay-{self.fixture_set}.sqlite"
        )
        return self.data_dir / filename

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def thumbnail_dir(self) -> Path:
        return self.data_dir / "thumbnails"
