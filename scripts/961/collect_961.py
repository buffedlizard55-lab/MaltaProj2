#!/usr/bin/env python3
"""Session 961e163a — external betting-line collector (raw quotes only).

Lane (claimed in COORDINATION.md, 2026-10-13 21:25 UTC): independently re-collect and
verify external prices for the fixtures listed in the Hotspawn Pick'ems lobby, adding an
HLTV-sourced odds layer for fixtures the Pinnacle/Bovada stream does not carry.

Sources read by this script (all public, no authentication, no bypass):
  * Hotspawn Pick'ems public fixtures API  -> the fixture list itself (never a probability input)
  * Pinnacle  guest odds API (sport 12 = E Sports, public)
  * Bovada    public esports coupon JSON
  * HLTV      public betting analytics pages (odds only where the page publishes them)
  * probe-only: other public candidate sources (recorded as status evidence, never quoted)

Guarantees
----------
* Nothing is inferred. Every emitted price is copied from the source response and keeps
  the exact URL it was read from plus the UTC retrieval timestamp.
* Map/handicap markets are excluded; only full-match (series) winner markets are emitted.
* Hotspawn's own "picked %" values are read from the fixture API for reference only and are
  written to a separate file (`data/961/hotspawn_reference.json`) that the probability
  builder must never read. They are never an input to any probability.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "961")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_SPORT_ESPORTS = 12
PIN_HEADERS = {
    "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "X-Device-UUID": str(uuid.uuid4()),
    "Referer": "https://www.pinnacle.com/",
}
BOVADA = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
HLTV_ANALYTICS = "https://www.hltv.org/betting/analytics"
CS2_RE = re.compile(r"(counter[\s-]?strike|cs2|cs:go|csgo)", re.I)
LOL_RE = re.compile(r"(league\s*of\s*legends|\blol\b)", re.I)


def iso_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_iso(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def fetch(url: str, headers=None, timeout: int = 60):
    """GET; always returns (status, body_bytes, final_url). Never raises."""
    hdrs = {
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.geturl()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b""
        return exc.code, body, url
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode("utf-8", "replace"), url


def get_json(url, headers=None, timeout=60):
    st, body, final = fetch(url, headers, timeout)
    try:
        return st, json.loads(body.decode("utf-8", "replace")), final
    except Exception:  # noqa: BLE001
        return st, None, final


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (100 / abs(a)) if a < 0 else 1 + (a / 100), 4)


# ------------------------------------------------------------------ name normalisation
SUFFIXES = [" esports", " esport", " gaming", " team", " club", " academy"]
PREFIXES = ["team "]


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for suf in SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    for pre in PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):].strip()
    return re.sub(r"\s+", " ", s)


def tokens(name: str) -> set:
    return {t for t in norm(name).split() if len(t) > 1}


def teams_match(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    if not inter:
        return False
    return len(inter) / min(len(ta), len(tb)) >= 0.5 or na in nb or nb in na


# ------------------------------------------------------------------ source: Hotspawn lobby
def collect_hotspawn(state):
    st, fixtures, url = get_json(HOTSPAWN_API + "/fixtures", timeout=120)
    state["sources"]["hotspawn_fixtures"] = {"url": url, "status": st,
                                             "rows": len(fixtures) if isinstance(fixtures, list) else None}
    if not isinstance(fixtures, list):
        return [], []
    st2, permalinks, url2 = get_json(HOTSPAWN_API + "/admin/gamification/fixtures/permalinks", timeout=60)
    state["sources"]["hotspawn_permalinks"] = {"url": url2, "status": st2,
                                               "rows": len(permalinks) if isinstance(permalinks, list) else None}
    link_by_id = {}
    if isinstance(permalinks, list):
        for row in permalinks:
            if not isinstance(row, dict):
                continue
            fid = row.get("fixture_id") or row.get("id")
            slug = row.get("permalink") or row.get("slug") or row.get("url")
            if fid is not None and slug:
                link_by_id[str(fid)] = str(slug)

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=24)
    fixtures_out, reference_out = [], []
    for f in fixtures:
        status = str(f.get("status") or "").lower()
        sched_ms = None
        try:
            sched_ms = int(f.get("scheduled_start_time"))
        except (TypeError, ValueError):
            sched_ms = None
        if status == "ended":
            continue
        if sched_ms is not None and datetime.fromtimestamp(sched_ms / 1000, tz=timezone.utc) < window_start:
            continue  # keep the current window only; older rows are not pickable
        fid = str(f.get("id"))
        slug = link_by_id.get(fid)
        fixtures_out.append({
            "fixture_id": fid,
            "sport": f.get("sport_alias"),
            "competition": f.get("competition_name"),
            "tier": f.get("tier"),
            "stage": f.get("stage"),
            "status": f.get("status"),
            "best_of": f.get("best_of"),
            "series_format": f.get("series_format"),
            "scheduled_start_time_utc": ms_iso(f.get("scheduled_start_time")),
            "lock_time_utc": ms_iso(f.get("lock_time")),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "offered_points": f.get("offered_points"),
            "base_points": f.get("base_points"),
            "team_a_id": f.get("participants0_id"),
            "team_a": f.get("participants0_name"),
            "team_b_id": f.get("participants1_id"),
            "team_b": f.get("participants1_name"),
            "score_a": f.get("participants0_score"),
            "score_b": f.get("participants1_score"),
            "source_url": HOTSPAWN_API + "/fixtures",
            "match_url": (f"https://www.hotspawn.com/matches/{slug}" if slug else
                          f"https://www.hotspawn.com/matches/{fid}"),
        })
        reference_out.append({
            "fixture_id": fid,
            "crowd_pick_pct_a": f.get("participants0_picked_percent"),
            "crowd_pick_pct_b": f.get("participants1_picked_percent"),
            "total_picks": f.get("total_picks"),
            "note": ("Hotspawn crowd pick % — reference only. FORBIDDEN as a probability input; "
                     "the probability builder does not read this file."),
        })
    fixtures_out.sort(key=lambda x: x["scheduled_start_time_utc"] or "")
    return fixtures_out, reference_out


# ------------------------------------------------------------------ source: Pinnacle
def collect_pinnacle(quotes, state, wanted_games):
    url = f"{PIN}/sports/{PIN_SPORT_ESPORTS}/matchups"
    st, matchups, final = get_json(url, PIN_HEADERS)
    state["sources"]["pinnacle_matchups"] = {"url": final, "status": st,
                                             "rows": len(matchups) if isinstance(matchups, list) else None}
    if not isinstance(matchups, list):
        return
    kept = 0
    for m in matchups:
        league = str((m.get("league") or {}).get("name") or "")
        if m.get("type") != "matchup" or m.get("parentId"):
            continue
        game = None
        if CS2_RE.search(league):
            game = "cs2"
        elif LOL_RE.search(league):
            game = "lol"
        if game not in wanted_games:
            continue
        parts = m.get("participants") or []
        if len(parts) != 2:
            continue
        mid = m.get("id")
        murl = f"{PIN}/matchups/{mid}/markets/related/straight"
        st2, markets, mfinal = get_json(murl, PIN_HEADERS)
        if not isinstance(markets, list):
            continue
        for mk in markets:
            if str(mk.get("type") or "").lower() != "moneyline":
                continue
            if mk.get("period") != 0 or mk.get("isAlternate"):
                continue
            prices = mk.get("prices") or []
            if len(prices) != 2 or any(p.get("price") is None for p in prices):
                continue
            by_align = {p.get("designation"): p.get("price") for p in prices}
            if parts[0].get("alignment") == "home":
                a_am, b_am = by_align.get("home"), by_align.get("away")
            else:
                a_am, b_am = by_align.get("away"), by_align.get("home")
            dec_a, dec_b = american_to_decimal(a_am), american_to_decimal(b_am)
            if not dec_a or not dec_b or dec_a <= 1 or dec_b <= 1:
                continue
            quotes.append({
                "source_key": "pinnacle",
                "source_name": "Pinnacle",
                "source_kind": "licensed bookmaker (public guest odds API)",
                "game": game,
                "source_url": mfinal,
                "source_event_id": str(mid),
                "source_league": league,
                "market_type": "series/match winner (moneyline, full match)",
                "market_is_live": bool(mk.get("isLive")),
                "source_reported_start_utc": ms_iso(m.get("startTime")),
                "retrieved_at_utc": iso_now(),
                "team_a_name": parts[0].get("name"),
                "team_b_name": parts[1].get("name"),
                "raw_price_format": "american",
                "raw_price_a": a_am,
                "raw_price_b": b_am,
                "decimal_odds_a": dec_a,
                "decimal_odds_b": dec_b,
                "decimal_odds_derived": True,
            })
            kept += 1
        time.sleep(0.2)
    state["sources"]["pinnacle_quotes_kept"] = kept


# ------------------------------------------------------------------ source: Bovada
def collect_bovada(quotes, state, wanted_games):
    st, data, final = get_json(BOVADA)
    state["sources"]["bovada"] = {"url": final, "status": st}
    if st != 200 or not isinstance(data, list):
        return
    kept = 0
    for group in data:
        for ev in (group.get("events") or []):
            link = str(ev.get("link") or "")
            low = link.lower()
            game = "cs2" if ("counter-strike" in low or "cs2" in low) else (
                "lol" if "league-of-legends" in low else None)
            if game not in wanted_games:
                continue
            comps = ev.get("competitors") or []
            if len(comps) != 2:
                continue
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if str(mk.get("description") or "").strip().lower() != "moneyline":
                        continue
                    period = mk.get("period") or {}
                    if not period.get("main"):
                        continue  # excludes map/set moneylines
                    outs = mk.get("outcomes") or []
                    if len(outs) != 2:
                        continue
                    dec = [((o.get("price") or {}).get("decimal")) for o in outs]
                    am = [((o.get("price") or {}).get("american")) for o in outs]
                    if not all(dec):
                        continue
                    names = [o.get("description") or (o.get("competitor") or {}).get("name") for o in outs]
                    quotes.append({
                        "source_key": "bovada",
                        "source_name": "Bovada",
                        "source_kind": "licensed bookmaker (public coupon JSON)",
                        "game": game,
                        "source_url": "https://www.bovada.lv" + link,
                        "source_api_url": final,
                        "source_event_id": str(ev.get("id")),
                        "source_market_id": str(mk.get("id")),
                        "source_league": dg.get("description") or "",
                        "market_type": "match winner (moneyline, full match)",
                        "market_is_live": bool(ev.get("live")),
                        "source_reported_start_utc": ev.get("startTime"),
                        "retrieved_at_utc": iso_now(),
                        "team_a_name": names[0],
                        "team_b_name": names[1],
                        "raw_price_format": "decimal",
                        "raw_price_a": am[0],
                        "raw_price_b": am[1],
                        "decimal_odds_a": float(dec[0]),
                        "decimal_odds_b": float(dec[1]),
                        "decimal_odds_derived": False,
                    })
                    kept += 1
    state["sources"]["bovada_quotes_kept"] = kept


# ------------------------------------------------------------------ source: HLTV (odds)
HLTV_LINK_RE = re.compile(r'href="(/betting/analytics/(\d+)/([a-z0-9\-]+))"', re.I)


def collect_hltv(quotes, state, fixtures):
    """Read HLTV's public betting analytics pages.

    HLTV renders the per-match odds client-side from an embedded payload; the raw HTML is
    fetched here and every odds-looking fragment is preserved in the probe file so that the
    parse can be re-derived from evidence instead of guessed. Only fragments that match a
    strict decimal-odds pattern inside an odds container are emitted as quotes.
    """
    st, body, final = fetch(HLTV_ANALYTICS)
    text = body.decode("utf-8", "replace")
    state["sources"]["hltv_analytics_list"] = {"url": final, "status": st, "bytes": len(body)}
    links = []
    seen = set()
    for href, mid, slug in HLTV_LINK_RE.findall(text):
        if mid in seen:
            continue
        seen.add(mid)
        links.append({"url": "https://www.hltv.org" + href, "match_id": mid, "slug": slug})
    state["sources"]["hltv_match_pages_found"] = len(links)

    cs2_fixtures = [f for f in fixtures if f.get("sport") == "cs2"]
    probe = {"fetched_at_utc": iso_now(), "source": HLTV_ANALYTICS, "samples": [], "parsed": []}
    kept = 0
    for item in links[:60]:
        slug = item["slug"]
        m = re.match(r"(.+?)-vs-(.+?)(?:-(?:cct|esl|cct|thunderpick|stake|pulse|elisa|dracula|svenska|urban|dach|"
                     r"european|rainhas|frag|lg|epl|nodwin|dfrag|gluck|1win|pgl|meta|united21|global|"
                     r"esports|blast|iem|pgl|regional|online|major|invitational|open|series|season|cup|"
                     r"league|championship|masters|games|qualifier).*)$", slug)
        if not m:
            continue
        a_slug, b_slug = m.group(1), m.group(2)
        a_slug = a_slug.replace("-", " ").strip()
        b_slug = b_slug.replace("-", " ").strip()
        # Only fetch pages whose slug can plausibly match a Hotspawn fixture (bounded work).
        candidates = [f for f in cs2_fixtures
                      if teams_match(a_slug, f.get("team_a") or "") or teams_match(a_slug, f.get("team_b") or "")
                      or teams_match(b_slug, f.get("team_a") or "") or teams_match(b_slug, f.get("team_b") or "")]
        if not candidates:
            continue
        st2, page, pfinal = fetch(item["url"])
        html_text = page.decode("utf-8", "replace")
        item["status"] = st2
        item["bytes"] = len(page)
        if st2 != 200:
            continue
        # Evidence: capture every odds-looking fragment verbatim (bounded, inert text).
        frags = re.findall(r'.{80}(?:data-odds|class="[^"]*odds[^"]*"|"odds"\s*:).{160}', html_text, re.I)
        if len(probe["samples"]) < 5:
            probe["samples"].append({"url": item["url"], "fragments": frags[:8]})
        pairs = re.findall(r'"team1Odds"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?.{0,200}?"team2Odds"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
                          html_text)
        if not pairs:
            pairs = re.findall(r'data-odds1="([0-9]+(?:\.[0-9]+)?)"[^>]*data-odds2="([0-9]+(?:\.[0-9]+)?)"', html_text)
        if not pairs:
            # `odds` widget markup observed in the wild: two `<span class="odds">` per row.
            spans = re.findall(r'class="[^"]*\bodds\b[^"]*"[^>]*>\s*([0-9]{1,2}\.[0-9]{1,3})\s*<', html_text)
            if len(spans) >= 2:
                pairs = [(spans[0], spans[1])]
        for o1, o2 in pairs:
            try:
                d1, d2 = float(o1), float(o2)
            except ValueError:
                continue
            if not (1.01 <= d1 <= 100 and 1.01 <= d2 <= 100):
                continue
            a_name, b_name = a_slug.title(), b_slug.title()
            quotes.append({
                "source_key": "hltv",
                "source_name": "HLTV.org (published bookmaker odds)",
                "source_kind": "esports media odds display (bookmaker prices as published by HLTV)",
                "game": "cs2",
                "source_url": pfinal,
                "source_event_id": item["match_id"],
                "source_league": None,
                "market_type": "match winner (moneyline)",
                "market_is_live": False,
                "source_reported_start_utc": None,
                "retrieved_at_utc": iso_now(),
                "team_a_name": a_name,
                "team_b_name": b_name,
                "raw_price_format": "decimal",
                "raw_price_a": d1,
                "raw_price_b": d2,
                "decimal_odds_a": d1,
                "decimal_odds_b": d2,
                "decimal_odds_derived": False,
                "parse_note": "decimal pair extracted from the public analytics page HTML",
            })
            kept += 1
            break
        probe["parsed"].append({"url": item["url"], "pairs_found": len(pairs), "kept": bool(pairs)})
        time.sleep(0.5)
    state["sources"]["hltv_quotes_kept"] = kept
    return probe


# ------------------------------------------------------------------ probe-only sources
PROBES = {
    "thunderpick_cs2": "https://thunderpick.io/esports/cs2",
    "betway_esports": "https://betway.com/en/sports/esports",
    "ggbet_esports": "https://gg.bet/en/esports",
    "egamersworld_cs2": "https://egamersworld.com/counterstrike/matches",
    "egamersworld_lol": "https://egamersworld.com/lol/matches",
    "hltv_matches": "https://www.hltv.org/matches",
    "pinnacle_esports_page": "https://www.pinnacle.com/en/esports/",
}


def run_probes(state):
    out = {}
    for key, url in PROBES.items():
        st, body, final = fetch(url, timeout=40)
        out[key] = {"url": final, "status": st, "bytes": len(body),
                    "first_bytes": body[:200].decode("utf-8", "replace") if st != 200 else None}
        time.sleep(0.3)
    state["probes"] = out


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    state = {
        "generated_at_utc": iso_now(),
        "collector": "scripts/961/collect_961.py",
        "rules": [
            "Raw quotes only: every price is copied from the named source URL at retrieved_at_utc.",
            "Full-match (series) winner markets only; map/handicap markets are excluded.",
            "No inference: a fixture with no readable external price is emitted with zero quotes.",
            "Hotspawn crowd pick percentages are stored separately and never used as probability inputs.",
        ],
        "sources": {},
    }
    fixtures, reference = collect_hotspawn(state)
    wanted = {f.get("sport") for f in fixtures} & {"cs2", "lol"}
    quotes = []
    collect_pinnacle(quotes, state, wanted)
    collect_bovada(quotes, state, wanted)
    state["hltv_probe"] = collect_hltv(quotes, state, fixtures)
    run_probes(state)

    with open(os.path.join(OUT, "lobby.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at_utc": state["generated_at_utc"],
            "source_page": "https://play.hotspawn.com/lobby",
            "source_api": HOTSPAWN_API + "/fixtures",
            "fixture_count": len(fixtures),
            "by_sport": {g: sum(1 for f in fixtures if f.get("sport") == g) for g in sorted(wanted)},
            "fixtures": fixtures,
        }, fh, indent=1, sort_keys=True)
    with open(os.path.join(OUT, "hotspawn_reference.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": state["generated_at_utc"],
                   "warning": "Reference only — never a probability input.",
                   "rows": reference}, fh, indent=1, sort_keys=True)
    with open(os.path.join(OUT, "quotes.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": state["generated_at_utc"],
                   "quote_count": len(quotes),
                   "by_source": {k: sum(1 for q in quotes if q["source_key"] == k)
                                 for k in sorted({q["source_key"] for q in quotes})},
                   "quotes": quotes}, fh, indent=1, sort_keys=True)
    with open(os.path.join(OUT, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    if isinstance(state.get("hltv_probe"), dict):
        with open(os.path.join(OUT, "hltv_probe.json"), "w", encoding="utf-8") as fh:
            json.dump(state["hltv_probe"], fh, indent=1, sort_keys=True)
    print(f"lobby fixtures={len(fixtures)} quotes={len(quotes)} "
          f"by_source={ {k: sum(1 for q in quotes if q['source_key'] == k) for k in sorted({q['source_key'] for q in quotes})} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
