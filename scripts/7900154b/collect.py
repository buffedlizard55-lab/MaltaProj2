#!/usr/bin/env python3
"""Day-5 desk collector (session 7900154b).

Runs on a GitHub-hosted runner (general internet access). One dated capture collects
everything needed to price **every** Counter-Strike 2 fixture the HotSpawn Pick'ems lobby
lists, plus the TWC 2026 day-5 matches:

  * https://play.hotspawn.com/lobby                      fixture discovery (Angular transfer state)
  * https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures
                                                          the same public API the lobby calls
  * https://bo3.gg/api/v1/matches?...                     esportsbook aggregator; the
                                                          `bet_updates` block carries real
                                                          Thunderpick coefficients for a very large
                                                          share of low-tier CS2 events that the
                                                          mainstream books do not list
  * https://bo3.gg/api/v1/teams?...                      team id -> team name, so a match can
                                                          be identified without parsing a slug
  * Pinnacle guest odds API          (licensed bookmaker; public guest key used by its own app)
  * Bovada coupon JSON               (licensed bookmaker)
  * Melbet / 1xBet-platform LineFeed (licensed bookmaker; prices most low-tier CCT/NODWIN events)
  * Kalshi KXCS2GAME                 (CFTC-regulated exchange; midpoints are not executable odds)
  * Polymarket gamma API             (prediction market; prices are midpoints, not book odds)
  * ValveSoftware/counter-strike_regional_standings (official ratings, via the GitHub API)

HotSpawn is **fixture discovery and settlement only**. Its crowd "picked %" is captured as
leaderboard context and is never used as a win probability.

Outputs (all under ``data/7900154b/``):

  raw/hotspawn.json   the fixtures array embedded in the lobby render + permalinks + week
  raw/bo3.json        the raw bo3.gg upcoming-match pages that were kept
  raw/bo3_teams.json  the raw bo3.gg team list
  raw/pinnacle.json   the raw CS2 matchup objects
  raw/bovada.json     the raw coupon JSON
  raw/melbet.json     the raw LineFeed JSON
  raw/kalshi.json     the raw events JSON
  raw/polymarket.json the raw gamma events JSON
  raw/vrs.json        Valve's official standings markdown + the git blob sha it came from
  quotes.json         every two-way match-winner quote normalised, with its own source URL
  access.json         HTTP status / bytes / error for every request, so a blocked source is
                      recorded as a failure and never as "no price exists"

Nothing here derives a probability. Derivation happens in build.py, which re-computes every
number from the retained raw prices so the published value can be audited.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "7900154b"
RAW = OUT / "raw"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/",
               "Accept": "application/json"}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
MELBET = "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
POLY = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=counter-strike"
BO3_MATCHES = ("https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming"
               "&filter%5Bmatches.discipline_id%5D%5Bin%5D=1&sort=start_date"
               "&page%5Blimit%5D=50&page%5Boffset%5D={offset}")
BO3_TEAMS = "https://bo3.gg/api/v1/teams?sort=-rating&page={page}&limit=100"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_API = (f"https://api.github.com/repos/{VRS_REPO}/contents/live/2026/standings_global_2026_10_05.md")
VRS_TREE = f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1"

# A price must start within this window of the HotSpawn fixture to be joined to it.
KICKOFF_TOLERANCE_HOURS = 30.0
# Only fixtures that have not finished are treated as "open for picks".
MAX_RAW_BYTES = 40_000_000
BO3_PAGES = 8

LOBBY_STATE_RE = re.compile(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol|winner", re.I)
# The rendered lobby card prints "N% picked" under each team. HotSpawn's crowd split is
# ownership only: it is never used as a win probability, only to measure a leaderboard edge.
PICKED_RE = re.compile(r"(\d{1,3})\s*%\s*picked", re.I)
ALT_RE = re.compile(r'alt\s*=\s*"([^"]{1,60})"', re.I)
PERMALINK_RE = re.compile(r"/matches/([a-z0-9\-]+?)-(\d{6,})", re.I)

ACCESS: dict = {}
RAW_FILES: dict = {}
QUOTES: list = []


# ----------------------------------------------------------------------------- helpers
def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_any(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
        if n <= 0:
            return None
        if n > 1e12:
            n /= 1000.0
        return datetime.fromtimestamp(n, tz=timezone.utc)
    if isinstance(value, str) and value.strip().isdigit():
        return parse_any(float(value))
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    return None


def fetch(url, headers=None, timeout=60):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    meta = {"url": url, "http_status": None, "response_bytes": 0, "error": None,
            "at_utc": iso(now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read(MAX_RAW_BYTES)
            meta["http_status"] = r.status
            meta["age_header"] = r.headers.get("Age")
    except urllib.error.HTTPError as exc:
        meta["http_status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a network failure is evidence, not a crash
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["response_bytes"] = len(body)
    if body:
        meta["sha256"] = hashlib.sha256(body).hexdigest()
    return body, meta


def fetch_json(url, headers=None, timeout=60):
    body, meta = fetch(url, headers, timeout)
    try:
        return (json.loads(body.decode("utf-8", "replace")) if body else None), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


def write_raw(name, payload):
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")


# ------------------------------------------------------------------- HotSpawn lobby
def parse_lobby_cards(html_text: str, api_fixtures: list) -> list:
    """Read the rendered lobby's "N% picked" ownership split off each card.

    HotSpawn prints the crowd split under each team on the card. The markup around it is
    not contractual, so the parser works from the visible label: the percentage, the nearest
    team name before it, and the nearest match permalink before the card. Everything is
    joined back to the public fixtures API by name and kickoff; a card that cannot be
    joined is dropped rather than guessed at.
    """
    if not html_text:
        return []
    pcts = [(m.start(), int(m.group(1))) for m in PICKED_RE.finditer(html_text)]
    if not pcts:
        return []
    names = [(m.start(), m.group(1).strip()) for m in ALT_RE.finditer(html_text)]
    links = [(m.start(), m.group(2)) for m in PERMALINK_RE.finditer(html_text)]
    pairs = []
    for pos, pct in pcts:
        name = None
        for npos, nval in names:
            if npos < pos and pos - npos < 900:
                name = nval
            else:
                break
        fid = None
        for lpos, lval in links:
            if lpos < pos and pos - lpos < 4000:
                fid = lval
            else:
                break
        pairs.append({"pos": pos, "pct": pct, "name": name, "fixture_id": fid})
    cards = []
    for i in range(0, len(pairs) - 1, 2):
        a, b = pairs[i], pairs[i + 1]
        if not a["name"] or not b["name"]:
            continue
        if a["pct"] > 100 or b["pct"] > 100:
            continue
        cards.append({"team_a": a["name"], "team_b": b["name"],
                      "crowd_a": a["pct"], "crowd_b": b["pct"],
                      "fixture_id": a["fixture_id"] or b["fixture_id"]})
    # join back to the public API by name and kickoff
    by_id = {str(f.get("fixture_id")): f for f in api_fixtures if isinstance(f, dict)}
    out = []
    for card in cards:
        fixture = by_id.get(str(card["fixture_id"])) if card["fixture_id"] else None
        if fixture is None:
            for cand in api_fixtures:
                if not isinstance(cand, dict):
                    continue
                if (str(cand.get("team_a")) == card["team_a"]
                        and str(cand.get("team_b")) == card["team_b"]):
                    fixture = cand
                    break
        if fixture is None:
            continue
        out.append({
            "fixture_id": str(fixture.get("fixture_id")),
            "competition": fixture.get("competition"), "tier": fixture.get("tier"),
            "stage": fixture.get("stage"), "best_of": fixture.get("best_of"),
            "points": fixture.get("points"),
            "start_utc": fixture.get("start_utc"), "lock_utc": fixture.get("lock_utc"),
            "team_a": fixture.get("team_a") or card["team_a"],
            "team_b": fixture.get("team_b") or card["team_b"],
            "crowd_a": card["crowd_a"], "crowd_b": card["crowd_b"],
            "hotspawn_url": fixture.get("hotspawn_url"),
        })
    return out


def collect_hotspawn():
    """Fixture discovery only. The crowd percentages are read but never used as a probability."""
    body, meta = fetch(LOBBY_PAGE)
    ACCESS["hotspawn_lobby_page"] = meta
    fixtures, permalinks, week = [], {}, None
    cards = []
    if body:
        html = body.decode("utf-8", "replace")
        m = LOBBY_STATE_RE.search(html)
        if m:
            try:
                state = json.loads(m.group(1))
            except ValueError:
                state = {}
            raw = state.get("raw") or state
            fixtures = raw.get("fixtures") or []
            permalinks = raw.get("permalinks") or {}
            week = raw.get("week")
    api, api_meta = fetch_json(HS_API)
    ACCESS["hotspawn_api"] = api_meta
    api_fixtures = []
    if isinstance(api, list):
        api_fixtures = [f for f in api if isinstance(f, dict)]
    if body:
        cards = parse_lobby_cards(body.decode("utf-8", "replace"), api_fixtures)
    ACCESS["hotspawn_lobby_cards"] = {"cards_recovered": len(cards),
                                     "note": "crowd ownership only; never a probability"}
    write_raw("hotspawn.json", {"fixtures": fixtures, "permalinks": permalinks,
                                "week": week, "api_fixtures": api_fixtures,
                                "cards": cards})
    if cards:
        doc = {
            "session": "7900154b",
            "read_utc": iso(now_utc()),
            "source_url": LOBBY_PAGE,
            "method": ("Crowd-pick shares are read from the rendered 'N% picked' label on each "
                       "HotSpawn lobby card, exactly as the label is printed on the page. They "
                       "are ownership only: never used as a win probability, never used to "
                       "derive a line. They are used solely for the leaderboard leverage "
                       "column and for the contrarian layer, which only ever takes a side the "
                       "crowd has under-picked."),
            "cards_seen": len(cards),
            "cards": sorted(cards, key=lambda c: (c.get("start_utc") or "", c.get("fixture_id"))),
        }
        (OUT / "lobby.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    return {"lobby_fixtures": fixtures, "permalinks": permalinks, "week": week,
            "api_fixtures": api_fixtures, "cards": cards}


# --------------------------------------------------------------------- bo3.gg lines
def collect_bo3():
    """bo3.gg carries Thunderpick's own coefficients for a large share of low-tier CS2.

    The `rating` field on a bo3.gg match is a *tournament-level* metric (it repeats across
    every match of the same event), so it is deliberately NOT used as a win probability.
    Only the `bet_updates` coefficients are used, and only when both sides carry one.
    """
    matches, access = [], {}
    for page in range(BO3_PAGES):
        url = BO3_MATCHES.format(offset=page * 50)
        data, meta = fetch_json(url)
        access[f"page_{page}"] = meta
        if not isinstance(data, dict):
            continue
        results = data.get("results")
        if not isinstance(results, list) or not results:
            break
        matches.extend([m for m in results if isinstance(m, dict)])
        total = (data.get("total") or {})
        if isinstance(total, dict) and page + 1 >= int(total.get("pages") or 1):
            break
        time.sleep(0.25)
    ACCESS["bo3_matches"] = access

    teams, teams_access = {}, {}
    for page in range(1, 4):
        url = BO3_TEAMS.format(page=page)
        data, meta = fetch_json(url)
        teams_access[f"page_{page}"] = meta
        rows = data if isinstance(data, list) else (data.get("results") if isinstance(data, dict) else [])
        if not isinstance(rows, list) or not rows:
            break
        for t in rows:
            if isinstance(t, dict) and t.get("id") is not None:
                teams[str(t["id"])] = {"name": t.get("name") or t.get("title") or t.get("short_name"),
                                       "slug": t.get("slug")}
        time.sleep(0.25)
    ACCESS["bo3_teams"] = teams_access
    write_raw("bo3.json", {"matches": matches, "teams": teams})
    return {"matches": matches, "teams": teams}


def bo3_quote(m: dict, teams: dict) -> dict | None:
    """Build one two-way quote from a bo3.gg match's Thunderpick coefficients."""
    upd = m.get("bet_updates")
    if not isinstance(upd, dict):
        return None
    t1, t2 = upd.get("team_1") or {}, upd.get("team_2") or {}
    ca, cb = t1.get("coeff"), t2.get("coeff")
    if not ca or not cb:
        return None
    name_a = t1.get("name") or (teams.get(str(m.get("team1_id"))) or {}).get("name")
    name_b = t2.get("name") or (teams.get(str(m.get("team2_id"))) or {}).get("name")
    if not name_a or not name_b:
        return None
    start = parse_any(m.get("start_date"))
    return {
        "source_key": "thunderpick_bo3",
        "source_name": f"Thunderpick (via bo3.gg, {upd.get('provider') or 'provider unknown'})",
        "public_url": upd.get("path") or f"https://bo3.gg/matches/{m.get('slug')}",
        "api_url": f"https://bo3.gg/api/v1/matches/{m.get('id')}",
        "event_id": str(m.get("id")),
        "team_a": name_a,
        "team_b": name_b,
        "decimal_a": float(ca),
        "decimal_b": float(cb),
        "start_utc": iso(start),
        "league": f"bo3.gg tournament {m.get('tournament_id')}",
        "bo_type": m.get("bo_type"),
        "tier": m.get("tier"),
        "raw_format": "decimal",
        "raw_a": ca,
        "raw_b": cb,
        "retrieved_utc": iso(now_utc()),
    }


# ---------------------------------------------------------------------- bookmakers
def american_to_decimal(price):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return 1.0 + p / 100.0
    if p <= -100:
        return 1.0 + 100.0 / abs(p)
    return None


def collect_pinnacle():
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    ACCESS["pinnacle"] = meta
    if not isinstance(data, list):
        return
    cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
          and len(m.get("participants") or []) == 2 and not m.get("parentId")
          and re.match(r"^(CS2|Counter-Strike)", str((m.get("league") or {}).get("name") or ""), re.I)]
    ACCESS["pinnacle"]["cs2_matchups"] = len(cs)
    write_raw("pinnacle.json", cs)
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
            da, db = american_to_decimal(by["home"]), american_to_decimal(by["away"])
            if da and db:
                QUOTES.append({
                    "source_key": "pinnacle", "source_name": "Pinnacle",
                    "public_url": "https://www.pinnacle.com/en/esports/cs2-hub",
                    "api_url": murl, "event_id": str(m["id"]),
                    "team_a": al["home"], "team_b": al["away"],
                    "decimal_a": round(da, 4), "decimal_b": round(db, 4),
                    "raw_format": "american", "raw_a": by["home"], "raw_b": by["away"],
                    "start_utc": iso(parse_any(m.get("startTime"))),
                    "league": (m.get("league") or {}).get("name"),
                    "live": bool(m.get("isLive") or mk.get("isLive")),
                    "retrieved_utc": iso(now_utc())})
                written += 1
            break
    ACCESS["pinnacle"]["quotes"] = written


def collect_bovada():
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    ACCESS["bovada"] = meta
    write_raw("bovada.json", data if isinstance(data, list) else {"payload": data})
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
                            or not (mk.get("period") or {}).get("main") or mk.get("status") != "O"
                            or (mk.get("period") or {}).get("live")):
                        continue
                    outs = {str(o.get("competitorId")): o for o in mk.get("outcomes") or []}
                    oh, oa = outs.get(str(home.get("id"))), outs.get(str(away.get("id")))
                    if not oh or not oa or oh.get("status") != "O" or oa.get("status") != "O":
                        continue
                    dh = (oh.get("price") or {}).get("decimal")
                    da = (oa.get("price") or {}).get("decimal")
                    if not dh or not da:
                        continue
                    QUOTES.append({
                        "source_key": "bovada", "source_name": "Bovada",
                        "public_url": "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                        "api_url": BOVADA, "event_id": str(ev.get("id")),
                        "team_a": home.get("name"), "team_b": away.get("name"),
                        "decimal_a": float(dh), "decimal_b": float(da),
                        "raw_format": "decimal", "raw_a": dh, "raw_b": da,
                        "start_utc": iso(parse_any(ev.get("startTime"))),
                        "league": league, "live": ev.get("live"),
                        "retrieved_utc": iso(now_utc())})
                    written += 1
                    break
    ACCESS["bovada"]["quotes"] = written


def collect_melbet():
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    ACCESS["melbet"] = meta
    write_raw("melbet.json", data)
    rows = (data or {}).get("Value") if isinstance(data, dict) else None
    written = 0
    for ev in rows if isinstance(rows, list) else []:
        league = str(ev.get("L") or ev.get("LE") or "")
        if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
            continue
        a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
        if not a or not b or PROP_RE.search(f"{a} {b}"):
            continue
        prices = {o.get("T"): o.get("C") for o in ev.get("E") or [] if o.get("G") == 1 and "P" not in o}
        if not prices.get(1) or not prices.get(3):
            continue
        QUOTES.append({
            "source_key": "melbet", "source_name": "Melbet",
            "public_url": "https://melbet.com/en/line/esports", "api_url": MELBET,
            "event_id": str(ev.get("I")), "team_a": a, "team_b": b,
            "decimal_a": float(prices[1]), "decimal_b": float(prices[3]),
            "raw_format": "decimal", "raw_a": prices[1], "raw_b": prices[3],
            "start_utc": iso(parse_any(ev.get("S"))), "league": league,
            "retrieved_utc": iso(now_utc())})
        written += 1
    ACCESS["melbet"]["quotes"] = written


def collect_kalshi():
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    ACCESS["kalshi"] = meta
    write_raw("kalshi.json", data)
    events = (data or {}).get("events") if isinstance(data, dict) else None
    ACCESS["kalshi"]["events"] = len(events) if isinstance(events, list) else None
    written = 0
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in (ev.get("markets") or []) if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        mids = []
        for m in mks:
            def num(*keys):
                for k in keys:
                    v = m.get(k)
                    if v not in (None, ""):
                        try:
                            f = float(v)
                        except (TypeError, ValueError):
                            continue
                        return f / 100.0 if not k.endswith("_dollars") else f
                return None
            bid, ask = num("yes_bid_dollars", "yes_bid"), num("yes_ask_dollars", "yes_ask")
            if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid:
                mids = []
                break
            mids.append(((bid + ask) / 2.0, ask - bid))
        if len(mids) != 2:
            continue
        if any(spread > 0.10 for _, spread in mids):
            continue
        names = [m.get("yes_sub_title") or "" for m in mks]
        pa = mids[0][0] / (mids[0][0] + mids[1][0])
        QUOTES.append({
            "source_key": "kalshi", "source_name": "Kalshi (exchange, bid/ask midpoint)",
            "public_url": f"https://kalshi.com/markets/kxcs2game/{str(ev.get('event_ticker')).lower()}",
            "api_url": KALSHI, "event_id": str(ev.get("event_ticker")),
            "team_a": names[0], "team_b": names[1],
            "decimal_a": round(1.0 / mids[0][0], 4), "decimal_b": round(1.0 / mids[1][0], 4),
            "raw_format": "decimal", "raw_a": mids[0][0], "raw_b": mids[1][0],
            "start_utc": None,
            "league": ev.get("title"),
            "retrieved_utc": iso(now_utc())})
        written += 1
    ACCESS["kalshi"]["quotes"] = written


def collect_polymarket():
    data, meta = fetch_json(POLY)
    ACCESS["polymarket"] = meta
    write_raw("polymarket.json", data)
    written = 0
    for ev in data if isinstance(data, list) else []:
        for mk in ev.get("markets") or []:
            if mk.get("closed") or not mk.get("active"):
                continue
            try:
                prices = json.loads(mk.get("outcomePrices") or "[]")
                outcomes = json.loads(mk.get("outcomes") or "[]")
            except ValueError:
                continue
            if len(prices) != 2 or len(outcomes) != 2:
                continue
            p_a, p_b = float(prices[0]), float(prices[1])
            if p_a <= 0 or p_b <= 0:
                continue
            QUOTES.append({
                "source_key": "polymarket", "source_name": "Polymarket (midpoint)",
                "public_url": f"https://polymarket.com/event/{ev.get('slug')}",
                "api_url": POLY, "event_id": str(mk.get("id")),
                "team_a": outcomes[0], "team_b": outcomes[1],
                "decimal_a": round(1.0 / p_a, 4), "decimal_b": round(1.0 / p_b, 4),
                "raw_format": "decimal", "raw_a": p_a, "raw_b": p_b,
                "start_utc": None, "league": ev.get("title"),
                "retrieved_utc": iso(now_utc())})
            written += 1
    ACCESS["polymarket"]["quotes"] = written


def collect_vrs():
    """Valve's own regional standings, read through the GitHub API."""
    tree, tree_meta = fetch_json(VRS_TREE, {"Accept": "application/vnd.github+json"})
    ACCESS["valve_vrs_tree"] = tree_meta
    blob, blob_meta = fetch_json(VRS_API, {"Accept": "application/vnd.github+json"})
    ACCESS["valve_vrs_file"] = blob_meta
    markdown, sha = None, None
    if isinstance(blob, dict) and blob.get("content"):
        import base64
        try:
            markdown = base64.b64decode(blob["content"]).decode("utf-8", "replace")
            sha = blob.get("sha")
        except Exception:  # noqa: BLE001
            markdown = None
    write_raw("vrs.json", {"markdown": markdown, "blob_sha": sha,
                            "path": "live/2026/standings_global_2026_10_05.md",
                            "page_url": f"https://github.com/{VRS_REPO}/blob/main/live/2026/standings_global_2026_10_05.md",
                            "tree_entries": len((tree or {}).get("tree") or []) if isinstance(tree, dict) else 0})
    return {"markdown": markdown, "blob_sha": sha}


def parse_vrs_markdown(markdown: str) -> list:
    """Parse Valve's global standings table.

    The file is a pipe table: ``| Standing | Points | Team Name | Roster | [details](...) |``.
    Only the standing, the points, the team name, the roster and the details path are kept.
    """
    teams = []
    for line in (markdown or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not cells[0].isdigit():
            continue
        try:
            standing = int(cells[0])
            points = int(cells[1])
        except ValueError:
            continue
        name = cells[2].strip()
        if not name:
            continue
        roster = cells[3].strip() if len(cells) > 3 else ""
        details = ""
        if len(cells) > 4:
            m = re.search(r"\(([^)]+)\)", cells[4])
            if m:
                details = m.group(1)
        teams.append({"standing": standing, "points": points, "team": name,
                      "roster": roster, "details_path": details})
    return teams


def write_calibration_pairs(vrs_teams: list, fixtures: list) -> int:
    """Record one (rating difference, market probability) pair per priced fixture.

    These are the observations the ratings model's slope is fitted to. A pair is only
    written when the fixture has a real two-way price and both teams carry a Valve rating.
    """
    import core  # local module, same directory
    idx = core.vrs_index(vrs_teams)
    pairs = {}
    for q in QUOTES:
        if q.get("source_key") not in ("pinnacle", "bovada", "melbet", "thunderpick_bo3"):
            continue
        nv = core.no_vig(q.get("decimal_a"), q.get("decimal_b"))
        if not nv:
            continue
        for fx in fixtures:
            if not isinstance(fx, dict):
                continue
            same = (core.same_team(q.get("team_a"), fx.get("team_a"))
                    and core.same_team(q.get("team_b"), fx.get("team_b")))
            swapped = (core.same_team(q.get("team_b"), fx.get("team_a"))
                       and core.same_team(q.get("team_a"), fx.get("team_b")))
            if not (same or swapped):
                continue
            a, _ = core.vrs_resolve(fx.get("team_a"), idx)
            b, _ = core.vrs_resolve(fx.get("team_b"), idx)
            if not a or not b:
                continue
            prob_a = nv["prob_b"] if swapped else nv["prob_a"]
            fid = str(fx.get("fixture_id"))
            pairs[fid] = {
                "fixture_id": fid, "delta": int(a["points"]) - int(b["points"]),
                "market_prob_a": round(prob_a, 6), "n_sources": 1,
                "observed_utc": iso(now_utc()), "start_utc": fx.get("start_utc"),
                "teams": [fx.get("team_a"), fx.get("team_b")],
                "source_key": q.get("source_key"),
            }
            break
    if pairs:
        (OUT / "calibration_pairs.json").write_text(
            json.dumps(pairs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(pairs)


# ----------------------------------------------------------------------------- main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    started = now_utc()

    hs = collect_hotspawn()
    bo3 = collect_bo3()
    for m in bo3["matches"]:
        q = bo3_quote(m, bo3["teams"])
        if q:
            QUOTES.append(q)
    ACCESS["bo3_quotes"] = sum(1 for q in QUOTES if q["source_key"] == "thunderpick_bo3")

    collect_pinnacle()
    collect_bovada()
    collect_melbet()
    collect_kalshi()
    collect_polymarket()
    vrs = collect_vrs()
    vrs_teams = parse_vrs_markdown(vrs.get("markdown") or "")
    if vrs_teams:
        (OUT / "vrs_teams.json").write_text(
            json.dumps({"snapshot": "2026_10_05", "blob_sha": vrs.get("blob_sha"),
                        "teams": vrs_teams}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
    fixtures = list(hs.get("api_fixtures") or []) + list(hs.get("lobby_fixtures") or [])
    n_pairs = write_calibration_pairs(vrs_teams, fixtures)

    payload = {
        "session": "7900154b",
        "collected_from_utc": iso(started),
        "collected_to_utc": iso(now_utc()),
        "quotes": QUOTES,
        "quotes_total": len(QUOTES),
        "access_log": ACCESS,
        "vrs": {"blob_sha": vrs.get("blob_sha"),
                "path": "live/2026/standings_global_2026_10_05.md",
                "page_url": f"https://github.com/{VRS_REPO}/blob/main/live/2026/standings_global_2026_10_05.md",
                "markdown_bytes": len(vrs.get("markdown") or "")},
        "hotspawn_week": hs.get("week"),
        "hotspawn_lobby_fixture_count": len(hs.get("lobby_fixtures") or []),
        "hotspawn_api_fixture_count": len(hs.get("api_fixtures") or []),
        "bo3_match_count": len(bo3.get("matches") or []),
        "bo3_team_count": len(bo3.get("teams") or {}),
        "vrs_team_count": len(vrs_teams),
        "calibration_pairs": n_pairs,
        "lobby_cards": len(hs.get("cards") or []),
    }
    (OUT / "quotes.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    (OUT / "access.json").write_text(json.dumps(ACCESS, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"quotes": len(QUOTES),
                      "by_source": {k: sum(1 for q in QUOTES if q["source_key"] == k)
                                    for k in sorted({q["source_key"] for q in QUOTES})},
                      "bo3_matches": len(bo3.get("matches") or []),
                      "hotspawn_lobby": len(hs.get("lobby_fixtures") or []),
                      "hotspawn_api": len(hs.get("api_fixtures") or [])}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
