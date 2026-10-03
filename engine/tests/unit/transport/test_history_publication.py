from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncl_engine.fixtures.record import _history_provenance, _materialize_derived


def _interaction(
    identifier: str, url: str = "https://example.test/archive/SCL.tif"
) -> dict[str, object]:
    return {
        "id": identifier,
        "source_id": "sentinel-cogs",
        "request": {"url": url},
    }


def test_history_provenance_is_preserved_without_bundled_interactions() -> None:
    payload = {
        "history_provenance": {
            "bytes_bundled": False,
            "interaction_ids": ["sentinel-cogs-0001-deadbeef"],
            "unbundled_interaction_ids": ["sentinel-cogs-0001-deadbeef"],
        }
    }
    provenance = _history_provenance(
        payload,
        {"sentinel-cogs-0001-deadbeef": _interaction("sentinel-cogs-0001-deadbeef")},
        set(),
    )
    assert provenance == {
        "bytes_bundled": False,
        "interaction_ids": ["sentinel-cogs-0001-deadbeef"],
        "unbundled_interaction_ids": ["sentinel-cogs-0001-deadbeef"],
    }
    assert "history_provenance" not in payload


@pytest.mark.parametrize(
    ("bundled_ids", "url", "message"),
    [
        ({"history-1"}, "https://example.test/archive/SCL.tif", "must not be bundled"),
        (set(), "https://example.test/archive/TCI.tif", "not an SCL range"),
    ],
)
def test_history_provenance_rejects_bundled_or_visual_ranges(
    bundled_ids: set[str], url: str, message: str
) -> None:
    payload = {
        "history_provenance": {
            "bytes_bundled": False,
            "interaction_ids": ["history-1"],
            "unbundled_interaction_ids": ["history-1"],
        }
    }
    with pytest.raises(ValueError, match=message):
        _history_provenance(
            payload,
            {"history-1": _interaction("history-1", url)},
            bundled_ids,
        )


def test_history_provenance_allows_memoized_recent_range() -> None:
    payload = {
        "history_provenance": {
            "bytes_bundled": False,
            "interaction_ids": ["memoized-recent"],
            "unbundled_interaction_ids": [],
        }
    }
    provenance = _history_provenance(
        payload,
        {"memoized-recent": _interaction("memoized-recent")},
        {"memoized-recent"},
    )
    assert provenance["interaction_ids"] == ["memoized-recent"]
    assert provenance["unbundled_interaction_ids"] == []


def test_history_artifact_retains_range_digests_without_blob_lineage(tmp_path: Path) -> None:
    range_digest = "a" * 64
    artifact = _materialize_derived(
        "history/datatake.json",
        {"bytes_bundled": False, "source_range_sha256": [range_digest]},
        tmp_path,
        [],
    )
    assert artifact["source_body_sha256"] == []
    body = json.loads((tmp_path / artifact["body"]["path"]).read_bytes())
    assert body == {"bytes_bundled": False, "source_range_sha256": [range_digest]}
