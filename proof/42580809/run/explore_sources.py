#!/usr/bin/env python3
"""
Runner task — find public endpoints that carry CS2 match-winner (moneyline) prices.

The pick'em lobby is dominated by tier-2/tier-3 tournaments (CCT Europe Series #11/#12,
DraculaN, Urban Riga Open, Svenska CS-Ligan, Rainhas do Clutch, ESL Challenger League cups).
Covering them needs books that price low-tier CS2, so this task probes candidate endpoints
with ordinary browser headers and reports, per endpoint, whether the payload contains
counter-strike fixtures and moneyline prices.

Nothing is authenticated, no challenge is solved or bypassed, and no source is modified.
Output: evidence/sources.json  (compact per-endpoint analysis + tiny raw samples)
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "evidence"))
SAMPLES = os.path.join(OUT, "samples")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

CS2_RE = re.compile(r"(counter[- ]?strike|cs2|cs:go|csgo|counterstrike)", re.I)
ODDS_KEY_RE = re.compile(r'"(odds|price|decimal|moneyline|betOffer|bet_offer|prices|'
                         r'homeOdds|awayOdds|oddsHome|oddsAway|coefficient|k[12])"\s*:', re.I)

KAMBI = "https://eu-offering-api.kambicdn.com/offering/v2018/{tenant}/esports/all/all/matches.json?lang={lang}&market={market}"

# (key, url, extra headers)
CANDIDATES = [
    # --- Kambi-powered licensed books (broad CS2 depth, incl. low tier) ---
    ("kambi_betriversus", KAMBI.format(tenant="betriversus", lang="en_US", market="US"), {}),
    ("kambi_betrivers", KAMBI.format(tenant="betrivers", lang="en_US", market="US"), {}),
    ("kambi_ubuk", KAMBI.format(tenant="ubuk", lang="en_GB", market="GB"), {}),
    ("kambi_ubse", KAMBI.format(tenant="ubse", lang="en_GB", market="SE"), {}),
    ("kambi_ubfr", KAMBI.format(tenant="ubfr", lang="fr_FR", market="FR"), {}),
    ("kambi_nordicbet", KAMBI.format(tenant="nordicbet", lang="en_GB", market="MT"), {}),
    ("kambi_betsson", KAMBI.format(tenant="betsson", lang="en_GB", market="MT"), {}),
    ("kambi_coolbet", KAMBI.format(tenant="coolbet", lang="en_GB", market="EE"), {}),
    ("kambi_otonl", KAMBI.format(tenant="otonl", lang="nl_NL", market="NL"), {}),
    ("kambi_bethard", KAMBI.format(tenant="bethard", lang="en_GB", market="MT"), {}),
    # --- Pinnacle ---
    ("pinnacle_sports", "https://guest.api.arcadia.pinnacle.com/0.1/sports",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("pinnacle_esports_leagues", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("pinnacle_esports_matchups", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    # --- bo3.gg (CS2-focused, publishes bookmaker odds per match) ---
    ("bo3gg_site_matches", "https://bo3.gg/matches", {"Accept": "text/html"}),
    ("bo3gg_site_cs2", "https://bo3.gg/matches?game=cs2", {"Accept": "text/html"}),
    ("bo3gg_api_upcoming_nostatus", "https://api.bo3.gg/api/v1/matches?page=1&per_page=50&site_id=1", {}),
    ("bo3gg_api_filter", "https://api.bo3.gg/api/v1/matches?filter=upcoming&page=1&per_page=50&site_id=1", {}),
    ("bo3gg_api_discipline", "https://api.bo3.gg/api/v1/matches?discipline_id=1&page=1&per_page=50&site_id=1", {}),
    ("bo3gg_api_teams", "https://api.bo3.gg/api/v1/teams?page=1&per_page=5&site_id=1", {}),
    # --- other licensed books / feeds ---
    ("bovada_esports", "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports", {}),
    ("draftkings_esports_json", "https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/15000?format=json",
     {"Accept": "application/json"}),
    ("draftkings_esports_html", "https://sportsbook.draftkings.com/leagues/esports",
     {"Accept": "text/html"}),
    ("fanduel_esports", "https://sportsbook.fanduel.com/api/content-managed-page"
                        "?page=CUSTOM&customPageId=esports&_ak=FhMFpcPWXMeyZxOx", {}),
    ("betmgm_esports", "https://www.betmgm.com/en/sports/esports-33", {"Accept": "text/html"}),
    ("caesars_esports", "https://sportsbook.caesars.com/us/az/sports/esports",
     {"Accept": "text/html"}),
    ("tipico_esports", "https://sportsbook.tipico.de/en/sports/esports", {"Accept": "text/html"}),
    ("marathonbet_esports", "https://www.marathonbet.com/en/betting/Esports/",
     {"Accept": "text/html"}),
    ("betano_esports", "https://www.betano.com/sport/esports/", {"Accept": "text/html"}),
    ("onexbet_linefeed", "https://1xbet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=500"
                         "&lng=en&mode=4&country=1&virtualSports=true&noFilterBlockEvent=true", {}),
    ("onexbet_linefeed_alt", "https://1xbet.com/LineFeed/Get1x2_VZip?sports=3&count=500&lng=en", {}),
    ("thunderpick_api", "https://api.thunderpick.io/api/v1/esports/matches", {}),
    ("thunderpick_site", "https://thunderpick.io/esports/cs2-betting", {"Accept": "text/html"}),
    ("ggbet_site", "https://gg.bet/en/esports", {"Accept": "text/html"}),
    ("betway_esports", "https://sports.betway.com/en/sports/grp/esports",
     {"Accept": "text/html"}),
    ("oddspedia_esports", "https://oddspedia.com/esports", {"Accept": "text/html"}),
    ("oddsportal_cs2", "https://www.oddsportal.com/esports/counter-strike/",
     {"Accept": "text/html"}),
    ("esportsbet_api", "https://www.esportsbet.io/api/v1/matches", {}),
    ("kalshi_cs2", "https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=200&series_ticker=KXCS2GAME", {}),
    ("polymarket_cs2", "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike", {}),
    # --- reference data (rated teams, form) ---
    ("valve_vrs_global_1005",
     "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026/standings_global_2026_10_05.md",
     {}),
    ("bo3gg_team_rating", "https://api.bo3.gg/api/v1/teams?page=1&per_page=50&site_id=1&sort=-rating", {}),
]


def analyse(key: str, body: bytes, ctype: str) -> dict:
    """Compact, source-agnostic analysis of a payload (no interpretation of values)."""
    info = {"content_type": ctype, "bytes": len(body)}
    text = None
    try:
        text = body.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return info
    info["cs2_mentions"] = len(CS2_RE.findall(text))
    info["has_odds_keys"] = bool(ODDS_KEY_RE.search(text))
    try:
        data = json.loads(text)
    except Exception:
        info["json"] = False
        if "text/html" in (ctype or ""):
            info["html_title"] = (re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I) or [None, None])[1]
            info["html_api_paths"] = sorted(set(re.findall(r"[\"'](/api/[a-zA-Z0-9_\-/?.=&]+)[\"']", text)))[:10]
            info["next_data"] = "__NEXT_DATA__" in text
            info["cf_challenge"] = ("Just a moment" in text) or ("cf-challenge" in text) or ("Attention Required" in text)
        return info
    info["json"] = True
    if isinstance(data, dict):
        info["top_keys"] = sorted(data.keys())[:25]
        if "events" in data and "betOffers" in data:
            info["events"] = len(data["events"] or [])
            info["bet_offers"] = len(data["betOffers"] or [])
        if "results" in data:
            info["results"] = len(data["results"] or [])
            info["total"] = data.get("total")
    elif isinstance(data, list):
        info["list_len"] = len(data)
        if data and isinstance(data[0], dict):
            info["item_keys"] = sorted(data[0].keys())[:25]
    # collect a few sample names/leagues for manual review
    names: list[str] = []
    def walk(node, depth=0):
        if depth > 4 or len(names) >= 12:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and k.lower() in ("name", "league", "tournament", "home",
                                                        "away", "team1", "team2", "participant",
                                                        "teamname", "description", "path") and len(v) < 60:
                    names.append(f"{k}={v}")
                elif isinstance(v, (dict, list)):
                    walk(v, depth + 1)
                if len(names) >= 12:
                    return
        elif isinstance(node, list):
            for v in node[:6]:
                walk(v, depth + 1)
                if len(names) >= 12:
                    return
    walk(data)
    info["samples"] = names[:12]
    return info


def probe(item):
    key, url, extra = item
    headers = dict(BASE_HEADERS)
    headers.update(extra)
    if "Referer" not in headers and "pinnacle" not in url:
        headers["Referer"] = url.rsplit("/", 1)[0] + "/" if "/" in url else url
    rec = {"key": key, "url": url, "status": None, "error": None}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            rec["status"] = resp.status
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        rec["status"] = exc.code
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec
    rec.update(analyse(key, body, ctype))
    if rec["status"] == 200 and (rec.get("cs2_mentions") or rec.get("json")):
        os.makedirs(SAMPLES, exist_ok=True)
        with open(os.path.join(SAMPLES, f"{key}.txt"), "wb") as fh:
            fh.write(body[:150_000])
    return rec


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(probe, CANDIDATES))
    json_ok = [r for r in results if r.get("status") == 200 and r.get("json")]
    cs2_ok = [r for r in results if r.get("status") == 200 and (r.get("cs2_mentions") or 0) > 0]
    with_prices = [r for r in cs2_ok if r.get("has_odds_keys")]
    summary = {
        "probe_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {"candidates": len(CANDIDATES), "http_200": sum(1 for r in results if r.get("status") == 200),
                   "json_200": len(json_ok), "cs2_payloads": len(cs2_ok),
                   "cs2_with_price_keys": len(with_prices)},
        "cs2_sources": [r["key"] for r in cs2_ok],
        "cs2_priced": [r["key"] for r in with_prices],
        "results": results,
    }
    with open(os.path.join(OUT, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
    print("cs2 payloads:", summary["cs2_sources"])
    print("cs2 priced:", summary["cs2_priced"])
    for r in results:
        print(f"  {r['key']:32s} status={r['status'] or r['error']} "
              f"json={r.get('json')} cs2={r.get('cs2_mentions')} odds={r.get('has_odds_keys')} "
              f"bytes={r.get('bytes')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
