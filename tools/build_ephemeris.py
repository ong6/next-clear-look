#!/usr/bin/env python3
"""Build the bounded DE421 excerpt used by replay from a local full BSP file."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

START = "2023/1/1"
END_EXCLUSIVE = "2028/1/1"
# Skyfield's apparent-position calculation applies Sun/Jupiter/Saturn
# deflection, so the two barycentre segments are required alongside Earth.
TARGETS = "3,5,6,10,399"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="local full de421.bsp"
    )
    parser.add_argument("--fixtures", default=Path("fixtures"), type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"source is not a local file: {source}")

    with tempfile.TemporaryDirectory(prefix="ncl-ephemeris-") as temporary:
        excerpt = Path(temporary) / "de421-2023-2027.bsp"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "jplephem",
                "excerpt",
                "--targets",
                TARGETS,
                START,
                END_EXCLUSIVE,
                str(source),
                str(excerpt),
            ],
            check=True,
        )
        body = excerpt.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        destination = args.fixtures / "blobs" / "sha256" / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(excerpt, destination)
    print(f"{digest} {len(body)} {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
