#!/usr/bin/env python3
"""One-off seed importer (session d9d7627b).

The build sandbox cannot reach bookmaker/HotSpawn hosts, so the first publish is seeded
from the freshest committed collector snapshot in this repo (session f7279a54, collected
2026-10-21T12:28Z). This converts `data/f7279a54/snapshot.json` + `calibration_pairs.json`
into this pipeline's formats, with the seed provenance recorded in the outputs and printed
on every generated page. Live runs (collect.py in GitHub Actions) replace the seed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "f7279a54"
OUT = ROOT / "data" / "d9d7627b"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    snap_path = SRC / "snapshot.json"
    src = json.loads(snap_path.read_text())
    permalinks = (src.get("hotspawn") or {}).get("permalinks") or {}
    fixtures = []
    for fx in (src.get("hotspawn") or {}).get("fixtures") or []:
        fx = dict(fx)
        fx["hotspawn_url"] = permalinks.get(fx["fixture_id"]) or LOBBY_PAGE
        fx["hotspawn_url_kind"] = "match page" if fx["fixture_id"] in permalinks else "lobby"
        fixtures.append(fx)
    seed = {
        "from_file": "data/f7279a54/snapshot.json",
        "from_session": src.get("session"),
        "file_sha256": sha256_file(snap_path),
        "collected_from_utc": src.get("collected_from_utc"),
        "collected_to_utc": src.get("collected_to_utc"),
        "note": ("Seed snapshot imported unchanged (fixture/permalink merge only) because "
                 "the build sandbox has no route to bookmaker/HotSpawn hosts. The live "
                 "collector (scripts/d9d7627b/collect.py, GitHub Actions) replaces it."),
    }
    snap = {"session": "d9d7627b", "seed": seed,
            "collected_from_utc": src.get("collected_from_utc"),
            "collected_to_utc": src.get("collected_to_utc"),
            "hotspawn_fallback_from": src.get("hotspawn_fallback_from"),
            "hotspawn": {"fixtures": fixtures, "permalinks": permalinks,
                         "week": (src.get("hotspawn") or {}).get("week")},
            "quotes": src.get("quotes") or [],
            "rejected_quotes": src.get("rejected_quotes") or [],
            "vrs": src.get("vrs") or {},
            "access_log": src.get("access_log") or {}}
    (OUT / "snapshot.json").write_text(
        json.dumps(snap, indent=1, ensure_ascii=False) + "\n")

    cal_path = SRC / "calibration_pairs.json"
    pairs_src = json.loads(cal_path.read_text()) if cal_path.exists() else {}
    pairs = {}
    for fid, p in pairs_src.items():
        pairs[str(fid)] = {**p, "origin": "seed:f7279a54"}
    cal = {"pairs": pairs,
           "seed": {"from_file": "data/f7279a54/calibration_pairs.json",
                    "file_sha256": sha256_file(cal_path) if cal_path.exists() else None,
                    "note": "Observed market-vs-VRS pairs collected by session f7279a54; "
                            "this pipeline keeps appending its own observations."}}
    (OUT / "calibration.json").write_text(
        json.dumps(cal, indent=1, ensure_ascii=False) + "\n")
    fit = core.fit_calibration(list(pairs.values()))
    print("seed snapshot:", len(fixtures), "fixtures,", len(snap["quotes"]), "quotes,",
          len((snap["vrs"] or {}).get("teams") or []), "VRS teams")
    print("calibration pairs:", fit["n_pairs"], "k:", fit["k"], "MAE:", fit["mae_prob"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
