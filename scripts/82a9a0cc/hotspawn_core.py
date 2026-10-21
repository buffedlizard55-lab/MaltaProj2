"""Pure probability and identity helpers for the 82a9a0cc HotSpawn-live board.

No network, no HotSpawn ownership data, and no hidden defaults live here.  A line can be
created only from retained two-way market prices or from dated official Valve VRS points.
"""
from __future__ import annotations

import math
import re
import unicodedata

VALVE_RD = 75.0
VALVE_Q = math.log(10.0) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q**2 * VALVE_RD**2 / math.pi**2)
VALVE_C = VALVE_G * math.log(10.0) / 400.0
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "thunderpick": 1.0}
SPORTSBOOKS = frozenset(SOURCE_WEIGHTS)

# Narrow, evidence-gated source spelling decision.  It is NEVER sufficient by itself: the
# resolver additionally requires the exact opponent, exact kickoff, same competition family,
# and at least two independent sportsbook quotes.
MARKET_ALIASES = {
    ("excybershoke", "cybershoke"): (
        "HotSpawn labels the roster ex-CYBERSHOKE while Bovada and Melbet omit the ex- prefix; "
        "both quote BlinkDagger at the exact HotSpawn kickoff in CIS LAN Championship #9."
    ),
}


def norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


def match_name(fixture_name: str, source_name: str) -> tuple[bool, str | None]:
    """Return (matches, alias_note). Exact normalized names need no note."""
    a, b = norm(fixture_name), norm(source_name)
    if a and a == b:
        return True, None
    note = MARKET_ALIASES.get((a, b)) or MARKET_ALIASES.get((b, a))
    return (True, note) if note else (False, None)


def no_vig(decimal_a, decimal_b) -> tuple[float, float] | None:
    try:
        da, db = float(decimal_a), float(decimal_b)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(da) and math.isfinite(db)) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:
        return None
    return ia / book, ib / book


def american_to_decimal(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value >= 100:
        return 1.0 + value / 100.0
    if value <= -100:
        return 1.0 + 100.0 / abs(value)
    return None


def quote_probability(quote: dict) -> float | None:
    """Re-derive P(source team_a), never trusting a stored derived probability."""
    fmt = quote.get("raw_format")
    try:
        raw_a, raw_b = quote["raw_a"], quote["raw_b"]
    except KeyError:
        return None
    if fmt == "american":
        da, db = american_to_decimal(raw_a), american_to_decimal(raw_b)
    elif fmt == "decimal":
        try:
            da, db = float(raw_a), float(raw_b)
        except (TypeError, ValueError):
            return None
    elif fmt == "yes mid ($)":
        try:
            pa, pb = float(raw_a), float(raw_b)
        except (TypeError, ValueError):
            return None
        if not (0 < pa < 1 and 0 < pb < 1):
            return None
        da, db = 1.0 / pa, 1.0 / pb
    else:
        return None
    result = no_vig(da, db)
    return result[0] if result else None


def market_consensus(oriented_quotes: list[dict]) -> float | None:
    """Weighted mean of independently re-derived team-A probabilities."""
    usable = [q for q in oriented_quotes if isinstance(q.get("prob_fixture_a"), float)]
    if not usable:
        return None
    total = sum(SOURCE_WEIGHTS.get(q["source_key"], 1.0) for q in usable)
    return sum(SOURCE_WEIGHTS.get(q["source_key"], 1.0) * q["prob_fixture_a"] for q in usable) / total


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def vrs_probability(points_a: float, points_b: float, k: float) -> float:
    return sigmoid(float(k) * VALVE_C * (float(points_a) - float(points_b)))


def confidence(prob_pick: float, directional: bool = False) -> str:
    if directional:
        return "Directional"
    if prob_pick >= 0.70:
        return "Strong"
    if prob_pick >= 0.60:
        return "Solid"
    if prob_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def fair_decimal(probability: float) -> float:
    return round(1.0 / probability, 3)


def make_line(prob_a: float, team_a: str, team_b: str, basis: str, *, directional=False,
              **extra) -> dict:
    prob_a = min(max(float(prob_a), 0.000001), 0.999999)
    prob_b = 1.0 - prob_a
    side = "a" if prob_a >= prob_b else "b"
    pick_prob = max(prob_a, prob_b)
    line = {
        "basis": basis,
        "prob_a": round(prob_a, 4),
        "prob_b": round(prob_b, 4),
        "pick_side": side,
        "pick_team": team_a if side == "a" else team_b,
        "pick_prob": round(pick_prob, 4),
        "confidence": confidence(pick_prob, directional),
        "fair_decimal_a": fair_decimal(prob_a),
        "fair_decimal_b": fair_decimal(prob_b),
        "directional": bool(directional),
    }
    line.update(extra)
    return line
