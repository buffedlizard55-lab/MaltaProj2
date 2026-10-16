#!/usr/bin/env python3
"""Fresh-capture collector for session 1c8f79f8 (day-4 desk).

Runs on GitHub Actions (unrestricted egress). Captures the HotSpawn
fixtures API per competition_id — the only filter parameter the API
accepts besides sport_alias/status (from/limit/tier are rejected with
400 "property should not exist") — and retains the raw JSON as evidence
before any derivation happens.

The API's status=scheduled filter is known to include stale past-dated
rows (verified 2026-10-16: rows with Oct 13-16 starts still return
"scheduled"), so this collector applies the client-side time filter
itself and records what it dropped.

Usage:
    python scripts/1c8f79f8/collect.py            # capture + verify
    python scripts/1c8f79f8/collect.py --check    # verify committed capture only

Outputs:
    data/1c8f79f8/evidence/fixtures_api_<competition_id>.json  (raw, verbatim)
    data/1c8f79f8/fixtures_raw.json                            (merged + time filter)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "1c8f79f8"
EVIDENCE = DATA / "evidence"
API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"

# Competition IDs enumerated from the live lobby + fixtures API on
# 2026-10-16. The TWC Malta playoffs are deliberately absent: the API
# has no Thunderpick World Championship (Malta) competition, which is
# itself the verification that those matches are not HotSpawn-listed.
COMPETITIONS = {
    36197: "Stake Pulse Beat III",
    36038: "NODWIN Clutch Series #13",
    34962: "PGL Bucharest 2027: Closed Qualifier",
    35827: "CCT Europe 2026 Challengers #8",
    34938: "CCT Europe 2026 Series #12 Play-In",
    35437: "Digital Crusade DraculaN Season 7",
    36412: "MaceMedia VOID Autumn Cup 2026",
    # stale-linger watchlist rows (past-dated but still 'scheduled')
    33804: "Thunderpick World Championship 2026 South African Series #1",
    35813: "CCT Europe 2026 Series #11",
    35434: "CCT Europe 2026 Challengers #4",
    35430: "CCT South America 2026 Series 3",
    35419: "ESL Pro League Season 8",
    35005: "ESL Pro League Season 8 Play-In",
    35439: "Svenska CS-Ligan",
    35440: "LG UltraGear Tournament",
    35441: "Rainhas do Clutch",
    35435: "Urban Riga Open #5",
}

LOCK_OFFSET_MS = 360_000  # lock_time = scheduled_start_time - 360000 ms (verified)


def fetch(competition_id: int) -> dict:
    url = f"{API}?sport_alias=cs2&status=scheduled&competition_id={competition_id}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def ms_to_utc(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def capture(now_utc: str) -> dict:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    merged = []
    meta = {"captured_utc": now_utc, "api": API, "competitions": {}}
    for comp_id, comp_name in COMPETITIONS.items():
        payload = fetch(comp_id)
        # retain the verbatim response as evidence before any filtering
        (EVIDENCE / f"fixtures_api_{comp_id}.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        rows = payload if isinstance(payload, list) else payload.get("fixtures", [])
        kept, dropped = [], []
        for row in rows:
            start_ms = int(row["scheduled_start_time"])
            if start_ms < int(time.time() * 1000) - LOCK_OFFSET_MS:
                dropped.append({"id": row["id"], "start_utc": ms_to_utc(start_ms),
                                "reason": "past_start_stale_scheduled_row"})
            else:
                kept.append(row)
        meta["competitions"][str(comp_id)] = {
            "name": comp_name, "rows_returned": len(rows),
            "rows_kept": len(kept), "stale_rows_dropped": dropped,
        }
        merged.extend(kept)
    return {"meta": meta, "fixtures": merged}


def verify(raw: dict) -> list[str]:
    problems = []
    for row in raw["fixtures"]:
        if int(row["lock_time"]) != int(row["scheduled_start_time"]) - LOCK_OFFSET_MS:
            problems.append(f"{row['id']}: lock_time offset != 360000 ms")
        crowd_sum = row["participants0_picked_percent"] + row["participants1_picked_percent"]
        if crowd_sum not in (99, 100, 101):
            problems.append(f"{row['id']}: crowd percentages sum to {crowd_sum}, not 100 (API rounding)")
        if row["sport_alias"] != "cs2" or row["status"] != "scheduled":
            problems.append(f"{row['id']}: unexpected sport/status")
    return problems


def main(check_only: bool = False) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    if check_only:
        raw = json.loads((DATA / "fixtures_raw.json").read_text())
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = capture(now)
        (DATA / "fixtures_raw.json").write_text(
            json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
    problems = verify(raw)
    print(f"fixtures retained: {len(raw['fixtures'])}")
    for comp_id, info in raw["meta"]["competitions"].items():
        print(f"  competition {comp_id} ({info['rows_kept']} open"
              f"{', ' + str(len(info['stale_rows_dropped'])) + ' stale dropped' if info['stale_rows_dropped'] else ''})")
    if problems:
        print("VERIFICATION PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print("capture self-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(check_only="--check" in sys.argv))
