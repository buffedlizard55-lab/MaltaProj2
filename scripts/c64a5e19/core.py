"""EVERY-MATCH core (session c64a5e19) — pure functions, no network access.

Forked from the proven f7279a54 core (same odds maths, same Valve VRS model) with
fallback-only additions documented inline. The featured (market/model) maths is unchanged.

Everything that turns raw source payloads into numbers lives here so it can be unit-tested
against real captured payloads without touching the internet.

Rules this module enforces
--------------------------
* HotSpawn is used for fixture discovery ONLY. No HotSpawn crowd "picked %" value is read by any
  function in this module (``fixture_from_hotspawn`` deliberately drops those fields).
* A price is joined to a fixture only when BOTH team names match after the documented
  normalisation (or an explicit, published alias) and the source start time is inside the
  tolerance window. Nothing is matched on a prefix or a substring, so "B8" never matches
  "B8 Academy".
* A value that cannot be derived from a source is left as ``None`` and flagged — never filled.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone

ISO = "%Y-%m-%dT%H:%M:%SZ"

# ------------------------------------------------------------------------------------ time

def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime(ISO) if dt else None


def parse_ms(value) -> datetime | None:
    """HotSpawn sends epoch milliseconds as strings ("1792173600000")."""
    try:
        ms = int(str(value))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def parse_iso(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:  # a naive timestamp has no verifiable zone -> refuse it
        return None
    return dt.astimezone(timezone.utc)


def parse_any(value) -> datetime | None:
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.isdigit():
        return parse_any(int(value))
    return parse_iso(value)


def hours_apart(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# ------------------------------------------------------------------------------- team names
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Generic organisation words that sources add or drop ("Team Falcons", "FURIA Esports",
# "Aurora Gaming", "9z Team"). Only whole leading/trailing tokens are removed.
_PREFIX_TOKENS = {"team", "the"}
_SUFFIX_TOKENS = {"team", "esports", "esport", "gaming", "gg", "club"}

# Source spelling (after normalisation) -> HotSpawn spelling (after normalisation).
# Each entry is a published matching decision (shown on the Flagged page whenever it is used).
ALIASES: dict[str, tuple[str, str]] = {
    # key: (canonical, evidence note)
    "bb": ("betboom", "BetBoom Team is listed as 'BB Team' by some bookmakers; the alias is only "
                      "applied together with an agreeing opponent and start time."),
    "nip": ("ninjasinpyjamas", "NIP is the official abbreviation of Ninjas in Pyjamas."),
    "pvision": ("parivision", "PARIVISION is listed as 'PVISION' on some feeds."),
    "9zglobant": ("9z", "9z Team is sponsored as '9z Globant' on some feeds."),
    # --- c64a5e19 fallback-only aliases (used ONLY where no featured line exists; every use is flagged) ---
    "roundsgg": ("rounds", "RoundsGG (HotSpawn/Kalshi spelling) is ROUNDS in Valve's official VRS file "
                           "(standing 310, 548 pts, roster Kollo/Lapa/Monoxx/Tumppis/ykis) and 'Rounds' "
                           "on HLTV team 12457 (roundsgg). Suffix 'GG' is part of the HotSpawn label."),
    "eacopenhagen": ("eac", "EA Copenhagen / Esport Academy Copenhagen is abbreviated EAC on Liquipedia's "
                            "Elisa BreakOut Series #2 participants list and on HLTV team 13838, whose roster "
                            "(Fessor, n1Xen, anber, sSen, bekker) matches Valve VRS 'EAC' (1035 pts)."),
    "esportacademycopenhagen": ("eac", "See eacopenhagen alias evidence (Liquipedia Elisa BreakOut #2; HLTV team 13838)."),
}


def norm(name: str | None) -> str:
    """Case/accents/punctuation-insensitive key, with generic org words stripped."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    tokens = [t for t in re.split(r"[^a-z0-9.&]+", text) if t]
    while len(tokens) > 1 and tokens[0] in _PREFIX_TOKENS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    return _NON_ALNUM.sub("", "".join(tokens))


def canon(name: str | None) -> tuple[str, str | None]:
    """Return (canonical key, alias note or None)."""
    key = norm(name)
    if key in ALIASES:
        return ALIASES[key][0], ALIASES[key][1]
    return key, None


def same_team(a: str | None, b: str | None) -> tuple[bool, list[str]]:
    ka, na = canon(a)
    kb, nb = canon(b)
    notes = [n for n in (na, nb) if n]
    return bool(ka) and ka == kb, notes


# ------------------------------------------------------------------------------- odds maths

def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return 1.0 + p / 100.0
    if p <= -100:
        return 1.0 + 100.0 / abs(p)
    return None  # -100 < p < 100 is not a valid American price


def decimal_to_american(dec: float | None) -> int | None:
    if dec is None or dec <= 1.0:
        return None
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def no_vig(dec_a, dec_b) -> dict | None:
    """Proportional (multiplicative) removal of the bookmaker margin from a two-way price."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(da) or not math.isfinite(db) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:  # outside any plausible two-way book -> treat as bad data
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


def rederive_quote(quote: dict) -> dict | None:
    """Stored derived probabilities are not evidence. Recompute from the quoted raw prices."""
    try:
        raw_a, raw_b = float(quote["raw_a"]), float(quote["raw_b"])
    except (KeyError, ValueError, TypeError):
        return None
    if quote.get("raw_format") == "american":
        da, db = american_to_decimal(raw_a), american_to_decimal(raw_b)
    elif quote.get("raw_format") == "decimal":
        da, db = raw_a, raw_b
    elif quote.get("raw_format") == "yes mid ($)" and 0 < raw_a < 1 and 0 < raw_b < 1:
        da, db = 1 / raw_a, 1 / raw_b
    else:
        return None
    nv = no_vig(da, db)
    if not nv:
        return None
    return {**quote, "start_utc": None if quote.get("start_is_approx") else quote.get("start_utc"),
            "decimal_a": da, "decimal_b": db, "prob_a": nv["prob_a"],
            "overround": nv["overround"]}


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# --------------------------------------------------------------------- market consensus
# Weighting is a stated modelling choice (published on the method page), not a source value.
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "kalshi": 1.0}
KALSHI_MAX_SPREAD = 0.10   # a wider bid/ask on either side means "no usable price"


def consensus(entries: list[dict]) -> dict | None:
    """Weighted mean of per-source no-vig probabilities for team A."""
    usable = [e for e in entries if isinstance(e.get("prob_a"), float)]
    if not usable:
        return None
    wsum = sum(SOURCE_WEIGHTS.get(e["source_key"], 1.0) for e in usable)
    pa = sum(SOURCE_WEIGHTS.get(e["source_key"], 1.0) * e["prob_a"] for e in usable) / wsum
    lo = min(e["prob_a"] for e in usable)
    hi = max(e["prob_a"] for e in usable)
    return {"prob_a": pa, "prob_b": 1.0 - pa, "n_sources": len(usable),
            "sources": sorted({e["source_key"] for e in usable}),
            "spread_a": hi - lo if len(usable) > 1 else None}


# ---------------------------------------------------------------- Valve VRS rating model
# Valve's own model code (ValveSoftware/counter-strike_regional_standings, model/glicko.js):
#   "rank delta of 400 points = 90% chance of victory";  Q = ln(10)/400
#   g  = 1 / sqrt(1 + 3*Q^2*RD^2/pi^2);   ev = 1 / (1 + 10^(g*(r-ro)/-400))
# and model/fit.js evaluates expected win rates with a fixed RD of 75 (defaultGlickoParams.rd).
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
# logit(p) = C * delta  for Valve's expected-win formula
VALVE_C = VALVE_G * math.log(10) / 400.0


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    """P(team A beats team B) from Valve VRS points; k scales Valve's slope (k=1 -> Valve)."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)


def fit_calibration(pairs: list[dict]) -> dict:
    """Least-squares fit of logit(market) = k * C * delta through the origin.

    Each pair is one fixture (latest pre-lock observation) where both teams have a VRS rating and
    a market consensus existed. The README of Valve's repository states their curve is too steep
    ("underestimate win rates at the low end and overestimate at the high end"), so the slope is
    learned from observed bookmaker lines instead of being assumed.
    """
    xs = [VALVE_C * p["delta"] for p in pairs]
    ys = [logit(p["market_prob_a"]) for p in pairs]
    n = len(xs)
    out = {"n_pairs": n, "k": 1.0, "fitted": False, "k_raw": None, "mae_prob": None,
           "mae_prob_valve": None, "min_pairs": CAL_MIN_PAIRS, "bounds": list(CAL_K_BOUNDS)}
    sxx = sum(x * x for x in xs)
    if n >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        k = min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1])
        out.update({"k": k, "k_raw": k_raw, "fitted": True})
    if n:
        out["mae_prob"] = sum(abs(sigmoid(out["k"] * x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
        out["mae_prob_valve"] = sum(abs(sigmoid(x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
    return out


# ------------------------------------------------------------------------- our line blend

def market_weight(n_sources: int) -> float:
    """Share of the blend given to the market (stated modelling choice)."""
    return 0.85 if n_sources >= 2 else 0.75


def blend(market_prob_a: float | None, n_sources: int, model_prob_a: float | None) -> dict | None:
    if market_prob_a is None and model_prob_a is None:
        return None
    if market_prob_a is not None and model_prob_a is not None:
        w = market_weight(n_sources)
        pa = sigmoid(w * logit(market_prob_a) + (1 - w) * logit(model_prob_a))
        basis = "market+model"
    elif market_prob_a is not None:
        w, pa, basis = 1.0, market_prob_a, "market"
    else:
        w, pa, basis = 0.0, model_prob_a, "model"
    return {"prob_a": pa, "prob_b": 1.0 - pa, "basis": basis, "market_weight": w}


def confidence_label(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


# ----------------------------------------------------------------------------- HotSpawn

LOBBY_STATE_RE = re.compile(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)


def lobby_state(page_html: str) -> dict:
    """Extract the Angular transfer state embedded in the public lobby page."""
    import json
    m = LOBBY_STATE_RE.search(page_html or "")
    if not m:
        return {}
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return {}
    out = {"fixtures": None, "fixtures_url": None, "permalinks": {}, "week": None}
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        if url.endswith("/api/v1/fixtures") or (url.split("?")[0].endswith("/api/v1/fixtures")):
            if isinstance(body, list):
                out["fixtures"], out["fixtures_url"] = body, url
        elif "permalinks" in url and isinstance(body, dict):
            links = body.get("permalinks")
            if isinstance(links, dict):
                out["permalinks"] = {str(k): str(v) for k, v in links.items()
                                     if re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(v))}
        elif "week-prizes" in url and isinstance(body, dict):
            out["week"] = {k: body.get(k) for k in ("weekId", "sportAlias", "status", "weekStartUtc",
                                                    "weekEndUtc", "cutoffUtc")}
    return out


def fixture_from_hotspawn(f: dict) -> dict | None:
    """Normalise one HotSpawn fixture. Crowd pick percentages are intentionally NOT copied."""
    if not isinstance(f, dict) or str(f.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(f.get("scheduled_start_time")), parse_ms(f.get("lock_time"))
    a, b = f.get("participants0_name"), f.get("participants1_name")
    if not f.get("id") or not a or not b or start is None:
        return None
    return {
        "fixture_id": str(f["id"]),
        "competition": f.get("competition_name"),
        "tier": (str(f.get("tier") or "").upper() or None),
        "stage": f.get("stage"),
        "best_of": f.get("best_of"),
        "status": f.get("status"),
        "points": f.get("offered_points"),
        "start_utc": to_iso(start),
        "lock_utc": to_iso(lock),
        "team_a": str(a).strip(),
        "team_b": str(b).strip(),
        "winner": result_winner(f),
    }


def result_winner(f: dict) -> str | None:
    """'a' / 'b' when HotSpawn reports the fixture as ended with unequal scores, else None."""
    if str(f.get("status") or "") != "ended":
        return None
    try:
        s0, s1 = int(f.get("participants0_score")), int(f.get("participants1_score"))
    except (TypeError, ValueError):
        return None
    if s0 == s1:
        return None
    return "a" if s0 > s1 else "b"


# ------------------------------------------------------------------------------ joining
TIME_TOLERANCE_H = 5 / 60   # same pairing must start within this many hours of HotSpawn's time
TIME_WARN_H = 3.0         # larger differences are joined but flagged
TIME_REJECT_LOG_H = 72.0  # same pairing 14-72 h apart: not joined, but published as a rejected join


def match_quote(fixture: dict, quote: dict) -> dict | None:
    """Return join info if `quote` prices `fixture` (either orientation), else None."""
    a_a, notes1 = same_team(fixture["team_a"], quote["team_a"])
    b_b, notes2 = same_team(fixture["team_b"], quote["team_b"])
    a_b, notes3 = same_team(fixture["team_a"], quote["team_b"])
    b_a, notes4 = same_team(fixture["team_b"], quote["team_a"])
    if a_a and b_b:
        swapped, notes = False, notes1 + notes2
    elif a_b and b_a:
        swapped, notes = True, notes3 + notes4
    else:
        return None
    diff = hours_apart(parse_iso(fixture["start_utc"]), parse_iso(quote.get("start_utc")))
    if diff is None or quote.get("start_is_approx"):
        return {"rejected": True, "swapped": swapped, "alias_notes": notes,
                "start_diff_h": diff, "reason": "unverified_start_time"}
    if diff > TIME_TOLERANCE_H:
        if diff <= TIME_REJECT_LOG_H:
            return {"rejected": True, "swapped": swapped, "alias_notes": notes, "start_diff_h": diff}
        return None
    return {"swapped": swapped, "alias_notes": notes, "start_diff_h": diff}


def oriented_prob(quote: dict, swapped: bool) -> float | None:
    p = quote.get("prob_a")
    if p is None:
        return None
    return 1.0 - p if swapped else p
