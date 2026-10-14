#!/usr/bin/env python3
"""EVERY-MATCH collector (session c64a5e19). Runs on a GitHub-hosted runner (general internet).

Writes ``data/c64a5e19/snapshot.json`` in the same schema as the proven f7279a54 snapshot:
HotSpawn CS2 fixture inventory, every external two-way match-winner price found (including
Kalshi thin books, retained as *fallback-only* evidence in ``rejected_quotes``), the official
Valve VRS ratings, and a per-source access log. HotSpawn is fixture discovery ONLY; its crowd
picked % is never copied. Additional probes (Liquipedia Elisa page, HLTV) record reachability
for the fallback identity evidence used only on matches with no featured line.
"""
from __future__ import annotations
import base64, json, re, ssl, sys, time, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "c64a5e19"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
MELBET = "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&status=open&with_nested_markets=true&limit=200")
POLY = "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=counter-strike"
HLTV = "https://www.hltv.org/matches"
LIQUIPEDIA_ELISA = "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol", re.I)
LOG: dict = {}

def fetch(url, headers=None, timeout=45):
    h = {"User-Agent": UA, "Accept": "*/*"}; h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None, "at_utc": core.to_iso(core.now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read(); meta["status"] = r.status; meta["age_header"] = r.headers.get("Age")
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    return body, meta

def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    try: return json.loads(body.decode("utf-8", "replace")) if body else None, meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"; return None, meta

def collect_hotspawn():
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
            if not fx: continue
            cur = fixtures.setdefault(fx["fixture_id"], {**fx, "seen_in": []})
            # Keep the lobby entry authoritative; API-only entries are inventory research.
            cur["seen_in"].append(origin)
    from datetime import timedelta
    cutoff = core.to_iso(core.now_utc() - timedelta(days=4))
    status_counts: dict[str, int] = {}; kept = {}
    for fid, fx in fixtures.items():
        status_counts[str(fx.get("status"))] = status_counts.get(str(fx.get("status")), 0) + 1
        if ("lobby_page" in fx["seen_in"] or fx.get("status") in ("scheduled", "started") or fx["start_utc"] >= cutoff):
            kept[fid] = fx
    LOG["hotspawn_api"]["cs2_status_counts_all_rows"] = status_counts
    LOG["hotspawn_api"]["cs2_rows_kept"] = len(kept)
    return {"fixtures": sorted(kept.values(), key=lambda r: (r["start_utc"], r["fixture_id"])), "permalinks": state.get("permalinks") or {}, "week": state.get("week")}

def q(source_key, source_name, public_url, api_url, event_id, a, b, dec_a, dec_b, start, league, raw_format, raw_a, raw_b, live=False):
    nv = core.no_vig(dec_a, dec_b)
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url, "api_url": api_url, "event_id": str(event_id), "team_a": a, "team_b": b, "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4), "raw_format": raw_format, "raw_a": raw_a, "raw_b": raw_b, "prob_a": nv["prob_a"] if nv else None, "overround": nv["overround"] if nv else None, "start_utc": core.to_iso(start), "league": league, "live": bool(live), "retrieved_utc": core.to_iso(core.now_utc())}

def collect_pinnacle(quotes):
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS); LOG["pinnacle"] = meta
    if not isinstance(data, list): return
    cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup" and len(m.get("participants") or []) == 2 and not m.get("parentId") and re.match(r"^(CS2|Counter-Strike)", str((m.get("league") or {}).get("name") or ""), re.I)]
    LOG["pinnacle"]["cs2_matchups"] = len(cs); written = 0
    for m in cs:
        names = [str(p.get("name") or "") for p in m["participants"]]
        if any(PROP_RE.search(n) for n in names): continue
        murl = f"{PIN}/matchups/{m['id']}/markets/related/straight"
        markets, _ = fetch_json(murl, PIN_HEADERS); time.sleep(0.1)
        if not isinstance(markets, list): continue
        for mk in markets:
            if (mk.get("type") != "moneyline" or mk.get("period") != 0 or mk.get("isAlternate") or mk.get("matchupId") != m["id"] or mk.get("status") != "open"): continue
            by = {p.get("designation"): p.get("price") for p in mk.get("prices") or []}
            al = {p.get("alignment"): p.get("name") for p in m["participants"]}
            if None in (by.get("home"), by.get("away"), al.get("home"), al.get("away")): continue
            da, db = core.american_to_decimal(by["home"]), core.american_to_decimal(by["away"])
            if da and db:
                quotes.append(q("pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub", murl, m["id"], al["home"], al["away"], da, db, core.parse_any(m.get("startTime")), (m.get("league") or {}).get("name"), "american", by["home"], by["away"], live=m.get("isLive") or mk.get("isLive"))); written += 1
            break
    LOG["pinnacle"]["quotes"] = written

def collect_bovada(quotes):
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"}); LOG["bovada"] = meta; written = 0
    for group in data if isinstance(data, list) else []:
        league = ((group.get("path") or [{}])[0]).get("description")
        for ev in group.get("events") or []:
            if ev.get("status") != "O" or ev.get("live"): continue
            comps = ev.get("competitors") or []
            if len(comps) != 2 or any(PROP_RE.search(str(c.get("name"))) for c in comps): continue
            home = next((c for c in comps if c.get("home")), comps[0]); away = next((c for c in comps if c is not home), comps[1])
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if (str(mk.get("description", "")).strip().casefold() != "moneyline" or not (mk.get("period") or {}).get("main")): continue
                    if mk.get("status") != "O": continue
                    outs = {str(o.get("competitorId")): o for o in mk.get("outcomes") or [] if o.get("status") == "O"}
                    oh, oa = outs.get(str(home.get("id"))), outs.get(str(away.get("id")))
                    if not oh or not oa: continue
                    dh, da = (oh.get("price") or {}).get("decimal"), (oa.get("price") or {}).get("decimal")
                    if not dh or not da: continue
                    quotes.append(q("bovada", "Bovada", "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"), BOVADA, ev.get("id"), home.get("name"), away.get("name"), float(dh), float(da), core.parse_any(ev.get("startTime")), league, "decimal", dh, da, live=ev.get("live"))); written += 1; break
    LOG["bovada"]["quotes"] = written

def collect_melbet(quotes):
    data, meta = fetch_json(MELBET, {"Accept": "application/json"}); LOG["melbet"] = meta
    rows = (data or {}).get("Value") if isinstance(data, dict) else None; written = 0
    for ev in rows if isinstance(rows, list) else []:
        league = str(ev.get("L") or ev.get("LE") or "")
        if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I): continue
        a, b = ev.get("O1E") or ev.get("O1"), ev.get("O2E") or ev.get("O2")
        if not a or not b or PROP_RE.search(f"{a} {b}"): continue
        prices = {o.get("T"): o.get("C") for o in ev.get("E") or [] if o.get("G") == 1 and "P" not in o}
        if not prices.get(1) or not prices.get(3): continue
        quotes.append(q("melbet", "Melbet", "https://melbet.com/en/line/esports", MELBET, ev.get("I"), a, b, float(prices[1]), float(prices[3]), core.parse_any(ev.get("S")), league, "decimal", prices[1], prices[3])); written += 1
    LOG["melbet"]["quotes"] = written

def _kalshi_mid(mk):
    def num(*keys):
        for k in keys:
            v = mk.get(k)
            if v not in (None, ""):
                try: f = float(v)
                except (TypeError, ValueError): continue
                return f / 100.0 if not k.endswith("_dollars") else f
        return None
    bid, ask = num("yes_bid_dollars", "yes_bid"), num("yes_ask_dollars", "yes_ask")
    if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid: return None, None
    return (bid + ask) / 2.0, ask - bid

KALSHI_TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")
def kalshi_start(event_ticker):
    # No officially verified timezone-qualified kickoff in this event ticker.
    return None

def collect_kalshi(quotes, rejected):
    data, meta = fetch_json(KALSHI, {"Accept": "application/json"}); LOG["kalshi"] = meta
    events = (data or {}).get("events") if isinstance(data, dict) else None
    LOG["kalshi"]["events"] = len(events) if isinstance(events, list) else None; written = 0
    for ev in events if isinstance(events, list) else []:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2: continue
        names = [m.get("yes_sub_title") or "" for m in mks]; mids = [_kalshi_mid(m) for m in mks]; tick = ev.get("event_ticker")
        rec = {"source_key": "kalshi", "event_id": tick, "team_a": names[0], "team_b": names[1], "public_url": f"https://kalshi.com/markets/kxcs2game/{str(tick).lower()}"}
        if any(m[0] is None for m in mids) or any(m[1] > core.KALSHI_MAX_SPREAD for m in mids):
            rejected.append({**rec, "reason": "thin or one-sided order book (bid/ask missing or spread > 10c)", "books": [{k: m.get(k) for k in ("ticker", "yes_bid_dollars", "yes_ask_dollars", "yes_bid", "yes_ask")} for m in mks]}); continue
        pa = mids[0][0] / (mids[0][0] + mids[1][0]); dec_a, dec_b = 1 / mids[0][0], 1 / mids[1][0]
        quotes.append({**q("kalshi", "Kalshi (exchange)", rec["public_url"], KALSHI, tick, names[0], names[1], dec_a, dec_b, kalshi_start(tick), ev.get("title"), "yes mid ($)", round(mids[0][0], 4), round(mids[1][0], 4)), "prob_a": pa, "overround": mids[0][0] + mids[1][0] - 1.0, "start_is_approx": True}); written += 1
    LOG["kalshi"]["quotes"] = written

def probe(name, url, headers=None):
    body, meta = fetch(url, headers); meta["looks_like_challenge"] = bool(re.search(rb"cf-chl|challenge-platform|Just a moment", body[:20000])); LOG[name] = meta

def gh_headers():
    import os; h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"): h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return h

DETAILS_DATE = re.compile(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)
def latest_match_date(details_md):
    dates = DETAILS_DATE.findall(details_md or ""); return max(dates) if dates else None

def collect_vrs(fixture_names):
    tree, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1", gh_headers()); LOG["valve_vrs_tree"] = meta
    newest = None
    for node in (tree or {}).get("tree", []) if isinstance(tree, dict) else []:
        m = re.match(r"^live/(\d{4})/standings_global_(\d{4}_\d{2}_\d{2})\.md$", str(node.get("path")))
        if m and (newest is None or m.group(2) > newest[1]): newest = (m.group(1), m.group(2), node["path"])
    if not newest: return {}
    api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{newest[2]}"
    blob, meta2 = fetch_json(api_url, gh_headers()); LOG["valve_vrs_file"] = meta2
    if not isinstance(blob, dict) or not blob.get("content"): return {}
    text = base64.b64decode(blob["content"]).decode("utf-8", "replace"); base_dir = newest[2].rsplit("/", 1)[0]; teams = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)", text, re.M):
        teams.append({"standing": int(m.group(1)), "points": int(m.group(2)), "team": m.group(3).strip(), "roster": m.group(4).strip(), "details_path": f"{base_dir}/{m.group(5).strip()}"})
    cache_path = OUT / "vrs_details_cache.json"
    try: cache = json.loads(cache_path.read_text())
    except (OSError, ValueError): cache = {}
    if cache.get("snapshot") != newest[1]: cache = {"snapshot": newest[1], "latest_match": {}}
    keys: dict[str, list] = {}
    for t in teams: keys.setdefault(core.canon(t["team"])[0], []).append(t)
    wanted = {core.canon(n)[0] for n in fixture_names}; fetched = 0
    for key, rows in keys.items():
        if len(rows) < 2 or key not in wanted: continue
        for t in rows:
            path = t["details_path"]
            if path not in cache["latest_match"]:
                from urllib.parse import quote
                durl = f"https://api.github.com/repos/{VRS_REPO}/contents/{quote(path)}"
                dblob, _ = fetch_json(durl, gh_headers()); fetched += 1
                md = (base64.b64decode(dblob["content"]).decode("utf-8", "replace") if isinstance(dblob, dict) and dblob.get("content") else "")
                cache["latest_match"][path] = latest_match_date(md)
            t["latest_match_date"] = cache["latest_match"][path]
    cache_path.parent.mkdir(parents=True, exist_ok=True); cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    LOG["valve_vrs_file"]["details_files_fetched"] = fetched
    return {"snapshot": newest[1], "path": newest[2], "api_url": api_url, "page_url": f"https://github.com/{VRS_REPO}/blob/main/{newest[2]}", "teams": teams}

def main():
    OUT.mkdir(parents=True, exist_ok=True); started = core.to_iso(core.now_utc()); hs = collect_hotspawn()
    quotes: list = []; rejected: list = []
    for fn in (collect_pinnacle, collect_bovada, collect_melbet):
        try: fn(quotes)
        except Exception as exc: LOG.setdefault(fn.__name__, {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    try: collect_kalshi(quotes, rejected)
    except Exception as exc: LOG.setdefault("kalshi", {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
    probe("polymarket_probe", POLY, {"Accept": "application/json"}); probe("hltv_probe", HLTV, {"Accept": "text/html"}); probe("liquipedia_elisa_probe", LIQUIPEDIA_ELISA, {"Accept": "text/html"})
    names = {n for f in hs["fixtures"] for n in (f["team_a"], f["team_b"])}; vrs = collect_vrs(names)
    snap = {"session": "c64a5e19", "collected_from_utc": started, "collected_to_utc": core.to_iso(core.now_utc()), "hotspawn": hs, "quotes": quotes, "rejected_quotes": rejected, "vrs": vrs, "access_log": LOG}
    if not any("lobby_page" in f.get("seen_in", []) for f in hs["fixtures"]):
        prev = OUT / "snapshot.json"
        if prev.exists():
            old = json.loads(prev.read_text()); snap["hotspawn"] = old.get("hotspawn", hs); snap["hotspawn_fallback_from"] = old.get("hotspawn_fallback_from") or (old.get("access_log", {}).get("hotspawn_lobby_page", {}).get("at_utc")) or old.get("collected_to_utc")
            old_meta = old.get("access_log", {}).get("hotspawn_lobby_page", {})
            snap["access_log"]["hotspawn_lobby_page"]["age_header"] = old_meta.get("age_header")
    (OUT / "snapshot.json").write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
    print("fixtures", len(snap["hotspawn"]["fixtures"]), "quotes", len(quotes), "rejected", len(rejected), "vrs teams", len(vrs.get("teams", [])))
    return 0

if __name__ == "__main__": sys.exit(main())
