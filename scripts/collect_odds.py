#!/usr/bin/env python3
"""
External betting-line collector (raw quotes only).

Sources:
  * Pinnacle  — licensed bookmaker, public guest odds API. Sport id 12 = "E Sports".
  * Bovada    — US-facing bookmaker, public coupon JSON.
  * Polymarket— public prediction market API (included; stale CS2 match markets filtered out).

Every emitted line keeps:
  - the exact public URL(s) the quote was read from,
  - the source's own event/market identifiers,
  - the retrieval timestamp (UTC),
  - the raw quoted price in the source's own format,
  - the market type (match winner / series winner only — map markets are excluded),
  - the source's reported start time and status.

A decimal price derived from a source-quoted American price is labelled as derived.
Nothing is converted across market types and nothing is filled in when a source is silent.
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
PIN_SPORT_ESPORTS = 12
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "X-Device-UUID": str(uuid.uuid4()), "Referer": "https://www.pinnacle.com/"}
CS2_LEAGUE_RE = re.compile(r"counter|cs2|cs:go|csgo", re.I)


def now_iso():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_iso(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (100 / abs(a)) if a < 0 else 1 + (a / 100), 4)


def fetch(url, headers=None, timeout=45):
    hdrs = {"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode()


def get_json(url, headers=None, timeout=45):
    st, body = fetch(url, headers, timeout)
    try:
        return st, json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return st, None


# ------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(lines, evidence):
    url = f"{PIN}/sports/{PIN_SPORT_ESPORTS}/matchups"
    st, matchups = get_json(url, PIN_HEADERS)
    evidence["pinnacle_matchups"] = {"url": url, "status": st,
                                     "count": len(matchups) if isinstance(matchups, list) else None}
    if not isinstance(matchups, list):
        return
    cs2 = [m for m in matchups
           if CS2_LEAGUE_RE.search(str((m.get("league") or {}).get("name", "")))]
    evidence["pinnacle_cs2_matchups"] = len(cs2)
    evidence["pinnacle_cs2_leagues"] = sorted({(m.get("league") or {}).get("name") for m in cs2})
    for m in cs2:
        parts = m.get("participants") or []
        if len(parts) != 2:
            continue
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        st2, markets = get_json(murl, PIN_HEADERS)
        if not isinstance(markets, list):
            time.sleep(0.2)
            continue
        # Main series/match moneyline = type moneyline, period 0, not alternate, 2 prices.
        cands = [mk for mk in markets
                 if str(mk.get("type", "")).lower() == "moneyline"
                 and mk.get("period") == 0 and not mk.get("isAlternate")
                 and isinstance(mk.get("prices"), list) and len(mk.get("prices") or []) == 2
                 and all(p.get("price") is not None for p in mk.get("prices") or [])]
        for mk in cands[:1]:
            prices = mk["prices"]
            home = parts[0] if parts[0].get("alignment") == "home" else parts[1]
            by_align = {p.get("designation"): p.get("price") for p in prices}
            a_am = by_align.get("home") if parts[0].get("alignment") == "home" else by_align.get("away")
            b_am = by_align.get("home") if parts[1].get("alignment") == "home" else by_align.get("away")
            lines.append({
                "source_key": "pinnacle",
                "source_name": "Pinnacle",
                "source_kind": "licensed bookmaker",
                "source_public_url": "https://www.pinnacle.com/en/esports/counter-strike/",
                "source_api_url": murl,
                "source_event_id": str(mid),
                "source_market_id": str(mk.get("id")),
                "source_league": (m.get("league") or {}).get("name"),
                "market_type": "series/match winner (moneyline)",
                "market_period": "full match",
                "market_is_live": bool(mk.get("isLive")),
                "market_status": mk.get("status"),
                "source_reported_status": m.get("status"),
                "retrieved_at_utc": now_iso(),
                "start_time_utc": ms_iso(m.get("startTime")),
                "team_a_name": parts[0].get("name"),
                "team_b_name": parts[1].get("name"),
                "raw_price_format": "american",
                "raw_price_a": a_am,
                "raw_price_b": b_am,
                "decimal_odds_a": american_to_decimal(a_am),
                "decimal_odds_b": american_to_decimal(b_am),
                "decimal_odds_derived": True,
                "raw_prices": prices,
            })
        time.sleep(0.25)


# --------------------------------------------------------------------------- Bovada
def collect_bovada(lines, evidence):
    url = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
    st, data = get_json(url)
    evidence["bovada"] = {"url": url, "status": st, "shape": type(data).__name__}
    if st != 200 or not isinstance(data, list):
        return
    groups = len(data)
    events = 0
    cs2_events = 0
    for group in data:
        for ev in (group.get("events") or []):
            events += 1
            link = str(ev.get("link") or "")
            if "counter-strike" not in link and "cs2" not in link:
                continue
            comps = ev.get("competitors") or []
            if len(comps) != 2:
                continue
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if str(mk.get("description", "")).strip().lower() != "moneyline":
                        continue
                    period = mk.get("period") or {}
                    if not period.get("main"):
                        continue  # excludes Map 1/Map 2/Map 3 moneylines
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    prices = [((o.get("price") or {}).get("decimal")) for o in outs]
                    am = [((o.get("price") or {}).get("american")) for o in outs]
                    if not all(prices):
                        continue
                    cs2_events += 1
                    lines.append({
                        "source_key": "bovada",
                        "source_name": "Bovada",
                        "source_kind": "licensed bookmaker",
                        "source_public_url": "https://www.bovada.lv" + link,
                        "source_api_url": url,
                        "source_event_id": str(ev.get("id")),
                        "source_market_id": str(mk.get("id")),
                        "source_league": (dg.get("description") or ""),
                        "market_type": "match winner (moneyline, full match)",
                        "market_period": period.get("description"),
                        "market_is_live": bool(ev.get("live")),
                        "market_status": mk.get("status"),
                        "source_reported_status": "live" if ev.get("live") else "scheduled",
                        "retrieved_at_utc": now_iso(),
                        "start_time_utc": ms_iso(ev.get("startTime")),
                        "team_a_name": comps[0].get("name"),
                        "team_b_name": comps[1].get("name"),
                        "raw_price_format": "decimal",
                        "raw_price_a": prices[0],
                        "raw_price_b": prices[1],
                        "decimal_odds_a": float(prices[0]),
                        "decimal_odds_b": float(prices[1]),
                        "decimal_odds_derived": False,
                        "raw_prices": {"outcomes": [o.get("description") for o in outs],
                                       "decimal": prices, "american": am},
                    })
    evidence["bovada"].update({"groups": groups, "events": events, "cs2_moneyline_lines": cs2_events})


# ----------------------------------------------------------------------- Polymarket
PM_TITLE = re.compile(
    r"^Counter-Strike:\s*(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)\s*(?:\((?P<fmt>[^)]*)\))?\s*-\s*(?P<tour>.+)$",
    re.I)


def collect_polymarket(lines, evidence):
    url = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports"
    st, events = get_json(url)
    evidence["polymarket"] = {"url": url, "status": st,
                              "events": len(events) if isinstance(events, list) else None}
    if not isinstance(events, list):
        return
    cs2_events = 0
    fresh = 0
    now = datetime.now(tz=timezone.utc)
    for ev in events:
        m = PM_TITLE.match(str(ev.get("title", "")).strip())
        if not m:
            continue
        cs2_events += 1
        for mk in ev.get("markets") or []:
            outcomes = mk.get("outcomes")
            prices = mk.get("outcomePrices")
            if isinstance(outcomes, str):
                outcomes = safe_json(outcomes)
            if isinstance(prices, str):
                prices = safe_json(prices)
            if not outcomes or not prices or len(outcomes) != 2 or len(prices) != 2:
                continue
            if mk.get("closed") or not mk.get("active"):
                continue
            if any(p is None for p in outcomes):
                continue
            end = mk.get("endDate") or ev.get("endDate")
            end_dt = parse_iso(end)
            if end_dt and end_dt < now:
                continue  # stale market (source still lists it, but the event date has passed)
            fresh += 1
            dec = [round(1 / float(p), 4) if float(p) > 0 else None for p in prices]
            lines.append({
                "source_key": "polymarket",
                "source_name": "Polymarket",
                "source_kind": "prediction market",
                "source_public_url": f"https://polymarket.com/event/{ev.get('slug')}",
                "source_api_url": url,
                "source_event_id": str(ev.get("id")),
                "source_market_id": str(mk.get("id")),
                "source_league": m.group("tour").strip(),
                "market_type": "match winner (event market)",
                "market_period": "full match",
                "market_is_live": False,
                "market_status": "open",
                "source_reported_status": "open",
                "retrieved_at_utc": now_iso(),
                "start_time_utc": iso_utc(mk.get("endDate") or ev.get("endDate")),
                "team_a_name": m.group("a").strip(),
                "team_b_name": m.group("b").strip(),
                "series_format": m.group("fmt"),
                "raw_price_format": "implied_probability_share",
                "raw_price_a": prices[0],
                "raw_price_b": prices[1],
                "decimal_odds_a": dec[0],
                "decimal_odds_b": dec[1],
                "decimal_odds_derived": True,
                "raw_prices": {"outcomes": outcomes, "share_prices": prices,
                               "volume": mk.get("volume")},
                "event_title": ev.get("title"),
            })
    evidence["polymarket"].update({"cs2_match_events": cs2_events, "fresh_markets": fresh})


def safe_json(s):
    try:
        return json.loads(s)
    except Exception:
        return None


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def iso_utc(value):
    dt = parse_iso(value)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


# ------------------------------------------------------- candidate source probing
CANDIDATES = {
    "rivalry_esports": "https://rivalry.com/en/esports",
    "rivalry_api": "https://api.rivalry.com/api/v1/esports/matches?limit=5",
    "onexbet_line": "https://1xbet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=50&lng=en&mode=4&country=1",
    "strafe_cs2": "https://strafe.com/matches/counter-strike",
    "flashscore_esports": "https://www.flashscore.com/esports/",
    "oddspedia_esports": "https://oddspedia.com/esports",
    "thunderpick_api": "https://api.thunderpick.io/api/v1/esports/matches",
    "ggbet_api": "https://gg.bet/api/line/esports",
}


def probe_candidates(evidence):
    rows = []
    for key, url in CANDIDATES.items():
        st, body = fetch(url, timeout=30)
        text = body.decode("utf-8", "replace")
        rows.append({"key": key, "url": url, "status": st, "bytes": len(body),
                     "json": text.lstrip()[:1] in "[{",
                     "preview": text[:220]})
        time.sleep(0.4)
    evidence["candidate_sources"] = rows


def main() -> int:
    started = now_iso()
    lines, evidence = [], {"collection_attempt_utc": started}
    for fn in (collect_pinnacle, collect_bovada, collect_polymarket, probe_candidates):
        try:
            fn(lines, evidence)
        except Exception as exc:  # noqa: BLE001
            evidence.setdefault("errors", []).append({"source": fn.__name__, "error": str(exc)})
    summary = {}
    for line in lines:
        summary[line["source_key"]] = summary.get(line["source_key"], 0) + 1
    doc = {
        "generated_at_utc": now_iso(),
        "collection_attempt_utc": started,
        "rules": [
            "HotSpawn is fixture discovery only — never a probability source.",
            "Only match/series-winner markets are collected (no map markets, no handicaps).",
            "Every price is a raw quote from the named source URL at retrieved_at_utc.",
            "A missing market stays missing: nothing is inferred, filled or extrapolated.",
        ],
        "source_summary": summary,
        "lines": lines,
    }
    _write("data/odds.json", doc)
    _write("evidence/odds_collection.json", evidence)
    print("lines:", len(lines), summary)
    return 0


def _write(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
