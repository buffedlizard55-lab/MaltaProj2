#!/usr/bin/env python3
"""Fetch the official Valve CS2 Regional Standings (VRS) and retain a parsed snapshot.

Session 6c5bb3d6 scope: writes only data/6c5bb3d6/vrs_official.json.

The standings are Valve's own published file, read through the GitHub contents API
(api.github.com is reachable from both the sandbox and hosted runners). Fails closed:
a non-200 response or an implausible parse retains the previous snapshot and reports
the failure, it never invents ratings.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

SNAPSHOT = "standings_global_2026_10_05.md"
API_URL = (
    "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings"
    f"/contents/live/2026/{SNAPSHOT}"
)
HUMAN_URL = (
    "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main"
    f"/live/2026/{SNAPSHOT}"
)
RAW_URL = (
    "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings"
    f"/main/live/2026/{SNAPSHOT}"
)
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "6c5bb3d6", "vrs_official.json")
MIN_TEAMS = 100

ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*(?:\[details\]\(([^)]*)\))?\s*\|?\s*$")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, timeout: int = 45) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.raw",
        "User-Agent": "maltaproj2-verify-6c5bb3d6 (independent source verification)",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        return 0, f"{type(exc).__name__}: {exc}"


def parse(text: str) -> dict:
    teams: dict[str, dict] = {}
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        standing, points, name, roster, details = m.groups()
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if not key or key in ("teamname",):
            continue
        teams[key] = {
            "team": name.strip(),
            "standing": int(standing),
            "points": int(points),
            "roster": [p.strip() for p in roster.split(",") if p.strip()],
            "details_path": (details or "").strip() or None,
        }
    return teams


def main() -> int:
    out = os.path.abspath(OUT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    status, body = fetch(API_URL)
    teams = parse(body) if status == 200 else {}
    record = {
        "session": "6c5bb3d6",
        "fetched_utc": utcnow(),
        "source": "ValveSoftware/counter-strike_regional_standings (official Valve publication)",
        "snapshot": "2026_10_05",
        "api_url": API_URL,
        "human_url": HUMAN_URL,
        "raw_url": RAW_URL,
        "http_status": status,
        "bytes": len(body.encode("utf-8")) if status == 200 else 0,
        "teams_parsed": len(teams),
        "error": None if status == 200 else body[:400],
        "teams": teams,
    }
    prior = None
    if os.path.exists(out):
        try:
            prior = json.load(open(out, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prior = None
    if status != 200 or len(teams) < MIN_TEAMS:
        if prior and prior.get("teams"):
            record = prior
            record["refetch_attempt_utc"] = utcnow()
            record["refetch_error"] = record.get("error") or f"only {len(teams)} teams parsed"
            record["refetch_http_status"] = status
            json.dump(record, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"RETAINED prior official VRS snapshot ({len(prior['teams'])} teams); "
                  f"live fetch failed (status {status})")
            return 1
        print(f"FATAL: official VRS fetch failed (status {status}) and no prior snapshot exists", file=sys.stderr)
        return 2
    json.dump(record, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"official VRS snapshot {record['snapshot']}: {len(teams)} teams parsed "
          f"(HTTP {status}) -> {os.path.relpath(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
