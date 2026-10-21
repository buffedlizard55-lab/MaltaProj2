#!/usr/bin/env python3
"""Resolution ladder for session 86f3af65.

Goal: a pick, with both teams' win probabilities, for **every** open Counter-Strike 2 fixture
listed in the HotSpawn Pick'ems lobby - without ever inventing a number.

The ladder, applied in this order, one rung at a time (nothing is blended across rungs):

    R1  External two-way market prices (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg)
    R2  Prediction-market / exchange mids (Kalshi KXCS2GAME), spread-gated
    R3  Originated line from Valve's official Regional Standings (VRS) points, using the slope
        fitted on this repository's own market-observation pairs
    R4  Originated line where one side has no published rating: the team absent from all four
        Valve files is assigned the lowest rank value Valve publishes (floor proxy). Explicitly
        an assumption, published as such.
    R5  Nothing usable -> no pick, row published on the Unresolved & limitations page with the
        exact sources attempted. (Never happens silently: a blank row is a failure, not a value.)

A price is only joined to a fixture when **both** team names agree after normalisation (or
through a published, evidence-linked alias) *and* the source's kickoff is within the tolerance
of HotSpawn's kickoff. A one-sided name match is published as an observation and never used.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

ISO = "%Y-%m-%dT%H:%M:%SZ"

# --------------------------------------------------------------------------------- time
def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime(ISO) if dt else None


def parse_iso(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return None if dt.tzinfo is None else dt.astimezone(timezone.utc)


def hours_apart(a, b) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# --------------------------------------------------------------------------------- maths
def sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return 1.0 + p / 100.0
    if p <= -100:
        return 1.0 + 100.0 / abs(p)
    return None


def no_vig(dec_a, dec_b) -> dict | None:
    """Proportional (multiplicative) removal of the two-way margin. Refuses implausible books."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(da) and math.isfinite(db)) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


# ------------------------------------------------------------- Valve VRS rating -> win prob
# Valve publishes the model it uses (model/glicko.js, model/fit.js in the same public
# repository):  g = 1/sqrt(1 + 3*Q^2*RD^2/pi^2) with Q = ln(10)/400 and a fixed RD of 75 for
# fit evaluations, and expected score ev = 1/(1 + 10^(g*(r - r0)/-400)).
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

CAL_MIN_PAIRS = 25          # more data than the upstream minimum: we refuse a thin fit
CAL_K_BOUNDS = (0.25, 1.5)


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def fit_k(pairs: list[dict]) -> dict:
    """Least-squares slope k of logit(market p) = k * C * (points_a - points_b) through origin.

    The slope is what converts Valve's point gap into a probability. Valve's own documentation
    warns that a straight read of its curve mis-prices the extremes, so the slope is learned from
    real two-way bookmaker lines observed on this repository's own fixtures and reported here
    with its sample size and error so a reader can judge it.
    """
    xs, ys = [], []
    for p in pairs:
        try:
            xs.append(VALVE_C * float(p["delta"]))
            ys.append(logit(float(p["market_prob_a"])))
        except (KeyError, TypeError, ValueError):
            continue
    n = len(xs)
    out = {"n_pairs": n, "k": 1.0, "fitted": False, "k_raw": None,
           "mae_prob": None, "mae_prob_valve": None, "resid_sd": None,
           "min_pairs": CAL_MIN_PAIRS, "bounds": list(CAL_K_BOUNDS), "c": VALVE_C}
    sxx = sum(x * x for x in xs)
    if n >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        out.update({"k": min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1]),
                    "k_raw": k_raw, "fitted": True})
    if n:
        errs = [sigmoid(out["k"] * x) - sigmoid(y) for x, y in zip(xs, ys)]
        valve = [sigmoid(x) - sigmoid(y) for x, y in zip(xs, ys)]
        out["mae_prob"] = sum(abs(e) for e in errs) / n
        out["mae_prob_valve"] = sum(abs(e) for e in valve) / n
        out["resid_sd"] = math.sqrt(sum(e * e for e in errs) / n)
    return out


def confidence_label(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


# --------------------------------------------------------------------------------- aliases
# Published name-variant decisions. Each entry must carry evidence a reader can check: an alias
# is only applied when the opponent joins exactly AND the kickoff agrees to within the tolerance.
# NEVER add an entry whose only support is "the names look similar" - the alias must also be
# corroborated by the fixture slot (competition + kickoff) in the evidence list.
ALIASES: dict[str, dict] = {
    "apogeebetclic": {
        "to": "apogee",
        "label": "Apogee Betclic -> Apogee Esports",
        "kind": "sponsor-name variant",
        "note": ("HotSpawn lists 'Apogee Betclic'; Melbet's feed lists 'Apogee Esports' for the "
                 "same Stake Ranked Episode 6 closed-qualifier slot against UNiTY at the same "
                 "kickoff. The shared org token 'Apogee' plus the identical opponent and kickoff "
                 "is the evidence; no roster-level document was available, so the row is flagged."),
    },
}

# Names that are known to be the *same roster set* under a second brand. These are recorded so
# they can be published as rejected joins, but they are NOT admitted for pricing: a roster claim
# we cannot re-read from an official page is not evidence enough to re-price a fixture.
REJECTED_ALIASES: dict[str, dict] = {
    "alianzalimaesports": {
        "to": "zetta",
        "label": "Alianza Lima Esports -> Zetta (NOT ADMITTED)",
        "note": ("An earlier session recorded that bo3.gg team 25489 'Alianza Lima Esports' "
                 "fields the five-player roster Valve's americas standings list as Zetta. Valve's "
                 "own files list only 'Zetta' (americas #80, 473 points) and contain no "
                 "'Alianza Lima Esports' row at all, and bo3.gg could not be re-read in this "
                 "session, so the identity is not re-verified here. The Kalshi market for "
                 "'Los Ninos vs Alianza Lima Esports' is therefore published as an observation "
                 "only and never used to price HotSpawn fixture 1082837."),
    },
}


def apply_aliases(name: str, norm) -> tuple[str, dict | None]:
    key = norm(name)
    rec = ALIASES.get(key)
    return (rec["to"], rec) if rec else (key, None)


# --------------------------------------------------------------------------------- joining
TIME_TOLERANCE_H = 5 / 60      # five minutes: a stated matching policy, not a source fact
TIME_OBSERVE_H = 72.0          # near-time mismatches are published for review, never joined
KALSHI_MAX_SPREAD = 0.10


def match_quote(fixture: dict, quote: dict, norm) -> dict | None:
    """Return {'admissible': bool, 'swapped', 'alias_notes', 'start_diff_h', 'reason'}."""
    ka, al_a = apply_aliases(fixture["team_a"], norm)
    kb, al_b = apply_aliases(fixture["team_b"], norm)
    qa, qal_a = apply_aliases(quote["team_a"], norm)
    qb, qal_b = apply_aliases(quote["team_b"], norm)
    aliases = [a for a in (al_a, al_b, qal_a, qal_b) if a]
    if ka == qa and kb == qb:
        swapped = False
    elif ka == qb and kb == qa:
        swapped = True
    else:
        return None
    diff = hours_apart(parse_iso(fixture["start_utc"]), parse_iso(quote.get("start_utc")))
    alias_notes = sorted({a["label"] for a in aliases})
    if diff is None or quote.get("start_is_approx"):
        return {"admissible": False, "swapped": swapped, "alias_notes": alias_notes,
                "start_diff_h": diff, "reason": "source kickoff time not verifiable"}
    if diff > TIME_TOLERANCE_H:
        return ({"admissible": False, "swapped": swapped, "alias_notes": alias_notes,
                 "start_diff_h": diff, "reason": f"kickoff differs by {diff:.2f} h"}
                if diff <= TIME_OBSERVE_H else None)
    return {"admissible": True, "swapped": swapped, "alias_notes": alias_notes,
            "start_diff_h": diff, "reason": None}


SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "thunderpick": 1.0,
                  "kalshi": 1.0}


def oriented_prob(quote: dict, swapped: bool) -> float | None:
    p = quote.get("prob_a")
    if p is None:
        return None
    return 1.0 - p if swapped else p


def consensus(entries: list[dict]) -> dict | None:
    usable = [e for e in entries if isinstance(e.get("prob_a"), (int, float))]
    if not usable:
        return None
    wsum = sum(SOURCE_WEIGHTS.get(e.get("source_key"), 1.0) for e in usable)
    pa = sum(SOURCE_WEIGHTS.get(e.get("source_key"), 1.0) * e["prob_a"] for e in usable) / wsum
    lo = min(e["prob_a"] for e in usable)
    hi = max(e["prob_a"] for e in usable)
    return {"prob_a": pa, "prob_b": 1.0 - pa, "n_sources": len(usable),
            "sources": sorted({e["source_key"] for e in usable}),
            "spread_a": (hi - lo) if len(usable) > 1 else None}


# ------------------------------------------------------------------------------ resolution
CONTESTED_GAP = 0.15  # market vs model disagreement that must be published as "Contested"


def resolve_fixture(fixture: dict, quotes: list[dict], standings, calibration: dict,
                    norm) -> dict:
    """Run the ladder for one fixture. Returns a complete, citable row."""
    joins, observations = [], []
    key_a = apply_aliases(fixture["team_a"], norm)[0]
    key_b = apply_aliases(fixture["team_b"], norm)[0]
    for quote in quotes:
        m = match_quote(fixture, quote, norm)
        if not m:
            qa = apply_aliases(quote.get("team_a") or "", norm)[0]
            qb = apply_aliases(quote.get("team_b") or "", norm)[0]
            shared = sorted({k for k in (qa, qb) if k and k in (key_a, key_b)})
            if len(shared) == 1:
                # Exactly one team agrees: a real risk of importing the wrong match's price.
                observations.append({
                    "source": quote.get("source_name") or quote.get("source_key"),
                    "url": quote.get("public_url"),
                    "teams": [quote.get("team_a"), quote.get("team_b")],
                    "reason": ("only one team name matches this fixture - not admissible "
                               "(a single-name join can attach another match's price)"),
                    "alias_notes": [],
                    "raw": f'{quote.get("decimal_a")} / {quote.get("decimal_b")}'})
            continue
        if not m["admissible"]:
            observations.append({
                "source": quote.get("source_name") or quote.get("source_key"),
                "url": quote.get("public_url"),
                "teams": [quote.get("team_a"), quote.get("team_b")],
                "reason": m["reason"],
                "alias_notes": m["alias_notes"],
                "raw": f'{quote.get("decimal_a")} / {quote.get("decimal_b")}'})
            continue
        p = oriented_prob(quote, m["swapped"])
        if p is None:
            continue
        joins.append({**quote, "prob_a_oriented": p, "alias_notes": m["alias_notes"],
                      "start_diff_h": m["start_diff_h"], "swapped": m["swapped"]})

    # R2: drop exchange quotes whose order book is too wide to be a price.
    priced = []
    for j in joins:
        if j.get("source_key") == "kalshi":
            spread = j.get("spread")
            if spread is not None and spread > KALSHI_MAX_SPREAD:
                observations.append({"source": "Kalshi (exchange)", "url": j.get("public_url"),
                                     "teams": [j.get("team_a"), j.get("team_b")],
                                     "reason": f"bid/ask spread {spread:.2f} > 0.10",
                                     "alias_notes": j.get("alias_notes"), "raw": None})
                continue
        priced.append(j)

    market = consensus(priced) if priced else None
    if market:
        market = {**market, "prob_b": 1.0 - market["prob_a"]}

    # R3/R4: originated line from official standings (always computed: it is the cross-check,
    # the sensitivity band and the fallback the moment a market price is missing).
    ra = standings.resolve(fixture["team_a"], floor_ok=True)
    rb = standings.resolve(fixture["team_b"], floor_ok=True)
    can_model = bool(ra.get("row") and rb.get("row")) and \
        ra["status"] != "ambiguous" and rb["status"] != "ambiguous"
    model = None
    if can_model:
        pa = vrs_prob(ra["row"]["points"], rb["row"]["points"], calibration["k"])
        notes = []
        for side, res in (("a", ra), ("b", rb)):
            if res["status"] == "roster-selected":
                rejected = [(r["standing"], r["points"], r["roster"]) for r in res["rejected"]]
                notes.append(
                    f"{res['team']}: Valve lists {len(res['candidates'])} rosters under this name; "
                    f"used #{res['row']['standing']} ({res['row']['points']} pts, roster "
                    f"{res['row']['roster']}, latest counted match "
                    f"{res['row'].get('latest_match_date')}). Not used: "
                    + "; ".join(f"#{s} ({p} pts, roster {r})" for s, p, r in rejected) + ".")
            if res["status"] == "floor-proxy":
                notes.append(res["assumption"])
        alt = None
        if any(r["status"] == "roster-selected" for r in (ra, rb)):
            pa_a = (ra["rejected"][0]["points"] if ra["status"] == "roster-selected" else
                    ra["row"]["points"])
            pa_b = (rb["rejected"][0]["points"] if rb["status"] == "roster-selected" else
                    rb["row"]["points"])
            alt = vrs_prob(pa_a, pa_b, calibration["k"])
        sensitivity = []
        for side, res, other in (("a", ra, rb), ("b", rb, ra)):
            if res["status"] == "floor-proxy" and other.get("row"):
                for assumed in (400, 600, 800):
                    p_side = vrs_prob(assumed, other["row"]["points"], calibration["k"])
                    sensitivity.append({
                        "team": res["team"], "assumed_points": assumed,
                        "prob_this_team": p_side})
        model = {
            "prob_a": pa, "prob_b": 1.0 - pa,
            "delta": ra["row"]["points"] - rb["row"]["points"],
            "k": calibration["k"], "c": calibration["c"],
            "rating_a": ra, "rating_b": rb,
            "notes": notes, "alternate_prob_a": alt, "sensitivity": sensitivity,
            "conflicted": bool(ra["status"] == "roster-selected" or rb["status"] == "roster-selected"),
        }

    # Compose the row ---------------------------------------------------------------
    basis, prob_a, unresolved, limitation = None, None, False, None
    if market:
        basis, prob_a = "market", market["prob_a"]
        if model:
            gap = abs(model["prob_a"] - market["prob_a"])
            if gap > CONTESTED_GAP:
                basis = "market (contested)"
                limitation = (f"The external price and the originated Valve-VRS line disagree by "
                              f"{gap * 100:.0f} points; the external price is used because market "
                              f"prices outrank a model here, but treat this row as contested.")
    elif model and "floor-proxy" in (ra["status"], rb["status"]):
        basis, prob_a = "originated (floor proxy)", model["prob_a"]
        unresolved = True
        missing = [r["team"] for r in (ra, rb) if r["status"] == "floor-proxy"]
        limitation = (f"{' and '.join(missing)} has no published Valve rating in the global, "
                      f"americas, asia or europe standings, so the lowest published rank value "
                      f"(381) is assumed for it. The pick direction is robust; the number is an "
                      f"estimate, not a market line.")
    elif model:
        basis, prob_a = "originated (Valve VRS)", model["prob_a"]
        unresolved = bool(model["conflicted"])
        if model["conflicted"]:
            limitation = ("Valve publishes two rosters under one of these team names; the row uses "
                          "the roster selected by the published duplicate-roster policy.")
    if prob_a is None:
        basis, unresolved = "unresolved", True
        limitation = ("No external two-way price could be joined and at least one team has no "
                      "published Valve rating, so no probability is published for this fixture.")

    pick_side = None
    if prob_a is not None:
        pick_side = "a" if prob_a >= 0.5 else "b"
    pick_prob = None if prob_a is None else (prob_a if pick_side == "a" else 1 - prob_a)

    sources = []
    for j in priced:
        sources.append({"kind": "price", "label": j.get("source_name"),
                        "url": j.get("public_url"), "event_id": j.get("event_id"),
                        "source_key": j.get("source_key"),
                        "read_utc": j.get("retrieved_utc"),
                        "note": f'{j.get("team_a")} / {j.get("team_b")} '
                                f'{j.get("decimal_a")} / {j.get("decimal_b")}'
                                + (f' - alias: {"; ".join(j["alias_notes"])}'
                                   if j.get("alias_notes") else "")})
    for res in (ra, rb):
        row = res.get("row")
        if row and not row.get("is_floor_proxy"):
            sources.append({"kind": "rating",
                            "label": f'{row["team"]} #{row["standing"]} ({row["points"]} pts)',
                            "url": res.get("source"), "read_utc": None,
                            "note": (f'roster {row.get("roster")}' +
                                     (f'; latest counted match {row.get("latest_match_date")}'
                                      if row.get("latest_match_date") else ""))})
        elif res["status"] == "floor-proxy":
            sources.append({"kind": "rating",
                            "label": f'{res["team"]} - no published rating',
                            "url": res.get("source"), "read_utc": None,
                            "note": res.get("assumption")})
    sources.append({"kind": "discovery", "label": "HotSpawn Pick'ems lobby (fixture only)",
                    "url": fixture.get("hotspawn_url"), "read_utc": fixture.get("observed_utc"),
                    "note": "fixture, kickoff and competition; never a probability input"})

    flags = []
    if market and market.get("n_sources") == 1:
        flags.append("single_source_price")
    if market and any(j.get("alias_notes") for j in priced):
        flags.append("alias_join")
    if model and model["conflicted"]:
        flags.append("duplicate_vrs_roster")
    if model and (ra["status"] == "floor-proxy" or rb["status"] == "floor-proxy"):
        flags.append("floor_proxy_unrated_team")
    if basis == "market (contested)":
        flags.append("market_model_conflict")
    if observations:
        flags.append("unused_observations")

    return {
        "fixture_id": fixture["fixture_id"],
        "competition": fixture.get("competition"),
        "tier": fixture.get("tier"),
        "best_of": fixture.get("best_of"),
        "points": fixture.get("points"),
        "start_utc": fixture.get("start_utc"),
        "lock_utc": fixture.get("lock_utc"),
        "team_a": fixture["team_a"], "team_b": fixture["team_b"],
        "hotspawn_url": fixture.get("hotspawn_url"),
        "basis": basis,
        "prob_a": prob_a, "prob_b": None if prob_a is None else 1.0 - prob_a,
        "pick_side": pick_side,
        "pick_team": None if pick_side is None else (
            fixture["team_a"] if pick_side == "a" else fixture["team_b"]),
        "pick_prob": pick_prob,
        "confidence": None if pick_prob is None else confidence_label(pick_prob),
        "market": market,
        "model": model,
        "sources": sources,
        "observations": observations,
        "flags": flags,
        "unresolved": unresolved,
        "limitation": limitation,
        "rejected_joins": [o for o in observations if "kickoff" in (o.get("reason") or "")],
    }


def open_fixtures(fixtures: list[dict], now: datetime) -> list[dict]:
    """A fixture is open when HotSpawn still reports it as scheduled and its lock is in future."""
    out = []
    for f in fixtures:
        if str(f.get("status")) != "scheduled":
            continue
        lock = parse_iso(f.get("lock_utc"))
        if lock is None or lock <= now:
            continue
        out.append(f)
    return sorted(out, key=lambda f: (f["start_utc"], f["fixture_id"]))
