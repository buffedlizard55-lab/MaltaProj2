#!/usr/bin/env python3
"""Repair per-row HotSpawn source links in a committed snapshot (session 7cd2e67a).

Why this exists
---------------
The inherited collectors built `https://www.hotspawn.com/matches/<fixture id>` for every row.
That path is **not** published by HotSawn: it resolves to the general matches index (verified
2026-10-14 ~01:50 UTC — fetching /matches/1079546 returns the "Matches - Hotspawn" listing, not the
Zomblers vs Overtake Sector detail page). Every row therefore carried a source link that did not
point at the match it claimed to cite, which fails the "every table row must have a source link to an
official site" requirement.

This script rewrites the per-row link to a permalink HotSawn itself publishes, taken only from
official HotSawn captures already committed to the repository:

  * `data/picks_permalinks.json`      (captured from the lobby page, 2026-10-13 21:58 UTC)
  * `data/live/samples/lobby_page.txt` (raw lobby HTML capture, 2026-10-13 23:43 UTC)

A fixture with no published permalink falls back to the official lobby page
(`https://play.hotspawn.com/lobby`). No slug is ever constructed or guessed, and no reachability is
claimed for a URL that was not observed in an official capture.

Usage:
  python3 scripts/7cd2e67a/repair_hotspawn_links.py [--target root|live|expanded] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "live"))

from live_core import extract_lobby_permalinks  # noqa: E402

LOBBY_PAGE = "https://play.hotspawn.com/lobby"
BARE_ROUTE = "https://www.hotspawn.com/matches/"
TARGETS = {
    "root": (ROOT / "data" / "hotspawn_matches.json", "matches", "fixture_id"),
    "live": (ROOT / "data" / "live" / "fixtures.json", "fixtures", "fixture_id"),
    # The expanded market board keeps its per-row URL at the top level of each fixture row.
    "expanded": (ROOT / "data" / "expanded" / "lines.json", "fixtures", "fixture_id"),
}
RULE = ("published lobby permalink when HotSawn publishes one, otherwise the official lobby page; "
        "a constructed /matches/<id> path is never used")


def load_permalinks() -> tuple[dict[str, str], list[str]]:
    """Collect every fixture id -> published permalink pair from committed official captures."""
    out: dict[str, str] = {}
    provenance: list[str] = []
    picks = ROOT / "data" / "picks_permalinks.json"
    if picks.is_file():
        doc = json.loads(picks.read_text(encoding="utf-8"))
        for fixture_id, url in (doc.get("permalinks") or {}).items():
            out.setdefault(str(fixture_id), url)
        provenance.append(f"{picks.relative_to(ROOT)} (captured {doc.get('generated_at_utc')})")
    sample = ROOT / "data" / "live" / "samples" / "lobby_page.txt"
    if sample.is_file():
        text = sample.read_text(encoding="utf-8", errors="replace")
        for fixture_id, url in extract_lobby_permalinks(text).items():
            out.setdefault(fixture_id, url)
        provenance.append(f"{sample.relative_to(ROOT)} (raw lobby HTML capture)")
    return out, provenance


def repair(path: Path, key: str, id_key: str, permalinks: dict[str, str]) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    kinds: dict[str, int] = {}
    for row in doc.get(key) or []:
        source = row.get("source") or {}
        fixture_id = str(row.get(id_key))
        old = source.get("hotspawn_match_url") or row.get("hotspawn_match_url")
        if old and old.startswith(BARE_ROUTE) and old[len(BARE_ROUTE):].isdigit():
            old = None
        published = permalinks.get(fixture_id)
        kind = "lobby_published_permalink" if published else "official_lobby_fallback"
        target = published or LOBBY_PAGE
        if old != target or row.get("hotspawn_match_url_kind") != kind:
            if "source" in row:
                source["hotspawn_match_url"] = target
                source["hotspawn_match_url_kind"] = kind
            else:
                row["hotspawn_match_url"] = target
                row["hotspawn_match_url_kind"] = kind
            changed += 1
        kinds[kind] = kinds.get(kind, 0) + 1
    provenance = {
        "repaired_by": "scripts/7cd2e67a/repair_hotspawn_links.py",
        "rule": RULE,
        "permalinks_available": len(permalinks),
        "rows_by_kind": kinds,
        "rows_changed": changed,
    }
    return {"doc": doc, "provenance": provenance, "path": path}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append", choices=sorted(TARGETS), default=None,
                    help="snapshot to repair (repeatable; default: all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    names = args.target or sorted(TARGETS)
    permalinks, sources = load_permalinks()
    if not permalinks:
        print("no published permalinks found in the committed official captures", file=sys.stderr)
        return 1
    print(f"published permalinks available: {len(permalinks)}")
    for name in names:
        path, key, id_key = TARGETS[name]
        if not path.is_file():
            print(f"skip {path.relative_to(ROOT)} (missing)")
            continue
        result = repair(path, key, id_key, permalinks)
        provenance = {**result["provenance"], "sources": sources}
        result["doc"]["link_provenance"] = provenance
        print(json.dumps({name: provenance}, indent=1))
        if not args.dry_run:
            result["path"].write_text(
                json.dumps(result["doc"], indent=1, ensure_ascii=False, allow_nan=False),
                encoding="utf-8")
            print(f"rewrote {result['path'].relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
