"""Shared helpers for the picks hub (session 7c2622db).

Pure functions only: every published probability can be re-derived from the
raw numbers stored next to it. No network access, no HotSpawn input.
"""
from __future__ import annotations

import math

# Rating scale. Valve's official model note is "rank delta of 400 points = 90%
# chance of victory" (model/glicko.js in the official standings repository),
# which gives 0.0023865 per point. The canonical every-match board publishes
# slightly different fitted numbers (delta_points / k / prob_a), so this module
# solves the scale back out of that published row at build time and only falls
# back to the constant below, which reproduces the canonical board exactly.
S_PER_POINT_FALLBACK = 0.0024321

# Canonical board slope is refit from eligible priced fixtures in the snapshot.
# Used only when the snapshot does not publish its own slope.
DEFAULT_K = 0.5338


def solve_scale(board: dict, default: float = S_PER_POINT_FALLBACK) -> float:
    """Recover the rating scale from the canonical board's own published row.

    Returns S such that 1/(1+10**(-delta*S*k)) equals the canonical uncalibrated
    probability. Nothing is trusted: the identity is checked before use.
    """
    for row in (board or {}).get("open", []):
        model = row.get("model") or {}
        delta = model.get("delta_points")
        k = model.get("k")
        p = model.get("valve_uncalibrated_prob_a")
        if not delta or not k or not p or not 0 < float(p) < 1:
            continue
        solved = math.log10(float(p) / (1.0 - float(p))) / (float(delta) * float(k))
        if solved > 0:
            return solved
    return default

# Reviewed name decisions for rows this session publishes. Each one is listed
# with its evidence in data/7c2622db/research.json -> coverage.alias_decisions.
ALIASES = {
    "bb team": "BETBOOM",
    "betboom team": "BETBOOM",
    "betboom": "BETBOOM",
    "whitebit team": "WBT",
    "whitebit": "WBT",
    "wbt": "WBT",
    "wrotberry": "WBT",
    "nexus gaming": "Nexus",
    "9z globant": "9z",
    "team aurora": "Aurora",
    "aurora gaming": "Aurora",
    "mouz nxt": "MOUZ NXT",
    "g2 ares": "G2 Ares",
}


def key(name: str | None) -> str:
    """Normalise a team label for joining; never merges different teams."""
    if not name:
        return ""
    return " ".join(str(name).strip().lower().split())


def resolve_alias(name: str | None) -> str:
    k = key(name)
    if k in ALIASES:
        return ALIASES[k]
    return str(name).strip() if name else ""


def model_prob(points_a: float, points_b: float, k: float = DEFAULT_K,
               scale: float = S_PER_POINT_FALLBACK) -> float:
    """Logistic rating-difference model over official Valve ratings.

    1 / (1 + 10 ** (-delta * scale * k)). This is this project's own calibrated
    calculation, not a bookmaker line and not a Valve forecast.
    """
    delta = float(points_a) - float(points_b)
    return 1.0 / (1.0 + 10.0 ** (-delta * float(scale) * float(k)))


def no_vig(dec_a: float, dec_b: float) -> tuple[float, float]:
    """Proportional no-vig derivation for a two-sided decimal quote."""
    ia, ib = 1.0 / float(dec_a), 1.0 / float(dec_b)
    total = ia + ib
    return ia / total, ib / total


def midpoints_normalised(mid_a: float, mid_b: float) -> tuple[float, float]:
    """Normalise two exchange midpoints for the same binary match."""
    total = float(mid_a) + float(mid_b)
    return float(mid_a) / total, float(mid_b) / total


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{100.0 * float(value):.{digits}f}%"


def safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def differential(points, prob_pick, ownership_pick):
    """Listed-points differential of a pick against the crowd that took it.

    points * (pick probability - crowd ownership of the same side). Published in
    LISTED points only: the lobby card advertises tier/stage multipliers but
    never states how they combine, so no score-adjusted number is invented.
    """
    p = safe_float(prob_pick)
    o = safe_float(ownership_pick)
    pts = safe_float(points)
    if p is None or o is None or pts is None:
        return None
    return pts * (p - o)


def swing_eligible(prob_market_low, prob_model, ownership_pick, has_context,
                   total_picks=None, min_picks: int = 10,
                   floor: float = 0.30, min_gap: float = 0.15, max_model_gap: float = 0.10):
    """Contrarian-but-not-stupid gate for one candidate side.

    Returns (eligible, reasons). The four published conditions are:
      G1 the candidate's market/exchange reading is at least `floor`;
      G2 its crowd ownership is at least `min_gap` below that reading (and below half);
      G3 there is at least one dated, source-linked fact about it;
      G4 when a rating model exists, it does not sit more than `max_model_gap` below the
         market reading - this blocks fades that only the crowd disagrees with while both
         the market and the rating model reject them.
    """
    reasons = []
    ok = True
    if total_picks is None:
        ok = False
        reasons.append("crowd sample size not captured for this fixture")
    elif int(total_picks) < min_picks:
        ok = False
        reasons.append(f"crowd sample has only {int(total_picks)} picks (minimum {min_picks})")
    if prob_market_low is None or prob_market_low < floor:
        ok = False
        reasons.append(
            f"market reading {pct(prob_market_low)} below the {pct(floor, 0)} floor"
            if prob_market_low is not None else "no market or exchange reading")
    if ownership_pick is None:
        ok = False
        reasons.append("crowd ownership not captured")
    else:
        if ownership_pick > 0.5:
            ok = False
            reasons.append(f"crowd ownership {pct(ownership_pick, 0)} is not a minority position")
        if prob_market_low is not None and (prob_market_low - ownership_pick) < min_gap:
            ok = False
            reasons.append(
                f"ownership gap {pct(prob_market_low - ownership_pick)} below the {pct(min_gap, 0)} minimum")
    if not has_context:
        ok = False
        reasons.append("no dated source-linked fact recorded for this side")
    if prob_model is not None and prob_market_low is not None and \
            (prob_market_low - prob_model) > max_model_gap:
        ok = False
        reasons.append(f"rating model {pct(prob_model)} sits {pct(prob_market_low - prob_model)} "
                       f"below the market reading (limit {pct(max_model_gap, 0)})")
    return ok, reasons
