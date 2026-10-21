#!/usr/bin/env python3
"""Session 51197e5b pure math & normalisation helpers — zero network calls.

Implements:
  * Proportional (multiplicative) bookmaker margin removal (`no_vig`),
  * Weighted multi-source market consensus (`consensus`),
  * Official Valve Regional Standings (VRS) Glicko win-probability curve (`vrs_prob`)
    from ValveSoftware/counter-strike_regional_standings (`model/glicko.js`, `model/fit.js`),
  * Team-name normalisation with explicit audit trail for `ex-` prefix / org-token stripping,
  * Kalshi `KXCS2GAME` ticker timestamp parser (EDT -> UTC).

HotSpawn pick percentages are NEVER read or used as a probability input anywhere in this module.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

VALVE_RD = 75.0
VALVE_Q = math.log(10.0) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10.0) / 400.0  # logit(p) = VALVE_C * delta for k=1

VRS_FLOOR_STANDING = 380
VRS_FLOOR_POINTS = 381  # Fruju (#380, 381 pts) in standings_global_2026_10_05.md

SOURCE_WEIGHTS = {
    "pinnacle": 2.0,
    "bovada": 1.0,
    "melbet": 1.0,
    "thunderpick": 1.0,
    "kalshi": 1.0,
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PREFIX_TOKENS = {"team", "the"}
_SUFFIX_TOKENS = {"team", "esports", "esport", "gaming", "gg", "club", "cs", "cs2"}

# Documented aliases (normalised key -> (canonical key, audit note)).
ALIASES: dict[str, tuple[str, str]] = {
    "bb": ("betboom", "BetBoom Team is listed as 'BB Team' on some feeds."),
    "nip": ("ninjasinpyjamas", "NIP is the official abbreviation of Ninjas in Pyjamas."),
    "pvision": ("parivision", "PARIVISION is listed as 'PVISION' on some feeds."),
    "9zglobant": ("9z", "9z Team is sponsored as '9z Globant' on some feeds."),
    "aurorayb": ("aurorayoungblud", "Aurora YB is the abbreviation of Aurora Young Blud (#326 in official Valve VRS)."),
    "thirtythree": ("betm", "BET-M is listed under its former slug 'thirtythree' on bo3.gg (team id 22191)."),
}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    """P(team A beats team B) from official Valve VRS points; k scales Valve's slope."""
    return sigmoid(float(k) * VALVE_C * (float(points_a) - float(points_b)))


def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100.0:
        return 1.0 + p / 100.0
    if p <= -100.0:
        return 1.0 + 100.0 / abs(p)
    return None


def decimal_to_american(dec: float | None) -> int | None:
    if dec is None or dec <= 1.0:
        return None
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100.0))
    return int(round(-100.0 / (dec - 1.0)))


def no_vig(dec_a, dec_b) -> dict | None:
    """Proportional removal of bookmaker overround from a two-way price."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(da) or not math.isfinite(db) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.94 <= book <= 1.30:
        return None
    return {
        "prob_a": ia / book,
        "prob_b": ib / book,
        "overround": book - 1.0,
    }


def rederive_quote(q: dict) -> dict | None:
    """Re-derive decimal odds and no-vig probability from raw quote inputs."""
    fmt = q.get("raw_format")
    raw_a, raw_b = q.get("raw_a"), q.get("raw_b")
    da, db = None, None
    try:
        if fmt == "american" and raw_a is not None and raw_b is not None:
            da, db = american_to_decimal(raw_a), american_to_decimal(raw_b)
        elif fmt == "decimal" and raw_a is not None and raw_b is not None:
            da, db = float(raw_a), float(raw_b)
        elif fmt == "yes mid ($)" and raw_a is not None and raw_b is not None:
            fa, fb = float(raw_a), float(raw_b)
            if 0.0 < fa < 1.0 and 0.0 < fb < 1.0:
                da, db = 1.0 / fa, 1.0 / fb
        elif q.get("decimal_a") is not None and q.get("decimal_b") is not None:
            da, db = float(q["decimal_a"]), float(q["decimal_b"])
    except (TypeError, ValueError):
        return None
    nv = no_vig(da, db)
    if not nv:
        return None
    return {
        **q,
        "decimal_a": round(da, 4),
        "decimal_b": round(db, 4),
        "prob_a": nv["prob_a"],
        "overround": nv["overround"],
    }


def consensus(entries: list[dict]) -> dict | None:
    """Weighted mean of de-vigged team-A win probabilities across external sources."""
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


def confidence_label(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def make_line(
    prob_a: float,
    team_a: str,
    team_b: str,
    basis: str,
    market_weight: float = 0.0,
    confidence: str | None = None,
    **extra,
) -> dict:
    """Construct a standardised line object with pick, probabilities, and fair odds."""
    pa = min(max(float(prob_a), 1e-6), 1.0 - 1e-6)
    pb = 1.0 - pa
    side = "a" if pa >= pb else "b"
    p_pick = max(pa, pb)
    fair_a, fair_b = 1.0 / pa, 1.0 / pb
    out = {
        "basis": basis,
        "market_weight": market_weight,
        "prob_a": round(pa, 4),
        "prob_b": round(pb, 4),
        "pick_side": side,
        "pick_team": team_a if side == "a" else team_b,
        "pick_prob": round(p_pick, 4),
        "confidence": confidence or confidence_label(p_pick),
        "fair_decimal_a": round(fair_a, 3),
        "fair_decimal_b": round(fair_b, 3),
        "fair_american_a": decimal_to_american(fair_a),
        "fair_american_b": decimal_to_american(fair_b),
    }
    out.update(extra)
    return out


def norm_tokens(name: str | None) -> list[str]:
    if not name:
        return []
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def canon_team(name: str | None, allow_ex_strip: bool = False) -> tuple[str, str | None]:
    """Return `(canonical_key, audit_note_or_None)`.

    When `allow_ex_strip=True`, a leading `ex-` token (e.g. `ex-CYBERSHOKE` vs `CYBERSHOKE`)
    is stripped and recorded in the audit note so it can only join when opponent + kickoff agree.
    """
    tokens = norm_tokens(name)
    if not tokens:
        return "", None
    notes: list[str] = []
    while len(tokens) > 1 and tokens[0] in _PREFIX_TOKENS:
        tokens.pop(0)
    if allow_ex_strip and len(tokens) > 1 and tokens[0] == "ex":
        tokens.pop(0)
        notes.append(f"'{name}' matched via ex-org prefix normalisation ('ex-' stripped, verified by opponent and start time).")
    while len(tokens) > 1 and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    key = _NON_ALNUM.sub("", "".join(tokens))
    if key in ALIASES:
        target, note = ALIASES[key]
        notes.append(note)
        key = target
    return key, (" ".join(notes) if notes else None)


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_KALSHI_TICKER_RE = re.compile(r"^KXCS2GAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def kalshi_ticker_utc(event_id: str | None) -> str | None:
    """Parse Kalshi KXCS2GAME event ticker timestamp (EDT = UTC-4 in Oct 2026) to ISO UTC."""
    if not event_id:
        return None
    m = _KALSHI_TICKER_RE.match(str(event_id).strip().upper())
    if not m:
        return None
    try:
        dt_edt = datetime.strptime(
            f"20{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}",
            "%Y-%b-%d %H:%M",
        )
    except ValueError:
        return None
    # US Eastern Daylight Time (EDT) is UTC-4 through Nov 1, 2026.
    dt_utc = (dt_edt + timedelta(hours=4)).replace(tzinfo=timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_apart(iso_a: str | None, iso_b: str | None) -> float | None:
    da, db = parse_iso(iso_a), parse_iso(iso_b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds()) / 3600.0
