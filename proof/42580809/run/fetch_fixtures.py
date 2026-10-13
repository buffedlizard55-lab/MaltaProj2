#!/usr/bin/env python3
"""
Runner task — HotSpawn Pick'ems fixture inventory.

Reverse-engineered source (public, unauthenticated):
  lobby page   https://play.hotspawn.com/lobby
  JSON API     https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures

The lobby page only server-renders the next handful of cards, so the API response is the
complete source of everything the pick'em game can currently offer. The API payload itself
is never stored wholesale (11k+ historical rows); its size and SHA-256 are recorded, and the
unmodified rows for the current pick'em window are kept as evidence.

Window rule (identical to the rule this repo already publishes):
  drop a fixture only when status == "ended"; also drop non-live rows whose scheduled start
  is older than 24 h. Nothing is ever invented.

Outputs (committed back to the session branch, see proof/42580809/evidence/):
  fixtures.json            - normalised pick'em window + counts + evidence
  fixtures_raw_window.json - unmodified API rows for the same fixtures
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "evidence"))
API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
LOBBIES = ["https://play.hotspawn.com/lobby"]
UA = "MaltaProj2-research/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)"
LIVE_STATUSES = {"upcoming", "live", "open", "pending", "scheduled"}


def get(url: str, timeout: int = 90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), (resp.headers.get("Date") or "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), (exc.headers.get("Date") if exc.headers else "") or ""
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}".encode(), ""


def ms_iso(value):
    if value in (None, "", "0"):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def write(rel: str, obj) -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, rel), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, sort_keys=False)


def main() -> int:
    now = datetime.now(tz=timezone.utc)
    evidence = {"collected_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "endpoints": {}}

    st, body, date_hdr = get(API + "/fixtures")
    evidence["endpoints"]["GET " + API + "/fixtures"] = {
        "status": st, "bytes": len(body), "response_date_header": date_hdr}

    lobby_snapshots = {}
    for url in LOBBIES:
        st2, body2, date2 = get(url, timeout=60)
        evidence["endpoints"]["GET " + url] = {"status": st2, "bytes": len(body2),
                                               "response_date_header": date2}
        if st2 == 200:
            text = body2.decode("utf-8", "replace")
            lobby_snapshots[url] = {
                "bytes": len(text),
                "sha256": hashlib.sha256(body2).hexdigest(),
                "has_ng_state": "ng-state" in text,
                "script_tag_count": text.count("<script"),
            }
    evidence["lobby_snapshots"] = lobby_snapshots

    if st != 200:
        write("fixtures.json", {"error": "fixtures endpoint unreachable", "evidence": evidence})
        return 1

    fixtures = json.loads(body.decode("utf-8", "replace"))
    evidence["fixtures_api"] = {"count": len(fixtures),
                                "sha256": hashlib.sha256(body).hexdigest(),
                                "bytes": len(body)}

    now_ms = int(now.timestamp() * 1000)
    window = []
    for f in fixtures:
        status_l = str(f.get("status", "")).lower()
        try:
            sched_ms = int(f.get("scheduled_start_time"))
        except (TypeError, ValueError):
            sched_ms = None
        if status_l == "ended":
            continue
        if sched_ms is not None and sched_ms < now_ms - 24 * 3600 * 1000 and status_l not in LIVE_STATUSES:
            continue
        window.append(f)
    window.sort(key=lambda f: int(f.get("scheduled_start_time") or 0))

    rows = []
    for f in window:
        rows.append({
            "fixture_id": str(f.get("id")),
            "competition_id": str(f.get("competition_id")) if f.get("competition_id") is not None else None,
            "competition_name": f.get("competition_name"),
            "sport": f.get("sport_alias"),
            "sport_name": f.get("sport_name"),
            "status": f.get("status"),
            "tier": f.get("tier") or None,
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "series_format": f.get("series_format"),
            "scheduled_start_time_utc": ms_iso(f.get("scheduled_start_time")),
            "lock_time_utc": ms_iso(f.get("lock_time")),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "offered_points": f.get("offered_points"),
            "base_points": f.get("base_points"),
            "total_picks": f.get("total_picks"),
            "team_a_id": str(f.get("participants0_id")) if f.get("participants0_id") is not None else None,
            "team_a": f.get("participants0_name"),
            "team_a_pick_pct": f.get("participants0_picked_percent"),
            "team_b_id": str(f.get("participants1_id")) if f.get("participants1_id") is not None else None,
            "team_b": f.get("participants1_name"),
            "team_b_pick_pct": f.get("participants1_picked_percent"),
            "source_url": f"https://www.hotspawn.com/matches/{f.get('id')}",
            "source_api_url": API + "/fixtures",
        })

    by_sport: dict[str, int] = {}
    for r in rows:
        by_sport[r["sport"] or "unknown"] = by_sport.get(r["sport"] or "unknown", 0) + 1

    keep_ids = {r["fixture_id"] for r in rows}
    write("fixtures_raw_window.json", {
        "collected_at_utc": evidence["collected_at_utc"],
        "source": API + "/fixtures",
        "note": "unmodified API rows for every fixture in the normalised window",
        "count": len([f for f in fixtures if str(f.get("id")) in keep_ids]),
        "fixtures": [f for f in fixtures if str(f.get("id")) in keep_ids],
    })
    write("fixtures.json", {
        "collected_at_utc": evidence["collected_at_utc"],
        "source_api": API + "/fixtures",
        "source_page": "https://play.hotspawn.com/lobby",
        "note": ("HotSpawn is fixture discovery only. participantsX_picked_percent is a player "
                 "pick percentage, never used as a probability."),
        "counts": {"api_total": len(fixtures), "window": len(rows), "by_sport": by_sport},
        "evidence": evidence,
        "fixtures": rows,
    })
    print(f"fixtures: api_total={len(fixtures)} window={len(rows)} by_sport={by_sport}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
