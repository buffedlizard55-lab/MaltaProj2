#!/usr/bin/env python3
"""T-FULLCOV collector (session fe803b80). Runs on a GitHub-hosted runner with general internet.

Writes ``data/fe803b80/snapshot.json``: every external two-way match-winner price found for a
HotSpawn CS2 fixture, the external rating inputs used to *originate* a line where no reachable
bookmaker prices the match, and a per-source access log (HTTP status, bytes, error) so that a
blocked source is published as a failure instead of looking like "no price exists".

Sources (all public, unauthenticated, read-only)
-------------------------------------------------
* https://play.hotspawn.com/lobby            fixture discovery only (public Angular transfer state)
* https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures
                                            the same public API the lobby page calls; also the
                                            settlement source for the track record (scores)
* Pinnacle guest odds API (licensed bookmaker)
* Bovada coupon JSON (licensed bookmaker)
* Melbet / 22bet / Betwinner LineFeed JSON (licensed bookmakers, 1xBet platform; mirror families)
* Kalshi trade API, series KXCS2GAME (CFTC-regulated exchange)
* bo3.gg public API — per-fixture **Thunderpick** two-way decimal coefficients (``bet_updates``)
  plus the fixture/team identity it publishes. This is what puts the tier-C matches no other
  reachable bookmaker lists (Elisa BreakOut, CCT play-ins, ...) on a market basis.
* ValveSoftware/counter-strike_regional_standings via api.github.com (official Valve VRS)
* bo3.gg finished-match history for the teams whose matches have no price and no VRS row — the
  input for this project's own Elo line (clearly labelled as an originated model).
* Reachability probes (recorded, never used as prices): HLTV, Polymarket, 22bet/Betwinner mirrors.

Nothing here reads a HotSpawn crowd percentage; ``core.fixture_from_hotspawn`` refuses those fields.
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote as urlquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "fe803b80"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/",
               "Accept": "application/json"}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
LINEFEED = {mirror: f"https://{mirror}.com/service-api/LineFeed/Get1x2_VZip"
                     "?sports=40&count=1000&lng=en&mode=4&country=1"
            for mirror in ("melbet", "22bet", "betwinner")}
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
BO3 = "https://api.bo3.gg/api/v1"
BO3_MATCHES = (f"{BO3}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               "&sort=start_date&page%5Blimit%5D=100")
POLY = "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol", re.I)
LOG: dict = {}
MAX_BO3_HISTORY_TEAMS = 40
MAX_BO3_TEAM_SEARCHES = 24


def fetch(url: str, headers: dict | None = None, timeout: int = 45) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None,
            "at_utc": core.to_iso(core.now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read()
            meta["status"] = r.status
            meta["age_header"] = r.headers.get("Age")
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - network failures are evidence
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    return body, meta


def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    if not body:
        return None, meta
    try:
        return json.loads(body.decode("utf-8", "replace")), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


# --------------------------------------------------------------------------------- HotSpawn
def collect_hotspawn() -> dict:
    page, meta = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=60)
    LOG["hotspawn_lobby_page"] = meta
    state = core.lobby_state(page.decode("utf-8", "replace")) if page else {}
    page_fx = state.get("fixtures") or []
    LOG["hotspawn_lobby_page"]["fixtures_in_transfer_state"] = len(page_fx)
    api_fx, meta2 = fetch_json(HS_API, {"Accept": "application/json", "Referer": LOBBY_PAGE}, 120)
    LOG["hotspawn_api"] = meta2
    api_fx = api_fx if isinstance(api_fx, list) else []
    LOG["hotspawn_api"]["rows"] = len(api_fx)
    fixtures: dict[str, dict] = {}
    for origin, rows in (("lobby_page", page_fx), ("api", api_fx)):
        for raw in rows:
            fx = core.fixture_from_hotspawn(raw)
            if not fx:
                continue
            cur = fixtures.setdefault(fx["fixture_id"], {**fx, "seen_in": []})
            if origin == "api":          # the API response is fresher than the cached page
                cur.update(fx)
            cur["seen_in"].append(origin)
    cutoff = core.to_iso(core.now_utc() - timedelta(days=4))
    status_counts: dict[str, int] = {}
    kept = {}
    for fid, fx in fixtures.items():
        status_counts[str(fx.get("status"))] = status_counts.get(str(fx.get("status")), 0) + 1
        if ("lobby_page" in fx["seen_in"] or fx.get("status") in ("scheduled", "started")
                or fx["start_utc"] >= cutoff):
            kept[fid] = fx
    LOG["hotspawn_api"]["cs2_status_counts_all_rows"] = status_counts
    LOG["hotspawn_api"]["cs2_rows_kept"] = len(kept)
    return {"fixtures": sorted(kept.values(), key=lambda r: (r["start_utc"], r["fixture_id"])),
            "permalinks": state.get("permalinks") or {}, "week": state.get("week")}


# ------------------------------------------------------------------------------ quote helper
def q(source_key, source_name, public_url, api_url, event_id, a, b, dec_a, dec_b, start, league,
      raw_format, raw_a, raw_b, live=False, extra=None):
    nv = core.no_vig(dec_a, dec_b)
    rec = {"source_key": source_key, "source_name": source_name, "public_url": public_url,
           "api_url": api_url, "event_id": str(event_id), "team_a": a, "team_b": b,
           "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
           "raw_format": raw_format, "raw_a": str(raw_a), "raw_b": str(raw_b),
           "prob_a": round(nv["prob_a"], 6) if nv else None,
           "overround": round(nv["overround"], 6) if nv else None,
           "start_utc": core.to_iso(start), "league": league, "live": bool(live),
           "retrieved_utc": core.to_iso(core.now_utc())}
    rec.update(extra or {})
    return rec


# --------------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(quotes: list) -> None:
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    LOG["pinnacle"] = meta
    if not isinstance(data, list):
        return
    cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
          and len(m.get("participants") or []) == 2 and not m.get("parentId")
          and re.match(r"^(CS2|Counter-Strike)", str((m.get("league") or {}).get("name") or ""), re.I)]
    LOG["pinnacle"]["cs2_matchups"] = len(cs)
    written = 0
    for m in cs:
        names = [str(p.get("name") or "") for p in m["participants"]]
        if any(PROP_RE.search(n) for n in names):
            continue
        murl = f"{PIN}/matchups/{m['id']}/markets/related/straight"
        markets, _ = fetch_json(murl, PIN_HEADERS)
        time.sleep(0.1)
        if not isinstance(markets, list):
            continue
        for mk in markets:
            if (mk.get("type") != "moneyline" or mk.get("period") != 0 or mk.get("isAlternate")
                    or mk.get("matchupId") != m["id"] or mk.get("status") != "open"):
                continue
            by = {p.get("designation"): p.get("price") for p in mk.get("prices") or []}
            al = {p.get("alignment"): p.get("name") for p in m["participants"]}
            if None in (by.get("home"), by.get("away"), al.get("home"), al.get("away")):
                continue
            da, db = core.american_to_decimal(by["home"]), core.american_to_decimal(by["away"])
            if da and db:
                quotes.append(q("pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub",
                                murl, m["id"], al["home"], al["away"], da, db,
                                core.parse_iso(str(m.get("startTime") or "").replace("Z", "+00:00")),
                                (m.get("league") or {}).get("name"), "american", by["home"],
                                by["away"], live=bool(m.get("isLive") or mk.get("isLive"))))
                written += 1
            break
    LOG["pinnacle"]["quotes"] = written


# ----------------------------------------------------------------------------------- Bovada
def collect_bovada(quotes: list) -> None:
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    LOG["bovada"] = meta
    written = 0
    for group in data if isinstance(data, list) else []:
        league = ((group.get("path") or [{}])[0]).get("description")
        for ev in group.get("events") or []:
            comps = ev.get("competitors") or []
            if len(comps) != 2 or any(PROP_RE.search(str(c.get("name"))) for c in comps):
                continue
            home = next((c for c in comps if c.get("home")), comps[0])
            away = next((c for c in comps if c is not home), comps[1])
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if (str(mk.get("description", "")).strip().casefold() != "moneyline"
                            or not (mk.get("period") or {}).get("main")):
                        continue
                    outs = {str(o.get("competitorId")): o for o in mk.get("outcomes") or []}
                    oh, oa = outs.get(str(home.get("id"))), outs.get(str(away.get("id")))
                    if not oh or not oa:
                        continue
                    dh = (oh.get("price") or {}).get("decimal")
                    da = (oa.get("price") or {}).get("decimal")
                    if not dh or not da:
                        continue
                    quotes.append(q("bovada", "Bovada",
                                    "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                                    BOVADA, ev.get("id"), home.get("name"), away.get("name"),
                                    float(dh), float(da),
                                    core.parse_iso(str(ev.get("startTime") or "").replace(
                                        "Z", "+00:00")) if isinstance(ev.get("startTime"), str)
                                    else core.parse_any(ev.get("startTime")),
                                    league, "decimal", dh, da, live=ev.get("live")))
                    written += 1
                    break
    LOG["bovada"]["quotes"] = written


# --------------------------------------------------------- 1xBet-platform mirrors (melbet etc.)
LINEFEED_MIRROR_ORDER = ("melbet", "22bet", "betwinner")


def collect_linefeed(quotes: list) -> None:
    """One quote per event, using the first mirror that carries it (the mirrors are one platform)."""
    seen_events: set[str] = set()
    for mirror in LINEFEED_MIRROR_ORDER:
        data, meta = fetch_json(LINEFEED[mirror], {"Accept": "application/json"})
        LOG[f"linefeed_{mirror}"] = meta
        rows = (data or {}).get("Value") if isinstance(data, dict) else None
        written = 0
        for ev in rows if isinstance(rows, list) else []:
            league = str(ev.get("L") or ev.get("LE") or "")
            if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
                continue
            key = str(ev.get("I"))
            if key in seen_events:
                continue
            a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
            if not a or not b or PROP_RE.search(f"{a} {b}"):
                continue
            prices = {o.get("T"): o.get("C") for o in ev.get("E") or []
                      if o.get("G") == 1 and "P" not in o}
            if not prices.get(1) or not prices.get(3):
                continue
            seen_events.add(key)
            quotes.append(q("melbet", "Melbet (1xBet platform)", "https://melbet.com/en/line/esports",
                            LINEFEED[mirror], key, a, b, float(prices[1]), float(prices[3]),
                            core.parse_any(ev.get("S")), league, "decimal", prices[1], prices[3],
                            extra={"mirror": mirror}))
            written += 1
        LOG[f"linefeed_{mirror}"]["quotes"] = written


# ---------------------------------------------------------------------------------- Kalshi
def _kalshi_mid(mk: dict):
    def num(*keys):
        for k in keys:
            v = mk.get(k)
            if v not in (None, ""):
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                return f / 100.0 if not k.endswith("_dollars") else f
        return None
    bid, ask = num("yes_bid_dollars", "yes_bid"), num("yes_ask_dollars", "yes_ask")
    if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid:
        return None, None
    return (bid + ask) / 2.0, ask - bid


KALSHI_TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def kalshi_start(event_ticker: str):
    """Event tickers encode the scheduled time in US Eastern time. The offset is not stated in the
    ticker, so the value is used ONLY to disambiguate the join window (±36 h), never displayed."""
    m = KALSHI_TICKER_TIME.search(event_ticker or "")
    if not m:
        return None
    months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    try:
        dt = core.datetime(2000 + int(m.group(1)), months.index(m.group(2)) + 1, int(m.group(3)),
                           int(m.group(4)), int(m.group(5)), tzinfo=core.timezone.utc)
    except ValueError:
        return None
    return dt + timedelta(hours=4)     # EDT approximation for the join window only


def collect_kalshi(quotes: list, rejected: list) -> None:
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    LOG["kalshi"] = meta
    events = (data or {}).get("events") if isinstance(data, dict) else None
    LOG["kalshi"]["events"] = len(events) if isinstance(events, list) else None
    written = 0
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        names = [m.get("yes_sub_title") or "" for m in mks]
        mids = [_kalshi_mid(m) for m in mks]
        tick = ev.get("event_ticker")
        rec = {"source_key": "kalshi", "event_id": tick, "team_a": names[0], "team_b": names[1],
               "public_url": f"https://kalshi.com/markets/kxcs2game/{str(tick).lower()}"}
        if any(m[0] is None for m in mids) or any(m[1] > core.KALSHI_MAX_SPREAD for m in mids):
            rejected.append({**rec,
                             "reason": "thin or one-sided order book (bid/ask missing or spread > 10c)",
                             "books": [{k: m.get(k) for k in ("ticker", "yes_bid_dollars",
                                                              "yes_ask_dollars", "yes_bid", "yes_ask")}
                                       for m in mks]})
            continue
        pa = mids[0][0] / (mids[0][0] + mids[1][0])
        dec_a, dec_b = 1 / mids[0][0], 1 / mids[1][0]
        quotes.append({**q("kalshi", "Kalshi (exchange)", rec["public_url"], KALSHI, tick, names[0],
                           names[1], dec_a, dec_b, kalshi_start(tick), ev.get("title"),
                           "yes mid ($)", round(mids[0][0], 4), round(mids[1][0], 4),
                           extra={"start_is_approx": True, "prob_a": round(pa, 6)}),
                       "prob_a": round(pa, 6), "start_is_approx": True})
        written += 1
    LOG["kalshi"]["quotes"] = written


# ----------------------------------------------------------------------------------- bo3.gg
def collect_bo3gg(pages: int = 6) -> dict:
    """Upcoming CS2 fixtures with the Thunderpick two-way coefficient bo3.gg publishes per match."""
    matches: list[dict] = []
    tournaments: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    page_meta = []
    for page in range(pages):
        url = (f"{BO3_MATCHES}&filter%5Bmatches.status%5D%5Bin%5D=upcoming"
               f"&page%5Boffset%5D={page * 100}")
        data, meta = fetch_json(url, {"Accept": "application/json"})
        page_meta.append(meta)
        results = (data or {}).get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            break
        for m in results:
            if not isinstance(m, dict):
                continue
            matches.append({k: m.get(k) for k in (
                "id", "slug", "team1_id", "team2_id", "tournament_id", "status", "bo_type",
                "start_date", "tier", "bet_updates")})
        if len(results) < 100:
            break
    LOG["bo3gg_matches"] = {"pages": len(page_meta), "matches": len(matches),
                            "errors": [m.get("error") for m in page_meta if m.get("error")]}
    # Tournament + team records only for the ids this page set references (keeps the snapshot small)
    tour_ids = sorted({str(m["tournament_id"]) for m in matches if m.get("tournament_id")})
    team_ids = sorted({str(i) for m in matches for i in (m.get("team1_id"), m.get("team2_id")) if i})
    bet_team_ids = []
    for m in matches:
        bu = m.get("bet_updates") or {}
        for side in ("team_1", "team_2"):
            tid = (bu.get(side) or {}).get("team_id")
            if tid:
                bet_team_ids.append(str(tid))
    team_ids = sorted(set(team_ids) | set(bet_team_ids))
    for tid in tour_ids:
        data, _ = fetch_json(f"{BO3}/tournaments/?filter%5Btournaments.id%5D%5Beq%5D={tid}&limit=1",
                             {"Accept": "application/json"})
        rec = (data or {}).get("results") if isinstance(data, dict) else None
        if rec:
            tournaments[tid] = {k: rec[0].get(k) for k in ("id", "name", "slug", "tier", "status",
                                                            "event_scope", "start_date", "end_date")}
    for tid in team_ids:
        data, _ = fetch_json(f"{BO3}/teams/?filter%5Bteams.id%5D%5Beq%5D={tid}&limit=1",
                             {"Accept": "application/json"})
        rec = (data or {}).get("results") if isinstance(data, dict) else None
        if rec:
            teams[tid] = {k: rec[0].get(k) for k in ("id", "name", "slug", "acronym", "rank",
                                                      "discipline_id")}
        time.sleep(0.05)
    LOG["bo3gg_meta"] = {"tournaments": len(tournaments), "teams": len(teams)}
    return {"matches": matches, "tournaments": tournaments, "teams": teams}


def unresolved_team_names(fixtures: list[dict], quotes: list[dict], vrs: dict, bo3: dict) -> list[str]:
    """Names of teams in a priced/rated fixture that the bo3.gg window did not reference.

    Only names inside an open fixture that has neither a matched quote nor a VRS row on both sides
    are looked up, so the number of extra requests stays small and tied to visible gaps.
    """
    vrs_keys = {core.canon(name)[0] for region in (vrs.get("regions") or {}).values() for name in region}
    quote_index = build_quote_index(quotes)
    known = set(team_id_index(bo3))
    need: list[str] = []
    for fx in fixtures:
        if str(fx.get("status")) not in ("scheduled", "started"):
            continue
        candidates = []
        for name in (fx["team_a"], fx["team_b"]):
            key, _, _ = core.canon(name)
            candidates.extend(quote_index.get(key, []))
        if any(core.match_quote(fx, qt) for qt in candidates):
            continue
        key_a, _, _ = core.canon(fx["team_a"])
        key_b, _, _ = core.canon(fx["team_b"])
        if key_a in vrs_keys and key_b in vrs_keys:
            continue
        for name, key in ((fx["team_a"], key_a), (fx["team_b"], key_b)):
            if key and key not in known and key not in vrs_keys and name not in need:
                need.append(name)
    return need[:MAX_BO3_TEAM_SEARCHES]


def collect_bo3gg_teams(names: list[str]) -> dict:
    """Team records looked up by name, for teams the upcoming-match window did not reference.

    The lookup is exact *after* this project's normalisation (the record's own name, acronym or slug
    must canonicalise to the same key), so a near-match can never be silently joined. Failures are
    logged per name and simply leave that team unrated; they never invent one.
    """
    out: dict[str, dict] = {}
    log: dict = {}
    for name in names:
        key, _, _ = core.canon(name)
        found = None
        for query in dict.fromkeys([name, core.norm(name)]):
            if not query:
                continue
            url = (f"{BO3}/teams/?filter%5Bteams.discipline_id%5D%5Beq%5D=1"
                   f"&filter%5Bteams.name%5D%5Blike%5D={urlquote(query, safe='')}"
                   "&page%5Blimit%5D=10")
            data, meta = fetch_json(url, {"Accept": "application/json"})
            log[name] = {"url": url, "status": meta.get("status"), "error": meta.get("error")}
            rows = (data or {}).get("results") if isinstance(data, dict) else None
            for rec in rows or []:
                for candidate in (rec.get("name"), rec.get("acronym"), rec.get("slug")):
                    if core.canon(candidate)[0] == key:
                        found = rec
                        break
                if found:
                    break
            if found:
                break
            time.sleep(0.05)
        if found:
            out[str(found.get("id"))] = {k: found.get(k) for k in
                                         ("id", "name", "slug", "acronym", "rank", "discipline_id")}
        time.sleep(0.05)
    LOG["bo3gg_team_search"] = {"requested": names, "found": sorted(out), "log": log}
    return out


def collect_bo3gg_history(team_ids: list[str], per_side: int = 60) -> dict:
    """Finished-match history for specific teams — the input for the originated Elo line."""
    out: dict[str, list] = {}
    calls = 0
    for tid in team_ids[:MAX_BO3_HISTORY_TEAMS]:
        rows: list[dict] = []
        for side in ("team1_id", "team2_id"):
            url = (f"{BO3}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
                   f"&filter%5Bmatches.{side}%5D%5Beq%5D={tid}"
                   "&filter%5Bmatches.status%5D%5Bin%5D=finished&sort=-start_date"
                   f"&page%5Blimit%5D={per_side}")
            data, _ = fetch_json(url, {"Accept": "application/json"})
            calls += 1
            for m in ((data or {}).get("results") or []) if isinstance(data, dict) else []:
                rows.append({k: m.get(k) for k in ("id", "slug", "team1_id", "team2_id",
                                                   "winner_team_id", "start_date", "tier")})
        out[tid] = rows
        time.sleep(0.05)
    LOG["bo3gg_history"] = {"teams": len(out), "calls": calls}
    return out


# ------------------------------------------------------------------------------------ VRS
def gh_headers() -> dict:
    import os
    h = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    token = os.environ.get("GITHUB_TOKEN")
    if token:                          # public repo: the token only raises the rate limit
        h["Authorization"] = f"Bearer {token}"
    return h


def collect_vrs() -> dict:
    """Official Valve regional standings, read from the table Valve publishes.

    The published table is:
        | Standing | Points | Team Name | Roster | [details](...) |
    so the standing is column 0, the points Valve awards are column 1, and the team name is column 2.
    Rows are keyed by team name because that is what a fixture can be joined on; the roster column is
    kept out of the snapshot (it is not needed to price a match).
    """
    tree, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1",
                            gh_headers())
    LOG["valve_vrs_tree"] = meta
    if not isinstance(tree, dict):
        return {}
    files = [t["path"] for t in tree.get("tree") or []
             if isinstance(t, dict) and re.match(r"live/\d{4}/standings_(global|europe|americas|asia)"
                                                 r"_\d{4}_\d{2}_\d{2}\.md$", str(t.get("path")))]
    if not files:
        return {}
    newest_date = max(re.search(r"_(\d{4}_\d{2}_\d{2})\.md$", f).group(1) for f in files)
    out = {"snapshot": newest_date, "regions": {}, "evidence": []}
    import base64
    for f in sorted(files):
        if newest_date not in f:
            continue
        region = re.search(r"standings_([a-z]+)_\d{4}_\d{2}_\d{2}\.md$", f).group(1)
        api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{f}"
        blob, meta2 = fetch_json(api_url, gh_headers())
        LOG[f"valve_vrs_{region}"] = meta2
        if not isinstance(blob, dict) or "content" not in blob:
            continue
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
        teams: dict[str, dict] = {}
        header_seen = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            if len(parts) < 3:
                continue
            if parts[0].casefold().startswith("standing"):
                header_seen = True
                continue
            if not parts[0].isdigit() or not re.fullmatch(r"\d+(?:\.\d+)?", parts[1] or ""):
                continue
            name = parts[2].strip()
            if not name:
                continue
            teams[name] = {"standing": int(parts[0]), "points": float(parts[1]),
                           "region": region, "vrs_name": name,
                           "row": stripped[:300]}
        out["regions"][region] = teams
        out["evidence"].append({"region": region, "path": f,
                                "page_url": f"https://github.com/{VRS_REPO}/blob/main/{f}",
                                "api_url": api_url, "teams": len(teams),
                                "header_parsed": header_seen})
    out["teams_global"] = out["regions"].get("global", {})
    LOG["valve_vrs"] = {"snapshot": newest_date,
                        "sizes": {k: len(v) for k, v in out["regions"].items()}}
    return out


# ----------------------------------------------------------------------------------- probes
def probe(name: str, url: str, headers=None) -> None:
    body, meta = fetch(url, headers, timeout=30)
    meta["first_bytes"] = body[:160].decode("utf-8", "replace") if body else ""
    LOG[f"probe_{name}"] = meta


def team_id_index(bo3: dict) -> dict:
    idx: dict[str, str] = {}
    for tid, rec in (bo3.get("teams") or {}).items():
        for candidate in (rec.get("name"), rec.get("acronym"), rec.get("slug")):
            key, _, _ = core.canon(candidate)
            if key and key not in idx:
                idx[key] = str(tid)
    return idx


def plan_history(fixtures: list[dict], quotes: list[dict], vrs: dict, bo3: dict) -> list[str]:
    """Teams that need a bo3.gg result history: their fixture has no price and no VRS row."""
    vrs_keys = {core.canon(name)[0] for region in (vrs.get("regions") or {}).values()
                for name in region}
    quote_index = build_quote_index(quotes)
    ids = team_id_index(bo3)
    need: set[str] = set()
    for fx in fixtures:
        if str(fx.get("status")) not in ("scheduled", "started"):
            continue
        candidates = []
        for name in (fx["team_a"], fx["team_b"]):
            key, _, _ = core.canon(name)
            candidates.extend(quote_index.get(key, []))
        if any(core.match_quote(fx, qt) for qt in candidates):
            continue
        key_a, _, _ = core.canon(fx["team_a"])
        key_b, _, _ = core.canon(fx["team_b"])
        if key_a in vrs_keys and key_b in vrs_keys:
            continue
        # Either side is enough: the history of one team already contains its opponents, so the
        # Elo graph can rate a team whose own id could not be resolved by name.
        for key in (key_a, key_b):
            if key not in vrs_keys and ids.get(key):
                need.add(ids[key])
    return sorted(need)


def build_quote_index(quotes: list[dict]) -> dict:
    idx: dict[str, list[dict]] = {}
    for qt in quotes:
        for name in (qt.get("team_a"), qt.get("team_b")):
            key, _, _ = core.canon(name)
            if key:
                idx.setdefault(key, []).append(qt)
    return idx


def main() -> int:
    started = core.now_utc()
    quotes: list[dict] = []
    rejected: list[dict] = []

    hotspawn = collect_hotspawn()

    for name, fn in (("pinnacle", lambda: collect_pinnacle(quotes)),
                     ("bovada", lambda: collect_bovada(quotes)),
                     ("linefeed", lambda: collect_linefeed(quotes)),
                     ("kalshi", lambda: collect_kalshi(quotes, rejected))):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - one failed source never stops the run
            LOG[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    bo3 = {"matches": [], "tournaments": {}, "teams": {}}
    try:
        bo3 = collect_bo3gg()
    except Exception as exc:  # noqa: BLE001
        LOG["bo3gg_matches"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    vrs = {}
    try:
        vrs = collect_vrs()
    except Exception as exc:  # noqa: BLE001
        LOG["valve_vrs"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    # ---- Thunderpick prices published by bo3.gg become normal quotes -------------------------
    written = 0
    for m in bo3["matches"]:
        bu = m.get("bet_updates") or {}
        t1, t2 = bu.get("team_1") or {}, bu.get("team_2") or {}
        coeff_a, coeff_b = t1.get("coeff"), t2.get("coeff")
        if not coeff_a or not coeff_b:
            continue
        try:
            da, db = float(coeff_a), float(coeff_b)
        except (TypeError, ValueError):
            continue
        if da <= 1.0 or db <= 1.0:
            continue
        start = core.parse_iso(str(m.get("start_date") or "").replace("Z", "+00:00"))
        tour = bo3["tournaments"].get(str(m.get("tournament_id"))) or {}
        quotes.append(q("thunderpick", "Thunderpick (via bo3.gg)",
                        f"https://bo3.gg/matches/{m.get('slug')}",
                        f"{BO3}/matches/?filter%5Bmatches.id%5D%5Beq%5D={m.get('id')}",
                        m.get("id"), t1.get("name") or "", t2.get("name") or "", da, db, start,
                        tour.get("name") or "", "decimal", coeff_a, coeff_b,
                        extra={"provider": bu.get("provider"), "mirror_page": "bo3.gg",
                               "team1_id": m.get("team1_id"), "team2_id": m.get("team2_id"),
                               "max_coeff_a": t1.get("max_coeff"), "max_coeff_b": t2.get("max_coeff")}))
        written += 1
    LOG["thunderpick_quotes"] = written

    # ---- teams the upcoming window never referenced: look them up by name (bounded) ----------
    try:
        missing = unresolved_team_names(hotspawn["fixtures"], quotes, vrs, bo3)
        if missing:
            bo3["teams"].update(collect_bo3gg_teams(missing))
    except Exception as exc:  # noqa: BLE001
        LOG["bo3gg_team_search"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    # ---- rating history only for the fixtures that have neither a price nor a VRS row --------
    history: dict = {}
    try:
        need = plan_history(hotspawn["fixtures"], quotes, vrs, bo3)
        LOG["bo3gg_history_plan"] = need
        if need:
            history = collect_bo3gg_history(need)
    except Exception as exc:  # noqa: BLE001
        LOG["bo3gg_history"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    for name, url in (("hltv_matches", "https://www.hltv.org/matches"),
                      ("polymarket", POLY),
                      ("linefeed_22bet", LINEFEED["22bet"]),
                      ("linefeed_betwinner", LINEFEED["betwinner"])):
        try:
            probe(name, url, {"Accept": "application/json, text/html;q=0.9"})
        except Exception as exc:  # noqa: BLE001
            LOG[f"probe_{name}"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    doc = {
        "session": "fe803b80",
        "generated_utc": core.to_iso(core.now_utc()),
        "collection_seconds": round((core.now_utc() - started).total_seconds(), 1),
        "hotspawn": hotspawn,
        "quotes": quotes,
        "rejected_quotes": rejected,
        "bo3gg": bo3,
        "bo3gg_history": history,
        "vrs": {k: v for k, v in vrs.items() if k != "regions"},
        "vrs_regions": vrs.get("regions", {}),
        "access": LOG,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "snapshot.json").write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n",
                                       encoding="utf-8")
    print(f"hotspawn fixtures={len(hotspawn['fixtures'])} quotes={len(quotes)} "
          f"rejected={len(rejected)} bo3_matches={len(bo3['matches'])} "
          f"vrs_global={len(vrs.get('teams_global') or {})} "
          f"seconds={doc['collection_seconds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
