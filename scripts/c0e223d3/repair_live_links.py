#!/usr/bin/env python3
"""One-off repair of the published `data/live/fixtures.json` snapshot (session c0e223d3 handoff).

Background
----------
`scripts/live/collect_live.py` (session 3cd9787c) wrote a constructed
`https://www.hotspawn.com/matches/<numeric id>` on every row. That route is not published by
HotSpawn: fetching it returns HotSpawn's general "Matches" index, not the match page. Session
7cd2e67a found and repaired the same defect on the root and market boards and added a regression
test, but `data/live/**` was regenerated afterwards by the hourly `live-coverage` workflow while
the constructed line was still in the collector, so the live board kept shipping the broken link
and the shared gate (`tests.test_verify_7cd2e67a`) failed on `main`.

This script fixes the two halves:
  1. `scripts/live/collect_live.py` no longer constructs the path (edited directly, see the
     comment there).
  2. The already-published snapshot is repaired here, in place, so the board that is live today
     stops pointing at the wrong page.

Replacements come only from permalinks the lobby page itself publishes, read out of the committed
lobby capture at `data/live/samples/lobby_page.txt`. Fixtures with no published permalink are
pointed at the official lobby page. Nothing is invented.

Usage: python scripts/c0e223d3/repair_live_links.py
Writes: data/live/fixtures.json and re-renders live/** via scripts/live/build_live.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "live"))

from live_core import extract_lobby_permalinks  # noqa: E402

FIXTURES = ROOT / "data" / "live" / "fixtures.json"
CAPTURE = ROOT / "data" / "live" / "samples" / "lobby_page.txt"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
BARE = re.compile(r"^https://www\.hotspawn\.com/matches/(\d+)$")


def main() -> int:
    if not CAPTURE.is_file():
        print(f"SKIP: no lobby capture at {CAPTURE}", file=sys.stderr)
        return 1
    permalinks = extract_lobby_permalinks(CAPTURE.read_text(encoding="utf-8", errors="replace"))

    doc = json.loads(FIXTURES.read_text(encoding="utf-8"))
    rows = doc.get("fixtures") or []
    counts = {"permalink": 0, "lobby": 0, "already_clean": 0, "constructed_repaired": 0}

    for row in rows:
        source = row.setdefault("source", {})
        url = source.get("hotspawn_match_url")
        if not url:
            source["hotspawn_match_url"] = LOBBY_PAGE
            source["hotspawn_match_url_kind"] = "official lobby page"
            counts["lobby"] += 1
            continue
        m = BARE.match(url)
        if not m:
            counts["already_clean"] += 1
            continue
        fid = m.group(1)
        published = permalinks.get(fid)
        if published:
            source["hotspawn_match_url"] = published
            source["hotspawn_match_url_kind"] = "lobby-published permalink"
            counts["permalink"] += 1
        else:
            source["hotspawn_match_url"] = LOBBY_PAGE
            source["hotspawn_match_url_kind"] = "official lobby page"
            counts["lobby"] += 1
        counts["constructed_repaired"] += 1

    FIXTURES.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    doc.setdefault("repair_note", {})
    print(f"repaired {FIXTURES.relative_to(ROOT)}: {counts}")
    print(f"permalinks available in the committed capture: {len(permalinks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
