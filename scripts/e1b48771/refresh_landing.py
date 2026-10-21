#!/usr/bin/env python3
"""Rewrite ONLY the root ``index.html`` from this session's board (session e1b48771).

Background: ``scripts/build_site.py`` renders every root page (cs2.html, flagged.html, the
per-tournament pages, data/lines.json, ...). Running it just to refresh the landing page would rewrite
other sessions' outputs, so the refresh workflow calls this narrow wrapper instead: it imports the
same renderer, regenerates the landing body from ``data/e1b48771/board.json`` (through
``build_site.canonical_home``) and writes ``index.html`` only.

Usage: ``python3 scripts/e1b48771/refresh_landing.py``
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import build_site  # noqa: E402  (same renderer the Pages build uses)


def main() -> int:
    board = build_site.load("data/c64a5e19/board.json")
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_site.page(
        "CS2 picks dashboard",
        "External betting lines, derived no-vig probabilities and explicit unverified gaps "
        "for every CS2 fixture in the HotSpawn Pick'ems lobby.",
        build_site.canonical_home(board), stamp, active="index.html", hero=True)
    path = os.path.join(build_site.ROOT, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"index.html rewritten ({len(html)} bytes) at {stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
