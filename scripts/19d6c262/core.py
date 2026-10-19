"""Session 19d6c262 resolution core — pure functions, no network.

Mirrors the ourline (f7279a54) VRS model exactly so the numbers are identical to the
featured board's own methodology, and adds the lower-bound origination for one-sided
(low-tier) matchups where only one team carries an official Valve VRS rating.

Valve's own model (ValveSoftware/counter-strike_regional_standings, model/glicko.js):
  "rank delta of 400 points = 90% chance of victory";  Q = ln(10)/400
  g  = 1 / sqrt(1 + 3*Q^2*RD^2/pi^2);   ev = 1 / (1 + 10^(g*(r-ro)/-400))
model/fit.js evaluates expected win rates with a fixed RD of 75 (defaultGlickoParams.rd).
We keep the SAME g, RD and the ourline-fitted slope k (least squares of logit(market)
on the rating delta over eligible priced fixtures) so a model pick here equals the pick
the ourline board would publish if its VRS snapshot were inside its 14-day window.
"""
from __future__ import annotations
import math

VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0  # logit(p) = C * delta for Valve's formula
VRS_FLOOR_POINTS = 381  # standing #380 (Fruju) in standings_global_2026_10_05.md — verified
VRS_FLOOR_STANDING = 380


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    """P(team A beats team B) from Valve VRS points; k scales Valve's slope (k=1 -> Valve)."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def confidence_label(p_pick: float) -> float:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def decimal_to_american(dec):
    if dec is None or dec <= 1.0:
        return None
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def make_line(prob_a: float, team_a: str, team_b: str, basis: str, confidence: str | None = None, **extra) -> dict:
    """Build a resolved line with pick, both probabilities and fair odds (1/p)."""
    prob_a = min(max(prob_a, 1e-6), 1 - 1e-6)
    prob_b = 1.0 - prob_a
    side = "a" if prob_a >= prob_b else "b"
    p_pick = max(prob_a, prob_b)
    fair_a, fair_b = 1 / prob_a, 1 / prob_b
    out = {
        "basis": basis, "prob_a": round(prob_a, 4), "prob_b": round(prob_b, 4),
        "pick_side": side, "pick_team": team_a if side == "a" else team_b,
        "pick_prob": round(p_pick, 4), "confidence": confidence or confidence_label(p_pick),
        "fair_decimal_a": round(fair_a, 3), "fair_decimal_b": round(fair_b, 3),
        "fair_american_a": decimal_to_american(fair_a), "fair_american_b": decimal_to_american(fair_b),
    }
    out.update(extra)
    return out
