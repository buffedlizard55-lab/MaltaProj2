#!/usr/bin/env python3
"""Session b1fb1465 build step — joins the collected quotes to the lobby fixtures and classifies
every open CS2 fixture into one of four resolutions.

Resolution order (the user's requirement, applied literally)
-----------------------------------------------------------
1. ``market``   — a two-way price from a licensed bookmaker (Pinnacle, Bovada, Melbet/1xBet
                  platform, or the Thunderpick coefficient bo3.gg publishes per fixture).
2. ``exchange`` — a two-sided Kalshi order book. A book wider than 10c is published with
                  ``thin_exchange_book`` and a Low confidence label instead of being dropped.
3. ``model``    — an **originated** line: Valve's official VRS points turned into a win probability
                  with Valve's own Glicko slope, whose scale is fitted on the market pairs observed in
                  the same run (never on HotSpawn). Published as a model estimate, not a price.
4. ``unresolved`` — no price and no official rating for both teams. The row keeps **blank** numbers
                  and is published on ``exec/unresolved.html`` with the sources that were tried, each
                  with its HTTP status and UTC read time, and the limitation that blocks the pick.

Nothing is inferred. A team name is only joined to a source when the canonical keys agree *and*
the kick-off times agree inside the window; every alias that was applied is listed with its evidence.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "b1fb1465"

MARKET_SOURCES = ("pinnacle", "bovada", "melbet", "thunderpick")
SOURCE_LABELS = {
    "pinnacle": "Pinnacle (licensed bookmaker)",
    "bovada": "Bovada (licensed bookmaker)",
    "melbet": "Melbet / 1xBet platform (licensed bookmaker)",
    "thunderpick": "Thunderpick coefficient published by bo3.gg (title-sponsor bookmaker)",
    "kalshi": "Kalshi (CFTC-regulated exchange)",
}
MATCH_WINDOW_H = 3.0          # the same pairing must be at the same kick-off inside this window
VALVE_Q = math.log(10) / 400.0
VALVE_RD = 200.0
VALVE_C = (1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)) * VALVE_Q
CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_snapshot() -> dict:
    path = DATA / "snapshot.json"
    if not path.exists():
        raise SystemExit(f"missing {path}: run scripts/b1fb1465/collect.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def _side_flip(qa: str, qb: str, ka: str, kb: str) -> bool | None:
    """Whether the quote's two sides must be flipped to line up with the fixture, or None.

    Two shapes are supported: the same two canonical teams in either order, and a reviewed name
    decision where one side is the fixture's team under another title. Anything else is refused.
    """
    if {qa, qb} == {ka, kb}:
        return qa != ka
    shared = {qa, qb} & {ka, kb}
    if len(shared) != 1:
        return None
    team = next(iter(shared))
    if qa == team:                      # the source lists the shared team first
        return team == kb               # flip iff that team is the fixture's second team
    return team != kb                   # source lists it second: flip iff it is the fixture's first


def join_quotes(fixture: dict, quotes_by_pair: dict, rejected: list) -> list[dict]:
    """All quotes that belong to this fixture, with side alignment resolved and the time gap kept.

    Two ways in, and both keep their time check: the exact canonical pair, or a reviewed
    ``OPPONENT_LABEL_DISAGREEMENTS`` record that ties a specific source title to this fixture pair.
    A name that differs without such a record is refused and published in ``rejected_joins``.
    """
    ka, ea, na = core.canon(fixture["team_a"])
    kb, eb, nb = core.canon(fixture["team_b"])
    start = core.parse_iso(fixture["start_utc"])
    joined: list[dict] = []

    def attach(q: dict, label: dict | None) -> None:
        qa, _, _ = core.canon(q.get("team_a"))
        qb, _, _ = core.canon(q.get("team_b"))
        swap = _side_flip(qa, qb, ka, kb)
        diff = core.hours_between(start, core.parse_iso(q.get("start_utc")))
        reasons = []
        if swap is None:
            reasons.append("the listed teams cannot be aligned with this fixture")
        if diff is None:
            reasons.append("source publishes no kick-off time")
        elif abs(diff) > MATCH_WINDOW_H:
            reasons.append("same team pair but the kick-off times disagree")
        if reasons:
            rejected.append({"fixture_id": fixture["fixture_id"],
                             "match": f"{fixture['team_a']} vs {fixture['team_b']}",
                             "source_key": q.get("source_key"), "source_event": q.get("event_id"),
                             "source_url": q.get("public_url"),
                             "source_match": f"{q.get('team_a')} vs {q.get('team_b')}",
                             "fixture_start_utc": fixture["start_utc"],
                             "source_start_utc": q.get("start_utc"),
                             "start_diff_h": diff,
                             "via": "reviewed name decision" if label else "canonical team names",
                             "reason": "; ".join(reasons)})
            return
        prob_a = q.get("prob_a")
        if prob_a is None:
            return
        row = {**q, "swapped": swap, "start_diff_h": diff,
               "prob_a": round(prob_a if not swap else 1 - prob_a, 6),
               "source_prob_a": prob_a,
               "pair_mismatch": bool(label)}
        if label:
            row["label_disagreement"] = {**label, "source_key": q.get("source_key"),
                                         "source_match": f"{q.get('team_a')} vs {q.get('team_b')}",
                                         "source_pair": sorted((qa, qb)),
                                         "fixture_match": f"{fixture['team_a']} vs {fixture['team_b']}",
                                         "fixture_pair": sorted((ka, kb))}
        row["alias_notes"] = [n for n in (na, nb) if n]
        row["alias_evidence"] = sorted(set(ea + eb))
        joined.append(row)

    for q in quotes_by_pair.get(frozenset((ka, kb)), []):
        attach(q, None)

    # Reviewed name decisions: a price source that titles this same fixture differently.
    fixture_pair = sorted((ka, kb))
    for (source_key, *entry_pair), rec in core.OPPONENT_LABEL_DISAGREEMENTS.items():
        if sorted(rec.get("fixture_pair") or ()) != fixture_pair:
            continue
        for q in quotes_by_pair.get(frozenset(entry_pair), []):
            if q.get("source_key") == source_key:
                attach(q, rec)
    return joined


def market_consensus(joined: list[dict]) -> dict | None:
    rows = [q for q in joined if q.get("source_key") in MARKET_SOURCES and q.get("prob_a") is not None]
    if not rows:
        return None
    probs = [q["prob_a"] for q in rows]
    mid = core.median(probs)
    return {"prob_a": mid, "prob_b": 1 - mid, "n_sources": len(rows),
            "sources": sorted({q["source_key"] for q in rows}),
            "min_a": min(probs), "max_a": max(probs), "spread_a": round(max(probs) - min(probs), 4),
            "quotes": rows}


def exchange_consensus(joined: list[dict]) -> dict | None:
    rows = [q for q in joined if q.get("source_key") == "kalshi" and q.get("prob_a") is not None]
    if not rows:
        return None
    thin = [q for q in rows if q.get("thin_book")]
    probs = [q["prob_a"] for q in rows]
    mid = core.median(probs)
    return {"prob_a": mid, "prob_b": 1 - mid, "n_sources": len(rows),
            "thin_book": bool(thin), "max_spread": max((q.get("spread") or 0) for q in rows),
            "quotes": rows}


def vrs_lookup(fixture: dict, vrs_teams: dict) -> dict | None:
    ka, ea_a, _ = core.canon(fixture["team_a"])
    kb, ea_b, _ = core.canon(fixture["team_b"])
    a, b = vrs_teams.get(ka), vrs_teams.get(kb)
    if not a or not b:
        return None
    return {"team_a": {**a, "key": ka}, "team_b": {**b, "key": kb}}


def fit_calibration(pairs: list[dict]) -> dict:
    """Least-squares fit of logit(market) = k * VALVE_C * dVRS through the origin."""
    out = {"n_pairs": len(pairs), "k": 1.0, "fitted": False, "k_raw": None,
           "bounds": list(CAL_K_BOUNDS), "min_pairs": CAL_MIN_PAIRS,
           "note": "k scales Valve's own Glicko slope; k=1 is Valve's published slope."}
    xs, ys = [], []
    for p in pairs:
        if p.get("delta") is None or p.get("market_prob_a") is None:
            continue
        xs.append(VALVE_C * p["delta"])
        ys.append(logit(p["market_prob_a"]))
    sxx = sum(x * x for x in xs)
    if len(xs) >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        out["k_raw"] = round(k_raw, 6)
        out["k"] = round(min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1]), 6)
        out["fitted"] = True
    if xs:
        out["mae_prob"] = round(sum(abs(sigmoid(out["k"] * x) - sigmoid(y))
                                     for x, y in zip(xs, ys)) / len(xs), 4)
        out["mae_prob_valve"] = round(sum(abs(sigmoid(x) - sigmoid(y))
                                          for x, y in zip(xs, ys)) / len(xs), 4)
    return out


def source_attempts(access: dict) -> list[dict]:
    """Every external read this run attempted, in the order the project requires."""
    rows = []
    for key, meta in access.items():
        if not isinstance(meta, dict) or not meta.get("url"):
            continue
        rows.append({"key": key, "url": meta.get("url"), "status": meta.get("status"),
                     "error": meta.get("error"), "bytes": meta.get("bytes"),
                     "at_utc": meta.get("at_utc"),
                     "note": "read succeeded" if meta.get("status") == 200
                             else (meta.get("error") or "no response")})
    def rank(row):
        url = row["url"] or ""
        if "hltv.org" in url:
            return (0, url)
        if any(k in url for k in ("pinnacle", "bovada", "melbet", "kalshi", "bo3.gg")):
            return (1, url)
        return (2, url)
    return sorted(rows, key=rank)


def build_row(fixture: dict, joined: list[dict], vrs_teams: dict, calibration: dict,
              rejected: list) -> dict:
    market = market_consensus(joined)
    exchange = exchange_consensus(joined)
    vrs = vrs_lookup(fixture, vrs_teams)
    model = None
    if vrs:
        slope = float(calibration.get("k", 1.0))
        delta = vrs["team_a"]["points"] - vrs["team_b"]["points"]
        prob_a = sigmoid(slope * VALVE_C * delta)
        model = {"basis": "valve_vrs", "prob_a": round(prob_a, 6), "prob_b": round(1 - prob_a, 6),
                 "delta": delta, "k": slope, "fitted": bool(calibration.get("fitted")),
                 "points_a": vrs["team_a"]["points"], "points_b": vrs["team_b"]["points"],
                 "standing_a": vrs["team_a"]["standing"], "standing_b": vrs["team_b"]["standing"],
                 "vrs_name_a": vrs["team_a"]["name"], "vrs_name_b": vrs["team_b"]["name"]}
    labels = [q["label_disagreement"] for q in joined if q.get("label_disagreement")]
    flags: list[str] = []
    if labels:
        flags.append("opponent_label_disagreement")
    if market:
        basis, prob_a = "market", market["prob_a"]
        if market["spread_a"] > 0.10:
            flags.append("bookmaker_disagreement_over_10_points")
        if market["n_sources"] == 1:
            flags.append("single_market_source")
    elif exchange:
        basis = "exchange"
        prob_a = exchange["prob_a"]
        flags.append("thin_exchange_book" if exchange["thin_book"] else "exchange_only_no_bookmaker")
    elif model:
        basis = "model"
        prob_a = model["prob_a"]
        flags += ["no_bookmaker_price_for_this_fixture", "originated_model_line",
                  f"originated_from_{model['basis']}"]
    else:
        basis, prob_a = "unresolved", None
        flags.append("no_price_and_no_official_rating")

    prob_b = None if prob_a is None else round(1 - prob_a, 6)
    pick = pick_prob = None
    if prob_a is not None:
        pick = fixture["team_a"] if prob_a >= 0.5 else fixture["team_b"]
        pick_prob = prob_a if prob_a >= 0.5 else prob_b

    sources = [{"label": "HotSpawn Pick'ems lobby (fixture discovery only, never a probability)",
                "url": fixture["hotspawn_url"], "kind": "discovery",
                "read_utc": (fixture.get("retrieved_utc") or None)}]
    for q in joined:
        sources.append({"label": f"{SOURCE_LABELS.get(q['source_key'], q['source_key'])} · "
                                 f"{q.get('raw_format')}",
                        "url": q.get("public_url"), "kind": "price",
                        "read_utc": q.get("retrieved_utc"),
                        "detail": f"{q.get('team_a')} {q.get('decimal_a')} / "
                                  f"{q.get('team_b')} {q.get('decimal_b')}"
                                  + (f" · spread {q.get('spread')}" if q.get("spread") is not None
                                     else "")})
    for ld in labels:
        sources.append({"label": f"Name decision · {ld['source_match']} = {ld['fixture_match']}",
                        "url": (ld.get("evidence") or [None])[0], "kind": "label",
                        "detail": ld.get("note")})
    if model:
        sources.append({"label": f"Valve VRS global standings · {model['vrs_name_a']} "
                                 f"#{model['standing_a']} ({model['points_a']} pts) / "
                                 f"{model['vrs_name_b']} #{model['standing_b']} "
                                 f"({model['points_b']} pts)",
                        "url": (vrs_teams.get("_source_url") if False else None) or
                               "https://github.com/ValveSoftware/counter-strike_regional_standings",
                        "kind": "rating",
                        "read_utc": vrs_teams.get("_read_utc")})

    return {
        "fixture_id": fixture["fixture_id"], "competition": fixture["competition"],
        "tier": fixture["tier"], "stage": fixture["stage"], "status": fixture["status"],
        "start_utc": fixture["start_utc"], "lock_utc": fixture["lock_utc"],
        "team_a": fixture["team_a"], "team_b": fixture["team_b"],
        "hotspawn_url": fixture["hotspawn_url"], "hotspawn_url_kind": fixture["hotspawn_url_kind"],
        "basis": basis, "pick": pick, "pick_probability": pick_prob,
        "prob_a": prob_a, "prob_b": prob_b,
        "confidence": core.confidence(pick_prob, basis),
        "market": market, "exchange": exchange, "model": model, "vrs": vrs,
        "flags": flags, "sources": [s for s in sources if s.get("url")],
        "alias_evidence": sorted({u for q in joined for u in q.get("alias_evidence", [])}),
        "alias_notes": sorted({n for q in joined for n in q.get("alias_notes", []) if n}),
        "label_disagreements": labels,
    }


def limitations_for(row: dict, attempts: list[dict], generated_utc: str) -> list[str]:
    """Plain-language limitations for every fixture without a bookmaker price."""
    notes: list[str] = []
    for ld in row.get("label_disagreements") or []:
        notes.append(f"Name check: {ld['source_key']} titles this fixture "
                     f"\"{ld['source_match']}\" while HotSpawn titles it \"{ld['fixture_match']}\". "
                     f"The price is for this fixture (identical kick-off), and the call is published "
                     f"with its evidence on the sources page.")
    if row["basis"] == "market":
        return notes
    if row["basis"] == "exchange":
        spread = (row.get("exchange") or {}).get("max_spread")
        notes.append("No licensed bookmaker lists this fixture: the pick rests on the Kalshi "
                     "exchange order book only, whose two legs are "
                     f"{spread:.3f} dollars wide." if spread is not None
                     else "No licensed bookmaker lists this fixture: exchange-only resolution.")
        notes.append("An exchange mid is a market observation, not a bookmaker price; liquidity is "
                     "thin and the quote can move.")
    elif row["basis"] == "model":
        notes.append("No bookmaker, exchange or aggregator reachable from the collection runner "
                     "quotes this fixture, so the pick is an **originated** line: Valve's official "
                     "VRS points with Valve's own Glicko slope, whose scale is fitted on the market "
                     "pairs seen in the same run. It is a model estimate, not a price.")
        notes.append("HLTV is checked on every run; when HLTV refuses the runner (HTTP 403 "
                     "Cloudflare challenge) its odds cannot be used automatically and are published "
                     "only as a dated interactive cross-check.")
    elif row["basis"] == "unresolved":
        missing = []
        if row.get("vrs") is None:
            missing.append("at least one team has no row in Valve's official global standings")
        notes.append("No pick is published for this fixture: " + "; ".join(missing or
                     ["no price and no official rating source covers both teams"]) + ".")
        notes.append("The row stays blank on purpose and is flagged for review; numbers are never "
                     "inferred to fill it.")
    blocked = [a for a in attempts if a.get("status") == 403 and "hltv.org" in (a.get("url") or "")]
    if blocked and row["basis"] in ("model", "unresolved"):
        notes.append(f"HLTV returned HTTP 403 from the collection runner at "
                     f"{blocked[0].get('at_utc')} ({blocked[0].get('url')}), which is why the "
                     f"HLTV route could not add a price to this row.")
    if row["tier"] and str(row["tier"]).upper() == "C":
        notes.append("Tier-C event: bookmaker coverage is structurally thin, so the pick is marked "
                     "as low confidence even when a price exists.")
    return notes


def main() -> int:
    snap = load_snapshot()
    generated = core.now_utc()
    fixtures = snap["hotspawn"]["fixtures"]
    quotes = snap.get("quotes") or []
    vrs_teams = dict(snap.get("vrs_teams") or {})
    vrs_meta = snap.get("vrs") or {}
    vrs_teams["_source_url"] = vrs_meta.get("source_url")
    vrs_teams["_read_utc"] = (snap.get("access", {}).get("valve_vrs_file", {}) or {}).get("at_utc")

    quotes_by_pair: dict[frozenset, list] = {}
    for q in quotes:
        qa, _, _ = core.canon(q.get("team_a"))
        qb, _, _ = core.canon(q.get("team_b"))
        if qa and qb:
            quotes_by_pair.setdefault(frozenset((qa, qb)), []).append(q)

    rejected: list[dict] = []
    open_rows: list[dict] = []
    closed_rows: list[dict] = []
    for fx in fixtures:
        joined = join_quotes(fx, quotes_by_pair, rejected)
        row = build_row(fx, joined, vrs_teams, {}, rejected)   # calibration filled after pass 1
        if core.is_open(fx, generated):
            open_rows.append(row)
        else:
            closed_rows.append(row)

    # Pass 1 used k=1; fit the slope on this run's own market pairs, then rebuild every row.
    pairs = [{"delta": row["model"]["delta"], "market_prob_a": row["market"]["prob_a"]}
             for row in open_rows if row.get("market") and row.get("model")]
    calibration = fit_calibration(pairs)
    open_rows = [build_row(fx, join_quotes(fx, quotes_by_pair, []), vrs_teams, calibration, rejected)
                 for fx in fixtures if core.is_open(fx, generated)]
    rejected = []
    for fx in fixtures:
        join_quotes(fx, quotes_by_pair, rejected)

    attempts = source_attempts(snap.get("access") or {})
    no_market = [r for r in open_rows if r["basis"] != "market"]
    unresolved = [r for r in open_rows if r["basis"] == "unresolved"]
    for row in open_rows:
        row["limitations"] = limitations_for(row, attempts, snap.get("generated_utc"))
        row["unresolved_category"] = (
            "resolved_by_bookmaker_price" if row["basis"] == "market" else
            "resolved_by_exchange_only" if row["basis"] == "exchange" else
            "resolved_by_originated_line" if row["basis"] == "model" else
            "not_resolved")

    label_records: list[dict] = []
    seen_labels: set = set()
    for row in open_rows:
        for ld in row.get("label_disagreements") or []:
            key = (row["fixture_id"], ld.get("source_key"), tuple(ld.get("source_pair") or []))
            if key in seen_labels:
                continue
            seen_labels.add(key)
            label_records.append({"fixture_id": row["fixture_id"], "fixture": ld["fixture_match"],
                                  **{k: v for k, v in ld.items() if k != "fixture_match"}})
    summary = {
        "fixtures_listed_cs2": len(fixtures),
        "open_for_picks": len(open_rows),
        "with_pick": sum(1 for r in open_rows if r["pick"]),
        "with_blank_pick": sum(1 for r in open_rows if not r["pick"]),
        "resolved_by_market": sum(1 for r in open_rows if r["basis"] == "market"),
        "resolved_by_exchange_only": sum(1 for r in open_rows if r["basis"] == "exchange"),
        "resolved_by_originated_line": sum(1 for r in open_rows if r["basis"] == "model"),
        "unresolved": len(unresolved),
        "no_market_price": len(no_market),
        "closed_or_locked_listed": len(closed_rows),
        "quotes_collected": len(quotes),
        "quotes_joined": sum(len(r["market"]["quotes"]) if r.get("market") else 0 for r in open_rows),
        "quotes_rejected_on_time": len(rejected),
        "rows_with_reviewed_name_decisions": sum(1 for r in open_rows
                                                 if r.get("label_disagreements")),
        "sources_by_key": dict(Counter(q.get("source_key") for q in quotes)),
    }
    board = {
        "session": "b1fb1465",
        "generated_utc": core.iso(generated),
        "snapshot_generated_utc": snap.get("generated_utc"),
        "fixture_source": {"url": "https://play.hotspawn.com/lobby",
                           "read_utc": (snap.get("access", {}).get("hotspawn_lobby_page", {})
                                        or {}).get("at_utc"),
                           "cache_age_seconds": (snap.get("access", {})
                                                 .get("hotspawn_lobby_page", {}) or {}).get(
                                                     "age_header")},
        "vrs": {"snapshot": vrs_meta.get("snapshot"), "source_url": vrs_meta.get("source_url"),
                "read_utc": (snap.get("access", {}).get("valve_vrs_file", {}) or {}).get("at_utc"),
                "teams": len(snap.get("vrs_teams") or {})},
        "calibration": calibration,
        "summary": summary,
        "open": open_rows,
        "no_market": no_market,
        "unresolved": unresolved,
        "rejected_joins": rejected,
        "label_disagreements": label_records,
        "source_attempts": attempts,
        "kalshi_not_usable": snap.get("kalshi_not_usable") or [],
        "access": snap.get("access") or {},
        "notes": snap.get("notes") or [],
    }
    (DATA / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
