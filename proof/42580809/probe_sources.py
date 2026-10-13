#!/usr/bin/env python3
"""
Session 42580809 — external source reachability probe.

Purpose: find every *public* endpoint a GitHub runner can read that carries
CS2 match-winner (moneyline) prices, so the HotSpawn pick'em fixtures can be
priced from outside sources instead of being left blank.

The probe only performs GET requests against public URLs, records the HTTP status,
the byte count, a content hash and a short inert snippet of the body. Nothing is
authenticated, nothing is bypassed, nothing is written back to any source.

Output: out/probe.json  (+ raw/ mirrors for the endpoints that answered 200)
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RAW = os.path.join(OUT, "raw")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

# (key, url, extra headers)
TARGETS = [
    ("pinnacle_esports_matchups",
     "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("pinnacle_esports_leagues",
     "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("bovada_esports_coupon",
     "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports", {}),
    ("kambi_betrivers_listview",
     "https://eu-offering-api.kambicdn.com/offering/v2018/betriversus/listView/esports.json?lang=en_US&market=US",
     {}),
    ("kambi_unibet_esports_all",
     "https://eu-offering-api.kambicdn.com/offering/v2018/ubse/esports/all/all/matches.json?lang=en_GB&market=GB",
     {}),
    ("kambi_888_listview",
     "https://eu-offering-api.kambicdn.com/offering/v2018/888sports/listView/esports.json?lang=en_GB&market=GB",
     {}),
    ("thunderpick_api_v1",
     "https://api.thunderpick.io/api/v1/esports/matches", {}),
    ("thunderpick_www_api",
     "https://thunderpick.io/api/v2/esports/cs2/matches", {}),
    ("egamersworld_cs2_matches",
     "https://egamersworld.com/counterstrike/matches", {}),
    ("egamersworld_api_upcoming",
     "https://egamersworld.com/api/v1/matches?game=counterstrike&status=upcoming&limit=100", {}),
    ("bo3gg_upcoming",
     "https://bo3.gg/api/v1/matches?scope=upcoming&page=1&per_page=100&site_id=1&sort=start_date_asc",
     {}),
    ("bo3gg_matches_alt",
     "https://api.bo3.gg/api/v1/matches?scope=upcoming&page=1&per_page=100&site_id=1", {}),
    ("hltv_matches", "https://www.hltv.org/matches", {}),
    ("hltv_betting_analytics", "https://www.hltv.org/betting/analytics", {}),
    ("oddspedia_cs_list",
     "https://oddspedia.com/api/v1/getMatchList?excludeExchanges=1&sport=counter-strike&status=all&sortBy=default&language=en",
     {}),
    ("betexplorer_next_esports", "https://www.betexplorer.com/next/esports/", {}),
    ("oddsportal_cs2", "https://www.oddsportal.com/esports/counter-strike/", {}),
    ("kalshi_events_open",
     "https://api.elections.kalshi.com/trade-api/v2/events?status=open&limit=200", {}),
    ("kalshi_markets_cs2",
     "https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=200&series_ticker=KXCS2GAME",
     {}),
    ("polymarket_esports_events",
     "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=esports", {}),
    ("polymarket_cs2_events",
     "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike", {}),
    ("onexbet_linefeed_esports",
     "https://1xbet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=50&lng=en&mode=4&country=1",
     {}),
    ("betway_esports_api",
     "https://betway.com/api/esports/events?country=GB&language=en", {}),
    ("strafe_cs2_upcoming", "https://api.strafe.com/v2/match/upcoming/csgo/", {}),
    ("liquipedia_cs2_api",
     "https://liquipedia.net/counterstrike/api.php?action=query&format=json&list=search&srsearch=HotSpawn", {}),
    ("valve_vrs_global_current",
     "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026/standings_global_2026_10_05.md",
     {}),
    ("valve_vrs_repo_contents",
     "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026", {}),
    ("esports_api_abios_public",
     "https://api.abiosgaming.com/v2/series?filter[game]=cs2", {}),
    ("draftkings_esports_group",
     "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/15000", {}),
    ("ggbet_api_esports", "https://gg.bet/api/line/esports", {}),
    ("smarkets_esports_api",
     "https://api.smarkets.com/v3/events/?type=counter-strike-2&sort=start_datetime,id&limit=100", {}),
    ("hyperino_esports", "https://www.hyperino.com/api/esports/matches", {}),
    ("pinnacle_csgo_specific_sport",
     "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups?withSpecials=false",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("hltv_ranking", "https://www.hltv.org/ranking/teams/2026/october/6", {}),
    ("esportcharts_cs2", "https://esportcharts.com/api/cs2/matches", {}),
    ("esportsodds_hltv_cs2", "https://www.esportsodds.com/cs2", {}),
]


def fetch(item):
    key, url, extra = item
    headers = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    headers.update(extra)
    rec = {"key": key, "url": url, "status": None, "bytes": None, "sha256": None,
           "content_type": None, "error": None, "snippet": None, "saved": None}
    try:
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
            body = resp.read()
            rec["status"] = resp.status
            rec["content_type"] = resp.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        rec["status"] = exc.code
        rec["content_type"] = exc.headers.get("Content-Type") if exc.headers else None
    except Exception as exc:  # noqa: BLE001 - record every failure mode verbatim
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec
    rec["bytes"] = len(body)
    rec["sha256"] = hashlib.sha256(body).hexdigest()
    text = body[:4000].decode("utf-8", "replace")
    rec["snippet"] = text[:1200].replace("\n", " ")[:1200]
    if rec["status"] == 200 and len(body) > 0:
        os.makedirs(RAW, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:60]
        ext = "json" if (text.lstrip()[:1] in "[{" and "json" in (rec["content_type"] or "")) else "txt"
        path = os.path.join(RAW, f"{safe}.{ext}")
        with open(path, "wb") as fh:
            fh.write(body[:8_000_000])
        rec["saved"] = os.path.relpath(path, OUT)
    return rec


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(fetch, TARGETS))
    summary = {
        "probe_utc": __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runner": os.environ.get("RUNNER_NAME"),
        "github_run": os.environ.get("GITHUB_RUN_ID"),
        "reachable_200": sorted(r["key"] for r in results if r["status"] == 200),
        "blocked": {r["key"]: (r["status"] or r["error"]) for r in results if r["status"] != 200},
        "results": results,
    }
    with open(os.path.join(OUT, "probe.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    print("REACHABLE 200:", json.dumps(summary["reachable_200"], indent=1))
    print("BLOCKED:", json.dumps(summary["blocked"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
