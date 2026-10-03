#!/usr/bin/env python3
"""Fail a check with a precise message when a required path is missing."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    if args.path.exists():
        return 0
    parser.exit(2, f"gate unavailable: {args.owner} has not provided {args.path}\n")


if __name__ == "__main__":
    raise SystemExit(main())
