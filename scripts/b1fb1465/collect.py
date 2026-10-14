#!/usr/bin/env python3
"""Session b1fb1465 collector — runs on a GitHub-hosted runner (general internet).

What it collects, and why
-------------------------
* **HotSpawn public lobby** (``play.hotspawn.com/lobby``) — fixture discovery only, read from the
  Angular transfer state the page itself embeds. A crowd pick percentage is refused by the parser in
  :mod:`core`; it is never stored here.
* **External prices** — Pinnacle (licensed bookmaker, public guest odds API), Bovada (licensed
  bookmaker, public coupon JSON), the 1xBet-platform LineFeed that Melbet/22bet/Betwinner serve, the
  CFTC-regulated **Kalshi** exchange (``KXCS2GAME``), and the **Thunderpick** coefficients bo3.gg
  publishes per fixture inside ``bet_updates``.
* **Official ratings** — Valve's own ``counter-strike_regional_standings`` global standings, read
  from the GitHub API. This is the only input used to *originate* a line where no market exists.
* **Access evidence** — every request is logged with URL, HTTP status, byte count, error text and
  UTC read time, including the sources that refuse this environment (HLTV, Thunderpick's own site,
  EGamersWorld, several sportsbooks). A blocked source is published as a failure, never as "no price
  exists". Kalshi legs keep their bid/ask and spread so a thin book can be labelled instead of
  silently dropped.

Output: ``data/b1fb1465/snapshot.json``.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "b1fb1465"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

LOBBY_PAGE = "https://play.hotspawn.com/lobby"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/",
               "Accept": "application/json"}
BOVADA = ("https://www.bovada.lv/services/sports/event/v2/events/A/description/"
          "esports/counter-strike-2")
LINEFEED_MIRRORS = ("melbet", "22bet", "betwinner")
LINEFEED_URL = "https://{mirror}.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"
KALSHI_EVENTS = ("https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}"
                 "&status=open&with_nested_markets=true&limit=200")
BO3 = "https://api.bo3.gg/api/v1"
BO3_MATCHES = (f"{BO3}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               "&sort=start_date&page%5Blimit%5D=100")
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
PROP_RE = re.compile(r"\(|\)|\byes\b|\bno\b|kills?|\bmaps?\b|total|handicap|rounds?|pistol", re.I)
HLTV_PROBES = ("https://www.hltv.org/matches",
               "https://www.hltv.org/betting/analytics")
PROBE_ONLY = {
    "oddsportal_cs2": "https://www.oddsportal.com/esports/counter-strike/",
    "flashscore_esports": "https://www.flashscore.com/esports/",
    "thunderpick_site": "https://thunderpick.io/esports/cs2-betting",
    "egamersworld": "https://egamersworld.com/counterstrike/matches",
    "ggbet": "https://gg.bet/en/esports",
    "stake": "https://stake.com/sports/esports",
    "betano": "https://www.betano.com/sport/esports/",
    "vbet": "https://www.vbet.com/en/sports/esports",
    "parimatch": "https://parimatch.com/en/sports/esports",
}
LOG: dict = {}
MAX_BO3_MATCH_PAGES = 5


def fetch(url: str, headers: dict | None = None, timeout: int = 45) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None,
            "at_utc": core.iso(core.now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read()
            meta["status"] = r.status
            meta["age_header"] = r.headers.get("Age")
            meta["content_type"] = r.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        meta["status"], meta["error"] = exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 - a network failure is evidence
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    if body:
        meta["sha256_16"] = __import__("hashlib").sha256(body).hexdigest()[:16]
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


# ------------------------------------------------------------------------------- HotSpawn
def collect_hotspawn() -> dict:
    page, meta = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=60)
    LOG["hotspawn_lobby_page"] = meta
    state = core.lobby_state(page.decode("utf-8", "replace")) if page else {}
    raw_fixtures = state.get("fixtures") or []
    LOG["hotspawn_lobby_page"]["fixtures_in_transfer_state"] = len(raw_fixtures)
    fixtures: dict[str, dict] = {}
    for raw in raw_fixtures:
        fx = core.fixture_from_hotspawn(raw)
        if fx:
            fixtures[fx["fixture_id"]] = fx
    permalinks = state.get("permalinks") or {}
    for fid, fx in fixtures.items():
        url = permalinks.get(fid)
        fx["hotspawn_url"] = url or LOBBY_PAGE
        fx["hotspawn_url_kind"] = "match page" if url else "official lobby page (no permalink)"
    return {"fixtures": sorted(fixtures.values(), key=lambda r: (r["start_utc"], r["fixture_id"])),
            "week": state.get("week"), "permalinks": permalinks}


# --------------------------------------------------------------------------- quote helpers
def quote(source_key: str, source_name: str, public_url: str, api_url: str, event_id, team_a,
          team_b, dec_a: float, dec_b: float, start, league, raw_format: str, raw_a, raw_b,
          live: bool = False, extra: dict | None = None) -> dict:
    nv = core.no_vig(dec_a, dec_b)
    rec = {
        "source_key": source_key, "source_name": source_name, "public_url": public_url,
        "api_url": api_url, "event_id": str(event_id), "team_a": team_a, "team_b": team_b,
        "decimal_a": round(float(dec_a), 4), "decimal_b": round(float(dec_b), 4),
        "raw_format": raw_format, "raw_a": str(raw_a), "raw_b": str(raw_b),
        "prob_a": round(nv["prob_a"], 6) if nv else None,
        "overround": round(nv["overround"], 6) if nv else None,
        "start_utc": core.iso(start), "league": league, "live": bool(live),
        "retrieved_utc": core.iso(core.now_utc()),
    }
    rec.update(extra or {})
    return rec


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
            da = core.american_to_decimal(by["home"])
            db = core.american_to_decimal(by["away"])
            if da and db:
                quotes.append(quote("pinnacle", "Pinnacle", "https://www.pinnacle.com/en/esports/cs2-hub",
                                    murl, m["id"], al["home"], al["away"], da, db,
                                    core.parse_iso(str(m.get("startTime") or "")),
                                    (m.get("league") or {}).get("name"), "american", by["home"],
                                    by["away"], live=bool(m.get("isLive") or mk.get("isLive"))))
                written += 1
            break
    LOG["pinnacle"]["quotes"] = written


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
                    quotes.append(quote("bovada", "Bovada",
                                        "https://www.bovada.lv" + str(ev.get("link") or "/sports/esports"),
                                        BOVADA, ev.get("id"), home.get("name"), away.get("name"),
                                        float(dh), float(da),
                                        core.parse_any(ev.get("startTime")),
                                        league, "decimal", dh, da, live=ev.get("live")))
                    written += 1
                    break
    LOG["bovada"]["quotes"] = written


def collect_linefeed(quotes: list) -> None:
    seen: set[str] = set()
    for mirror in LINEFEED_MIRRORS:
        url = LINEFEED_URL.format(mirror=mirror)
        data, meta = fetch_json(url, {"Accept": "application/json"})
        LOG[f"linefeed_{mirror}"] = meta
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
            quotes.append(quote("melbet", "Melbet (1xBet platform)", "https://melbet.com/en/line/esports",
                                url, key, a, b, float(prices[1]), float(prices[3]),
                                core.parse_any(ev.get("S")), league, "decimal",
                                prices[1], prices[3], extra={"mirror": mirror}))
            written += 1
        LOG[f"linefeed_{mirror}"]["quotes"] = written


def _epoch_to_iso(value) -> str | None:
    try:
        secs = float(value)
    except (TypeError, ValueError):
        return None
    if secs <= 0:
        return None
    return core.iso(core.datetime.fromtimestamp(secs, tz=core.timezone.utc))


def _money(value):
    """Kalshi reports dollars (0..1) in ``*_dollars`` and cents in the legacy fields."""
    if value in (None, ""):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f <= 1.0 else f / 100.0


def collect_kalshi(quotes: list, attempts: list) -> None:
    """Game-winner markets only (map markets are kept out of the match pick)."""
    events: list[dict] = []
    for series in ("KXCS2GAME",):
        data, meta = fetch_json(KALSHI_EVENTS.format(series=series), {"Accept": "application/json"})
        LOG[f"kalshi_{series}"] = meta
        rows = (data or {}).get("events") if isinstance(data, dict) else None
        LOG[f"kalshi_{series}"]["events"] = len(rows) if isinstance(rows, list) else None
        events.extend(rows if isinstance(rows, list) else [])
    written = 0
    for ev in events:
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
        ticker = ev.get("event_ticker")
        start = kalshi_start(ticker)
        public_url = f"https://kalshi.com/markets/kxcs2game/{str(ticker).lower()}"
        rec = {"source_key": "kalshi", "source_name": "Kalshi (exchange)",
               "public_url": public_url, "api_url": KALSHI_EVENTS.format(series="KXCS2GAME"),
               "event_id": ticker, "team_a": legs[0]["team"], "team_b": legs[1]["team"],
               "start_utc": core.iso(start), "start_is_approx": True,
               "retrieved_utc": core.iso(core.now_utc()), "legs": legs}
        if any(leg["bid"] is None for leg in legs):
            attempts.append({**rec, "reason": "one-sided or empty order book (no bid on a leg)"})
            continue
        spread = max((leg["spread"] or 0) for leg in legs)
        mids = [(leg["bid"] + leg["ask"]) / 2.0 for leg in legs]
        if sum(mids) <= 0:
            attempts.append({**rec, "reason": "mid price could not be formed"})
            continue
        prob_a = mids[0] / (mids[0] + mids[1])
        quotes.append({**quote("kalshi", "Kalshi (exchange)", public_url,
                               KALSHI_EVENTS.format(series="KXCS2GAME"), ticker, legs[0]["team"],
                               legs[1]["team"], 1.0 / mids[0] if mids[0] else 0,
                               1.0 / mids[1] if mids[1] else 0, start, ev.get("title"),
                               "yes mid ($)", round(mids[0], 4), round(mids[1], 4),
                               extra={"start_is_approx": True, "spread": round(spread, 4),
                                      "thin_book": bool(spread > 0.10), "legs": legs,
                                      "prob_a": round(prob_a, 6)})})
        written += 1
    LOG["kalshi_quotes"] = written


KALSHI_TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def kalshi_start(event_ticker: str):
    """Kalshi tickers encode US Eastern time. Used only for the join window, never displayed."""
    m = KALSHI_TICKER_TIME.search(event_ticker or "")
    if not m:
        return None
    months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    try:
        dt = core.datetime(2000 + int(m.group(1)), months.index(m.group(2)) + 1, int(m.group(3)),
                           int(m.group(4)), int(m.group(5)), tzinfo=core.timezone.utc)
    except ValueError:
        return None
    return dt + timedelta(hours=4)   # EDT in October; only widens the join window


# ------------------------------------------------------------------------------- bo3.gg
def collect_bo3gg() -> dict:
    """Upcoming fixtures with the Thunderpick two-way coefficient bo3.gg publishes per match."""
    matches: list[dict] = []
    for page in range(MAX_BO3_MATCH_PAGES):
        url = (f"{BO3_MATCHES}&filter%5Bmatches.status%5D%5Bin%5D=upcoming"
               f"&page%5Boffset%5D={page * 100}")
        data, meta = fetch_json(url, {"Accept": "application/json"})
        if page == 0:
            LOG["bo3gg_matches"] = meta
        rows = (data or {}).get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        for m in rows:
            if isinstance(m, dict):
                matches.append({k: m.get(k) for k in (
                    "id", "slug", "team1_id", "team2_id", "tournament_id", "status", "bo_type",
                    "start_date", "tier", "bet_updates", "tournament")})
        if len(rows) < 100:
            break
    LOG["bo3gg_matches"]["matches"] = len(matches)
    # Team records are kept only for the ids the bet feed references: they are the published
    # evidence that a feed name (e.g. "ROUNDS") and a page name ("RoundsGG") are one roster.
    team_ids = set()
    for m in matches:
        bu = m.get("bet_updates") or {}
        for side in ("team_1", "team_2"):
            tid = (bu.get(side) or {}).get("team_id") or m.get(f"team{side[-1]}_id")
            if tid:
                team_ids.add(str(tid))
    teams: dict[str, dict] = {}
    for tid in sorted(team_ids)[:80]:
        data, _ = fetch_json(f"{BO3}/teams/?filter%5Bteams.id%5D%5Beq%5D={tid}&limit=1",
                             {"Accept": "application/json"})
        rec = (data or {}).get("results") if isinstance(data, dict) else None
        if rec:
            teams[tid] = {k: rec[0].get(k) for k in ("id", "name", "slug", "acronym", "rank",
                                                     "discipline_id")}
        time.sleep(0.05)
    LOG["bo3gg_teams"] = len(teams)
    return {"matches": matches, "teams": teams}


# ----------------------------------------------------------------------------- Valve VRS
def collect_vrs() -> dict:
    tree, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1",
                            {"Accept": "application/vnd.github+json"})
    LOG["valve_vrs_tree"] = meta
    files = sorted(str(t.get("path")) for t in (tree or {}).get("tree") or []
                   if str(t.get("path", "")).startswith("live/2026/standings_global_"))
    if not files:
        return {}
    latest = files[-1]
    url = f"https://api.github.com/repos/{VRS_REPO}/contents/{latest}"
    data, meta2 = fetch_json(url, {"Accept": "application/vnd.github+json"})
    LOG["valve_vrs_file"] = {**meta2, "path": latest}
    import base64
    text = ""
    if isinstance(data, dict) and data.get("content"):
        try:
            text = base64.b64decode(data["content"]).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            text = ""
    teams: dict[str, dict] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        try:
            standing, points = int(cells[0]), float(cells[1])
        except ValueError:
            continue
        name = cells[2]
        if not name:
            continue
        teams[core.norm(name)] = {"name": name, "standing": standing, "points": points,
                                  "roster": cells[3]}
    return {"snapshot": latest, "source_url": f"https://github.com/{VRS_REPO}/blob/main/{latest}",
            "api_url": url, "teams": teams, "count": len(teams)}


# ------------------------------------------------------------------------------- probes
def probe(name: str, url: str, headers: dict | None = None) -> None:
    body, meta = fetch(url, headers or {"Accept": "text/html,application/json;q=0.9"}, timeout=30)
    meta["first_bytes"] = body[:120].decode("utf-8", "replace") if body else ""
    LOG[f"probe_{name}"] = meta


def main() -> int:
    started = core.now_utc()
    quotes: list[dict] = []
    attempts: list[dict] = []
    hotspawn = collect_hotspawn()
    for name, fn in (("pinnacle", lambda: collect_pinnacle(quotes)),
                     ("bovada", lambda: collect_bovada(quotes)),
                     ("linefeed", lambda: collect_linefeed(quotes)),
                     ("kalshi", lambda: collect_kalshi(quotes, attempts))):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - one failed source never stops a run
            LOG[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    bo3 = {"matches": [], "teams": {}}
    try:
        bo3 = collect_bo3gg()
        written = 0
        for m in bo3["matches"]:
            bu = m.get("bet_updates") or {}
            t1, t2 = bu.get("team_1") or {}, bu.get("team_2") or {}
            try:
                da, db = float(t1.get("coeff")), float(t2.get("coeff"))
            except (TypeError, ValueError):
                continue
            if da <= 1.0 or db <= 1.0:
                continue
            quotes.append(quote("thunderpick", "Thunderpick (via bo3.gg)",
                                f"https://bo3.gg/matches/{m.get('slug')}",
                                f"{BO3}/matches/?filter%5Bmatches.id%5D%5Beq%5D={m.get('id')}",
                                m.get("id"), t1.get("name") or "", t2.get("name") or "", da, db,
                                core.parse_iso(str(m.get("start_date") or "")),
                                (m.get("tournament") or {}).get("name") or "", "decimal",
                                t1.get("coeff"), t2.get("coeff"),
                                extra={"provider": bu.get("provider"), "mirror_page": "bo3.gg",
                                       "team1_id": m.get("team1_id"), "team2_id": m.get("team2_id"),
                                       "max_coeff_a": t1.get("max_coeff"),
                                       "max_coeff_b": t2.get("max_coeff"),
                                       "feed_team_ids": {t1.get("name") or "": t1.get("team_id"),
                                                         t2.get("name") or "": t2.get("team_id")}}))
            written += 1
        LOG["thunderpick_quotes"] = written
    except Exception as exc:  # noqa: BLE001
        LOG["bo3gg_matches"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    vrs: dict = {}
    try:
        vrs = collect_vrs()
    except Exception as exc:  # noqa: BLE001
        LOG["valve_vrs"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    for name, url in PROBE_ONLY.items():
        try:
            probe(name, url)
        except Exception as exc:  # noqa: BLE001
            LOG[f"probe_{name}"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    for url in HLTV_PROBES:
        try:
            probe("hltv_" + re.sub(r"[^a-z]+", "_", url.split("//", 1)[1]), url)
        except Exception as exc:  # noqa: BLE001
            LOG["probe_hltv"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}

    doc = {
        "session": "b1fb1465",
        "generated_utc": core.iso(core.now_utc()),
        "collection_seconds": round((core.now_utc() - started).total_seconds(), 1),
        "hotspawn": hotspawn,
        "quotes": quotes,
        "kalshi_not_usable": attempts,
        "vrs": {k: v for k, v in vrs.items() if k != "teams"},
        "vrs_teams": vrs.get("teams") or {},
        "bo3gg_teams": bo3.get("teams") or {},
        "access": LOG,
        "notes": [
            "HotSpawn is used for fixture discovery and the final score only; its crowd pick "
            "percentage is never read, stored or used as an input.",
            "Kalshi legs keep bid/ask/spread: a two-sided thin book is published with a flag "
            "instead of being dropped, and a one-sided book is refused.",
            "HLTV is probed on every run; when it refuses the runner the failure is published and "
            "HLTV can only be cited as a dated, interactive cross-check.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "snapshot.json").write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n",
                                       encoding="utf-8")
    open_fixtures = [f for f in hotspawn["fixtures"] if core.is_open(f)]
    print(f"hotspawn fixtures={len(hotspawn['fixtures'])} open={len(open_fixtures)} "
          f"quotes={len(quotes)} kalshi_refused={len(attempts)} vrs={vrs.get('count')} "
          f"seconds={doc['collection_seconds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
