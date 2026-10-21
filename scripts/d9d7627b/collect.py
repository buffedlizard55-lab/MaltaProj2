#!/usr/bin/env python3
"""Live collector for the HotSpawn CS2 every-match picks board (session d9d7627b).

Runs where general internet is available (GitHub Actions). Writes
``data/d9d7627b/snapshot.json``: the HotSpawn CS2 fixture inventory, every external
two-way match-winner price found, the official Valve VRS standings, and a per-source
access log (HTTP status, bytes, SHA-256, error) so a blocked source is recorded as a
failure — never silently as "no price".

Sources (all public, unauthenticated, read-only; endpoint research originally by
session f7279a54 and re-verified against recorded payloads on 2026-10-21):
  * HotSpawn lobby page transfer state + the public fixtures API the page calls
  * Pinnacle guest odds API        (licensed bookmaker; key is Pinnacle's own public web-client key)
  * Bovada coupon JSON             (licensed bookmaker)
  * Melbet LineFeed JSON           (licensed bookmaker)
  * Kalshi trade API               (regulated exchange; feed has no verified kickoff -> evidence only)
  * Polymarket Gamma API           (prediction market; strict parser, joins only on verified names+start)
  * HLTV                           (access probe only — HTTP 403 to automation as of 2026-10-21)
  * ValveSoftware/counter-strike_regional_standings via api.github.com (official VRS)
"""
from __future__ import annotations
import importlib.util as _ilu, sys as _sys
from pathlib import Path as _Path
def _load_d9(name):
    key = f"d9d7627b_{name}"
    if key in _sys.modules:
        return _sys.modules[key]
    p = _Path(__file__).resolve().parent / f"{name}.py" if (_Path(__file__).resolve().parent / f"{name}.py").exists() else _Path(__file__).resolve().parents[1] / "scripts" / "d9d7627b" / f"{name}.py"
    spec = _ilu.spec_from_file_location(key, p)
    mod = _ilu.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


import base64
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
core = _load_d9('core')

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "d9d7627b"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",  # public guest web-client key
               "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
MELBET = "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
POLYMARKET = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=counter-strike"
HLTV = "https://www.hltv.org/matches"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
KALSHI_MAX_SPREAD = 0.10
# Participant names containing these words are props/totals, not match-winner markets.
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol", re.I)
PIN_MAX_MATCHUPS = 120

LOG: dict = {}


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
    except Exception as exc:  # noqa: BLE001 - network failures are evidence, not crashes
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    if body:
        meta["sha256"] = hashlib.sha256(body).hexdigest()
    return body, meta


def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    if not body:
        return None, meta
    try:
        return json.loads(body.decode("utf-8", "replace")), meta
    except ValueError:
        meta["error"] = ((meta["error"] or "") + " invalid JSON").strip()
        return None, meta


def quote(source_key, source_name, public_url, api_url, event_id, a, b, dec_a, dec_b,
          start_dt, league, raw_format, raw_a, raw_b, live=False, start_is_approx=False):
    nv = core.no_vig(dec_a, dec_b)
    if nv is None or not a or not b:
        return None
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url,
            "api_url": api_url, "event_id": str(event_id), "team_a": str(a), "team_b": str(b),
            "decimal_a": round(float(dec_a), 6), "decimal_b": round(float(dec_b), 6),
            "raw_format": raw_format, "raw_a": raw_a, "raw_b": raw_b,
            "prob_a": nv["prob_a"], "overround": nv["overround"],
            "start_utc": core.to_iso(start_dt), "start_is_approx": bool(start_is_approx),
            "league": league, "live": bool(live),
            "retrieved_utc": core.to_iso(core.now_utc())}


# ---------------------------------------------------------------------------- HotSpawn

def collect_hotspawn() -> dict:
    page, meta = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=60)
    LOG["hotspawn_lobby_page"] = meta
    state = core.lobby_state(page.decode("utf-8", "replace")) if page else {}
    page_fx = state.get("fixtures") or []
    LOG["hotspawn_lobby_page"]["fixtures_in_transfer_state"] = len(page_fx)
    api_fx, meta2 = fetch_json(HS_API, {"Accept": "application/json", "Referer": LOBBY_PAGE}, 90)
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
            if origin == "api" and "lobby_page" not in cur["seen_in"]:
                cur.update(fx)  # API-only history informs results, not lobby membership
            cur["seen_in"].append(origin)
    permalinks = state.get("permalinks") or {}
    for fx in fixtures.values():
        fx["hotspawn_url"] = permalinks.get(fx["fixture_id"]) or LOBBY_PAGE
        fx["hotspawn_url_kind"] = "match page" if fx["fixture_id"] in permalinks else "lobby"
    # Retention: the API returns full history. Keep every lobby-listed row, every
    # scheduled/started row, and rows started within 4 days; count the rest.
    cutoff = core.to_iso(core.now_utc() - timedelta(days=4))
    status_counts: dict[str, int] = {}
    kept = {}
    for fid, fx in fixtures.items():
        status_counts[str(fx.get("status"))] = status_counts.get(str(fx.get("status")), 0) + 1
        if ("lobby_page" in fx["seen_in"] or fx.get("status") in ("scheduled", "started")
                or (fx["start_utc"] or "") >= cutoff):
            kept[fid] = fx
    LOG["hotspawn_api"]["cs2_status_counts_all_rows"] = status_counts
    LOG["hotspawn_api"]["cs2_rows_kept"] = len(kept)
    return {"fixtures": sorted(kept.values(), key=lambda r: (r["start_utc"], r["fixture_id"])),
            "permalinks": permalinks, "week": state.get("week")}


# ----------------------------------------------------------------------- book: Pinnacle

def parse_pinnacle_matchups(payload) -> list[dict]:
    """CS2 match-winner matchups from the Pinnacle guest sports/12/matchups payload."""
    out = []
    for m in payload if isinstance(payload, list) else []:
        if not isinstance(m, dict) or m.get("type") != "matchup" or m.get("parentId"):
            continue
        parts = m.get("participants") or []
        league = str((m.get("league") or {}).get("name") or "")
        if len(parts) != 2 or not re.match(r"^(CS2|Counter-Strike)", league, re.I):
            continue
        names = [str(p.get("name") or "") for p in parts]
        if any(PROP_RE.search(n) for n in names):
            continue
        out.append(m)
    return out


def parse_pinnacle_markets(matchup: dict, markets, api_url: str) -> dict | None:
    """First open full-match moneyline in a markets/related/straight payload."""
    al = {p.get("alignment"): p.get("name") for p in matchup.get("participants") or []}
    for mk in markets if isinstance(markets, list) else []:
        if (mk.get("type") != "moneyline" or mk.get("period") != 0 or mk.get("isAlternate")
                or mk.get("matchupId") != matchup.get("id") or mk.get("status") != "open"):
            continue
        by = {p.get("designation"): p.get("price") for p in mk.get("prices") or []}
        if None in (by.get("home"), by.get("away"), al.get("home"), al.get("away")):
            continue
        da = core.american_to_decimal(by["home"])
        db = core.american_to_decimal(by["away"])
        if da and db:
            return quote("pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub",
                         api_url, matchup["id"], al["home"], al["away"], da, db,
                         core.parse_any(matchup.get("startTime")),
                         (matchup.get("league") or {}).get("name"), "american",
                         by["home"], by["away"],
                         live=bool(matchup.get("isLive") or mk.get("isLive")))
    return None


def collect_pinnacle(quotes: list) -> None:
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    LOG["pinnacle"] = meta
    matchups = parse_pinnacle_matchups(data)
    LOG["pinnacle"]["cs2_matchups"] = len(matchups)
    written = 0
    for m in matchups[:PIN_MAX_MATCHUPS]:
        murl = f"{PIN}/matchups/{m['id']}/markets/related/straight"
        markets, _ = fetch_json(murl, PIN_HEADERS)
        time.sleep(0.1)
        q = parse_pinnacle_markets(m, markets, murl)
        if q:
            quotes.append(q)
            written += 1
    LOG["pinnacle"]["quotes"] = written


# ------------------------------------------------------------------------- book: Bovada

def parse_bovada(payload) -> list[dict]:
    out = []
    for group in payload if isinstance(payload, list) else []:
        league = ((group.get("path") or [{}])[-1] or {}).get("description")
        for ev in group.get("events") or []:
            comps = ev.get("competitors") or []
            if len(comps) != 2 or any(PROP_RE.search(str(c.get("name"))) for c in comps):
                continue
            home = next((c for c in comps if c.get("home")), comps[0])
            away = next(c for c in comps if c is not home)
            done = False
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if (str(mk.get("description", "")).strip().casefold() != "moneyline"
                            or not (mk.get("period") or {}).get("main")
                            or mk.get("status") != "O" or (mk.get("period") or {}).get("live")):
                        continue
                    outs = {str(o.get("competitorId")): o for o in mk.get("outcomes") or []}
                    oh, oa = outs.get(str(home.get("id"))), outs.get(str(away.get("id")))
                    if not oh or not oa or oh.get("status") != "O" or oa.get("status") != "O":
                        continue
                    dh = (oh.get("price") or {}).get("decimal")
                    da = (oa.get("price") or {}).get("decimal")
                    if not dh or not da:
                        continue
                    q = quote("bovada", "Bovada",
                              "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                              BOVADA, ev.get("id"), home.get("name"), away.get("name"),
                              float(dh), float(da), core.parse_any(ev.get("startTime")),
                              league, "decimal", dh, da, live=bool(ev.get("live")))
                    if q:
                        out.append(q)
                        done = True
                    break
                if done:
                    break
    return out


def collect_bovada(quotes: list) -> None:
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    LOG["bovada"] = meta
    parsed = parse_bovada(data)
    quotes.extend(parsed)
    LOG["bovada"]["quotes"] = len(parsed)


# ------------------------------------------------------------------------- book: Melbet

def parse_melbet(payload) -> list[dict]:
    out = []
    rows = (payload or {}).get("Value") if isinstance(payload, dict) else None
    for ev in rows if isinstance(rows, list) else []:
        league = str(ev.get("L") or ev.get("LE") or "")
        if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
            continue
        a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
        if not a or not b or PROP_RE.search(f"{a} {b}"):
            continue
        prices = {o.get("T"): o.get("C") for o in ev.get("E") or []
                  if o.get("G") == 1 and "P" not in o}
        if not prices.get(1) or not prices.get(3):
            continue
        q = quote("melbet", "Melbet", "https://melbet.com/en/line/esports", MELBET,
                  ev.get("I"), a, b, float(prices[1]), float(prices[3]),
                  core.parse_any(ev.get("S")), league, "decimal", prices[1], prices[3])
        if q:
            out.append(q)
    return out


def collect_melbet(quotes: list) -> None:
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    LOG["melbet"] = meta
    parsed = parse_melbet(data)
    quotes.extend(parsed)
    LOG["melbet"]["quotes"] = len(parsed)


# -------------------------------------------------------------------- exchange: Kalshi

def _kalshi_mid(mk: dict) -> tuple[float | None, float | None]:
    def num(*keys):
        for k in keys:
            v = mk.get(k)
            if v not in (None, ""):
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                return f if k.endswith("_dollars") else f / 100.0
        return None
    bid, ask = num("yes_bid_dollars", "yes_bid"), num("yes_ask_dollars", "yes_ask")
    if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid:
        return None, None
    return (bid + ask) / 2.0, ask - bid


def parse_kalshi(payload) -> tuple[list[dict], list[dict]]:
    """Kalshi prices are recorded with start_is_approx=True: the feed's event ticker has
    no verified timezone/kickoff semantics, so the join step publishes them as rejected
    joins (evidence) instead of guessing a kickoff time."""
    quotes, rejected = [], []
    events = (payload or {}).get("events") if isinstance(payload, dict) else None
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        names = [m.get("yes_sub_title") or "" for m in mks]
        mids = [_kalshi_mid(m) for m in mks]
        tick = ev.get("event_ticker")
        rec = {"source_key": "kalshi", "event_id": tick, "team_a": names[0], "team_b": names[1],
               "public_url": f"https://kalshi.com/markets/kxcs2game/{str(tick).lower()}"}
        if any(m[0] is None for m in mids) or any((m[1] or 0) > KALSHI_MAX_SPREAD for m in mids):
            rejected.append({**rec,
                             "reason": "thin or one-sided order book (bid/ask missing or spread > 10c)",
                             "books": [{k: m.get(k) for k in ("ticker", "yes_bid_dollars",
                                                               "yes_ask_dollars", "yes_bid",
                                                               "yes_ask")} for m in mks]})
            continue
        q = quote("kalshi", "Kalshi (exchange)", rec["public_url"], KALSHI, tick,
                  names[0], names[1], 1.0 / mids[0][0], 1.0 / mids[1][0], None,
                  ev.get("title"), "yes mid ($)", round(mids[0][0], 4), round(mids[1][0], 4),
                  start_is_approx=True)
        if q:
            quotes.append(q)
    return quotes, rejected


def collect_kalshi(quotes: list, rejected: list) -> None:
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    LOG["kalshi"] = meta
    qs, rj = parse_kalshi(data)
    quotes.extend(qs)
    rejected.extend(rj)
    LOG["kalshi"]["quotes"] = len(qs)
    LOG["kalshi"]["rejected_thin_books"] = len(rj)


# --------------------------------------------------------------- prediction: Polymarket

def parse_polymarket(payload) -> tuple[list[dict], dict]:
    """Strict Polymarket Gamma parser.

    Only two-outcome markets are considered. A quote is emitted only when the market
    carries a parseable explicit game start (``gameStartTime``); markets with merely an
    end/close date are counted as unverifiable evidence, never joined by guessing.
    As of 2026-10-21 no CS2 match-winner markets have been observed on Polymarket;
    the returned stats record that finding each run instead of assuming it.
    """
    quotes: list[dict] = []
    stats = {"events": 0, "markets": 0, "two_outcome": 0, "with_game_start": 0}
    events = payload if isinstance(payload, list) else []
    stats["events"] = len(events)
    for ev in events:
        for mk in ev.get("markets") or []:
            stats["markets"] += 1
            try:
                outcomes = json.loads(mk.get("outcomes") or "[]")
                prices = [float(p) for p in json.loads(mk.get("outcomePrices") or "[]")]
            except (ValueError, TypeError):
                continue
            if len(outcomes) != 2 or len(prices) != 2:
                continue
            stats["two_outcome"] += 1
            a, b = str(outcomes[0]).strip(), str(outcomes[1]).strip()
            if PROP_RE.search(f"{a} {b}") or not all(0.0 < p < 1.0 for p in prices):
                continue
            start = core.parse_any(mk.get("gameStartTime"))
            if start is not None:
                stats["with_game_start"] += 1
            slug = ev.get("slug") or mk.get("slug") or ""
            q = quote("polymarket", "Polymarket", f"https://polymarket.com/event/{slug}",
                      POLYMARKET, mk.get("id") or ev.get("id"), a, b,
                      1.0 / prices[0], 1.0 / prices[1], start,
                      ev.get("title"), "probability", prices[0], prices[1],
                      start_is_approx=start is None)
            if q:
                quotes.append(q)
    return quotes, stats


def collect_polymarket(quotes: list) -> None:
    data, meta = fetch_json(POLYMARKET, {"Accept": "application/json"})
    LOG["polymarket"] = meta
    qs, stats = parse_polymarket(data)
    quotes.extend(qs)
    LOG["polymarket"].update(stats)
    LOG["polymarket"]["quotes"] = len(qs)


def probe_hltv() -> None:
    body, meta = fetch(HLTV, {"Accept": "text/html"})
    meta["looks_like_challenge"] = bool(
        re.search(rb"cf-chl|challenge-platform|Just a moment", body[:20000]))
    LOG["hltv_probe"] = meta


# --------------------------------------------------------------------------------- VRS

def gh_headers() -> dict:
    import os
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return h


DETAILS_DATE = re.compile(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)
VRS_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)", re.M)


def latest_match_date(details_md: str) -> str | None:
    dates = DETAILS_DATE.findall(details_md or "")
    return max(dates) if dates else None


def parse_vrs_standings(text: str, base_dir: str) -> list[dict]:
    return [{"standing": int(m.group(1)), "points": int(m.group(2)),
             "team": m.group(3).strip(), "roster": m.group(4).strip(),
             "details_path": f"{base_dir}/{m.group(5).strip()}"}
            for m in VRS_ROW.finditer(text or "")]


def collect_vrs(fixture_names: set[str]) -> dict:
    tree, meta = fetch_json(
        f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1", gh_headers())
    LOG["valve_vrs_tree"] = meta
    newest = None
    for node in (tree or {}).get("tree", []) if isinstance(tree, dict) else []:
        m = re.match(r"^live/(\d{4})/standings_global_(\d{4}_\d{2}_\d{2})\.md$",
                     str(node.get("path")))
        if m and (newest is None or m.group(2) > newest[1]):
            newest = (m.group(1), m.group(2), node["path"])
    if not newest:
        return {}
    api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{newest[2]}"
    blob, meta2 = fetch_json(api_url, gh_headers())
    LOG["valve_vrs_file"] = meta2
    if not isinstance(blob, dict) or not blob.get("content"):
        return {}
    text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
    teams = parse_vrs_standings(text, newest[2].rsplit("/", 1)[0])
    # Duplicate team names: VRS keeps an older roster of the same organisation as a
    # separate row. For names in the fixture list, fetch each candidate's official
    # details file and record its most recent counted match date (published for review;
    # the Resolver still refuses to guess which roster plays). Cached per snapshot.
    cache_path = OUT / "vrs_details_cache.json"
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    if cache.get("snapshot") != newest[1]:
        cache = {"snapshot": newest[1], "latest_match": {}}
    keys: dict[str, list] = {}
    for t in teams:
        keys.setdefault(core.canon(t["team"])[0], []).append(t)
    wanted = {core.canon(n)[0] for n in fixture_names}
    fetched = 0
    for key, rows in keys.items():
        if len(rows) < 2 or key not in wanted:
            continue
        for t in rows:
            path = t["details_path"]
            if path not in cache["latest_match"]:
                from urllib.parse import quote as urlquote
                dblob, _ = fetch_json(
                    f"https://api.github.com/repos/{VRS_REPO}/contents/{urlquote(path)}",
                    gh_headers())
                fetched += 1
                md = (base64.b64decode(dblob["content"]).decode("utf-8", "replace")
                      if isinstance(dblob, dict) and dblob.get("content") else "")
                cache["latest_match"][path] = latest_match_date(md)
            t["latest_match_date"] = cache["latest_match"][path]
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    LOG["valve_vrs_file"]["details_files_fetched"] = fetched
    LOG["valve_vrs_file"]["teams_parsed"] = len(teams)
    return {"snapshot": newest[1], "path": newest[2], "api_url": api_url,
            "page_url": f"https://github.com/{VRS_REPO}/blob/main/{newest[2]}",
            "teams": teams}


# ----------------------------------------------------------------------------------- main

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = core.to_iso(core.now_utc())
    hs = collect_hotspawn()
    quotes: list = []
    rejected: list = []
    for fn in (collect_pinnacle, collect_bovada, collect_melbet, collect_polymarket):
        try:
            fn(quotes)
        except Exception as exc:  # noqa: BLE001
            LOG.setdefault(fn.__name__.replace("collect_", ""), {})["crash"] = \
                f"{type(exc).__name__}: {exc}"[:300]
    try:
        collect_kalshi(quotes, rejected)
    except Exception as exc:  # noqa: BLE001
        LOG.setdefault("kalshi", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        probe_hltv()
    except Exception as exc:  # noqa: BLE001
        LOG.setdefault("hltv_probe", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    names = {n for f in hs["fixtures"] for n in (f["team_a"], f["team_b"])}
    vrs: dict = {}
    try:
        vrs = collect_vrs(names)
    except Exception as exc:  # noqa: BLE001
        LOG.setdefault("valve_vrs", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    snap = {"session": "d9d7627b", "seed": None,
            "collected_from_utc": started, "collected_to_utc": core.to_iso(core.now_utc()),
            "hotspawn": hs, "quotes": quotes, "rejected_quotes": rejected,
            "vrs": vrs, "access_log": LOG}
    if not any("lobby_page" in f.get("seen_in", []) for f in hs["fixtures"]):
        # Never publish an empty board: keep the previous inventory, log the failure.
        prev = OUT / "snapshot.json"
        if prev.exists():
            old = json.loads(prev.read_text())
            snap["hotspawn"] = old.get("hotspawn", hs)
            previous_meta = (old.get("access_log") or {}).get("hotspawn_lobby_page") or {}
            snap["hotspawn_fallback_from"] = (old.get("hotspawn_fallback_from")
                                              or previous_meta.get("at_utc")
                                              or old.get("collected_to_utc"))
            LOG["hotspawn_failed_refresh"] = LOG.get("hotspawn_lobby_page", {})
            LOG["hotspawn_lobby_page"] = previous_meta
    (OUT / "snapshot.json").write_text(
        json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items()
                           if kk in ("status", "error", "quotes", "rows",
                                     "fixtures_in_transfer_state", "looks_like_challenge",
                                     "events", "markets", "two_outcome", "with_game_start")}
                      for k, v in LOG.items() if isinstance(v, dict)}, indent=1))
    print("fixtures", len(snap["hotspawn"]["fixtures"]), "quotes", len(quotes),
          "vrs teams", len(vrs.get("teams", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
