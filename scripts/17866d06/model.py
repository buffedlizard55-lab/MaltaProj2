#!/usr/bin/env python3
"""Session 17866d06 — probability model and pick engine.

Reads the evidence captured by ``collect.py`` plus the verified editorial ledger in
``research.py`` and writes ``data/17866d06/board.json``.

Three numbers are published per fixture and they are never conflated:

  quotes ...... what each book/exchange actually said (decimal odds -> no-vig implied)
  consensus ... our win probability, a weighted average of the no-vig quotes
  vrs ......... our *originated* line: a logistic function of the official Valve
                Regional Standings point delta, with its scale fitted to the markets
                captured in the same run (so the model is calibrated, not asserted)

``final`` is the number the pick is made from. Market consensus wins when a market
exists (a liquid market aggregates roster, form, veto and travel information we
cannot verify line by line); the originated VRS line is used alone when no market
covers the fixture, and blended 25% into a single thin quote to shrink its noise.

HotSpawn is never used as a probability input. Its ``picked_percent`` is carried
through as crowd ownership only, and its ``offered_points`` as the payout.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "17866d06"
HERE = Path(__file__).resolve().parent

# Weight given to each price source when averaging no-vig probabilities.
BOOK_WEIGHTS = {"thunderpick": 1.0, "melbet": 1.0}
EXCHANGE = "polymarket"
DISAGREEMENT_LIMIT = 0.12      # >12 points of spread between sources -> flagged
SINGLE_QUOTE_MODEL_BLEND = 0.25
COIN_FLIP_BAND = 0.02          # R5 tie-break band
SCALE_BOUNDS = (150.0, 1200.0)
SCALE_FALLBACK = 700.0
MIN_CALIBRATION_SAMPLES = 8

# Team-name aliases and the names deliberately left unresolved live in research.py so that
# collect.py (join) and model.py (standings lookup) cannot drift apart.
_RESEARCH = None


def research_module():
    global _RESEARCH
    if _RESEARCH is None:
        _RESEARCH = load_research()
    return _RESEARCH


def alias_table():
    return getattr(research_module(), "ALIASES", {})


def unresolved_by_design():
    return getattr(research_module(), "UNRESOLVED_BY_DESIGN", {})


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_research():
    spec = importlib.util.spec_from_file_location("research_17866d06", HERE / "research.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def norm(name) -> str:
    if not name:
        return ""
    text = "".join(ch if ch.isalnum() else " " for ch in str(name).lower())
    return "".join(text.split())


# --------------------------------------------------------------------- market math
def no_vig_from_decimal(decimal_a, decimal_b):
    """Two-way no-vig: (1/o_a) / ((1/o_a) + (1/o_b)). Returns None on bad input."""
    try:
        inv_a, inv_b = 1.0 / float(decimal_a), 1.0 / float(decimal_b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if inv_a <= 0 or inv_b <= 0:
        return None
    total = inv_a + inv_b
    return inv_a / total, inv_b / total


def overround(decimal_a, decimal_b):
    try:
        return 1.0 / float(decimal_a) + 1.0 / float(decimal_b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def poly_weight(volume_usd):
    """Exchange prices carry no vig but thin books are noisy: weight grows with volume.
    ~$1k -> 0.75, ~$10k -> 1.0, ~$100k+ -> 1.25 (capped)."""
    try:
        volume = float(volume_usd or 0)
    except (TypeError, ValueError):
        volume = 0.0
    if volume <= 0:
        return 0.5
    return round(min(1.25, 0.5 + math.log10(max(volume, 1.0)) / 4.0), 3)


def quote_implied(quote):
    """Normalise any quote into (prob_a, prob_b, weight, kind)."""
    key = quote.get("source_key")
    if key == EXCHANGE:
        pa, pb = quote.get("price_a"), quote.get("price_b")
        if not pa or not pb:
            return None
        total = float(pa) + float(pb)
        if total <= 0:
            return None
        # Polymarket outcome prices already sum to ~1.0; renormalise to remove rounding.
        return pa / total, pb / total, poly_weight(quote.get("volume_usd")), "exchange"
    fair = no_vig_from_decimal(quote.get("decimal_a"), quote.get("decimal_b"))
    if not fair:
        return None
    return fair[0], fair[1], BOOK_WEIGHTS.get(key, 0.75), "book"


def consensus(quotes):
    rows, weight_sum, prob_sum = [], 0.0, 0.0
    for quote in quotes:
        implied = quote_implied(quote)
        if not implied:
            rows.append({**slim_quote(quote), "implied_a": None, "weight": 0.0,
                         "note": "no usable two-way price"})
            continue
        pa, pb, weight, kind = implied
        rows.append({**slim_quote(quote), "implied_a": round(pa, 4), "implied_b": round(pb, 4),
                     "overround": (round(overround(quote["decimal_a"], quote["decimal_b"]), 4)
                                   if quote.get("decimal_a") else None),
                     "weight": weight, "kind": kind})
        weight_sum += weight
        prob_sum += weight * pa
    if weight_sum <= 0:
        return None, rows
    prob_a = prob_sum / weight_sum
    implied_values = [r["implied_a"] for r in rows if r.get("implied_a") is not None]
    spread = round(max(implied_values) - min(implied_values), 4) if len(implied_values) > 1 else 0.0
    return {"n_sources": len(implied_values),
            "sources": sorted({r["source_key"] for r in rows if r.get("implied_a") is not None}),
            "weight_total": round(weight_sum, 3),
            "prob_a": round(prob_a, 4), "prob_b": round(1 - prob_a, 4),
            "spread": spread,
            "disagreement": spread > DISAGREEMENT_LIMIT,
            "method": ("weighted average of no-vig implied probabilities; books weighted 1.0, "
                       "Polymarket weighted 0.5-1.25 by traded volume")}, rows


def slim_quote(quote):
    keep = ("source_key", "book", "team_a", "team_b", "decimal_a", "decimal_b", "draw_decimal",
            "price_a", "price_b", "start_utc", "public_url", "evidence_url", "retrieved_utc",
            "volume_usd", "liquidity_usd", "best_bid", "best_ask", "market_updated_utc",
            "market_slug", "event_slug", "league", "stage", "feed_row_id", "bo3_match_id",
            "bo3_slug", "tier", "join")
    return {k: quote[k] for k in keep if quote.get(k) is not None}


# ------------------------------------------------------------------------ VRS line
def vrs_index(standings):
    """Prefer the global standings; regional files fill gaps. Returns norm-name -> record.

    Two different rosters can share one name inside a single region file (Valve's 2026_10_05
    snapshot lists '6666' twice). Collapsing those silently would invent a mapping, so the
    record is marked ambiguous and resolve_vrs refuses it.
    """
    index = {}
    for region in ("europe", "americas", "asia", "global"):   # global written last = highest priority
        for name, record in (standings.get(region) or {}).items():
            key = norm(name)
            entry = {**record, "name": name, "region": region}
            previous = index.get(key)
            if previous and previous["region"] == region and previous.get("roster") != record.get("roster"):
                rosters = previous.get("ambiguous_rosters") or [previous.get("roster")]
                rosters = rosters + [record.get("roster")]
                entry = {**entry, "ambiguous_rosters": rosters,
                         "ambiguous_standings": (previous.get("ambiguous_standings") or [previous.get("standing")]
                                                 ) + [record.get("standing")]}
            elif previous and previous.get("ambiguous_rosters"):
                entry["ambiguous_rosters"] = previous["ambiguous_rosters"]
            index[key] = entry
    return index


def resolve_vrs(team_name, index):
    key = norm(team_name)
    if not key:
        return {"resolved": False, "reason": "no team name on the fixture row"}
    blocked = unresolved_by_design()
    if key in blocked:
        return {"resolved": False, "query": team_name, "reason": blocked[key]}
    if key in index:
        record = index[key]
        if record.get("ambiguous_rosters"):
            return {"resolved": False, "query": team_name, "reason":
                    "Valve's standings list more than one roster under this exact name",
                    "ambiguous_rosters": record["ambiguous_rosters"]}
        return {"resolved": True, "query": team_name, "method": "exact", **record}
    alias = alias_table().get(key)
    if alias:
        target = norm(alias[0])
        if target in index:
            return {"resolved": True, "query": team_name, "method": "verified alias",
                    "alias_evidence": alias[1], "alias_of": alias[0], **index[target]}
        return {"resolved": False, "query": team_name,
                "reason": f"alias '{alias[0]}' not present in Valve's standings snapshot"}
    candidates = [name for name in index if name and (name in key or key in name) and len(name) >= 4
                  and not index[name].get("ambiguous_rosters")]
    if len(candidates) == 1:
        return {"resolved": True, "query": team_name, "method": "unique substring",
                **index[candidates[0]]}
    if len(candidates) > 1:
        return {"resolved": False, "query": team_name, "reason": "ambiguous substring match",
                "candidates": sorted(index[c]["name"] for c in candidates)[:6]}
    return {"resolved": False, "query": team_name,
            "reason": "not listed in Valve's official standings snapshot"}


def logistic(delta_points, scale):
    return 1.0 / (1.0 + math.exp(-delta_points / scale))


def fit_scale(samples):
    """Least-squares fit of logit(p_market) = delta_points / S through the origin."""
    usable = []
    for sample in samples:
        delta, prob = sample.get("delta_points"), sample.get("market_prob_a")
        if delta is None or prob is None or not (0.02 <= prob <= 0.98) or delta == 0:
            continue
        usable.append((float(delta), math.log(prob / (1 - prob))))
    if len(usable) < MIN_CALIBRATION_SAMPLES:
        return {"scale": SCALE_FALLBACK, "calibrated": False, "samples": len(usable),
                "note": (f"fewer than {MIN_CALIBRATION_SAMPLES} usable market/VRS pairs in this "
                         "capture; the documented fallback scale is used and every model line "
                         "derived from it is flagged uncalibrated")}
    denominator = sum(d * l for d, l in usable)
    if denominator <= 0:
        return {"scale": SCALE_FALLBACK, "calibrated": False, "samples": len(usable),
                "note": "fit degenerate (non-positive covariance); fallback scale used"}
    raw = sum(d * d for d, _ in usable) / denominator
    scale = min(SCALE_BOUNDS[1], max(SCALE_BOUNDS[0], raw))
    predicted = [logistic(d, scale) for d, _ in usable]
    observed = [1 / (1 + math.exp(-l)) for _, l in usable]
    mean_obs = sum(observed) / len(observed)
    ss_res = sum((o - p) ** 2 for o, p in zip(observed, predicted))
    ss_tot = sum((o - mean_obs) ** 2 for o in observed) or 1e-9
    residuals = sorted((round(abs(o - p), 4) for o, p in zip(observed, predicted)), reverse=True)
    return {"scale": round(scale, 1), "raw_scale": round(raw, 1), "calibrated": True,
            "samples": len(usable), "r_squared": round(1 - ss_res / ss_tot, 4),
            "mean_abs_error": round(sum(residuals) / len(residuals), 4),
            "max_abs_error": residuals[0],
            "bounds": list(SCALE_BOUNDS),
            "method": ("ordinary least squares of logit(no-vig market probability) on the Valve "
                       "Regional Standings point delta, through the origin; S = sum(delta^2) / "
                       "sum(delta * logit)"),
            "clamped": bool(raw < SCALE_BOUNDS[0] or raw > SCALE_BOUNDS[1]),
            "fit_points": [{"delta_points": d, "logit_market": round(l, 4)} for d, l in usable]}


def calibration_samples(quotes, index):
    samples = []
    for quote in quotes:
        implied = quote_implied(quote)
        if not implied:
            continue
        a = resolve_vrs(quote.get("team_a"), index)
        b = resolve_vrs(quote.get("team_b"), index)
        if not (a.get("resolved") and b.get("resolved")):
            continue
        samples.append({"source_key": quote.get("source_key"), "team_a": quote.get("team_a"),
                        "team_b": quote.get("team_b"), "market_prob_a": round(implied[0], 4),
                        "vrs_a": a["points"], "vrs_b": b["points"],
                        "delta_points": a["points"] - b["points"],
                        "public_url": quote.get("public_url")})
    return samples


# --------------------------------------------------------------------- pick engine
def crowd_favourite(row):
    ca, cb = row.get("crowd_a"), row.get("crowd_b")
    if ca is None or cb is None:
        return None
    if ca == cb:
        return "split"
    return "a" if ca > cb else "b"


def apply_rules(row, r3_budget):
    """Rules R1-R5 from research.py, applied in order. Returns the pick block.

    R4 is deliberately absent: it needs user-side inputs (position on the leaderboard,
    picks remaining) that this desk does not have, so it is published as a decision aid
    and never auto-applied.
    """
    final = row.get("final") or {}
    prob_a, prob_b = final.get("prob_a"), final.get("prob_b")
    if prob_a is None:
        return {"team": None, "rule": "none", "prob": None,
                "reason": "no probability could be quoted or originated for this fixture"}
    crowd = crowd_favourite(row)
    offered = row.get("offered_points") or 0
    basis = final.get("basis")
    context_flags = row.get("context_flags") or []
    our_side = "a" if prob_a >= prob_b else "b"
    our_prob = max(prob_a, prob_b)
    our_team = row.get(f"team_{our_side}")

    # R5 - streak protection is a tie-break only, never an override of a real edge.
    if abs(prob_a - prob_b) <= COIN_FLIP_BAND and crowd in ("a", "b") and crowd != our_side:
        our_side = crowd
        our_team = row.get(f"team_{our_side}")
        our_prob = prob_a if crowd == "a" else prob_b
        return {"team": our_team, "side": our_side, "rule": "R5 streak protection",
                "reason": (f"our line is a coin flip ({prob_a:.1%} / {prob_b:.1%}); take the crowd "
                           "favourite to maximise P(correct) and protect the streak bonus"),
                "prob": round(our_prob, 4), "points_if_correct": offered,
                "crowd_ownership_of_pick": row.get(f"crowd_{our_side}"),
                "expected_points": round(offered * our_prob, 2)}

    # R3 - verified-context swing: capped, needs real offered points and real evidence.
    consensus = row.get("consensus") or {}
    market_prob = consensus.get("prob_a")
    market_prob_ours = None
    if market_prob is not None:
        market_prob_ours = market_prob if our_side == "a" else 1 - market_prob
    best_decimal = max((q.get("decimal_a") if our_side == "a" else q.get("decimal_b")
                        for q in row.get("quotes") or []
                        if (q.get("decimal_a") if our_side == "a" else q.get("decimal_b"))), default=None)
    break_even = round(1 / our_prob, 3) if our_prob else None
    value_ok = None
    if best_decimal is not None and break_even is not None:
        value_ok = best_decimal >= break_even
    elif market_prob_ours is not None:
        # HotSpawn pays flat points, so with no external price the value test is whether our
        # originated line rates the side higher than the market does.
        value_ok = our_prob - market_prob_ours >= 0.03
    against_market = market_prob_ours is not None and our_prob < 0.5
    if (our_prob < 0.5 and our_prob >= 0.30 and offered >= 3 and len(context_flags) >= 2
            and against_market and value_ok and r3_budget["remaining"] > 0):
        r3_budget["remaining"] -= 1
        r3_budget["used"].append(row["fixture_id"])
        return {"team": our_team, "side": our_side, "rule": "R3 verified-context swing",
                "reason": " | ".join(context_flag_texts(row)) +
                          f" || originated {our_prob:.1%} vs market {market_prob_ours:.1%}"
                          + (f", best external decimal {best_decimal} >= break-even {break_even}"
                             if best_decimal is not None else ""),
                "context_flags": context_flags,
                "prob": round(our_prob, 4), "points_if_correct": offered,
                "crowd_ownership_of_pick": row.get(f"crowd_{our_side}"),
                "expected_points": round(offered * our_prob, 2),
                "external_best_decimal": best_decimal, "external_break_even": break_even}

    # R2 - free contrarian: our favourite is not the crowd's, and we still rate it >= 50%.
    rule = "R1 max-probability default"
    reason = f"{basis}: {our_prob:.1%} {our_team}"
    ownership = row.get(f"crowd_{our_side}")
    if crowd in ("a", "b") and crowd != our_side and our_prob >= 0.50 and ownership is not None and ownership <= 40:
        rule = "R2 free contrarian"
        reason = (f"{basis}: {our_prob:.1%} {our_team}, while the crowd is {ownership}% on "
                  f"{row.get(f'team_{crowd}')} ({row.get(f'crowd_{crowd}')}%). HotSpawn pays flat "
                  "points per correct pick, so fading the crowd costs nothing and is free upside "
                  "if the field is wrong")
    elif crowd in ("a", "b") and crowd != our_side:
        reason += (f" | contrarian versus the crowd ({ownership}% on {row.get(f'team_{crowd}')}) "
                   "but our probability is below the R2 50% gate, so it is labelled R1 with a note")
    return {"team": our_team, "side": our_side, "rule": rule, "reason": reason,
            "prob": round(our_prob, 4), "points_if_correct": offered,
            "crowd_ownership_of_pick": ownership,
            "expected_points": round(offered * our_prob, 2)}


def final_probability(row, scale):
    market = row.get("consensus")
    vrs = row.get("vrs") or {}
    model_prob = None
    if vrs.get("a", {}).get("resolved") and vrs.get("b", {}).get("resolved"):
        model_prob = round(logistic(vrs["delta_points"], scale), 4)
        row["vrs"]["prob_a"] = model_prob
        row["vrs"]["prob_b"] = round(1 - model_prob, 4)
        row["vrs"]["scale_used"] = scale
    if market and market.get("prob_a") is not None:
        if market["n_sources"] == 1 and model_prob is not None:
            blended = 0.75 * market["prob_a"] + SINGLE_QUOTE_MODEL_BLEND * model_prob
            return {"prob_a": round(blended, 4), "prob_b": round(1 - blended, 4),
                    "basis": "market consensus (single quote) shrunk 25% toward the originated VRS line",
                    "model_prob_a": model_prob}
        return {"prob_a": market["prob_a"], "prob_b": market["prob_b"],
                "basis": f"market consensus ({market['n_sources']} source(s): {', '.join(market['sources'])})",
                "model_prob_a": model_prob}
    if model_prob is not None:
        return {"prob_a": model_prob, "prob_b": round(1 - model_prob, 4),
                "basis": "originated VRS logistic line only - no market covers this fixture",
                "model_prob_a": model_prob, "no_market": True}
    return {"prob_a": None, "prob_b": None, "basis": None, "model_prob_a": None}


def build_board(research, fixtures_doc, quotes_doc, vrs_doc):
    index = vrs_index((vrs_doc or {}).get("standings") or {})
    quotes = (quotes_doc or {}).get("joined") or []
    all_quotes = quotes + ((quotes_doc or {}).get("unjoined_for_calibration") or [])
    scale = fit_scale(calibration_samples(all_quotes, index))
    used_scale = scale["scale"]

    by_fixture = {}
    for quote in quotes:
        by_fixture.setdefault(quote["fixture_id"], []).append(quote)

    rows = []
    r3_budget = {"remaining": 2, "used": []}
    for fixture in (fixtures_doc or {}).get("open") or []:
        row = dict(fixture)
        fixture_quotes = by_fixture.get(fixture["fixture_id"], [])
        cons, quote_rows = consensus(fixture_quotes)
        row["quotes"] = quote_rows
        row["consensus"] = cons
        row["vrs"] = {"a": resolve_vrs(fixture.get("team_a"), index),
                      "b": resolve_vrs(fixture.get("team_b"), index)}
        if row["vrs"]["a"].get("resolved") and row["vrs"]["b"].get("resolved"):
            row["vrs"]["delta_points"] = row["vrs"]["a"]["points"] - row["vrs"]["b"]["points"]
            row["vrs"]["source"] = (f"https://github.com/ValveSoftware/counter-strike_regional_standings"
                                    f"/blob/main/live/2026/standings_global_{(vrs_doc or {}).get('snapshot')}.md")
        row["final"] = final_probability(row, used_scale)
        row["context_flags"] = context_flags_for(row, research)
        row["pick"] = apply_rules(row, r3_budget)
        row["crowd_favourite"] = crowd_favourite(row)
        row["unresolved"] = row["final"]["prob_a"] is None
        row["unresolved_reason"] = unresolved_reason(row) if row["unresolved"] else None
        row["limitations"] = limitations_for(row, scale)
        rows.append(row)

    twc = twc_rows(research, index, quotes_doc, used_scale, scale)
    board = {
        "session": "17866d06",
        "generated_utc": now_utc(),
        "captured_utc": (fixtures_doc or {}).get("captured_utc"),
        "vrs_snapshot": (vrs_doc or {}).get("snapshot"),
        "vrs_source": (vrs_doc or {}).get("source"),
        "calibration": scale,
        "quote_counts": (quotes_doc or {}).get("counts"),
        "rules": research.RULES,
        "scoring": research.SCORING,
        "open": rows,
        "twc": twc,
        "twc_settlement": (fixtures_doc or {}).get("twc_settlement") or [],
        "crowd_backtest": crowd_backtest((fixtures_doc or {}).get("twc_settlement") or []),
        "rejected_quotes": (quotes_doc or {}).get("rejected") or [],
        "dropped_stale_fixtures": (fixtures_doc or {}).get("dropped_stale") or [],
        "flags": research.FLAGS,
        "sources_index": research.SOURCES_INDEX,
        "aurora": research.AURORA,
        "event": research.EVENT,
        "results_day1_3": research.RESULTS,
        "r3_uses": r3_budget,
    }
    board["unresolved"] = [row for row in rows + twc if row.get("unresolved")]
    board["summary"] = summarise(board)
    return board


def context_flags_for(row, research):
    """Only flags backed by a source read this session (research.CONTEXT_FLAGS) are attached.
    Teams with no verified context get none, so rule R3 cannot fire on a hunch."""
    flags = []
    for side in ("team_a", "team_b"):
        for entry in (research.CONTEXT_FLAGS or {}).get(norm(row.get(side)), []):
            flags.append({"team": row.get(side), "text": entry["text"],
                          "sources": [{"label": label, "url": url} for label, url in entry["sources"]]})
    return flags


def context_flag_texts(row):
    return [f"{flag['team']}: {flag['text']}" for flag in row.get("context_flags") or []]


def unresolved_reason(row):
    vrs = row.get("vrs") or {}
    parts = []
    if not (row.get("consensus") or {}).get("prob_a"):
        parts.append("no book or exchange quote joined to this fixture (join rule: start time within "
                     "90 minutes plus at least one matching team name)")
    for side in ("a", "b"):
        record = vrs.get(side) or {}
        if not record.get("resolved"):
            parts.append(f"Valve standings: {record.get('reason', 'unresolved')} for '{row.get(f'team_{side}')}'")
    return "; ".join(parts) or "unresolved"


def limitations_for(row, scale):
    out = []
    if row.get("consensus") and row["consensus"].get("n_sources") == 1:
        out.append("single price source - the line is shrunk 25% toward our originated VRS model and "
                   "carries more uncertainty than a multi-book consensus")
    if row.get("consensus") and row["consensus"].get("disagreement"):
        out.append(f"sources disagree by {row['consensus']['spread']:.0%} - the consensus is an average "
                   "of genuinely different views, not a tight market")
    if (row.get("final") or {}).get("no_market"):
        out.append("no market covers this fixture: the probability is originated from Valve's official "
                   "standings alone (roster changes, form, vetoes and travel are NOT in that input)")
    if not scale.get("calibrated"):
        out.append("the VRS scale used for this row is the documented fallback, not fitted to this run")
    for quote in row.get("quotes") or []:
        join = quote.get("join") or {}
        if join.get("confidence") == "alias":
            out.append(f"{quote.get('source_key')} names the sides differently "
                       f"({quote.get('team_a')} / {quote.get('team_b')}); joined through a verified alias "
                       f"with the start time matching to within {join.get('start_delta_sec')}s")
        elif join.get("confidence") == "partial":
            out.append(f"{quote.get('source_key')} joined on a partial name match "
                       f"({join.get('side_a_match')}/{join.get('side_b_match')}, "
                       f"start delta {join.get('start_delta_sec')}s) - verify the teams before staking")
    return out


def twc_rows(research, index, quotes_doc, scale, scale_meta):
    """Day 4/5 of the Thunderpick World Championship: marquee matches that HotSpawn does
    not list in its pick'em (verified), so they earn no leaderboard points."""
    poly_by_slug = {}
    for quote in (quotes_doc or {}).get("joined") or []:
        if quote.get("source_key") == "polymarket" and quote.get("market_slug"):
            poly_by_slug[quote["market_slug"]] = quote
    rows = []
    for entry in list(research.DAY4) + list(research.DAY5):
        row = {"slot": entry.get("slot"), "hltv_match_id": entry.get("hltv"),
               "hltv_url": entry.get("hltv_url") or entry.get("url"),
               "hltv_analytics": entry.get("hltv_analytics"),
               "start_utc": entry.get("start_utc"), "bo": entry.get("bo"),
               "team_a": entry.get("a"), "team_b": entry.get("b"),
               "teams": entry.get("teams"),
               "hotspawn_pickable": bool(entry.get("hotspawn_pickem_listed")),
               "hotspawn_schedule_url": entry.get("hotspawn_schedule_url"),
               "not_pickable_evidence": (
                   "HotSpawn fixtures API ?sport_alias=cs2&status=scheduled&competition_id=35859 "
                   "returns [] - the semifinals are not offered as pick'em fixtures, so they award "
                   "no leaderboard points"),
               "start_evidence": entry.get("start_evidence") or [],
               "hltv_facts": entry.get("hltv_facts") or [],
               "polymarket_slug": entry.get("polymarket_slug"),
               "polymarket_url": entry.get("polymarket_url")}
        quote = poly_by_slug.get(entry.get("polymarket_slug") or "")
        if quote:
            implied = quote_implied(quote)
            row["quotes"] = [{**slim_quote(quote), "implied_a": round(implied[0], 4),
                              "implied_b": round(implied[1], 4), "weight": implied[2], "kind": implied[3]}]
            row["consensus"] = {"n_sources": 1, "sources": ["polymarket"], "weight_total": implied[2],
                                "prob_a": round(implied[0], 4), "prob_b": round(implied[1], 4),
                                "spread": 0.0, "disagreement": False,
                                "method": "single exchange price (no vig to remove)"}
        else:
            row["quotes"] = []
            row["consensus"] = None
        row["vrs"] = {"a": resolve_vrs(entry.get("a"), index), "b": resolve_vrs(entry.get("b"), index)}
        if row["vrs"]["a"].get("resolved") and row["vrs"]["b"].get("resolved"):
            row["vrs"]["delta_points"] = row["vrs"]["a"]["points"] - row["vrs"]["b"]["points"]
            row["vrs"]["source"] = ("https://github.com/ValveSoftware/counter-strike_regional_standings"
                                    "/blob/main/live/2026/standings_global_2026_10_05.md")
        row["final"] = final_probability(row, scale)
        row["context_flags"] = context_flags_for(row, research)
        row["offered_points"] = 0
        row["crowd_a"] = None
        row["crowd_b"] = None
        if row["final"]["prob_a"] is None:
            row["unresolved"] = True
            row["unresolved_reason"] = ("teams are still 'Waiting for information' on HotSpawn and "
                                        "HLTV; no probability can be originated for an unknown pairing")
            row["pick"] = {"team": None, "rule": "none", "prob": None,
                           "reason": "participants not yet determined"}
        else:
            row["unresolved"] = False
            row["unresolved_reason"] = None
            side = "a" if row["final"]["prob_a"] >= row["final"]["prob_b"] else "b"
            row["pick"] = {"team": row[f"team_{side}"], "side": side,
                           "rule": "R1 max-probability default (no HotSpawn points available)",
                           "reason": f"{row['final']['basis']} probability "
                                     f"{max(row['final']['prob_a'], row['final']['prob_b']):.1%}",
                           "prob": round(max(row["final"]["prob_a"], row["final"]["prob_b"]), 4),
                           "points_if_correct": 0}
        row["limitations"] = limitations_for(row, scale_meta) + [
            "not pickable on HotSpawn (verified): shown for context and for any external market "
            "the reader wants to compare against our originated line"]
        rows.append(row)
    return rows


def crowd_backtest(settlement):
    """Days 1-3 of TWC 2026, read from HotSpawn's own settled rows."""
    rows, favourites = [], []
    for match in settlement:
        ca, cb = match.get("crowd_a"), match.get("crowd_b")
        sa, sb = match.get("score_a"), match.get("score_b")
        status = match.get("status")
        winner = None
        if sa is not None and sb is not None and sa != sb:
            winner = "a" if sa > sb else "b"
        rows.append({**match, "winner_side": winner,
                     "crowd_favourite": ("a" if (ca or 0) > (cb or 0) else "b" if (cb or 0) > (ca or 0) else None)})
        if winner and ca is not None and cb is not None and max(ca, cb) >= 60:
            favourites.append({"fixture_id": match.get("fixture_id"), "status": status,
                               "favourite": match.get(f"team_{'a' if ca > cb else 'b'}"),
                               "favourite_ownership": max(ca, cb),
                               "winner": match.get(f"team_{'a' if winner == 'a' else 'b'}"),
                               "favourite_won": winner == ("a" if ca > cb else "b"),
                               "offered_points": match.get("offered_points")})
    wins = sum(1 for f in favourites if f["favourite_won"])
    return {"rows": rows, "strong_favourites": favourites,
            "strong_favourite_record": f"{wins}-{len(favourites) - wins}",
            "note": ("HotSpawn pays a flat offered_points per correct pick plus an unpublished streak "
                     "bonus; ownership does not scale the payout, so expected points = offered_points x "
                     "P(correct). Days 1-3 show a >=60% crowd favourite winning "
                     f"{wins} of {len(favourites)} decided fixtures - the crowd is right often enough to "
                     "respect, wrong often enough to fade when our own line disagrees.")}


def summarise(board):
    open_rows = board["open"]
    resolved = [r for r in open_rows if not r["unresolved"]]
    pickable_points = sum(r.get("offered_points") or 0 for r in resolved)
    return {
        "captured_utc": board["captured_utc"],
        "open_fixtures": len(open_rows),
        "resolved": len(resolved),
        "unresolved": len(open_rows) - len(resolved),
        "points_available_on_resolved": pickable_points,
        "points_available_all_open": sum(r.get("offered_points") or 0 for r in open_rows),
        "by_tier": {tier: sum(1 for r in open_rows if r.get("tier") == tier)
                    for tier in sorted({r.get("tier") or "?" for r in open_rows})},
        "contrarian_picks": sum(1 for r in resolved
                                if r["pick"].get("rule", "").startswith(("R2", "R3"))),
        "model_only_picks": sum(1 for r in resolved if (r.get("final") or {}).get("no_market")),
        "market_coverage": round(len([r for r in open_rows if r.get("consensus")]) / max(len(open_rows), 1), 3),
        "quote_sources": board.get("quote_counts"),
        "vrs_scale": board["calibration"].get("scale"),
        "vrs_calibrated": board["calibration"].get("calibrated"),
        "twc_semifinals_pickable": False,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    research = load_research()
    fixtures_doc = read_json(DATA / "fixtures.json")
    quotes_doc = read_json(DATA / "quotes.json")
    vrs_doc = read_json(DATA / "vrs.json")
    if not fixtures_doc and "--allow-empty" not in argv:
        print("no capture found - run scripts/17866d06/collect.py first (or pass --allow-empty)")
        return 1
    board = build_board(research, fixtures_doc or {"open": []}, quotes_doc or {}, vrs_doc or {})
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = board["summary"]
    print(f"board.json: {summary['open_fixtures']} open fixtures, {summary['resolved']} resolved, "
          f"{summary['unresolved']} unresolved, VRS scale {summary['vrs_scale']} "
          f"(calibrated={summary['vrs_calibrated']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
