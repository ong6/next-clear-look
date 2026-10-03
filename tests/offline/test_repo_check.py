from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.repo_check import PNPM_LOCAL_VALUE  # noqa: E402


def test_pnpm_setting_name_is_not_a_local_dependency() -> None:
    assert PNPM_LOCAL_VALUE.search("  excludeLinksFromLockfile: false") is None


def test_pnpm_file_and_link_values_are_rejected() -> None:
    assert (
        PNPM_LOCAL_VALUE.search("      specifier: file:../private-package") is not None
    )
    assert PNPM_LOCAL_VALUE.search("      version: link:../private-package") is not None
