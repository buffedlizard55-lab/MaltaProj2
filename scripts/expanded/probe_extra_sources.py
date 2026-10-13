#!/usr/bin/env python3
"""Round-3 source exploration: full-coverage endpoints for the reachable sources, plus a
second sweep of candidate bookmakers that were not probed before.

Why: the 1xBet-family `Get1x2_VZip` mirror feed returns only ~50 events per sport, which is
enough for the biggest matches but not for full lobby coverage. This probe looks for the
per-championship endpoints of that platform and tests a further set of bookmakers that may
serve JSON/HTML to a datacentre IP.

Writes data/expanded/source_probe_extra.json. No price is published from this probe.

Usage: python3 scripts/expanded/probe_extra_sources.py
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, text/html;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
MAX = 600_000

LINE_FEED_VARIANTS = [
    ("champs_a", "https://melbet.com/service-api/LineFeed/GetChampsZip?sports=40&lng=en&country=1"),
    ("champs_b", "https://melbet.com/service-api/LineFeed/GetChampsZip?sports=40&lng=en&country=1&partner=51"),
    ("champs_c", "https://melbet.com/service-api/LineFeed/GetChampsZip?sports=40&lng=en&country=1&virtualSports=true&groupChamps=true"),
    ("champs_d", "https://melbet.com/service-api/LineFeed/GetChampsZip?"),
    ("champs_e", "https://melbet.com/service-api/LineFeed/GetSportsZip?sports=1&lng=en&country=1"),
    ("champs_f", "https://melbet.com/service-api/LineFeed/GetChampsZip?sports=40&lng=en&country=1&tf=1000000&tz=3"),
    ("champs_g", "https://melbet.com/service-api/LineFeed/GetChampsZip?sports=40&lng=en&country=1&hideZeros=true"),
    ("1x2_a", "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1&getEmpty=true"),
    ("1x2_b", "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=1&country=1&type=1"),
    ("1x2_c", "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&country=1&tf=1000000&tz=3&antiExpressBlock=true&groupChamps=true"),
    ("1x2_d", "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=2000&lng=en&mode=4&country=1&partner=51&virtualSports=true"),
    ("line", "https://melbet.com/service-api/LineFeed/GetLineZip?sports=40&count=500&lng=en&country=1"),
    ("game_sample", "https://melbet.com/service-api/LineFeed/GetGameZip?id=761038194&lng=en&country=1"),
    ("live", "https://melbet.com/service-api/LineFeed/GetLiveZip?sports=40&count=500&lng=en&country=1"),
]

EXTRA_BOOKMAKERS = [
    ("marathonbet_esports", "https://www.marathonbet.com/en/betting/eSports/"),
    ("marathonbet_api", "https://www.marathonbet.com/en/betting/InternetJsonLines?action=line&sport=esports"),
    ("coolbet_api", "https://www.coolbet.com/api/betoffer/v2/bet-offers?lang=en&sport=counter_strike"),
    ("coolbet_alt", "https://api.coolbet.com/api/betoffer/v2/bet-offers?sport=counter_strike"),
    ("bwin_api", "https://www.bwin.com/api/Sportsbook/Events?query=esports"),
    ("betclic_api", "https://www.betclic.com/api/sports/v1/competitions?site=1&country=2&sport=esports"),
    ("winamax_esports", "https://www.winamax.fr/paris-sportifs/sports/4"),
    ("nordicbet_api", "https://www.nordicbet.com/api/line/esports"),
    ("betsson_api", "https://www.betsson.com/api/line/esports"),
    ("tipico_api", "https://sports.tipico.de/api/sportsbook/esports"),
    ("888sport_api", "https://www.888sport.com/api/line/esports"),
    ("leovegas_api", "https://www.leovegas.com/api/line/esports"),
    ("kambi_ub", "https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/esports/all/all/matches.json?lang=en_GB&market=GB&client_id=2&channel_id=1&ncid=1&useCombined=true&useCombinedLive=true"),
    ("kambi_ubse", "https://eu-offering-api.kambicdn.com/offering/v2018/ubse/listView/esports/all/all/matches.json?lang=en_GB&market=SE&client_id=2&channel_id=1&ncid=1&useCombined=true"),
    ("pinnacle_archived", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups?withSpecials=false"),
    ("pinnacle_special", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/markets/straight"),
    ("thunderpick_web", "https://thunderpick.io/api/v1/matches?status=active"),
    ("thunderpick_web2", "https://thunderpick.io/api/esports/matches"),
    ("esportsbets", "https://esportsbets.com/counter-strike/"),
    ("csgo_betting_odds", "https://www.csgo-betting.com/"),
    ("midnite_esports", "https://www.midnite.com/esports/counter-strike-2"),
    ("bolag_esports", "https://www.betsson.se/api/line/esports"),
    ("bo3_teams", "https://bo3.gg/api/v1/teams?sort=-rating&page=1&limit=100"),
    ("bo3_rankings", "https://bo3.gg/api/v1/teams/rankings?discipline=counter-strike"),
    ("bo3_team_one", "https://bo3.gg/api/v1/teams/1049"),
    ("bo3_match_one", "https://bo3.gg/api/v1/matches/128537"),
    ("hltv_alt", "https://www.hltv.org/ranking/teams"),
    ("egamersworld_api", "https://egamersworld.com/api/v1/matches?game=counterstrike"),
    ("oddspedia_alt", "https://oddspedia.com/api/v1/getMatchList?language=en&sport=counter_strike&status=all&limit=100"),
]


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            body = r.read(MAX)
            return r.status, r.headers.get("Content-Type"), body, None, r.geturl()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(MAX)
        except Exception:  # noqa: BLE001
            pass
        return exc.code, (exc.headers.get("Content-Type") if exc.headers else None), body, f"HTTPError {exc.code}", None
    except Exception as exc:  # noqa: BLE001
        return 0, None, b"", f"{type(exc).__name__}: {str(exc)[:160]}", None


def summarise(status: int, body: bytes, ctype: str | None):
    info = {"json": False, "records": None, "keys": None, "preview": ""}
    if not body:
        return info
    text = body.decode("utf-8", "replace")
    info["preview"] = text[:400]
    if text.lstrip()[:1] in "[{":
        try:
            data = json.loads(text)
            info["json"] = True
            if isinstance(data, list):
                info["records"] = len(data)
                if data and isinstance(data[0], dict):
                    info["keys"] = sorted(data[0].keys())[:25]
            elif isinstance(data, dict):
                info["keys"] = sorted(data.keys())[:25]
                for k in ("Value", "Value2", "data", "items", "results"):
                    v = data.get(k)
                    if isinstance(v, list):
                        info["records"] = len(v)
                        if v and isinstance(v[0], dict):
                            info["item_keys"] = sorted(v[0].keys())[:30]
                        break
                    if isinstance(v, dict):
                        info["records"] = v.get("_original_length")
                        items = v.get("_items")
                        if items and isinstance(items[0], dict):
                            info["item_keys"] = sorted(items[0].keys())[:30]
                        break
        except Exception:  # noqa: BLE001
            pass
    return info


def main() -> int:
    out = ROOT / "data" / "expanded" / "source_probe_extra.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for group, items in (("linefeed_variants", LINE_FEED_VARIANTS),
                         ("extra_bookmakers", EXTRA_BOOKMAKERS)):
        print(f"--- {group} ---")
        for key, url in items:
            status, ctype, body, err, final = fetch(url)
            info = summarise(status, body, ctype)
            results.append({"group": group, "key": key, "url": url, "http_status": status,
                            "content_type": ctype, "bytes": len(body), "error": err,
                            "final_url": final, **info})
            print(f"{status:>4} {key:<22} json={str(info['json']):<5} recs={str(info['records']):<6} "
                  f"bytes={len(body):<8} {str(err)[:50]}")
            if info.get("item_keys"):
                print(f"      item_keys={info['item_keys']}")
    doc = {"generated_at_utc": now_iso(),
           "purpose": ("Round-3 reachability/structure probe. A failed row is recorded as unavailable "
                       "and is never used for prices."),
           "results": results}
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    ok = [r for r in results if r["http_status"] == 200]
    print(f"\nWROTE {out} — 200: {len(ok)}/{len(results)}")
    print("ok keys: " + ", ".join(r["key"] for r in ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
