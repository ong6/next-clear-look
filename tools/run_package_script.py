#!/usr/bin/env python3
"""Run a package script, failing clearly when it is unavailable."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("script")
    parser.add_argument("--", dest="extra", nargs="*")
    args, extra = parser.parse_known_args()
    package = args.directory / "package.json"
    if not package.exists():
        parser.exit(2, f"gate unavailable: missing {package}\n")
    scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
    if args.script not in scripts:
        parser.exit(2, f"gate unavailable: {package} has no {args.script!r} script\n")
    command = ["pnpm", "--dir", str(args.directory), "run", args.script, *extra]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
