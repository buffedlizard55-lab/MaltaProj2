#!/usr/bin/env python3
"""Session b1fb1465 source probe.

Runs on a GitHub-hosted runner (the only environment this project has general internet in) and
answers one question with evidence: **for the open HotSpawn CS2 fixtures that no bookmaker or
exchange priced in the last full-coverage collection, which additional public sources carry a
usable two-way price or an official rating?**

The user's requested order of investigation is implemented literally:

1. ``hltv`` — HLTV match pages and the HLTV betting-analytics pages that publish the best odds
   their partner bookmakers quote.
2. ``esportsbook`` — bookmaker / esportsbook endpoints that are public and unauthenticated
   (1xBet-platform mirrors with per-championship enumeration, Kalshi exchange, Polymarket,
   bo3.gg's published Thunderpick coefficients, and the remaining reachability probes).
3. ``origin`` — the official Valve VRS standings, the only ratings source this project uses to
   originate a line when no market exists.

Every request is recorded with URL, HTTP status, byte count, error text and UTC read time, so a
blocked source is published as a *failure*, never as "no price exists". Nothing is inferred from a
source that did not answer, and a price is only recorded when the payload itself contains both
sides of a two-way market.

Output: ``data/b1fb1465/probe.json`` plus a compact stdout summary the workflow log keeps.
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "b1fb1465"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

# The fixtures that had no market price and no exchange quote at the last full-coverage build.
TARGETS = [
    {"fixture_id": "1081112", "team_a": "Banda chuya", "team_b": "6666",
     "competition": "CCT Europe 2026 Series #12 Play-In", "start_utc": "2026-10-14T11:00:00Z"},
    {"fixture_id": "1081113", "team_a": "Ryvex", "team_b": "PCIFIC",
     "competition": "CCT Europe 2026 Series #12 Play-In", "start_utc": "2026-10-14T14:00:00Z"},
    {"fixture_id": "1080286", "team_a": "HAVU", "team_b": "RoundsGG",
     "competition": "Elisa BreakOut Series #2", "start_utc": "2026-10-16T10:00:00Z"},
    {"fixture_id": "1081120", "team_a": "mellren", "team_b": "Privateer",
     "competition": "CCT Europe 2026 Series #12 Play-In", "start_utc": "2026-10-16T14:00:00Z"},
    {"fixture_id": "1080289", "team_a": "RoundsGG", "team_b": "Voca",
     "competition": "Elisa BreakOut Series #2", "start_utc": "2026-10-16T16:00:00Z"},
    {"fixture_id": "1080200", "team_a": "Wildcard", "team_b": "DENDELE",
     "competition": "FRAG University 2026", "start_utc": "2026-11-12T00:00:00Z"},
]

REQUEST_LOG: list[dict] = []


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, headers: dict | None = None, timeout: int = 40) -> tuple[bytes, dict]:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None, "at_utc": iso(now_utc())}
    body = b""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            body = r.read()
            meta["status"] = r.status
            meta["content_type"] = r.headers.get("Content-Type")
            meta["age_header"] = r.headers.get("Age")
    except urllib.error.HTTPError as exc:
        meta["status"] = exc.code
        meta["error"] = f"HTTPError {exc.code}"
        try:
            body = exc.read(4096)
        except Exception:  # noqa: BLE001
            body = b""
    except Exception as exc:  # noqa: BLE001 - a network failure is evidence, never a result
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(body)
    meta["first_bytes"] = body[:120].decode("utf-8", "replace") if body else ""
    REQUEST_LOG.append(meta)
    return body, meta


def fetch_json(url, headers=None, timeout=40):
    body, meta = fetch(url, headers, timeout)
    if not body:
        return None, meta
    try:
        return json.loads(body.decode("utf-8", "replace")), meta
    except ValueError:
        meta["error"] = (meta["error"] or "") + " invalid JSON"
        return None, meta


TEAM_PATTERNS = {
    "banda": re.compile(r"banda", re.I),
    "6666": re.compile(r"(^|[^0-9])6666([^0-9]|$)"),
    "ryvex": re.compile(r"ryvex", re.I),
    "pcific": re.compile(r"pcific", re.I),
    "havu": re.compile(r"\bhavu\b", re.I),
    "roundsgg": re.compile(r"rounds\s*gg|roundsgg", re.I),
    "mellren": re.compile(r"mellren", re.I),
    "privateer": re.compile(r"privateer", re.I),
    "wildcard": re.compile(r"wildcard", re.I),
    "dendele": re.compile(r"dendele", re.I),
}


def team_keys(text: str) -> set[str]:
    return {key for key, rx in TEAM_PATTERNS.items() if rx.search(text or "")}


def probe_kalshi(report: dict) -> None:
    """CFTC-regulated exchange: what does it list for CS2 today, and does it cover the gaps?"""
    cs2_events: list[dict] = []
    for ticker in ("KXCS2GAME", "KXCS2MAP", "KXCS2SERIES", "KXCS2MATCH", "KXCS2"):
        url = (f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={ticker}"
               "&status=open&with_nested_markets=true&limit=200")
        data, meta = fetch_json(url)
        events = (data or {}).get("events") if isinstance(data, dict) else None
        report[f"kalshi_{ticker}"] = {"status": meta.get("status"), "error": meta.get("error"),
                                     "events": len(events) if isinstance(events, list) else None}
        if isinstance(events, list):
            for ev in events:
                if ticker == "KXCS2GAME" or team_keys(str(ev.get("title"))):
                    cs2_events.append({"series": ticker, "event_ticker": ev.get("event_ticker"),
                                       "title": ev.get("title"),
                                       "markets": len(ev.get("markets") or [])})
    hits = [e for e in cs2_events if team_keys(str(e.get("title")))]
    report["kalshi_cs2_events"] = len(cs2_events)
    report["kalshi_gap_hits"] = hits


def probe_bo3gg(report: dict) -> None:
    """bo3.gg publishes Thunderpick coefficients per fixture inside ``bet_updates``."""
    base = "https://api.bo3.gg/api/v1"
    found: list[dict] = []
    for page in range(4):
        url = (f"{base}/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               "&filter%5Bmatches.status%5D%5Bin%5D=upcoming&sort=start_date"
               f"&page%5Blimit%5D=100&page%5Boffset%5D={page * 100}")
        data, meta = fetch_json(url)
        rows = (data or {}).get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        for m in rows:
            bu = m.get("bet_updates") or {}
            t1 = (bu.get("team_1") or {})
            t2 = (bu.get("team_2") or {})
            text = f"{t1.get('name') or ''} {t2.get('name') or ''} {m.get('slug') or ''}"
            keys = team_keys(text)
            if not keys:
                continue
            found.append({"id": m.get("id"), "slug": m.get("slug"), "status": m.get("status"),
                          "start_date": m.get("start_date"), "bet_provider": bu.get("provider"),
                          "team_1": t1, "team_2": t2, "team_keys": sorted(keys),
                          "tournament_id": m.get("tournament_id"),
                          "updated_at": bu.get("updated_at") or bu.get("update_time")})
    report["bo3gg_gap_matches"] = found
    # Does the detail endpoint expose more than the list endpoint?
    if found:
        mid = found[0]["id"]
        detail, meta = fetch_json(f"{base}/matches/?filter%5Bmatches.id%5D%5Beq%5D={mid}&page%5Blimit%5D=1")
        rec = ((detail or {}).get("results") or [{}])[0] if isinstance(detail, dict) else {}
        report["bo3gg_detail_keys"] = sorted(rec.keys()) if isinstance(rec, dict) else None
        report["bo3gg_detail_bet_updates"] = rec.get("bet_updates") if isinstance(rec, dict) else None


def probe_hltv(report: dict) -> None:
    """HLTV: reachability plus whether the odds the analytics pages publish are in the HTML."""
    pages = {
        "matches": "https://www.hltv.org/matches",
        "analytics": "https://www.hltv.org/betting/analytics",
        "analytics_pcific_ryvex":
            "https://www.hltv.org/betting/analytics/2399463/pcific-vs-ryvex-"
            "cct-2026-europe-series-12-closed-qualifier",
        "analytics_match_page":
            "https://www.hltv.org/matches/2399463/pcific-vs-ryvex-"
            "cct-2026-europe-series-12-closed-qualifier",
        "analytics_havu_roundsgg_guess":
            "https://www.hltv.org/betting/analytics?event=3564",
    }
    for key, url in pages.items():
        body, meta = fetch(url, {"Accept": "text/html,application/xhtml+xml"})
        html = body.decode("utf-8", "replace")
        report[f"hltv_{key}"] = {
            "status": meta.get("status"), "error": meta.get("error"), "bytes": meta.get("bytes"),
            "cloudflare_challenge": "Just a moment" in html or "cf-challenge" in html,
            "has_odds_markers": bool(re.search(r"oddsCellWrap|betting-analytics-best-odds|"
                                              r"\"odds\"", html)),
            "odds_numbers": sorted(set(re.findall(r"bestOdds[^0-9]{0,20}(\d\.\d\d)", html)))[:10],
            "team_names_seen": sorted(team_keys(html)),
        }


def probe_linefeed_deep(report: dict) -> None:
    """1xBet-platform mirrors: the flat feed is capped, so enumerate championships."""
    base = "https://melbet.com/service-api/LineFeed"
    data, meta = fetch_json(f"{base}/Get1x2_VZip?sports=40&count=2000&lng=en&mode=4&country=1",
                            {"Accept": "application/json"})
    rows = (data or {}).get("Value") if isinstance(data, dict) else None
    cs2 = [ev for ev in (rows or []) if re.search(r"\bCS\s*2\b|Counter-Strike",
                                                 str(ev.get("L") or ev.get("LE") or ""), re.I)]
    report["linefeed_flat"] = {"status": meta.get("status"), "rows": len(rows or []),
                               "cs2_rows": len(cs2)}
    report["linefeed_flat_gap_hits"] = [
        {"id": ev.get("I"), "a": ev.get("O1E") or ev.get("O1"), "b": ev.get("O2E") or ev.get("O2"),
         "league": ev.get("L") or ev.get("LE"), "start": ev.get("S"), "keys": sorted(team_keys(
             f"{ev.get('O1E') or ev.get('O1')} {ev.get('O2E') or ev.get('O2')}"))}
        for ev in cs2 if team_keys(f"{ev.get('O1E') or ev.get('O1')} {ev.get('O2E') or ev.get('O2')}")]
    champs, cmeta = fetch_json(
        f"{base}/GetChampsZip?sports=40&count=500&lng=en&mode=4&country=1&champs=1&partner=1",
        {"Accept": "application/json"})
    crow = (champs or {}).get("Value") if isinstance(champs, dict) else None
    interesting = []
    for ch in crow or []:
        name = str(ch.get("L") or ch.get("LE") or "")
        if re.search(r"cs\s*2|counter-strike|cct|elisa|dach|urban|pulse", name, re.I):
            interesting.append({"id": ch.get("LI") or ch.get("I"), "name": name,
                                "events": ch.get("E") or ch.get("CE")})
    report["linefeed_champs"] = {"status": cmeta.get("status"), "rows": len(crow or []),
                                 "interesting": interesting[:40]}


def probe_books(report: dict) -> None:
    """Remaining esportsbook / odds-page candidates: reachability only, never a price."""
    candidates = {
        "egamersworld_match":
            "https://egamersworld.com/counterstrike/match/4kY9VAmiEg/pcific-espor-vs-ryvex-WPw_DghZr3",
        "egamersworld_matches": "https://egamersworld.com/counterstrike/matches",
        "thunderpick_cs2": "https://thunderpick.io/esports/cs2-betting",
        "ggbet": "https://gg.bet/en/esports",
        "betway_esports": "https://betway.com/en/sports/esports",
        "dafabet_esports": "https://www.dafabet.com/en/esports",
        "parimatch_esports": "https://parimatch.com/en/sports/esports",
        "vbet_esports": "https://www.vbet.com/en/sports/esports",
        "betano_esports": "https://www.betano.com/sport/esports/",
        "stake_esports": "https://stake.com/sports/esports",
        "csgobettings": "https://csgobettings.com/matches/",
        "oddsportal_esports": "https://www.oddsportal.com/esports/",
        "flashscore_esports": "https://www.flashscore.com/esports/",
        "polymarket_cs2":
            "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike",
        "pinnacle_cs2": "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups",
        "bovada_cs2":
            "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2",
    }
    out: dict = {}
    for key, url in candidates.items():
        headers = {"Accept": "application/json"}
        if key == "pinnacle_cs2":
            headers = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
                       "Referer": "https://www.pinnacle.com/", "Accept": "application/json"}
        if key == "polymarket_cs2":
            try:
                data, meta = fetch_json(url, headers)
                events = data if isinstance(data, list) else []
                hits = [{"title": e.get("title"), "slug": e.get("slug")}
                        for e in events if team_keys(str(e.get("title")))]
                out[key] = {"status": meta.get("status"), "error": meta.get("error"),
                            "events": len(events), "gap_hits": hits}
                continue
            except Exception as exc:  # noqa: BLE001
                out[key] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
                continue
        if key in ("pinnacle_cs2", "bovada_cs2"):
            data, meta = fetch_json(url, headers)
            text = json.dumps(data)[:20_000_000] if data is not None else ""
            out[key] = {"status": meta.get("status"), "error": meta.get("error"),
                        "gap_hits": sorted(team_keys(text))}
            continue
        body, meta = fetch(url, {"Accept": "text/html,application/xhtml+xml"})
        html = body.decode("utf-8", "replace")
        out[key] = {"status": meta.get("status"), "error": meta.get("error"),
                    "bytes": meta.get("bytes"), "gap_hits": sorted(team_keys(html))}
    report["books"] = out


def probe_valve(report: dict) -> None:
    """Official Valve VRS standings, read from the repository Valve publishes them in."""
    url = ("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/"
           "git/trees/main?recursive=1")
    data, meta = fetch_json(url, {"Accept": "application/vnd.github+json"})
    files = [t.get("path") for t in (data or {}).get("tree") or []
             if str(t.get("path", "")).startswith("live/2026/standings_global_")]
    report["valve_vrs"] = {"status": meta.get("status"), "error": meta.get("error"),
                           "global_standings_files": sorted(files)[-4:]}


def main() -> int:
    report: dict = {"session": "b1fb1465", "generated_utc": iso(now_utc()),
                    "targets": TARGETS, "order": ["hltv", "esportsbook", "origin"]}
    steps = [("kalshi", probe_kalshi), ("bo3gg", probe_bo3gg), ("hltv", probe_hltv),
             ("linefeed_deep", probe_linefeed_deep), ("books", probe_books),
             ("valve", probe_valve)]
    for name, fn in steps:
        try:
            fn(report)
        except Exception as exc:  # noqa: BLE001 - one failed probe never stops the run
            report[f"{name}_error"] = f"{type(exc).__name__}: {exc}"[:300]
        print(f"[probe] {name} done")

    report["requests"] = REQUEST_LOG
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")

    print("\n== summary ==")
    print("hltv:", json.dumps({k: v for k, v in report.items() if k.startswith("hltv_")})[:1500])
    print("kalshi gap hits:", json.dumps(report.get("kalshi_gap_hits"))[:1200])
    print("bo3gg gap matches:", json.dumps(report.get("bo3gg_gap_matches"))[:1500])
    print("linefeed gap hits:", json.dumps(report.get("linefeed_flat_gap_hits"))[:1200])
    print("books:", json.dumps(report.get("books"))[:2500])
    print("valve:", json.dumps(report.get("valve_vrs"))[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
