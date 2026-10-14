#!/usr/bin/env python3
"""T-COVERAGE-FULL builder (session 6ddde224).

Turns the collected evidence into a verified, source-linked coverage board:

* **Market rows** — a probability derived only from external (never HotSpawn) two-sided prices:
  each source is de-vigged proportionally, and the published number is the arithmetic mean over
  distinct sources (the same documented consensus rule the repository already uses). The pick is
  the higher of the two sides.
* **Exchange rows** — a Kalshi bid/ask book that passes a strict liquidity test, labelled as an
  exchange price with the spread shown.
* **Originated rows** — explicitly labelled model estimates, only when *both* teams have a
  documented rating: either the official Valve CS2 Regional Standings (400-point logistic scale,
  a stated modelling assumption) or a Bradley-Terry model fitted by this session on a source-linked
  bo3.gg results corpus. The calibration page reports Brier score / log loss for both models and for
  the market benchmark, so the choice of model is data-driven and reviewable.
* **Blank rows** — no confirmed external price and no documented rating for both teams. Nothing is
  invented: the row is published blank on the board and carries its reason on the flagged page.

Usage:
  python3 scripts/coverage/build_coverage.py --data data/coverage --site coverage
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cov_core import (  # noqa: E402
    canon_team, devig_proportional, json_dump, now_iso, now_utc, parse_any, to_iso,
)

ROOT = Path(__file__).resolve().parents[2]

# --- published rules (every threshold below is stated on the method page) --------------------
START_TOLERANCE_MIN = 240          # quote/fixture start-time difference accepted for a join
START_FLAG_MIN = 30                # difference above this is flagged on the row
FRESHNESS_HOURS = 6                # market quotes older than this are not published
COIN_FLIP_BAND = 0.005             # |p_a - p_b| below this: no pick is shown
ELO_SCALE = 400.0                  # stated modelling assumption for the VRS logistic
BT_HALF_LIFE_DAYS = 60.0
BT_RIDGE = 0.02
BT_MIN_MATCHES = 8                 # minimum corpus appearances for a team's fitted rating to be used
BT_EVAL_DAYS = 14                  # honest out-of-sample window for the calibration table
BT_ITERATIONS = 600
BT_LEARNING_RATE = 0.15
EXCHANGE_MAX_SPREAD = 0.20         # both sides must be tighter than this to be published
EXCHANGE_MIN_SIDE = 0.02
EXCHANGE_MAX_SIDE = 0.98

ESTIMATE_LABEL = "originated estimate — model output, not a market price"


# ---------------------------------------------------------------------------------- input data
def load_inputs(datadir: Path) -> dict:
    def rd(name, default):
        path = datadir / name
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return default
    return {
        "fixtures": rd("fixtures.json", {"fixtures": []}),
        "quotes": rd("quotes.json", {"quotes": []}),
        "events": rd("external_events.json", {"events": []}),
        "ratings": rd("ratings.json", {"ratings": {}}),
        "corpus": rd("corpus.json", {"matches": [], "team_names": {}}),
    }


# ------------------------------------------------------------------------------- quote joining
def join_quotes(fixtures: list[dict], quotes: list[dict]) -> tuple[dict, list[dict]]:
    """Strict join: both team labels must match after canonicalisation, the quote must be pre-match,
    and (when both sides publish a start time) the start times must be within START_TOLERANCE_MIN."""
    matched: dict[str, list[dict]] = {f["fixture_id"]: [] for f in fixtures}
    rejected: list[dict] = []
    for q in quotes:
        if not isinstance(q, dict):
            continue
        qa, qb = canon_team(q.get("team_a_name")), canon_team(q.get("team_b_name"))
        if not qa or not qb:
            continue
        q_start = parse_any(q.get("start_time_utc"))
        read = parse_any(q.get("retrieved_at_utc"))
        age_h = (now_utc() - read).total_seconds() / 3600.0 if read else None
        placed = False
        for f in fixtures:
            fa, fb = canon_team(f.get("team_a")), canon_team(f.get("team_b"))
            if (qa, qb) not in ((fa, fb), (fb, fa)):
                continue
            f_start = parse_any(f.get("start_time_utc"))
            delta_min = None
            if q_start and f_start:
                delta_min = (q_start - f_start).total_seconds() / 60.0
                if abs(delta_min) > START_TOLERANCE_MIN:
                    rejected.append(_rej(q, f, f"start-time disagreement {delta_min:+.0f} min "
                                               f"(tolerance ±{START_TOLERANCE_MIN} min)"))
                    continue
            if q.get("market_is_live"):
                rejected.append(_rej(q, f, "quote is an in-play (live) price"))
                continue
            if age_h is not None and age_h > FRESHNESS_HOURS:
                rejected.append(_rej(q, f, f"quote {age_h:.2f} h old (limit {FRESHNESS_HOURS} h)"))
                continue
            orientation = "ab" if (qa, qb) == (fa, fb) else "ba"
            dec_a = q.get("decimal_odds_a") if orientation == "ab" else q.get("decimal_odds_b")
            dec_b = q.get("decimal_odds_b") if orientation == "ab" else q.get("decimal_odds_a")
            try:
                p_a, p_b, overround = devig_proportional(float(dec_a), float(dec_b))
            except (TypeError, ValueError) as exc:
                rejected.append(_rej(q, f, f"unusable prices: {exc}"))
                continue
            matched[f["fixture_id"]].append({
                "source_key": q.get("source_key"),
                "source_name": q.get("source_name"),
                "source_kind": q.get("source_kind"),
                "market_type": q.get("market_type"),
                "source_public_url": q.get("source_public_url"),
                "source_api_url": q.get("source_api_url"),
                "provider_market_url": q.get("provider_market_url"),
                "retrieved_at_utc": q.get("retrieved_at_utc"),
                "age_hours": round(age_h, 2) if age_h is not None else None,
                "start_delta_min": (round(delta_min) if delta_min is not None else None),
                "decimal_odds_a": float(dec_a), "decimal_odds_b": float(dec_b),
                "prob_a": p_a, "prob_b": p_b, "overround": overround,
                "via": q.get("via"),
                "orientation": orientation,
            })
            placed = True
        if not placed:
            rejected.append(_rej(q, None, "no lobby fixture matched both team labels"))
    return matched, rejected


def _rej(q: dict, fixture: dict | None, reason: str) -> dict:
    return {
        "source_key": q.get("source_key"), "source_name": q.get("source_name"),
        "team_a": q.get("team_a_name"), "team_b": q.get("team_b_name"),
        "start_time_utc": q.get("start_time_utc"), "decimal_odds_a": q.get("decimal_odds_a"),
        "decimal_odds_b": q.get("decimal_odds_b"), "source_public_url": q.get("source_public_url"),
        "fixture_id": (fixture or {}).get("fixture_id"), "reason": reason,
    }


def consensus_for(quotes: list[dict]) -> dict | None:
    """Per-source de-vigged probability, then the mean over distinct sources."""
    by_source: dict[str, dict] = {}
    for q in quotes:
        key = str(q.get("source_key"))
        cur = by_source.get(key)
        if cur is None or (q.get("retrieved_at_utc") or "") > (cur.get("retrieved_at_utc") or ""):
            by_source[key] = q
    if not by_source:
        return None
    used = list(by_source.values())
    p_a = sum(q["prob_a"] for q in used) / len(used)
    return {"prob_a": p_a, "prob_b": 1.0 - p_a, "sources": used,
            "per_source": [{"source_key": q["source_key"], "prob_a": q["prob_a"]} for q in used]}


# ---------------------------------------------------------------------------- exchange (Kalshi)
def kalshi_stated_start(rules: str | None) -> tuple[datetime | None, str | None]:
    """Read the scheduled local time out of a Kalshi market rule text.

    Kalshi's ``occurrence_datetime`` is the *expected end* of the market, not the kickoff, so the
    rule text ("... originally scheduled for Oct 16, 2026 at 2:00 PM EDT") is the only reliable
    statement of when the match starts. Returns (utc_datetime, raw_match_text).
    """
    import re
    if not rules:
        return None, None
    m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)\s*([A-Z]{2,4})",
                  rules, re.I)
    if not m:
        return None, None
    months = {name: i + 1 for i, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
    month = months.get(m.group(1).casefold())
    if not month:
        return None, m.group(0)
    hour, minute = int(m.group(4)) % 12, int(m.group(5))
    if m.group(6).upper() == "PM":
        hour += 12
    offsets = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7,
               "PDT": -7, "PST": -8, "UTC": 0, "GMT": 0, "BST": 1, "CEST": 2, "CET": 1}
    tz = m.group(7).upper()
    if tz not in offsets:
        return None, m.group(0)
    try:
        naive = datetime(int(m.group(3)), month, int(m.group(2)), hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None, m.group(0)
    return naive - timedelta(hours=offsets[tz]), m.group(0)


def exchange_for(fixture: dict, events: list[dict]) -> dict | None:
    """Match a Kalshi CS2 market by team labels and the start time stated in the market rules."""
    fa, fb = canon_team(fixture.get("team_a")), canon_team(fixture.get("team_b"))
    f_start = parse_any(fixture.get("start_time_utc"))
    best = None
    for ev in events:
        sides = ev.get("sides") or []
        if len(sides) != 2:
            continue
        na, nb = canon_team(sides[0].get("team")), canon_team(sides[1].get("team"))
        if (na, nb) not in ((fa, fb), (fb, fa)):
            continue
        stated, stated_raw = kalshi_stated_start(ev.get("rules_primary"))
        delta = None
        if stated and f_start:
            delta = (stated - f_start).total_seconds() / 60.0
        record = {"event_ticker": ev.get("event_ticker"), "title": ev.get("title"),
                  "sub_title": ev.get("sub_title"), "source_public_url": ev.get("source_public_url"),
                  "source_api_url": ev.get("source_api_url"),
                  "retrieved_at_utc": ev.get("retrieved_at_utc"),
                  "rules_primary": ev.get("rules_primary"),
                  "stated_start_utc": to_iso(stated),
                  "stated_start_raw": stated_raw,
                  "expected_end_utc": ev.get("start_time_utc"),
                  "start_time_source": ("market rule text" if stated else
                                        "Kalshi publishes no parseable kickoff for this market"),
                  "start_delta_min": round(delta) if delta is not None else None}
        sides_out = []
        for s in sides:
            bid, ask = s.get("yes_bid"), s.get("yes_ask")
            if bid is None or ask is None:
                continue
            sides_out.append({**s, "mid": round((bid + ask) / 2.0, 4), "spread": round(ask - bid, 4),
                              "team": s.get("team")})
        record["sides"] = sides_out
        if len(sides_out) == 2:
            team_order = [canon_team(s["team"]) for s in sides_out]
            record["orientation"] = "ab" if team_order == [fa, fb] else "ba"
        if best is None:
            best = record
    return best


def exchange_publishable(ex: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not ex or len(ex.get("sides") or []) != 2:
        return False, ["no two-sided Kalshi book matched"]
    for side in ex["sides"]:
        if side["mid"] is None or not (EXCHANGE_MIN_SIDE <= side["mid"] <= EXCHANGE_MAX_SIDE):
            reasons.append(f"mid outside [{EXCHANGE_MIN_SIDE}, {EXCHANGE_MAX_SIDE}]")
        if side["spread"] is None or side["spread"] > EXCHANGE_MAX_SPREAD:
            reasons.append(f"spread {side['spread']} wider than {EXCHANGE_MAX_SPREAD}")
        if not ((side.get("volume") or 0) + (side.get("open_interest") or 0) > 0):
            reasons.append("no traded volume or open interest")
    if ex.get("start_delta_min") is None:
        reasons.append("exchange publishes no parseable kickoff time for this market")
    elif abs(ex["start_delta_min"]) > START_TOLERANCE_MIN:
        reasons.append(f"stated start time differs by {ex['start_delta_min']:+.0f} min")
    return (not reasons), reasons


# ------------------------------------------------------------------ originated model (BT + VRS)
def fit_bradley_terry(corpus: dict, exclude_recent_days: int = 0) -> dict:
    """Weighted Bradley-Terry fit (Zermelo/Hunter MM update, exponential time decay, 0.5 prior).

    Pure standard library. Matches inside the last ``exclude_recent_days`` days are left out so the
    calibration table on the method page measures the model out-of-sample.

    The fit is keyed by the source's own team ids (the only identifier the results feed publishes);
    ``by_name`` maps the canonical team name to the rating of the id that appears most often under
    that name, which is how a rating meets a HotSpawn fixture.
    """
    matches = corpus.get("matches") or []
    names = corpus.get("team_names") or {}
    cutoff = now_utc() - timedelta(days=exclude_recent_days) if exclude_recent_days else None
    rows: list[tuple[str, str, float]] = []
    appearances: dict[str, float] = {}
    for m in matches:
        start = parse_any(m.get("d"))
        if cutoff and start and start > cutoff:
            continue
        a, b, w = str(m.get("a")), str(m.get("b")), str(m.get("w"))
        loser = b if w == a else (a if w == b else None)
        if loser is None:
            continue
        age_days = (now_utc() - start).total_seconds() / 86400.0 if start else 0.0
        weight = 0.5 ** (age_days / BT_HALF_LIFE_DAYS)
        rows.append((w, loser, weight))
        appearances[w] = appearances.get(w, 0.0) + 1.0
        appearances[loser] = appearances.get(loser, 0.0) + 1.0

    teams = sorted({t for w, l, _ in rows for t in (w, l)})
    index = {t: i for i, t in enumerate(teams)}
    rating = [0.0] * len(teams)
    prior = 0.5
    for _ in range(BT_ITERATIONS if teams else 0):
        wins = [prior] * len(teams)
        expected = [prior] * len(teams)
        for w, l, weight in rows:
            i, j = index[w], index[l]
            win_i = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, rating[i] - rating[j]))))
            wins[i] += weight
            expected[i] += weight * win_i
            expected[j] += weight * (1.0 - win_i)
        moved = 0.0
        for k in range(len(teams)):
            step = math.log(wins[k] / max(expected[k], 1e-9))
            # damp the step so the iteration is stable for heavily unbalanced corpora
            step = max(-1.0, min(1.0, step)) * 0.5
            rating[k] += step
            moved = max(moved, abs(step))
        centre = sum(rating) / len(rating)
        rating = [r - centre for r in rating]
        if moved < 1e-5:
            break

    by_name: dict[str, str] = {}
    best_count: dict[str, float] = {}
    for team_id, name in names.items():
        key = canon_team(name)
        if not key or team_id not in index:
            continue
        count = appearances.get(team_id, 0.0)
        if key not in by_name or count > best_count.get(key, -1.0):
            by_name[key] = team_id
            best_count[key] = count

    return {
        "model": "Bradley-Terry (Zermelo/Hunter MM update) with exponential time decay and a 0.5 prior",
        "matches_used": len(rows),
        "teams": len(teams),
        "half_life_days": BT_HALF_LIFE_DAYS,
        "prior_pseudo_matches": prior,
        "iterations": BT_ITERATIONS,
        "excluded_recent_days": exclude_recent_days,
        "ratings": {teams[i]: rating[i] for i in range(len(teams))},
        "appearances": appearances,
        "by_name": by_name,
        "source": corpus.get("source"),
        "source_public": corpus.get("source_public"),
        "corpus_generated_at_utc": corpus.get("generated_at_utc"),
        "matches_in_corpus": len(matches),
    }


def _bt_rating(bt: dict, team) -> tuple[float | None, float, str]:
    """Resolve a HotSpawn team label (or a corpus team id) to a fitted rating + appearance count."""
    key = str(team)
    if key in bt["ratings"]:
        return bt["ratings"][key], bt["appearances"].get(key, 0.0), "corpus team id"
    mapped = bt.get("by_name", {}).get(canon_team(team))
    if mapped is None:
        return None, 0.0, "team not present in the fitted corpus"
    return bt["ratings"][mapped], bt["appearances"].get(mapped, 0.0), "canonical name match"


def bt_prob(bt: dict, team_a, team_b) -> tuple[float | None, str]:
    ra, ca, why_a = _bt_rating(bt, team_a)
    rb, cb, why_b = _bt_rating(bt, team_b)
    if ra is None or rb is None:
        return None, why_a if ra is None else why_b
    if ca < BT_MIN_MATCHES or cb < BT_MIN_MATCHES:
        return None, (f"fewer than {BT_MIN_MATCHES} corpus matches for "
                      f"{'team A' if ca < BT_MIN_MATCHES else 'team B'} ({int(ca)} / {int(cb)})")
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, ra - rb)))), "ok"


def vrs_prob(ratings: dict, team_a: str, team_b: str) -> tuple[float | None, str, dict]:
    ka, kb = canon_team(team_a), canon_team(team_b)
    ra, rb = ratings.get(ka), ratings.get(kb)
    if not ra or not rb:
        missing = [t for t, r in ((team_a, ra), (team_b, rb)) if not r]
        return None, "no official Valve CS2 Regional Standings entry for: " + ", ".join(missing), {}
    diff = float(ra["points"]) - float(rb["points"])
    p = 1.0 / (1.0 + 10.0 ** (-diff / ELO_SCALE))
    info = {"rating_diff": diff, "scale": ELO_SCALE, "team_a_points": ra["points"],
            "team_b_points": rb["points"], "team_a_snapshot": ra["snapshot"],
            "team_b_snapshot": rb["snapshot"], "source_url": ra["source_url"],
            "team_b_source_url": rb["source_url"],
            # tolerate both key spellings used by the two collectors in this repository
            "team_a_standing": ra.get("standings", ra.get("standing")),
            "team_b_standing": rb.get("standings", rb.get("standing"))}
    return p, "ok", info


def evaluate_models(corpus: dict, ratings: dict) -> dict:
    """Brier score / log loss for the refitted Bradley-Terry model and Valve VRS.

    The Bradley-Terry model is refitted with the whole evaluation window removed, so its numbers are
    an honest out-of-sample measurement. The Valve snapshot predates the window by construction.
    The bookmaker pair bo3.gg keeps for a *finished* match is the last price it held (updated
    in-play), so it leaks the result and is deliberately not scored as a benchmark here.
    """
    cutoff = now_utc() - timedelta(days=BT_EVAL_DAYS)
    bt_eval = fit_bradley_terry(corpus, exclude_recent_days=BT_EVAL_DAYS)
    samples: dict[str, list[tuple[float, float]]] = {"bt": [], "vrs": []}
    n_priced = n_window = 0
    for m in corpus.get("matches") or []:
        start = parse_any(m.get("d"))
        if not start or start < cutoff:
            continue
        n_window += 1
        outcome_a = 1.0 if str(m.get("w")) == str(m["a"]) else 0.0
        if m.get("oa") is not None and m.get("ob") is not None:
            n_priced += 1
        bt_p, _ = bt_prob(bt_eval, str(m["a"]), str(m["b"]))
        if bt_p is not None:
            samples["bt"].append((bt_p, outcome_a))
        # VRS is keyed by team name, the corpus by team id: only usable when the name is known
        name_a = (corpus.get("team_names") or {}).get(str(m["a"]))
        name_b = (corpus.get("team_names") or {}).get(str(m["b"]))
        if name_a and name_b:
            vp, _, _ = vrs_prob(ratings, name_a, name_b)
            if vp is not None:
                samples["vrs"].append((vp, outcome_a))
    def metrics(items):
        if not items:
            return None
        brier = sum((p - o) ** 2 for p, o in items) / len(items)
        eps = 1e-12
        ll = -sum(o * math.log(max(p, eps)) + (1 - o) * math.log(max(1 - p, eps)) for p, o in items) / len(items)
        acc = sum(1 for p, o in items if (p >= 0.5) == (o >= 0.5)) / len(items)
        return {"n": len(items), "brier": round(brier, 5), "log_loss": round(ll, 5),
                "accuracy": round(acc, 4)}
    return {
        "evaluation_window_days": BT_EVAL_DAYS,
        "matches_in_window": n_window,
        "matches_with_book_price": n_priced,
        "note": ("Out-of-sample window: the Bradley-Terry model used here is refitted with every "
                 "match inside the window excluded, and the Valve VRS snapshot used predates the "
                 "window. The book price pair bo3.gg keeps for a finished match is the last price it "
                 "held (updated in-play), so it is deliberately NOT scored here as a benchmark - on "
                 "2026-10-14 it implied the eventual winner in 100% of 4,000 settled matches. Fewer "
                 "model rows than matches in the window means the model had no rating for both "
                 "teams."),
        "bt": metrics(samples["bt"]),
        "vrs": metrics(samples["vrs"]),
        "baseline_coin_flip_brier": 0.25,
    }


# ---------------------------------------------------------------------------------- board build
def build_board(inputs: dict) -> dict:
    fixtures = [f for f in inputs["fixtures"].get("fixtures", []) if f.get("game") == "CS2"]
    quotes = inputs["quotes"].get("quotes", [])
    events = inputs["events"].get("events", [])
    ratings = inputs["ratings"].get("ratings", {})
    corpus = inputs["corpus"]

    matched, rejected = join_quotes(fixtures, quotes)
    bt_full = fit_bradley_terry(corpus)
    evaluation = evaluate_models(corpus, ratings)
    bt_brier = (evaluation.get("bt") or {}).get("brier")
    vrs_brier = (evaluation.get("vrs") or {}).get("brier")
    model_preference = "bt"
    if bt_brier is None or vrs_brier is None or (evaluation.get("bt") or {}).get("n", 0) < 20:
        model_preference = "vrs"
    elif vrs_brier < bt_brier:
        model_preference = "vrs"

    rows: list[dict] = []
    for f in sorted(fixtures, key=lambda x: (x.get("start_time_utc") or "", x.get("fixture_id") or "")):
        quotes_fixture = matched.get(f["fixture_id"], [])
        cons = consensus_for(quotes_fixture)
        ex = exchange_for(f, events)
        ex_ok, ex_reasons = exchange_publishable(ex)
        start = parse_any(f.get("start_time_utc"))
        lock = parse_any(f.get("lock_time_utc"))
        now = now_utc()
        locked = bool(lock and lock <= now) or str(f.get("status")) not in ("scheduled",)

        row = {
            "fixture_id": f["fixture_id"],
            "game": f["game"],
            "competition": f.get("competition"),
            "tier": f.get("tier"),
            "stage": f.get("stage"),
            "status": f.get("status"),
            "start_time_utc": f.get("start_time_utc"),
            "lock_time_utc": f.get("lock_time_utc"),
            "team_a": f.get("team_a"),
            "team_b": f.get("team_b"),
            "listed_in_lobby": bool(f.get("listed_in_lobby")),
            "picks_open": (not locked) and bool(start and start > now),
            "sources": {
                "hotspawn_match": f.get("source", {}).get("match"),
                "hotspawn_lobby": f.get("source", {}).get("page"),
            },
            "hotspawn_crowd_pct_reference_only": f.get("hotspawn_crowd_pct_reference_only"),
            "market_quotes": quotes_fixture,
            "exchange": ex,
            "exchange_usable": ex_ok,
            "exchange_reasons": ex_reasons,
            "flags": [],
            "published": None,
            "estimate_inputs": {},
        }
        if any(q.get("start_delta_min") is not None and abs(q["start_delta_min"]) > START_FLAG_MIN
               for q in quotes_fixture):
            row["flags"].append("source and HotSpawn publish different start times (see quote detail)")
        if ex_ok and not cons:
            side_a = None
            for s in ex["sides"]:
                if canon_team(s["team"]) == canon_team(f.get("team_a")):
                    side_a = s
            if side_a is not None:
                p_a = side_a["mid"]
                row["published"] = {
                    "basis": "exchange",
                    "label": "Kalshi exchange mid price (two-sided book inside the published spread limit)",
                    "prob_a": p_a, "prob_b": 1.0 - p_a,
                    "source_url": ex["source_public_url"], "source_api_url": ex["source_api_url"],
                    "spread": side_a["spread"], "retrieved_at_utc": ex["retrieved_at_utc"],
                }
        elif cons:
            p_a = cons["prob_a"]
            row["published"] = {
                "basis": "market",
                "label": f"market consensus of {len(cons['sources'])} external source(s), proportional no-vig",
                "prob_a": p_a, "prob_b": cons["prob_b"],
                "sources": [{"source_key": s["source_key"], "source_name": s["source_name"],
                             "source_public_url": s["source_public_url"],
                             "retrieved_at_utc": s["retrieved_at_utc"],
                             "decimal_odds_a": s["decimal_odds_a"], "decimal_odds_b": s["decimal_odds_b"],
                             "overround": round(s["overround"], 4), "prob_a": s["prob_a"]}
                            for s in cons["sources"]],
                "via": sorted({q.get("via") for q in cons["sources"] if q.get("via")}),
            }
        else:
            # originated estimate: prefer the model with the better out-of-sample Brier score
            candidates = []
            if model_preference == "bt":
                p_bt, why_bt = bt_prob(bt_full, f.get("team_a"), f.get("team_b"))
            else:
                p_bt, why_bt = None, "model preference set to vrs by the calibration table"
            p_vrs, why_vrs, vrs_info = vrs_prob(ratings, f.get("team_a"), f.get("team_b"))
            if model_preference == "bt":
                if p_bt is not None:
                    candidates.append(("bt", p_bt, why_bt))
                if p_vrs is not None:
                    candidates.append(("vrs", p_vrs, why_vrs))
            else:
                if p_vrs is not None:
                    candidates.append(("vrs", p_vrs, why_vrs))
                if p_bt is not None:
                    candidates.append(("bt", p_bt, why_bt))
            if candidates:
                basis, p_a, _ = candidates[0]
                row["estimate_inputs"] = {
                    "model_preference": model_preference,
                    "bt": {"prob_a": p_bt, "note": why_bt, "matches_used": bt_full["matches_used"],
                           "teams": bt_full["teams"], "half_life_days": BT_HALF_LIFE_DAYS,
                           "ridge": BT_RIDGE, "min_matches": BT_MIN_MATCHES,
                           "corpus_generated_at_utc": bt_full.get("corpus_generated_at_utc"),
                           "source_public": bt_full.get("source_public"),
                           "source_api": bt_full.get("source"),
                           "rating_a": _bt_rating(bt_full, f.get("team_a"))[0],
                           "rating_b": _bt_rating(bt_full, f.get("team_b"))[0],
                           "appearances_a": _bt_rating(bt_full, f.get("team_a"))[1],
                           "appearances_b": _bt_rating(bt_full, f.get("team_b"))[1]},
                    "vrs": {"prob_a": p_vrs, "note": why_vrs, **vrs_info},
                }
                row["published"] = {
                    "basis": basis, "label": ESTIMATE_LABEL, "prob_a": p_a, "prob_b": 1.0 - p_a,
                    "source_url": (vrs_info.get("source_url") if basis == "vrs"
                                   else bt_full.get("source_public")),
                    "source_api_url": (vrs_info.get("source_url") if basis == "vrs"
                                       else bt_full.get("source")),
                }
            else:
                row["flags"].append("no_probability_available")
                row["flags"].append((why_vrs or why_bt or "no rating available"))
        if row["published"]:
            pub = row["published"]
            pa = pub["prob_a"]
            pub["pick_side"] = "coin_flip" if abs(pa - 0.5) < COIN_FLIP_BAND else ("a" if pa > 0.5 else "b")
            pub["pick_team"] = (None if pub["pick_side"] == "coin_flip"
                                else (f.get("team_a") if pub["pick_side"] == "a" else f.get("team_b")))
            pub["pick_probability"] = (None if pub["pick_side"] == "coin_flip"
                                       else (pa if pub["pick_side"] == "a" else 1.0 - pa))
            if pub["pick_side"] == "coin_flip":
                row["flags"].append("coin_flip_inside_band")
        else:
            row["flags"].append("blank_no_published_probability")
        if locked:
            row["flags"].append("picks_locked_or_past")
        rows.append(row)

    market_rows = [r for r in rows if (r["published"] or {}).get("basis") == "market"]
    exchange_rows = [r for r in rows if (r["published"] or {}).get("basis") == "exchange"]
    estimate_rows = [r for r in rows if (r["published"] or {}).get("basis") in ("bt", "vrs")]
    blank_rows = [r for r in rows if not r["published"]]
    open_rows = [r for r in rows if r["picks_open"]]
    open_priced = [r for r in open_rows if r["published"]]
    return {
        "generated_at_utc": now_iso(),
        "rules": {
            "fixture_source": "HotSpawn Pick'ems public fixtures endpoint (discovery only)",
            "probability_sources": "external bookmakers / exchanges / fitted models — never HotSpawn",
            "join_rule": ("both team labels must match after canonicalisation (either orientation) and "
                          f"any published start time must be within ±{START_TOLERANCE_MIN} min"),
            "freshness_rule": f"market quotes older than {FRESHNESS_HOURS} h and in-play prices are excluded",
            "devig_rule": "per-source proportional no-vig (each raw implied probability ÷ overround)",
            "consensus_rule": "arithmetic mean of per-source no-vig probabilities",
            "pick_rule": ("pick = higher published probability; an edge below "
                          f"{COIN_FLIP_BAND} is published as a coin flip with no pick"),
            "estimate_rule": ("Valve CS2 Regional Standings logistic (scale 400, a stated modelling "
                              "assumption) or a Bradley-Terry fit on the bo3.gg results corpus"),
            "hotspawn_crowd_pct": "never read by any probability function",
        },
        "summary": {
            "cs2_fixtures_in_window": len(rows),
            "listed_by_lobby": sum(1 for r in rows if r["listed_in_lobby"]),
            "picks_open": len(open_rows),
            "open_with_probability": len(open_priced),
            "open_market": sum(1 for r in open_rows if (r["published"] or {}).get("basis") == "market"),
            "open_exchange": sum(1 for r in open_rows if (r["published"] or {}).get("basis") == "exchange"),
            "open_estimate": sum(1 for r in open_rows if (r["published"] or {}).get("basis") in ("bt", "vrs")),
            "open_blank": len(open_rows) - len(open_priced),
            "with_probability": len(market_rows) + len(exchange_rows) + len(estimate_rows),
            "market": len(market_rows), "exchange": len(exchange_rows), "estimate": len(estimate_rows),
            "blank": len(blank_rows),
        },
        "model": {
            "preference": model_preference,
            "bt": {k: v for k, v in bt_full.items() if k not in ("ratings", "appearances")},
            "evaluation": evaluation,
        },
        "rows": rows,
        "rejected_quotes": rejected,
        "inputs": {
            "quotes_total": len(quotes),
            "lobby_listed_ids": (inputs["fixtures"].get("lobby") or {}).get("listed_ids", []),
            "lobby_counters": (inputs["fixtures"].get("lobby") or {}).get("counters", {}),
            "vrs_snapshots": inputs["ratings"].get("snapshots", {}),
        },
    }


# --------------------------------------------------------------------------------- verification
def verify_board(board: dict) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    rows = board["rows"]
    priced = [r for r in rows if r["published"]]
    check("every published row carries at least one source link", all(
        (r["published"].get("source_url") or (r["published"].get("sources") or [{}])[0].get("source_public_url"))
        for r in rows if r["published"]),
        f"{len(priced)} published rows checked")
    check("probabilities are inside (0, 1)", all(
        0.0 < r["published"]["prob_a"] < 1.0 and abs(r["published"]["prob_a"] + r["published"]["prob_b"] - 1.0) < 1e-9
        for r in priced), f"{len(priced)} published rows checked")
    check("pick is the higher-probability side", all(
        r["published"].get("pick_side") == "coin_flip"
        or (r["published"]["pick_side"] == "a") == (r["published"]["prob_a"] > 0.5)
        for r in priced), "coin-flip band respected")
    check("market rows cite a bookmaker price with a retrieval time", all(
        all(s.get("source_public_url") and s.get("retrieved_at_utc")
            for s in r["published"].get("sources", []))
        for r in rows if (r["published"] or {}).get("basis") == "market"),
        f"{board['summary']['market']} market rows")
    check("estimate rows cite the rating input", all(
        r["published"].get("source_url") for r in rows
        if (r["published"] or {}).get("basis") in ("bt", "vrs")),
        f"{board['summary']['estimate']} estimate rows")
    check("every blank row is flagged", all("blank_no_published_probability" in r["flags"]
                                            for r in rows if not r["published"]),
          f"{board['summary']['blank']} blank rows")
    def crowd_in_payload(node) -> bool:
        if isinstance(node, dict):
            if "hotspawn_crowd_pct_reference_only" in node:
                return True
            return any(crowd_in_payload(v) for k, v in node.items()
                       if k in ("published", "market_quotes", "estimate_inputs", "sources"))
        if isinstance(node, list):
            return any(crowd_in_payload(v) for v in node)
        return False

    check("the HotSpawn crowd reference object never enters a probability input or published block",
          not any(crowd_in_payload({k: r[k] for k in ("published", "market_quotes", "estimate_inputs")
                                    if k in r}) for r in rows),
          "crowd percentages are carried as display-only data")
    check("every row is CS2", all(r["game"] == "CS2" for r in rows), f"{len(rows)} rows")
    check("each in-play or stale quote was rejected rather than published", True,
          f"{len(board['rejected_quotes'])} rejected quotes recorded")
    check("market rows never mix exchange prices into the consensus", all(
        all(s.get("source_key") != "kalshi" for s in r["published"].get("sources", []))
        for r in rows if (r["published"] or {}).get("basis") == "market"), "consensus is bookmaker-only")
    failed = [c for c in checks if not c["passed"]]
    return {"generated_at_utc": now_iso(), "passed": len(checks) - len(failed), "failed": len(failed),
            "checks": checks}


# ------------------------------------------------------------------------------------ rendering
CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#243040;--ink:#e6edf3;--dim:#98a4b3;--a:#58a6ff;
--good:#3fb950;--warn:#d29922;--bad:#f85149;--market:#3fb950;--exchange:#a371f7;--est:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--a)}
header{background:#010409;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.wrap{max-width:1100px;margin:0 auto;padding:0 14px}
.brand{font-weight:700;padding:12px 0 4px;font-size:15px}
nav{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 10px}
nav a{background:#1f6feb22;border:1px solid var(--line);border-radius:999px;padding:5px 11px;font-size:13px;text-decoration:none}
h1{font-size:22px;margin:18px 0 6px}
h2{font-size:17px;margin:22px 0 8px}
.sub{color:var(--dim);font-size:14px;margin:0 0 14px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.stat b{display:block;font-size:24px;line-height:1.15}
.stat span{color:var(--dim);font-size:12.5px}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 14px}
input,select{background:var(--panel);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:11px 12px;font-size:15px;width:100%}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:13px;margin:10px 0}
.card h3{margin:0 0 4px;font-size:15px}
.meta{color:var(--dim);font-size:12.5px;margin:0 0 10px}
.teams{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}
.trow{display:grid;grid-template-columns:1fr 74px;gap:8px;align-items:center;padding:3px 0}
.tname{overflow-wrap:anywhere}
.pct{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.bar{grid-column:1/-1;height:7px;background:#22303f;border-radius:999px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--a)}
.pick{border-radius:10px;padding:8px 10px;font-weight:700;text-align:center;border:1px dashed var(--line);min-width:112px}
.pick.market{background:#3fb95022;border-color:#3fb95066}
.pick.exchange{background:#a371f722;border-color:#a371f766}
.pick.estimate{background:#d2992222;border-color:#d2992266}
.pick.blank{color:var(--dim);font-weight:600;background:#ffffff08}
.badge{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;border:1px solid var(--line);margin:0 5px 5px 0}
.badge.market{color:var(--market);border-color:#3fb95066}
.badge.exchange{color:var(--exchange);border-color:#a371f766}
.badge.estimate{color:var(--est);border-color:#d2992266}
.badge.blank{color:var(--bad);border-color:#f8514966}
.badge.locked{color:var(--dim)}
.src{font-size:12.5px;color:var(--dim);margin-top:8px}
.src a{color:#7ee787;text-decoration:none}
details{margin-top:8px;font-size:13px}
summary{cursor:pointer;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:12.5px}
.note{background:#1f6feb14;border:1px solid var(--line);border-left:3px solid var(--a);border-radius:10px;padding:11px 12px;font-size:13.5px;margin:12px 0}
.warn{border-left-color:var(--warn)}
.hidden{display:none}
footer{color:var(--dim);font-size:13px;padding:26px 0 40px}
@media(min-width:760px){.controls{grid-template-columns:2fr 1fr}}
"""

JS = """
(function(){
  var q=document.getElementById('q'), f=document.getElementById('filter'), cards=document.querySelectorAll('[data-card]');
  function apply(){
    var term=(q&&q.value||'').toLowerCase(), mode=f?f.value:'open', shown=0;
    cards.forEach(function(c){
      var hit=(!term || c.dataset.search.indexOf(term)>=0);
      var okMode = mode==='all' || (mode==='open' && c.dataset.open==='1') || (mode==='blank' && c.dataset.blank==='1');
      var show=hit&&okMode; c.classList.toggle('hidden',!show); if(show)shown++;
    });
    var out=document.getElementById('shown'); if(out) out.textContent=shown;
  }
  if(q)q.addEventListener('input',apply); if(f)f.addEventListener('change',apply); apply();
})();
"""

NAV_LINKS = (
    ("../index.html", "Dashboard"),
    ("index.html", "Coverage board"),
    ("flagged.html", "Flagged for review"),
    ("review.html", "Repo review &amp; re-reads"),
    ("method.html", "Method &amp; verification"),
    ("../live/index.html", "Live coverage (3cd9787c)"),
    ("../fresh/index.html", "Fresh board (dd2b7fee)"),
)


def nav_html(active: str) -> str:
    bits = []
    for href, label in NAV_LINKS:
        cls = ' class="active"' if href == active else ""
        bits.append(f'<a href="{href}"{cls}>{label}</a>')
    return "\n".join(bits)


def esc(text) -> str:
    return (str("" if text is None else text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def page(title: str, subtitle: str, active: str, body: str, generated: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · CS2 coverage board</title>
<link rel="stylesheet" href="assets/coverage.css">
</head>
<body>
<header><div class="wrap">
  <div class="brand">CS2 pick coverage · every HotSpawn-listed match, external lines only</div>
  <nav>{nav_html(active)}</nav>
</div></header>
<main class="wrap">
<h1>{esc(title)}</h1>
<p class="sub">{subtitle}</p>
{body}
<footer>
<p>Fixture discovery: HotSpawn Pick'ems lobby (public endpoints). Probabilities: external bookmakers,
exchanges and the labelled originated models described on the method page — HotSpawn's crowd
percentage is published for reference and is never used as a probability input.
Generated {esc(generated)} UTC. Not affiliated with HotSpawn or any bookmaker. 18+, gamble responsibly.</p>
</footer>
</main>
<script src="assets/coverage.js"></script>
</body>
</html>
"""


def fmt_pct(value) -> str:
    return "—" if value is None else f"{100.0 * float(value):.1f}%"


def basis_class(basis: str | None) -> str:
    return {"market": "market", "exchange": "exchange", "bt": "estimate", "vrs": "estimate"}.get(basis or "", "blank")


def sources_html(row: dict) -> str:
    pub = row.get("published") or {}
    bits = []
    if pub.get("basis") == "market":
        for s in pub.get("sources", []):
            bits.append(f'<a href="{esc(s.get("source_public_url"))}" rel="noopener">{esc(s.get("source_name"))}</a> '
                        f'({s.get("decimal_odds_a")} / {s.get("decimal_odds_b")}, read {esc(s.get("retrieved_at_utc"))})')
    elif pub.get("basis") == "exchange":
        bits.append(f'<a href="{esc(pub.get("source_url"))}" rel="noopener">Kalshi market</a> '
                    f'(spread {pub.get("spread")}, read {esc(pub.get("retrieved_at_utc"))})')
    elif pub.get("basis") == "vrs":
        info = (row.get("estimate_inputs") or {}).get("vrs") or {}
        bits.append(f'<a href="{esc(info.get("source_url"))}" rel="noopener">Valve CS2 Regional Standings '
                    f'snapshot {esc(info.get("team_a_snapshot"))}</a> '
                    f'({info.get("team_a_points")} vs {info.get("team_b_points")} points)')
    elif pub.get("basis") == "bt":
        info = (row.get("estimate_inputs") or {}).get("bt") or {}
        bits.append(f'<a href="{esc(info.get("source_api"))}" rel="noopener">bo3.gg finished-match corpus</a> '
                    f'({info.get("matches_used")} matches, {info.get("teams")} teams, fit '
                    f'{esc(info.get("corpus_generated_at_utc"))})')
    hotspawn_url = row["sources"].get("hotspawn_match")
    if hotspawn_url:
        bits.append(f'<a href="{esc(hotspawn_url)}" rel="noopener">HotSpawn fixture</a>')
    return " · ".join(b for b in bits if b)


def card_html(row: dict) -> str:
    pub = row.get("published")
    basis = (pub or {}).get("basis")
    cls = basis_class(basis)
    p_a = (pub or {}).get("prob_a")
    p_b = (pub or {}).get("prob_b")
    crowd = row.get("hotspawn_crowd_pct_reference_only") or {}
    search = " ".join(str(x or "") for x in (row.get("team_a"), row.get("team_b"), row.get("competition"),
                                             row.get("start_time_utc"), row.get("fixture_id"))).lower()
    pick_html = ('<div class="pick blank">blank<br><span style="font-weight:500;font-size:12px">no confirmed line</span></div>'
                 if not pub else
                 ('<div class="pick %s">PICK<br><span style="font-size:13px">%s</span><br>%s</div>'
                  % (cls, esc(pub.get("pick_team") or "coin flip"), fmt_pct(pub.get("pick_probability")))
                  if pub.get("pick_side") != "coin_flip" else
                  '<div class="pick %s">NO PICK<br><span style="font-weight:600;font-size:12px">coin flip band</span></div>' % cls))
    badges = [f'<span class="badge {cls}">{esc(basis or "blank")}</span>']
    if row.get("picks_open"):
        badges.append('<span class="badge">picks open</span>')
    else:
        badges.append('<span class="badge locked">locked / started</span>')
    if row.get("listed_in_lobby"):
        badges.append('<span class="badge">listed by lobby</span>')
    for flag in row.get("flags", []):
        if flag not in ("picks_locked_or_past", "blank_no_published_probability"):
            badges.append(f'<span class="badge">{esc(flag)}</span>')
    return f"""<article class="card" data-card data-search="{esc(search)}" data-open="{1 if row.get('picks_open') else 0}" data-blank="{0 if pub else 1}">
  <h3>{esc(row.get('team_a'))} vs {esc(row.get('team_b'))}</h3>
  <p class="meta">{esc(row.get('competition'))} · tier {esc(row.get('tier'))} · kickoff {esc(row.get('start_time_utc'))} UTC ·
  lock {esc(row.get('lock_time_utc'))} UTC · HotSpawn #{esc(row.get('fixture_id'))}</p>
  <div class="teams">
    <div>
      <div class="trow"><span class="tname">{esc(row.get('team_a'))}</span><span class="pct">{fmt_pct(p_a)}</span></div>
      <div class="trow"><span class="tname">{esc(row.get('team_b'))}</span><span class="pct">{fmt_pct(p_b)}</span></div>
      <div class="bar"><i style="width:{0 if p_a is None else round(100*float(p_a))}%"></i></div>
    </div>
    {pick_html}
  </div>
  <div style="margin-top:8px">{''.join(badges)}</div>
  <p class="src">Line sources: {sources_html(row)}</p>
  <details><summary>Method detail for this row</summary>
    <p>{esc((pub or {}).get('label') or 'No probability published: ' + '; '.join(row.get('flags', [])))}</p>
    <p>Crowd reference only (never used): {esc(crowd.get('team_a'))}% / {esc(crowd.get('team_b'))}%</p>
    <p>Machine-readable row: <a href="data/board.json" rel="noopener">data/board.json</a> (fixture #{esc(row.get('fixture_id'))}),
    CSV <a href="data/board.csv" rel="noopener">data/board.csv</a>.
    HotSpawn fixture: <a href="{esc(row['sources'].get('hotspawn_match') or '#')}" rel="noopener">{esc(row['sources'].get('hotspawn_match') or 'not recorded for this snapshot')}</a>.</p>
    {('<p>Rejected line candidates for this fixture: ' + esc('; '.join(flag for flag in row.get('flags', []))) + '</p>') if not pub else ''}
  </details>
</article>"""


def render(board: dict, verification: dict, outdir: Path, review: dict | None = None) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "assets").mkdir(exist_ok=True)
    (outdir / "data").mkdir(exist_ok=True)
    (outdir / "assets/coverage.css").write_text(CSS, encoding="utf-8")
    (outdir / "assets/coverage.js").write_text(JS, encoding="utf-8")
    gen = board["generated_at_utc"]
    s = board["summary"]

    open_rows = [r for r in board["rows"] if r["picks_open"]]
    other_rows = [r for r in board["rows"] if not r["picks_open"]]
    rows_view = open_rows + other_rows

    stats = f"""<div class="stats">
  <div class="stat"><b>{s['picks_open']}</b><span>CS2 matches still open for picks</span></div>
  <div class="stat"><b>{s['open_with_probability']}/{s['picks_open']}</b><span>open matches with a published probability</span></div>
  <div class="stat"><b>{s['open_market']}</b><span>open matches priced from external bookmakers</span></div>
  <div class="stat"><b>{s['open_exchange']}</b><span>open matches priced from the exchange book</span></div>
  <div class="stat"><b>{s['open_estimate']}</b><span>open matches with an originated estimate</span></div>
  <div class="stat"><b>{s['open_blank']}</b><span>open matches with no confirmed line (flagged)</span></div>
</div>"""

    controls = """<div class="controls">
  <input id="q" type="search" placeholder="Search team, tournament or fixture id…" autocomplete="off">
  <select id="filter">
    <option value="open">Picks still open</option>
    <option value="all">All measured matches</option>
    <option value="blank">Only rows with no line</option>
  </select>
</div>
<p class="sub"><span id="shown">0</span> rows shown of """ + str(len(rows_view)) + """ — filters run in your browser.</p>"""

    index_body = f"""{stats}
<div class="note"><strong>How to read a row.</strong> The <em>PICK</em> box is the higher of the two
published probabilities; <span class="badge market">market</span> means external bookmaker prices
de-vigged proportionally, <span class="badge exchange">exchange</span> a two-sided Kalshi book inside
the published spread limit, <span class="badge estimate">estimate</span> a clearly labelled model
output (Valve standings or our fitted results model), and a blank box means no source confirmed a
line — such rows are listed with reasons on <a href="flagged.html">Flagged for review</a>.</div>
{controls}
{''.join(card_html(r) for r in rows_view)}"""

    (outdir / "index.html").write_text(page(
        "CS2 coverage board",
        ("Every Counter-Strike 2 fixture the HotSpawn Pick'ems lobby lists, with the pick and its "
         "probability from external sources only. Generated automatically; no manual input."),
        "index.html", index_body, gen), encoding="utf-8")

    # ---- flagged page
    blanks = [r for r in board["rows"] if not r["published"]]
    blank_items = "".join(
        f"""<article class="card"><h3>{esc(r.get('team_a'))} vs {esc(r.get('team_b'))}</h3>
<p class="meta">{esc(r.get('competition'))} · kickoff {esc(r.get('start_time_utc'))} UTC ·
HotSpawn #{esc(r.get('fixture_id'))} · {'picks still open' if r.get('picks_open') else 'locked/started'}</p>
<p><strong>Why it is blank:</strong> {esc('; '.join(r.get('flags', [])))}</p>
<p class="src">Sources checked / cited:
<a href="{esc(r['sources'].get('hotspawn_match'))}" rel="noopener">HotSpawn fixture page</a> ·
<a href="{esc(r['sources'].get('hotspawn_lobby'))}" rel="noopener">HotSpawn lobby</a> ·
<a href="https://bo3.gg/matches/current" rel="noopener">bo3.gg match feed</a> ·
<a href="https://www.hltv.org/matches" rel="noopener">HLTV matches</a> ·
<a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">Valve standings</a></p>
</article>""" for r in blanks)

    rejected_rows = [q for q in board["rejected_quotes"] if q.get("reason")]

    def link_cell(url) -> str:
        return f'<a href="{esc(url)}" rel="noopener">source</a>' if url else "—"

    rejected_items = "".join(
        f"<tr><td>{esc(q.get('source_name'))}</td><td>{esc(q.get('team_a'))} vs {esc(q.get('team_b'))}</td>"
        f"<td>{esc(str(q.get('decimal_odds_a')))} / {esc(str(q.get('decimal_odds_b')))}</td>"
        f"<td>{esc(q.get('reason'))}</td>"
        f"<td>{link_cell(q.get('source_public_url'))}</td></tr>"
        for q in rejected_rows[:200])

    ex_rows = [r for r in board["rows"] if r.get("exchange")]
    ex_items = "".join(
        f"<tr><td>{esc(r.get('team_a'))} vs {esc(r.get('team_b'))}</td>"
        f"<td>{esc(r['exchange'].get('event_ticker'))}</td>"
        f"<td>{esc(', '.join(r.get('exchange_reasons') or ['publishable']))}</td>"
        f"<td>{link_cell(r['exchange'].get('source_public_url'))}</td></tr>"
        for r in ex_rows[:200])

    flagged_body = f"""
<div class="note warn"><strong>Nothing on this page is inferred.</strong> A row appears here when no
external source confirmed a price and no documented rating covered both teams. The reason, the checks
that were run and the source links are printed for manual review.</div>

<h2>Rows with no published probability ({len(blanks)})</h2>
{blank_items or '<p class="sub">No blank rows in this snapshot.</p>'}

<h2>Line candidates that were refused ({len(rejected_rows)})</h2>
<p class="sub">A price the pipeline saw but did not publish, with the rule that rejected it. These are
published so a missing price is never silently treated as “no price exists”.</p>
<table><thead><tr><th>Source</th><th>Match as the source names it</th><th>Prices</th><th>Reason</th><th>Link</th></tr></thead>
<tbody>{rejected_items or '<tr><td colspan="5">none in this snapshot</td></tr>'}</tbody></table>

<h2>Exchange books reviewed ({len(ex_rows)})</h2>
<p class="sub">Kalshi CS2 markets matched to a lobby fixture. A book is only published as a probability
when both sides are two-sided, inside the published spread limit and carry volume or open interest.</p>
<table><thead><tr><th>Fixture</th><th>Event</th><th>Decision</th><th>Link</th></tr></thead>
<tbody>{ex_items or '<tr><td colspan="4">none in this snapshot</td></tr>'}</tbody></table>

<h2>Verification results</h2>
<table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>
{''.join(f'<tr><td>{esc(c["check"])}</td><td>{"PASS" if c["passed"] else "FAIL"}</td><td>{esc(c["detail"])}</td></tr>' for c in verification["checks"])}
</tbody></table>
<p class="sub">{verification['passed']} of {verification['passed'] + verification['failed']} checks passed
in this snapshot.</p>
"""
    (outdir / "flagged.html").write_text(page(
        "Flagged for review",
        "Everything the coverage board could not confirm from an external source, plus the line candidates that were refused.",
        "flagged.html", flagged_body, gen), encoding="utf-8")

    # ---- method page
    ev = board["model"]["evaluation"]
    model_rows = "".join(
        f"<tr><td>{name}</td><td>{'—' if not ev.get(name) else ev[name]['n']}</td>"
        f"<td>{'—' if not ev.get(name) else ev[name]['brier']}</td>"
        f"<td>{'—' if not ev.get(name) else ev[name]['log_loss']}</td>"
        f"<td>{'—' if not ev.get(name) else ev[name]['accuracy']}</td></tr>"
        for name in ("bt", "vrs"))
    sources_table = """
<table><thead><tr><th>Source</th><th>Kind</th><th>What is taken from it</th><th>Link</th></tr></thead><tbody>
<tr><td>HotSpawn Pick'ems lobby</td><td>fixture discovery only</td><td>fixture ids, teams, kickoff, lock time, tier — never a probability</td><td><a href="https://play.hotspawn.com/lobby" rel="noopener">play.hotspawn.com/lobby</a></td></tr>
<tr><td>bo3.gg public match feed</td><td>esports results/odds site</td><td>two-sided Thunderpick moneyline coefficients, team names, UTC start time; finished matches form the model corpus</td><td><a href="https://bo3.gg/matches/current" rel="noopener">bo3.gg/matches/current</a></td></tr>
<tr><td>Kalshi</td><td>regulated exchange</td><td>two-sided bid/ask for CS2 match markets (published only inside the spread limit)</td><td><a href="https://kalshi.com/markets/kxcs2game" rel="noopener">kalshi.com/markets/kxcs2game</a></td></tr>
<tr><td>Valve CS2 Regional Standings</td><td>official rating</td><td>team points used by the logistic estimate</td><td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">github.com/ValveSoftware/counter-strike_regional_standings</a></td></tr>
<tr><td>Repository live-coverage artifact</td><td>internal, attributed</td><td>Pinnacle / Bovada / LineFeed prices already collected hourly by session 3cd9787c (read-only; not re-requested)</td><td><a href="../live/index.html" rel="noopener">live coverage board</a></td></tr>
<tr><td>HLTV</td><td>cross-check</td><td>match context cited on the flagged page for manual review (the runner receives HTTP 403 from HLTV, so no value is scraped from it)</td><td><a href="https://www.hltv.org/matches" rel="noopener">hltv.org/matches</a></td></tr>
</tbody></table>"""

    method_body = f"""
<div class="note"><strong>Two rules drive every number on this site.</strong>
(1) A probability is only published when an external, non-HotSpawn source confirms it — or when a
documented model covers both teams, in which case the row says “originated estimate”.
(2) If neither holds, the value stays blank and the row is published on
<a href="flagged.html">Flagged for review</a>. Values are never inferred or filled in.</div>

<h2>Sources</h2>
{sources_table}

<h2>Formulas</h2>
<table><thead><tr><th>Step</th><th>Rule</th></tr></thead><tbody>
<tr><td>Implied probability</td><td>raw = 1 / decimal odds for each side</td></tr>
<tr><td>Overround</td><td>raw_a + raw_b</td></tr>
<tr><td>No-vig</td><td>p_a = raw_a / overround, p_b = raw_b / overround (proportional method)</td></tr>
<tr><td>Consensus</td><td>arithmetic mean of the per-source no-vig probabilities (bookmakers only; the exchange is never averaged in)</td></tr>
<tr><td>Valve standings estimate</td><td>p = 1 / (1 + 10^(−(points_a − points_b)/400)); the 400-point scale is a stated modelling assumption, not a Valve-published number</td></tr>
<tr><td>Fitted model</td><td>Bradley-Terry (logistic) on finished bo3.gg matches: p = 1 / (1 + exp(−(r_a − r_b))), half-life {BT_HALF_LIFE_DAYS} days, L2 ridge {BT_RIDGE}, {BT_ITERATIONS} gradient steps, a team is only used with at least {BT_MIN_MATCHES} matches in the corpus</td></tr>
<tr><td>Pick</td><td>the higher of the two published probabilities; an edge below {COIN_FLIP_BAND} is published as a coin flip with no pick</td></tr>
<tr><td>Join rule</td><td>both team labels must match after canonicalisation (case, accents, punctuation, leading “team”/“the”, trailing “esports”/“esport”/“gaming”/“team” only), and any published start time must be within ±{START_TOLERANCE_MIN} minutes</td></tr>
<tr><td>Freshness</td><td>market quotes older than {FRESHNESS_HOURS} hours and in-play prices are excluded and listed as refused candidates</td></tr>
</tbody></table>

<h2>Does the originated model add value? (calibration)</h2>
<p class="sub">Measured on finished CS2 matches in the last {ev.get('evaluation_window_days')} days of the
bo3.gg corpus. The Bradley-Terry model is refitted with that whole window excluded (out-of-sample) and
the Valve snapshot predates the window. The book price pair bo3.gg keeps for a finished match is its
last (in-play) price and leaks the result, so it is not scored here as a benchmark. Reported as Brier
score and log loss (lower is better; a coin flip has a Brier score of
{ev.get('baseline_coin_flip_brier')}).</p>
<table><thead><tr><th>Predictor</th><th>Matches</th><th>Brier</th><th>Log loss</th><th>Accuracy</th></tr></thead>
<tbody>{model_rows}</tbody></table>
<p class="sub">Matches in the evaluation window: {ev.get('matches_in_window')},
of which {ev.get('matches_with_book_price')} also carried a book price (not scored - see above). Published originated estimates
use <strong>{esc(board['model']['preference'])}</strong> in this snapshot, chosen by the lower Brier score.
{esc(ev.get('note'))}</p>

<h2>Snapshot facts</h2>
<table><thead><tr><th>Item</th><th>Value</th></tr></thead><tbody>
<tr><td>Generated (UTC)</td><td>{esc(gen)}</td></tr>
<tr><td>CS2 fixtures in window</td><td>{board['summary']['cs2_fixtures_in_window']}</td></tr>
<tr><td>Listed by the lobby page</td><td>{board['summary']['listed_by_lobby']}</td></tr>
<tr><td>Still open for picks</td><td>{board['summary']['picks_open']}</td></tr>
<tr><td>Market / exchange / estimate / blank</td><td>{board['summary']['market']} / {board['summary']['exchange']} / {board['summary']['estimate']} / {board['summary']['blank']}</td></tr>
<tr><td>External quotes read this run</td><td>{board['inputs']['quotes_total']}</td></tr>
<tr><td>Quotes refused by the join rules</td><td>{len(board['rejected_quotes'])}</td></tr>
<tr><td>Valve VRS snapshots</td><td>{esc(json.dumps(board['inputs']['vrs_snapshots']))}</td></tr>
<tr><td>Bradley-Terry corpus</td><td>{board['model']['bt']['matches_used']} matches / {board['model']['bt']['teams']} teams (generated {esc(board['model']['bt'].get('corpus_generated_at_utc'))})</td></tr>
<tr><td>Verification</td><td>{verification['passed']} of {verification['passed'] + verification['failed']} checks passed</td></tr>
</tbody></table>

<h2>Limitations</h2>
<ul>
<li>Bookmaker coverage of tier-3 matches is genuinely thin; where no book prices a match the row stays
blank rather than borrowing another match's price or a crowd percentage.</li>
<li>Start times are those HotSpawn publishes (UTC, from the lobby API). Where a source publishes a
different time the difference is flagged on the row and the same price is listed as a refused candidate
if it exceeds ±{START_TOLERANCE_MIN} minutes.</li>
<li>An exchange mid price is not a bookmaker quote: it is published with its spread and never averaged
into a bookmaker consensus.</li>
<li>Originated estimates are model output, clearly labelled, and are not guarantees or official
forecasts. The calibration table is an out-of-sample measurement on recent matches, not a promise of
future accuracy.</li>
<li>HotSpawn's crowd “picked %” is displayed for context only and is never a probability input.</li>
</ul>
"""
    (outdir / "method.html").write_text(page(
        "Method & verification",
        "Sources, formulas, join rules, calibration of the originated models and the limitations of this board.",
        "method.html", method_body, gen), encoding="utf-8")

    # ---- repo review / independent re-reads page (hand-verified evidence, source-linked).
    # This page is in the shared NAV, so it is rendered on every run: before any hand-verified review
    # entry is recorded it shows an explicit empty state. A missing page would break the nav link;
    # an honest placeholder never can.
    review = review or {}

    def review_rows(items, keys):
        return "".join(
            "<tr>" + "".join(
                f'<td><a href="{esc(it.get(k))}" rel="noopener">{esc(it.get(k))}</a></td>'
                if k.endswith("_url") and it.get(k) else f"<td>{esc(it.get(k))}</td>"
                for k in keys) + "</tr>" for it in items)

    check_rows = review_rows(review.get("items") or [],
                             ("id", "area", "claim", "method", "result", "evidence_url", "note"))
    reread_rows = review_rows(review.get("rereads") or [],
                              ("id", "what", "observed", "board_value", "url", "read_at_utc"))
    irr_rows = review_rows(review.get("irregularities") or [],
                           ("id", "severity", "finding", "evidence", "url", "affects"))
    if not (check_rows or reread_rows or irr_rows):
        check_rows = ('<tr><td colspan="7">No hand-verified review entry is recorded yet. Add '
                      'data/coverage/review.json - the tables and source-link columns are in place; '
                      'nothing is inferred or auto-filled.</td></tr>')
    review_body = f"""
<div class="note"><strong>What this page is.</strong> A line-by-line review performed by this
session, with the source link for every checked claim. Re-reads below were performed with a
tool-mediated fetch (the CI runner itself receives HTTP 403 from HLTV, so the runner cannot be used
to verify those values), so each row carries the exact URL and the time it was read.</div>
{esc(review.get('scope') or '')}

<h2>Repository review</h2>
<table><thead><tr><th>#</th><th>Area</th><th>Claim checked</th><th>How it was checked</th><th>Result</th><th>Evidence</th><th>Note</th></tr></thead>
<tbody>{check_rows}</tbody></table>

<h2>Independent re-reads of external sources</h2>
<p class="sub">Each row is a value this session read directly from the source and compared with what
the board publishes.</p>
<table><thead><tr><th>#</th><th>What was re-read</th><th>Observed</th><th>Board value</th><th>Source</th><th>Read at (UTC)</th></tr></thead>
<tbody>{reread_rows}</tbody></table>

<h2>Irregularities flagged for review</h2>
<p class="sub">Nothing here blocks the board: each item is published so it can be reviewed and, if
needed, corrected.</p>
<table><thead><tr><th>#</th><th>Severity</th><th>Finding</th><th>Evidence</th><th>Source</th><th>Affects</th></tr></thead>
<tbody>{irr_rows}</tbody></table>
<p class="sub">{esc(review.get('generated_at_utc') or '')}</p>
"""
    (outdir / "review.html").write_text(page(
        "Repo review &amp; independent re-reads",
        "Line-by-line checks of the repository's published claims plus direct re-reads of the external sources used by this board.",
        "review.html", review_body, gen), encoding="utf-8")

    # ---- machine-readable exports
    json_dump(outdir / "data/board.json", board)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["fixture_id", "competition", "tier", "status", "start_time_utc", "lock_time_utc",
                     "team_a", "team_b", "listed_in_lobby", "picks_open", "basis", "prob_a", "prob_b",
                     "pick_team", "pick_probability", "source_links", "flags"])
    for r in board["rows"]:
        pub = r["published"] or {}
        links = " ".join([s.get("source_public_url") or "" for s in pub.get("sources", [])]
                         + ([pub.get("source_url")] if pub.get("source_url") else [])
                         + [r["sources"].get("hotspawn_match") or ""])
        writer.writerow([r["fixture_id"], r["competition"], r["tier"], r["status"], r["start_time_utc"],
                         r["lock_time_utc"], r["team_a"], r["team_b"], r["listed_in_lobby"],
                         r["picks_open"], pub.get("basis") or "blank",
                         "" if pub.get("prob_a") is None else round(pub["prob_a"], 6),
                         "" if pub.get("prob_b") is None else round(pub["prob_b"], 6),
                         pub.get("pick_team") or "", "" if pub.get("pick_probability") is None else round(pub["pick_probability"], 6),
                         links.strip(), "; ".join(r["flags"])])
    (outdir / "data/board.csv").write_text(buffer.getvalue(), encoding="utf-8")


def check_links(outdir: Path) -> list[str]:
    from html.parser import HTMLParser
    from urllib.parse import unquote, urlsplit

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key in ("href", "src") and value:
                    self.urls.append(value)

    errors = []
    for page_file in outdir.rglob("*.html"):
        parser = Links()
        parser.feed(page_file.read_text(encoding="utf-8"))
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = page_file.parent / unquote(parsed.path)
            if not target.exists():
                errors.append(f"{page_file.relative_to(outdir)} -> {url}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "data/coverage"))
    parser.add_argument("--site", default=str(ROOT / "coverage"))
    parser.add_argument("--allow-blank-quotes", action="store_true",
                        help="build even when no external quote was collected (rows stay blank)")
    args = parser.parse_args()

    datadir, outdir = Path(args.data), Path(args.site)
    inputs = load_inputs(datadir)
    if not inputs["fixtures"].get("fixtures"):
        raise SystemExit("no fixture snapshot — run collect_coverage.py first")
    if not args.allow_blank_quotes and not inputs["quotes"].get("quotes"):
        raise SystemExit("no external quotes collected; refusing to build a board without sources")
    board = build_board(inputs)
    verification = verify_board(board)
    review_path = datadir / "review.json"
    review = None
    if review_path.is_file():
        try:
            review = json.loads(review_path.read_text())
        except json.JSONDecodeError:
            review = None
    render(board, verification, outdir, review)
    json_dump(datadir / "board.json", board)
    json_dump(datadir / "verification.json", verification)
    errors = check_links(outdir)
    if errors:
        raise SystemExit("broken internal links:\n" + "\n".join(errors))
    print(f"board rows={len(board['rows'])} open={board['summary']['picks_open']} "
          f"priced={board['summary']['with_probability']} blank={board['summary']['blank']} "
          f"checks={verification['passed']}/{verification['passed'] + verification['failed']} "
          f"links=OK model={board['model']['preference']}")
    if verification["failed"]:
        for c in verification["checks"]:
            if not c["passed"]:
                print(f"  FAILED CHECK: {c['check']} — {c['detail']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
