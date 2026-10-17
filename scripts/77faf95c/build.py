#!/usr/bin/env python3
"""HQ page builder (session 77faf95c). Renders hq/** from data/77faf95c/** only.

Every probability it publishes is re-derived here from the raw prices retained by collect.py, so
the number on the page can be recomputed from the same evidence the page links to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "77faf95c"


def main():
    if not (DATA / "raw" / "hotspawn.json").exists():
        print("no capture yet - nothing to build")
        return 0
    print("capture present; full builder not yet implemented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
