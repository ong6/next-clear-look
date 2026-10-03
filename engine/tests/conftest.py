from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ncl_engine.config import Settings
from ncl_engine.main import create_app


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path: Path, repository_root: Path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=tmp_path / "state",
        fixture_root=repository_root / "fixtures",
    )
    with TestClient(create_app(settings)) as value:
        yield value
