#!/usr/bin/env python3
"""EVERY-MATCH collector (session af573ff1). Runs on a GitHub-hosted runner.

Writes ``data/af573ff1/snapshot.json``: a fresh HotSpawn CS2 fixture check,
fallback-market quotes (Melbet LineFeed, Kalshi), official Valve VRS ratings
(global + regional files), a bo3.gg upcoming-fixture probe, and a per-source
access log. Blocked sources (HLTV, EGamersWorld) are recorded as failures —
never bypassed, never treated as "no price exists".

This collector exists so the fallback cascade in build.py always works from
fresh inputs; the featured line itself still comes from the featured board
(session f7279a54) and is never recomputed here.
"""
from __future__ import annotations

import base64
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote as urlquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "af573ff1"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
MELBET = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000"
          "&lng=en&mode=4&country=1")
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
BO3_UPCOMING = ("https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming"
                "&sort=start_date&page=1&limit=50")
EGW = "https://egamersworld.com/counterstrike/matches"
HLTV_RANKING = "https://www.hltv.org/ranking/teams"
# NOTE: no bare "rounds?" token here — the team literally named "Rounds" must not
# be mistaken for a rounds prop market (that exact bug hides RoundsGG prices in
# upstream feeds). Prop participants are still caught via total/handicap/maps/kills.
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|pistol", re.I)
LOG: dict = {}


def gh_headers():
    import os
    tok = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"} if tok else {}


def fetch(url, headers=None, timeout=45):
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
    try:
        return json.loads(body.decode("utf-8", "replace")) if body else None, meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


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
            if origin == "api":
                cur.update(fx)
            cur["seen_in"].append(origin)
    now = core.now_utc()
    open_fx = []
    for fx in fixtures.values():
        lock = core.parse_iso(fx.get("lock_utc") or fx["start_utc"])
        if fx.get("status") in ("scheduled", "started") and lock and lock > now:
            open_fx.append(fx)
    return {"fixtures": sorted(open_fx, key=lambda r: (r["start_utc"], r["fixture_id"])),
            "permalinks": state.get("permalinks") or {}}


def _q(source_key, source_name, public_url, api_url, event_id, a, b, dec_a, dec_b, start, league,
       raw_format, raw_a, raw_b, live=False):
    nv = core.no_vig(dec_a, dec_b)
    if not nv:
        return None
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url,
            "api_url": api_url, "event_id": str(event_id), "team_a": a, "team_b": b,
            "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
            "raw_format": raw_format, "raw_a": raw_a, "raw_b": raw_b,
            "prob_a": nv["prob_a"], "overround": nv["overround"],
            "start_utc": core.to_iso(start) if not isinstance(start, str) else start,
            "league": league, "live": bool(live),
            "retrieved_utc": core.to_iso(core.now_utc())}


def collect_melbet(quotes: list) -> None:
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    LOG["melbet"] = meta
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
        try:  # Melbet "S" is epoch seconds
            from datetime import datetime, timezone
            start = datetime.fromtimestamp(float(ev.get("S")), tz=timezone.utc)
        except (TypeError, ValueError):
            continue
        qq = _q("melbet", "Melbet", "https://melbet.com/en/line/esports", MELBET, ev.get("I"),
                a, b, float(prices[1]), float(prices[3]), start,
                league, "decimal", prices[1], prices[3])
        if qq is None:
            continue
        quotes.append(qq)
        written += 1
    LOG["melbet"]["quotes"] = written


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


KALSHI_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                 "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
KALSHI_TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def collect_kalshi(quotes: list) -> None:
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    LOG["kalshi"] = meta
    written = 0
    for ev in (data or {}).get("events", []) if isinstance(data, dict) else []:
        markets = ev.get("markets") or []
        if len(markets) != 2:
            continue
        sides = []
        for mk in markets:
            mid, spread = _kalshi_mid(mk)
            if mid is None or spread is None or spread > 0.10:
                sides = []
                break
            sides.append((str(mk.get("yes_sub_title") or mk.get("title") or ""), mid, mk))
        if len(sides) != 2 or PROP_RE.search(sides[0][0] + sides[1][0]):
            continue
        total = sides[0][1] + sides[1][1]
        if not 0.90 <= total <= 1.10:
            continue
        start = None
        m = KALSHI_TICKER_TIME.search(str(ev.get("event_ticker") or ""))
        if m:
            yy, mon, dd, hh, mm = m.groups()
            from datetime import datetime, timezone
            # Kalshi CS2 tickers are US Eastern kickoff times; convert ET->UTC (+4h, EDT in Oct).
            start = datetime(2000 + int(yy), KALSHI_MONTHS[mon], int(dd), int(hh) + 4, int(mm),
                             tzinfo=timezone.utc)
        qq = _q("kalshi", "Kalshi (exchange)",
                "https://kalshi.com/markets/kxcs2game/" + str(ev.get("event_ticker") or "").lower(),
                KALSHI, ev.get("event_ticker"), sides[0][0], sides[1][0],
                1.0 / sides[0][1] if sides[0][1] else None, 1.0 / sides[1][1] if sides[1][1] else None,
                start, str(ev.get("title") or ""), "yes mid ($)",
                round(sides[0][1], 4), round(sides[1][1], 4))
        if qq:
            qq["start_is_approx"] = True
            quotes.append(qq)
            written += 1
    LOG["kalshi"]["quotes"] = written


def parse_standings(text: str, base_dir: str) -> list:
    teams = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)",
                         text or "", re.M):
        teams.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                      "team": m.group(3).strip(), "roster": m.group(4).strip(),
                      "details_path": f"{base_dir}/{m.group(5).strip()}"})
    return teams


def collect_vrs() -> dict:
    tree, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1",
                            gh_headers())
    LOG["valve_vrs_tree"] = meta
    newest: dict[str, tuple] = {}
    for node in (tree or {}).get("tree", []) if isinstance(tree, dict) else []:
        m = re.match(r"^live/(\d{4})/standings_(global|europe|americas|asia)_(\d{4}_\d{2}_\d{2})\.md$",
                     str(node.get("path")))
        if m and (m.group(2) not in newest or m.group(3) > newest[m.group(2)][1]):
            newest[m.group(2)] = (m.group(1), m.group(3), node["path"])
    out = {"snapshot": None, "teams": [], "files": []}
    for region in ("global", "europe", "americas", "asia"):
        if region not in newest:
            continue
        _yr, date, path = newest[region]
        api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{path}"
        blob, meta2 = fetch_json(api_url, gh_headers())
        LOG[f"valve_vrs_{region}"] = meta2
        if not isinstance(blob, dict) or not blob.get("content"):
            continue
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
        teams = parse_standings(text, path.rsplit("/", 1)[0])
        for t in teams:
            t["region_file"] = region
        out["teams"].extend(teams)
        out["files"].append({"region": region, "path": path, "api_url": api_url,
                             "page_url": f"https://github.com/{VRS_REPO}/blob/main/{path}",
                             "snapshot": date, "teams": len(teams)})
        if region == "global":
            out["snapshot"] = date
            out["page_url"] = f"https://github.com/{VRS_REPO}/blob/main/{path}"
            out["api_url"] = api_url
    return out


def probe(name: str, url: str) -> None:
    _body, meta = fetch(url, {"Accept": "text/html,application/json"}, timeout=30)
    LOG[name] = meta


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = core.to_iso(core.now_utc())
    hs = collect_hotspawn()
    quotes: list = []
    collect_melbet(quotes)
    collect_kalshi(quotes)
    vrs = collect_vrs()
    # Information-source probes: results are published, failures are evidence.
    _bo3, meta_bo3 = fetch_json(BO3_UPCOMING, {"Accept": "application/json"}, timeout=30)
    LOG["bo3_upcoming"] = {**meta_bo3,
                           "results": len((_bo3 or {}).get("results") or []) if isinstance(_bo3, dict) else 0}
    probe("egamersworld_probe", EGW)
    probe("hltv_probe", HLTV_RANKING)
    snap = {"session": "af573ff1", "collected_from_utc": started,
            "collected_to_utc": core.to_iso(core.now_utc()),
            "hotspawn": hs, "quotes": quotes, "vrs": vrs, "access_log": LOG}
    (OUT / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n")
    print("open fixtures", len(hs["fixtures"]), "quotes", len(quotes),
          "vrs teams", len(vrs.get("teams", [])), "sources ok",
          [k for k, v in LOG.items() if isinstance(v, dict) and v.get("status") == 200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
