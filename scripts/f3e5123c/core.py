#!/usr/bin/env python3
"""Session f3e5123c pure helpers — zero network calls.

Math only: proportional no-vig, multi-source consensus, official Valve VRS
Glicko curve with a market-calibrated slope, team-name canonicalisation.
HotSpawn crowd/pick percentages are NEVER read here and never used as a
probability input anywhere in this session's pipeline.
"""
from __future__ import annotations

import math
import re
import unicodedata

# Valve VRS Glicko constants (ValveSoftware/counter-strike_regional_standings
# model/glicko.js): RD = 75, q = ln(10)/400, g(RD) as below.
VALVE_RD = 75.0
VALVE_Q = math.log(10.0) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10.0) / 400.0  # logit(p) = k * VALVE_C * delta_points

SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "thunderpick": 1.0, "kalshi": 1.0}

_SUFFIX = {"team", "esports", "esport", "gaming", "gg", "club", "cs", "cs2"}
_PREFIX = {"team", "the"}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    """P(A beats B) from official Valve VRS points; k scales Valve's slope."""
    return sigmoid(float(k) * VALVE_C * (float(points_a) - float(points_b)))


def no_vig(dec_a, dec_b):
    """Proportional margin removal for a two-way price; None if implausible."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(da) and math.isfinite(db)) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.94 <= book <= 1.30:
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


def decimals_from_raw(q: dict):
    """Re-derive (decimal_a, decimal_b) from a snapshot quote's raw fields."""
    fmt = q.get("raw_format")
    ra, rb = q.get("raw_a"), q.get("raw_b")
    try:
        if fmt == "decimal" and ra is not None and rb is not None:
            return float(ra), float(rb)
        if fmt == "yes mid ($)" and ra is not None and rb is not None:
            fa, fb = float(ra), float(rb)
            if 0.0 < fa < 1.0 and 0.0 < fb < 1.0:
                return 1.0 / fa, 1.0 / fb
            return None
        if fmt == "american" and ra is not None and rb is not None:
            def conv(p):
                p = float(p)
                return 1.0 + p / 100.0 if p >= 100 else (1.0 + 100.0 / abs(p) if p <= -100 else None)
            da, db = conv(ra), conv(rb)
            return (da, db) if da and db else None
        if q.get("decimal_a") is not None and q.get("decimal_b") is not None:
            return float(q["decimal_a"]), float(q["decimal_b"])
    except (TypeError, ValueError):
        return None
    return None


def consensus(entries: list[dict]):
    """Weighted mean of de-vigged P(team A) across external sources."""
    usable = [e for e in entries if isinstance(e.get("prob_a"), (int, float))]
    if not usable:
        return None
    wsum = sum(SOURCE_WEIGHTS.get(str(e.get("source_key")), 1.0) for e in usable)
    pa = sum(SOURCE_WEIGHTS.get(str(e.get("source_key")), 1.0) * float(e["prob_a"]) for e in usable) / wsum
    probs = [float(e["prob_a"]) for e in usable]
    return {
        "prob_a": round(pa, 4),
        "prob_b": round(1.0 - pa, 4),
        "n_sources": len(usable),
        "sources": sorted({str(e.get("source_key")) for e in usable}),
        "spread_a": round(max(probs) - min(probs), 4) if len(probs) > 1 else None,
    }


def decimal_to_american(dec):
    if dec is None or dec <= 1.0:
        return None
    return int(round((dec - 1.0) * 100.0)) if dec >= 2.0 else int(round(-100.0 / (dec - 1.0)))


def confidence_label(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def make_line(prob_a, team_a, team_b, basis, confidence=None, **extra):
    pa = min(max(float(prob_a), 1e-6), 1.0 - 1e-6)
    pb = 1.0 - pa
    side = "a" if pa >= pb else "b"
    fa, fb = 1.0 / pa, 1.0 / pb
    out = {
        "basis": basis,
        "prob_a": round(pa, 4),
        "prob_b": round(pb, 4),
        "pick_side": side,
        "pick_team": team_a if side == "a" else team_b,
        "pick_prob": round(max(pa, pb), 4),
        "confidence": confidence or confidence_label(max(pa, pb)),
        "fair_decimal_a": round(fa, 3),
        "fair_decimal_b": round(fb, 3),
        "fair_american_a": decimal_to_american(fa),
        "fair_american_b": decimal_to_american(fb),
    }
    out.update(extra)
    return out


def norm_tokens(name) -> list[str]:
    if not name:
        return []
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def canon_team(name, allow_ex_strip: bool = False):
    """Return (canonical_key, audit_note|None). Deterministic, conservative."""
    toks = norm_tokens(name)
    notes = []
    if allow_ex_strip and toks[:1] == ["ex"]:
        toks = toks[1:]
        notes.append("stripped leading 'ex-' roster-prefix")
    while toks and toks[0] in _PREFIX:
        toks = toks[1:]
    while toks and toks[-1] in _SUFFIX and len(toks) > 1:
        toks = toks[:-1]
    key = "".join(toks)
    return key, ("; ".join(notes) if notes else None)


def hours_apart(a, b):
    from datetime import datetime

    def parse(v):
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None

    da, db = parse(a), parse(b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds()) / 3600.0
