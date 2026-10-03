#!/usr/bin/env python3
"""Run or stop the local engine and web development processes."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_DIR = ROOT / ".local" / "dev"


def stop() -> int:
    stopped = 0
    for path in PID_DIR.glob("*.pid") if PID_DIR.exists() else ():
        try:
            pid = int(path.read_text(encoding="utf-8"))
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        except (FileNotFoundError, ProcessLookupError, ValueError):
            pass
        path.unlink(missing_ok=True)
    subprocess.run(
        ["docker", "compose", "--project-name", "ncl-platform", "down"],
        cwd=ROOT,
        check=False,
    )
    print(f"stopped {stopped} local process(es); state and fixtures were preserved")
    return 0


def run(mode: str) -> int:
    required = [
        ROOT / "engine" / "src" / "ncl_engine" / "main.py",
        ROOT / "web" / "package.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            f"development stack is waiting for required paths: {', '.join(missing)}"
        )
    if mode == "live" and os.environ.get("NCL_ALLOW_LIVE") != "1":
        raise RuntimeError("live mode requires NCL_ALLOW_LIVE=1")
    PID_DIR.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "NCL_FIXTURE_SET": "ncl-showcase",
        "NCL_FIXTURES_DIR": str(ROOT / "fixtures"),
        "NCL_MODE": mode,
        "NCL_STATE_DIR": str(ROOT / ".local" / "state"),
        "TZ": "UTC",
        "VITE_NCL_API_TARGET": "http://127.0.0.1:4200",
    }
    if mode == "replay":
        environment.pop("NCL_ALLOW_LIVE", None)
    else:
        print(
            "LIVE MODE: requests may reach three allowlisted public hosts",
            flush=True,
        )
    commands = {
        "engine": [
            "uv",
            "run",
            "--project",
            "engine",
            "uvicorn",
            "ncl_engine.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "4200",
        ],
        "web": ["pnpm", "--dir", "web", "dev", "--host", "127.0.0.1", "--port", "5173"],
    }
    processes: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for name, command in commands.items():
            process = subprocess.Popen(command, cwd=ROOT, env=environment)
            processes[name] = process
            (PID_DIR / f"{name}.pid").write_text(f"{process.pid}\n", encoding="utf-8")
        while True:
            for name, process in processes.items():
                code = process.poll()
                if code is not None:
                    return code or (1 if name != "" else 0)
            signal.pause()
    except KeyboardInterrupt:
        return 130
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for path in PID_DIR.glob("*.pid"):
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    try:
        return stop() if args.stop else run(args.mode)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
