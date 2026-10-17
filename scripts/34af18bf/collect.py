#!/usr/bin/env python3
"""Session 34af18bf collector — runs on a GitHub-hosted runner (general egress).

Discovery (HotSpawn is discovery + settlement ONLY; its crowd percentage is
stored as ownership and is never allowed into the probability arithmetic):

* the public lobby page ``https://play.hotspawn.com/lobby`` and the
  competition-scoped URL ``…/lobby?competitionId=<id>`` — the Angular
  transfer state the page embeds, which is what a browser actually renders;
* HotSpawn's own fixtures endpoint, swept once per competition id seen in the
  transfer state **plus** the ids HotSpawn itself publishes in article links
  (this is how the Thunderpick World Championship pick'em competition ``35859``
  gets included — earlier collectors hard-coded a competition list that omitted
  it, so the two TWC semifinals never reached any board).

Prices (external only):

* Pinnacle guest odds API (licensed bookmaker)
* Bovada coupon JSON (licensed bookmaker)
* the 1xBet-platform LineFeed served by Melbet / 22bet / Betwinner
* Kalshi exchange (KXCS2GAME), kept with bid/ask/spread
* Thunderpick coefficients published per fixture by bo3.gg (``bet_updates``)
* Polymarket gamma API (prediction market, volume retained)
* official Valve regional standings (VRS) from Valve's own repository — the only
  input this desk uses to *originate* a line when no market prices a fixture

Every request is logged with URL, status, bytes, sha256-16, error text and UTC
read time, including sources that refuse the runner (HLTV, EGamersWorld and
several sportsbooks block the GitHub IP range). A blocked source is published
as a failure, never as "no price exists".

Output: ``data/34af18bf/snapshot.json`` (raw payload bodies are not committed;
their sha256/size are, which keeps the evidence auditable without the bulk).
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "34af18bf"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

LOBBY = "https://play.hotspawn.com/lobby"
FIXTURES_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
BOVADA = ("https://www.bovada.lv/services/sports/event/v2/events/A/description/"
          "esports/counter-strike-2")
LINEFEED_URL = ("https://{mirror}.com/service-api/LineFeed/Get1x2_VZip"
                "?sports=40&count=1000&lng=en&mode=4&country=1")
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}"
          "&status=open&with_nested_markets=true&limit=200")
BO3 = "https://api.bo3.gg/api/v1"
BO3_MATCHES = (f"{BO3}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               "&sort=start_date&page%5Blimit%5D=100")
POLY = ("https://gamma-api.polymarket.com/events?closed=false&limit=200"
        "&tag_slug=counter-strike")
VRS_TREE = "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/"
VRS_RAW = ("https://raw.githubusercontent.com/ValveSoftware/"
           "counter-strike_regional_standings/main/{path}")

# Competition ids HotSpawn publishes in its own article/tournament links.
# 35859 = "Thunderpick World Championship 2026" pick'em competition, linked from
# https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview
KNOWN_COMPETITIONS = {35859: "Thunderpick World Championship 2026",
                      33804: "Thunderpick World Championship 2026: South American Series #1"}

PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?", re.I)
NG_STATE_RE = re.compile(r'<script[^>]+id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)
LOBBY_PARSE_LIMIT = 4_000_000

LOG: dict[str, dict] = {}


# --------------------------------------------------------------------------- http
def _digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()[:16]


def fetch(url: str, headers: dict | None = None, timeout: int = 45) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None, "at_utc": core.iso(core.now_utc()),
            "sha256_16": None, "age_header": None}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read(LOBBY_PARSE_LIMIT)
            meta["status"] = r.status
            meta["age_header"] = r.headers.get("Age")
            meta["content_type"] = r.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a network failure is evidence
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    if body:
        meta["sha256_16"] = _digest(body)
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


# --------------------------------------------------------------------------- HotSpawn
def lobby_state(page_html: str) -> dict:
    m = NG_STATE_RE.search(page_html or "")
    if not m:
        return {}
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return {}
    out = {"fixtures": [], "permalinks": {}, "week": None, "urls": []}
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        out["urls"].append(url)
        if url.split("?")[0].endswith("/api/v1/fixtures") and isinstance(body, list):
            out["fixtures"].extend(body)
        elif "permalinks" in url and isinstance(body, dict):
            for k, v in (body.get("permalinks") or {}).items():
                if re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(v)):
                    out["permalinks"][str(k)] = str(v)
        elif "week-prizes" in url and isinstance(body, dict):
            out["week"] = {k: body.get(k) for k in ("weekId", "sportAlias", "status",
                                                    "weekStartUtc", "weekEndUtc", "cutoffUtc")}
    return out


def normalise_fixture(raw: dict) -> dict | None:
    """Normalise one HotSpawn fixture row. Crowd % is copied to ``crowd_*`` only."""
    if not isinstance(raw, dict) or str(raw.get("sport_alias") or "").casefold() != "cs2":
        return None
    start = core.from_epoch_ms(raw.get("scheduled_start_time"))
    lock = core.from_epoch_ms(raw.get("lock_time"))
    a, b = raw.get("participants0_name"), raw.get("participants1_name")
    if not raw.get("id") or not a or not b or start is None:
        return None
    return {
        "fixture_id": str(raw.get("id")),
        "competition_id": str(raw.get("competition_id") or ""),
        "competition": raw.get("competition_name"),
        "tier": raw.get("tier"),
        "stage": raw.get("stage"),
        "status": str(raw.get("status") or "").lower(),
        "start_utc": core.iso(start),
        "lock_utc": core.iso(lock) if lock else None,
        "team_a": str(a),
        "team_b": str(b),
        "crowd_a_pct": raw.get("participants0_picked_percent"),
        "crowd_b_pct": raw.get("participants1_picked_percent"),
        "crowd_picks_total": raw.get("total_picks"),
        "offered_points": raw.get("offered_points"),
        "base_points": raw.get("base_points"),
        "points_breakdown": raw.get("points_breakdown"),
        "participants0_score": raw.get("participants0_score"),
        "participants1_score": raw.get("participants1_score"),
        "source_url": LOBBY,
    }


def collect_hotspawn() -> dict:
    page, meta = fetch(LOBBY, {"Accept": "text/html"}, timeout=60)
    LOG["hotspawn_lobby_page"] = dict(meta, fixtures=0)
    html = page.decode("utf-8", "replace") if page else ""
    state = lobby_state(html)
    fixtures: dict[str, dict] = {}
    for raw in state.get("fixtures") or []:
        fx = normalise_fixture(raw)
        if fx:
            fx["lobby_card"] = True
            fx["discovery"] = "HotSpawn lobby transfer state (the cards a browser renders)"
            fixtures[fx["fixture_id"]] = fx
    LOG["hotspawn_lobby_page"]["fixtures_in_transfer_state"] = len(fixtures)

    # Competition ids: the ones seen in the transfer state, the ones in HotSpawn's
    # own published links, and anything the rendered page leaks in an href/param.
    comps: dict[str, str] = dict(KNOWN_COMPETITIONS)
    for fx in fixtures.values():
        if fx["competition_id"]:
            comps[fx["competition_id"]] = fx["competition"]
    for cid in set(re.findall(r"competitionId(?:=|%3D)(\d{2,6})", html, re.I)):
        comps.setdefault(cid, "competition id published on the lobby page")

    sweep: dict[str, dict] = {}
    for cid, name in sorted(comps.items(), key=lambda kv: int(kv[0])):
        url = (f"{FIXTURES_API}?sport_alias=cs2&status=scheduled&competition_id={cid}")
        payload, cmeta = fetch_json(url, {"Accept": "application/json"}, timeout=45)
        key = f"fixtures_api_{cid}"
        rows = payload if isinstance(payload, list) else ((payload or {}).get("data")
                                                         if isinstance(payload, dict) else None)
        kept = 0
        for raw in rows if isinstance(rows, list) else []:
            fx = normalise_fixture(raw)
            if not fx:
                continue
            fx["competition"] = fx["competition"] or name
            fx["lobby_card"] = False
            fx["discovery"] = ("HotSpawn fixtures endpoint (listed by HotSpawn, "
                               "not on the rendered lobby page)")
            # the status=scheduled filter is known to return past-dated rows
            start = core.parse_iso(fx["start_utc"])
            if start and start < core.now_utc():
                continue
            fixtures.setdefault(fx["fixture_id"], fx)
            kept += 1
        LOG[key] = dict(cmeta, competition=name, rows_returned=len(rows or []), rows_kept=kept)
        time.sleep(0.2)

    permalinks = state.get("permalinks") or {}
    for fid, fx in fixtures.items():
        link = permalinks.get(fid)
        fx["hotspawn_url"] = link or LOBBY
        fx["hotspawn_url_kind"] = "official match page" if link else "official lobby page"
    ordered = sorted(fixtures.values(), key=lambda r: (r["start_utc"], r["fixture_id"]))
    return {"fixtures": ordered, "week": state.get("week"), "permalinks": permalinks,
            "competitions_swept": comps}


# --------------------------------------------------------------------------- quotes
def quote(source_key, source_name, public_url, api_url, event_id, team_a, team_b,
          dec_a, dec_b, start_utc, league, raw_format, raw_a, raw_b, extra=None) -> dict:
    nv = core.no_vig(dec_a, dec_b)
    rec = {
        "source_key": source_key, "source_name": source_name, "public_url": public_url,
        "api_url": api_url, "event_id": str(event_id), "team_a": team_a, "team_b": team_b,
        "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
        "raw_format": raw_format, "raw_a": str(raw_a), "raw_b": str(raw_b),
        "start_utc": start_utc, "league": league,
        "retrieved_utc": core.iso(core.now_utc()),
    }
    if nv:
        rec["prob_a"] = round(nv["prob_a"], 6)
        rec["prob_b"] = round(nv["prob_b"], 6)
        rec["overround"] = round(nv["overround"], 6)
    rec.update(extra or {})
    return rec


def collect_pinnacle(quotes: list) -> None:
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    LOG["pinnacle"] = dict(meta, quotes=0)
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
            da = core.american_to_decimal(by["home"])
            db = core.american_to_decimal(by["away"])
            if da and db:
                quotes.append(quote("pinnacle", "Pinnacle",
                                    "https://www.pinnacle.com/en/esports/cs2-hub", murl, m["id"],
                                    al["home"], al["away"], da, db,
                                    core.iso(core.parse_iso(str(m.get("startTime") or "")) or core.now_utc()),
                                    (m.get("league") or {}).get("name"), "american",
                                    by["home"], by["away"]))
                written += 1
            break
    LOG["pinnacle"]["quotes"] = written


def collect_bovada(quotes: list) -> None:
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    LOG["bovada"] = dict(meta, quotes=0)
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
                    start = core.parse_iso(str(ev.get("startTime"))) or core.now_utc()
                    quotes.append(quote("bovada", "Bovada",
                                        "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                                        BOVADA, ev.get("id"), home.get("name"), away.get("name"),
                                        float(dh), float(da), core.iso(start), league, "decimal", dh, da))
                    written += 1
                    break
    LOG["bovada"]["quotes"] = written


def collect_linefeed(quotes: list) -> None:
    seen: set[str] = set()
    for mirror in ("melbet", "22bet", "betwinner"):
        url = LINEFEED_URL.format(mirror=mirror)
        data, meta = fetch_json(url, {"Accept": "application/json"})
        LOG[f"linefeed_{mirror}"] = dict(meta, quotes=0)
        rows = (data or {}).get("Value") if isinstance(data, dict) else None
        written = 0
        for ev in rows if isinstance(rows, list) else []:
            league = str(ev.get("L") or ev.get("LE") or "")
            if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
                continue
            key = str(ev.get("I"))
            if key in seen:
                continue
            a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
            if not a or not b or PROP_RE.search(f"{a} {b}"):
                continue
            prices = {o.get("T"): o.get("C") for o in ev.get("E") or []
                      if o.get("G") == 1 and "P" not in o}
            if not prices.get(1) or not prices.get(3):
                continue
            seen.add(key)
            start = core.from_epoch_s(ev.get("S")) or core.now_utc()
            quotes.append(quote("melbet", "Melbet (1xBet platform)",
                                "https://melbet.com/en/line/esports", url, key, a, b,
                                float(prices[1]), float(prices[3]), core.iso(start), league,
                                "decimal", prices[1], prices[3], extra={"mirror": mirror}))
            written += 1
        LOG[f"linefeed_{mirror}"]["quotes"] = written


KALSHI_TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def kalshi_start(event_ticker: str):
    m = KALSHI_TICKER_TIME.search(str(event_ticker or ""))
    if not m:
        return None
    day, mon, yy, hh, mm = m.groups()
    if mon not in MONTHS:
        return None
    try:
        from datetime import datetime
        return datetime(2000 + int(yy), MONTHS[mon], int(day), int(hh), int(mm),
                        tzinfo=core.timezone.utc)
    except ValueError:
        return None


def _money(value):
    if value in (None, ""):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f <= 1.0 else f / 100.0


def collect_kalshi(quotes: list, attempts: list) -> None:
    data, meta = fetch_json(KALSHI.format(series="KXCS2GAME"), {"Accept": "application/json"})
    events = (data or {}).get("events") if isinstance(data, dict) else None
    LOG["kalshi_KXCS2GAME"] = dict(meta, events=len(events or []), quotes=0)
    written = 0
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        legs = []
        for mk in mks:
            bid = _money(mk.get("yes_bid_dollars") or mk.get("yes_bid"))
            ask = _money(mk.get("yes_ask_dollars") or mk.get("yes_ask"))
            legs.append({"team": mk.get("yes_sub_title") or "", "bid": bid, "ask": ask,
                         "spread": None if None in (bid, ask) else round(ask - bid, 4),
                         "volume": mk.get("volume"), "open_interest": mk.get("open_interest")})
        ticker = str(ev.get("event_ticker"))
        public_url = f"https://kalshi.com/markets/kxcs2game/{ticker.lower()}"
        base = {"source_key": "kalshi", "source_name": "Kalshi (exchange)",
                "public_url": public_url, "api_url": KALSHI.format(series="KXCS2GAME"),
                "event_id": ticker, "team_a": legs[0]["team"], "team_b": legs[1]["team"],
                "start_utc": core.iso(kalshi_start(ticker)) if kalshi_start(ticker) else None,
                "retrieved_utc": core.iso(core.now_utc()), "legs": legs}
        if any(leg["bid"] is None or leg["ask"] is None for leg in legs):
            attempts.append({**base, "reason": "one-sided or empty order book"})
            continue
        mids = [(leg["bid"] + leg["ask"]) / 2.0 for leg in legs]
        if sum(mids) <= 0:
            attempts.append({**base, "reason": "mid price could not be formed"})
            continue
        spread = max((leg["spread"] or 0) for leg in legs)
        prob_a = mids[0] / (mids[0] + mids[1])
        rec = quote("kalshi", "Kalshi (exchange)", public_url,
                    KALSHI.format(series="KXCS2GAME"), ticker, legs[0]["team"], legs[1]["team"],
                    1.0 / mids[0] if mids[0] else 0, 1.0 / mids[1] if mids[1] else 0,
                    base["start_utc"], ev.get("title"), "yes mid ($)",
                    round(mids[0], 4), round(mids[1], 4),
                    extra={"spread": round(spread, 4), "thin_book": bool(spread > 0.10),
                           "legs": legs, "prob_a": round(prob_a, 6), "prob_b": round(1 - prob_a, 6)})
        quotes.append(rec)
        written += 1
    LOG["kalshi_KXCS2GAME"]["quotes"] = written


def collect_bo3(quotes: list) -> dict:
    """Upcoming fixtures plus the Thunderpick two-way coefficient bo3.gg publishes per match.

    Schema (verified against the working collectors already in this repository): the payload is
    ``bet_updates = {"provider": ..., "team_1": {name, coeff, max_coeff, team_id}, "team_2": {...}}``.
    Team records are kept for the ids the feed references, because the rank in that record is the
    only rating this desk can read for the tier-C teams that no bookmaker prices and Valve does not
    rank — it becomes the last-resort ORIGINATED rung in build.py, always labelled as such.
    """
    matches: list[dict] = []
    for page in range(3):
        url = (f"{BO3}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               f"&filter%5Bmatches.status%5D%5Bin%5D=upcoming&sort=start_date"
               f"&page%5Blimit%5D=100&page%5Boffset%5D={page * 100}")
        data, meta = fetch_json(url, {"Accept": "application/json"})
        LOG[f"bo3gg_matches_p{page + 1}"] = dict(meta, rows=0, quotes=0)
        rows = (data or {}).get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        written = 0
        for m in rows:
            if not isinstance(m, dict):
                continue
            matches.append(m)
            bu = m.get("bet_updates") or {}
            t1, t2 = bu.get("team_1") or {}, bu.get("team_2") or {}
            try:
                da, db = float(t1.get("coeff")), float(t2.get("coeff"))
            except (TypeError, ValueError):
                continue
            if da <= 1.0 or db <= 1.0:
                continue
            name_a, name_b = t1.get("name") or "", t2.get("name") or ""
            if not name_a or not name_b or PROP_RE.search(f"{name_a} {name_b}"):
                continue
            tour = m.get("tournament") or {}
            quotes.append(quote("thunderpick", "Thunderpick (coefficients via bo3.gg)",
                                f"https://bo3.gg/matches/{m.get('slug')}",
                                f"{BO3}/matches/?filter%5Bmatches.id%5D%5Beq%5D={m.get('id')}",
                                m.get("id"), name_a, name_b, da, db,
                                core.iso(core.parse_iso(str(m.get("start_date") or "").replace("Z", "+00:00"))
                                         or core.now_utc()),
                                tour.get("name") if isinstance(tour, dict) else None, "decimal",
                                t1.get("coeff"), t2.get("coeff"),
                                extra={"provider": bu.get("provider"), "team1_id": m.get("team1_id"),
                                       "team2_id": m.get("team2_id"), "max_coeff_a": t1.get("max_coeff"),
                                       "max_coeff_b": t2.get("max_coeff")}))
            written += 1
        LOG[f"bo3gg_matches_p{page + 1}"]["rows"] = len(rows)
        LOG[f"bo3gg_matches_p{page + 1}"]["quotes"] = written
        if len(rows) < 100:
            break
        time.sleep(0.2)

    team_ids = sorted({str(i) for m in matches for i in (m.get("team1_id"), m.get("team2_id")) if i})
    teams: dict[str, dict] = {}
    for tid in team_ids[:120]:
        data, _ = fetch_json(f"{BO3}/teams/?filter%5Bteams.id%5D%5Beq%5D={tid}&limit=1",
                             {"Accept": "application/json"})
        rec = (data or {}).get("results") if isinstance(data, dict) else None
        if rec and isinstance(rec, list) and rec:
            row = rec[0]
            teams[tid] = {k: row.get(k) for k in ("id", "name", "slug", "acronym", "rank")}
        time.sleep(0.05)
    LOG["bo3gg_teams"] = {"teams": len(teams), "matches": len(matches)}
    return {"matches": len(matches), "teams": teams}


PM_TITLE = re.compile(r"^(?:Counter-Strike|CS2)\s*:\s*(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)"
                       r"\s*(?:\((?P<fmt>[^)]*)\))?\s*-\s*(?P<tour>.+)$", re.I)


def collect_polymarket(quotes: list, attempts: list) -> None:
    """CS2 match-winner markets only; a book with no traded volume is refused, not priced."""
    url = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports"
    data, meta = fetch_json(url, {"Accept": "application/json"})
    LOG["polymarket_events"] = dict(meta, cs2_events=0, quotes=0)
    events = data if isinstance(data, list) else (data or {}).get("events")
    if not isinstance(events, list):
        return
    cs2_events, written = 0, 0
    now = core.now_utc()
    for ev in events:
        m = PM_TITLE.match(str(ev.get("title") or "").strip())
        if not m:
            continue
        cs2_events += 1
        for mk in ev.get("markets") or []:
            outcomes, prices = mk.get("outcomes"), mk.get("outcomePrices")
            try:
                outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
                prices = [float(x) for x in (json.loads(prices) if isinstance(prices, str) else prices)]
            except (TypeError, ValueError):
                continue
            if not outcomes or len(outcomes) != 2 or len(prices) != 2:
                continue
            if mk.get("closed") or mk.get("active") is False:
                continue
            end = mk.get("endDate") or ev.get("endDate")
            end_dt = core.parse_iso(str(end)) if end else None
            if end_dt and end_dt < now:
                continue
            volume = float(mk.get("volumeNum") or mk.get("volume") or 0)
            public_url = f"https://polymarket.com/event/{ev.get('slug')}"
            base = {"source_key": "polymarket", "source_name": "Polymarket (prediction market)",
                    "public_url": public_url, "api_url": url, "event_id": ev.get("id"),
                    "team_a": str(outcomes[0]).strip(), "team_b": str(outcomes[1]).strip(),
                    "start_utc": core.iso(end_dt) if end_dt else None,
                    "retrieved_utc": core.iso(core.now_utc()), "volume_usd": round(volume, 2),
                    "raw_format": "share price ($)", "raw_a": prices[0], "raw_b": prices[1]}
            if volume < 25.0 or min(prices) <= 0.0:
                attempts.append({**base, "reason": f"untraded book (${volume:.2f} traded) — refused as a price"})
                continue
            total = prices[0] + prices[1]
            if total <= 0.5:
                attempts.append({**base, "reason": "no two-sided book"})
                continue
            prob_a = prices[0] / total
            quotes.append(quote("polymarket", "Polymarket (prediction market)", public_url, url,
                                ev.get("id"), base["team_a"], base["team_b"],
                                1.0 / prices[0], 1.0 / prices[1], base["start_utc"],
                                m.group("tour").strip(), "share price ($)", prices[0], prices[1],
                                extra={"prob_a": round(prob_a, 6), "prob_b": round(1 - prob_a, 6),
                                       "volume_usd": round(volume, 2)}))
            written += 1
    LOG["polymarket_events"].update({"cs2_events": cs2_events, "quotes": written})


# --------------------------------------------------------------------------- Valve VRS
def collect_vrs() -> dict:
    tree, meta = fetch_json(VRS_TREE, {"Accept": "application/vnd.github+json"})
    LOG["valve_vrs_tree"] = dict(meta)
    names = [n.get("name") for n in tree if isinstance(n, dict)] if isinstance(tree, list) else []
    files = sorted([n for n in names if n and n.startswith("standings_global") and n.endswith(".md")])
    if not files:
        return {"file": None, "teams": {}, "raw": None}
    latest = files[-1]
    body, fmeta = fetch(VRS_RAW.format(path=latest), {"Accept": "text/plain"})
    LOG["valve_vrs_file"] = dict(fmeta, file=latest)
    text = body.decode("utf-8", "replace") if body else ""
    teams: dict[str, dict] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        if not parts[1].isdigit():
            continue
        name, points = parts[2], parts[3]
        try:
            pts = float(points.replace(",", ""))
        except ValueError:
            continue
        teams[core.canon(name)] = {"name": name, "rank": int(parts[1]), "points": pts}
    return {"file": latest, "teams": teams,
            "source_url": VRS_RAW.format(path=latest),
            "repo_url": "https://github.com/ValveSoftware/counter-strike_regional_standings",
            "retrieved_utc": core.iso(core.now_utc())}


# --------------------------------------------------------------------------- main
def main() -> int:
    started = core.now_utc()
    hotspawn = collect_hotspawn()
    quotes: list[dict] = []
    attempts: list[dict] = []
    collect_pinnacle(quotes)
    collect_bovada(quotes)
    collect_linefeed(quotes)
    collect_kalshi(quotes, attempts)
    bo3 = collect_bo3(quotes)
    collect_polymarket(quotes, attempts)
    vrs = collect_vrs()

    snapshot = {
        "session": "34af18bf",
        "captured_utc": core.iso(core.now_utc()),
        "collection_seconds": round((core.now_utc() - started).total_seconds(), 2),
        "policy": {
            "hotspawn_role": "fixture discovery + settlement only; crowd pick % is ownership, never a probability",
            "probability_sources": ["pinnacle", "bovada", "melbet", "kalshi", "thunderpick",
                                    "polymarket", "research(dated,manual)", "valve_vrs(originated)"],
        },
        "hotspawn": {
            "week": hotspawn["week"],
            "competitions_swept": hotspawn["competitions_swept"],
            "fixtures": hotspawn["fixtures"],
            "permalinks": hotspawn["permalinks"],
        },
        "quotes": quotes,
        "refused_quotes": attempts,
        "vrs": vrs,
        "bo3_teams": bo3.get("teams") or {},
        "access": LOG,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "snapshot.json").write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    open_now = [f for f in hotspawn["fixtures"]
                if not f.get("lock_utc") or core.parse_iso(f["lock_utc"]) > core.now_utc()]
    print(json.dumps({
        "snapshot": str(OUT / "snapshot.json"),
        "fixtures_total_future": len(hotspawn["fixtures"]),
        "fixtures_open": len(open_now),
        "competitions": len(hotspawn["competitions_swept"]),
        "quotes": len(quotes),
        "by_source": {k: len([q for q in quotes if q["source_key"] == k])
                      for k in sorted({q["source_key"] for q in quotes})},
        "refused": len(attempts),
        "vrs_file": vrs.get("file"),
        "vrs_teams": len(vrs.get("teams") or {}),
        "blocked_sources": sorted(k for k, v in LOG.items()
                                  if isinstance(v, dict) and v.get("error")),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
