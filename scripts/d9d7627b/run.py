#!/usr/bin/env python3
"""Orchestrator for the HotSpawn CS2 every-match picks board (session d9d7627b).

Default (live) mode: collect -> resolve -> build. With --from-snapshot the collect
step is skipped (replay/CI validation against the committed snapshot).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(script: str, *args: str) -> None:
    print(f"== {script} {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-snapshot", action="store_true",
                    help="skip live collection; resolve+build from committed snapshot.json")
    args = ap.parse_args()
    if not args.from_snapshot:
        step("collect.py")
    step("resolve.py")
    step("build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
