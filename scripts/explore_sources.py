#!/usr/bin/env python3
"""Multi-source exploration: find which external betting-line sources are usable and how
their data is shaped. Writes one evidence file per source under evidence/."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "X-Device-UUID": str(uuid.uuid4()),
}


def fetch(url, headers=None, timeout=45):
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, {}, str(exc).encode()


def save(name, obj):
    path = os.path.join(ROOT, "evidence", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    return path


def probe_pinnacle():
    st, hdrs, body = fetch(f"{PIN}/sports", PIN_HEADERS)
    out = {"generated_at_utc": now(), "endpoint": f"{PIN}/sports", "status": st,
           "sports": [], "esports_candidates": [], "league_probe": [], "matchup_probe": []}
    if st == 200:
        try:
            sports = json.loads(body)
            out["sports"] = [{"id": s.get("id"), "name": s.get("name"),
                              "isHidden": s.get("isHidden"),
                              "matchupCount": s.get("matchupCount")} for s in sports]
            out["esports_candidates"] = [s for s in out["sports"]
                                         if "esport" in str(s.get("name", "")).lower()
                                         or "counter" in str(s.get("name", "")).lower()]
        except Exception as exc:  # noqa: BLE001
            out["parse_error"] = str(exc)
            out["body_preview"] = body[:400].decode("utf-8", "replace")
    # try a few likely esports sport ids even if hidden
    for sid in list({s["id"] for s in out["esports_candidates"]}) + [33, 36, 37]:
        st2, _, b2 = fetch(f"{PIN}/sports/{sid}/leagues", PIN_HEADERS)
        entry = {"sport_id": sid, "leagues_status": st2}
        try:
            leagues = json.loads(b2)
            entry["league_count"] = len(leagues)
            entry["names"] = [l.get("name") for l in leagues][:25]
            entry["counter_strike"] = [{"id": l.get("id"), "name": l.get("name"),
                                        "matchupCount": l.get("matchupCount")}
                                       for l in leagues
                                       if "counter" in str(l.get("name", "")).lower()]
        except Exception:
            entry["body_preview"] = b2[:200].decode("utf-8", "replace")
        out["league_probe"].append(entry)
        time.sleep(0.2)
    # cluster/baseball-style direct matchup probe on esports sport ids
    for sid in [33, 36, 37]:
        st3, _, b3 = fetch(f"{PIN}/sports/{sid}/matchups", PIN_HEADERS)
        out["matchup_probe"].append({"sport_id": sid, "status": st3,
                                     "bytes": len(b3),
                                     "preview": b3[:300].decode("utf-8", "replace")})
        time.sleep(0.2)
    return save("pinnacle_sports_probe.json", out)


def probe_polymarket():
    out = {"generated_at_utc": now(), "samples": []}
    urls = [
        "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike",
        "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=esports",
        "https://gamma-api.polymarket.com/public-search?q=counter-strike&limit_per_type=10",
    ]
    for u in urls:
        st, hdrs, body = fetch(u)
        entry = {"url": u, "status": st, "bytes": len(body),
                 "preview": body[:500].decode("utf-8", "replace")}
        if st == 200:
            try:
                data = json.loads(body)
                if isinstance(data, list):
                    entry["count"] = len(data)
                    entry["titles"] = [d.get("title") for d in data[:40]]
                    entry["sample_keys"] = sorted(data[0].keys()) if data else []
                elif isinstance(data, dict):
                    entry["keys"] = sorted(data.keys())
                    entry["count"] = len(data.get("events", []) or data.get("markets", []) or [])
                    entry["titles"] = [d.get("title") for d in (data.get("events") or [])[:20]]
            except Exception as exc:  # noqa: BLE001
                entry["parse_error"] = str(exc)
        out["samples"].append(entry)
        time.sleep(0.3)
    return save("polymarket_probe.json", out)


def probe_html_variants():
    targets = {
        "betexplorer_cs": ["https://www.betexplorer.com/counter-strike/",
                           "https://www.betexplorer.com/esports/counter-strike/",
                           "https://www.betexplorer.com/csgo/",
                           "https://www.betexplorer.com/"],
        "oddspedia": ["https://oddspedia.com/esports", "https://oddspedia.com/counter-strike",
                      "https://oddspedia.com/esports/counter-strike/"],
        "bo3gg": ["https://bo3.gg/matches/", "https://bo3.gg/cs2/matches"],
        "egamersworld": ["https://egamersworld.com/counterstrike/matches",
                         "https://egamersworld.com/cs2/matches"],
        "flashscore_esports": ["https://www.flashscore.com/esports/"],
        "sportsbook_cloudbet": ["https://www.cloudbet.com/en/sports/esports"],
        "sportsbook_bovada": ["https://www.bovada.lv/sports/esports"],
        "kalshi": ["https://api.elections.kalshi.com/trade-api/v2/events?limit=5"],
    }
    out = {"generated_at_utc": now(), "targets": {}}
    for key, urls in targets.items():
        rows = []
        for u in urls:
            st, hdrs, body = fetch(u)
            text = body.decode("utf-8", "replace")
            rows.append({
                "url": u, "status": st, "bytes": len(body),
                "content_type": hdrs.get("Content-Type"),
                "cf_mitigated": hdrs.get("cf-mitigated"),
                "login_wall": bool(re.search(r"sign in|log in|login", text[:20000], re.I)),
                "odds_like_tokens": len(re.findall(r"\b\d\.\d{2}\b", text)),
                "preview": text[:300],
            })
            time.sleep(0.4)
        out["targets"][key] = rows
    return save("html_source_probe.json", out)


def now():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    print(probe_pinnacle())
    print(probe_polymarket())
    print(probe_html_variants())
    return 0


if __name__ == "__main__":
    sys.exit(main())
