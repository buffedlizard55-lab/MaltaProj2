#!/usr/bin/env python3
"""Collect this session's own source capture (session 6484426f).

Runs on a GitHub-hosted runner, where the public sources are reachable. Every payload is kept
verbatim under ``data/6484426f/sources/`` with its URL, HTTP status, byte count, UTC read time and
raw sha256, so a reviewer can replay any published number against the exact bytes we read.

Sources, in the order the published ladder uses them:

  * HotSpawn lobby page + fixtures API  - fixture inventory, kickoff, points, ownership (never a price)
  * Pinnacle guest odds, Bovada, Melbet - external bookmaker prices (2-way full-match moneylines)
  * Kalshi trade API, series KXCS2GAME  - CFTC-regulated exchange books with the official rules text
  * Valve counter-strike_regional_standings (GitHub) - the official rating source for originated lines
  * HLTV probes                         - reachability only; HLTV facts in this session are dated
                                          manual reads recorded in data/6484426f/research.json

No authenticated API, no access-control bypass, and no price is ever inferred.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "6484426f"
SRC = OUT / "sources"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
MELBET = "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"
KALSHI = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME"
          "&status=open&with_nested_markets=true&limit=200")
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_FILES = ("standings_global", "standings_europe", "standings_americas", "standings_asia")
HLTV_PROBES = ("https://www.hltv.org/matches",
               "https://www.hltv.org/events/8932/matches",
               "https://www.hltv.org/results?event=8932")
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol|\bby \d", re.I)
MAX_BYTES = 2_000_000

LOG: dict = {}
PAYLOADS: dict = {}


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_any(value):
    return shared.core().parse_any(value)


def fetch(url: str, headers: dict | None = None, timeout: int = 45):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                   **(headers or {})})
    started = iso_now()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            meta = {"url": url, "status": response.status, "bytes": len(body),
                    "read_utc": started, "finished_utc": iso_now(),
                    "date_header": response.headers.get("Date"), "error": None,
                    "sha256": hashlib.sha256(body[:MAX_BYTES]).hexdigest()}
            if len(body) > MAX_BYTES:
                meta["error"] = "payload over safety limit"
                return None, meta
            return body, meta
    except urllib.error.HTTPError as exc:
        return None, {"url": url, "status": exc.code, "bytes": None, "read_utc": started,
                      "finished_utc": iso_now(), "error": f"HTTP {exc.code}", "sha256": None}
    except Exception as exc:  # noqa: BLE001
        return None, {"url": url, "status": None, "bytes": None, "read_utc": started,
                      "finished_utc": iso_now(), "error": f"{type(exc).__name__}: {exc}"[:200],
                      "sha256": None}


def fetch_json(url, headers=None, timeout=45):
    body, meta = fetch(url, headers, timeout)
    if body is None:
        return None, meta
    try:
        return json.loads(body.decode("utf-8", "replace")), meta
    except ValueError:
        meta["error"] = (meta.get("error") or "") + " invalid JSON"
        return None, meta


# ------------------------------------------------------------------------------- HotSpawn
def collect_hotspawn() -> dict:
    core = shared.core()
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
                cur.update(fx)
            cur["seen_in"].append(origin)
    cutoff = core.to_iso(core.now_utc() - timedelta(days=4))
    kept = {fid: fx for fid, fx in fixtures.items()
            if ("lobby_page" in fx["seen_in"] or fx.get("status") in ("scheduled", "started")
                or str(fx.get("start_utc") or "") >= cutoff)}
    # Ownership (crowd pick shares) exactly as the lobby publishes them; never a price.
    ownership = {}
    for raw in page_fx:
        fx = core.fixture_from_hotspawn(raw)
        if not fx:
            continue
        ownership[fx["fixture_id"]] = {
            "team_a": fx["team_a"], "team_b": fx["team_b"],
            "picked_percent_a": raw.get("participants0_picked_percent"),
            "picked_percent_b": raw.get("participants1_picked_percent"),
            "total_picks": raw.get("total_picks"),
        }
    return {"fixtures": sorted(kept.values(), key=lambda r: (str(r.get("start_utc")), r["fixture_id"])),
            "permalinks": state.get("permalinks") or {}, "week": state.get("week"),
            "ownership": ownership}


# ------------------------------------------------------------------------------ Pinnacle
def collect_pinnacle(lobby_names: set[str]) -> dict:
    data, meta = fetch_json(f"{PIN}/sports/12/matchups", PIN_HEADERS)
    LOG["pinnacle_matchups"] = meta
    rows_out, markets_out = [], []
    if isinstance(data, list):
        cs = [m for m in data if isinstance(m, dict) and m.get("type") == "matchup"
              and len(m.get("participants") or []) == 2 and not m.get("parentId")
              and re.match(r"^(CS2|Counter-Strike)", str((m.get("league") or {}).get("name") or ""), re.I)]
        LOG["pinnacle_matchups"]["cs2_matchups"] = len(cs)
        for m in cs:
            names = [str(p.get("name") or "") for p in m["participants"]]
            if any(PROP_RE.search(n) for n in names):
                continue
            start = parse_any(m.get("startTime"))
            interesting = any(shared.core().same_team(n, ln)[0] for n in names for ln in lobby_names)
            if not interesting and (start is None or start > shared.core().now_utc() + timedelta(days=6)):
                continue
            murl = f"{PIN}/matchups/{m['id']}/markets/related/straight"
            markets, mmeta = fetch_json(murl, PIN_HEADERS)
            LOG.setdefault("pinnacle_markets", {})[str(m["id"])] = {
                k: mmeta.get(k) for k in ("status", "bytes", "read_utc", "error")}
            time.sleep(0.08)
            if not isinstance(markets, list):
                continue
            markets_out.append({"matchup_id": m["id"], "participants": names, "start_utc":
                                shared.core().to_iso(start), "league": (m.get("league") or {}).get("name"),
                                "n_markets": len(markets),
                                "market_types": sorted({str(mk.get("type")) for mk in markets
                                                        if isinstance(mk, dict)})})
            for mk in markets:
                if (mk.get("type") != "moneyline" or mk.get("period") != 0 or mk.get("isAlternate")
                        or mk.get("matchupId") != m["id"] or mk.get("status") != "open"):
                    continue
                by = {p.get("designation"): p.get("price") for p in mk.get("prices") or []}
                al = {p.get("alignment"): p.get("name") for p in m["participants"]}
                if None in (by.get("home"), by.get("away"), al.get("home"), al.get("away")):
                    continue
                da = shared.core().american_to_decimal(by["home"])
                db = shared.core().american_to_decimal(by["away"])
                if da and db:
                    rows_out.append({"source_key": "pinnacle", "source_name": "Pinnacle",
                                     "public_url": "https://www.pinnacle.com/en/esports/cs2-hub",
                                     "api_url": murl, "event_id": str(m["id"]),
                                     "names_at_source": [al["home"], al["away"]],
                                     "raw_format": "american", "raw_a": by["home"], "raw_b": by["away"],
                                     "decimal_a": da, "decimal_b": db,
                                     "start_utc": shared.core().to_iso(parse_any(m.get("startTime"))),
                                     "league": (m.get("league") or {}).get("name"),
                                     "retrieved_utc": iso_now()})
                break
    return {"quotes": rows_out, "matchups": markets_out}


# -------------------------------------------------------------------------------- Bovada
def collect_bovada() -> dict:
    data, meta = fetch_json(BOVADA, {"Accept": "application/json"})
    LOG["bovada"] = meta
    rows_out = []
    for group in data if isinstance(data, list) else []:
        league = ((group.get("path") or [{}])[0]).get("description")
        for ev in group.get("events") or []:
            comps = ev.get("competitors") or []
            if len(comps) != 2 or any(PROP_RE.search(str(c.get("name"))) for c in comps):
                continue
            home = next((c for c in comps if c.get("home")), comps[0])
            away = next((c for c in comps if c is not home), comps[1])
            for dg in ev.get("displayGroups") or []:
                hit = False
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
                    link = "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports")
                    rows_out.append({"source_key": "bovada", "source_name": "Bovada",
                                     "public_url": link, "api_url": BOVADA, "event_id": str(ev.get("id")),
                                     "names_at_source": [home.get("name"), away.get("name")],
                                     "raw_format": "decimal", "raw_a": dh, "raw_b": da,
                                     "decimal_a": float(dh), "decimal_b": float(da),
                                     "start_utc": shared.core().to_iso(parse_any(ev.get("startTime"))),
                                     "league": league, "retrieved_utc": iso_now()})
                    hit = True
                    break
                if hit:
                    break
    return {"quotes": rows_out}


# ------------------------------------------------------------------------------- Melbet
def collect_melbet() -> dict:
    data, meta = fetch_json(MELBET, {"Accept": "application/json"})
    LOG["melbet"] = meta
    rows = (data or {}).get("Value") if isinstance(data, dict) else None
    parsed, kept_rows = [], []
    for ev in rows if isinstance(rows, list) else []:
        league = str(ev.get("L") or ev.get("LE") or "")
        if not re.search(r"\bCS\s*2\b|Counter-Strike", league, re.I):
            continue
        a = ev.get("O1E") or ev.get("O1")
        b = ev.get("O2E") or ev.get("O2")
        if not a or not b or PROP_RE.search(f"{a} {b}"):
            continue
        prices = {o.get("T"): o.get("C") for o in ev.get("E") or [] if o.get("G") == 1 and "P" not in o}
        if not prices.get(1) or not prices.get(3):
            continue
        kept_rows.append({"event_id": ev.get("I"), "league": league, "names": [a, b],
                          "decimal": [prices[1], prices[3]], "start_utc":
                          shared.core().to_iso(parse_any(ev.get("S")))})
        parsed.append({"source_key": "melbet", "source_name": "Melbet",
                       "public_url": "https://melbet.com/en/line/esports", "api_url": MELBET,
                       "event_id": str(ev.get("I")), "names_at_source": [a, b],
                       "raw_format": "decimal", "raw_a": prices[1], "raw_b": prices[3],
                       "decimal_a": float(prices[1]), "decimal_b": float(prices[3]),
                       "start_utc": shared.core().to_iso(parse_any(ev.get("S"))), "league": league,
                       "retrieved_utc": iso_now()})
    return {"quotes": parsed, "rows": kept_rows}


# ------------------------------------------------------------------------------- Kalshi
KALSHI_RULES_TIME = re.compile(
    r"scheduled for\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)\s*"
    r"(EDT|EST|UTC|GMT)", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def kalshi_kickoff(rules_text: str):
    """Explicit kickoff published in Kalshi's own rules text, converted from its stated zone."""
    m = KALSHI_RULES_TIME.search(rules_text or "")
    if not m:
        return None
    month = MONTHS.get(m.group(1)[:3].title())
    if not month:
        return None
    hour = int(m.group(4)) % 12
    if m.group(6).upper() == "PM":
        hour += 12
    offset = {"EDT": -4, "EST": -5, "UTC": 0, "GMT": 0}[m.group(7).upper()]
    try:
        naive = datetime(int(m.group(3)), month, int(m.group(2)), hour, int(m.group(5)),
                         tzinfo=timezone.utc)
    except ValueError:
        return None
    return naive - timedelta(hours=offset)


def collect_kalshi() -> dict:
    events, cursor, pages = [], "", 0
    while pages < 8:
        url = KALSHI + (f"&cursor={cursor}" if cursor else "")
        data, meta = fetch_json(url, {"Accept": "application/json"})
        LOG.setdefault("kalshi_pages", {})[str(pages)] = {k: meta.get(k) for k in
                                                          ("status", "bytes", "read_utc", "error")}
        if not isinstance(data, dict):
            break
        events.extend(data.get("events") or [])
        cursor = data.get("cursor") or ""
        pages += 1
        if not cursor:
            break
        time.sleep(0.2)
    LOG["kalshi"] = {"events": len(events), "pages": pages, "read_utc": iso_now()}
    markets, rejects = [], []
    for ev in events:
        mks = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(mks) != 2:
            continue
        names = [m.get("yes_sub_title") or m.get("no_sub_title") or "" for m in mks]
        rules = " ".join(str(m.get("rules_primary") or "") for m in mks)
        rec = {"source_key": "kalshi", "source_name": "Kalshi (exchange)",
               "public_url": f"https://kalshi.com/markets/kxcs2game/{str(ev.get('event_ticker')).lower()}",
               "api_url": KALSHI, "event_id": ev.get("event_ticker"),
               "names_at_source": names, "rules_primary": rules[:600],
               "kickoff_utc": shared.core().to_iso(kalshi_kickoff(rules)), "retrieved_utc": iso_now()}
        books = {}
        for m in mks:
            bid, ask = m.get("yes_bid_dollars"), m.get("yes_ask_dollars")
            try:
                bid, ask = float(bid), float(ask)
            except (TypeError, ValueError):
                bid = ask = None
            books[m.get("ticker")] = {"yes_bid": bid, "yes_ask": ask, "spread":
                                      (ask - bid) if (bid is not None and ask is not None) else None}
            if bid is not None and ask is not None and bid > 0 and ask < 1 and ask >= bid:
                rec.setdefault("yes_mid", []).append(round((bid + ask) / 2.0, 4))
        rec["books"] = books
        if len(rec.get("yes_mid") or []) == 2 and not any(
                b["spread"] is None or b["spread"] > 0.10 for b in books.values()):
            markets.append(rec)
        else:
            rejects.append({**rec, "reject_reason": "thin or one-sided order book (spread > 10c "
                                                    "or a missing side)"})
    return {"markets": markets, "rejected": rejects, "events": events}


# -------------------------------------------------------------------------- Valve (VRS)
def gh_headers() -> dict:
    import os
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return h


def collect_valve() -> dict:
    files, commit = {}, None
    head, head_meta = fetch_json(
        f"https://api.github.com/repos/{VRS_REPO}/commits?per_page=1", gh_headers())
    LOG["valve_commits"] = {k: head_meta.get(k) for k in ("status", "bytes", "read_utc", "error")}
    if isinstance(head, list) and head:
        commit = {"sha": head[0].get("sha"), "date": (head[0].get("commit") or {}).get("committer", {}).get("date")}
    listing, listing_meta = fetch_json(
        f"https://api.github.com/repos/{VRS_REPO}/contents/live/2026", gh_headers())
    LOG["valve_listing"] = {k: listing_meta.get(k) for k in ("status", "bytes", "read_utc", "error")}
    latest: dict[str, str] = {}
    for entry in listing if isinstance(listing, list) else []:
        name = str(entry.get("name") or "")
        for stem in VRS_FILES:
            if name.startswith(stem) and name.endswith(".md"):
                if name > latest.get(stem, ""):
                    latest[stem] = name
    for stem, name in latest.items():
        url = f"https://api.github.com/repos/{VRS_REPO}/contents/live/2026/{name}"
        payload, meta = fetch_json(url, gh_headers())
        LOG.setdefault("valve_files", {})[stem] = {
            "file": name, **{k: meta.get(k) for k in ("status", "bytes", "read_utc", "error")}}
        if isinstance(payload, dict) and payload.get("content"):
            import base64
            try:
                text = base64.b64decode(payload["content"]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            files[stem] = {"file": name,
                           "raw_url": f"https://github.com/{VRS_REPO}/blob/main/live/2026/{name}",
                           "api_url": url, "text": text, "sha256":
                           hashlib.sha256(text.encode()).hexdigest()}
    return {"commit": commit, "files": files}


# --------------------------------------------------------------------------------- probes
def probe_hltv() -> dict:
    out = {}
    for url in HLTV_PROBES:
        body, meta = fetch(url, {"Accept": "text/html"}, timeout=30)
        challenge = bool(body and re.search(rb"cf-chl|challenge-platform|Just a moment", body[:20000]))
        out[url] = {"status": meta.get("status"), "bytes": meta.get("bytes"),
                    "read_utc": meta.get("read_utc"), "looks_like_challenge": challenge,
                    "error": meta.get("error")}
        time.sleep(0.2)
    LOG["hltv_probes"] = out
    return out


# ----------------------------------------------------------------------------------- main
def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    started = iso_now()
    hs = collect_hotspawn()
    lobby_names = {n for f in hs["fixtures"] for n in (f.get("team_a"), f.get("team_b")) if n}

    def guard(fn, *args, default):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001
            LOG.setdefault(fn.__name__, {})["crash"] = f"{type(exc).__name__}: {exc}"[:300]
            return default

    pinnacle = guard(collect_pinnacle, lobby_names, default={"quotes": [], "matchups": []})
    bovada = guard(collect_bovada, default={"quotes": []})
    melbet = guard(collect_melbet, default={"quotes": [], "rows": []})
    kalshi = guard(collect_kalshi, default={"markets": [], "rejected": [], "events": []})
    valve = guard(collect_valve, default={"commit": None, "files": {}})
    hltv = guard(probe_hltv, default={})

    capture = {"session": "6484426f", "started_utc": started, "finished_utc": iso_now(),
               "hotspawn": hs, "pinnacle": pinnacle, "bovada": bovada, "melbet": melbet,
               "kalshi": kalshi, "valve": valve, "hltv_probe": hltv}
    digest = {"session": "6484426f", "started_utc": started, "finished_utc": capture["finished_utc"],
              "hotspawn_fixtures": len(hs["fixtures"]),
              "hotspawn_lobby_rows": sum(1 for f in hs["fixtures"]
                                         if "lobby_page" in f.get("seen_in", [])),
              "ownership_rows": len(hs.get("ownership") or {}),
              "quotes": {"pinnacle": pinnacle["quotes"], "bovada": bovada["quotes"],
                         "melbet": melbet["quotes"], "kalshi": kalshi.get("markets") or []},
              "kalshi_rejected": kalshi.get("rejected") or [],
              "valve": {"commit": (valve.get("commit") or {}).get("sha") if isinstance(valve.get("commit"), dict)
                        else valve.get("commit"), "files": sorted(valve.get("files") or {})},
              "http": {k: {"status": v.get("status"), "bytes": v.get("bytes"), "error": v.get("error"),
                           "read_utc": v.get("read_utc")} for k, v in LOG.items()}}
    (SRC / "capture_digest.json").write_text(json.dumps(digest, indent=1, ensure_ascii=False) + "\n")
    (SRC / "capture.json").write_text(json.dumps(capture, indent=1, ensure_ascii=False) + "\n")
    (SRC / "access_log.json").write_text(json.dumps({"session": "6484426f", "log": LOG},
                                                    indent=1, ensure_ascii=False) + "\n")
    counts = {"lobby_fixtures": len(hs["fixtures"]), "pinnacle_quotes": len(pinnacle["quotes"]),
              "bovada_quotes": len(bovada["quotes"]), "melbet_quotes": len(melbet["quotes"]),
              "kalshi_markets": len(kalshi["markets"]), "kalshi_rejected": len(kalshi["rejected"]),
              "valve_files": sorted(valve["files"]), "hltv": {k.split("/")[2] + k[-14:]: v.get("status")
                                                             for k, v in hltv.items()}}
    print(json.dumps(counts, indent=1))
    lobby_ok = any("lobby_page" in f.get("seen_in", []) for f in hs["fixtures"])
    print("hotspawn lobby membership rows:", sum(1 for f in hs["fixtures"]
                                                 if "lobby_page" in f.get("seen_in", [])))
    return 0 if lobby_ok else 1


if __name__ == "__main__":
    sys.exit(main())
