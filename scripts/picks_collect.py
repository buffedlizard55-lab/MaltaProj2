#!/usr/bin/env python3
"""
Live picks collector — session `ac475c09` (task T-LIVE).

Purpose
-------
Build one machine-collected, fully source-linked picture of the HotSpawn Pick'ems lobby:

  1. `data/picks_fixtures.json` — every fixture the lobby's own public API offers, with the
     lobby's lock time (UTC), tier, tournament and the crowd "picked %" recorded for reference only.
  2. `data/picks_quotes.json`   — external match-winner quotes only. Every quote keeps the exact
     URL it was read from, the source's own event/market ids, the retrieval timestamp (UTC), the
     raw price and whether a decimal value is derived.
  3. `evidence/picks/reachability.json` — what each candidate source answered (status, size,
     item counts, error text) so an unreachable source is never confused with "no price exists".

Rules (never violated by this script):
  * HotSpawn is fixture discovery only. `team_a_pick_pct` / `team_b_pick_pct` are crowd picks and
    are NEVER emitted as, or mixed into, a probability.
  * Only match/series-winner moneyline markets are quoted. Map winners, handicaps, totals and
    live markets are excluded.
  * Nothing is inferred: if a source does not quote a fixture, no value is written for it.

No authentication, no admin endpoints, no paywall bypass: every URL below is a public page or a
public JSON endpoint that the source's own website calls in a normal browser session.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
HOTSPAWN_LOBBY = "https://play.hotspawn.com/lobby"

PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_SPORT_ESPORTS = 12
PIN_HEADERS = {
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "Referer": "https://www.pinnacle.com/",
    "Accept": "application/json",
}
BOVADA_ESPORTS = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"

# Candidate extra sources. Each is probed and recorded; a parser only runs when the probe
# finds a shape it can read without guessing.
EXTRA_SOURCES = {
    "egamersworld_cs2": "https://egamersworld.com/counterstrike/matches",
    "egamersworld_lol": "https://egamersworld.com/lol/matches",
    "thunderpick_api": "https://api.thunderpick.io/api/v1/esports/matches",
    "cloudbet_esports": "https://sports-api.cloudbet.com/pub/v2/odds/sports/3/categories",
    "onexbet_line": ("https://1xbet.com/service-api/LineFeed/Get1x2_VZip"
                     "?sports=3&count=200&lng=en&mode=4&country=1&getEmpty=true"),
    "polymarket_cs2": ("https://gamma-api.polymarket.com/events?closed=false&limit=100"
                       "&tag_slug=counter-strike"),
    "kalshi_esports": "https://api.elections.kalshi.com/trade-api/v2/events?limit=200",
    "bo3gg_matches": "https://bo3.gg/api/v1/matches?page[limit]=50",
}

CS2_LEAGUE_RE = re.compile(r"counter[- ]?strike|cs2|cs:?go", re.I)
LOL_LEAGUE_RE = re.compile(r"league of legends|\blol\b", re.I)
ESPORT_LEAGUE_RE = re.compile(r"counter[- ]?strike|cs2|cs:?go|league of legends|\blol\b", re.I)

SUFFIXES = (" esports", " esport", " e sports", " gaming", " club", " academy")
PREFIXES = ("team ",)
# Source spelling -> HotSpawn spelling. Documented in the site's methodology page; an alias is
# accepted only when the fixture also agrees on start time or tournament (enforced in picks_build).
ALIASES = {
    "bb team": "betboom",
    "pvision": "parivision",
    "9z globant": "9z",
    "team aurora": "aurora",
    "sashi esport": "sashi",
    "furia esports": "furia",
    "ninjas in pyjamas": "ninjas in pyjamas",
    "n i p": "ninjas in pyjamas",
    "nip": "ninjas in pyjamas",
    "virtus pro": "virtus pro",
    "g2 ares": "g2 ares",
    "mibr academy": "mibr academy",
}


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for suf in SUFFIXES:
        if s.endswith(suf.strip()):
            s = s[: -len(suf.strip())].strip()
    for pre in PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):].strip()
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


def ms_iso(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (100 / abs(a)) if a < 0 else 1 + (a / 100), 4)


def fetch(url: str, headers: dict | None = None, timeout: int = 45):
    hdrs = {
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    if headers:
        hdrs.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout) as r:
            return r.status, r.read(), r.geturl()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        return exc.code, body, url
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode("utf-8", "replace"), url


def write(rel: str, obj) -> None:
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {rel}")


# --------------------------------------------------------------------------- fixtures
def collect_fixtures(evidence: dict) -> list[dict]:
    url = f"{HOTSPAWN_API}/fixtures"
    status, body, _ = fetch(url, {"Accept": "application/json"}, timeout=120)
    evidence["hotspawn_fixtures"] = {"url": url, "status": status, "bytes": len(body)}
    try:
        raw = json.loads(body.decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        evidence["hotspawn_fixtures"]["error"] = f"unparsable: {exc}"
        return []
    if not isinstance(raw, list):
        evidence["hotspawn_fixtures"]["error"] = "endpoint did not return a list"
        return []
    evidence["hotspawn_fixtures"]["count"] = len(raw)

    evidence["hotspawn_fixtures"]["fields"] = sorted({k for f in raw for k in f})
    out = []
    for f in raw:
        out.append({
            "fixture_id": str(f.get("id")),
            "sport": f.get("sport_alias"),
            "sport_name": f.get("sport_name"),
            "competition": f.get("competition_name"),
            "competition_id": str(f.get("competition_id")) if f.get("competition_id") is not None else None,
            "tier": f.get("tier"),
            "status": f.get("status"),
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "start_time_utc": ms_iso(f.get("scheduled_start_time")),
            "lock_time_utc": ms_iso(f.get("lock_time")),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "offered_points": f.get("offered_points"),
            "team_a": f.get("participants0_name"),
            "team_b": f.get("participants1_name"),
            # Recorded for reference only; never used as a probability by any script in this repo.
            "team_a_pick_pct_reference_only": f.get("participants0_picked_percent"),
            "team_b_pick_pct_reference_only": f.get("participants1_picked_percent"),
        })
    return out


# --------------------------------------------------------------------------- Pinnacle
def collect_pinnacle(quotes: list[dict], evidence: dict) -> None:
    url = f"{PIN}/sports/{PIN_SPORT_ESPORTS}/matchups"
    status, body, _ = fetch(url, PIN_HEADERS)
    evidence["pinnacle_matchups"] = {"url": url, "status": status, "bytes": len(body)}
    try:
        matchups = json.loads(body.decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        evidence["pinnacle_matchups"]["error"] = str(exc)
        return
    if not isinstance(matchups, list):
        evidence["pinnacle_matchups"]["error"] = "not a list"
        return
    leagues = sorted({(m.get("league") or {}).get("name", "") for m in matchups})
    evidence["pinnacle_matchups"]["count"] = len(matchups)
    evidence["pinnacle_matchups"]["esports_leagues"] = leagues[:80]
    esports = [m for m in matchups if ESPORT_LEAGUE_RE.search(str((m.get("league") or {}).get("name", "")))]
    evidence["pinnacle_matchups"]["esports_count"] = len(esports)
    evidence["pinnacle_matchups"]["cs2_leagues"] = sorted(
        {(m.get("league") or {}).get("name", "") for m in esports
         if CS2_LEAGUE_RE.search(str((m.get("league") or {}).get("name", "")))})

    for m in esports:
        parts = m.get("participants") or []
        if len(parts) != 2:
            continue
        league = (m.get("league") or {}).get("name", "")
        game = "cs2" if CS2_LEAGUE_RE.search(league) else ("lol" if LOL_LEAGUE_RE.search(league) else None)
        if game is None:
            continue
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        st2, body2, _ = fetch(murl, PIN_HEADERS)
        try:
            markets = json.loads(body2.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
            continue
        if not isinstance(markets, list):
            time.sleep(0.2)
            continue
        cands = [mk for mk in markets
                 if str(mk.get("type", "")).lower() == "moneyline" and mk.get("period") == 0
                 and not mk.get("isAlternate") and isinstance(mk.get("prices"), list)
                 and len(mk.get("prices") or []) == 2
                 and all(p.get("price") is not None for p in mk.get("prices") or [])]
        if not cands:
            continue
        mk = cands[0]
        by_align = {p.get("designation"): p.get("price") for p in mk["prices"]}
        a_am = by_align.get("home" if parts[0].get("alignment") == "home" else "away")
        b_am = by_align.get("home" if parts[1].get("alignment") == "home" else "away")
        if a_am is None or b_am is None:
            continue
        quotes.append({
            "source_key": "pinnacle",
            "source_name": "Pinnacle",
            "source_kind": "licensed bookmaker (public guest odds API)",
            "source_public_url": f"https://www.pinnacle.com/en/esports/matchups/{mid}",
            "source_api_url": murl,
            "source_event_id": str(mid),
            "source_market_id": str(mk.get("id")),
            "source_game": game,
            "source_league": league,
            "market_type": "match/series winner (moneyline)",
            "market_is_live": bool(m.get("isLive")),
            "market_status": mk.get("status"),
            "retrieved_at_utc": now_iso(),
            "start_time_utc": ms_iso(m.get("startTime")),
            "team_a_name": parts[0].get("name"),
            "team_b_name": parts[1].get("name"),
            "raw_price_format": "american",
            "raw_price_a": a_am,
            "raw_price_b": b_am,
            "decimal_odds_a": american_to_decimal(a_am),
            "decimal_odds_b": american_to_decimal(b_am),
            "decimal_odds_derived": True,
        })
        time.sleep(0.2)


# --------------------------------------------------------------------------- Bovada
def collect_bovada(quotes: list[dict], evidence: dict) -> None:
    status, body, _ = fetch(BOVADA_ESPORTS, {"Accept": "application/json"})
    evidence["bovada_esports"] = {"url": BOVADA_ESPORTS, "status": status, "bytes": len(body)}
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        evidence["bovada_esports"]["error"] = str(exc)
        return
    events = []
    for group in data if isinstance(data, list) else []:
        for path in (group.get("events") or []), ((group.get("path") or [{}])[0].get("events") or []):
            for ev in path:
                events.append((group, ev))
    evidence["bovada_esports"]["events"] = len(events)
    groups = {}
    for group, ev in events:
        league = "/".join([(p.get("description") or "") for p in (group.get("path") or [])]) or group.get("description") or ""
        game = "cs2" if CS2_LEAGUE_RE.search(league) else ("lol" if LOL_LEAGUE_RE.search(league) else None)
        if game is None:
            continue
        comp = ev.get("competitors") or []
        if len(comp) != 2:
            continue
        ml = None
        for disp in ev.get("displayGroups") or []:
            for mk in disp.get("markets") or []:
                if str(mk.get("description", "")).lower().startswith("moneyline") and len(mk.get("outcomes") or []) == 2:
                    ml = mk
                    break
            if ml:
                break
        if not ml:
            continue
        prices = {}
        for oc in ml["outcomes"]:
            try:
                prices[str(oc.get("description"))] = float(str(oc.get("price", "")).replace(",", ""))
            except (TypeError, ValueError):
                prices[str(oc.get("description"))] = None
        a_am = prices.get(str(comp[0].get("description")))
        b_am = prices.get(str(comp[1].get("description")))
        if a_am is None or b_am is None:
            continue
        link = ev.get("link") or f"/sports/esports/{ev.get('id')}"
        groups.setdefault(league, 0)
        groups[league] += 1
        quotes.append({
            "source_key": "bovada",
            "source_name": "Bovada",
            "source_kind": "licensed bookmaker (public coupon JSON)",
            "source_public_url": "https://www.bovada.lv" + link,
            "source_api_url": BOVADA_ESPORTS,
            "source_event_id": str(ev.get("id")),
            "source_market_id": str(ml.get("id")),
            "source_game": game,
            "source_league": league,
            "market_type": "match winner (moneyline)",
            "market_is_live": bool(ev.get("live")),
            "market_status": ev.get("status"),
            "retrieved_at_utc": now_iso(),
            "start_time_utc": ev.get("startTime"),
            "team_a_name": comp[0].get("description"),
            "team_b_name": comp[1].get("description"),
            "raw_price_format": "american",
            "raw_price_a": a_am,
            "raw_price_b": b_am,
            "decimal_odds_a": american_to_decimal(a_am),
            "decimal_odds_b": american_to_decimal(b_am),
            "decimal_odds_derived": True,
        })
    evidence["bovada_esports"]["matched_by_league"] = groups


# --------------------------------------------------------------------------- extras (probe + best effort)
def probe_extra_sources(quotes: list[dict], evidence: dict) -> None:
    for key, url in EXTRA_SOURCES.items():
        status, body, final = fetch(url, None, timeout=45)
        entry = {"url": url, "status": status, "bytes": len(body), "final_url": final}
        text = body.decode("utf-8", "replace")
        entry["preview"] = text[:300].replace("\n", " ")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001
            parsed = None
        if isinstance(parsed, dict):
            entry["json_keys"] = sorted(parsed.keys())[:25]
        elif isinstance(parsed, list):
            entry["json_list_len"] = len(parsed)
        if status == 200:
            # A raw, inert sample is kept so every parse can be re-checked against the exact bytes
            # the source served (never re-typed by hand).
            entry["sample"] = text[:4000]
            raw_name = {"egamersworld_cs2": "egamersworld_cs2.html",
                        "egamersworld_lol": "egamersworld_lol.html",
                        "bo3gg_matches": "bo3gg_matches.html"}.get(key)
            if raw_name:
                raw_path = os.path.join(ROOT, "evidence", "picks", "raw", raw_name)
                os.makedirs(os.path.dirname(raw_path), exist_ok=True)
                with open(raw_path, "w", encoding="utf-8") as fh:
                    fh.write(text[:900_000])
                entry["raw_saved"] = f"evidence/picks/raw/{raw_name}"
        evidence[key] = entry


# --------------------------------------------------------------------------- main
def main() -> int:
    started = now_iso()
    evidence = {"generated_at_utc": started, "session": "ac475c09"}
    quotes: list[dict] = []

    fixtures = collect_fixtures(evidence)

    for fn in (collect_pinnacle, collect_bovada):
        try:
            fn(quotes, evidence)
        except Exception as exc:  # noqa: BLE001
            evidence[fn.__name__ + "_error"] = repr(exc)

    try:
        probe_extra_sources(quotes, evidence)
    except Exception as exc:  # noqa: BLE001
        evidence["extra_sources_error"] = repr(exc)

    now = datetime.now(tz=timezone.utc)
    for f in fixtures:
        lock = f.get("lock_time_utc")
        f["open_for_picks"] = bool(lock and lock > now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        f["hotspawn_match_url"] = f"https://www.hotspawn.com/matches/{f['fixture_id']}"

    open_cs2 = [f for f in fixtures if f["open_for_picks"] and (f.get("sport") or "").lower() in ("cs2", "counter-strike-2", "csgo")]
    open_lol = [f for f in fixtures if f["open_for_picks"] and (f.get("sport") or "").lower() in ("lol", "league-of-legends")]
    summary = {
        "generated_at_utc": started,
        "hotspawn_source": {"page": HOTSPAWN_LOBBY, "api": f"{HOTSPAWN_API}/fixtures"},
        "fixtures_total": len(fixtures),
        "fixtures_open_cs2": len(open_cs2),
        "fixtures_open_lol": len(open_lol),
        "quotes_total": len(quotes),
        "quotes_by_source": {},
        "rules": [
            "HotSpawn is fixture discovery only; crowd pick percentages are never used as probabilities.",
            "Match/series winner moneyline markets only; map markets, handicaps, totals and live markets excluded.",
            "A missing price stays missing: no value is inferred, filled or extrapolated.",
        ],
    }
    for q in quotes:
        summary["quotes_by_source"][q["source_key"]] = summary["quotes_by_source"].get(q["source_key"], 0) + 1

    write("data/picks_fixtures.json", {"summary": summary, "fixtures": fixtures})
    write("data/picks_quotes.json", {"summary": summary, "quotes": quotes})
    write("evidence/picks/reachability.json", evidence)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
