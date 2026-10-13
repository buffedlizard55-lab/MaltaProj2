#!/usr/bin/env python3
"""Dump raw (trimmed) JSON samples from each external source so the field names and market
structures can be verified instead of guessed. Evidence only — never used for values."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "X-Device-UUID": str(uuid.uuid4()), "Referer": "https://www.pinnacle.com/"}


def fetch_json(url, headers=None, timeout=60):
    hdrs = {"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def save(name, obj):
    path = os.path.join(ROOT, "evidence", "raw_samples", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    return path


def main() -> int:
    out = {"generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    st, leagues = fetch_json(f"{PIN}/sports/12/leagues", PIN_HEADERS)
    cs = [l for l in (leagues or []) if "counter" in str(l.get("name", "")).lower()]
    out["pinnacle_cs2_leagues"] = cs
    sample_matchups = None
    if cs:
        st2, matchups = fetch_json(f"{PIN}/leagues/{cs[0]['id']}/matchups", PIN_HEADERS)
        out["pinnacle_matchups_status"] = st2
        out["pinnacle_matchup_sample"] = (matchups or [{}])[0]
        sample_matchups = matchups
        mid = (matchups or [{}])[0].get("id")
        if mid:
            st3, markets = fetch_json(f"{PIN}/matchups/{mid}/markets/related/straight", PIN_HEADERS)
            out["pinnacle_markets_url"] = f"{PIN}/matchups/{mid}/markets/related/straight"
            out["pinnacle_markets_status"] = st3
            # keep every market type/period combination observed, full price objects
            out["pinnacle_markets_sample"] = markets

    st4, bov = fetch_json("https://www.bovada.lv/services/sports/event/v2/events/A/description/esports")
    out["bovada_status"] = st4
    if isinstance(bov, list):
        out["bovada_group_descriptions"] = [g.get("description") for g in bov][:30]
        ev = None
        for g in bov:
            for e in (g.get("events") or []):
                desc = " ".join(str(c.get("name", "")) for c in (e.get("competitors") or []))
                if e.get("displayGroups"):
                    ev = e
                    break
            if ev:
                break
        out["bovada_event_sample"] = ev
        # path/category listing
        out["bovada_link_sample"] = (bov[0].get("events") or [{}])[0].get("link") if bov else None

    st5, pm = fetch_json("https://gamma-api.polymarket.com/public-search?q=Falcons&limit_per_type=3")
    out["polymarket_search_status"] = st5
    out["polymarket_search_sample"] = (pm or {}) if not isinstance(pm, list) else pm[:2]
    st6, pm2 = fetch_json("https://gamma-api.polymarket.com/events?closed=false&limit=5&tag_slug=esports")
    out["polymarket_events_status"] = st6
    out["polymarket_event_sample"] = (pm2 or [{}])[0] if isinstance(pm2, list) else pm2
    save("raw_samples.json", out)
    print("raw samples saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
