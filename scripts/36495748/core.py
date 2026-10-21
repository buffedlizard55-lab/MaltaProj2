"""Session 36495748 — shared exact math for the every-match resolution ladder.

Every formula here is either (a) elementary probability arithmetic, or (b) copied from a
published, citable source named in the comment above it. Nothing in this module guesses:
probabilities are only ever derived from stored bookmaker/exchange decimal prices or from
official Valve Regional Standings points read out of Valve's own GitHub repository.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone


# --------------------------------------------------------------------- time / names

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def norm(name) -> str:
    """Lowercase, accent-fold, strip org suffixes/punctuation -> comparison key (never displayed)."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(esports|e sports|gaming|team|club|cs2|cs go|org)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(name) -> tuple:
    return tuple(norm(name).split())


def same_name(a, b) -> bool:
    """Strict identity: equal after normalisation, or equal token multiset (word-order only)."""
    if not a or not b:
        return False
    if norm(a) == norm(b):
        return True
    return sorted(tokens(a)) == sorted(tokens(b)) and norm(a) != ""


# --------------------------------------------------------------------- prices

def no_vig(dec_first, dec_second):
    """Proportional removal of a two-way bookmaker margin.

    Same standard construction the whole repo uses (e.g. scripts/f7279a54/core.py):
    implied_i = 1/decimal_i, probability_i = implied_i / (implied_1 + implied_2).
    Books whose implied total is outside [0.95, 1.30] are treated as bad data, not prices.
    Returns (p_first, p_second, overround) or None.
    """
    try:
        d1, d2 = float(dec_first), float(dec_second)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(d1) and math.isfinite(d2)) or d1 <= 1.0 or d2 <= 1.0:
        return None
    i1, i2 = 1.0 / d1, 1.0 / d2
    book = i1 + i2
    if not 0.95 <= book <= 1.30:
        return None
    return i1 / book, i2 / book, book - 1.0


# Consensus source weights published upstream (scripts/f7279a54/core.py SOURCE_WEIGHTS):
# Pinnacle counts double; every other admissible book/exchange counts once.
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "kalshi": 1.0,
                  "thunderpick": 1.0, "bo3gg_thunderpick": 1.0}


def consensus_prob_a(entries):
    """Weighted mean of per-source no-vig probabilities for team A; entries: dicts with
    keys source_key, prob_a. Mirrors the upstream consensus so this desk's re-derived
    market number is directly comparable with the canonical board."""
    usable = [e for e in entries if isinstance(e.get("prob_a"), (int, float))]
    if not usable:
        return None
    wsum = sum(SOURCE_WEIGHTS.get(e.get("source_key"), 1.0) for e in usable)
    pa = sum(SOURCE_WEIGHTS.get(e.get("source_key"), 1.0) * float(e["prob_a"]) for e in usable) / wsum
    return {"prob_a": pa, "prob_b": 1.0 - pa, "n_sources": len(usable),
            "sources": sorted({e.get("source_key") for e in usable}),
            "min_a": min(float(e["prob_a"]) for e in usable),
            "max_a": max(float(e["prob_a"]) for e in usable)}


# --------------------------------------------------------------------- Valve VRS model

# Valve's own expected-win formula, from ValveSoftware/counter-strike_regional_standings
# (model/glicko.js): a 400-point rank delta = 90% win chance before the RD damping,
# Q = ln(10)/400, g = 1/sqrt(1 + 3 Q^2 RD^2 / pi^2) with fixed RD = 75 (model/fit.js),
# ev = 1 / (1 + 10^(g (r-ro) / -400))  ==  sigmoid( g * ln(10)/400 * delta ).
VALVE_RD = 75.0
_VALVE_Q = math.log(10) / 400.0
_VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * _VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = _VALVE_G * math.log(10) / 400.0

# The slope is NOT taken from Valve raw: Valve's README itself warns the curve is too
# steep, so upstream sessions fit k by least squares of logit(market) = k*C*delta on
# fixtures that had both a market consensus and two VRS ratings. The builder reads the
# current fitted k (and its pair count / MAE) from data/f7279a54/board.json at build
# time and records it on every model row; this fallback only applies if that calibration
# block is missing, and is flagged when used.
FALLBACK_K = 0.43077894236569164  # f7279a54 calibration as of 2026-10-21T12:28Z (n=60, MAE 0.077)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob_a(points_a: float, points_b: float, k: float) -> float:
    """P(team A beats team B) from official VRS points, market-calibrated slope k."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def confidence_label(p_pick: float) -> str:
    """Repo-wide label ladder (same cutoffs as the canonical boards)."""
    p = abs(p_pick)
    if p >= 0.80:
        return "Heavy favourite"
    if p >= 0.70:
        return "Strong"
    if p >= 0.60:
        return "Solid"
    if p >= 0.525:
        return "Lean"
    return "Toss-up"


def pct(p, digits=1):
    if p is None:
        return "—"
    return f"{100.0 * float(p):.{digits}f}%"
