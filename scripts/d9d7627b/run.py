#!/usr/bin/env python3
"""Orchestrator for the HotSpawn CS2 every-match picks board (session d9d7627b).

Default (live) mode: collect -> resolve -> build. With --from-snapshot the collect
step is skipped (replay/CI validation against the committed snapshot).
"""
from __future__ import annotations
import importlib.util as _ilu, sys as _sys
from pathlib import Path as _Path
def _load_d9(name):
    key = f"d9d7627b_{name}"
    if key in _sys.modules:
        return _sys.modules[key]
    p = _Path(__file__).resolve().parent / f"{name}.py" if (_Path(__file__).resolve().parent / f"{name}.py").exists() else _Path(__file__).resolve().parents[1] / "scripts" / "d9d7627b" / f"{name}.py"
    spec = _ilu.spec_from_file_location(key, p)
    mod = _ilu.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


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
