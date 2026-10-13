#!/usr/bin/env python3
"""T-EXPAND external line collector.

Enumerates every fixture the HotSpawn Pick'ems lobby lists (its own public fixtures API),
then collects *external* betting lines for them from sources that are not HotSpawn:

  * Pinnacle        — licensed bookmaker, public guest odds API (sport 12 "E Sports")
  * Bovada          — licensed bookmaker, public coupon JSON
  * Melbet / 22Bet / BetWinner — licensed bookmakers on the 1xBet platform, public LineFeed
                      JSON (mirrors are used because 1xbet.com itself is Cloudflare-challenged
                      from datacentre IPs)
  * Polymarket      — public prediction market (only markets that are still open are used)

Outputs (all evidence-first; nothing is inferred):
  data/expanded/fixtures.json   — the lobby fixture snapshot used for this run
  data/expanded/quotes.json     — every raw external quote with its source URL + ids + time
  data/expanded/lines.json      — fixtures joined to quotes, de-vigged, with consensus + flags
  data/expanded/collection_log.json — per-source status and counts (including failures)

HotSpawn is used for fixture discovery only. Its crowd "picked %" is copied into the output as
labelled reference context and is never an input to any probability.

Usage: python3 scripts/expanded/collect_lines.py [--limit-matchups N]
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lines_core import (TIME_TOLERANCE_MIN,   # noqa: E402
    american_to_decimal, consensus, implied, join_quote, minutes_between, norm, parse_iso, to_utc_iso,
)

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "data" / "expanded"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/",
               "X-Device-UUID": "b9dc3e0e-2f6e-4a5f-9d5c-6a0a5e5b1a11"}
LOBBY_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
LINE_FEED_MIRRORS = [("melbet", "https://melbet.com"), ("22bet", "https://22bet.com"),
                     ("betwinner", "https://betwinner.com")]
ESPORTS_HINTS = ("esport", "counter", "cs2", "csgo", "cyber", "dota", "league of legends",
                 "valorant", "starcraft", "warcraft", "mobile legends")

# Which lobby sport aliases this collector handles (the lobby's own sport_alias values).
GAMES = {"cs2": "CS2", "lol": "LoL"}
LEAGUE_GAME_HINTS = {
    "cs2": ("counter", "cs2", "csgo"),
    "lol": ("league of legends", "lol"),
}
MAX_BYTES = 64 * 1024 * 1024
MAX_QUOTE_MATCHUPS = 400


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url: str, headers: dict | None = None, timeout: int = 45):
    hdrs = dict(BASE_HEADERS)
    if headers:
        hdrs.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs),
                                    timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read(MAX_BYTES)
            return r.status, json.loads(body.decode("utf-8", "replace")), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return 0, None, f"{type(exc).__name__}: {str(exc)[:200]}"


# ------------------------------------------------------------------------- fixtures
def collect_fixtures(log: dict) -> list[dict]:
    url = f"{LOBBY_API}/fixtures"
    status, data, err = fetch_json(url)
    log["fixtures"] = {"url": url, "status": status, "error": err,
                       "count": len(data) if isinstance(data, list) else None}
    if not isinstance(data, list):
        # Fail-over: the repository's scheduled job refreshes this snapshot every 3 hours from
        # the same lobby endpoint. Using it keeps the board building when the API hiccups; the
        # fallback is recorded in the log so the snapshot age is always visible.
        fallback = ROOT / "data" / "hotspawn_matches.json"
        if fallback.exists():
            snap = json.loads(fallback.read_text(encoding="utf-8"))
            log["fixtures"]["fallback"] = {"file": str(fallback.relative_to(ROOT)),
                                           "generated_at_utc": snap.get("generated_at_utc"),
                                           "matches": len(snap.get("matches") or [])}
            data = []
            for m in snap.get("matches") or []:
                data.append({
                    "id": m.get("fixture_id"),
                    "sport_alias": m.get("sport"),
                    "competition_id": m.get("competition_id"),
                    "competition_name": m.get("competition_name"),
                    "tier": m.get("tier"),
                    "stage": m.get("stage"),
                    "best_of": m.get("best_of"),
                    "status": m.get("status"),
                    "scheduled_start_time": m.get("scheduled_start_time"),
                    "lock_time": m.get("lock_time"),
                    "offered_points": m.get("offered_points"),
                    "participants0_id": m.get("team_a_id"),
                    "participants0_name": m.get("team_a"),
                    "participants0_picked_percent": m.get("team_a_pick_pct"),
                    "participants1_id": m.get("team_b_id"),
                    "participants1_name": m.get("team_b"),
                    "participants1_picked_percent": m.get("team_b_pick_pct"),
                    "total_picks": m.get("total_picks"),
                })
        else:
            return []
    out = []
    skipped = {"ended": 0, "other_sport": 0}
    for f in data:
        sport = str(f.get("sport_alias") or "").lower()
        if sport not in GAMES:
            skipped["other_sport"] += 1
            continue
        # Same window rule the repository's own lobby collector uses: a fixture that the API
        # marks "ended" can no longer be offered by the lobby, so it is not part of the board.
        if str(f.get("status") or "").lower() in ("ended", "cancelled", "canceled"):
            skipped["ended"] += 1
            continue
        start = f.get("scheduled_start_time")
        out.append({
            "fixture_id": str(f.get("id")),
            "game": GAMES[sport],
            "sport_alias": sport,
            "competition_id": str(f.get("competition_id") or ""),
            "competition_name": f.get("competition_name"),
            "tier": (f.get("tier") or "").lower() or None,
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "status": f.get("status"),
            "scheduled_start_time": start,
            "lock_time": f.get("lock_time"),
            "offered_points": f.get("offered_points"),
            "team_a_id": str(f.get("participants0_id") or ""),
            "team_a": f.get("participants0_name"),
            "team_a_pick_pct": f.get("participants0_picked_percent"),
            "team_b_id": str(f.get("participants1_id") or ""),
            "team_b": f.get("participants1_name"),
            "team_b_pick_pct": f.get("participants1_picked_percent"),
            "total_picks": f.get("total_picks"),
            "source": {"api": url, "page": LOBBY_PAGE,
                       "hotspawn_match_url": f"https://www.hotspawn.com/matches/{f.get('id')}"},
        })
    log["fixtures"]["skipped"] = skipped
    log["fixtures"]["by_game"] = {g: sum(1 for x in out if x["game"] == g) for g in set(GAMES.values())}
    return out


# ------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(quotes: list[dict], log: dict, game_filter: set[str]) -> None:
    url = f"{PIN}/sports/12/matchups"
    status, matchups, err = fetch_json(url, PIN_HEADERS)
    log["pinnacle"] = {"url": url, "status": status, "error": err}
    if not isinstance(matchups, list):
        return
    goals = [m for m in matchups if m.get("type") == "matchup" and len(m.get("participants") or []) == 2]
    relevant = []
    for m in goals:
        league = ((m.get("league") or {}).get("name") or "").lower()
        for game, hints in LEAGUE_GAME_HINTS.items():
            if game_filter and game not in game_filter:
                continue
            if any(h in league for h in hints):
                relevant.append((game, m))
                break
    log["pinnacle"].update({"matchups_total": len(goals), "matchups_relevant": len(relevant)})
    for game, m in relevant[:MAX_QUOTE_MATCHUPS]:
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        st, markets, err2 = fetch_json(murl, PIN_HEADERS)
        if not isinstance(markets, list):
            log["pinnacle"].setdefault("market_errors", []).append({"id": mid, "status": st, "error": err2})
            continue
        parts = m.get("participants") or []
        cands = [mk for mk in markets
                 if str(mk.get("type", "")).lower() == "moneyline" and mk.get("period") == 0
                 and not mk.get("isAlternate") and isinstance(mk.get("prices"), list)
                 and len(mk["prices"]) == 2 and all(p.get("price") is not None for p in mk["prices"])]
        for mk in cands[:1]:
            by = {p.get("designation"): p.get("price") for p in mk["prices"]}
            a_am = by.get("home") if parts[0].get("alignment") == "home" else by.get("away")
            b_am = by.get("home") if parts[1].get("alignment") == "home" else by.get("away")
            quotes.append({
                "source_key": "pinnacle", "source_name": "Pinnacle",
                "source_kind": "licensed bookmaker", "game": game,
                "source_public_url": "https://www.pinnacle.com/en/esports/",
                "source_api_url": murl,
                "source_event_id": str(mid), "source_market_id": str(mk.get("id")),
                "source_league": (m.get("league") or {}).get("name"),
                "market_type": "match winner (moneyline, full match)",
                "market_is_live": bool(mk.get("isLive")), "market_status": mk.get("status"),
                "retrieved_at_utc": now_iso(), "start_time_utc": to_utc_iso(parse_iso(m.get("startTime"))),
                "team_a_name": parts[0].get("name"), "team_b_name": parts[1].get("name"),
                "raw_price_format": "american", "raw_price_a": a_am, "raw_price_b": b_am,
                "decimal_odds_a": american_to_decimal(a_am), "decimal_odds_b": american_to_decimal(b_am),
                "decimal_odds_derived": True,
            })
        time.sleep(0.2)


# --------------------------------------------------------------------------- Bovada
def collect_bovada(quotes: list[dict], log: dict, game_filter: set[str]) -> None:
    url = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
    status, data, err = fetch_json(url)
    log["bovada"] = {"url": url, "status": status, "error": err}
    if not isinstance(data, list):
        return
    events = cs2 = lol = 0
    for group in data:
        path = " ".join(str(p.get("link") or "") for p in (group.get("path") or [])).lower()
        if "counter-strike" in path:
            game = "cs2"
        elif "league-of-legends" in path:
            game = "lol"
        else:
            continue
        if game_filter and game not in game_filter:
            continue
        for ev in (group.get("events") or []):
            events += 1
            comps = ev.get("competitors") or []
            if len(comps) != 2:
                continue
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if str(mk.get("description", "")).strip().lower() != "moneyline":
                        continue
                    if not ((mk.get("period") or {}).get("main")):
                        continue  # excludes Map 1/2/3 moneylines
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    dec = [((o.get("price") or {}).get("decimal")) for o in outs]
                    if not all(dec):
                        continue
                    if game == "cs2":
                        cs2 += 1
                    else:
                        lol += 1
                    quotes.append({
                        "source_key": "bovada", "source_name": "Bovada",
                        "source_kind": "licensed bookmaker", "game": game,
                        "source_public_url": "https://www.bovada.lv" + str(ev.get("link") or ""),
                        "source_api_url": url,
                        "source_event_id": str(ev.get("id")), "source_market_id": str(mk.get("id")),
                        "source_league": (group.get("path") or [{}])[0].get("description"),
                        "market_type": "match winner (moneyline, full match)",
                        "market_is_live": bool(ev.get("live")), "market_status": mk.get("status"),
                        "retrieved_at_utc": now_iso(),
                        "start_time_utc": to_utc_iso(parse_iso(ev.get("startTime"))),
                        "team_a_name": comps[0].get("name"), "team_b_name": comps[1].get("name"),
                        "raw_price_format": "decimal", "raw_price_a": dec[0], "raw_price_b": dec[1],
                        "decimal_odds_a": float(dec[0]), "decimal_odds_b": float(dec[1]),
                        "decimal_odds_derived": False,
                    })
    log["bovada"].update({"events_scanned": events, "moneyline_rows": {"cs2": cs2, "lol": lol}})


# ------------------------------------------------------- 1xBet family (Melbet/22Bet/Betwinner)
def linefeed_sports_ids(log: dict) -> list[int]:
    url = ("https://melbet.com/service-api/LineFeed/GetSportsShortZip"
           "?sports=1&lng=en&country=1&virtualSports=true&groupChamps=true")
    status, data, err = fetch_json(url)
    log["linefeed_sports"] = {"url": url, "status": status, "error": err}
    ids = []
    if isinstance(data, dict):
        value = data.get("Value")
        items = value.get("_items") if isinstance(value, dict) else value
        for it in items or []:
            if not isinstance(it, dict):
                continue
            name = " ".join(str(it.get(k) or "") for k in ("N", "SE", "SN", "E")).casefold()
            if any(h in name for h in ESPORTS_HINTS) and isinstance(it.get("I"), int):
                ids.append((it["I"], str(it.get("SE") or it.get("N") or it.get("SN"))))
    log["linefeed_sports"]["esports_sport_ids"] = ids
    return sorted({i for i, _ in ids})


def collect_linefeed(quotes: list[dict], log: dict, game_filter: set[str]) -> None:
    """Collect the 1xBet-platform match moneylines.

    Melbet, 22Bet and BetWinner are three mirrors of one platform and quote identical prices,
    so only ONE of them is published as a source. The other mirrors are still fetched and their
    event-id/price agreement with the primary is recorded, so a mirror outage is visible instead
    of silently changing the consensus.
    """
    ids = linefeed_sports_ids(log)
    if not ids:
        ids = [40]
    log["linefeed"] = {"sport_ids": ids, "mirrors": [], "primary": None, "published_quotes": 0}
    per_mirror: dict[str, dict] = {}
    for mirror_key, base in LINE_FEED_MIRRORS:
        events: dict[str, tuple[str, str, float, float, str, str, str]] = {}
        epochs: dict[str, object] = {}
        info = {"mirror": mirror_key, "urls": [], "events": 0, "moneyline_events": 0,
                "by_league": {}, "errors": [], "game_counts": {}}
        for sid in ids:
            url = (f"{base}/service-api/LineFeed/Get1x2_VZip"
                   f"?sports={sid}&count=1000&lng=en&mode=4&country=1")
            info["urls"].append(url)
            status, data, err = fetch_json(url)
            if not isinstance(data, dict):
                info["errors"].append(f"{url} -> {status} {err}")
                continue
            value = data.get("Value")
            rows = value.get("_items") if isinstance(value, dict) else value
            if not isinstance(rows, list):
                continue
            for ev in rows:
                info["events"] += 1
                league = ev.get("LE") or ev.get("L")
                game = guess_game(str(ev.get("SN") or ev.get("SE") or ""), league)
                if game:
                    info["game_counts"][game] = info["game_counts"].get(game, 0) + 1
                parsed = parse_linefeed_event(ev)
                if not parsed:
                    continue
                info["moneyline_events"] += 1
                info["by_league"][str(league)[:60]] = info["by_league"].get(str(league)[:60], 0) + 1
                if not game or (game_filter and game not in game_filter):
                    continue
                events[str(ev.get("I"))] = (parsed["team_a"], parsed["team_b"], parsed["dec_a"],
                                            parsed["dec_b"], str(league), url, game)
                epochs[str(ev.get("I"))] = ev.get("S")
        per_mirror[mirror_key] = {"info": info, "events": events, "epochs": epochs}
        time.sleep(0.2)

    primary_key = max(per_mirror, key=lambda k: len(per_mirror[k]["events"])) if per_mirror else None
    log["linefeed"]["primary"] = primary_key
    if primary_key is None:
        return
    primary = per_mirror[primary_key]
    for key, payload in per_mirror.items():
        agreement = {"mirror": key, "events": len(payload["events"]),
                     "matching_ids": None, "price_mismatches": [], "errors": payload["info"]["errors"]}
        if key != primary_key:
            shared = set(payload["events"]) & set(primary["events"])
            agreement["matching_ids"] = len(shared)
            for eid in sorted(shared)[:50]:
                if payload["events"][eid][2:4] != primary["events"][eid][2:4]:
                    agreement["price_mismatches"].append(eid)
        log["linefeed"]["mirrors"].append({**payload["info"], **agreement})

    base = dict(LINE_FEED_MIRRORS)[primary_key]
    for eid, (ta, tb, da, db, league, url, game) in primary["events"].items():
        quotes.append({
            "source_key": "linefeed_1xbet_platform",
            "source_name": f"{primary_key.capitalize()} (1xBet platform, LineFeed)",
            "source_kind": "licensed bookmaker (public LineFeed JSON)",
            "source_platform_note": ("Melbet / 22Bet / BetWinner are mirrors of one platform and quote "
                                     "the same prices; the primary mirror is published once, and mirror "
                                     "agreement is recorded in data/expanded/collection_log.json"),
            "game": game,
            "source_public_url": f"{base}/en/line/esports/",
            "source_api_url": url,
            "source_event_id": eid,
            "source_market_id": "main match moneyline (market type codes T1/T3)",
            "source_league": league,
            "market_type": "match winner (moneyline, 2-way, full match)",
            "market_is_live": False,
            "market_status": "open",
            "retrieved_at_utc": now_iso(),
            "start_time_utc": to_utc_iso(parse_iso(primary["epochs"].get(eid))),
            "team_a_name": ta, "team_b_name": tb,
            "raw_price_format": "decimal", "raw_price_a": da, "raw_price_b": db,
            "decimal_odds_a": da, "decimal_odds_b": db, "decimal_odds_derived": False,
        })
        log["linefeed"]["published_quotes"] += 1


def parse_linefeed_event(ev: dict) -> dict | None:
    """Extract a 2-way match moneyline from a LineFeed event row.

    LineFeed market codes used here: T=1 is outcome "1" (home), T=3 is outcome "2" (away);
    T=2 would be the draw. Entries carry G = market group and P = handicap/total parameter,
    so only parameter-less T1/T3 pairs inside one group are accepted as the match moneyline.
    """
    if not isinstance(ev, dict):
        return None
    team_a = ev.get("O1E") or ev.get("O1")
    team_b = ev.get("O2E") or ev.get("O2")
    if not team_a or not team_b:
        return None
    odds = ev.get("E")
    if not isinstance(odds, list):
        return None
    groups: dict[int, dict] = {}
    for o in odds:
        if not isinstance(o, dict) or "P" in o:
            continue
        if o.get("T") == 1:
            groups.setdefault(o.get("G"), {})["a"] = o.get("C")
        elif o.get("T") == 3:
            groups.setdefault(o.get("G"), {})["b"] = o.get("C")
    complete = {g: v for g, v in groups.items() if v.get("a") and v.get("b")}
    if not complete:
        return None
    group = 1 if 1 in complete else sorted(complete)[0]
    pair = complete[group]
    return {"team_a": str(team_a).strip(), "team_b": str(team_b).strip(),
            "dec_a": float(pair["a"]), "dec_b": float(pair["b"]), "group": group}


def guess_game(sport_name: str, league: str | None) -> str | None:
    """Map a source's own naming to a lobby game.

    The 1xBet-platform feeds label CS2 leagues as e.g. "CS 2. Elisa Esports BreakOut" and the
    sport itself as "Esports", so the league name — not the sport name — carries the title.
    """
    hay = f"{sport_name} {league or ''}".casefold()
    if re.search(r"\bcounter[- ]?strike\b", hay) or re.search(r"\bcs\s*2\b", hay) \
            or re.search(r"\bcs\s*:?\s*go\b", hay) or re.search(r"\bcsgo\b", hay):
        return "cs2"
    if "league of legends" in hay or re.search(r"\blol\b", hay):
        return "lol"
    return None


# ----------------------------------------------------------------------- Polymarket
PM_TITLE = re.compile(r"^(?:Counter-Strike|CS2|League of Legends|LoL)\s*:\s*"
                      r"(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)\s*(?:\((?P<fmt>[^)]*)\))?\s*-\s*(?P<tour>.+)$", re.I)


def collect_polymarket(quotes: list[dict], log: dict, game_filter: set[str]) -> None:
    url = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports"
    status, events, err = fetch_json(url)
    log["polymarket"] = {"url": url, "status": status, "error": err}
    if not isinstance(events, list):
        return
    fresh = 0
    now = datetime.now(tz=timezone.utc)
    for ev in events:
        m = PM_TITLE.match(str(ev.get("title", "")).strip())
        if not m:
            continue
        head = str(ev.get("title", "")).strip().split(":", 1)[0].casefold()
        game = "cs2" if ("counter" in head or "cs2" in head) else "lol"
        if game_filter and game not in game_filter:
            continue
        for mk in ev.get("markets") or []:
            outcomes, prices = mk.get("outcomes"), mk.get("outcomePrices")
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if isinstance(prices, str):
                prices = json.loads(prices)
            if not outcomes or not prices or len(outcomes) != 2 or len(prices) != 2:
                continue
            if mk.get("closed") or not mk.get("active"):
                continue
            end = parse_iso(mk.get("endDate") or ev.get("endDate"))
            if end and end < now:
                continue
            try:
                dec = [round(1 / float(p), 6) if float(p) > 0 else None for p in prices]
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            fresh += 1
            quotes.append({
                "source_key": "polymarket", "source_name": "Polymarket",
                "source_kind": "prediction market", "game": game,
                "source_public_url": f"https://polymarket.com/event/{ev.get('slug')}",
                "source_api_url": url, "source_event_id": str(ev.get("id")),
                "source_market_id": str(mk.get("id")), "source_league": m.group("tour").strip(),
                "market_type": "match winner (event market, share price)",
                "market_is_live": False, "market_status": "open",
                "retrieved_at_utc": now_iso(), "start_time_utc": to_utc_iso(end),
                "team_a_name": m.group("a").strip(), "team_b_name": m.group("b").strip(),
                "raw_price_format": "implied_probability_share",
                "raw_price_a": prices[0], "raw_price_b": prices[1],
                "decimal_odds_a": dec[0], "decimal_odds_b": dec[1],
                "decimal_odds_derived": True,
            })
    log["polymarket"].update({"fresh_markets": fresh})


# --------------------------------------------------------------------------- assembly
def build_lines(fixtures: list[dict], quotes: list[dict], log: dict) -> dict:
    now = datetime.now(tz=timezone.utc)
    rows = []
    used_quote_ids = set()
    for f in fixtures:
        f_dt = parse_iso(f.get("scheduled_start_time"))
        f["start_time_utc"] = to_utc_iso(f_dt)
        f["is_future"] = bool(f_dt and f_dt > now - timedelta(minutes=15))
        matched = []
        for idx, q in enumerate(quotes):
            join = join_quote(f, q)
            if not join:
                continue
            if str(q["game"]).lower() != str(f["game"]).lower():
                continue
            pa, pb, over = implied(q["decimal_odds_a"], q["decimal_odds_b"])
            if join["side_order"] == "reversed":
                pa, pb = pb, pa
            record = dict(q)
            record.update(join)
            record["implied_prob_a"], record["implied_prob_b"] = pa, pb
            record["overround"] = over
            record["fixture_id"] = f["fixture_id"]
            matched.append(record)
            used_quote_ids.add(idx)
        cons = consensus(matched)
        flags = []
        if not matched:
            flags.append("no_external_line_found")
        if not f["is_future"] and f.get("status") == "scheduled":
            flags.append("start_time_in_the_past_but_source_status_scheduled")
        if matched and not f["is_future"]:
            flags.append("line_for_a_fixture_whose_start_time_has_passed")
        rows.append({
            "fixture_id": f["fixture_id"], "game": f["game"], "tier": f["tier"],
            "competition": f["competition_name"], "status": f["status"],
            "start_time_utc": f["start_time_utc"], "is_future": f["is_future"],
            "team_a": f["team_a"], "team_b": f["team_b"],
            "hotspawn_match_url": f["source"]["hotspawn_match_url"],
            "hotspawn_pick_pct_reference_only": {
                "team_a": f["team_a_pick_pct"], "team_b": f["team_b_pick_pct"],
                "total_picks": f.get("total_picks"),
                "note": ("HotSpawn crowd pick percentage — shown for reference only; "
                         "never used as a probability input"),
            },
            "quotes": matched,
            "consensus": cons,
            "pick": (None if not cons else {
                "team": f["team_a"] if cons["prob_a"] >= cons["prob_b"] else f["team_b"],
                "probability": max(cons["prob_a"], cons["prob_b"]),
                "basis": "market consensus (external lines only)",
            }),
            "verification": {
                "status": "verified_external_line" if matched else "unverified_no_external_line",
                "flags": flags,
            },
        })
    unused = [q for i, q in enumerate(quotes) if i not in used_quote_ids]

    # ---------------------------------------------------------------- join diagnostics
    # Every unused quote is explained: which fixtures its team names matched (full and partial),
    # how far the source start time is from the fixture, and why the join was refused. This is the
    # evidence a reviewer needs to see that a blank row means "no external line", not "we gave up".
    diag = []
    for i, q in enumerate(quotes):
        if i in used_quote_ids:
            continue
        full, partial = [], []
        for f in fixtures:
            if str(f["game"]).lower() != str(q["game"]).lower():
                continue
            direct = (same_team(f["team_a"], q["team_a_name"]), same_team(f["team_b"], q["team_b_name"]))
            swap = (same_team(f["team_a"], q["team_b_name"]), same_team(f["team_b"], q["team_a_name"]))
            delta = minutes_between(parse_iso(f.get("scheduled_start_time")), parse_iso(q.get("start_time_utc")))
            entry = {"fixture_id": f["fixture_id"], "teams": f"{f['team_a']} vs {f['team_b']}",
                     "competition": f["competition_name"], "start_time_utc": f.get("start_time_utc"),
                     "start_time_delta_min": round(delta, 1) if delta is not None else None}
            if all(direct) or all(swap):
                full.append(entry)
            elif any(direct) or any(swap):
                partial.append(entry)
        reason = ("both team names match a fixture but the source start time is outside the "
                  f"{TIME_TOLERANCE_MIN} min tolerance" if full else
                  "no fixture has both team names, even though one team name matches others"
                  if partial else
                  "neither team name matches any fixture in the current lobby list")
        diag.append({"source": q.get("source_key"), "source_league": q.get("source_league"),
                     "teams": f"{q['team_a_name']} vs {q['team_b_name']}",
                     "quote_start_time_utc": q.get("start_time_utc"),
                     "reason": reason,
                     "full_name_matches": sorted(full, key=lambda e: abs(e["start_time_delta_min"] or 1e9))[:3],
                     "partial_name_matches": partial[:3]})
    log["joins"] = {"quotes_total": len(quotes), "quotes_joined": len(used_quote_ids),
                    "unused_quotes": len(diag), "diagnostics": diag[:40]}
    future_rows = [r for r in rows if r["is_future"]]
    doc = {
        "generated_at_utc": now_iso(),
        "method": {
            "fixture_source": "HotSpawn lobby public fixtures API (enumeration only)",
            "match_rule": ("both participants match by normalised name/alias table and the source start "
                           "time is within 90 minutes, or — when the source publishes no start time — "
                           "the competition names agree after normalisation"),
            "probability_rule": "p_i = (1/d_i) / sum_j(1/d_j)  [proportional no-vig, per source]",
            "consensus_rule": "arithmetic mean over sources quoting the same fixture",
            "note": "probabilities are DERIVED from quoted market prices, not forecasts",
        },
        "summary": {
            "fixtures_total": len(rows),
            "fixtures_future": len(future_rows),
            "future_with_external_line": sum(1 for r in future_rows if r["quotes"]),
            "future_without_external_line": sum(1 for r in future_rows if not r["quotes"]),
            "future_with_two_or_more_sources": sum(
                1 for r in future_rows if len({q["source_key"] for q in r["quotes"]}) >= 2),
            "quotes_total": len(quotes),
            "quotes_joined": len(used_quote_ids),
            "unused_quotes": len(unused),
            "by_game": {g: {"total": sum(1 for r in rows if r["game"] == g),
                            "future": sum(1 for r in future_rows if r["game"] == g),
                            "priced": sum(1 for r in future_rows if r["game"] == g and r["quotes"])}
                        for g in sorted({r["game"] for r in rows})},
            "by_source": {s: sum(1 for q in quotes if q["source_key"] == s)
                          for s in sorted({q["source_key"] for q in quotes})},
        },
        "fixtures": rows,
        "unused_quotes": unused,
    }
    return doc


def main() -> int:
    try:
        return run()
    except Exception:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        OUTDIR.mkdir(parents=True, exist_ok=True)
        (OUTDIR / "collection_errors.json").write_text(json.dumps(
            {"generated_at_utc": now_iso(), "error": tb}, indent=1), encoding="utf-8")
        print("collector crashed; traceback:\n" + tb)
        return 2


def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-out", default=str(OUTDIR / "lines.json"))
    ap.add_argument("--games", default="cs2,lol")
    args = ap.parse_args()
    game_filter = {g.strip() for g in args.games.split(",") if g.strip()}
    OUTDIR.mkdir(parents=True, exist_ok=True)

    log: dict = {"generated_at_utc": now_iso()}
    fixtures = collect_fixtures(log)
    print(f"fixtures: {len(fixtures)}")
    if not fixtures:
        print("no fixtures collected — aborting without writing (fail closed)")
        (OUTDIR / "collection_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        return 1

    quotes: list[dict] = []
    collect_pinnacle(quotes, log, game_filter)
    print(f"after pinnacle: {len(quotes)}")
    collect_bovada(quotes, log, game_filter)
    print(f"after bovada: {len(quotes)}")
    collect_linefeed(quotes, log, game_filter)
    print(f"after linefeed: {len(quotes)}")
    collect_polymarket(quotes, log, game_filter)
    print(f"after polymarket: {len(quotes)}")

    doc = build_lines(fixtures, quotes, log)
    (OUTDIR / "fixtures.json").write_text(json.dumps(
        {"generated_at_utc": doc["generated_at_utc"], "source": LOBBY_API, "page": LOBBY_PAGE,
         "fixtures": fixtures}, indent=1), encoding="utf-8")
    (OUTDIR / "quotes.json").write_text(json.dumps(
        {"generated_at_utc": doc["generated_at_utc"], "quotes": quotes}, indent=1), encoding="utf-8")
    Path(args.capture_out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    (OUTDIR / "collection_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    s = doc["summary"]
    print(json.dumps({k: v for k, v in s.items() if k != "by_game"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
