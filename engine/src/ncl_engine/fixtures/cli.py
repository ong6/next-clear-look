"""Command-line entrypoint for fixture record/check/diff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .check import FixtureCheckError, check_repository
from .diff import fixture_diff
from .record import run_record


def _default_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ncl_engine.fixtures")
    parser.add_argument("--root", default=_default_root(), type=Path, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="run the engine pipeline through live recording")
    record.add_argument("--preset", action="append", dest="presets", required=True)
    record.add_argument(
        "--clock",
        required=True,
        help="recording instant; the replay clock is selected at or before it",
    )
    record.add_argument(
        "--frozen-at",
        help="reuse a reviewed replay clock when regenerating derived fixture outputs",
    )
    record.add_argument(
        "--resume",
        action="store_true",
        help="resume a failed publication from its validated local source cache",
    )
    commands.add_parser("check", help="validate manifests, hashes, lineage and byte budgets")
    diff = commands.add_parser("diff", help="compare a working fixture with the committed version")
    diff.add_argument("--preset", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "record":
            result = run_record(
                args.root,
                args.presets,
                args.clock,
                resume=args.resume,
                frozen_at=args.frozen_at,
            )
        elif args.command == "diff":
            result = fixture_diff(args.root.resolve(), args.preset)
        else:
            result = check_repository(args.root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (FixtureCheckError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
