#!/usr/bin/env python3
"""Session 371a1ce7 — refresh HotSpawn crowd shares (ownership only, never a probability).

Reads HotSpawn's public fixtures API (the endpoint behind https://play.hotspawn.com/lobby) and writes
data/371a1ce7/crowd.json for every fixture on the newest line board's open list.
When the API cannot be reached the existing file is kept untouched, so its read time keeps ageing
visibly on the site instead of a stale number being passed off as fresh.
Standard library only.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "data/fe803b80/board.json"
OUT = ROOT / "data/371a1ce7/crowd.json"
API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
LOBBY = "https://play.hotspawn.com/lobby"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
METHOD = ("participantsN_picked_percent and total_picks from HotSpawn's public fixtures API, copied as served. "
          "OWNERSHIP ONLY: never a probability, never an input to any line. Small samples on low-tier matches.")


def norm(name) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def rows_from_api(api: list, open_rows: list) -> list:
    by_id = {str(f.get("id")): f for f in api if isinstance(f, dict)}
    out = []
    for o in open_rows:
        f = by_id.get(str(o["fixture_id"]))
        if not f:
            continue
        p0, p1 = f.get("participants0_picked_percent"), f.get("participants1_picked_percent")
        if p0 is None or p1 is None:
            continue
        if int(p0) + int(p1) == 0 or not f.get("total_picks"):
            continue          # nobody has picked yet: there is no crowd to report
        n0, n1 = norm(f.get("participants0_name")), norm(f.get("participants1_name"))
        if (n0, n1) == (norm(o["team_a"]), norm(o["team_b"])):
            ca, cb = p0, p1
        elif (n1, n0) == (norm(o["team_a"]), norm(o["team_b"])):
            ca, cb = p1, p0
        else:
            continue          # names disagree: leave the row out rather than guess a side
        out.append({"fixture_id": str(o["fixture_id"]), "team_a": o["team_a"], "crowd_a": int(ca),
                    "team_b": o["team_b"], "crowd_b": int(cb), "total_picks": f.get("total_picks")})
    return out


def main() -> int:
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    open_rows = board.get("open") or []
    try:
        req = urllib.request.Request(API, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as r:
            api = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 - an unreachable API is a reported outcome, not a crash
        print(f"HotSpawn API unreachable ({type(exc).__name__}: {str(exc)[:120]}); keeping existing crowd.json")
        return 0
    if not isinstance(api, list):
        print("HotSpawn API returned an unexpected shape; keeping existing crowd.json")
        return 0
    rows = rows_from_api(api, open_rows)
    if not rows:
        print("no open fixture matched in the API response; keeping existing crowd.json")
        return 0
    doc = {"session": "371a1ce7", "read_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source_url": LOBBY, "source_api": API, "source_kind": "api", "method": METHOD, "rows": rows}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"crowd.json: {len(rows)} of {len(open_rows)} open fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
