"""T-FULLCOV core (session fe803b80) — pure functions only, no network access.

Purpose
-------
Turn raw source payloads into (a) a joined market probability, (b) an originated probability
that exists for *every* fixture, and (c) an explicitly labelled pick. Everything is deterministic
so the published board can be re-derived from the stored snapshot without touching the internet.

Rules enforced here
-------------------
* HotSpawn is fixture discovery **and** settlement-results only. Its crowd "picked %" is never
  read by any function in this module (``sources.FIXTURE_KEYS`` refuses those fields upstream).
* A price is joined to a fixture only when BOTH team names match after the documented
  normalisation, or a *published alias* matches and the pairing/time evidence agrees.
  No prefix or substring matching is ever used ("B8" can never match "B8 Academy").
* A number that cannot be derived from a source stays ``None`` and is flagged. It is never filled.

Independence note
-----------------
This module deliberately re-implements the documented normalisation/maths rules instead of
importing another session's file, so this session's tests cannot be broken by an edit in a
different session's scope. The formulas are the same published ones (see the URLs below); where
they are copied, the source of the formula is named in the comment.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

ISO = "%Y-%m-%dT%H:%M:%SZ"

# -------------------------------------------------------------------------------------- time


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
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:          # a naive timestamp has no verifiable zone -> refuse it
        return None
    return dt.astimezone(timezone.utc)


def parse_any(value) -> datetime | None:
    """Epoch milliseconds, epoch seconds, or an ISO date string -> UTC, else None.

    Bovada/Melbet publish start times as epoch milliseconds while their other fields are text, so a
    single entry point refuses anything whose zone cannot be established instead of guessing.
    """
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.strip().isdigit():
        return parse_any(int(value.strip()))
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


# Source spelling (normalised) -> HotSpawn spelling (normalised), with the evidence that
# authorises the equivalence. Every alias applied to a published row is also shown on
# board/flagged.html so a reviewer can check the evidence.
ALIASES: dict[str, dict] = {
    # HotSpawn lists the Ukrainian roster WROTBERRY; bo3.gg's own team record for the same
    # roster (id 22734) is name "WBT", acronym "WBT"; HLTV's team page for the same id-free
    # roster is titled WROTBERRY with the acronym WBT. The three fixtures below therefore
    # join on name+time once the alias is applied.
    "wrotberry": {
        "canonical": "wbt",
        "note": "HLTV team page 'WROTBERRY' carries the acronym WBT; bo3.gg team id 22734 "
                "(same roster: fl1peR, svemyy, aRTYSAN, tired73, lyoli) is named WBT.",
        "evidence": ["https://www.hltv.org/team/13683/wrotberry",
                     "https://bo3.gg/teams/wbt",
                     "https://api.bo3.gg/api/v1/teams/?filter%5Bteams.id%5D%5Beq%5D=22734"],
    },
    "bb": {"canonical": "betboom",
           "note": "BetBoom Team is listed as 'BB Team' by some bookmakers.",
           "evidence": ["https://bo3.gg/teams/betboom"]},
    "nip": {"canonical": "ninjasinpyjamas",
            "note": "NIP is the official abbreviation of Ninjas in Pyjamas.",
            "evidence": ["https://www.hltv.org/team/4411/ninjas-in-pyjamas"]},
    "pvision": {"canonical": "parivision",
                "note": "PARIVISION is listed as 'PVISION' on some feeds.",
                "evidence": ["https://bo3.gg/teams/parivision"]},
    "9zglobant": {"canonical": "9z",
                  "note": "9z Team is sponsored as '9z Globant' on some feeds.",
                  "evidence": ["https://bo3.gg/teams/9z"]},
    # HotSpawn lists the 17:00 CCT Europe 2026 Series #11 fixture as "FORZE Reload vs LFO 10".
    # bo3.gg's CCT Europe 2026 Series #11 (tournament 5625) lists the same 17:00 slot as
    # "Forze Reload vs Sokerorg", and Kalshi (a regulated exchange) prices the same pairing at the
    # same kick-off. bo3.gg has no team named "LFO 10" (its LFO teams are LFO, LFO 2/3/5/7/8/9), so
    # the two listings are treated as the same fixture under one published alias. Flagged for
    # review on the board: the alias is visible on the row and in the flagged table.
    "lfo10": {
        "canonical": "sokerorg",
        "note": "Same kick-off (2026-10-14T17:00Z) and same CCT Europe 2026 Series #11 slot as "
                "bo3.gg's 'Forze Reload vs Sokerorg' and Kalshi's Sokerorg vs FORZE Reload market; "
                "bo3.gg publishes no team called 'LFO 10'.",
        "evidence": ["https://bo3.gg/matches/forze-reload-vs-sokerorg-14-10-2026",
                     "https://bo3.gg/teams/sokerorg",
                     "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct141300skrforzer"],
    },
    # HotSpawn 'EAC' == bo3.gg/Thunderpick 'EAC' (Esport Academy Copenhagen) - same spelling,
    # no alias needed. Kept out of the table on purpose: no undocumented expansion is applied.
}


def canon(name: str | None) -> tuple[str, list[str], str | None]:
    """Return (canonical key, evidence URLs, alias note)."""
    key = norm(name)
    entry = ALIASES.get(key)
    if entry:
        return entry["canonical"], list(entry["evidence"]), entry["note"]
    return key, [], None


def same_team(a: str | None, b: str | None) -> tuple[bool, list[str], str | None]:
    ka, ea, na = canon(a)
    kb, eb, nb = canon(b)
    if not ka or ka != kb:
        return False, [], None
    notes = [n for n in (na, nb) if n]
    return True, sorted(set(ea + eb)), (" ".join(notes) if notes else None)


# ---------------------------------------------------------------------------------- odds maths

def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return 1.0 + p / 100.0
    if p <= -100:
        return 1.0 + 100.0 / abs(p)
    return None                      # -100 < p < 100 is not a valid American price


def decimal_to_american(dec) -> int | None:
    if dec is None or dec <= 1.0:
        return None
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def no_vig(dec_a, dec_b) -> dict | None:
    """Proportional (multiplicative) margin removal from a two-way price."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:     # outside any plausible two-way book -> treat as bad data
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


def logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------- market consensus
# Weighting is a stated modelling choice (published on board/method.html), not a source value.
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.5, "kalshi": 1.0, "melbet": 1.0, "thunderpick": 1.5,
                  "1xbet": 1.0, "polymarket": 1.0}
KALSHI_MAX_SPREAD = 0.10   # wider bid/ask on either side means "no usable price"


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
            "spread_a": (hi - lo) if len(usable) > 1 else None}


# ---------------------------------------------------------------------- Valve VRS rating model
# Valve's own model code (ValveSoftware/counter-strike_regional_standings, model/glicko.js):
#   "rank delta of 400 points = 90% chance of victory";  Q = ln(10)/400
#   g  = 1 / sqrt(1 + 3*Q^2*RD^2/pi^2);   ev = 1 / (1 + 10^(g*(r-ro)/-400))
# and model/fit.js evaluates expected win rates with a fixed RD of 75 (defaultGlickoParams.rd).
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    """P(team A beats team B) from Valve VRS points; k scales Valve's slope (k=1 -> Valve)."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


# Valve's own published model starts every roster at 400 points
# ("400 + ((Roster_Average - Min_Average) / (Max_Average - Min_Average)) * 1600" — see the
# per-team detail files in the official repository). A roster that is absent from the published
# table has therefore no more than that 400-point floor, which is the assumption the one-sided
# bound below makes explicit and labels.
VRS_FLOOR_POINTS = 400.0


def vrs_floor_prob(points_rated: float, floor_points: float = VRS_FLOOR_POINTS,
                   k: float = 1.0) -> float:
    """P(rated roster beats an unrated opponent) with the opponent placed on Valve's floor.

    This is a *bound under a stated assumption*, never a price: the unrated opponent is placed on
    the lowest rank value Valve's published model can award (400 points), so the number is the
    most favourable reading the official data supports for the rated side.
    """
    return sigmoid(k * VALVE_C * (float(points_rated) - float(floor_points)))


EX_PREFIX_RE = re.compile(r"^ex[-_ ]+", re.I)


def ex_prefix_candidates(name: str | None) -> list[str]:
    """Canonical keys to try when a source lists a team under a former name ("ex-...").

    Only the prefix is removed; the rest of the name still has to match an official row exactly.
    The result is a *candidate*, never an automatic join: a candidate that is not confirmed by a
    published source is published as an explicit, flagged assumption.
    """
    if not name:
        return []
    stripped = EX_PREFIX_RE.sub("", str(name)).strip()
    if not stripped or stripped.casefold() == str(name).strip().casefold():
        return []
    key, _, _ = canon(stripped)
    return [key] if key else []


# Model bases and what they mean for a published number. A "bound" depends on a stated assumption
# (an unrated opponent placed on Valve's published floor, or an unconfirmed former-name alias);
# an "origin" is a line derived from published ratings or published results with a documented
# formula. Both are published on the unresolved page next to the number they produce.
BOUND_BASES = ("vrs_floor_bound", "vrs_alias_candidate_bound", "vrs_alias_candidate")
ORIGIN_BASES = ("valve_vrs", "originated_elo", "originated_rank", "originated_hltv_rank")

CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)


def fit_calibration(pairs: list[dict]) -> dict:
    """Least-squares fit of logit(market) = k * C * delta through the origin.

    Each pair is one fixture where both teams have a VRS rating and an external market consensus
    exists. Valve's own README states the published curve is too steep at both ends, so the slope
    is learned from observed bookmaker lines instead of being assumed.
    """
    xs = [VALVE_C * p["delta"] for p in pairs]
    ys = [logit(p["market_prob_a"]) for p in pairs]
    n = len(xs)
    out = {"n_pairs": n, "k": 1.0, "fitted": False, "k_raw": None, "mae_prob": None,
           "mae_prob_valve": None, "min_pairs": CAL_MIN_PAIRS, "bounds": list(CAL_K_BOUNDS)}
    sxx = sum(x * x for x in xs)
    if n >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        out["k_raw"] = k_raw
        out["k"] = min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1])
        out["fitted"] = True
    if n:
        out["mae_prob"] = sum(abs(sigmoid(out["k"] * x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
        out["mae_prob_valve"] = sum(abs(sigmoid(x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
    return out


# ------------------------------------------------------------------- our own Elo (last resort)
ELO_BASE = 1500.0
ELO_K = 20.0
ELO_SCALE = 400.0


def elo_expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / ELO_SCALE))


def elo_run(matches: list[dict], seed: dict[str, float] | None = None,
            k: float = ELO_K, passes: int = 8) -> dict[str, float]:
    """Plain Elo over an externally sourced result list.

    ``matches`` items: {"key_a","key_b","winner": "a"|"b", "start_utc"}. Seeds (when a team has an
    official VRS rating, its rating is mapped onto the Elo scale) are re-applied at the start of
    every pass so that seeded teams stay anchored to the official rating.
    """
    seed = seed or {}
    ratings: dict[str, float] = dict(seed)
    ordered = sorted(matches, key=lambda m: m.get("start_utc") or "")
    for _ in range(passes):
        for key in ratings:
            if key in seed:
                ratings[key] = seed[key]
        for m in ordered:
            a, b = m["key_a"], m["key_b"]
            if not a or not b or a == b:
                continue
            ra = ratings.setdefault(a, ELO_BASE)
            rb = ratings.setdefault(b, ELO_BASE)
            ea = elo_expected(ra, rb)
            sa = 1.0 if m["winner"] == "a" else 0.0
            ratings[a] = ra + k * (sa - ea)
            ratings[b] = rb + k * ((1.0 - sa) - (1.0 - ea))
    return ratings


# ------------------------------------------------------------------------------ our line blend

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


# ------------------------------------------------------------------------------------ HotSpawn
LOBBY_STATE_RE = re.compile(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)

# Fields copied out of the public fixture response. The crowd pick fields are refused by name so
# that a future HotSpawn field rename cannot silently reintroduce them as an input.
FIXTURE_KEYS = ("id", "sport_alias", "competition_name", "tier", "stage", "best_of", "status",
                "offered_points", "scheduled_start_time", "lock_time", "participants0_name",
                "participants1_name", "participants0_score", "participants1_score")
CROWD_PICK_RE = re.compile(r"pick|picked|percent|crowd", re.I)


def lobby_state(page_html: str) -> dict:
    """Extract the Angular transfer state embedded in the public lobby page."""
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
        if url.split("?")[0].endswith("/api/v1/fixtures"):
            if isinstance(body, list):
                out["fixtures"], out["fixtures_url"] = body, url
        elif "permalinks" in url and isinstance(body, dict):
            links = body.get("permalinks")
            if isinstance(links, dict):
                out["permalinks"] = {
                    str(k): str(v) for k, v in links.items()
                    if re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(v))}
        elif "week-prizes" in url and isinstance(body, dict):
            out["week"] = {k: body.get(k) for k in ("weekId", "sportAlias", "status",
                                                    "weekStartUtc", "weekEndUtc", "cutoffUtc")}
    return out


def fixture_from_hotspawn(f: dict) -> dict | None:
    """Normalise one HotSpawn fixture. Crowd pick percentages are intentionally NOT copied."""
    if not isinstance(f, dict) or str(f.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(f.get("scheduled_start_time")), parse_ms(f.get("lock_time"))
    a, b = f.get("participants0_name"), f.get("participants1_name")
    if not f.get("id") or not a or not b or start is None:
        return None
    clean = {k: f.get(k) for k in FIXTURE_KEYS}
    if any(CROWD_PICK_RE.search(k) for k in clean):
        raise AssertionError("a crowd-pick field reached the fixture parser")
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


# ------------------------------------------------------------------------------------- joining
TIME_TOLERANCE_H = 14.0    # the same pairing must start within this many hours
TIME_EXACT_H = 0.25        # "same start time" for the tournament-triangulated alias route


def match_quote(fixture: dict, quote: dict) -> dict | None:
    """Join info if ``quote`` prices ``fixture`` (either orientation), else None."""
    aa, e1, n1 = same_team(fixture["team_a"], quote["team_a"])
    bb, e2, n2 = same_team(fixture["team_b"], quote["team_b"])
    ab, e3, n3 = same_team(fixture["team_a"], quote["team_b"])
    ba, e4, n4 = same_team(fixture["team_b"], quote["team_a"])
    if aa and bb:
        swapped, notes, evidence = False, [n for n in (n1, n2) if n], sorted(set(e1 + e2))
    elif ab and ba:
        swapped, notes, evidence = True, [n for n in (n3, n4) if n], sorted(set(e3 + e4))
    else:
        return None
    diff = hours_apart(parse_iso(fixture["start_utc"]), parse_iso(quote.get("start_utc")))
    if diff is not None and diff > TIME_TOLERANCE_H:
        return None
    return {"swapped": swapped, "alias_notes": notes, "alias_evidence": evidence,
            "start_diff_h": diff}


def oriented_prob(quote: dict, swapped: bool) -> float | None:
    """The quote's probability re-oriented to the fixture's team_a/team_b order."""
    p = quote.get("prob_a")
    if p is None:
        return None
    return 1.0 - float(p) if swapped else float(p)


def triangulation_key(start_utc_a, start_utc_b, tolerance_h: float = TIME_EXACT_H) -> bool:
    """True when two fixtures start at the same moment (used for alias triangulation)."""
    diff = hours_apart(parse_iso(start_utc_a), parse_iso(start_utc_b))
    return diff is not None and diff <= tolerance_h


def close_rows(fixtures: list[dict], now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Split into still-open and closed rows using the published lock time."""
    now = now or now_utc()
    open_rows, closed = [], []
    for fx in fixtures:
        lock = parse_iso(fx.get("lock_utc"))
        if str(fx.get("status") or "") in ("ended", "cancelled", "canceled", "forfeited"):
            closed.append(fx)
        elif lock is not None and lock <= now:
            closed.append(fx)
        else:
            open_rows.append(fx)
    return open_rows, closed


def week_window(start_iso: str | None, days: int = 7) -> tuple[datetime | None, datetime | None]:
    start = parse_iso(start_iso)
    if start is None:
        return None, None
    return start, start + timedelta(days=days)
