#!/usr/bin/env python3
"""Run G1-G17 in order and retain a one-line result for every gate.

With --no-gpu, the browser gates (G12-G16) are reported as skipped: they render a WebGL globe
and need hardware WebGL, which GPU-less CI runners lack. Run plain `make ci` on a workstation
for the full set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES = (
    ("G1", ("repo-check",)),
    ("G2", ("contract-check",)),
    ("G3", ("engine-static",)),
    ("G4", ("engine-unit", "engine-coverage")),
    ("G5", ("engine-property",)),
    ("G6", ("engine-golden",)),
    ("G7", ("fixtures-check",)),
    ("G8", ("offline-check",)),
    ("G9", ("api-contract",)),
    ("G10", ("web-check",)),
    ("G11", ("integration",)),
    ("G12", ("e2e-desktop",)),
    ("G13", ("e2e-mobile",)),
    ("G14", ("screenshots-check",)),
    ("G15", ("a11y",)),
    ("G16", ("perf",)),
    ("G17", ("compose-smoke",)),
)


BROWSER_GATES = {"G12", "G13", "G14", "G15", "G16"}


def main() -> int:
    no_gpu = "--no-gpu" in sys.argv[1:]
    failures = 0
    for gate, targets in GATES:
        if no_gpu and gate in BROWSER_GATES:
            print(f"{gate} SKIP {'+'.join(targets)} (needs hardware WebGL)", flush=True)
            continue
        returncodes = [
            subprocess.run(
                ["make", "--no-print-directory", target], cwd=ROOT, check=False
            ).returncode
            for target in targets
        ]
        outcome = "PASS" if not any(returncodes) else "FAIL"
        print(f"{gate} {outcome} {'+'.join(targets)}", flush=True)
        failures += any(returncodes)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
