#!/usr/bin/env python3
"""Freeze the minimum source evidence needed by the HotSpawn-live resolver.

Inputs are existing collectors' outputs and stay read-only.  The capture deliberately excludes
HotSpawn crowd percentages and copies no historical performance claims.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_BOARD = ROOT / "data" / "f7279a54" / "board.json"
BASE_SNAPSHOT = ROOT / "data" / "f7279a54" / "snapshot.json"
SECONDARY = ROOT / "data" / "fe803b80" / "board.json"
OFFICIAL = ROOT / "data" / "82a9a0cc" / "official_check.json"
OUT = ROOT / "data" / "82a9a0cc" / "input.json"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    board, snapshot = load(BASE_BOARD), load(BASE_SNAPSHOT)
    if not board.get("open") or not snapshot.get("vrs", {}).get("teams"):
        raise RuntimeError("fresh OURLINE board/snapshot is missing its open inventory or VRS evidence")
    secondary = load(SECONDARY, {})
    # Current bo3.gg team metadata is retained only for duplicate-name roster disambiguation.
    bo3 = secondary.get("bo3gg_teams") or {}
    relevant_names = set()
    for row in board["open"]:
        relevant_names.update((row.get("team_a", "").casefold(), row.get("team_b", "").casefold()))
    bo3_relevant = {key: value for key, value in bo3.items()
                    if str(value.get("name", "")).casefold() in relevant_names}
    capture = {
        "session": "82a9a0cc",
        "captured_utc": board.get("generated_utc"),
        "input_hashes": {str(BASE_BOARD.relative_to(ROOT)): sha(BASE_BOARD),
                         str(BASE_SNAPSHOT.relative_to(ROOT)): sha(BASE_SNAPSHOT),
                         str(SECONDARY.relative_to(ROOT)): sha(SECONDARY)},
        "base": {
            "path": "data/f7279a54/board.json",
            "generated_utc": board.get("generated_utc"),
            "collected_from_utc": board.get("collected_from_utc"),
            "fixture_observation_age_seconds": board.get("fixture_observation_age_seconds"),
            "freshness_limit_hours": board.get("freshness_limit_hours"),
            "week": board.get("week"),
            "calibration": board.get("calibration"),
            "access": board.get("access"),
            "status_conflicts": board.get("status_conflicts"),
            "open": board["open"],
        },
        "raw_quotes": snapshot.get("quotes") or [],
        "vrs": snapshot["vrs"],
        "official_check": load(OFFICIAL, {}),
        "secondary": {"path": "data/fe803b80/board.json",
                      "generated_utc": secondary.get("generated_utc"),
                      "bo3gg_teams": bo3_relevant},
        "policy": {
            "hotspawn_role": "fixture discovery and lock time only; crowd percentages excluded",
            "market_order": "featured OURLINE market, then an evidence-gated two-book alias rescue",
            "fallback_order": "current HLTV probe; additional esportsbooks; unique Valve VRS pair; bo3.gg-rank duplicate resolution; robust VRS candidate range; one-sided VRS floor scenario",
        },
    }
    forbidden = ("picked_percent", "pick_pct_reference", "crowd_pct", "total_picks")
    blob = json.dumps(capture).casefold()
    if any(key in blob for key in forbidden):
        raise RuntimeError("crowd ownership field leaked into probability capture")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(capture, indent=1, ensure_ascii=False) + "\n")
    print(f"captured {len(board['open'])} open fixtures, {len(capture['raw_quotes'])} raw quotes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
