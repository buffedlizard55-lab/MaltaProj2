#!/usr/bin/env python3
"""HQ collector (session 77faf95c). Runs on a GitHub-hosted runner (general internet access).

Purpose
-------
Collect, in one dated capture, everything needed to price **every** Counter-Strike 2 fixture the
HotSpawn Pick'ems lobby lists:

  * https://play.hotspawn.com/lobby                      (fixture discovery; Angular transfer state)
  * https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures
                                                          (the same public API the lobby calls, so
                                                           fixtures added after the page cache was
                                                           built are still covered)
  * Pinnacle guest odds API          (licensed bookmaker; public guest key used by its own web app)
  * Bovada coupon JSON               (licensed bookmaker)
  * Melbet / 1xBet-platform LineFeed (licensed bookmaker; prices most low-tier CCT/NODWIN events)
  * Kalshi KXCS2GAME                 (CFTC-regulated exchange; midpoints are not executable odds)

HotSpawn is **fixture discovery and settlement only**. Its crowd "picked %" is never copied and
never used as a win probability.

Outputs (all under ``data/77faf95c/``):
  raw/hotspawn.json   the exact fixtures array embedded in the lobby render + permalinks + week
  raw/pinnacle.json   the CS2 matchup objects kept, with the straight market payload used
  raw/bovada.json     the raw coupon JSON
  raw/melbet.json     the raw LineFeed JSON
  raw/kalshi.json     the raw events JSON
  quotes.json         every two-way match-winner quote normalised, with its own source URL
  access.json         HTTP status / bytes / error for every request, so a blocked source is
                      recorded as a failure and never as "no price exists"

Nothing here derives a probability. Derivation happens in build.py, which re-computes every number
from the retained raw prices so the published value can be audited.
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "77faf95c"
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

LOBBY_STATE_RE = re.compile(r'<script id="[^"]*transfer-state[^"]*"[^>]*>(.*?)</script>', re.S)
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol|winner", re.I)
CS2_LEAGUE_RE = re.compile(r"^(CS2|Counter-Strike|CS 2|CS:GO)", re.I)
MAX_TOTAL_RAW_BYTES = 12_000_000

ACCESS: dict = {}
RAW_FILES: dict = {}
QUOTES: list = []


# ----------------------------------------------------------------------------- helpers
def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ms(value):
    """HotSpawn sends epoch milliseconds; tolerate seconds."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n > 1e12:
        n /= 1000.0
    return datetime.fromtimestamp(n, tz=timezone.utc)


def fetch(url, headers=None, timeout=45):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    meta = {"url": url, "http_status": None, "response_bytes": 0, "error": None,
            "at_utc": iso(now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read()
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


def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    try:
        return (json.loads(body.decode("utf-8", "replace")) if body else None), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


def keep_raw(name, obj):
    """Retain a source payload as evidence, bounded in total size."""
    blob = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    budget = MAX_TOTAL_RAW_BYTES - sum(len(v) for v in RAW_FILES.values())
    if len(blob) > budget:
        RAW_FILES[name] = json.dumps({"truncated": True, "reason": "size budget exceeded"}).encode()
        return
    RAW_FILES[name] = blob


def record(key, meta, **extra):
    ACCESS[key] = {**meta, **extra}


def american_to_decimal(price):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return 1 + p / 100.0 if p > 0 else 1 + 100.0 / abs(p)


def quote(source_key, source_name, public_url, api_url, event_id, team_a, team_b,
          dec_a, dec_b, start_utc, league, raw_format, raw_a, raw_b, live=False, extra=None):
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url,
            "api_url": api_url, "event_id": str(event_id), "team_a": team_a, "team_b": team_b,
            "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
            "raw_format": raw_format, "raw_a": raw_a, "raw_b": raw_b,
            "start_utc": start_utc, "league": league, "live": bool(live),
            "extra": extra or {}, "retrieved_utc": iso(now_utc())}


# --------------------------------------------------------------------------- HotSpawn
def lobby_state(page_html):
    m = LOBBY_STATE_RE.search(page_html or "")
    if not m:
        return {}
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return {}
    out = {"fixtures": None, "fixtures_url": None, "permalinks": {}, "week": None}
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        if url.split("?")[0].endswith("/api/v1/fixtures") and isinstance(body, list):
            out["fixtures"], out["fixtures_url"] = body, url
        elif "permalinks" in url and isinstance(body, dict) and isinstance(body.get("permalinks"), dict):
            out["permalinks"] = {str(k): str(v) for k, v in body["permalinks"].items()
                                 if re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(v))}
        elif "week-prizes" in url and isinstance(body, dict):
            out["week"] = {k: body.get(k) for k in ("weekId", "sportAlias", "status",
                                                    "weekStartUtc", "weekEndUtc", "cutoffUtc")}
    return out


def fixture_from_hotspawn(f):
    """Normalise one HotSpawn row. Crowd pick percentages are deliberately not copied."""
    if not isinstance(f, dict) or str(f.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(f.get("scheduled_start_time")), parse_ms(f.get("lock_time"))
    a, b = f.get("participants0_name"), f.get("participants1_name")
    if not f.get("id") or not a or not b or start is None:
        return None
    return {"fixture_id": str(f["id"]), "competition": f.get("competition_name"),
            "tier": (str(f.get("tier") or "").upper() or None), "stage": f.get("stage"),
            "best_of": f.get("best_of"), "status": f.get("status"),
            "points": f.get("offered_points"),
            "start_utc": iso(start), "lock_utc": iso(lock) if lock else None,
            "team_a": str(a).strip(), "team_b": str(b).strip(),
            "team_a_id": f.get("participants0_id"), "team_b_id": f.get("participants1_id"),
            "score_a": f.get("participants0_score"), "score_b": f.get("participants1_score")}


def collect_hotspawn():
    page, meta = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=60)
    state = lobby_state(page.decode("utf-8", "replace")) if page else {}
    page_fx = [f for f in (state.get("fixtures") or []) if str((f or {}).get("sport_alias", "cs2")).casefold() == "cs2"]
    record("hotspawn_lobby_page", meta, rows_total=len(state.get("fixtures") or []), rows_cs2=len(page_fx))

    api_rows, meta2 = fetch_json(HS_API, {"Accept": "application/json", "Referer": LOBBY_PAGE}, 90)
    api_rows = api_rows if isinstance(api_rows, list) else []
    record("hotspawn_api", meta2, rows=len(api_rows))

    fixtures = {}
    for origin, rows in (("lobby_page", page_fx), ("api", api_rows)):
        for raw in rows:
            fx = fixture_from_hotspawn(raw)
            if not fx:
                continue
            cur = fixtures.setdefault(fx["fixture_id"], {**fx, "seen_in": []})
            if origin == "api" and "lobby_page" not in cur["seen_in"]:
                cur.update({k: v for k, v in fx.items() if k != "seen_in"})
            if origin not in cur["seen_in"]:
                cur["seen_in"].append(origin)

    # The direct API holds the whole history (>10k rows). Keep the lobby rows, anything still to be
    # played, and anything that ended in the last 7 days (settlement evidence).
    cutoff = now_utc() - __import__("datetime").timedelta(days=7)
    status_counts = {}
    kept = {}
    for fid, fx in fixtures.items():
        status_counts[str(fx.get("status"))] = status_counts.get(str(fx.get("status")), 0) + 1
        if "lobby_page" in fx["seen_in"] or fx.get("status") in ("scheduled", "started") \
                or (fx.get("start_utc") or "") >= iso(cutoff):
            kept[fid] = fx
    record("hotspawn_api", ACCESS["hotspawn_api"], rows=len(api_rows),
           cs2_status_counts=status_counts, cs2_rows_kept=len(kept))

    permalinks = state.get("permalinks") or {}
    for fid, fx in kept.items():
        fx["hotspawn_url"] = permalinks.get(fid) or f"https://play.hotspawn.com/lobby"
        fx["hotspawn_url_kind"] = "match page" if fid in permalinks else "lobby (no per-match link published)"
    keep_raw("hotspawn", {"fixtures_url": state.get("fixtures_url"), "week": state.get("week"),
                          "fixtures": sorted(kept.values(), key=lambda r: (r["start_utc"], r["fixture_id"]))})
    return sorted(kept.values(), key=lambda r: (r["start_utc"], r["fixture_id"])), state.get("week")


# --------------------------------------------------------------------------- bookmakers
def collect_pinnacle():
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    if not isinstance(data, list):
        record("pinnacle", meta, cs2_matchups=0, quotes=0)
        return
    cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
          and len(m.get("participants") or []) == 2 and not m.get("parentId")
          and CS2_LEAGUE_RE.match(str((m.get("league") or {}).get("name") or ""))]
    kept, written = [], 0
    for m in cs:
        names = [str(p.get("name") or "") for p in m["participants"]]
        if any(PROP_RE.search(n) for n in names):
            continue
        murl = f"{PIN}/matchups/{m['id']}/markets/related/straight"
        markets, _ = fetch_json(murl, PIN_HEADERS)
        time.sleep(0.05)
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
                QUOTES.append(quote("pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub",
                                    murl, m["id"], al["home"], al["away"], da, db,
                                    m.get("startTime"), (m.get("league") or {}).get("name"),
                                    "american", by["home"], by["away"], live=m.get("isLive")))
                written += 1
                kept.append({"matchup": m, "market": mk})
            break
    record("pinnacle", meta, esports_matchups=len(data), cs2_matchups=len(cs), quotes=written)
    keep_raw("pinnacle", {"sport_matchups_url": f"{PIN}/sports/12/matchups",
                          "kept_matchups": kept})


def collect_bovada():
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
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
                    dh, da = (oh.get("price") or {}).get("decimal"), (oa.get("price") or {}).get("decimal")
                    if not dh or not da:
                        continue
                    QUOTES.append(quote("bovada", "Bovada",
                                        "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                                        BOVADA, ev.get("id"), home.get("name"), away.get("name"),
                                        float(dh), float(da),
                                        iso(datetime.fromtimestamp(float(ev["startTime"]) / 1000, tz=timezone.utc))
                                        if ev.get("startTime") else None,
                                        league, "decimal", dh, da, live=ev.get("live"),
                                        extra={"event_description": ev.get("description")}))
                    written += 1
                    break
    record("bovada", meta, quotes=written)
    keep_raw("bovada", data if data is not None else {"error": meta.get("error")})


def collect_melbet():
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    rows = (data or {}).get("Value") if isinstance(data, dict) else None
    rows = rows if isinstance(rows, list) else []
    written = 0
    for ev in rows:
        league = str(ev.get("L") or ev.get("LE") or "")
        if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
            continue
        a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
        if not a or not b or PROP_RE.search(f"{a} {b}"):
            continue
        prices = {o.get("T"): o.get("C") for o in ev.get("E") or [] if o.get("G") == 1 and "P" not in o}
        if not prices.get(1) or not prices.get(3):
            continue
        QUOTES.append(quote("melbet", "Melbet (1xBet platform)", "https://melbet.com/en/line/esports",
                            MELBET, ev.get("I"), a, b, float(prices[1]), float(prices[3]),
                            iso(datetime.fromtimestamp(float(ev["S"]), tz=timezone.utc)) if ev.get("S") else None,
                            league, "decimal", prices[1], prices[3],
                            extra={"id1": ev.get("O1I"), "id2": ev.get("O2I"),
                                   "stage": (ev.get("MIO") or {}).get("TSt")}))
        written += 1
    record("melbet", meta, cs2_rows=len(rows), quotes=written)
    keep_raw("melbet", data if data is not None else {"error": meta.get("error")})


def _num(mk, *keys):
    for k in keys:
        v = mk.get(k)
        if v not in (None, ""):
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            return f / 100.0 if not str(k).endswith("_dollars") else f
    return None


def collect_kalshi():
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    written = 0
    for ev in (data or {}).get("events") or [] if isinstance(data, dict) else []:
        for mk in ev.get("markets") or []:
            bid, ask = _num(mk, "yes_bid_dollars", "yes_bid"), _num(mk, "yes_ask_dollars", "yes_ask")
            if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid:
                continue
            mid = (bid + ask) / 2.0
            if not 0.02 <= mid <= 0.98:
                continue
            title = str(ev.get("title") or mk.get("title") or "")
            if PROP_RE.search(title):
                continue
            QUOTES.append(quote("kalshi", "Kalshi (regulated exchange)",
                                "https://kalshi.com/markets/kxcs2game",
                                KALSHI, mk.get("ticker"), title, f"{title} (no)",
                                1.0 / mid, 1.0 / (1.0 - mid),
                                mk.get("open_time") or mk.get("expected_expiration_time"),
                                "KXCS2GAME", "exchange midpoint", round(bid, 4), round(ask, 4),
                                extra={"ticker": mk.get("ticker"), "title": title,
                                       "volume": mk.get("volume"),
                                       "note": "exchange midpoint, not an executable bookmaker price"}))
            written += 1
    record("kalshi", meta, quotes=written)
    keep_raw("kalshi", data if data is not None else {"error": meta.get("error")})


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    started = iso(now_utc())
    fixtures, week = collect_hotspawn()
    collect_pinnacle()
    collect_bovada()
    collect_melbet()
    collect_kalshi()
    for name, blob in RAW_FILES.items():
        (RAW / f"{name}.json").write_bytes(blob)
    (OUT / "quotes.json").write_text(json.dumps(
        {"collected_at_utc": started, "collected_to_utc": iso(now_utc()),
         "quote_count": len(QUOTES), "quotes": QUOTES}, indent=1), encoding="utf-8")
    (OUT / "access.json").write_text(json.dumps(
        {"collection_started_utc": started, "collection_ended_utc": iso(now_utc()),
         "sources": ACCESS, "week": week,
         "fixture_count": len(fixtures),
         "raw_files": {k: len(v) for k, v in RAW_FILES.items()}}, indent=1), encoding="utf-8")
    print(json.dumps({"started": started, "fixtures": len(fixtures), "quotes": len(QUOTES),
                      "sources": {k: v.get("http_status") for k, v in ACCESS.items()}}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
