#!/usr/bin/env python3
"""
Runner task — compact inventory of Pinnacle's market structure for CS2 matchups.

The full-match moneyline must be identified exactly (map moneylines and specials must never
be published as a match price), so this task records, for a sample of CS2 matchups, every
market's type / period / key / alternate flag / designations and the matchup's own period
list. Output: evidence/pinnacle_markets_inventory.json (small, human-readable).
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "evidence"))
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
H = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
     "X-Device-UUID": "be7f6d0f-2a3d-4d1a-9e6f-6a2b5f6c1d20",
     "Referer": "https://www.pinnacle.com/",
     "User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(url):
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    st, data = get(f"{PIN}/sports/12/matchups")
    if not isinstance(data, list):
        print("matchups unavailable", st)
        return 1
    cs2 = [m for m in data if "cs2" in str((m.get("league") or {}).get("name", "")).lower()
           or "counter" in str((m.get("league") or {}).get("name", "")).lower()]
    sample = cs2[:8]
    inv = {"retrieved_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "matchups_total": len(cs2), "samples": []}

    def one(m):
        st2, mkts = get(f"{PIN}/matchups/{m.get('id')}/markets/related/straight")
        rows = []
        if isinstance(mkts, list):
            for mk in mkts:
                rows.append({
                    "type": mk.get("type"), "period": mk.get("period"), "key": mk.get("key"),
                    "matchupId": mk.get("matchupId"), "isAlternate": mk.get("isAlternate"),
                    "designations": [p.get("designation") for p in (mk.get("prices") or [])],
                    "prices": [p.get("price") for p in (mk.get("prices") or [])],
                    "isLive": mk.get("isLive"), "status": mk.get("status"),
                })
        return {"id": m.get("id"), "league": (m.get("league") or {}).get("name"),
                "type": m.get("type"), "special": bool(m.get("special")),
                "status": m.get("status"), "isLive": m.get("isLive"),
                "startTime": m.get("startTime"),
                "participants": [p.get("name") for p in (m.get("participants") or [])],
                "matchup_periods": m.get("periods"),
                "parentId": m.get("parentId"), "totalMarketCount": m.get("totalMarketCount"),
                "markets_http": st2, "markets": rows}

    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        inv["samples"] = list(pool.map(one, sample))
    with open(os.path.join(OUT, "pinnacle_markets_inventory.json"), "w", encoding="utf-8") as fh:
        json.dump(inv, fh, indent=1, ensure_ascii=False)
    for s in inv["samples"]:
        money = [r for r in s["markets"] if r["type"] == "moneyline"]
        print(f"{s['id']} {s['participants']} periods={s['matchup_periods']} "
              f"moneylines={[(r['period'], r['key'], r['designations'], r['prices']) for r in money]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
