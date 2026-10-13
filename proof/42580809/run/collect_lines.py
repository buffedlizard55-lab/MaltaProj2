#!/usr/bin/env python3
"""
Runner task — collect raw CS2 match-winner (moneyline) quotes from public sources.

Sources (all public, unauthenticated, no challenge is solved or bypassed):
  1. Pinnacle      - licensed bookmaker, public guest odds API (sport 12 "E Sports").
  2. Bovada        - licensed US-facing bookmaker, public coupon JSON.
  3. Kalshi        - CFTC-regulated US prediction exchange, public trade API
                     (series KXCS2GAME = "<A> vs <B>" winner markets, per-market book).
  4. Polymarket    - public prediction market (Gamma API), CS2 match markets only.
  5. Kambi tenants - licensed bookmakers on the Kambi platform, public offering API.

Every emitted quote keeps: the exact URL it came from, the source's own event/market ids,
the retrieval timestamp (UTC), the price in the source's own format, and the market type.
Nothing is interpreted, converted across market types, or filled in when a source is silent.

Outputs:
  evidence/lines.json           - every raw quote + provenance
  evidence/lines_sources.json   - per-source status/statistics (incl. failures)
  evidence/kalshi_compact.json  - Kalshi market structure + two-sided book (evidence)
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
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "X-Device-UUID": "be7f6d0f-2a3d-4d1a-9e6f-6a2b5f6c1d20",
               "Referer": "https://www.pinnacle.com/", "User-Agent": UA,
               "Accept": "application/json"}
CS2_RE = re.compile(r"(cs2|counter[- ]?strike|cs:go)", re.I)
NOW = None


def now_iso():
    return NOW


def get(url, headers=None, timeout=60):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read()
        except Exception:  # noqa: BLE001
            return exc.code, b""
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}".encode()


def jload(body):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None


def as_number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def american_to_decimal(a):
    a = as_number(a)
    if a is None or a == 0:
        return None
    return round(1 + (a / 100.0 if a > 0 else 100.0 / abs(a)), 6)


# --------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(lines, stats):
    url = f"{PIN}/sports/12/matchups"
    st, body = get(url, PIN_HEADERS)
    data = jload(body)
    stats["pinnacle"] = {"url": url, "status": st,
                         "matchups": len(data) if isinstance(data, list) else None}
    if not isinstance(data, list):
        return
    cs2 = [m for m in data if CS2_RE.search(str((m.get("league") or {}).get("name", "")))]
    stats["pinnacle"]["cs2_matchups"] = len(cs2)
    stats["pinnacle"]["cs2_leagues"] = sorted({(m.get("league") or {}).get("name") for m in cs2})

    def one(m):
        """Only the matchup's own full-match moneyline, never a map or special market.

        Pinnacle's /matchups/<id>/markets/related/straight payload contains the whole market
        family (map winners, alternate lines, specials such as "Yes vs No"). A quote is kept
        only when the market belongs to this matchup (`matchupId`), is a non-alternate
        moneyline on period 0 with exactly two priced sides, and the matchup itself is a real
        head-to-head (`type == "matchup"`).
        """
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        st2, body2 = get(murl, PIN_HEADERS)
        mkts = jload(body2)
        out = []
        parts = m.get("participants") or []
        if not isinstance(mkts, list) or len(parts) != 2:
            return out
        if str(m.get("type", "matchup")) != "matchup" or m.get("special"):
            return out
        cands = []
        for mk in mkts:
            if mk.get("matchupId") != mid:
                continue
            if str(mk.get("type", "")).lower() != "moneyline" or mk.get("period") != 0:
                continue
            if mk.get("isAlternate"):
                continue
            prices = mk.get("prices") or []
            if len(prices) != 2 or any(p.get("price") is None for p in prices):
                continue
            if {p.get("designation") for p in prices} != {"home", "away"}:
                continue
            cands.append(mk)
        cands.sort(key=lambda mk: mk.get("id") or 0)
        for mk in cands[:1]:
            prices = mk["prices"]
            by_des = {p.get("designation"): p.get("price") for p in prices}
            out.append({
                "source_key": "pinnacle",
                "source_name": "Pinnacle",
                "source_kind": "licensed bookmaker",
                "source_public_url": "https://www.pinnacle.com/en/esports/",
                "source_api_url": murl,
                "source_event_id": str(mid),
                "source_market_id": str(mk.get("id")),
                "source_market_candidates": len(cands),
                "source_league": (m.get("league") or {}).get("name"),
                "market_type": "series/match winner (moneyline, full match)",
                "market_is_live": bool(mk.get("isLive")),
                "market_status": mk.get("status"),
                "source_reported_status": m.get("status"),
                "retrieved_at_utc": now_iso(),
                "start_time_utc": m.get("startTime"),
                "team_a_name": parts[0].get("name"),
                "team_b_name": parts[1].get("name"),
                "raw_price_format": "american",
                "raw_price_a": by_des.get("home"),
                "raw_price_b": by_des.get("away"),
                "decimal_odds_a": american_to_decimal(by_des.get("home")),
                "decimal_odds_b": american_to_decimal(by_des.get("away")),
                "decimal_odds_derived": True,
            })
        return out

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        for res in pool.map(one, cs2):
            lines.extend(res)
    stats["pinnacle"]["quotes"] = len([l for l in lines if l["source_key"] == "pinnacle"])


# --------------------------------------------------------------------------- Bovada
def collect_bovada(lines, stats):
    url = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
    st, body = get(url)
    data = jload(body)
    stats["bovada"] = {"url": url, "status": st,
                       "groups": len(data) if isinstance(data, list) else None}
    if not isinstance(data, list):
        return
    n = skipped = 0
    for group in data:
        for ev in (group.get("events") or []):
            link = str(ev.get("link") or "")
            if "counter-strike" not in link and "cs2" not in link:
                skipped += 1
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
                        continue
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    prices = [(o.get("price") or {}).get("decimal") for o in outs]
                    am = [(o.get("price") or {}).get("american") for o in outs]
                    if not all(prices):
                        continue
                    n += 1
                    lines.append({
                        "source_key": "bovada",
                        "source_name": "Bovada",
                        "source_kind": "licensed bookmaker",
                        "source_public_url": "https://www.bovada.lv" + link,
                        "source_api_url": url,
                        "source_event_id": str(ev.get("id")),
                        "source_market_id": str(mk.get("id")),
                        "source_league": dg.get("description") or "",
                        "market_type": "match winner (moneyline, full match)",
                        "market_is_live": bool(ev.get("live")),
                        "market_status": mk.get("status"),
                        "source_reported_status": "live" if ev.get("live") else "scheduled",
                        "retrieved_at_utc": now_iso(),
                        "start_time_utc": ev.get("startTime"),
                        "team_a_name": comps[0].get("name"),
                        "team_b_name": comps[1].get("name"),
                        "raw_price_format": "decimal",
                        "raw_price_a": prices[0],
                        "raw_price_b": prices[1],
                        "decimal_odds_a": as_number(prices[0]),
                        "decimal_odds_b": as_number(prices[1]),
                        "decimal_odds_derived": False,
                        "raw_outcome_names": [o.get("description") for o in outs],
                    })
    stats["bovada"].update({"cs2_moneyline_quotes": n, "non_cs2_events_skipped": skipped})


# --------------------------------------------------------------------------- Kalshi
KALSHI_EVENTS = ("https://api.elections.kalshi.com/trade-api/v2/events"
                 "?series_ticker=KXCS2GAME&status=open&with_nested_markets=true&limit=200")
KALSHI_MARKET = "https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"


def collect_kalshi(lines, stats):
    """Kalshi (CFTC-regulated US exchange).

    The events listing publishes the market structure without prices; each market's own
    endpoint publishes the live two-sided book (yes_bid/yes_ask/no_bid/no_ask), the
    scheduled occurrence time and settlement rules that name the exact match.
    """
    st_e, body_e = get(KALSHI_EVENTS)
    events = jload(body_e)
    stats["kalshi"] = {"events_url": KALSHI_EVENTS, "events_status": st_e}
    if not isinstance(events, dict):
        return
    evs = events.get("events") or []
    stats["kalshi"]["events"] = len(evs)
    book = []

    def fetch_market(mk):
        url = KALSHI_MARKET.format(ticker=mk.get("ticker"))
        st, body = get(url)
        return mk, url, st, jload(body)

    for ev in evs:
        row = {"event_ticker": ev.get("event_ticker"), "title": ev.get("title"),
               "sub_title": ev.get("sub_title"), "category": ev.get("category"),
               "mutually_exclusive": ev.get("mutually_exclusive"), "markets": []}
        with cf.ThreadPoolExecutor(max_workers=5) as pool:
            for mk, url, st, detail in pool.map(fetch_market, ev.get("markets") or []):
                m = (detail or {}).get("market") or {}
                keep = {"_http_status": st, "_source_api_url": url}
                for k in ("ticker", "event_ticker", "title", "yes_sub_title", "no_sub_title",
                          "status", "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars",
                          "no_ask_dollars", "last_price_dollars", "previous_price_dollars",
                          "volume_fp", "volume_24h_fp", "open_interest_fp", "open_time",
                          "close_time", "occurrence_datetime", "expected_expiration_time",
                          "rules_primary", "market_type"):
                    if k in m:
                        keep[k] = m.get(k)
                row["markets"].append(keep)
                if st != 200 or not m:
                    continue
                yb = as_number(m.get("yes_bid_dollars"))
                ya = as_number(m.get("yes_ask_dollars"))
                nb = as_number(m.get("no_bid_dollars"))
                na = as_number(m.get("no_ask_dollars"))
                if not any(v for v in (yb, ya, nb, na) if v):
                    continue  # listed but no observable price: nothing to publish
                lines.append({
                    "source_key": "kalshi",
                    "source_name": "Kalshi",
                    "source_kind": "CFTC-regulated prediction exchange",
                    "source_public_url": "https://kalshi.com/markets/" + str(ev.get("event_ticker", "")).lower(),
                    "source_api_url": url,
                    "source_event_id": ev.get("event_ticker"),
                    "source_market_id": m.get("ticker"),
                    "source_league": ev.get("category"),
                    "source_rules_primary": m.get("rules_primary"),
                    "market_type": "match winner (Kalshi binary 'wins' market)",
                    "market_is_live": m.get("status") == "active",
                    "market_status": m.get("status"),
                    "retrieved_at_utc": now_iso(),
                    "start_time_utc": m.get("occurrence_datetime"),
                    "source_close_time_utc": m.get("close_time"),
                    "event_title": ev.get("title"),
                    "event_sub_title": ev.get("sub_title"),
                    "outcome_name": m.get("yes_sub_title") or m.get("title"),
                    "raw_price_format": "usd_probability_0_1_two_sided_book",
                    "yes_bid": yb, "yes_ask": ya, "no_bid": nb, "no_ask": na,
                    "last_price": as_number(m.get("last_price_dollars")),
                    "volume": m.get("volume_fp"), "open_interest": m.get("open_interest_fp"),
                })
        book.append(row)
    with open(os.path.join(OUT, "kalshi_compact.json"), "w", encoding="utf-8") as fh:
        json.dump({"retrieved_at_utc": now_iso(), "events_url": KALSHI_EVENTS,
                   "events": book}, fh, indent=1, ensure_ascii=False)
    stats["kalshi"]["quotes"] = len([l for l in lines if l["source_key"] == "kalshi"])


# --------------------------------------------------------------------------- Polymarket
PM_URLS = ["https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike",
           "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=esports"]


def collect_polymarket(lines, stats):
    stats["polymarket"] = {"urls": PM_URLS, "quotes": 0, "events_with_cs2": 0}
    seen = set()
    for url in PM_URLS:
        st, body = get(url)
        data = jload(body)
        stats["polymarket"][url] = {"status": st,
                                    "events": len(data) if isinstance(data, list) else None}
        if not isinstance(data, list):
            continue
        for ev in data:
            title = str(ev.get("title") or "")
            if not CS2_RE.search(title):
                continue
            stats["polymarket"]["events_with_cs2"] += 1
            for mk in (ev.get("markets") or []):
                outs = mk.get("outcomes")
                prices = mk.get("outcomePrices")
                for val, key in ((outs, "outcomes"), (prices, "prices")):
                    if isinstance(val, str):
                        try:
                            if key == "outcomes":
                                outs = json.loads(val)
                            else:
                                prices = json.loads(val)
                        except Exception:  # noqa: BLE001
                            pass
                if not isinstance(outs, list) or not isinstance(prices, list) or not prices:
                    continue
                key = (ev.get("slug"), mk.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                p = [as_number(x) for x in prices]
                lines.append({
                    "source_key": "polymarket",
                    "source_name": "Polymarket",
                    "source_kind": "public prediction market",
                    "source_public_url": f"https://polymarket.com/event/{ev.get('slug')}",
                    "source_api_url": url,
                    "source_event_id": str(ev.get("id")),
                    "source_market_id": str(mk.get("id")),
                    "source_league": title,
                    "market_type": "match winner (prediction market)",
                    "market_is_live": not bool(mk.get("closed")),
                    "market_status": "open" if not mk.get("closed") else "closed",
                    "retrieved_at_utc": now_iso(),
                    "start_time_utc": ev.get("endDate") or mk.get("endDate"),
                    "team_a_name": outs[0] if len(outs) > 0 else None,
                    "team_b_name": outs[1] if len(outs) > 1 else None,
                    "raw_price_format": "probability_0_1",
                    "raw_prices": prices,
                    "market_volume": mk.get("volume"),
                    "market_liquidity": mk.get("liquidity"),
                })
    stats["polymarket"]["quotes"] = len([l for l in lines if l["source_key"] == "polymarket"])


# --------------------------------------------------------------------------- Kambi tenants
KAMBI_TENANTS = [("betriversus", "en_US", "US", "BetRivers"),
                 ("betrivers", "en_US", "US", "BetRivers PA"),
                 ("nordicbet", "en_GB", "MT", "NordicBet"),
                 ("betsson", "en_GB", "MT", "Betsson"),
                 ("otonl", "nl_NL", "NL", "OTO"),
                 ("bethard", "en_GB", "MT", "Bethard")]


def collect_kambi(lines, stats):
    stats["kambi"] = {}
    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    for tenant, lang, market, label in KAMBI_TENANTS:
        url = (f"https://eu-offering-api.kambicdn.com/offering/v2018/{tenant}/esports/all/all/"
               f"matches.json?lang={lang}&market={market}&client_id=2&channel_id=1&ncid={ts}")
        st, body = get(url)
        data = jload(body)
        rec = {"url": url, "status": st}
        if isinstance(data, dict):
            rec["events"] = len(data.get("events") or [])
            rec["bet_offers"] = len(data.get("betOffers") or [])
        stats["kambi"][tenant] = rec
        if not isinstance(data, dict):
            continue
        events = {e.get("id"): e for e in (data.get("events") or [])}
        n = 0
        for bo in (data.get("betOffers") or []):
            ev = events.get(bo.get("eventId"))
            if not ev:
                continue
            path = json.dumps(ev.get("path") or []) + json.dumps(ev.get("group") or "")
            if not CS2_RE.search(path):
                continue
            bet_type = str((bo.get("betOfferType") or {}).get("name", ""))
            if bet_type.lower() not in ("match", "winner", "head to head", "moneyline", "main"):
                continue
            outs = bo.get("outcomes") or []
            if len(outs) != 2:
                continue
            odds = [o.get("odds") for o in outs]
            if not all(isinstance(o, int) and o > 1000 for o in odds):
                continue
            n += 1
            lines.append({
                "source_key": f"kambi_{tenant}",
                "source_name": f"{label} (Kambi)",
                "source_kind": "licensed bookmaker",
                "source_public_url": f"https://www.{tenant}.com/",
                "source_api_url": url,
                "source_event_id": str(ev.get("id")),
                "source_market_id": str(bo.get("id")),
                "source_league": " / ".join(str(p.get("name")) for p in (ev.get("path") or [])),
                "market_type": f"match winner ({bet_type})",
                "market_is_live": bool(bo.get("live")),
                "market_status": bo.get("state"),
                "retrieved_at_utc": now_iso(),
                "start_time_utc": ev.get("start"),
                "team_a_name": outs[0].get("label"),
                "team_b_name": outs[1].get("label"),
                "raw_price_format": "kambi_odds_x1000",
                "raw_price_a": odds[0],
                "raw_price_b": odds[1],
                "decimal_odds_a": round(odds[0] / 1000.0, 6),
                "decimal_odds_b": round(odds[1] / 1000.0, 6),
                "decimal_odds_derived": True,
            })
        rec["cs2_quotes"] = n


def main() -> int:
    global NOW
    NOW = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(OUT, exist_ok=True)
    lines: list[dict] = []
    stats: dict = {"collected_at_utc": NOW}

    collect_pinnacle(lines, stats)
    collect_bovada(lines, stats)
    collect_kalshi(lines, stats)
    collect_polymarket(lines, stats)
    collect_kambi(lines, stats)

    with open(os.path.join(OUT, "lines.json"), "w", encoding="utf-8") as fh:
        json.dump({"collected_at_utc": NOW,
                   "rules": ["Every price is a raw quote from the named URL at retrieved_at_utc.",
                             "Only match/series-winner markets are collected.",
                             "A missing price stays missing: nothing is inferred or extrapolated."],
                   "counts": {"quotes": len(lines)},
                   "lines": lines}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "lines_sources.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=1, ensure_ascii=False)
    print("quotes:", len(lines))
    print(json.dumps({k: v for k, v in stats.items() if k != "collected_at_utc"})[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
