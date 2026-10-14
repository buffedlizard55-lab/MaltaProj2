#!/usr/bin/env python3
"""T-COVERAGE-FULL collector (session 6ddde224) — run on a host with general internet access.

What it collects (each with the HTTP metadata needed to audit it):

1. **HotSpawn Pick'ems lobby** — the public `/api/v1/fixtures` response used by the lobby page and
   the ids the lobby page itself renders, plus the lobby's own counters. HotSpawn is used for
   *fixture discovery only*: the lobby's crowd "picked %" is stored as reference and is never read
   by any probability function (`tests/test_coverage_6ddde224.py` asserts this).
2. **bo3.gg public match feed** (`/api/v1/matches`) — an esports results/odds site that republishes
   two-sided Thunderpick moneyline coefficients together with team names and a UTC start time.
   Upcoming records become **market quotes**; finished records become the **results corpus** used to
   fit the originated model (and, where the feed carries them, the closing prices used as the
   market benchmark for the model's calibration table).
3. **Kalshi exchange** (`KXCS2GAME`) — two-sided bid/ask for CS2 match markets, recorded as an
   exchange reference with its spread, never averaged with bookmaker prices.
4. **Valve CS2 Regional Standings** — official rating input for the VRS-based originated estimate.
5. **The repository's own hourly live-coverage artifact** (`data/live/quotes.json`, session
   3cd9787c) — read-only, attributed per quote, so this pipeline does not duplicate requests to
   Pinnacle/Bovada/LineFeed. If the artifact is missing or stale it is recorded as unavailable and
   the board simply has fewer market sources (never a fabricated one).

Usage: python3 scripts/coverage/collect_coverage.py [--outdir data/coverage] [--corpus-days 90]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cov_core import (  # noqa: E402
    canon_team, fetch, fetch_json, json_dump, now_iso, now_utc, parse_any, parse_ms,
    save_sample, sleep, to_iso,
)

ROOT = Path(__file__).resolve().parents[2]
LOBBY_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
BO3G_API = "https://bo3.gg/api/v1/matches"
KALSHI_EVENTS = ("https://api.elections.kalshi.com/trade-api/v2/events"
                 "?series_ticker=KXCS2GAME&status=open&limit=200&with_nested_markets=true")
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_DIR = "live/2026"
VRS_REGIONS = ("global", "europe", "americas", "asia")
LIVE_QUOTES = ROOT / "data/live/quotes.json"
LIVE_BOARD = ROOT / "data/live/board.json"

KEEP_PAST_DAYS = 10
KEEP_FUTURE_DAYS = 21
BO3G_MAX_UPCOMING_PAGES = 60
CORPUS_MAX_PAGES = 500
CORPUS_CAP_MATCHES = 8000
CORPUS_REFRESH_DAYS = 7


# ----------------------------------------------------------------------------- HotSpawn lobby
def fixtures_from_live_artifact(log: dict) -> list[dict]:
    """Fallback inventory: the repository's own hourly live-coverage snapshot (session 3cd9787c).

    Used only when HotSpawn cannot be reached from the runner. The provenance of every row is
    rewritten to name that artifact, so the board never claims a direct HotSpawn read it did not make.
    """
    path = ROOT / "data/live/fixtures.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    rows = payload.get("fixtures") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    log["hotspawn_fixtures_fallback"] = {
        "path": str(path.relative_to(ROOT)),
        "generated_at_utc": payload.get("generated_at_utc"),
        "rows": len(rows),
        "reason": "direct HotSpawn request failed from this runner",
    }
    out = []
    for r in rows:
        out.append({
            "fixture_id": str(r.get("fixture_id")), "game": r.get("game"),
            "sport_alias": r.get("sport_alias"), "competition": r.get("competition"),
            "competition_id": r.get("competition_id"), "tier": r.get("tier"), "stage": r.get("stage"),
            "status": r.get("status"), "start_time_utc": r.get("start_time_utc"),
            "lock_time_utc": r.get("lock_time_utc"), "lock_offset_sec": r.get("lock_offset_sec"),
            "best_of": r.get("best_of"), "team_a": r.get("team_a"), "team_b": r.get("team_b"),
            "team_a_id": r.get("team_a_id"), "team_b_id": r.get("team_b_id"),
            "listed_in_lobby": bool(r.get("listed_in_lobby_hint")),
            "hotspawn_crowd_pct_reference_only": r.get("hotspawn_pick_pct_reference_only"),
            "source": {
                "api": r.get("source", {}).get("api") or f"{LOBBY_API}/fixtures",
                "page": r.get("source", {}).get("page") or LOBBY_PAGE,
                "match": r.get("source", {}).get("hotspawn_match_url")
                         or f"https://www.hotspawn.com/matches/{r.get('fixture_id')}",
                "inventory_via": str(path.relative_to(ROOT)),
            },
        })
    return out


def collect_fixtures(log: dict, sample_dir: Path | None) -> tuple[list[dict], dict]:
    url = f"{LOBBY_API}/fixtures"
    data, meta = fetch_json(url, {"Referer": LOBBY_PAGE}, timeout=90)
    rows = data if isinstance(data, list) else []
    log["hotspawn_fixtures"] = {**meta, "rows": len(rows)}
    if not rows:
        fallback = fixtures_from_live_artifact(log)
        if fallback:
            return [r for r in fallback if _in_window(r, log)], {}

    # The lobby page renders its fixture ids into the Angular transfer state; read them from the
    # public HTML (never from an authenticated/admin endpoint).
    page = fetch(LOBBY_PAGE, {"Accept": "text/html"}, timeout=60)
    listed_ids: list[str] = []
    lobby_counters: dict = {}
    text = page["body"].decode("utf-8", "replace") if page["body"] else ""
    if page["status"] == 200 and text:
        save_sample(sample_dir, "lobby_page.txt", text, limit=600_000)
        listed_ids = sorted({m for m in re.findall(r'"id"\s*:\s*"(\d{5,9})"', text)})
        for pattern, key in ((r"This week\s*</?[^>]*>\s*(\d+)\s*matches this week", "matches_this_week"),
                             (r"All tiers\s*\((\d+)\)", "all_tiers"),
                             (r"All tournaments\s*\((\d+)\)", "all_tournaments")):
            found = re.search(pattern, text, re.I)
            if found:
                lobby_counters[key] = int(found.group(1))
    log["lobby_page"] = {k: v for k, v in page.items() if k != "body"}
    log["lobby_page"]["listed_ids_found"] = len(listed_ids)
    log["lobby_page"]["counters"] = lobby_counters

    if not listed_ids:
        # the lobby page could not be read: reuse the listing hint recorded by the fallback / by
        # the live snapshot instead of inventing a second definition of "listed"
        pass
    listed = set(listed_ids)
    now = now_utc()
    lo, hi = now - timedelta(days=KEEP_PAST_DAYS), now + timedelta(days=KEEP_FUTURE_DAYS)
    out: list[dict] = []
    statuses: dict[str, int] = {}
    sports: dict[str, int] = {}
    for f in rows:
        if not isinstance(f, dict):
            continue
        sport = str(f.get("sport_alias") or "").casefold()
        sports[sport] = sports.get(sport, 0) + 1
        status = str(f.get("status") or "")
        statuses[status] = statuses.get(status, 0) + 1
        start = parse_ms(f.get("scheduled_start_time"))
        fid = str(f.get("id"))
        must_keep = fid in listed
        if not must_keep and (start is None or not lo <= start <= hi):
            continue
        out.append({
            "fixture_id": fid,
            "game": "CS2" if sport == "cs2" else ("LoL" if sport == "lol" else sport or None),
            "sport_alias": sport,
            "competition": f.get("competition_name"),
            "competition_id": str(f.get("competition_id") or ""),
            "tier": f.get("tier"),
            "stage": f.get("stage"),
            "status": status,
            "start_time_utc": to_iso(start),
            "lock_time_utc": to_iso(parse_ms(f.get("lock_time"))),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "best_of": f.get("best_of"),
            "team_a": f.get("participants0_name"),
            "team_b": f.get("participants1_name"),
            "team_a_id": str(f.get("participants0_id") or ""),
            "team_b_id": str(f.get("participants1_id") or ""),
            "listed_in_lobby": must_keep,
            # Reference only — see the module docstring and the guard test.
            "hotspawn_crowd_pct_reference_only": {
                "team_a": f.get("participants0_picked_percent"),
                "team_b": f.get("participants1_picked_percent"),
                "note": ("HotSpawn crowd Pick'ems percentage. Published for human reference only; "
                         "no probability or estimate in this pipeline reads this object."),
            },
            "source": {
                "api": url,
                "page": LOBBY_PAGE,
                "match": f"https://www.hotspawn.com/matches/{fid}",
            },
        })
    log["hotspawn_fixtures"].update({
        "status_counts_all_rows": statuses,
        "sport_counts_all_rows": sports,
        "kept": len(out),
        "kept_listed": sum(1 for r in out if r["listed_in_lobby"]),
        "window": {"from": to_iso(lo), "to": to_iso(hi),
                   "rule": f"start within -{KEEP_PAST_DAYS}d..+{KEEP_FUTURE_DAYS}d, or listed by the lobby page"},
    })
    return out, {"listed_ids": listed_ids, "counters": lobby_counters}


# --------------------------------------------------------------------------------------- bo3.gg
def bo3g_fetch_page(url: str) -> dict:
    """Fetch one bo3.gg page; safe to call from several threads at once."""
    data, meta = fetch_json(url, {"Accept": "application/json", "Referer": "https://bo3.gg/"}, timeout=45)
    results = (data or {}).get("results") if isinstance(data, dict) else None
    return {"url": url, "meta": meta, "results": results if isinstance(results, list) else []}


def bo3g_fetch_pages(url_fn, pages: list[int], workers: int = 5) -> dict[int, dict]:
    """Fetch several pages concurrently — the bo3.gg feed pages 10 records at a time, so a results
    corpus needs hundreds of requests and sequential fetching would not fit an hourly job."""
    import concurrent.futures as cf
    out: dict[int, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(bo3g_fetch_page, url_fn(page)): page for page in pages}
        for future in cf.as_completed(futures):
            page = futures[future]
            try:
                out[page] = future.result()
            except Exception as exc:  # noqa: BLE001
                out[page] = {"url": url_fn(page), "meta": {"error": f"{type(exc).__name__}: {exc}"},
                             "results": []}
    return out


def bo3g_get(url: str, log: dict, sample_dir: Path | None, name: str) -> list[dict]:
    data, meta = fetch_json(url, {"Accept": "application/json", "Referer": "https://bo3.gg/"}, timeout=60)
    log.setdefault("bo3gg", {})[name] = {**meta, "url": url}
    results = (data or {}).get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        log["bo3gg"][name]["error"] = log["bo3gg"][name].get("error") or "no results array"
        return []
    log["bo3gg"][name]["results"] = len(results)
    # keep one bounded raw sample per feed so the evidence stays reviewable and small
    if sample_dir is not None and results and name.endswith("p1"):
        save_sample(sample_dir, f"{name}.json", {"url": url, "results": results[:3]}, limit=90_000)
    return results


def bo3g_quote_from_match(m: dict, log: dict) -> dict | None:
    """Build a two-sided market quote from one bo3.gg match record, or None when unusable."""
    bet = m.get("bet_updates")
    if not isinstance(bet, dict):
        return None
    t1, t2 = bet.get("team_1"), bet.get("team_2")
    if not isinstance(t1, dict) or not isinstance(t2, dict):
        return None
    try:
        dec_a, dec_b = float(t1.get("coeff")), float(t2.get("coeff"))
    except (TypeError, ValueError):
        return None
    if not (1.0 < dec_a < 1000.0 and 1.0 < dec_b < 1000.0):
        return None
    if t1.get("active") is False or t2.get("active") is False:
        return None
    name_a, name_b = t1.get("name"), t2.get("name")
    if not name_a or not name_b:
        return None
    status = str(m.get("status") or "")
    return {
        "source_key": "bo3gg_thunderpick",
        "source_name": "Thunderpick prices via bo3.gg",
        "source_kind": "licensed bookmaker price republished by an esports results site",
        "provider": bet.get("provider"),
        "provider_market_url": bet.get("path"),
        "market_type": "match winner (moneyline, full match)",
        "market_is_live": status in ("live", "playing"),
        "market_status": status,
        "source_event_id": str(m.get("id")),
        "source_public_url": f"https://bo3.gg/matches/{m.get('slug')}",
        "source_api_url": f"{BO3G_API}?filter[matches.id][in]={m.get('id')}",
        "retrieved_at_utc": now_iso(),
        "start_time_utc": to_iso(parse_any(str(m.get("start_date")))),
        "start_time_raw": m.get("start_date"),
        "team_a_name": str(name_a),
        "team_b_name": str(name_b),
        "team_a_external_id": str(t1.get("team_id") or ""),
        "team_b_external_id": str(t2.get("team_id") or ""),
        "decimal_odds_a": dec_a,
        "decimal_odds_b": dec_b,
        "max_coeff_a": t1.get("max_coeff"),
        "max_coeff_b": t2.get("max_coeff"),
        "best_of": m.get("bo_type"),
        "tier": m.get("tier"),
        "confidence": "market",
        "raw_price_format": "decimal",
    }


def collect_bo3gg(quotes: list[dict], log: dict, sample_dir: Path | None, budget_s: float = 120.0) -> None:
    """Upcoming matches -> market quotes (two-sided Thunderpick prices republished by bo3.gg)."""
    started = time.time()
    base = ("?filter[matches.status][in]=upcoming&filter[matches.discipline_id][in]=1"
            "&sort=start_date&limit=10&page=")
    horizon = now_utc() + timedelta(days=KEEP_FUTURE_DAYS)
    entry: dict = {"pages_read": 0, "quotes": 0, "errors": []}
    log.setdefault("bo3gg", {})["upcoming"] = entry
    page = 1
    while page <= BO3G_MAX_UPCOMING_PAGES and time.time() - started < budget_s:
        batch = bo3g_fetch_pages(lambda p: f"{BO3G_API}{base}{p}", list(range(page, page + 5)))
        stop = False
        for number in sorted(batch):
            payload = batch[number]
            if payload["meta"].get("error") or payload["meta"].get("status") != 200:
                entry["errors"].append({number: payload["meta"].get("error") or payload["meta"].get("status")})
                continue
            if not payload["results"]:
                stop = True
                continue
            entry["pages_read"] += 1
            if number == 1 and sample_dir is not None:
                save_sample(sample_dir, "bo3gg_upcoming_p1.json",
                            {"url": payload["url"], "results": payload["results"][:3]}, limit=90_000)
            for m in payload["results"]:
                start = parse_any(str(m.get("start_date")))
                if start is None or start <= horizon:
                    stop = False
                quote = bo3g_quote_from_match(m, log)
                if quote:
                    quotes.append(quote)
                    entry["quotes"] += 1
        if stop:
            break
        page += 5
    entry["seconds"] = round(time.time() - started, 1)


def collect_bo3gg_corpus(log: dict, sample_dir: Path | None, corpus_days: int,
                         existing: dict | None, budget_s: float = 300.0) -> dict:
    """Distilled finished-match corpus (model input + closing-price benchmark)."""
    if existing and existing.get("generated_at_utc"):
        age = (now_utc() - (parse_any(existing["generated_at_utc"]) or now_utc())).days
        if age < CORPUS_REFRESH_DAYS and existing.get("matches"):
            log.setdefault("bo3gg", {})["corpus"] = {"reused": True, "age_days": age,
                                                     "matches": len(existing["matches"])}
            return existing
    started = time.time()
    base = ("?filter[matches.status][in]=finished&filter[matches.discipline_id][in]=1"
            "&sort=-start_date&limit=10&page=")
    cutoff = now_utc() - timedelta(days=corpus_days)
    matches: list[dict] = []
    names: dict[str, str] = {}
    entry: dict = {"reused": False, "pages_read": 0, "errors": [], "stopped": None}
    log.setdefault("bo3gg", {})["corpus"] = entry
    page = 1
    while page <= CORPUS_MAX_PAGES:
        if time.time() - started > budget_s:
            entry["stopped"] = f"time budget {budget_s}s reached"
            break
        batch = bo3g_fetch_pages(lambda p: f"{BO3G_API}{base}{p}", list(range(page, page + 5)))
        done = False
        for number in sorted(batch):
            payload = batch[number]
            if payload["meta"].get("error") or payload["meta"].get("status") != 200:
                entry["errors"].append({number: payload["meta"].get("error") or payload["meta"].get("status")})
                continue
            if not payload["results"]:
                done = True
                continue
            entry["pages_read"] += 1
            if number == 1 and sample_dir is not None:
                save_sample(sample_dir, "bo3gg_finished_p1.json",
                            {"url": payload["url"], "results": payload["results"][:3]}, limit=90_000)
            for m in payload["results"]:
                start = parse_any(str(m.get("start_date")))
                if start is None or start < cutoff:
                    done = True
                    continue
                winner, loser = m.get("winner_team_id"), m.get("loser_team_id")
                a, b = m.get("team1_id"), m.get("team2_id")
                if not winner or not a or not b or str(winner) not in (str(a), str(b)):
                    continue
                rec = {"id": m.get("id"), "d": to_iso(start), "a": str(a), "b": str(b),
                       "w": str(winner), "bo": m.get("bo_type"), "t": m.get("tier")}
                bet = m.get("bet_updates") or {}
                t1, t2 = (bet.get("team_1") or {}), (bet.get("team_2") or {})
                try:
                    if t1.get("coeff") and t2.get("coeff"):
                        rec["oa"], rec["ob"] = float(t1["coeff"]), float(t2["coeff"])
                    for side, tid in ((t1, a), (t2, b)):
                        if side.get("name") and tid:
                            names[str(tid)] = str(side["name"])
                except (TypeError, ValueError):
                    pass
                matches.append(rec)
                if len(matches) >= CORPUS_CAP_MATCHES:
                    done = True
                    break
        if done:
            break
        page += 5
    entry.update({"matches": len(matches), "team_names": len(names),
                  "seconds": round(time.time() - started, 1), "window_days": corpus_days})
    corpus = {
        "generated_at_utc": now_iso(),
        "source": BO3G_API,
        "source_public": "https://bo3.gg/matches/finished",
        "window_days": corpus_days,
        "note": ("Distilled finished CS2 matches: id, UTC start, team ids, winner id, best-of, tier, "
                 "and the last bookmaker price pair published by bo3.gg for that match (used only as "
                 "the market benchmark on the method page)."),
        "pages_read": entry["pages_read"],
        "stopped_reason": entry["stopped"],
        "matches": matches,
        "team_names": names,
    }
    return corpus


# ---------------------------------------------------------------------------------------- Kalshi
def collect_kalshi(events: list[dict], log: dict, sample_dir: Path | None) -> None:
    """Two-sided exchange books for CS2 match markets (published only inside the spread limit)."""
    data, meta = fetch_json(KALSHI_EVENTS, {"Accept": "application/json"}, timeout=60)
    log["kalshi"] = {**meta}
    evs = (data or {}).get("events") if isinstance(data, dict) else None
    if not isinstance(evs, list):
        log["kalshi"]["error"] = log["kalshi"].get("error") or "no events array"
        return
    log["kalshi"]["events"] = len(evs)
    written = 0
    for ev in evs:
        ticker = str(ev.get("event_ticker") or "")
        if not ticker.startswith("KXCS2GAME-"):
            continue
        markets = ev.get("markets") or []
        sides = []
        rules = ""
        expected_end = None
        for mk in markets:
            def num(key):
                try:
                    return float(mk.get(key))
                except (TypeError, ValueError):
                    return None
            rules = rules or str(mk.get("rules_primary") or "")
            expected_end = expected_end or mk.get("expected_expiration_time")
            sides.append({"ticker": mk.get("ticker"), "team": mk.get("yes_sub_title"),
                          "yes_bid": num("yes_bid_dollars"), "yes_ask": num("yes_ask_dollars"),
                          "last_price": num("last_price_dollars"), "bid_size": num("yes_bid_size_fp"),
                          "ask_size": num("yes_ask_size_fp"), "volume": num("volume_fp"),
                          "open_interest": num("open_interest_fp"), "status": mk.get("status")})
        if len(sides) != 2 or not all(s.get("team") for s in sides):
            continue
        events.append({
            "source_key": "kalshi", "source_name": "Kalshi (regulated exchange)",
            "source_kind": "exchange (reference; never averaged with bookmaker prices)",
            "event_ticker": ticker, "title": ev.get("title"), "sub_title": ev.get("sub_title"),
            "source_public_url": f"https://kalshi.com/markets/{ticker.split('-')[0].lower()}",
            "source_api_url": KALSHI_EVENTS, "retrieved_at_utc": now_iso(),
            # NOTE: Kalshi's own occurrence/expiration timestamps describe the market, not the
            # kickoff; the builder parses the kickoff out of `rules_primary` instead.
            "expected_end_utc": expected_end, "rules_primary": rules, "sides": sides,
        })
        written += 1
    log["kalshi"]["cs2_events_written"] = written
    if sample_dir is not None:
        save_sample(sample_dir, "kalshi_cs2_events.json",
                    [{k: v for k, v in e.items() if k != "rules_primary"} for e in events],
                    limit=200_000)


# --------------------------------------------------------------------------- Valve VRS ratings
def vrs_rows(markdown: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        standing, points, team = cells[0], cells[1], cells[2]
        if not standing.isdigit() or not re.fullmatch(r"\d+", points or ""):
            continue
        key = canon_team(team)
        if key:
            out[key] = {"team": team, "standings": int(standing), "points": int(points),
                        "roster": cells[3] if len(cells) > 3 else ""}
    return out


def collect_vrs(log: dict, sample_dir: Path | None) -> dict:
    tree, meta = fetch_json(f"https://api.github.com/repos/{VRS_REPO}/git/trees/main?recursive=1",
                            {"Accept": "application/vnd.github+json"}, timeout=90)
    log["valve_vrs_tree"] = meta
    latest: dict[str, str] = {}
    nodes = (tree or {}).get("tree") if isinstance(tree, dict) else None
    if isinstance(nodes, list):
        for node in nodes:
            path = str((node or {}).get("path") or "")
            m = re.match(rf"{VRS_DIR}/standings_([a-z]+)_(\d{{4}}_\d{{2}}_\d{{2}})\.md$", path)
            if m and m.group(1) in VRS_REGIONS:
                region, date = m.group(1), m.group(2)
                if region not in latest or date > latest[region]:
                    latest[region] = date
    ratings: dict[str, dict] = {}
    files: dict[str, dict] = {}
    for region in VRS_REGIONS:
        date = latest.get(region)
        if not date:
            continue
        api_url = (f"https://api.github.com/repos/{VRS_REPO}/contents/{VRS_DIR}/"
                   f"standings_{region}_{date}.md")
        blob, meta2 = fetch_json(api_url, {"Accept": "application/vnd.github+json"}, timeout=90)
        text = None
        if isinstance(blob, dict) and blob.get("content"):
            try:
                text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                text = None
        files[region] = {**{k: v for k, v in meta2.items() if k != "body"}, "snapshot": date,
                         "api_url": api_url,
                         "raw_url": (f"https://raw.githubusercontent.com/{VRS_REPO}/main/"
                                     f"{VRS_DIR}/standings_{region}_{date}.md")}
        if not text:
            continue
        rows = vrs_rows(text)
        files[region]["teams_parsed"] = len(rows)
        if sample_dir is not None and region == "global":
            save_sample(sample_dir, f"vrs_{region}_{date}.md", text, limit=250_000)
        for key, rec in rows.items():
            cur = ratings.get(key)
            if cur is None or rec["points"] > cur["points"]:
                ratings[key] = {**rec, "region": region, "snapshot": date,
                                "source_url": api_url,
                                "also_regions": [region] if cur else []}
            elif region not in cur.get("also_regions", []):
                cur.setdefault("also_regions", []).append(region)
        sleep(0.3)
    log["valve_vrs"] = {"snapshots": latest, "files": files, "teams": len(ratings)}
    return {"generated_at_utc": now_iso(), "source": f"https://github.com/{VRS_REPO}",
            "snapshots": latest, "files": files, "ratings": ratings}


# ------------------------------------------------------- read-only live-pipeline input artifact
def collect_supplementary(log: dict) -> dict:
    entry: dict = {"path": str(LIVE_QUOTES.relative_to(ROOT)), "available": False}
    board_meta = {}
    if LIVE_BOARD.is_file():
        try:
            board = json.loads(LIVE_BOARD.read_text())
            board_meta = {"generated_at_utc": board.get("generated_at_utc"),
                          "rows": len(board.get("rows") or []),
                          "source": "data/live/board.json (session 3cd9787c)"}
        except json.JSONDecodeError:
            board_meta = {"error": "board.json not parseable"}
    entry["board"] = board_meta
    if not LIVE_QUOTES.is_file():
        entry["reason"] = "artifact not present"
        log["live_pipeline_quotes"] = entry
        return entry
    try:
        payload = json.loads(LIVE_QUOTES.read_text())
    except json.JSONDecodeError as exc:
        entry["reason"] = f"not parseable: {exc}"
        log["live_pipeline_quotes"] = entry
        return entry
    quotes = payload.get("quotes") if isinstance(payload, dict) else payload
    if not isinstance(quotes, list):
        entry["reason"] = "no quotes array"
        log["live_pipeline_quotes"] = entry
        return entry
    generated = payload.get("generated_at_utc") if isinstance(payload, dict) else None
    age = None
    if generated:
        parsed = parse_any(generated)
        if parsed:
            age = round((now_utc() - parsed).total_seconds() / 3600.0, 2)
    entry.update({"available": True, "generated_at_utc": generated, "age_hours": age,
                  "quotes_read": len(quotes)})
    log["live_pipeline_quotes"] = entry
    return {"meta": entry, "quotes": quotes}


def _in_window(row: dict, log: dict) -> bool:
    """Keep CS2 fixtures within the collection window, plus everything the lobby is listing."""
    if row.get("game") not in ("CS2", "LoL"):
        row["game"] = row.get("game") or "CS2"
    start = parse_any(row.get("start_time_utc"))
    now = now_utc()
    lo, hi = now - timedelta(days=KEEP_PAST_DAYS), now + timedelta(days=KEEP_FUTURE_DAYS)
    if row.get("listed_in_lobby"):
        return True
    return bool(start and lo <= start <= hi)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(ROOT / "data/coverage"))
    parser.add_argument("--corpus-days", type=int, default=90)
    parser.add_argument("--skip-corpus", action="store_true")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    sample_dir = outdir / "samples"
    log: dict = {"generated_at_utc": now_iso(), "collector": "scripts/coverage/collect_coverage.py"}

    fixtures, lobby = collect_fixtures(log, sample_dir)
    json_dump(outdir / "fixtures.json", {
        "generated_at_utc": now_iso(), "lobby": lobby, "fixtures": fixtures,
        "source": {"api": f"{LOBBY_API}/fixtures", "page": LOBBY_PAGE},
    })

    quotes: list[dict] = []
    collect_bo3gg(quotes, log, sample_dir)

    events: list[dict] = []
    collect_kalshi(events, log, sample_dir)

    existing_corpus = None
    corpus_path = outdir / "corpus.json"
    if corpus_path.is_file():
        try:
            existing_corpus = json.loads(corpus_path.read_text())
        except json.JSONDecodeError:
            existing_corpus = None
    corpus = existing_corpus or {"matches": []}
    if not args.skip_corpus:
        corpus = collect_bo3gg_corpus(log, sample_dir, args.corpus_days, existing_corpus)
    json_dump(corpus_path, corpus)

    supplementary = collect_supplementary(log)
    for q in supplementary.get("quotes", []):
        if not isinstance(q, dict) or q.get("confidence") != "market":
            continue
        quotes.append({
            "source_key": q.get("source_key"),
            "source_name": q.get("source_name"),
            "source_kind": q.get("source_kind"),
            "provider": q.get("source_key"),
            "market_type": q.get("market_type"),
            "market_is_live": bool(q.get("market_is_live")),
            "market_status": q.get("market_status"),
            "source_event_id": q.get("source_event_id"),
            "source_public_url": q.get("source_public_url"),
            "source_api_url": q.get("source_api_url"),
            "retrieved_at_utc": q.get("retrieved_at_utc"),
            "start_time_utc": q.get("start_time_utc"),
            "team_a_name": q.get("team_a_name"),
            "team_b_name": q.get("team_b_name"),
            "decimal_odds_a": q.get("decimal_odds_a"),
            "decimal_odds_b": q.get("decimal_odds_b"),
            "best_of": None,
            "tier": None,
            "confidence": "market",
            "raw_price_format": q.get("raw_price_format"),
            "via": "data/live/quotes.json (session 3cd9787c, read-only)",
        })

    json_dump(outdir / "quotes.json", {
        "generated_at_utc": now_iso(),
        "note": ("External non-HotSpawn two-sided match-winner prices. 'bo3gg_thunderpick*' entries "
                 "were collected by this session directly; entries carrying 'via' were read from the "
                 "repository's own hourly live-coverage artifact and are attributed to it."),
        "quotes": quotes,
    })
    json_dump(outdir / "external_events.json", {"generated_at_utc": now_iso(), "events": events})

    ratings = collect_vrs(log, sample_dir)
    json_dump(outdir / "ratings.json", ratings)

    log["ok"] = bool(fixtures)
    json_dump(outdir / "collection_log.json", log)
    (outdir / "collector_run.log").write_text(
        "coverage collector run\n" + json.dumps({k: log.get(k) for k in
        ("generated_at_utc", "hotspawn_fixtures", "hotspawn_fixtures_fallback", "bo3gg", "kalshi",
         "valve_vrs", "live_pipeline_quotes", "lobby_page", "ok")}, indent=1) + "\n", encoding="utf-8")
    print(f"fixtures={len(fixtures)} quotes={len(quotes)} kalshi_events={len(events)} "
          f"corpus_matches={len(corpus.get('matches') or [])} vrs_teams={len(ratings.get('ratings') or {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
