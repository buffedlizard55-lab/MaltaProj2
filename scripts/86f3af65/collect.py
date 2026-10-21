#!/usr/bin/env python3
"""Capture layer for session 86f3af65.

Two modes, one output schema (``data/86f3af65/capture.json``):

``--live``            Reads the sources over the network. This is what the scheduled GitHub
                      Actions workflow runs (runners have general internet access).
``--from-canonical``  Re-reads the repository's own pinned capture (``data/f7279a54/snapshot.json``
                      plus its ``source_payloads.json`` and ``access_log``) and converts it into
                      this session's schema, keeping every original ``retrieved_utc`` and payload
                      SHA-256. Used when there is no network, and used for this session's own
                      initial build so that the published numbers are reproducible from committed
                      evidence rather than from an unverifiable claim of having fetched a site.

Reverse-engineered HotSpawn lobby (the part the user asked for):

  * page:  https://play.hotspawn.com/lobby  - server-rendered Angular transfer state in
           ``<script id="ng-state">``; the fixture array is embedded there and is the same payload
           the page itself requests from ``/api/v1/fixtures``.
  * API:   https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures - the undocumented
           public endpoint the lobby calls; returns *all* sports/fixtures (~12k rows) with
           ``sport_alias == 'cs2'`` selecting Counter-Strike 2. Each row carries the fixture id,
           competition, tier, stage, best-of, offered points, status, epoch-millisecond start and
           lock times and both participant names.
  * the response is cached upstream (the ``Age`` header is recorded), so the page and the API are
    both read and merged; anything only in one of them is marked with its origin.

HotSpawn is used for fixture discovery, kickoff and contest context only. No HotSpawn crowd
"picked %" field is read by any function in this session.
"""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "86f3af65"
VALVE_DIR = OUT / "valve"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
# Public key the pinnacle.com web client uses for its logged-out (guest) odds view.
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
BOVADA = ("https://www.bovada.lv/services/sports/event/v2/events/A/description/"
          "esports/counter-strike-2")
MELBET = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en"
          "&mode=4&country=1")
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
POLY = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=counter-strike"
HLTV = "https://www.hltv.org/matches"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol", re.I)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder  # noqa: E402


# ------------------------------------------------------------------------------- transport
def fetch(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None,
            "at_utc": ladder.to_iso(ladder.now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            body = r.read()
            meta["status"] = r.status
            meta["age_header"] = r.headers.get("Age")
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a failure is evidence, not a crash
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
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


def parse_ms(value):
    try:
        ms = int(str(value))
    except (TypeError, ValueError):
        return None
    return None if ms <= 0 else ladder.datetime.fromtimestamp(
        ms / 1000, tz=ladder.timezone.utc)


def parse_any(value):
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return ladder.datetime.fromtimestamp(value / 1000, tz=ladder.timezone.utc)
    if isinstance(value, (int, float)) and value > 0:
        return ladder.datetime.fromtimestamp(value, tz=ladder.timezone.utc)
    return ladder.parse_iso(value)


def gh_headers() -> dict:
    import os
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return h


# --------------------------------------------------------------------------------- HotSpawn
LOBBY_STATE_RE = re.compile(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)


def lobby_state(page_html: str) -> dict:
    """Pull the Angular transfer state out of the public lobby page."""
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
        elif "permalinks" in url and isinstance(body, dict):
            links = body.get("permalinks")
            if isinstance(links, dict):
                out["permalinks"] = {str(k): str(v) for k, v in links.items()}
        elif "week-prizes" in url and isinstance(body, dict):
            out["week"] = {k: body.get(k) for k in ("weekId", "sportAlias", "status",
                                                    "weekStartUtc", "weekEndUtc", "cutoffUtc")}
    return out


def fixture_from_hotspawn(f: dict) -> dict | None:
    if not isinstance(f, dict) or str(f.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(f.get("scheduled_start_time")), parse_ms(f.get("lock_time"))
    a, b = f.get("participants0_name"), f.get("participants1_name")
    if not f.get("id") or not a or not b or start is None:
        return None
    return {
        "fixture_id": str(f["id"]),
        "competition": f.get("competition_name"),
        "tier": (str(f.get("tier") or "").upper() or None),
        "stage": f.get("stage"),
        "best_of": f.get("best_of"),
        "status": f.get("status"),
        "points": f.get("offered_points"),
        "start_utc": ladder.to_iso(start),
        "lock_utc": ladder.to_iso(lock),
        "team_a": str(a).strip(),
        "team_b": str(b).strip(),
        "winner": result_winner(f),
    }


def result_winner(f: dict) -> str | None:
    if str(f.get("status") or "") != "ended":
        return None
    try:
        s0, s1 = int(f.get("participants0_score")), int(f.get("participants1_score"))
    except (TypeError, ValueError):
        return None
    return None if s0 == s1 else ("a" if s0 > s1 else "b")


def permalink(state: dict, fixture_id: str) -> str:
    url = (state.get("permalinks") or {}).get(str(fixture_id))
    if url and re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(url)):
        return str(url)
    return LOBBY_PAGE


def collect_live_hotspawn(access: dict) -> dict:
    page, meta = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=90)
    access["hotspawn_lobby_page"] = meta
    state = lobby_state(page.decode("utf-8", "replace")) if page else {}
    meta["fixtures_in_transfer_state"] = len(state.get("fixtures") or [])
    api_rows, meta2 = fetch_json(HS_API, {"Accept": "application/json",
                                          "Referer": LOBBY_PAGE}, 120)
    access["hotspawn_api"] = meta2
    api_rows = api_rows if isinstance(api_rows, list) else []
    meta2["rows"] = len(api_rows)
    merged: dict[str, dict] = {}
    for origin, rows in (("lobby_page", state.get("fixtures") or []), ("api", api_rows)):
        for raw in rows:
            fx = fixture_from_hotspawn(raw)
            if not fx:
                continue
            cur = merged.setdefault(fx["fixture_id"], {**fx, "seen_in": []})
            if "api" in origin:
                cur.update(fx)
            cur["seen_in"].append(origin)
    counts: dict[str, int] = {}
    for fx in merged.values():
        counts[str(fx.get("status"))] = counts.get(str(fx.get("status")), 0) + 1
    meta2["cs2_status_counts_all_rows"] = counts
    for fx in merged.values():
        fx["hotspawn_url"] = permalink(state, fx["fixture_id"])
    # The API serves the whole season (10k+ rows). Committing all of it every four hours would
    # bloat the repository for no reader, so keep the open window plus a two-day tail of results
    # and carry the counters for everything else.
    cutoff = ladder.to_iso(ladder.now_utc() - timedelta(hours=48))
    keep = [fx for fx in merged.values()
            if str(fx.get("status")) in ("scheduled", "started")
            or (fx.get("start_utc") or "") >= cutoff]
    meta2["fixtures_kept"] = len(keep)
    meta2["fixtures_dropped_ended_before_cutoff"] = len(merged) - len(keep)
    return {"fixtures": sorted(keep, key=lambda r: (r["start_utc"], r["fixture_id"])),
            "week": state.get("week"),
            "lobby_url": LOBBY_PAGE, "api_url": HS_API}


# ----------------------------------------------------------------------------- bookmakers
def make_quote(source_key, source_name, public_url, api_url, event_id, a, b, dec_a, dec_b,
               start, league, raw_format, raw_a, raw_b, live=False):
    nv = ladder.no_vig(dec_a, dec_b)
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url,
            "api_url": api_url, "event_id": str(event_id), "team_a": a, "team_b": b,
            "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
            "raw_format": raw_format, "raw_a": raw_a, "raw_b": raw_b,
            "prob_a": nv["prob_a"] if nv else None,
            "overround": nv["overround"] if nv else None,
            "start_utc": ladder.to_iso(start), "league": league, "live": bool(live),
            "retrieved_utc": ladder.to_iso(ladder.now_utc())}


def collect_pinnacle(quotes: list, access: dict) -> None:
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    access["pinnacle"] = meta
    if not isinstance(data, list):
        return
    cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
          and len(m.get("participants") or []) == 2 and not m.get("parentId")
          and re.match(r"^(CS2|Counter-Strike)",
                       str((m.get("league") or {}).get("name") or ""), re.I)]
    meta["cs2_matchups"] = len(cs)
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
            if (mk.get("type") != "moneyline" or mk.get("period") != 0
                    or mk.get("isAlternate") or mk.get("matchupId") != m["id"]
                    or mk.get("status") != "open"):
                continue
            by = {p.get("designation"): p.get("price") for p in mk.get("prices") or []}
            al = {p.get("alignment"): p.get("name") for p in m["participants"]}
            if None in (by.get("home"), by.get("away"), al.get("home"), al.get("away")):
                continue
            da = ladder.american_to_decimal(by["home"])
            db = ladder.american_to_decimal(by["away"])
            if da and db:
                quotes.append(make_quote(
                    "pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub", murl,
                    m["id"], al["home"], al["away"], da, db, parse_any(m.get("startTime")),
                    (m.get("league") or {}).get("name"), "american", by["home"], by["away"],
                    live=m.get("isLive") or mk.get("isLive")))
                written += 1
            break
    meta["quotes"] = written


def collect_bovada(quotes: list, access: dict) -> None:
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    access["bovada"] = meta
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
                    quotes.append(make_quote(
                        "bovada", "Bovada",
                        "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                        BOVADA, ev.get("id"), home.get("name"), away.get("name"), float(dh),
                        float(da), parse_any(ev.get("startTime")), league, "decimal", dh, da,
                        live=ev.get("live")))
                    written += 1
                    break
    meta["quotes"] = written


def collect_melbet(quotes: list, access: dict) -> None:
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    access["melbet"] = meta
    rows = (data or {}).get("Value") if isinstance(data, dict) else None
    written = 0
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
        quotes.append(make_quote("melbet", "Melbet", "https://melbet.com/en/line/esports",
                                 MELBET, ev.get("I"), a, b, float(prices[1]),
                                 float(prices[3]), parse_any(ev.get("S")), league, "decimal",
                                 prices[1], prices[3]))
        written += 1
    meta["quotes"] = written


def kalshi_mid(mk: dict):
    def num(*keys):
        for k in keys:
            v = mk.get(k)
            if v in (None, ""):
                continue
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


def collect_kalshi(quotes: list, rejected: list, access: dict) -> None:
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"})
    access["kalshi"] = meta
    events = (data or {}).get("events") if isinstance(data, dict) else None
    meta["events"] = len(events) if isinstance(events, list) else None
    written = 0
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        names = [m.get("yes_sub_title") or "" for m in mks]
        mids = [kalshi_mid(m) for m in mks]
        tick = ev.get("event_ticker")
        url = f"https://kalshi.com/markets/kxcs2game/{str(tick).lower()}"
        if any(m[0] is None for m in mids):
            if any(m[0] is not None for m in mids):
                rejected.append({"source_key": "kalshi", "event_id": tick, "team_a": names[0],
                                 "team_b": names[1], "public_url": url,
                                 "reason": "one-sided order book (no bid or no ask)"})
            continue
        pa = mids[0][0] / (mids[0][0] + mids[1][0])
        quote = make_quote("kalshi", "Kalshi (exchange)", url, KALSHI, tick, names[0], names[1],
                           1 / mids[0][0], 1 / mids[1][0], None, ev.get("title"), "yes mid ($)",
                           round(mids[0][0], 4), round(mids[1][0], 4))
        quote.update({"start_utc": None, "start_is_approx": True,
                      "spread": max(m[1] for m in mids)})
        quotes.append(quote)
        written += 1
    meta["quotes"] = written


def probe_observation(name: str, url: str, access: dict, headers=None) -> None:
    body, meta = fetch(url, headers, timeout=45)
    meta["looks_like_challenge"] = bool(
        re.search(rb"cf-chl|challenge-platform|Just a moment", body[:20000]))
    meta["body_bytes_sample"] = body[:200].decode("utf-8", "replace") if body else ""
    access[name] = meta


# ----------------------------------------------------------------------------------- Valve
def latest_standings_paths() -> tuple[str | None, dict]:
    tree, meta = fetch_json(
        f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1", gh_headers())
    newest = {}
    for node in (tree or {}).get("tree", []) if isinstance(tree, dict) else []:
        m = re.match(r"^live/(\d{4})/standings_(global|americas|asia|europe)_(\d{4}_\d{2}_\d{2})\.md$",
                     str(node.get("path")))
        if not m:
            continue
        region, snap = m.group(2), m.group(3)
        if region not in newest or snap > newest[region][0]:
            newest[region] = (snap, node["path"])
    return (max(v[0] for v in newest.values()) if newest else None), {"tree": meta,
                                                                    "paths": newest}


def collect_vrs(names: set[str], access: dict, norm) -> dict:
    snapshot, info = latest_standings_paths()
    access["valve_vrs_tree"] = info["tree"]
    files, rows, details = [], [], {}
    raw_files: dict[str, bytes] = {}
    raw_details: dict[str, bytes] = {}
    if not snapshot:
        return {"snapshot": None, "files": [], "rows": [], "details": {},
                "floor": {"points": 381, "standing": 380}}
    for region in ("global", "americas", "asia", "europe"):
        if region not in info["paths"]:
            continue
        _, path = info["paths"][region]
        blob, meta = fetch_json(
            f"https://api.github.com/repos/{VRS_REPO}/contents/{path}", gh_headers(), timeout=90)
        access[f"valve_vrs_{region}"] = meta
        if not isinstance(blob, dict) or not blob.get("content"):
            continue
        raw = base64.b64decode(blob["content"])
        text = raw.decode("utf-8", "replace")
        files.append({
            "region": region, "snapshot": snapshot, "path": path,
            "page_url": f"https://github.com/{VRS_REPO}/blob/main/{path}",
            "api_url": f"https://api.github.com/repos/{VRS_REPO}/contents/{path}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_sha": blob.get("sha"), "retrieved_utc": meta.get("at_utc"),
        })
        raw_files[path] = raw
        rows.extend(parse_rows(text, region, path.rsplit("/", 1)[0]))
    # Official per-roster details pages, read only for names that appear more than once
    # (that is how this session resolves duplicate organisation names with evidence).
    wanted = {norm(n) for n in names if n}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["region"] == "global":
            groups.setdefault(norm(r["team"]), []).append(r)
    for key, group in groups.items():
        if len(group) < 2 or key not in wanted:
            continue
        for r in group:
            from urllib.parse import quote
            path = r["details_path"]
            if not path:
                continue
            blob, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/contents/"
                                    f"{quote(path)}", gh_headers(), timeout=60)
            if not isinstance(blob, dict) or not blob.get("content"):
                continue
            md_bytes = base64.b64decode(blob["content"])
            md = md_bytes.decode("utf-8", "replace")
            raw_details[path] = md_bytes
            dates = re.findall(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", md, re.M)
            details[path] = {"latest_match_date": max(dates) if dates else None,
                             "counted_matches": len(dates), "payload_sha256":
                                 hashlib.sha256(md_bytes).hexdigest()[:16]}
            r["latest_match_date"] = details[path]["latest_match_date"]
            r["counted_matches"] = details[path]["counted_matches"]
    access["valve_vrs_details"] = {"files_read": len(details)}
    global_rows = [r for r in rows if r["region"] == "global"]
    floor = max(global_rows, key=lambda r: r["standing"]) if global_rows else {"points": 381,
                                                                               "standing": 380}
    return {"snapshot": snapshot, "files": files, "rows": rows, "details": details,
            "floor": {"points": floor["points"], "standing": floor["standing"],
                      "team": floor.get("team")},
            "_raw_files": raw_files, "_raw_details": raw_details}


ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)", re.M)


def parse_rows(text: str, region: str, base_dir: str = "live/2026") -> list[dict]:
    """Parse one standings markdown table.

    The ``details`` link inside Valve's table is written relative to the directory the standings
    file lives in (``live/<year>/``), so it is resolved against ``base_dir`` here once, instead of
    being mistaken for a repository-root path by whoever reads this record later.
    """
    out = []
    for m in ROW_RE.finditer(text or ""):
        roster = m.group(4).strip()
        rel = m.group(5).strip()
        if rel and not rel.startswith("live/"):
            rel = f"{base_dir}/{rel}"
        out.append({"region": region, "standing": int(m.group(1)), "points": int(m.group(2)),
                    "team": m.group(3).strip(), "roster": roster,
                    "players": [p.strip() for p in roster.split(",") if p.strip()],
                    "details_path": rel})
    return out


# ----------------------------------------------------------------------------------- modes
def from_canonical() -> dict:
    """Convert the repository's pinned 2026-10-21T19:24Z capture into this session's schema."""
    snap_path = ROOT / "data" / "f7279a54" / "snapshot.json"
    snap = json.loads(snap_path.read_text())
    access = snap.get("access_log") or {}
    week = (snap.get("hotspawn") or {}).get("week")
    permalinks = (snap.get("hotspawn") or {}).get("permalinks") or {}
    fixtures = []
    for fx in (snap.get("hotspawn") or {}).get("fixtures", []):
        url = permalinks.get(str(fx["fixture_id"])) or f"{LOBBY_PAGE}"
        fixtures.append({**fx, "hotspawn_url": url})
    quotes = []
    for q in snap.get("quotes") or []:
        quotes.append({**q, "spread": None})
    vrs = snap.get("vrs") or {}
    rows = []
    for t in vrs.get("teams") or []:
        rows.append({**t, "region": "global",
                     "players": [p.strip() for p in (t.get("roster") or "").split(",")
                                 if p.strip()]})
    # Pinned regional files add no team that the global file lacks (verified in this session and
    # asserted by tests/test_86f3af65.py), but they are shipped so the claim can be re-checked.
    regional = []
    for path in sorted(VALVE_DIR.glob("standings_*.md")):
        m = re.search(r"standings_(americas|asia|europe)_(\d{4}_\d{2}_\d{2})\.md$", path.name)
        if not m:
            continue
        text = path.read_text(encoding="utf-8")
        regional.append({"region": m.group(1), "snapshot": m.group(2),
                         "path": f"live/2026/{path.name}",
                         "page_url": ("https://github.com/ValveSoftware/"
                                      f"counter-strike_regional_standings/blob/main/live/2026/"
                                      f"{path.name}"),
                         "api_url": ("https://api.github.com/repos/ValveSoftware/"
                                     f"counter-strike_regional_standings/contents/live/2026/"
                                     f"{path.name}"),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "retrieved_utc": None})
        rows.extend(parse_rows(text, m.group(1)))
    detail_meta = {}
    for md in sorted((VALVE_DIR / "details").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        dates = re.findall(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", text, re.M)
        base = f"live/2026/details/{md.name}"
        detail_meta[base] = {"latest_match_date": max(dates) if dates else None,
                             "counted_matches": len(dates),
                             "sha256": hashlib.sha256(md.read_bytes()).hexdigest()}
    for r in rows:
        base = (r.get("details_path") or "").rsplit("/", 1)[-1]
        if base in detail_meta:
            r["latest_match_date"] = detail_meta[base]["latest_match_date"]
            r["counted_matches"] = detail_meta[base]["counted_matches"]
    gpath = vrs.get("path") or "live/2026/standings_global_2026_10_05.md"
    files = [{"region": "global", "snapshot": vrs.get("snapshot"), "path": gpath,
              "page_url": vrs.get("page_url"),
              "api_url": vrs.get("api_url"),
              "sha256": hashlib.sha256(
                  (VALVE_DIR / Path(gpath).name).read_bytes()).hexdigest(), "retrieved_utc": None}]
    files.extend(regional)
    floor = max([r for r in rows if r["region"] == "global"],
                key=lambda r: r["standing"])
    return {
        "session": "86f3af65",
        "capture_mode": "canonical-import",
        "captured_utc": snap.get("collected_to_utc"),
        "captured_from_utc": snap.get("collected_from_utc"),
        "provenance": {
            "kind": "repository-pinned capture, converted",
            "source_path": "data/f7279a54/snapshot.json",
            "source_session": "f7279a54",
            "source_access_log": access,
            "note": ("This session had no outbound network access to the odds, lobby or HLTV "
                     "sources, so the published board is derived from the repository's own "
                     "19:24Z capture of those exact endpoints (every HTTP status, byte count, "
                     "cache Age and payload SHA-256 is carried here verbatim) plus Valve "
                     "standings files re-read live from api.github.com in this session. The "
                     "scheduled workflow re-runs the same conversion from a fresh live capture."),
        },
        "hotspawn": {"week": week, "fixtures": fixtures, "lobby_url": LOBBY_PAGE,
                     "api_url": HS_API, "access": access.get("hotspawn_lobby_page")},
        "quotes": quotes,
        "rejected_quotes": snap.get("rejected_quotes") or [],
        "vrs": {"snapshot": vrs.get("snapshot"), "files": files, "rows": rows,
                "floor": {"points": floor["points"], "standing": floor["standing"],
                          "team": floor.get("team")},
                "details": detail_meta},
        "access": access,
    }


def live() -> dict:
    access: dict = {}
    import vrs as vrs_mod  # local module; used only for normalisation of team names
    started = ladder.to_iso(ladder.now_utc())
    hs = collect_live_hotspawn(access)
    quotes: list = []
    rejected: list = []
    for fn in (collect_pinnacle, collect_bovada, collect_melbet):
        try:
            fn(quotes, access)
        except Exception as exc:  # noqa: BLE001
            access[fn.__name__] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        collect_kalshi(quotes, rejected, access)
    except Exception as exc:  # noqa: BLE001
        access["kalshi"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    probe_observation("polymarket_probe", POLY, access, {"Accept": "application/json"})
    probe_observation("hltv_probe", HLTV, access, {"Accept": "text/html"})
    names = {n for f in hs["fixtures"] for n in (f["team_a"], f["team_b"])}
    try:
        vrs = collect_vrs(names, access, vrs_mod.norm)
    except Exception as exc:  # noqa: BLE001 - a blocked ranking source must not kill the capture
        access["valve_vrs_error"] = {"error": f"{type(exc).__name__}: {exc}"[:400]}
        vrs = {"snapshot": None, "files": [], "rows": [], "details": {},
               "floor": {"points": 381, "standing": 380}}
    try:
        persist_valve(vrs, access)
    except Exception as exc:  # noqa: BLE001
        access["valve_vrs_persist_error"] = {"error": f"{type(exc).__name__}: {exc}"[:400]}
    return {"session": "86f3af65", "capture_mode": "live",
            "captured_from_utc": started, "captured_utc": ladder.to_iso(ladder.now_utc()),
            "provenance": {"kind": "live capture", "source_access_log": access},
            "hotspawn": hs, "quotes": quotes, "rejected_quotes": rejected, "vrs": vrs,
            "access": access}


def persist_valve(vrs: dict, access: dict) -> None:
    """Pin the standings files and per-roster pages exactly as they were parsed.

    The board and the tests both read these pinned copies, so a live run must leave them in the
    state it actually used. The bytes are the ones collected in memory - nothing is re-fetched
    here, so a second, separate request can never produce a hash that disagrees with the board.
    """
    VALVE_DIR.mkdir(parents=True, exist_ok=True)
    (VALVE_DIR / "details").mkdir(exist_ok=True)
    files, details = {}, {}
    for path, raw in (vrs.get("_raw_files") or {}).items():
        name = Path(path).name
        (VALVE_DIR / name).write_bytes(raw)
        files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    for path, raw in (vrs.get("_raw_details") or {}).items():
        (VALVE_DIR / "details" / Path(path).name).write_bytes(raw)
        details[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    for f in vrs.get("files") or []:
        rec = files.get(Path(f["path"]).name)
        if rec:
            f["sha256"] = rec["sha256"]
    if not files:
        access["valve_vrs_persist"] = {"error": "no standings bytes were available to pin"}
        return
    read = {"note": ("Live re-read of the official Valve standings files from api.github.com "
                     "by scripts/86f3af65/collect.py --live. Hashes are of the exact bytes that "
                     "were parsed into the board."),
            "read_utc": ladder.to_iso(ladder.now_utc()),
            "listing": {"url": f"https://api.github.com/repos/{VRS_REPO}/contents/live",
                        "http_status": (access.get("valve_vrs_tree") or {}).get("status"),
                        "conclusion": f"newest published snapshot {vrs.get('snapshot')}"},
            "files": files,
            "details_read_utc": ladder.to_iso(ladder.now_utc()),
            "details_files": sorted(details)}
    (VALVE_DIR / "live_reads.json").write_text(json.dumps(read, indent=1) + "\n")
    access["valve_vrs_persist"] = {"files": len(files), "details": len(details)}


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mode = "live" if "--live" in argv else "from-canonical"
    capture = live() if mode == "live" else from_canonical()
    if not capture["hotspawn"]["fixtures"]:
        print(json.dumps({"mode": mode, "error": "no HotSpawn CS2 fixtures were read - refusing "
                                                  "to overwrite the committed capture",
                          "access": capture.get("access")}, indent=1))
        return 2
    for key in list((capture.get("vrs") or {}).keys()):
        if key.startswith("_"):
            capture["vrs"].pop(key, None)
    (OUT / "capture.json").write_text(json.dumps(capture, indent=1, ensure_ascii=False) + "\n")
    fx = capture["hotspawn"]["fixtures"]
    opened = ladder.open_fixtures(fx, ladder.now_utc())
    print(json.dumps({"mode": mode, "captured_utc": capture["captured_utc"],
                      "fixtures": len(fx), "open_now": len(opened),
                      "quotes": len(capture["quotes"]),
                      "vrs_rows": len(capture["vrs"]["rows"]),
                      "vrs_snapshot": capture["vrs"]["snapshot"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
