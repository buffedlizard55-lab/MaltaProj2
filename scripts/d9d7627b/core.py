"""Core pure functions for the HotSpawn CS2 every-match picks board (session d9d7627b).

Everything that turns raw source payloads into numbers lives here so it can be unit-tested
offline against recorded payloads. No network access in this module.

Rules enforced here
-------------------
* HotSpawn is used for fixture discovery ONLY. HotSpawn crowd "picked %" values are never
  read, copied, or turned into a probability (``fixture_from_hotspawn`` drops them).
* A bookmaker/exchange price is joined to a fixture only when BOTH team names match after
  the documented normalisation (exact canonical equality, an explicit published alias, or
  an exact same-token reorder such as "Apogee Betclic" / "Betclic Apogee") AND the source
  start time agrees with HotSpawn within ``JOIN_TOLERANCE_H``. Near misses are returned as
  rejected joins so they can be published for review — never silently used.
* A value that cannot be derived from a source stays ``None`` and is flagged downstream.
  Model probabilities are labelled estimates, never presented as bookmaker prices.
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
    """HotSpawn sends epoch milliseconds as strings (e.g. "1792173600000")."""
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
    """Epoch seconds / epoch milliseconds / ISO-8601 with offset. Anything else -> None."""
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

# Source spelling (after normalisation) -> canonical spelling (after normalisation).
# Each entry is a published matching decision, shown on the Flagged page whenever used.
# Adopted from session f7279a54's published alias table (same evidence notes).
ALIASES: dict[str, tuple[str, str]] = {
    "bb": ("betboom", "BetBoom Team is listed as 'BB Team' by some bookmakers; the alias is "
                      "only applied together with an agreeing opponent and start time."),
    "nip": ("ninjasinpyjamas", "NIP is the official abbreviation of Ninjas in Pyjamas."),
    "pvision": ("parivision", "PARIVISION is listed as 'PVISION' on some feeds."),
    "9zglobant": ("9z", "9z Team is sponsored as '9z Globant' on some feeds."),
}


def _tokens(name: str | None) -> list[str]:
    if not name:
        return []
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    tokens = [t for t in re.split(r"[^a-z0-9.&]+", text) if t]
    while len(tokens) > 1 and tokens[0] in _PREFIX_TOKENS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    return tokens


def norm(name: str | None) -> str:
    """Case/accents/punctuation-insensitive key, with generic org words stripped."""
    return _NON_ALNUM.sub("", "".join(_tokens(name)))


def canon(name: str | None) -> tuple[str, str | None]:
    """Return (canonical key, alias note or None)."""
    key = norm(name)
    if key in ALIASES:
        return ALIASES[key][0], ALIASES[key][1]
    return key, None


def token_key(name: str | None) -> str:
    """Order-insensitive exact token-multiset key ("Apogee Betclic" == "Betclic Apogee")."""
    toks = [_NON_ALNUM.sub("", t) for t in _tokens(name)]
    toks = [ALIASES.get(t, (t,))[0] if t in ALIASES else t for t in toks if t]
    return " ".join(sorted(toks))


def same_team(a: str | None, b: str | None) -> tuple[bool, list[str]]:
    """Strict team-name equality. Returns (matched, evidence notes).

    Match modes, in order: identical canonical key; otherwise identical sorted-token key
    (exact same words, different order — flagged as a reorder join). Prefix/substring or
    fuzzy matches are never made ("WBT" does not match "WROTBERRY", "B8" != "B8 Academy").
    """
    ka, na = canon(a)
    kb, nb = canon(b)
    notes = [n for n in (na, nb) if n]
    if ka and ka == kb:
        return True, notes
    ta, tb = token_key(a), token_key(b)
    if ta and ta == tb and len(ta.split()) > 1:
        return True, notes + [f"name word-order variant joined exactly: '{a}' / '{b}'"]
    return False, notes


# ----------------------------------------------------------------------------------- odds

def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0 or not math.isfinite(p):
        return None
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / abs(p))


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
    if not 0.95 <= book <= 1.30:  # outside any plausible two-way book -> bad data
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


def rederive_quote(quote: dict) -> dict | None:
    """Recompute a quote's fair probability from its stored raw prices (never trust stored)."""
    try:
        raw_a, raw_b = float(quote["raw_a"]), float(quote["raw_b"])
    except (KeyError, ValueError, TypeError):
        return None
    if quote.get("raw_format") == "american":
        da, db = american_to_decimal(raw_a), american_to_decimal(raw_b)
    elif quote.get("raw_format") == "decimal":
        da, db = raw_a, raw_b
    elif quote.get("raw_format") in ("yes mid ($)", "probability") and 0 < raw_a < 1 and 0 < raw_b < 1:
        da, db = 1.0 / raw_a, 1.0 / raw_b
    else:
        return None
    nv = no_vig(da, db)
    if not nv:
        return None
    return {**quote,
            "start_utc": None if quote.get("start_is_approx") else quote.get("start_utc"),
            "decimal_a": da, "decimal_b": db,
            "prob_a": nv["prob_a"], "overround": nv["overround"]}


def fair_decimal(prob: float | None) -> float | None:
    if prob is None or not 0.0 < prob < 1.0:
        return None
    return 1.0 / prob


def median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if isinstance(v, float))
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def consensus(entries: list[dict]) -> dict | None:
    """Market consensus = median of per-source no-vig probabilities for team A.

    `entries` must already be oriented to the fixture (prob_a = P(fixture team_a wins)).
    The median is published because any reader can re-derive it from the listed sources.
    """
    usable = [e for e in entries if isinstance(e.get("prob_a"), float)]
    if not usable:
        return None
    pa = median([e["prob_a"] for e in usable])
    lo = min(e["prob_a"] for e in usable)
    hi = max(e["prob_a"] for e in usable)
    return {"prob_a": pa, "prob_b": 1.0 - pa,
            "n_sources": len({e["source_key"] for e in usable}),
            "sources": sorted({e["source_key"] for e in usable}),
            "spread_a": (hi - lo) if len(usable) > 1 else None}


# -------------------------------------------------------------- Valve VRS originated line
# Valve's published model (ValveSoftware/counter-strike_regional_standings, model/glicko.js):
# a 400-point rank delta = 90% expected win rate at fixed RD 75 (model/fit.js default),
#   Q = ln(10)/400 ; g = 1/sqrt(1 + 3 Q^2 RD^2 / pi^2) ; E = 1/(1 + 10^(-g*delta/400))
# so logit(E) = C * delta with C = g * ln(10) / 400. Valve's own README warns the curve is
# too steep, so the slope multiplier k is FITTED to observed bookmaker consensus lines
# (least squares through the origin on stored calibration pairs) instead of assumed.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

MODEL_PROB_MIN = 0.03   # originated lines are capped so a rating gap is never shown as
MODEL_PROB_MAX = 0.97   # near-certainty; market lines are published uncapped.


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    """P(team A beats team B) from Valve VRS points under the fitted slope k."""
    p = sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))
    return min(max(p, MODEL_PROB_MIN), MODEL_PROB_MAX)


CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)


def fit_calibration(pairs: list[dict]) -> dict:
    """Least-squares fit of logit(market_prob_a) = k * C * (points_a - points_b)."""
    xs = [VALVE_C * p["delta"] for p in pairs]
    ys = [logit(p["market_prob_a"]) for p in pairs]
    n = len(xs)
    out = {"n_pairs": n, "k": None, "k_raw": None, "fitted": False,
           "mae_prob": None, "mae_prob_valve_k1": None, "fav_agree": None,
           "min_pairs": CAL_MIN_PAIRS, "bounds": list(CAL_K_BOUNDS)}
    sxx = sum(x * x for x in xs)
    if n >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        out["k_raw"] = k_raw
        out["k"] = min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1])
        out["fitted"] = True
    if n and out["k"] is not None:
        out["mae_prob"] = sum(abs(sigmoid(out["k"] * x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
        out["mae_prob_valve_k1"] = sum(abs(sigmoid(x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
        out["fav_agree"] = sum(
            1 for x, y in zip(xs, ys) if (x > 0) == (y > 0)) / n
    return out


def confidence_label(p_pick: float | None) -> str | None:
    if p_pick is None:
        return None
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
    """Extract fixtures/permalinks/week from the lobby page's Angular transfer state.

    The server-rendered page embeds the exact JSON responses its own UI consumed
    (``/api/v1/fixtures`` body and a permalinks map). Returns {} when absent so the
    caller can keep the previous inventory instead of publishing an empty board.
    """
    import json as _json
    m = LOBBY_STATE_RE.search(page_html or "")
    if not m:
        return {}
    try:
        entries = _json.loads(m.group(1))
    except ValueError:
        return {}
    fixtures, permalinks, week = None, {}, None
    for value in entries.values() if isinstance(entries, dict) else []:
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        if url.rstrip("/").endswith("/api/v1/fixtures") and isinstance(body, list):
            fixtures = body
        if isinstance(body, dict):
            if isinstance(body.get("permalinks"), dict):
                permalinks = body["permalinks"]
            if body.get("weekId") is not None or "weekStartUtc" in body:
                week = body
            inner = body.get("week")
            if isinstance(inner, dict):
                week = inner
    return {"fixtures": fixtures or [], "permalinks": permalinks, "week": week}


def result_winner(f: dict) -> str | None:
    """'a' / 'b' when HotSpawn reports the fixture ended with unequal scores, else None."""
    if str(f.get("status") or "") != "ended":
        return None
    try:
        s0, s1 = int(f.get("participants0_score")), int(f.get("participants1_score"))
    except (TypeError, ValueError):
        return None
    if s0 == s1:
        return None
    return "a" if s0 > s1 else "b"


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


# ------------------------------------------------------------------------------ joining
JOIN_TOLERANCE_H = 0.5      # start times must agree within 30 minutes to join a price
JOIN_WARN_H = 5.0 / 60.0    # joins looser than 5 minutes are flagged on the row
REJECT_LOG_H = 72.0         # name-matching quotes within 72h are published as rejected joins


def match_quote(fixture: dict, quote: dict) -> dict | None:
    """Return join info if `quote` prices `fixture` (either orientation), else None.

    A returned dict with ``rejected: True`` means the team names matched but the price must
    NOT be used (unverified or disagreeing start time) — it is published as evidence.
    """
    a_a, n1 = same_team(fixture["team_a"], quote["team_a"])
    b_b, n2 = same_team(fixture["team_b"], quote["team_b"])
    if a_a and b_b:
        swapped, notes = False, n1 + n2
    else:
        a_b, n3 = same_team(fixture["team_a"], quote["team_b"])
        b_a, n4 = same_team(fixture["team_b"], quote["team_a"])
        if not (a_b and b_a):
            return None
        swapped, notes = True, n3 + n4
    diff = hours_apart(parse_iso(fixture["start_utc"]), parse_iso(quote.get("start_utc")))
    if diff is None or quote.get("start_is_approx"):
        return {"rejected": True, "swapped": swapped, "alias_notes": notes,
                "start_diff_h": diff,
                "reason": "source publishes no verified start time for this event"}
    if diff > JOIN_TOLERANCE_H:
        if diff <= REJECT_LOG_H:
            return {"rejected": True, "swapped": swapped, "alias_notes": notes,
                    "start_diff_h": diff,
                    "reason": f"source start time differs from HotSpawn by {diff:.2f}h "
                              f"(join limit {JOIN_TOLERANCE_H:.2f}h)"}
        return None
    return {"swapped": swapped, "alias_notes": notes, "start_diff_h": diff,
            "loose_time": diff > JOIN_WARN_H}


def oriented_prob(quote: dict, swapped: bool) -> float | None:
    p = quote.get("prob_a")
    if p is None:
        return None
    return 1.0 - p if swapped else p
