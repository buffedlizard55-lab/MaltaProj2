#!/usr/bin/env python3
"""
External betting-line collector.

Sources (all public, no login, no bot-protection bypass):
  1. Pinnacle  — licensed bookmaker, public guest odds API (sport id 12 "E Sports").
  2. Polymarket — public prediction-market API (real-money CS2 match markets).
  3. Bovada    — US-facing sportsbook, public coupon JSON (probe).

Output: data/odds.json
  { generated_at_utc, collection_attempt_utc, sources[], lines[] }
Each line keeps the RAW quoted decimal prices plus the exact public URL they were read
from, the source's own event/market identifiers, retrieval timestamp and market type.
No probabilities are computed here, and nothing is inferred: a market that is not returned
by the source simply does not appear in the output.
"""

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
PIN_ESPORT_SPORT_ID = 12  # "E Sports" per /0.1/sports
PIN_HEADERS = {
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "X-Device-UUID": str(uuid.uuid4()),
    "Referer": "https://www.pinnacle.com/",
}


def now_iso():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url, headers=None, timeout=45):
    hdrs = {"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode(), {}


def get_json(url, headers=None, timeout=45):
    st, body, hdrs = fetch(url, headers, timeout)
    try:
        return st, json.loads(body.decode("utf-8", "replace")), hdrs
    except Exception:
        return st, None, hdrs


# --------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(lines, evidence):
    st, leagues, _ = get_json(f"{PIN}/sports/{PIN_ESPORT_SPORT_ID}/leagues", PIN_HEADERS)
    evidence["pinnacle_sports_12_leagues"] = {"status": st, "count": len(leagues or [])}
    if not isinstance(leagues, list):
        return
    cs_leagues = [l for l in leagues if re.search(r"counter|cs2|cs:go", str(l.get("name", "")), re.I)]
    evidence["pinnacle_cs2_leagues"] = [{"id": l.get("id"), "name": l.get("name"),
                                         "matchupCount": l.get("matchupCount")} for l in cs_leagues]
    seen = 0
    for league in cs_leagues:
        if not league.get("matchupCount"):
            continue
        st2, matchups, _ = get_json(f"{PIN}/leagues/{league['id']}/matchups", PIN_HEADERS)
        if not isinstance(matchups, list):
            continue
        for m in matchups:
            parts = m.get("participants") or []
            if len(parts) != 2:
                continue
            seen += 1
            mid = m.get("id")
            market_url = f"{PIN}/matchups/{mid}/markets/related/straight"
            st3, markets, _ = get_json(market_url, PIN_HEADERS)
            if not isinstance(markets, list):
                continue
            moneylines = [mk for mk in markets
                          if str(mk.get("type", "")).lower() == "moneyline"
                          and mk.get("period") == 0 and not mk.get("isAlternate")]
            for mk in moneylines:
                prices = mk.get("prices") or []
                if len(prices) != 2:
                    continue
                by_des = {str(p.get("designation")): p.get("price") for p in prices}
                line = {
                    "source_key": "pinnacle",
                    "source_name": "Pinnacle",
                    "source_kind": "bookmaker",
                    "source_api_url": market_url,
                    "source_public_url": "https://www.pinnacle.com/en/esports/",
                    "source_event_id": str(mid),
                    "source_league": league.get("name"),
                    "source_market_id": str(mk.get("id")),
                    "market_type": "moneyline (series winner)",
                    "market_period": mk.get("period"),
                    "market_is_live": bool(mk.get("isLive")),
                    "market_status": mk.get("status"),
                    "retrieved_at_utc": now_iso(),
                    "start_time_utc": ms_iso(m.get("startTime")),
                    "team_a_name": parts[0].get("name"),
                    "team_b_name": parts[1].get("name"),
                    "team_a_designation": "home" if parts[0].get("alignment") == "home" else "away",
                    "team_b_designation": "home" if parts[1].get("alignment") == "home" else "away",
                    "decimal_odds_a": by_des.get("home") if parts[0].get("alignment") == "home" else by_des.get("away"),
                    "decimal_odds_b": by_des.get("home") if parts[1].get("alignment") == "home" else by_des.get("away"),
                    "raw_prices": prices,
                    "source_matchup_status": m.get("status"),
                }
                lines.append(line)
            time.sleep(0.25)
    evidence["pinnacle_matchups_scanned"] = seen


def ms_iso(value):
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------- Polymarket
PM_TITLE = re.compile(r"^Counter-Strike:\s*(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)\s*(?:\((?P<fmt>[^)]*)\))?\s*-\s*(?P<tour>.+)$", re.I)


def collect_polymarket(lines, evidence):
    st, events, _ = get_json(
        "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports")
    evidence["polymarket_events"] = {"status": st, "count": len(events or [])}
    if not isinstance(events, list):
        return
    matched = 0
    for ev in events:
        title = str(ev.get("title", ""))
        m = PM_TITLE.match(title.strip())
        if not m:
            continue
        matched += 1
        markets = ev.get("markets") or []
        for mk in markets:
            outcomes = mk.get("outcomes")
            prices = mk.get("outcomePrices")
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except Exception:
                    outcomes = None
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except Exception:
                    prices = None
            if not outcomes or not prices or len(outcomes) != 2:
                continue
            def dec(p):
                try:
                    p = float(p)
                    return round(1.0 / p, 4) if p > 0 else None
                except (TypeError, ValueError):
                    return None
            lines.append({
                "source_key": "polymarket",
                "source_name": "Polymarket",
                "source_kind": "prediction market",
                "source_api_url": "https://gamma-api.polymarket.com/events?closed=false&tag_slug=esports",
                "source_public_url": f"https://polymarket.com/event/{ev.get('slug')}",
                "source_event_id": str(ev.get("id")),
                "source_market_id": str(mk.get("id")),
                "source_league": m.group("tour").strip(),
                "market_type": "match winner (moneyline)",
                "market_period": 0,
                "market_is_live": bool(mk.get("closed") is False and mk.get("active")),
                "market_status": "open" if mk.get("active") and not mk.get("closed") else "closed",
                "retrieved_at_utc": now_iso(),
                "start_time_utc": iso_or_none(ev.get("startDate") or mk.get("endDate")),
                "team_a_name": m.group("a").strip(),
                "team_b_name": m.group("b").strip(),
                "series_format": m.group("fmt"),
                "decimal_odds_a": dec(prices[0]),
                "decimal_odds_b": dec(prices[1]),
                "raw_prices": {"outcomes": outcomes, "outcome_prices": prices,
                               "last_trade_price": mk.get("lastTradePrice"),
                               "best_bid": mk.get("bestBid"), "best_ask": mk.get("bestAsk"),
                               "volume": mk.get("volume")},
                "event_title": title,
            })
    evidence["polymarket_cs2_match_events"] = matched


def iso_or_none(value):
    if not value:
        return None
    try:
        v = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(v).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


# ----------------------------------------------------------------------------- Bovada
BOVADA_URLS = [
    "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike",
    "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports",
]


def collect_bovada(lines, evidence):
    for url in BOVADA_URLS:
        st, data, hdrs = get_json(url)
        evidence.setdefault("bovada", []).append({"url": url, "status": st,
                                                  "content_type": hdrs.get("Content-Type"),
                                                  "shape": type(data).__name__})
        if st != 200 or data is None:
            continue
        events = []
        if isinstance(data, list):
            for group in data:
                events.extend(group.get("events", []) if isinstance(group, dict) else [])
        for ev in events:
            competitors = (ev.get("competitors") or [])
            if len(competitors) != 2:
                continue
            for dg in ev.get("displayGroups", []):
                for mk in dg.get("markets", []):
                    if str(mk.get("description", "")).lower() not in ("moneyline", "money line", "match winner"):
                        continue
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    prices = [o.get("price", {}).get("decimal") for o in outs]
                    if not all(prices):
                        continue
                    lines.append({
                        "source_key": "bovada",
                        "source_name": "Bovada",
                        "source_kind": "bookmaker",
                        "source_api_url": url,
                        "source_public_url": "https://www.bovada.lv/sports/esports",
                        "source_event_id": str(ev.get("id")),
                        "source_market_id": str(mk.get("id")),
                        "source_league": (dg.get("description") or ev.get("description")),
                        "market_type": "moneyline (match winner)",
                        "market_period": 0,
                        "market_is_live": bool(ev.get("live")),
                        "market_status": mk.get("status"),
                        "retrieved_at_utc": now_iso(),
                        "start_time_utc": iso_or_none(ev.get("startTime")),
                        "team_a_name": competitors[0].get("name"),
                        "team_b_name": competitors[1].get("name"),
                        "decimal_odds_a": prices[0],
                        "decimal_odds_b": prices[1],
                        "raw_prices": {"outcomes": [o.get("description") for o in outs],
                                       "decimal": prices},
                    })
        break


def main() -> int:
    started = now_iso()
    lines = []
    evidence = {"generated_at_utc": started, "collection_attempt_utc": started}
    for fn in (collect_pinnacle, collect_polymarket, collect_bovada):
        try:
            fn(lines, evidence)
        except Exception as exc:  # noqa: BLE001 - a failed source must not lose the others
            evidence.setdefault("errors", []).append({"source": fn.__name__, "error": str(exc)})
    doc = {
        "generated_at_utc": now_iso(),
        "collection_attempt_utc": started,
        "rules": [
            "HotSpawn is used for fixture discovery only, never as a probability source.",
            "Every price below is a raw decimal quote copied from the named external source URL.",
            "Missing market = the source did not quote it; nothing is inferred or filled in.",
        ],
        "source_summary": {},
        "lines": lines,
    }
    for line in lines:
        key = line["source_key"]
        doc["source_summary"][key] = doc["source_summary"].get(key, 0) + 1
    _write("data/odds.json", doc)
    _write("evidence/odds_collection.json", evidence)
    print("lines:", len(lines), doc["source_summary"])
    return 0


def _write(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
