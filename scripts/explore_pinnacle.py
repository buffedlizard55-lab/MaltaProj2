#!/usr/bin/env python3
"""
Pinnacle (guest API) explorer + extractor.

Pinnacle is a licensed bookmaker that publishes machine-readable decimal odds through its
public guest API. We use it as the primary external line source because it is a real
bookmaker (not a pick'em site) and it exposes the exact numbers plus the exact public URL
the numbers came from.

Evidence written to:
  evidence/pinnacle_probe.json   - structure/reachability diagnostics
  data/pinnacle_matchups.json    - trimmed CS2 matchups + moneyline prices seen this run
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
DEVICE = str(uuid.uuid4())
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "X-Device-UUID": DEVICE,
}


def get(path, timeout=45, headers=None):
    url = path if path.startswith("http") else BASE + path
    hdrs = dict(HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace")), url
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        return exc.code, {"error_body": body}, url
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}, url


def main() -> int:
    probe = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_base": BASE,
        "device_uuid": DEVICE,
        "steps": [],
    }

    st, sports, url = get("/sports")
    probe["steps"].append({"step": "sports", "url": url, "status": st, "count": len(sports) if isinstance(sports, list) else None})
    esports = [s for s in sports if isinstance(s, dict) and "esport" in str(s.get("name", "")).lower()] if isinstance(sports, list) else []
    probe["esports_sport_rows"] = esports
    if not esports:
        _write(probe, None)
        return 0
    sport_id = esports[0]["id"]

    st, leagues, url = get(f"/sports/{sport_id}/leagues")
    cs2_leagues = [l for l in leagues if isinstance(l, dict) and "counter" in str(l.get("name", "")).lower()] if isinstance(leagues, list) else []
    probe["steps"].append({"step": "leagues", "url": url, "status": st,
                           "count": len(leagues) if isinstance(leagues, list) else None,
                           "cs2_leagues": len(cs2_leagues)})
    probe["cs2_league_names"] = sorted({l.get("name") for l in cs2_leagues})
    probe["all_league_count_sample"] = [{"id": l.get("id"), "name": l.get("name"), "matchupCount": l.get("matchupCount")} for l in (leagues or [])[:40]]

    matchups = []
    for league in cs2_leagues[:40]:
        if not league.get("matchupCount"):
            continue
        st2, rows, u2 = get(f"/leagues/{league['id']}/matchups")
        if isinstance(rows, list):
            for m in rows:
                m["_league_name"] = league.get("name")
                m["_league_id"] = league.get("id")
            matchups.extend(rows)
        probe["steps"].append({"step": "league_matchups", "url": u2, "status": st2,
                               "count": len(rows) if isinstance(rows, list) else None,
                               "league": league.get("name")})
        time.sleep(0.3)

    trimmed = []
    for m in matchups:
        parts = m.get("participants") or []
        trimmed.append({
            "matchup_id": str(m.get("id")),
            "league": m.get("_league_name"),
            "league_id": str(m.get("_league_id")),
            "start_time": m.get("startTime"),
            "status": m.get("status"),
            "type": m.get("type"),
            "participants": [p.get("name") for p in parts],
            "participant_ids": [str(p.get("id")) for p in parts],
            "public_url": f"https://www.pinnacle.com/en/esports/{m.get('_league_name')}".replace(" ", "-").lower() if m.get("_league_name") else None,
        })

    # moneyline for the first few upcoming matchups (evidences price shape)
    price_samples = []
    for m in trimmed[:6]:
        st3, markets, u3 = get(f"/matchups/{m['matchup_id']}/markets/related/straight")
        price_samples.append({"matchup_id": m["matchup_id"], "url": u3, "status": st3,
                              "markets": markets if isinstance(markets, list) else markets})
        time.sleep(0.3)
    probe["price_samples"] = price_samples

    _write(probe, {"generated_at_utc": probe["generated_at_utc"], "source": "pinnacle",
                   "api_base": BASE, "matchup_count": len(trimmed), "matchups": trimmed})
    print(f"pinnacle cs2 matchups: {len(trimmed)}; price samples: {len(price_samples)}")
    return 0


def _write(probe, matchup_doc):
    ev = os.path.join(ROOT, "evidence", "pinnacle_probe.json")
    os.makedirs(os.path.dirname(ev), exist_ok=True)
    with open(ev, "w", encoding="utf-8") as fh:
        json.dump(probe, fh, indent=1, ensure_ascii=False)
    if matchup_doc:
        out = os.path.join(ROOT, "data", "pinnacle_matchups.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(matchup_doc, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
