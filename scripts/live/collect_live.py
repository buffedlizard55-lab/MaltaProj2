#!/usr/bin/env python3
"""T-COVER collector (session 3cd9787c) — run this on a host with general internet access.

Responsibilities
----------------
1. Enumerate the HotSpawn Pick'ems lobby fixtures from the lobby's own public endpoint and read
   the lobby's own counters off the served page (fixture discovery ONLY — no Pick'ems number is
   ever used as a probability input).
2. Collect two-way match-winner prices for CS2 and LoL from external sources that are not
   HotSpawn, keeping every raw price together with the exact URL, id and read time.
3. Fetch the official Valve CS2 Regional Standings (github.com/ValveSoftware/...) used as the
   rating input for the labelled originated estimate.
4. Write `data/live/fixtures.json`, `data/live/quotes.json`, `data/live/ratings.json`,
   `data/live/collection_log.json` and bounded raw samples under `data/live/samples/`.

Every source is probed independently and its status is recorded, so a blocked or changed source
shows up as an access failure in the evidence instead of silently becoming "no price exists".

Usage: python3 scripts/live/collect_live.py [--outdir data/live]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_core import (  # noqa: E402
    UA, UA_BROWSER, canon_team, extract_lobby_listing, extract_lobby_permalinks, fetch, fetch_json,
    html_to_text, json_dump, now_iso, now_utc, parse_any, parse_lobby_counters, parse_ms, to_iso,
)

ROOT = Path(__file__).resolve().parents[2]
LOBBY_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
GAMES = {"cs2": "CS2", "lol": "LoL"}
LEAGUE_GAME_HINTS = {
    "cs2": ("counter", "cs2", "csgo", "cs:go"),
    "lol": ("league of legends", "lol"),
}
PROP_NAME_RE = re.compile(r"[()]|\byes\b|\bno\b|kills?|maps?|total|handicap|rounds?|first blood",
                          re.I)

# Fixture window kept in the committed snapshot (the rest is summarised by counts only, so the
# repository does not grow by megabytes every hour).
KEEP_PAST_DAYS = 3
KEEP_FUTURE_DAYS = 45


# ------------------------------------------------------------------------------- HotSpawn
def collect_fixtures(log: dict, listed_ids: set[str] | None = None,
                     permalinks: dict[str, str] | None = None) -> list[dict]:
    url = f"{LOBBY_API}/fixtures"
    data, meta = fetch_json(url, {"Accept": "application/json", "Referer": LOBBY_PAGE}, timeout=90)
    log["hotspawn_fixtures"] = meta
    rows = data if isinstance(data, list) else []
    log["hotspawn_fixtures"]["rows"] = len(rows)
    if not rows:
        return []
    listed_ids = listed_ids or set()
    permalinks = permalinks or {}
    link_kinds: dict[str, int] = {}
    now = now_utc()
    lo, hi = now - timedelta(days=KEEP_PAST_DAYS), now + timedelta(days=KEEP_FUTURE_DAYS)
    out, kept, skipped = [], 0, 0
    statuses: dict[str, int] = {}
    games: dict[str, int] = {}
    for f in rows:
        if not isinstance(f, dict):
            continue
        sport = str(f.get("sport_alias") or "").casefold()
        game = sport if sport in GAMES else None
        status = str(f.get("status") or "")
        statuses[status] = statuses.get(status, 0) + 1
        games[sport] = games.get(sport, 0) + 1
        start = parse_ms(f.get("scheduled_start_time"))
        lock = parse_ms(f.get("lock_time"))
        in_window = start is not None and lo <= start <= hi
        # A fixture the lobby page is listing is always kept, whatever its start time says, so the
        # board can never miss a match the user can actually pick.
        must_keep = str(f.get("id")) in listed_ids
        if not in_window and not must_keep:
            skipped += 1
            continue
        kept += 1 if in_window else 0
        out.append({
            "fixture_id": str(f.get("id")),
            "game": GAMES.get(game) if game else None,
            "sport_alias": sport,
            "competition_id": str(f.get("competition_id") or ""),
            "competition": f.get("competition_name"),
            "tier": (f.get("tier") or None),
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "status": status,
            "start_time_utc": to_iso(start),
            "lock_time_utc": to_iso(lock),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "offered_points": f.get("offered_points"),
            "team_a_id": str(f.get("participants0_id") or ""),
            "team_a": f.get("participants0_name"),
            "team_b_id": str(f.get("participants1_id") or ""),
            "team_b": f.get("participants1_name"),
            "listed_in_lobby_hint": bool(must_keep),
            "hotspawn_pick_pct_reference_only": {
                "team_a": f.get("participants0_picked_percent"),
                "team_b": f.get("participants1_picked_percent"),
                "note": ("HotSpawn crowd Pick'ems percentage, published for reference only. It is "
                         "never read by any probability or estimate function in this pipeline."),
            },
            "source": {
                "api": url,
                "page": LOBBY_PAGE,
                "hotspawn_match_url": permalinks.get(str(f.get("id"))) or LOBBY_PAGE,
                "hotspawn_match_url_kind": ("lobby_published_permalink"
                                            if str(f.get("id")) in permalinks
                                            else "official_lobby_fallback"),
            },
        })
    log["hotspawn_fixtures"].update({
        "status_counts_all_rows": statuses,
        "game_counts_all_rows": games,
        "kept_in_snapshot": kept,
        "force_kept_from_lobby_listing": sum(1 for r in out if r.get("listed_in_lobby_hint")),
        "omitted_outside_window": skipped,
        "window": {"from": to_iso(lo), "to": to_iso(hi),
                   "rule": f"start time within -{KEEP_PAST_DAYS}d..+{KEEP_FUTURE_DAYS}d of collect time"},
    })
    return out


def collect_lobby_page(log: dict, sample_dir: Path | None = None) -> dict:
    res = fetch(LOBBY_PAGE, {"Accept": "text/html", "User-Agent": UA_BROWSER}, timeout=60)
    counters: dict = {}
    if res["body"]:
        text = res["body"].decode("utf-8", "replace")
        counters = parse_lobby_counters(text)
        listing = extract_lobby_listing(text)
        counters["listing"] = {k: v for k, v in listing.items() if k != "listed_ids"}
        counters["listing_ids_sample"] = listing["listed_ids"][:5]
        # Ids are kept out of the counters blob only to keep the log readable; they travel with the
        # fixture snapshot below.
        counters["listing_ids"] = listing["listed_ids"]
        if sample_dir is not None:
            # stored as .txt: the raw page is inert evidence and must not be treated as a site page by
            # any link checker (the staged-site check walks every .html file in the artifact).
            save_sample(sample_dir, "lobby_page.txt", text, limit=600_000)
    log["lobby_page"] = {k: v for k, v in res.items() if k != "body"}
    log["lobby_page"]["counters"] = {k: v for k, v in counters.items() if k != "listing_ids"}
    return counters


# -------------------------------------------------------------------------- Valve VRS
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_BRANCH = "main"
VRS_DIR = "live/2026"
VRS_REGIONS = ("global", "europe", "americas", "asia")


def vrs_latest(log: dict) -> dict:
    url = f"https://api.github.com/repos/{VRS_REPO}/git/trees/{VRS_BRANCH}?recursive=1"
    data, meta = fetch_json(url, {"Accept": "application/vnd.github+json"}, timeout=90)
    log["valve_vrs_tree"] = meta
    tree = (data or {}).get("tree") if isinstance(data, dict) else None
    newest: dict[str, str] = {}
    if isinstance(tree, list):
        for node in tree:
            path = str((node or {}).get("path") or "")
            m = re.match(rf"{VRS_DIR}/standings_([a-z]+)_(\d{{4}}_\d{{2}}_\d{{2}})\.md$", path)
            if not m or m.group(1) not in VRS_REGIONS:
                continue
            region, date = m.group(1), m.group(2)
            if region not in newest or date > newest[region]:
                newest[region] = date
    log["valve_vrs_tree"]["paths_parsed"] = len(newest)
    ratings: dict[str, dict] = {}
    files: dict[str, dict] = {}
    for region in VRS_REGIONS:
        date = newest.get(region)
        if not date:
            continue
        api_url = (f"https://api.github.com/repos/{VRS_REPO}/contents/{VRS_DIR}/"
                   f"standings_{region}_{date}.md")
        raw_url = f"https://raw.githubusercontent.com/{VRS_REPO}/{VRS_BRANCH}/{VRS_DIR}/standings_{region}_{date}.md"
        blob, meta2 = fetch_json(api_url, {"Accept": "application/vnd.github+json"}, timeout=90)
        text = None
        via = None
        if isinstance(blob, dict) and blob.get("content"):
            try:
                text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
                via = "api.github.com contents (base64)"
            except Exception:  # noqa: BLE001
                text = None
        files[region] = {**{k: v for k, v in meta2.items() if k != "body"},
                         "snapshot": date, "raw_url": raw_url, "via": via}
        if not text:
            continue
        from live_core import vrs_markdown_rows  # local import keeps module import side-effect free
        rows = vrs_markdown_rows(text)
        files[region]["teams_parsed"] = len(rows)
        for key, rec in rows.items():
            cur = ratings.get(key)
            # Regions overlap (a team can appear in both global and its regional table). Keep the
            # record with the most points and remember every region it was seen in.
            if cur is None or rec["points"] > cur["points"]:
                ratings[key] = {
                    "team": rec["team"],
                    "points": rec["points"],
                    "standing": rec["standing"],
                    "region": region,
                    "snapshot": date,
                    "source_url": api_url,
                    "raw_url": raw_url,
                    "roster": rec.get("roster") or "",
                }
            elif cur is not None and region not in str(cur.get("also_regions", "")):
                cur.setdefault("also_regions", []).append(region)
        time.sleep(0.3)
    return {"ratings": ratings, "files": files, "snapshots": newest}


# ------------------------------------------------------------------------------ Pinnacle
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "Referer": "https://www.pinnacle.com/",
    "Accept": "application/json",
}


def save_sample(sample_dir: Path, name: str, payload, limit: int = 200_000) -> None:
    """Persist a bounded, verbatim sample of what a source served (evidence, never re-typed)."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    target = sample_dir / name
    if isinstance(payload, (bytes, bytearray)):
        text = bytes(payload[:limit]).decode("utf-8", "replace")
    elif isinstance(payload, str):
        text = payload[:limit]
    else:
        text = json.dumps(payload, indent=1)[:limit]
    target.write_text(text, encoding="utf-8")


def collect_pinnacle(quotes: list[dict], log: dict, sample_dir: Path | None = None) -> None:
    url = f"{PIN}/sports/12/matchups"
    data, meta = fetch_json(url, PIN_HEADERS)
    entry = {**{k: v for k, v in meta.items() if k != "body"}, "type": "matchups list"}
    log["pinnacle"] = entry
    if sample_dir is not None:
        save_sample(sample_dir, "pinnacle_matchups_head.json",
                    data[:8] if isinstance(data, list) else data)
    if not isinstance(data, list):
        return
    matchups = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
                and len(m.get("participants") or []) == 2]
    relevant = []
    for m in matchups:
        league = ((m.get("league") or {}).get("name") or "")
        for game, hints in LEAGUE_GAME_HINTS.items():
            if any(h in league.casefold() for h in hints):
                relevant.append((game, m))
                break
    entry.update({"matchups_total": len(matchups), "matchups_relevant": len(relevant)})
    rows_written = 0
    for game, m in relevant:
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        markets, meta2 = fetch_json(murl, PIN_HEADERS)
        if not isinstance(markets, list):
            entry.setdefault("market_errors", []).append(
                {"matchup": mid, **{k: v for k, v in meta2.items() if k != "body"}})
            continue
        parts = m.get("participants") or []
        names = [str(p.get("name") or "") for p in parts]
        if any(PROP_NAME_RE.search(n) for n in names):
            continue
        cands = [mk for mk in markets
                 if str(mk.get("type", "")).casefold() == "moneyline" and mk.get("period") == 0
                 and not mk.get("isAlternate") and isinstance(mk.get("prices"), list)
                 and len(mk["prices"]) == 2
                 and all(p.get("price") is not None for p in mk["prices"])]
        for mk in cands[:1]:
            by = {p.get("designation"): p.get("price") for p in mk["prices"]}
            if parts[0].get("alignment") == "home":
                a_am, b_am = by.get("home"), by.get("away")
            else:
                a_am, b_am = by.get("away"), by.get("home")
            if a_am is None or b_am is None:
                continue
            from live_core import american_to_decimal
            dec_a, dec_b = american_to_decimal(a_am), american_to_decimal(b_am)
            if dec_a is None or dec_b is None:
                continue
            quotes.append({
                "source_key": "pinnacle", "source_name": "Pinnacle",
                "source_kind": "licensed bookmaker", "game": game,
                "source_public_url": "https://www.pinnacle.com/en/esports/",
                "source_api_url": murl,
                "source_event_id": str(mid), "source_market_id": str(mk.get("id")),
                "source_league": (m.get("league") or {}).get("name"),
                "market_type": "match winner (moneyline, full match)",
                "market_is_live": bool(mk.get("isLive")), "market_status": mk.get("status"),
                "retrieved_at_utc": now_iso(),
                "start_time_utc": to_iso(parse_any(m.get("startTime"))),
                "start_time_raw": m.get("startTime"),
                "team_a_name": names[0], "team_b_name": names[1],
                "raw_price_format": "american", "raw_price_a": a_am, "raw_price_b": b_am,
                "decimal_odds_a": dec_a, "decimal_odds_b": dec_b, "decimal_odds_derived": True,
                "confidence": "market",
            })
            rows_written += 1
        time.sleep(0.15)
    entry["quotes_written"] = rows_written


# -------------------------------------------------------------------------------- Bovada
def collect_bovada(quotes: list[dict], log: dict, sample_dir: Path | None = None) -> None:
    url = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
    data, meta = fetch_json(url, {"Accept": "application/json"})
    entry = {**{k: v for k, v in meta.items() if k != "body"}, "type": "coupon"}
    log["bovada"] = entry
    if sample_dir is not None:
        save_sample(sample_dir, "bovada_esports_head.json",
                    [{**g, "events": (g.get("events") or [])[:2]}
                     for g in (data[:3] if isinstance(data, list) else [])])
    if not isinstance(data, list):
        return
    events = 0
    written = 0
    for group in data:
        if not isinstance(group, dict):
            continue
        path = " ".join(str(p.get("link") or "") for p in (group.get("path") or [])).casefold()
        if "counter-strike" in path:
            game = "cs2"
        elif "league-of-legends" in path:
            game = "lol"
        else:
            continue
        for ev in (group.get("events") or []):
            events += 1
            comps = ev.get("competitors") or []
            if len(comps) != 2:
                continue
            names = [str(c.get("name") or "") for c in comps]
            if any(PROP_NAME_RE.search(n) for n in names):
                continue
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if str(mk.get("description", "")).strip().casefold() != "moneyline":
                        continue
                    if not (mk.get("period") or {}).get("main"):
                        continue
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    dec = [((o.get("price") or {}).get("decimal")) for o in outs]
                    if not all(dec):
                        continue
                    from live_core import parse_iso
                    start = parse_iso(ev.get("startTime"))
                    quotes.append({
                        "source_key": "bovada", "source_name": "Bovada",
                        "source_kind": "licensed bookmaker", "game": game,
                        "source_public_url": "https://www.bovada.lv" + str(ev.get("link") or ""),
                        "source_api_url": url,
                        "source_event_id": str(ev.get("id")), "source_market_id": str(mk.get("id")),
                        "source_league": (group.get("path") or [{}])[0].get("description"),
                        "market_type": "match winner (moneyline, full match)",
                        "market_is_live": bool(ev.get("live")), "market_status": mk.get("status"),
                        "retrieved_at_utc": now_iso(), "start_time_utc": to_iso(start),
                        "team_a_name": names[0], "team_b_name": names[1],
                        "raw_price_format": "decimal", "raw_price_a": float(dec[0]),
                        "raw_price_b": float(dec[1]), "decimal_odds_a": float(dec[0]),
                        "decimal_odds_b": float(dec[1]), "decimal_odds_derived": False,
                        "confidence": "market",
                    })
                    written += 1
    entry.update({"events_scanned": events, "quotes_written": written})


# ------------------------------------------------------- 1xBet platform (Melbet/22Bet/BetWinner)
LINE_FEED_MIRRORS = [("melbet", "https://melbet.com"), ("22bet", "https://22bet.com"),
                     ("betwinner", "https://betwinner.com"), ("1xbet", "https://1xbet.com")]
ESPORTS_HINTS = ("esport", "counter", "cs2", "csgo", "cyber", "dota", "league of legends",
                 "valorant")


def parse_linefeed_event(ev: dict) -> dict | None:
    """Two-way match moneyline from a LineFeed event row (codes T=1 home, T=3 away)."""
    if not isinstance(ev, dict):
        return None
    team_a = ev.get("O1E") or ev.get("O1")
    team_b = ev.get("O2E") or ev.get("O2")
    if not team_a or not team_b:
        return None
    odds = ev.get("E")
    if not isinstance(odds, list):
        return None
    groups: dict = {}
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
    hay = f"{sport_name} {league or ''}".casefold()
    if re.search(r"\bcounter[- ]?strike\b", hay) or re.search(r"\bcs\s*2\b", hay) \
            or re.search(r"\bcs\s*:?\s*go\b", hay) or re.search(r"\bcsgo\b", hay):
        return "cs2"
    if "league of legends" in hay or re.search(r"\blol\b", hay):
        return "lol"
    return None


def mirror_sport_ids(base: str) -> tuple[list[int], dict]:
    """Ask one mirror for its own esports sport ids (they are not guaranteed to be identical)."""
    url = (f"{base}/service-api/LineFeed/GetSportsShortZip"
           "?sports=1&lng=en&country=1&virtualSports=true&groupChamps=true")
    data, meta = fetch_json(url)
    ids: list[int] = []
    if isinstance(data, dict):
        value = data.get("Value")
        items = value.get("_items") if isinstance(value, dict) else value
        for it in items or []:
            if not isinstance(it, dict):
                continue
            name = " ".join(str(it.get(k) or "") for k in ("N", "SE", "SN", "E")).casefold()
            if any(h in name for h in ESPORTS_HINTS) and isinstance(it.get("I"), int):
                ids.append(int(it["I"]))
    return ids, {k: v for k, v in meta.items() if k != "body"}


def collect_linefeed(quotes: list[dict], log: dict, sample_dir: Path | None = None) -> None:
    entry: dict = {"mirrors": [], "sport_id_discovery": {}}
    log["linefeed"] = entry
    ids: list[int] = []
    for mirror_key, base in LINE_FEED_MIRRORS:
        try:
            found, meta = mirror_sport_ids(base)
        except Exception as exc:  # noqa: BLE001
            entry["sport_id_discovery"][mirror_key] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        entry["sport_id_discovery"][mirror_key] = {**meta, "esports_sport_ids": sorted(set(found))}
        ids.extend(found)
    entry["esports_sport_ids"] = sorted(set(ids))
    if not ids:
        ids = [40]
    per_mirror: dict[str, dict] = {}
    for key, base in LINE_FEED_MIRRORS:
        events: dict[str, dict] = {}
        info = {"mirror": key, "urls": [], "events": 0, "with_moneyline": 0, "errors": []}
        for sid in sorted(set(ids)):
            url = (f"{base}/service-api/LineFeed/Get1x2_VZip"
                   f"?sports={sid}&count=1000&lng=en&mode=4&country=1")
            info["urls"].append(url)
            payload, meta2 = fetch_json(url)
            if not isinstance(payload, dict):
                info["errors"].append({"url": url, "status": meta2.get("status"),
                                       "error": meta2.get("error")})
                continue
            value = payload.get("Value")
            rows = value.get("_items") if isinstance(value, dict) else value
            if not isinstance(rows, list):
                continue
            for ev in rows:
                info["events"] += 1
                league = ev.get("LE") or ev.get("L")
                parsed = parse_linefeed_event(ev)
                if not parsed:
                    continue
                info["with_moneyline"] += 1
                game = guess_game(str(ev.get("SN") or ev.get("SE") or ""), str(league or ""))
                events[str(ev.get("I"))] = {
                    "team_a": parsed["team_a"], "team_b": parsed["team_b"],
                    "dec_a": parsed["dec_a"], "dec_b": parsed["dec_b"],
                    "league": str(league or ""), "game": game,
                    "start_ms": ev.get("S"), "url": url,
                }
        per_mirror[key] = {"info": info, "events": events}
        entry["mirrors"].append(info)
        time.sleep(0.2)
    if not per_mirror:
        return
    primary_key = max(per_mirror, key=lambda k: len(per_mirror[k]["events"]))
    entry["primary_mirror"] = primary_key
    primary = per_mirror[primary_key]
    # Mirror agreement: the three mirrors are one platform, so a mismatch is worth publishing.
    for key, payload in per_mirror.items():
        if key == primary_key:
            continue
        shared = set(payload["events"]) & set(primary["events"])
        mismatches = [eid for eid in sorted(shared)
                      if (payload["events"][eid]["dec_a"], payload["events"][eid]["dec_b"])
                      != (primary["events"][eid]["dec_a"], primary["events"][eid]["dec_b"])]
        for info in entry["mirrors"]:
            if info["mirror"] == key:
                info["shared_event_ids"] = len(shared)
                info["price_mismatches"] = mismatches[:50]
    from live_core import parse_iso
    base = dict(LINE_FEED_MIRRORS)[primary_key]
    written = 0
    for eid, ev in primary["events"].items():
        if ev["game"] not in GAMES:
            continue
        if PROP_NAME_RE.search(f"{ev['team_a']} {ev['team_b']}"):
            continue
        start = parse_ms(ev["start_ms"]) if ev["start_ms"] else None
        quotes.append({
            "source_key": f"linefeed_{primary_key}", "source_name": f"{primary_key.capitalize()} (1xBet platform)",
            "source_kind": "licensed bookmaker (public LineFeed JSON)", "game": ev["game"],
            "source_public_url": f"{base}/en/line/esports/",
            "source_api_url": ev["url"], "source_event_id": eid,
            "source_market_id": "match moneyline (LineFeed market group %s)" % ev.get("group", 1),
            "source_league": ev["league"], "market_type": "match winner (moneyline, full match)",
            "market_is_live": False, "market_status": "open", "retrieved_at_utc": now_iso(),
            "start_time_utc": to_iso(start),
            "team_a_name": ev["team_a"], "team_b_name": ev["team_b"],
            "raw_price_format": "decimal", "raw_price_a": ev["dec_a"], "raw_price_b": ev["dec_b"],
            "decimal_odds_a": ev["dec_a"], "decimal_odds_b": ev["dec_b"],
            "decimal_odds_derived": False, "confidence": "market",
        })
        written += 1
    entry["quotes_written"] = written


# -------------------------------------------------------------------------- EGamersWorld
EGW_MATCH_LINK_RE = re.compile(r"https://egamersworld\.com/(counterstrike|lol)/match/[^\s\)\]\"']+",
                               re.I)
EGW_TITLE_RE = re.compile(r'"([^"]{3,80}?)\s+VS\s+([^"]{1,60}?)"')
DECIMAL_ODD_RE = re.compile(r"\[?\s*(\d{1,2}\.\d{2,3})\s*\]?")
TRANSPORTS = {
    "direct": "{url}",
    "allorigins": "https://api.allorigins.win/raw?url={url}",
    "codetabs": "https://api.codetabs.com/v1/proxy?quest={url}",
    "jina": "https://r.jina.ai/{url}",
}
EGW_PAGES = {
    "egamersworld_cs2": "https://egamersworld.com/counterstrike/matches",
    "egamersworld_lol": "https://egamersworld.com/lol/matches",
}


def extract_egw_rows(text: str, game: str, transport_url: str) -> list[dict]:
    """Pull (match link, pairing, two prices) out of an EGamersWorld listing page.

    The odds widget is server-rendered, so the numbers follow the pairing text in the served
    markup. A row is emitted only when the link, the quoted pairing and two plausible decimal
    prices sit in the same fragment.
    """
    rows = []
    links = list(EGW_MATCH_LINK_RE.finditer(text))
    for i, m in enumerate(links):
        end = links[i + 1].start() if i + 1 < len(links) else min(len(text), m.start() + 700)
        segment = text[m.start():end]
        title = EGW_TITLE_RE.search(segment[:400])
        if not title:
            continue
        tail = segment[title.end() - m.start():][:500]
        numbers = [float(x) for x in DECIMAL_ODD_RE.findall(tail)]
        odds = [n for n in numbers if 1.01 <= n <= 60]
        if len(odds) < 2:
            continue
        rows.append({
            "source_key": "egamersworld", "source_name": "EGamersWorld odds widget",
            "source_kind": "esports odds aggregator (widget bookmaker: bc.game)", "game": game,
            "source_public_url": m.group(0), "source_api_url": transport_url,
            "source_event_id": None, "source_market_id": None, "source_league": None,
            "market_type": "match winner (moneyline, full match)", "market_is_live": False,
            "market_status": "listed", "retrieved_at_utc": now_iso(), "start_time_utc": None,
            "team_a_name": title.group(1).strip(), "team_b_name": title.group(2).strip(),
            "raw_price_format": "decimal", "raw_price_a": odds[0], "raw_price_b": odds[1],
            "decimal_odds_a": odds[0], "decimal_odds_b": odds[1], "decimal_odds_derived": False,
            "confidence": "market",
        })
    return rows


def collect_egamersworld(quotes: list[dict], log: dict, sample_dir: Path) -> None:
    entry: dict = {}
    for page_key, target in EGW_PAGES.items():
        game = "lol" if "/lol/" in target else "cs2"
        attempts = []
        got_rows = 0
        for tname, template in TRANSPORTS.items():
            from urllib.parse import quote as urlquote
            turl = target if tname == "direct" else template.format(url=urlquote(target, safe=""))
            res = fetch(turl, {"Accept": "text/html,text/plain;q=0.9,*/*;q=0.8",
                               "User-Agent": UA_BROWSER}, timeout=40)
            text = res["body"].decode("utf-8", "replace")
            attempt = {"transport": tname, "url": turl, "status": res["status"],
                       "bytes": res["bytes"], "error": res["error"]}
            if res["status"] == 200 and res["bytes"] > 2000 and "egamersworld.com" in text:
                rows = extract_egw_rows(text, game, turl)
                attempt["rows_parsed"] = len(rows)
                attempt["contains_match_link"] = bool(EGW_MATCH_LINK_RE.search(text))
                attempt["contains_vs_title"] = bool(EGW_TITLE_RE.search(text))
                save_sample(sample_dir, f"{page_key}_{tname}.txt", text, limit=400_000)
                attempt["sample_saved"] = f"{page_key}_{tname}.txt"
                if rows:
                    quotes.extend(rows)
                    got_rows += len(rows)
                    attempts.append(attempt)
                    break
            attempts.append(attempt)
            time.sleep(0.3)
        entry[page_key] = {"target": target, "attempts": attempts, "rows": got_rows}
    log["egamersworld"] = entry


# ---------------------------------------------------------- exchanges (reference only)
def collect_kalshi(quotes: list[dict], log: dict, sample_dir: Path | None = None) -> None:
    url = ("https://api.elections.kalshi.com/trade-api/v2/events"
           "?limit=200&status=open&with_nested_markets=true")
    data, meta = fetch_json(url, {"Accept": "application/json"})
    entry = {**{k: v for k, v in meta.items() if k != "body"}, "type": "events+markets"}
    log["kalshi"] = entry
    if sample_dir is not None and isinstance(data, dict):
        save_sample(sample_dir, "kalshi_tickers.json",
                    [{"event_ticker": e.get("event_ticker"), "title": e.get("title"),
                      "sub_title": e.get("sub_title"), "category": e.get("category"),
                      "markets": [{"ticker": m.get("ticker"), "title": m.get("title"),
                                   "yes_bid": m.get("yes_bid"), "yes_ask": m.get("yes_ask")}
                                  for m in (e.get("markets") or [])[:1]]}
                     for e in (data.get("events") or [])])
    events = (data or {}).get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return
    entry["events"] = len(events)
    written = 0
    for ev in events:
        title = str(ev.get("title") or "")
        hay = f"{title} {ev.get('sub_title') or ''}".casefold()
        if not any(h in hay for h in ("counter-strike", "cs2", "league of legends")):
            continue
        for mk in ev.get("markets") or []:
            yes_bid, yes_ask = mk.get("yes_bid"), mk.get("yes_ask")
            if not yes_bid or not yes_ask:
                continue
            mid = (float(yes_bid) + float(yes_ask)) / 2.0 / 100.0
            if not 0.01 <= mid <= 0.99:
                continue
            quotes.append({
                "source_key": "kalshi", "source_name": "Kalshi (exchange)",
                "source_kind": "prediction-market exchange (reference, never averaged)", "game": None,
                "source_public_url": f"https://kalshi.com/markets/{ev.get('event_ticker')}",
                "source_api_url": url, "source_event_id": ev.get("event_ticker"),
                "source_market_id": mk.get("ticker"), "source_league": None,
                "market_type": "binary market %s (mid of bid/ask)" % mk.get("ticker"),
                "market_is_live": False, "market_status": mk.get("status"),
                "retrieved_at_utc": now_iso(), "start_time_utc": None,
                "team_a_name": str(mk.get("title") or ""), "team_b_name": None,
                "raw_price_format": "probability_mid", "raw_price_a": mid, "raw_price_b": None,
                "decimal_odds_a": None, "decimal_odds_b": None, "decimal_odds_derived": False,
                "confidence": "reference",
            })
            written += 1
    entry["quotes_written"] = written


def collect_polymarket(quotes: list[dict], log: dict, sample_dir: Path | None = None) -> None:
    url = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports"
    data, meta = fetch_json(url, {"Accept": "application/json"})
    entry = {**{k: v for k, v in meta.items() if k != "body"}, "type": "events"}
    log["polymarket"] = entry
    if sample_dir is not None and isinstance(data, list):
        save_sample(sample_dir, "polymarket_events_head.json",
                    [{"title": e.get("title"), "slug": e.get("slug"), "outcomes": e.get("outcomes"),
                      "outcomePrices": e.get("outcomePrices"), "tags": [t.get("slug") for t in (e.get("tags") or [])]}
                     for e in data[:40]])
    if not isinstance(data, list):
        return
    entry["events"] = len(data)
    written = 0
    for ev in data:
        title = str(ev.get("title") or "")
        m = re.match(r"^(?:Counter-Strike|CS2|League of Legends|LoL)\s*:\s*(?P<a>.+?)\s+"
                     r"vs\.?\s+(?P<b>.+?)\s*(?:\((?P<fmt>[^)]*)\))?\s*-\s*(?P<tour>.+)$",
                     title, re.I)
        if not m:
            continue
        prices = ev.get("outcomePrices")
        outcomes = ev.get("outcomes")
        try:
            outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            prices = json.loads(prices) if isinstance(prices, str) else prices
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(prices, list) or len(prices) != 2:
            continue
        try:
            pa, pb = float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            continue
        if not (0 < pa < 1 and 0 < pb < 1):
            continue
        game = "cs2" if re.match(r"^Counter-Strike", title, re.I) else "lol"
        quotes.append({
            "source_key": "polymarket", "source_name": "Polymarket (exchange)",
            "source_kind": "prediction-market exchange (reference, never averaged)", "game": game,
            "source_public_url": f"https://polymarket.com/event/{ev.get('slug')}",
            "source_api_url": url, "source_event_id": str(ev.get("id")),
            "source_market_id": None, "source_league": m.group("tour"),
            "market_type": "match winner (binary market last price, whole match)",
            "market_is_live": False, "market_status": "open", "retrieved_at_utc": now_iso(),
            "start_time_utc": None, "team_a_name": m.group("a").strip(),
            "team_b_name": m.group("b").strip(), "raw_price_format": "probability",
            "raw_price_a": pa, "raw_price_b": pb, "decimal_odds_a": None, "decimal_odds_b": None,
            "decimal_odds_derived": False, "confidence": "reference",
            "outcomes": outcomes if isinstance(outcomes, list) else None,
            "volume": ev.get("volume"),
        })
        written += 1
    entry["quotes_written"] = written


# ----------------------------------------------------------------------------------- main
def main() -> int:
    try:
        return _main()
    except Exception:  # noqa: BLE001 - a crash must still leave a readable trace in the evidence
        import traceback
        outdir = ROOT / "data" / "live"
        for i, arg in enumerate(sys.argv):
            if arg == "--outdir" and i + 1 < len(sys.argv):
                outdir = Path(sys.argv[i + 1])
        try:
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "collector_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        traceback.print_exc()
        return 1


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/live")
    args = ap.parse_args()
    outdir = (ROOT / args.outdir) if not Path(args.outdir).is_absolute() else Path(args.outdir)
    sample_dir = outdir / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    # Raw page captures are inert evidence and must never be stored as .html: the site staging step
    # walks every .html file in the published artifact, so a captured page would be checked as if it
    # were one of our pages. Any stale .html capture from an older run is removed here.
    for stale in sample_dir.glob("*.html"):
        stale.unlink()

    log: dict = {"session": "3cd9787c", "task": "T-COVER", "started_at_utc": now_iso(),
                 "notes": [
                     "HotSpawn is used for fixture discovery only; its crowd picked % is never a "
                     "probability input.",
                     "Quotes with confidence=market come from licensed bookmakers or an odds "
                     "aggregator's cited widget; confidence=reference rows are exchanges and are "
                     "published separately, never averaged into the consensus.",
                 ]}

    counters = collect_lobby_page(log, sample_dir)
    listed_ids = {str(i) for i in (counters.get("listing_ids") or [])}
    # Per-match source links come only from permalinks HotSpawn itself publishes on the lobby page.
    permalinks = extract_lobby_permalinks(
        (sample_dir / "lobby_page.txt").read_text(encoding="utf-8", errors="replace")
        if sample_dir is not None and (sample_dir / "lobby_page.txt").is_file() else "")
    log["lobby_page"]["permalinks_published"] = len(permalinks)
    fixtures = collect_fixtures(log, listed_ids, permalinks)
    vrs = vrs_latest(log)

    quotes: list[dict] = []
    collectors = [
        ("pinnacle", lambda: collect_pinnacle(quotes, log, sample_dir)),
        ("bovada", lambda: collect_bovada(quotes, log, sample_dir)),
        ("linefeed", lambda: collect_linefeed(quotes, log, sample_dir)),
        ("egamersworld", lambda: collect_egamersworld(quotes, log, sample_dir)),
        ("kalshi", lambda: collect_kalshi(quotes, log, sample_dir)),
        ("polymarket", lambda: collect_polymarket(quotes, log, sample_dir)),
    ]
    for name, fn in collectors:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the rest
            log.setdefault("source_errors", []).append(
                {"collector": name, "error": f"{type(exc).__name__}: {exc}"})

    # Bounded raw samples so a parser can always be re-checked against real bytes.
    if fixtures:
        json_dump(sample_dir / "fixtures_head.json", fixtures[:3])
    json_dump(sample_dir / "lobby_counters.json", counters)
    market_quotes = [q for q in quotes if q.get("confidence") == "market"]
    json_dump(sample_dir / "quotes_head.json", market_quotes[:5])

    log["finished_at_utc"] = now_iso()
    log["counts"] = {
        "fixtures_in_snapshot": len(fixtures),
        "quotes_total": len(quotes),
        "quotes_market": len(market_quotes),
        "quotes_reference": len(quotes) - len(market_quotes),
        "by_source": {k: sum(1 for q in quotes if q["source_key"] == k)
                      for k in sorted({q["source_key"] for q in quotes})},
        "by_game": {g: sum(1 for q in market_quotes if q.get("game") == g)
                    for g in sorted({q.get("game") for q in market_quotes})},
    }
    log["vrs_snapshots"] = vrs.get("snapshots", {})

    json_dump(outdir / "fixtures.json", {
        "generated_at_utc": log["finished_at_utc"],
        "lobby_page": LOBBY_PAGE,
        "fixtures_api": f"{LOBBY_API}/fixtures",
        "lobby_counters": counters,
        "fixtures": fixtures,
        "source_note": "Fixture inventory from the HotSpawn Pick'ems public endpoint (discovery only).",
    })
    json_dump(outdir / "quotes.json", {
        "generated_at_utc": log["finished_at_utc"], "quotes": quotes,
        "note": "Raw external prices exactly as parsed from each source, with url/id/read time.",
    })
    json_dump(outdir / "ratings.json", {
        "generated_at_utc": log["finished_at_utc"],
        "source": "https://github.com/ValveSoftware/counter-strike_regional_standings",
        "source_kind": "official Valve CS2 Regional Standings",
        "snapshots": vrs.get("snapshots", {}), "files": vrs.get("files", {}),
        "scoring_note": ("Each team's record is the highest-points row across the global and "
                         "regional tables of the newest snapshot; the exact url of the table it "
                         "came from is stored per team."),
        "ratings": vrs.get("ratings", {}),
    })
    json_dump(outdir / "collection_log.json", log)
    print(json.dumps(log.get("counts", {}), indent=1))
    print(json.dumps({k: v for k, v in log.items()
                      if k in ("lobby_page", "valve_vrs_tree")}, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
