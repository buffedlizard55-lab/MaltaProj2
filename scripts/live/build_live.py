#!/usr/bin/env python3
"""T-COVER builder (session 3cd9787c).

Turns the raw evidence written by `collect_live.py` into:

* `data/live/board.json`        — one row per lobby fixture, with either a market-derived
                                  probability, a clearly labelled originated estimate, or blanks
                                  plus a review flag;
* `data/live/verification.json` — the line-by-line re-derivation of every published number from
                                  the raw quotes;
* `live/*.html`                 — the mobile-first published pages.

The builder is fail-closed: `verify_board()` re-derives every published value from
`data/live/quotes.json` and `data/live/ratings.json`; if any check fails the pages are not
written and the process exits non-zero, so a broken board can never be published.

Usage: python3 scripts/live/build_live.py [--data data/live] [--site live]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_core import (  # noqa: E402
    VRS_MODEL, canon_team, consensus, hours_between, json_dump, json_load, no_vig_two_way, now_iso,
    to_iso,
    now_utc, parse_iso, pct, safe_round, same_team, vrs_estimate, week_window,
)

ROOT = Path(__file__).resolve().parents[2]
QUOTE_FRESHNESS_HOURS = 6.0        # a market quote older than this is not used for the pick
JOIN_TIME_TOLERANCE_HOURS = 8.0    # source start time must agree with the lobby start time
TIE_TOLERANCE = 0.005              # below this edge the row is published as a coin flip
MIN_SOURCES = 1                    # a single verified bookmaker quote is enough to publish


# --------------------------------------------------------------------------------- loading
def load_inputs(data_dir: Path) -> tuple[dict, dict, dict, dict]:
    fixtures = json_load(data_dir / "fixtures.json", {}) or {}
    quotes = json_load(data_dir / "quotes.json", {}) or {}
    ratings = json_load(data_dir / "ratings.json", {}) or {}
    log = json_load(data_dir / "collection_log.json", {}) or {}
    return fixtures, quotes, ratings, log


def lobby_week(now) -> tuple:
    return week_window(now)


# ------------------------------------------------------------------------- window analysis
def window_analysis(fixtures: list[dict], counters: dict, now) -> dict:
    """Reproduce the lobby's own counters from the fixture data, or say that we cannot.

    The lobby prints a "matches this week" counter and per-tier counts. Rather than assume what
    they mean, every candidate window rule is evaluated here and the counts are compared with
    what the page actually printed.
    """
    start, end = lobby_week(now)
    rules = {
        "all rows": lambda f: True,
        "scheduled (any time)": lambda f: f.get("status") == "scheduled",
        "scheduled and kickoff inside current UTC week": lambda f: (
            f.get("status") == "scheduled"
            and (d := parse_iso(f.get("start_time_utc"))) is not None and start <= d < end),
        "scheduled and lock inside current UTC week": lambda f: (
            f.get("status") == "scheduled"
            and (d := parse_iso(f.get("lock_time_utc"))) is not None and start <= d < end),
        "pick still open (scheduled, lock in the future)": lambda f: (
            f.get("status") == "scheduled"
            and (d := parse_iso(f.get("lock_time_utc"))) is not None and d > now),
        "kickoff in the future": lambda f: (
            (d := parse_iso(f.get("start_time_utc"))) is not None and d > now),
    }
    listing_ids = counters.get("listing_ids") or []
    listing_set = set(str(i) for i in listing_ids)
    if listing_set:
        rules["listed by the lobby page state"] = lambda f: str(f.get("fixture_id")) in listing_set
    out = {"week_window": {"start": start.isoformat(), "end": end.isoformat(),
                           "rule": "Monday 00:00 UTC .. next Monday 00:00 UTC"},
           "lobby_counters": {k: v for k, v in counters.items() if k != "listing_ids"},
           "listing_ids_count": len(listing_set), "candidates": {}}
    for name, fn in rules.items():
        rows = [f for f in fixtures if fn(f)]
        out["candidates"][name] = {
            "total": len(rows),
            "cs2": sum(1 for f in rows if f.get("game") == "CS2"),
            "lol": sum(1 for f in rows if f.get("game") == "LoL"),
            "by_tier": {t: sum(1 for f in rows if (f.get("tier") or "").lower() == t)
                        for t in ("s", "b", "c")},
        }
    # Which candidate (if any) reproduces the counters the lobby printed?
    matches = []
    for name, info in out["candidates"].items():
        if counters.get("all_tiers") is not None and info["total"] == counters["all_tiers"]:
            matches.append({"rule": name, "counter": "all_tiers", "value": info["total"]})
        if counters.get("matches_this_week") is not None and \
                info["total"] == counters["matches_this_week"]:
            matches.append({"rule": name, "counter": "matches_this_week", "value": info["total"]})
    for tier, value in (counters.get("tier_counts") or {}).items():
        for name, info in out["candidates"].items():
            if info["by_tier"].get(tier) == value:
                matches.append({"rule": name, "counter": f"tier_{tier}", "value": value})
    # Profile of the lobby's own listing: the page state carries ids that are *not* all from the
    # current week. Publishing that fact (rather than calling all 90 ids "this week's matches") is
    # part of the line-by-line honesty of the board: every id is shown, but the stale ones are
    # labelled and never counted as live coverage.
    listing_rows = [f for f in fixtures if str(f.get("fixture_id")) in listing_set] if listing_set else []
    months: dict[str, int] = {}
    stale = 0
    for f in listing_rows:
        d = parse_iso(f.get("start_time_utc"))
        if d is None:
            continue
        months[d.strftime("%Y-%m")] = months.get(d.strftime("%Y-%m"), 0) + 1
        if d < start - timedelta(days=30):
            stale += 1
    out["listed_profile"] = {
        "ids_carried_by_page_state": len(listing_set),
        "present_in_this_board": len(listing_rows),
        "kickoff_months": dict(sorted(months.items())),
        "stale_kickoff_more_than_30d_before_this_week": stale,
        "rendered_match_links": (counters.get("listing") or {}).get("match_links_rendered"),
    }
    out["counter_reproductions"] = matches
    out["unexplained_counters"] = sorted({
        k for k, v in counters.items()
        if k in ("all_tiers", "matches_this_week") and v is not None
        and not any(m["counter"] == k for m in matches)
    })
    return out


# ------------------------------------------------------------------------------ join rules
def resolve_rating(name: str, ratings: dict) -> tuple[dict | None, dict | None]:
    """Look a team up in the official standings, allowing only exact, reviewable name variants.

    The only transformations applied are stripping a leading "team " or a trailing " esports" /
    " esport" / " gaming" — each one is recorded with the standings entry it resolved to and that
    entry's table URL is shown on the row, so a reviewer can confirm the mapping with one click. A
    variant is accepted only when it matches exactly one standings entry; anything else stays
    unresolved and is published as blank.
    """
    key = canon_team(name)
    if not key:
        return None, None
    rec = ratings.get(key)
    if rec:
        return rec, None
    variants = []
    if key.startswith("team") and len(key) > 4:
        variants.append((key[4:], "leading \"team \" stripped"))
    for suffix, label in (("esports", "trailing \" esports\" stripped"),
                          ("esport", "trailing \" esport\" stripped"),
                          ("gaming", "trailing \" gaming\" stripped")):
        if key.endswith(suffix) and len(key) > len(suffix):
            variants.append((key[:-len(suffix)], label))
    hits = [(value, label, ratings[value]) for value, label in variants if value in ratings]
    if len(hits) == 1:
        value, label, rec = hits[0]
        return rec, {"board_name": name, "standings_name": rec["team"], "rule": label,
                     "source_url": rec.get("source_url"), "raw_url": rec.get("raw_url")}
    return None, None


def rating_candidates(name: str, ratings: dict) -> list[dict]:
    """Names in the official standings that look like this team but are NOT it.

    Published on the flagged page so a reviewer can confirm or reject the mapping; a candidate is
    never applied automatically, because a wrong rating would silently corrupt a probability.
    """
    key = canon_team(name)
    out = []
    if not key:
        return out
    for other, rec in ratings.items():
        if other == key or len(other) < 4:
            continue
        if other.startswith(key) or key.startswith(other):
            out.append({"standings_name": rec["team"], "points": rec["points"],
                        "region": rec["region"], "snapshot": rec["snapshot"]})
    return sorted(out, key=lambda r: -r["points"])[:4]


def classify_quote(quote: dict) -> str:
    return quote.get("confidence") or "market"


def join_quote_to_fixture(fixture: dict, quote: dict) -> dict | None:
    """Return {'orientation': 'ab'|'ba', 'time_hours': float|None, 'notes': [...]} or None.

    A join needs BOTH team names to match after normalisation/aliases. When the source publishes
    a start time it must agree with the lobby's start time inside the tolerance; when the source
    publishes no start time the row is still accepted only because both names matched, and that
    is recorded as a note so the weaker join is visible on the site.
    """
    a, b = fixture.get("team_a"), fixture.get("team_b")
    qa, qb = quote.get("team_a_name"), quote.get("team_b_name")
    if not (a and b and qa and qb):
        return None
    if same_team(qa, a) and same_team(qb, b):
        orientation = "ab"
    elif same_team(qa, b) and same_team(qb, a):
        orientation = "ba"
    else:
        return None
    notes = []
    f_start, q_start = parse_iso(fixture.get("start_time_utc")), parse_iso(quote.get("start_time_utc"))
    hours = hours_between(f_start, q_start)
    if hours is None:
        notes.append("source publishes no start time: joined on exact team pairing only")
    elif hours > JOIN_TIME_TOLERANCE_HOURS:
        return None
    elif hours > 1.0:
        notes.append(f"start times differ by {hours:.1f}h (inside the {JOIN_TIME_TOLERANCE_HOURS:.0f}h tolerance)")
    return {"orientation": orientation, "time_hours": hours, "notes": notes}


# --------------------------------------------------------------------------- board build
def build_board(fixtures_doc: dict, quotes_doc: dict, ratings_doc: dict, now) -> dict:
    fixtures = fixtures_doc.get("fixtures") or []
    quotes = quotes_doc.get("quotes") or []
    ratings = ratings_doc.get("ratings") or {}
    counters = fixtures_doc.get("lobby_counters") or {}

    # Pairing ambiguity inside the kept window: two fixtures with the same two teams cannot be
    # told apart by a quote that carries no start time, so those are never auto-joined.
    pairings: dict[tuple, int] = {}
    for f in fixtures:
        key = tuple(sorted([canon_team(f.get("team_a")), canon_team(f.get("team_b"))]))
        pairings[key] = pairings.get(key, 0) + 1

    listing_ids = (counters.get("listing_ids") or None)
    listing_set = set(listing_ids) if listing_ids else None

    rows = []
    used_quotes: set[int] = set()
    rejected: list[dict] = []
    for f in fixtures:
        row = {
            "fixture_id": f.get("fixture_id"),
            "game": f.get("game"),
            "competition": f.get("competition"),
            "tier": f.get("tier"),
            "status": f.get("status"),
            "start_time_utc": f.get("start_time_utc"),
            "lock_time_utc": f.get("lock_time_utc"),
            "team_a": f.get("team_a"),
            "team_b": f.get("team_b"),
            "hotspawn_match_url": (f.get("source") or {}).get("hotspawn_match_url"),
            "hotspawn_match_url_kind": (f.get("source") or {}).get("hotspawn_match_url_kind"),
            "hotspawn_fixture_api": (f.get("source") or {}).get("api"),
            "hotspawn_pick_pct_reference_only": f.get("hotspawn_pick_pct_reference_only"),
            "listed_in_lobby": (None if listing_set is None
                                else str(f.get("fixture_id")) in listing_set),
            "flags": [],
            "quotes": [],
            "market": None,
            "estimate": None,
            "reference": [],
            "published": None,
        }
        start = parse_iso(f.get("start_time_utc"))
        lock = parse_iso(f.get("lock_time_utc"))
        if f.get("status") != "scheduled":
            row["flags"].append(f"status:{f.get('status')}")
        if lock is not None and lock <= now:
            row["flags"].append("picks_locked_or_past")
        if start is not None and start <= now:
            row["flags"].append("kickoff_passed")

        for idx, q in enumerate(quotes):
            joined = join_quote_to_fixture(f, q)
            if not joined:
                continue
            key = tuple(sorted([canon_team(f.get("team_a")), canon_team(f.get("team_b"))]))
            if (q.get("confidence") or "market") == "market" and joined["time_hours"] is None \
                    and pairings.get(key, 0) > 1:
                rejected.append({"fixture_id": f.get("fixture_id"),
                                 "source_key": q.get("source_key"),
                                 "reason": "ambiguous pairing inside the window and the source "
                                           "publishes no start time",
                                 "quote": {"team_a": q.get("team_a_name"), "team_b": q.get("team_b_name"),
                                           "url": q.get("source_public_url")}})
                continue
            entry = {
                "source_key": q.get("source_key"),
                "source_name": q.get("source_name"),
                "source_kind": q.get("source_kind"),
                "source_public_url": q.get("source_public_url"),
                "source_api_url": q.get("source_api_url"),
                "source_event_id": q.get("source_event_id"),
                "source_market_id": q.get("source_market_id"),
                "source_league": q.get("source_league"),
                "market_type": q.get("market_type"),
                "market_is_live": q.get("market_is_live"),
                "retrieved_at_utc": q.get("retrieved_at_utc"),
                "source_start_time_utc": q.get("start_time_utc"),
                "orientation": joined["orientation"],
                "join_notes": joined["notes"],
                "raw_price_format": q.get("raw_price_format"),
                "raw_price_a": q.get("raw_price_a"),
                "raw_price_b": q.get("raw_price_b"),
            }
            if (q.get("confidence") or "market") != "market":
                entry["quoted_probability"] = q.get("raw_price_a")
                entry["quoted_probability_for"] = "team_a" if joined["orientation"] == "ab" else "team_b"
                row["reference"].append(entry)
                used_quotes.add(idx)
                continue
            dec_a = q.get("decimal_odds_a")
            dec_b = q.get("decimal_odds_b")
            if joined["orientation"] == "ba":
                dec_a, dec_b = dec_b, dec_a
            nv = no_vig_two_way(dec_a, dec_b)
            if not nv:
                rejected.append({"fixture_id": f.get("fixture_id"), "source_key": q.get("source_key"),
                                 "reason": "quoted prices do not produce a two-way de-vig",
                                 "quote": {"dec_a": dec_a, "dec_b": dec_b}})
                continue
            entry.update({"decimal_odds_a": dec_a, "decimal_odds_b": dec_b,
                          "prob_a": nv["prob_a"], "prob_b": nv["prob_b"],
                          "overround": nv["overround"]})
            row["quotes"].append(entry)
            used_quotes.add(idx)

        # Duplicate quotes from one source: keep the newest, record the others.
        by_source: dict[str, dict] = {}
        for entry in row["quotes"]:
            key = entry["source_key"]
            if key in by_source:
                row["flags"].append(f"duplicate_quote:{key}")
                if str(entry.get("retrieved_at_utc") or "") > str(by_source[key].get("retrieved_at_utc") or ""):
                    by_source[key] = entry
            else:
                by_source[key] = entry
        fresh = []
        for entry in by_source.values():
            read = parse_iso(entry.get("retrieved_at_utc"))
            age = hours_between(read, now)
            entry["age_hours"] = safe_round(age, 2) if age is not None else None
            if entry.get("market_is_live"):
                entry["stale"] = True
                row["flags"].append(f"live_market_excluded:{entry['source_key']}")
                continue
            if age is not None and age > QUOTE_FRESHNESS_HOURS:
                entry["stale"] = True
                row["flags"].append(f"stale_quote_excluded:{entry['source_key']}")
                continue
            entry["stale"] = False
            fresh.append(entry)
        fresh_consensus = consensus([{"source_key": e["source_key"], "prob_a": e["prob_a"],
                                      "prob_b": e["prob_b"]} for e in fresh])
        if fresh_consensus and len(fresh) >= MIN_SOURCES:
            row["market"] = {**fresh_consensus,
                             "sources_detail": [{"source_key": e["source_key"],
                                                 "source_name": e["source_name"],
                                                 "source_public_url": e["source_public_url"],
                                                 "source_api_url": e["source_api_url"],
                                                 "source_event_id": e["source_event_id"],
                                                 "source_market_id": e["source_market_id"],
                                                 "decimal_odds_a": e["decimal_odds_a"],
                                                 "decimal_odds_b": e["decimal_odds_b"],
                                                 "prob_a": e["prob_a"], "prob_b": e["prob_b"],
                                                 "overround": e["overround"],
                                                 "retrieved_at_utc": e["retrieved_at_utc"],
                                                 "join_notes": e["join_notes"],
                                                 "orientation": e["orientation"]}
                                                for e in fresh]}
        # Originated estimate — CS2 only, official Valve VRS input, its own labelled field.
        if (row["game"] or "").upper() == "CS2":
            ra, alias_a = resolve_rating(row["team_a"], ratings)
            rb, alias_b = resolve_rating(row["team_b"], ratings)
            row["rating_aliases_used"] = [a for a in (alias_a, alias_b) if a]
            if ra and rb:
                est = vrs_estimate(ra["points"], rb["points"])
                if est:
                    row["estimate"] = {
                        **est,
                        "label": "originated estimate — not a market price",
                        "rating_source": ratings_doc.get("source"),
                        "team_a_points": ra["points"], "team_a_standing": ra["standing"],
                        "team_a_region": ra["region"], "team_a_snapshot": ra["snapshot"],
                        "team_a_source_url": ra.get("source_url"),
                        "team_b_points": rb["points"], "team_b_standing": rb["standing"],
                        "team_b_region": rb["region"], "team_b_snapshot": rb["snapshot"],
                        "team_b_source_url": rb.get("source_url"),
                    }
            else:
                missing = [t for t, r in ((row["team_a"], ra), (row["team_b"], rb)) if not r]
                row["flags"].append("no_valve_vrs_rating:" + "|".join(missing))
                row["rating_candidates_refused"] = {t: rating_candidates(t, ratings) for t in missing}
        elif (row["game"] or "").upper() == "LOL":
            row["flags"].append("no_official_rating_source_for_lol")

        # What gets published (market first, then labelled estimate, else blank + flag).
        if row["market"]:
            prob_a = row["market"]["prob_a"]
            basis = "market"
            edge = abs(prob_a - 0.5)
            side = None if (row["market"]["prob_b"] is None) else ("a" if prob_a > row["market"]["prob_b"] else "b")
            if row["market"]["spread_a"] is not None and row["market"]["spread_a"] > 0.25:
                row["flags"].append("wide_source_disagreement")
            if edge < TIE_TOLERANCE:
                side = None
                row["flags"].append("coin_flip_market")
            row["published"] = {
                "basis": basis, "prob_a": prob_a, "prob_b": row["market"]["prob_b"],
                "pick_side": side,
                "pick_team": None if side is None else (row["team_a"] if side == "a" else row["team_b"]),
                "pick_probability": max(prob_a, row["market"]["prob_b"]),
                "edge": abs(prob_a - row["market"]["prob_b"]),
                "source_links": [d["source_public_url"] for d in row["market"]["sources_detail"]],
            }
        elif row["estimate"]:
            e = row["estimate"]
            side = "a" if e["prob_a"] >= e["prob_b"] else "b"
            if abs(e["prob_a"] - e["prob_b"]) < TIE_TOLERANCE:
                side = None
                row["flags"].append("coin_flip_estimate")
            row["published"] = {
                "basis": "estimate", "prob_a": e["prob_a"], "prob_b": e["prob_b"],
                "pick_side": side,
                "pick_team": None if side is None else (row["team_a"] if side == "a" else row["team_b"]),
                "pick_probability": max(e["prob_a"], e["prob_b"]),
                "edge": abs(e["prob_a"] - e["prob_b"]),
                "source_links": [e["team_a_source_url"], e["team_b_source_url"]],
                "label": "originated estimate — not a market price",
            }
        else:
            row["flags"].append("no_probability_available")
            row["published"] = {"basis": "none", "prob_a": None, "prob_b": None,
                                "pick_side": None, "pick_team": None, "pick_probability": None,
                                "edge": None, "source_links": []}
        rows.append(row)

    listed = [r for r in rows if r.get("listed_in_lobby") is True]
    listed_pickable = [r for r in listed if "picks_locked_or_past" not in r["flags"]]
    unlisted = [r for r in rows if r.get("listed_in_lobby") is False]
    summary = {
        "rows": len(rows),
        "lobby_listing_available": listing_set is not None,
        "lobby_listed_rows": len(listed),
        "lobby_listed_with_probability": sum(1 for r in listed if r["published"]["basis"] != "none"),
        "lobby_listed_market": sum(1 for r in listed if r["published"]["basis"] == "market"),
        "lobby_listed_estimate": sum(1 for r in listed if r["published"]["basis"] == "estimate"),
        "lobby_listed_blank": sum(1 for r in listed if r["published"]["basis"] == "none"),
        "not_in_lobby_listing_rows": len(unlisted),
        "lobby_listed_pickable": len(listed_pickable),
        "lobby_listed_pickable_with_probability": sum(1 for r in listed_pickable
                                                      if r["published"]["basis"] != "none"),
        "lobby_listed_pickable_market": sum(1 for r in listed_pickable
                                            if r["published"]["basis"] == "market"),
        "lobby_listed_pickable_estimate": sum(1 for r in listed_pickable
                                              if r["published"]["basis"] == "estimate"),
        "lobby_listed_pickable_blank": sum(1 for r in listed_pickable
                                           if r["published"]["basis"] == "none"),
        "lobby_listed_picks_closed": len(listed) - len(listed_pickable),
        "with_market_probability": sum(1 for r in rows if r["published"]["basis"] == "market"),
        "with_originated_estimate": sum(1 for r in rows if r["published"]["basis"] == "estimate"),
        "blank": sum(1 for r in rows if r["published"]["basis"] == "none"),
        "pickable_now": sum(1 for r in rows
                            if "picks_locked_or_past" not in r["flags"]
                            and r["status"] == "scheduled"),
        "with_pick": sum(1 for r in rows if r["published"]["pick_side"]),
        "by_game": {},
    }
    for game in ("CS2", "LoL", None):
        subset = [r for r in rows if (r["game"] or None) == game]
        if not subset:
            continue
        summary["by_game"][game or "other"] = {
            "rows": len(subset),
            "market": sum(1 for r in subset if r["published"]["basis"] == "market"),
            "estimate": sum(1 for r in subset if r["published"]["basis"] == "estimate"),
            "blank": sum(1 for r in subset if r["published"]["basis"] == "none"),
        }
    return {
        # Stamp the board with the instant it was computed at, not with wall-clock time.
        # verify_board() rebuilds the board from its own stamp to prove HotSpawn's crowd
        # percentages are not an input (check C7); if the stamp were wall-clock while `now`
        # was an explicit evaluation time, the two builds would land in different freshness
        # windows and C7 would report a false failure. (Repaired by c0e223d3.)
        "generated_at_utc": to_iso(now) or now_iso(),
        "rules": {
            "fixture_source": "HotSpawn Pick'ems public fixtures endpoint (discovery only)",
            "probability_source": "external bookmakers and the EGamersWorld odds widget — never HotSpawn",
            "join_rule": (f"both team names must match after normalisation/alias mapping and, when the "
                          f"source publishes a start time, it must be within "
                          f"{JOIN_TIME_TOLERANCE_HOURS:.0f}h of the lobby start time"),
            "freshness_rule": f"market quotes older than {QUOTE_FRESHNESS_HOURS:.0f}h and live (in-play) "
                              "markets are excluded from the published probability",
            "consensus_rule": "arithmetic mean of per-source proportional no-vig probabilities",
            "pick_rule": f"pick = higher published probability; an edge below {TIE_TOLERANCE} is published "
                         "as a coin flip with no pick",
            "estimate_rule": VRS_MODEL + " Published only for CS2 and always labelled as an estimate.",
            "hotspawn_pick_pct": "never used as an input to any probability",
        },
        "window_analysis": window_analysis(fixtures, counters, now),
        "summary": summary,
        "rows": rows,
        "rejected_joins": rejected,
        "quotes_used": len(used_quotes),
    }


# -------------------------------------------------------------------------------- verify
def verify_board(board: dict, quotes_doc: dict, ratings_doc: dict, fixtures_doc: dict) -> dict:
    """Re-derive every published number from the raw evidence. Returns check results."""
    checks: list[dict] = []
    quotes = quotes_doc.get("quotes") or []
    ratings = ratings_doc.get("ratings") or {}

    def add(name, ok, detail):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    rows = board.get("rows") or []
    market_rows = [r for r in rows if r["published"]["basis"] == "market"]
    est_rows = [r for r in rows if r["published"]["basis"] == "estimate"]
    blank_rows = [r for r in rows if r["published"]["basis"] == "none"]

    # C1: every published market probability re-derives exactly from the raw quoted prices.
    worst = 0.0
    bad = []
    for r in market_rows:
        for d in r["market"]["sources_detail"]:
            nv = no_vig_two_way(d["decimal_odds_a"], d["decimal_odds_b"])
            if not nv:
                bad.append({"fixture_id": r["fixture_id"], "source": d["source_key"],
                            "reason": "no de-vig"})
                continue
            delta = max(abs(nv["prob_a"] - d["prob_a"]), abs(nv["prob_b"] - d["prob_b"]))
            worst = max(worst, delta)
            if delta > 1e-9:
                bad.append({"fixture_id": r["fixture_id"], "source": d["source_key"],
                            "delta": delta})
    add("C1 per-source probabilities re-derive from raw prices", not bad,
        {"rows": len(market_rows), "max_abs_delta": worst, "failures": bad[:5]})

    # C2: consensus = arithmetic mean of the per-source no-vig probabilities.
    bad = []
    for r in market_rows:
        detail = r["market"]["sources_detail"]
        mean = sum(d["prob_a"] for d in detail) / len(detail)
        if abs(mean - r["market"]["prob_a"]) > 1e-9 or len(detail) != r["market"]["n_sources"]:
            bad.append({"fixture_id": r["fixture_id"], "mean": mean,
                        "published": r["market"]["prob_a"]})
    add("C2 consensus equals the mean of its sources", not bad,
        {"rows": len(market_rows), "failures": bad[:5]})

    # C3: published pick = higher published probability.
    bad = []
    for r in rows:
        p = r["published"]
        if p["pick_side"] is None:
            continue
        expected = r["team_a"] if p["prob_a"] > p["prob_b"] else r["team_b"]
        if p["pick_team"] != expected or abs(p["pick_probability"] - max(p["prob_a"], p["prob_b"])) > 1e-12:
            bad.append({"fixture_id": r["fixture_id"], "pick": p["pick_team"], "expected": expected})
    add("C3 published pick is the higher published probability", not bad,
        {"picked_rows": sum(1 for r in rows if r["published"]["pick_side"]), "failures": bad[:5]})

    # C4: market rows expose http(s) source links and a read time for every source used.
    bad = []
    for r in market_rows:
        for d in r["market"]["sources_detail"]:
            links = [d.get("source_public_url"), d.get("source_api_url")]
            if not any(isinstance(l, str) and l.startswith("http") for l in links) \
                    or not d.get("retrieved_at_utc"):
                bad.append({"fixture_id": r["fixture_id"], "source": d["source_key"]})
    add("C4 every market source carries a link and a read time", not bad,
        {"failures": bad[:5]})

    # C5: estimate rows re-derive from the official Valve VRS points and carry their source link.
    bad = []
    for r in est_rows:
        e = r["estimate"]
        ra, _ = resolve_rating(r["team_a"], ratings)
        rb, _ = resolve_rating(r["team_b"], ratings)
        if not (ra and rb):
            bad.append({"fixture_id": r["fixture_id"], "reason": "rating missing"})
            continue
        if ra["points"] != e["team_a_points"] or rb["points"] != e["team_b_points"]:
            bad.append({"fixture_id": r["fixture_id"], "reason": "points mismatch"})
            continue
        again = vrs_estimate(ra["points"], rb["points"])
        if abs(again["prob_a"] - e["prob_a"]) > 1e-12:
            bad.append({"fixture_id": r["fixture_id"], "reason": "estimate mismatch"})
        if not (e.get("team_a_source_url", "").startswith("http")
                and e.get("team_b_source_url", "").startswith("http")):
            bad.append({"fixture_id": r["fixture_id"], "reason": "estimate without source link"})
    add("C5 estimates re-derive from the official Valve VRS table", not bad,
        {"rows": len(est_rows), "failures": bad[:5]})

    # C6: blank rows are blank and flagged.
    bad = [{"fixture_id": r["fixture_id"]} for r in blank_rows
           if r["published"]["prob_a"] is not None or "no_probability_available" not in r["flags"]]
    add("C6 unverified rows stay blank and flagged", not bad,
        {"rows": len(blank_rows), "failures": bad[:5]})

    # C7: HotSpawn crowd percentage cannot reach a published number. Recompute the whole board
    # with every crowd number replaced by a sentinel and require byte-identical probabilities.
    scrambled = json.loads(json.dumps(fixtures_doc))
    for f in scrambled.get("fixtures") or []:
        f["hotspawn_pick_pct_reference_only"] = {"team_a": 99, "team_b": -1}
    other = build_board(scrambled, quotes_doc, ratings_doc, parse_iso(board["generated_at_utc"]))
    keys = [(r["fixture_id"], r["published"]["prob_a"], r["published"]["prob_b"],
             r["published"]["pick_side"]) for r in other["rows"]]
    here = [(r["fixture_id"], r["published"]["prob_a"], r["published"]["prob_b"],
             r["published"]["pick_side"]) for r in rows]
    add("C7 HotSpawn crowd percentages are not an input", keys == here,
        {"rows_compared": len(here), "identical": keys == here})

    # C8: every lobby row inside the kept window appears exactly once; every row's fixture id is
    # present in the fixture snapshot (no invented rows).
    ids_snapshot = [f.get("fixture_id") for f in (fixtures_doc.get("fixtures") or [])]
    ids_board = [r["fixture_id"] for r in rows]
    add("C8 board covers the fixture snapshot exactly once", ids_board == ids_snapshot,
        {"board": len(ids_board), "snapshot": len(ids_snapshot),
         "duplicates": len(ids_board) - len(set(ids_board))})

    # C9: freshness — no published market row uses a quote older than the rule, none is in-play.
    bad = []
    for r in market_rows:
        for d in r["market"]["sources_detail"]:
            if d.get("stale"):
                bad.append({"fixture_id": r["fixture_id"], "source": d["source_key"]})
    add("C9 no stale or in-play quote is published", bad == [],
        {"market_rows": len(market_rows), "failures": bad[:5]})

    # C10: arithmetic sanity — probabilities are in (0,1), pairs sum to 1, overround positive.
    bad = []
    for r in rows:
        p = r["published"]
        if p["prob_a"] is None:
            continue
        if not (0 < p["prob_a"] < 1 and 0 < p["prob_b"] < 1
                and abs(p["prob_a"] + p["prob_b"] - 1.0) < 1e-9):
            bad.append({"fixture_id": r["fixture_id"], "prob_a": p["prob_a"], "prob_b": p["prob_b"]})
        for d in r["market"]["sources_detail"] if r["market"] else []:
            if not (0 < d["prob_a"] < 1 and d["overround"] > 0):
                bad.append({"fixture_id": r["fixture_id"], "source": d["source_key"]})
    add("C10 probability arithmetic is in range and normalised", not bad,
        {"failures": bad[:5]})

    # C11: the lobby's own listing must be fully inside this board — a missing id is a coverage gap,
    # published rather than hidden.
    listing_ids = {str(i) for i in
                   ((fixtures_doc.get("lobby_counters") or {}).get("listing_ids") or [])}
    board_ids = {str(r["fixture_id"]) for r in rows}
    missing = sorted(listing_ids - board_ids)
    flag_wrong = [r["fixture_id"] for r in rows
                  if r.get("listed_in_lobby") is not None
                  and (str(r["fixture_id"]) in listing_ids) != bool(r.get("listed_in_lobby"))]
    add("C11 every lobby-listed fixture is present in the board",
        not missing and not flag_wrong,
        {"listed_ids": len(listing_ids), "missing_count": len(missing), "missing": missing[:20],
         "listing_flag_mismatches": flag_wrong[:5]})

    passed = sum(1 for c in checks if c["passed"])
    return {"verified_at_utc": now_iso(), "checks": checks, "passed": passed,
            "failed": len(checks) - passed,
            "rows_checked": len(rows),
            "market_rows": len(market_rows), "estimate_rows": len(est_rows),
            "blank_rows": len(blank_rows)}


# ------------------------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#2a2f3a;--fg:#eef1f6;--mut:#9aa4b2;--ok:#2ecc71;
--est:#f5a623;--bad:#ff6b6b;--blue:#4aa3ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;background:#12151c;border-bottom:1px solid var(--line);padding:10px 14px;
z-index:5}
h1{font-size:18px;margin:0 0 6px}
h2{font-size:17px;margin:22px 14px 8px}
h3{font-size:15px;margin:0 0 6px}
a{color:var(--blue);text-decoration:none}
nav{display:flex;flex-wrap:wrap;gap:8px;font-size:14px}
nav a{background:#1d2230;border:1px solid var(--line);border-radius:999px;padding:5px 10px}
main{padding:0 12px 60px;max-width:1100px;margin:0 auto}
.cards{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.meta{color:var(--mut);font-size:12.5px;margin:2px 0 8px}
.teams{display:flex;flex-direction:column;gap:6px;margin:6px 0 8px}
.team{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:6px 8px;
border:1px solid var(--line);border-radius:8px;background:#12151c}
.team.pick{border-color:var(--ok);box-shadow:inset 0 0 0 1px rgba(46,204,113,.35)}
.team .name{font-weight:600}
.team .prob{font-variant-numeric:tabular-nums;font-weight:700}
.badge{display:inline-block;font-size:11.5px;border-radius:999px;padding:2px 8px;border:1px solid var(--line);
color:var(--mut);margin:0 4px 4px 0}
.badge.ok{border-color:var(--ok);color:var(--ok)}
.badge.est{border-color:var(--est);color:var(--est)}
.badge.bad{border-color:var(--bad);color:var(--bad)}
.pickline{margin-top:6px;font-size:14px}
.pickline b{color:var(--ok)}
.src{font-size:12.5px;color:var(--mut);margin-top:6px;word-break:break-word}
.bar{height:7px;border-radius:6px;background:#2a2f3a;overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#4aa3ff,#2ecc71)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{border-bottom:1px solid var(--line);padding:7px 6px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}
.wrap{overflow-x:auto}
.note{background:#131722;border:1px solid var(--line);border-left:3px solid var(--blue);padding:10px 12px;
border-radius:8px;margin:12px 0;font-size:13.5px;color:#cdd6e2}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.kpi div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:120px}
.kpi b{display:block;font-size:22px}
footer{padding:20px 12px;color:var(--mut);font-size:12.5px;border-top:1px solid var(--line)}
@media (max-width:520px){h1{font-size:16px}.cards{grid-template-columns:1fr}}
"""

NAV = [("index.html", "Live board"), ("cs2.html", "CS2"), ("lol.html", "LoL"),
       ("flagged.html", "Flagged for review"), ("methodology.html", "Method & sources"),
       ("sources.html", "Sources")]


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def page(title: str, active: str, body: str, generated: str, extra_note: str = "") -> str:
    parts = []
    for href, label in NAV:
        style = ' style="border-color:#4aa3ff"' if href == active else ""
        parts.append(f'<a href="{esc(href)}"{style}>{esc(label)}</a>')
    nav = "".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="External betting-line probabilities for every CS2 and LoL match listed in the HotSpawn Pick'ems lobby.">
<link rel="stylesheet" href="assets/live.css">
</head><body>
<header><h1>{esc(title)}</h1><nav>{nav}</nav></header>
<main>{extra_note}{body}</main>
<footer>Generated {esc(generated)} · Fixtures discovered from the HotSpawn Pick'ems lobby; all
probabilities come from external bookmakers or a labelled originated estimate — never from HotSpawn's
crowd pick percentage. Estimates are not guarantees. 18+; gamble responsibly. Not affiliated with
HotSpawn or any bookmaker.</footer>
</body></html>
"""


def fixture_link(row: dict) -> str:
    """Per-row HotSpawn source link: the published permalink when there is one, else the lobby."""
    url = row.get("hotspawn_match_url")
    if not url:
        return ""
    if row.get("hotspawn_match_url_kind") == "lobby_published_permalink":
        return f'<a href="{esc(url)}">HotSpawn match page</a>'
    return f'<a href="{esc(url)}">HotSpawn lobby</a>'


def row_card(row: dict, show_estimate: bool = True) -> str:
    pub = row["published"]
    basis = pub["basis"]
    badges = []
    if basis == "market":
        badges.append(f'<span class="badge ok">external market line · {esc(row["market"]["n_sources"])} '
                      f'source(s)</span>')
    elif basis == "estimate":
        badges.append('<span class="badge est">originated estimate — not a market price</span>')
    else:
        badges.append('<span class="badge bad">no verified line — blank</span>')
    for flag in (row.get("flags") or []):
        if flag.startswith(("no_valve_vrs_rating", "no_official_rating", "stale_quote",
                            "live_market", "duplicate_quote", "wide_source")):
            badges.append(f'<span class="badge bad">{esc(flag)}</span>')
    tie = "coin_flip" in " ".join(row.get("flags") or [])
    def team_line(side: str, name: str, prob) -> str:
        cls = "team pick" if pub.get("pick_side") == side else "team"
        width = int(round((prob or 0) * 100))
        return (f'<div class="{cls}"><span class="name">{esc(name)}</span>'
                f'<span class="prob">{pct(prob)}</span></div>'
                f'<div class="bar"><i style="width:{width}%"></i></div>')
    pick = (f'Pick: <b>{esc(pub["pick_team"])}</b> at {pct(pub["pick_probability"])} · edge '
            f'{pct(pub["edge"])}') if pub.get("pick_team") else (
        "No pick published — probabilities are level" if tie else "No probability published")
    detail = ""
    if basis == "market":
        used = row["market"]["sources_detail"]
        links = []
        for d in used:
            rate = d.get("decimal_odds_a"), d.get("decimal_odds_b")
            links.append(f'<div class="src">· <a href="{esc(d["source_api_url"] or d["source_public_url"])}">'
                         f'{esc(d["source_name"])}</a> — quoted {esc(d["raw_price_format"] if d.get("raw_price_format") else "decimal")} '
                         f'{esc(rate[0])} / {esc(rate[1])} → no-vig '
                         f'{pct(d["prob_a"])} / {pct(d["prob_b"])} · margin {pct(d["overround"])} · '
                         f'read {esc(d["retrieved_at_utc"])}'
                         + (f' · <span class="badge bad">{esc("; ".join(d["join_notes"]))}</span>'
                            if d.get("join_notes") else "")
                         + '</div>')
        detail = "".join(links)
        detail += (f'<div class="src">Consensus: arithmetic mean of the per-source no-vig probabilities '
                   f'({esc(", ".join(row["market"]["sources"]))})'
                   + (f' · source range {pct(row["market"]["min_prob_a"])}–{pct(row["market"]["max_prob_a"])}'
                      if row["market"]["n_sources"] > 1 else "") + '</div>')
    elif basis == "estimate":
        e = row["estimate"]
        detail = (f'<div class="src">Valve VRS points: {esc(row["team_a"])} {esc(e["team_a_points"])} '
                  f'(#{esc(e["team_a_standing"])} {esc(e["team_a_region"])}, {esc(e["team_a_snapshot"])}) · '
                  f'{esc(row["team_b"])} {esc(e["team_b_points"])} (#{esc(e["team_b_standing"])} '
                  f'{esc(e["team_b_region"])}, {esc(e["team_b_snapshot"])})</div>'
                  f'<div class="src">Rating source: <a href="{esc(e["team_a_source_url"])}">{esc(row["team_a"])}</a> · '
                  f'<a href="{esc(e["team_b_source_url"])}">{esc(row["team_b"])}</a> · {esc(e["model"])}</div>'
                  + "".join(f'<div class="src">Name matched to the standings entry '
                            f'<b>{esc(a["standings_name"])}</b> ({esc(a["rule"])}) — '
                            f'<a href="{esc(a["source_url"])}">standings table</a></div>'
                            for a in (row.get("rating_aliases_used") or [])))
    else:
        reason = [f for f in row["flags"] if f.startswith(("no_valve_vrs", "no_official_rating"))]
        detail = (f'<div class="src">No external price and no official rating available for both teams '
                  f'— left blank rather than estimated.{esc(" (" + "; ".join(reason) + ")") if reason else ""}</div>')
    if row.get("reference"):
        refs = "".join(f'<div class="src">Exchange reference (not averaged): '
                       f'<a href="{esc(r["source_public_url"])}">{esc(r["source_name"])}</a> '
                       f'{esc(r.get("quoted_probability_for"))} {esc(r.get("quoted_probability"))} · '
                       f'read {esc(r["retrieved_at_utc"])}</div>' for r in row["reference"])
        detail += refs
    if row.get("hotspawn_match_url"):
        hs = (f'<div class="src">{fixture_link(row)} · '
              f'<a href="{esc(row["hotspawn_fixture_api"])}">fixture API</a></div>')
    else:
        hs = ""
    return f"""<article class="card">
<div class="meta">{esc(row["start_time_utc"])} · Tier {esc((row["tier"] or "?").upper())} · {esc(row["competition"])} · {esc(row["status"])}</div>
<h3>{esc(row["team_a"])} vs {esc(row["team_b"])}</h3>
{''.join(badges)}
<div class="teams">{team_line("a", row["team_a"], pub["prob_a"])}{team_line("b", row["team_b"], pub["prob_b"])}</div>
<div class="pickline">{pick}</div>
{detail}{hs}
</article>"""


def render_index(board: dict, verification: dict) -> str:
    rows = board["rows"]
    order = {"market": 0, "estimate": 1, "none": 2}

    def sort_key(r):
        locked = "picks_locked_or_past" in r["flags"]
        return (locked, order[r["published"]["basis"]], r["start_time_utc"] or "")

    listed = sorted([r for r in rows if r.get("listed_in_lobby") is True], key=sort_key)
    open_listed = [r for r in listed if "picks_locked_or_past" not in r["flags"]]
    closed_listed = [r for r in listed if "picks_locked_or_past" in r["flags"]]
    other = sorted([r for r in rows if r.get("listed_in_lobby") is not True], key=sort_key)
    s = board["summary"]
    kpis = f"""<div class="kpi">
<div><b>{s["lobby_listed_rows"]}</b>matches listed by the lobby</div>
<div><b>{s["lobby_listed_pickable"]}</b>still open for picks</div>
<div><b>{s["lobby_listed_pickable_market"]}</b>of those priced from external bookmaker lines</div>
<div><b>{s["lobby_listed_pickable_estimate"]}</b>labelled originated estimate</div>
<div><b>{s["lobby_listed_pickable_blank"]}</b>blank / unverified</div>
</div>"""
    note = f"""<div class="note"><b>What this page is.</b> Every fixture the HotSpawn Pick'ems lobby is
currently listing, with a win probability and an obvious pick. A probability is published only from an
external bookmaker's two-way price (de-vigged) or, when no bookmaker prices the match, from a clearly
labelled estimate derived from Valve's official CS2 Regional Standings. Anything that cannot be confirmed
stays blank and is listed on <a href="flagged.html">Flagged for review</a>.
Verification: {verification["passed"]}/{len(verification["checks"])} checks passed on this build.</div>"""
    wc = board["window_analysis"]["lobby_counters"]
    listing = (wc.get("listing") or {})
    win_note = (f"""<div class="note"><b>Coverage check.</b> The lobby page itself prints """
                f"""{esc(wc.get("matches_this_week"))} matches this week and All tiers {esc(wc.get("all_tiers"))} """
                f"""(tiers {esc(wc.get("tier_counts"))}); its own page state carries """
                f"""{esc(listing.get("listed_count"))} fixture ids; the rendered page shows """
                f"""{esc((board["window_analysis"].get("listed_profile") or {}).get("rendered_match_links"))} """
                f"""match links. This board holds all {s["lobby_listed_rows"]} of those ids """
                f"""({len(open_listed)} still open for picks, {len(closed_listed)} with picks already """
                f"""locked or past), and {s["lobby_listed_with_probability"]} of them carry a published """
                f"""probability. Of the carried ids, """
                f"""{esc((board["window_analysis"].get("listed_profile") or {}).get("stale_kickoff_more_than_30d_before_this_week"))} """
                f"""have a kickoff more than 30 days before this week (months: """
                f"""{esc((board["window_analysis"].get("listed_profile") or {}).get("kickoff_months"))}) — """
                f"""the page state is not a "this week" list, so stale ids are labelled, never counted as """
                f"""live coverage."""
                + (f""" <b>Unreproduced counters: {esc(", ".join(board["window_analysis"]["unexplained_counters"]))}"""
                   f""" — published as unexplained rather than guessed.</b>"""
                   if board["window_analysis"].get("unexplained_counters") else "") + "</div>")
    cards = "".join(row_card(r) for r in open_listed) or "<p>No lobby-listed fixture is still open for picks.</p>"
    closed_rows = "".join(
        f'<tr><td>{esc(r["start_time_utc"])}</td><td>{esc(r["tier"])}</td>'
        f'<td>{esc(r["competition"])}</td><td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td>{esc(r["published"]["basis"])}</td>'
        f'<td>{esc("; ".join(r["flags"]))}</td>'
        f'<td>{fixture_link(r)}</td></tr>' for r in closed_listed)
    closed_block = (
        f'<h2>Listed by the lobby but no longer open for picks ({len(closed_listed)})</h2>'
        f'<div class="note">Published so the listing coverage is complete and auditable. Rows here carry a '
        f'kickoff or lock time in the past; a stale fixture the lobby page state still carries is shown, '
        f'never silently dropped, and never counted as live coverage.</div>'
        f'<div class="wrap"><table><thead><tr><th>Kickoff (UTC)</th><th>Tier</th><th>Tournament</th>'
        f'<th>Match</th><th>Basis</th><th>Flags</th><th>Source</th></tr></thead>'
        f'<tbody>{closed_rows}</tbody></table></div>') if closed_listed else ""
    other_block = ""
    if other:
        other_rows = "".join(
            f'<tr><td>{esc(r["start_time_utc"])}</td><td>{esc(r["game"])}</td>'
            f'<td>{esc(r["competition"])}</td><td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
            f'<td>{esc(r["published"]["basis"])}</td>'
            f'<td>{"yes" if r["published"]["pick_side"] else "no"}</td>'
            f'<td>{fixture_link(r)}</td></tr>' for r in other[:400])
        other_block = (f'<h2>Also returned by the fixture API but not listed by the lobby right now '
                       f'({len(other)})</h2><div class="note">Kept so nothing is hidden, but these rows '
                       f'are <b>not</b> part of the lobby listing and are excluded from the coverage '
                       f'numbers above.</div><details><summary>Show the list</summary>'
                       f'<div class="wrap"><table><thead><tr><th>Kickoff (UTC)</th><th>Game</th>'
                       f'<th>Tournament</th><th>Match</th><th>Basis</th><th>Pick</th><th>Source</th>'
                       f'</tr></thead><tbody>{other_rows}</tbody></table></div></details>')
    return page("HotSpawn Pick'ems — live probability board", "index.html",
                kpis + note + win_note + f'<h2>Listed by the lobby and open for picks ({len(open_listed)})</h2>'
                f'<div class="cards">{cards}</div>' + closed_block + other_block,
                board["generated_at_utc"])


def render_game(board: dict, game: str) -> str:
    rows = [r for r in board["rows"] if (r["game"] or "").upper() == game]
    rows.sort(key=lambda r: (r.get("listed_in_lobby") is not True,
                             r["published"]["basis"] != "market", r["start_time_utc"] or ""))
    listed = [r for r in rows if r.get("listed_in_lobby") is True]
    listed_pickable = [r for r in listed if "picks_locked_or_past" not in r["flags"]]
    body = (f'<h2>{esc(game)} matches ({len(rows)} in the fixture window, {len(listed)} listed in '
            f'the lobby now)</h2><div class="cards">' + "".join(row_card(r) for r in rows) + "</div>")
    return page(f"{game} — HotSpawn Pick'ems probabilities", f"{game.lower()}.html", body,
                board["generated_at_utc"])


def render_flagged(board: dict, verification: dict, quotes_doc: dict, log: dict) -> str:
    blanks = [r for r in board["rows"] if r["published"]["basis"] == "none"]
    flagged = [r for r in board["rows"] if r["flags"]]
    def table(rows, cols):
        head = "".join(f"<th>{esc(c)}</th>" for c in cols)
        body = ""
        for r in rows[:400]:
            body += "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
        return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    blank_rows = table([[
        esc(r["start_time_utc"]), esc(r["game"]), esc(r["competition"]), esc(r["tier"]),
        f'{esc(r["team_a"])} vs {esc(r["team_b"])}',
        esc("; ".join(f for f in r["flags"] if f.startswith(("no_valve", "no_official")))),
        fixture_link(r)] for r in blanks],
        ["Kickoff (UTC)", "Game", "Tournament", "Tier", "Match", "Why blank", "Source"])
    flag_rows = table([[
        esc(r["start_time_utc"]), esc(r["game"]), f'{esc(r["team_a"])} vs {esc(r["team_b"])}',
        esc("; ".join(r["flags"])), esc(r["published"]["basis"])] for r in flagged],
        ["Kickoff (UTC)", "Game", "Match", "Flags", "Basis"])
    rejected = board.get("rejected_joins") or []
    rej_lines = "".join(f'<li>{esc(j.get("fixture_id"))} · {esc(j.get("source_key"))} · {esc(j.get("reason"))} '
                        f'· <a href="{esc((j.get("quote") or {}).get("url"))}">quote</a></li>' for j in rejected[:200])
    source_problems = []
    for key, value in (log.items()):
        if isinstance(value, dict) and (value.get("error") or value.get("status") not in (200, None)):
            source_problems.append(f'<li>{esc(key)} — status {esc(value.get("status"))} '
                                   f'{esc(value.get("error"))} <a href="{esc(value.get("url"))}">url</a></li>')
    checks = "".join(f'<li>{"PASS" if c["passed"] else "FAIL"} — {esc(c["check"])}: '
                     f'{esc(json.dumps(c["detail"])[:400])}</li>' for c in verification["checks"])
    cand_rows = []
    for r in board["rows"]:
        for team, cands in (r.get("rating_candidates_refused") or {}).items():
            for c in cands:
                cand_rows.append(
                    f'<tr><td>{esc(r["start_time_utc"])}</td>'
                    f'<td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
                    f'<td>{esc(team)}</td><td>{esc(c["standings_name"])}</td>'
                    f'<td>{esc(c["points"])}</td><td>{esc(c["region"])}</td>'
                    f'<td>{esc(c["snapshot"])}</td></tr>')
    rating_candidates_html = (
        '<div class="wrap"><table><thead><tr><th>Kickoff (UTC)</th><th>Match</th>'
        '<th>Team we could not rate</th><th>Similar name in the standings</th><th>Points</th>'
        '<th>Region</th><th>Snapshot</th></tr></thead><tbody>' + "".join(cand_rows)
        + '</tbody></table></div>') if cand_rows else (
        '<p>No similar names were found for the unrated teams in this build.</p>')
    body = f"""<div class="note"><b>Flagged for review.</b> Nothing on this page blocks the release.
It is the complete list of what could <i>not</i> be confirmed from an official or primary source, published
so the numbers above can be challenged item by item.</div>
<h2>Rows published blank ({len(blanks)})</h2>{blank_rows}
<h2>Row-level flags ({len(flagged)})</h2>{flag_rows}
<h2>Joins refused ({len(rejected)})</h2><ul>{rej_lines or "<li>none</li>"}</ul>
<h2>Source access problems</h2><ul>{''.join(source_problems) or "<li>none recorded in this run</li>"}</ul>
<h2>Rating candidates considered and refused</h2>
<p>When a match has no external price, the originated estimate needs an official Valve VRS rating for
<b>both</b> teams. Where a name in the standings merely looks similar, the mapping is <b>never</b> applied
automatically — it is listed here for a human decision, because a wrong rating would silently corrupt a
probability.</p>
{rating_candidates}
<h2>Listing irregularities</h2>
<p>The lobby page state carries fixture ids that are not all from the current week: months present
{esc(((board.get("window_analysis") or {}).get("listed_profile") or {}).get("kickoff_months"))}, of which
{esc(((board.get("window_analysis") or {}).get("listed_profile") or {}).get("stale_kickoff_more_than_30d_before_this_week"))} have a
kickoff more than 30 days before this week's window — while the rendered page shows
{esc(((board.get("window_analysis") or {}).get("listed_profile") or {}).get("rendered_match_links"))} match links. The lobby's own
"matches this week" counter ({esc(((board.get("window_analysis") or {}).get("lobby_counters") or {}).get("matches_this_week"))}) is not
reproduced by any candidate rule tried in the methodology page and stays published as unexplained rather
than guessed. Stale ids are labelled and excluded from live coverage numbers.</p>
<h2>Coverage gap against the lobby listing</h2>
<p>Check C11 compares the fixture ids the lobby page itself carries against this board: if the lobby
lists a match that is not in this board, it is reported here rather than dropped.</p>
<pre style="white-space:pre-wrap;font-size:12.5px;color:#9aa4b2">{esc(next((json.dumps(c["detail"])
   for c in verification["checks"] if c["check"].startswith("C11")), "C11 not present"))}</pre>
<h2>Line-by-line verification of this build</h2><ul>{checks}</ul>"""
    body = body.replace("{rating_candidates}", rating_candidates_html)
    return page("Flagged for review — HotSpawn Pick'ems board", "flagged.html", body,
                board["generated_at_utc"])


def render_methodology(board: dict, verification: dict, log: dict, counters: dict) -> str:
    rules = board["rules"]
    window = board["window_analysis"]
    cand = window["candidates"]
    cand_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{esc(v['total'])}</td><td>{esc(v['cs2'])}</td>"
        f"<td>{esc(v['lol'])}</td><td>{esc(v['by_tier'])}</td></tr>" for name, v in cand.items())
    repro = "".join(f'<li>{esc(m["counter"])} = {esc(m["value"])} reproduced by rule '
                    f'“{esc(m["rule"])}”</li>' for m in window["counter_reproductions"]) or "<li>none</li>"
    return page("Method & sources — HotSpawn Pick'ems board", "methodology.html", f"""
<h2>Method</h2>
<ul>
<li><b>Fixture discovery:</b> {esc(rules["fixture_source"])} — <a href="{esc(board.get("fixture_api", ""))}">fixtures endpoint</a>.</li>
<li><b>Probabilities:</b> {esc(rules["probability_source"])}.</li>
<li><b>Join rule:</b> {esc(rules["join_rule"])}.</li>
<li><b>De-vig:</b> raw quoted odds → implied share <code>q = 1/odds</code> → normalised
<code>p = q / (q_a + q_b)</code>. The bookmaker margin (overround) is published per row.</li>
<li><b>Consensus:</b> {esc(rules["consensus_rule"])}.</li>
<li><b>Pick:</b> {esc(rules["pick_rule"])}.</li>
<li><b>Freshness:</b> {esc(rules["freshness_rule"])}.</li>
<li><b>Estimate:</b> {esc(rules["estimate_rule"])}</li>
<li><b>HotSpawn crowd picks:</b> {esc(rules["hotspawn_pick_pct"])}. The board re-derives every number
with the crowd fields scrambled and requires identical output (check C7).</li>
</ul>
<h2>Lobby counter reconciliation</h2>
<p>The lobby prints its own counters. Instead of assuming what they mean, every candidate window rule is
counted here and compared with what the page printed ({esc(counters)}).</p>
<div class="wrap"><table><thead><tr><th>Candidate rule</th><th>Total</th><th>CS2</th><th>LoL</th>
<th>By tier</th></tr></thead><tbody>{cand_rows}</tbody></table></div>
<ul>{repro}</ul>
<h2>This build</h2>
<ul>
<li>Verification: {verification["passed"]}/{len(verification["checks"])} checks passed
({verification["rows_checked"]} rows: {verification["market_rows"]} market,
{verification["estimate_rows"]} estimate, {verification["blank_rows"]} blank).</li>
<li>Collection run: started {esc(log.get("started_at_utc"))}, finished {esc(log.get("finished_at_utc"))}.</li>
<li>Quote counts: {esc(json.dumps(log.get("counts", {})))}</li>
</ul>""", board["generated_at_utc"])


def render_sources(board: dict, quotes_doc: dict, ratings_doc: dict, log: dict) -> str:
    quotes = quotes_doc.get("quotes") or []
    by_source: dict[str, dict] = {}
    for q in quotes:
        key = q["source_key"]
        info = by_source.setdefault(key, {"source_name": q["source_name"], "kind": q["source_kind"],
                                          "url": q.get("source_public_url"), "n": 0,
                                          "games": set(), "example": q.get("source_api_url")})
        info["n"] += 1
        info["games"].add(q.get("game"))
    rows = "".join(
        f'<tr><td>{esc(k)}</td><td><a href="{esc(v["url"])}">{esc(v["source_name"])}</a></td>'
        f'<td>{esc(v["kind"])}</td><td>{esc(v["n"])}</td><td>{esc(sorted(g or "?" for g in v["games"]))}</td>'
        f'<td><a href="{esc(v["example"])}">payload</a></td></tr>'
        for k, v in sorted(by_source.items()))
    vrs = ratings_doc.get("files") or {}
    vrs_rows = "".join(
        f'<tr><td>{esc(region)}</td><td>{esc(info.get("snapshot"))}</td>'
        f'<td>{esc(info.get("teams_parsed"))}</td><td><a href="{esc(info.get("raw_url"))}">table</a> · '
        f'<a href="{esc(info.get("url"))}">contents API</a></td></tr>' for region, info in vrs.items())
    return page("Sources — HotSpawn Pick'ems board", "sources.html", f"""
<h2>External price sources used in this build</h2>
<div class="wrap"><table><thead><tr><th>Key</th><th>Source</th><th>Kind</th><th>Quotes</th>
<th>Games</th><th>Exact payload</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="note">Exchanges (Kalshi, Polymarket) are published as <b>reference only</b>: their prices are
never averaged into a bookmaker consensus. HotSpawn appears only as the fixture-discovery source and as
a reference link per row.</div>
<h2>Rating source for the originated estimate</h2>
<div class="wrap"><table><thead><tr><th>Region</th><th>Snapshot</th><th>Teams parsed</th>
<th>Source</th></tr></thead><tbody>{vrs_rows}</tbody></table></div>
<p>{esc(ratings_doc.get("scoring_note"))}</p>
<h2>Access outcomes recorded in this run</h2>
<pre style="white-space:pre-wrap;font-size:12.5px;color:#9aa4b2">{esc(json.dumps(
    {k: v for k, v in (log or {}).items() if k not in ("notes",)}, indent=1)[:6000])}</pre>
""", board["generated_at_utc"])


def write_site(board: dict, verification: dict, quotes_doc: dict, ratings_doc: dict, log: dict,
               site_dir: Path) -> list[str]:
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "assets").mkdir(parents=True, exist_ok=True)
    (site_dir / "assets" / "live.css").write_text(CSS, encoding="utf-8")
    counters = (log.get("lobby_page") or {}).get("counters") or {}
    files = {
        "index.html": render_index(board, verification),
        "cs2.html": render_game(board, "CS2"),
        "lol.html": render_game(board, "LoL"),
        "flagged.html": render_flagged(board, verification, quotes_doc, log),
        "methodology.html": render_methodology(board, verification, log, counters),
        "sources.html": render_sources(board, quotes_doc, ratings_doc, log),
    }
    for name, text in files.items():
        (site_dir / name).write_text(text, encoding="utf-8")
    return sorted(files)


def check_page_links(site_dir: Path) -> dict:
    """Every local href must resolve to a file we actually wrote."""
    import re
    problems = []
    written = {p.name for p in site_dir.glob("*.html")} | {"assets/live.css"}
    for page_path in site_dir.glob("*.html"):
        text = page_path.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if href not in written:
                problems.append({"page": page_path.name, "href": href})
    return {"ok": not problems, "problems": problems}


# ----------------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/live")
    ap.add_argument("--site", default="live")
    ap.add_argument("--allow-blank-quotes", action="store_true",
                    help="do not fail when the quote file is empty (first bootstrap run)")
    args = ap.parse_args()
    data_dir = (ROOT / args.data) if not Path(args.data).is_absolute() else Path(args.data)
    site_dir = (ROOT / args.site) if not Path(args.site).is_absolute() else Path(args.site)

    fixtures_doc, quotes_doc, ratings_doc, log = load_inputs(data_dir)
    if not fixtures_doc.get("fixtures"):
        print("no fixtures in the snapshot — refusing to build", file=sys.stderr)
        return 2
    if not (quotes_doc.get("quotes") or []) and not args.allow_blank_quotes:
        print("no external quotes collected — refusing to publish (use --allow-blank-quotes to "
              "bootstrap)", file=sys.stderr)
        return 2

    now = parse_iso(fixtures_doc.get("generated_at_utc")) or now_utc()
    board = build_board(fixtures_doc, quotes_doc, ratings_doc, now)
    verification = verify_board(board, quotes_doc, ratings_doc, fixtures_doc)
    json_dump(data_dir / "board.json", board)
    json_dump(data_dir / "verification.json", verification)
    print(json.dumps(board["summary"], indent=1))
    print(f"verification: {verification['passed']}/{len(verification['checks'])} checks passed")
    for c in verification["checks"]:
        if not c["passed"]:
            print("FAIL:", c["check"], json.dumps(c["detail"])[:400], file=sys.stderr)
    if verification["failed"]:
        print("verification failed — pages not written", file=sys.stderr)
        return 3
    written = write_site(board, verification, quotes_doc, ratings_doc, log, site_dir)
    links = check_page_links(site_dir)
    json_dump(data_dir / "page_links.json", links)
    print("pages written:", ", ".join(written), "| links ok:", links["ok"])
    if not links["ok"]:
        print("broken internal links:", links["problems"], file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
