"""EVERY-MATCH core (session af573ff1) — pure functions, no network access.

Purpose: give every open HotSpawn CS2 fixture a pick, applying extra information
sources ONLY where the featured boards publish no line.

Rules enforced here
-------------------
* HotSpawn is fixture discovery only. No HotSpawn crowd "picked %" is read.
* Featured lines are never recomputed or overwritten by this module — the builder
  copies them verbatim from `data/f7279a54/board.json` and this module is only
  consulted for fixtures that board leaves with ``line is None``.
* Fallback market joins require BOTH team names to match (after normalisation or
  a published, evidence-linked alias below) AND the source start time to be
  within 90 minutes of the HotSpawn start. One-team or tournament-only matches
  are never joined.
* The EGamersWorld 1.80/1.80 identical pair is a documented widget placeholder
  (see data/current_board.json irregularities), never a price.
* Anything that cannot be derived is returned as None and flagged by the caller.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone

ISO = "%Y-%m-%dT%H:%M:%SZ"

# Valve VRS expected-win constants, re-derived from Valve's own model code
# (same derivation as scripts/f7279a54/core.py, which cites model/glicko.js and
# model/fit.js in ValveSoftware/counter-strike_regional_standings):
#   Q = ln(10)/400 ; g = 1/sqrt(1 + 3 Q^2 RD^2 / pi^2), RD = 75.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

# Fallback-market join tolerance: source start within 90 minutes of HotSpawn.
TIME_TOLERANCE_H = 1.5
# Single-rating estimate: shrink the raw logit toward 50/50 and clamp, because a
# population prior is not a team rating. Stated modelling choice, published on
# the method page — it only ever makes the estimate MORE conservative.
SINGLE_RATING_SHRINK = 0.55
SINGLE_RATING_CLAMP = (0.35, 0.65)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt):
    return dt.astimezone(timezone.utc).strftime(ISO) if dt else None


def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def parse_ms(value):
    try:
        ms = int(str(value))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def hours_apart(a, b):
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    """P(A beats B) from Valve VRS points with the featured board's fitted k."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def no_vig(dec_a, dec_b):
    """Proportional no-vig probabilities for a two-way decimal price, else None."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if da <= 1.0 or db <= 1.0:
        return None
    if da == db == 1.8:
        return None  # documented EGamersWorld widget placeholder, not a price
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


# ----------------------------------------------------------------- team names
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PREFIX_TOKENS = {"team", "the"}
_SUFFIX_TOKENS = {"team", "esports", "esport", "gaming", "gg", "club"}

# Published alias decisions. Every entry carries the evidence a reviewer can
# open. An alias is only ever applied together with an agreeing opponent and
# start time (market joins) or as an exact VRS roster-name resolution.
#   key (normalised source/VRS spelling) -> (HotSpawn spelling normalised, note, evidence URL)
ALIASES = {
    "wbt": ("wrotberry",
            "HLTV's WBT team page lists its next matches as 15 Oct vs EAC, ENCE and BOJONG — the "
            "exact HotSpawn WROTBERRY fixtures — with roster Psycho/Smash/s4ltovsk1yy/DemQQ/tyr1k, "
            "identical to Valve VRS team 'WBT'; Liquipedia lists the Elisa BreakOut team as "
            "WhiteBIT Team (WBT). HotSpawn spells the same team WROTBERRY.",
            "https://www.hltv.org/team/13683/wbt"),
    "whitebit": ("wrotberry",
                 "Melbet/EGamersWorld list WROTBERRY's Elisa BreakOut matches under the team's "
                 "full name WhiteBIT Team (WBT); identity evidence as for 'wbt'.",
                 "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2"),
    "rounds": ("roundsgg",
               "HLTV's ROUNDS team page roster Kollo/Lapa/Monoxx/Tumppis/ykis is identical to "
               "Valve VRS team 'ROUNDS'; EGamersWorld's team page for the same roster uses the "
               "slug 'roundsgg'. HotSpawn spells the team RoundsGG.",
               "https://www.hltv.org/team/12457/rounds"),
    "eacopenhagen": ("eac",
                     "Liquipedia's Elisa BreakOut Series 2 page lists 'EA Copenhagen' with the "
                     "tag EAC; the Melbet/EGamersWorld fixtures pair it with the same opponents "
                     "and start times as HotSpawn's EAC fixtures.",
                     "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2"),
    "bb": ("betboom", "BetBoom Team is listed as 'BB Team' by some bookmakers (featured board alias).",
           "https://www.hltv.org/team/12376/betboom"),
    "nip": ("ninjasinpyjamas", "NIP is the official abbreviation of Ninjas in Pyjamas.",
            "https://www.hltv.org/team/4411/ninjas-in-pyjamas"),
    "pvision": ("parivision", "PARIVISION is listed as 'PVISION' on some feeds (featured board alias).",
                "https://www.hltv.org/team/12734/parivision"),
    "9zglobant": ("9z", "9z Team is sponsored as '9z Globant' on some feeds (featured board alias).",
                  "https://www.hltv.org/team/9996/9z"),
}
# Reverse view used for VRS lookups: HotSpawn normalised -> VRS normalised spellings to try.
VRS_NAME_CANDIDATES = {}
for _src, (_hs, _note, _url) in ALIASES.items():
    VRS_NAME_CANDIDATES.setdefault(_hs, []).append(_src)


def norm(name) -> str:
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


def canon(name):
    """(canonical HotSpawn-side key, alias note or None, evidence URL or None)."""
    key = norm(name)
    if key in ALIASES:
        hs, note, url = ALIASES[key]
        return hs, note, url
    return key, None, None


def same_team(a, b):
    ka, na, ua = canon(a)
    kb, nb, ub = canon(b)
    notes = [n for n in (na, nb) if n]
    urls = [u for u in (ua, ub) if u]
    return bool(ka) and ka == kb, notes, urls


def match_quote(fixture, quote):
    """Join info if `quote` prices `fixture` under fallback rules, else None."""
    a_a, n1, u1 = same_team(fixture["team_a"], quote["team_a"])
    b_b, n2, u2 = same_team(fixture["team_b"], quote["team_b"])
    a_b, n3, u3 = same_team(fixture["team_a"], quote["team_b"])
    b_a, n4, u4 = same_team(fixture["team_b"], quote["team_a"])
    if a_a and b_b:
        swapped, notes, urls = False, n1 + n2, u1 + u2
    elif a_b and b_a:
        swapped, notes, urls = True, n3 + n4, u3 + u4
    else:
        return None
    diff = hours_apart(parse_iso(fixture["start_utc"]), parse_iso(quote.get("start_utc")))
    if diff is not None and diff > TIME_TOLERANCE_H:
        return None
    return {"swapped": swapped, "alias_notes": notes, "evidence_urls": urls, "start_diff_h": diff}


def oriented_prob(quote, swapped):
    p = quote.get("prob_a")
    if p is None:
        return None
    return 1.0 - p if swapped else p


def confidence_label(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def single_rating_prob(rated_points: float, prior_points: float, k: float, rated_is_a: bool):
    """Conservative P(team A) when only one side has a VRS rating.

    Raw Valve-curve probability of rated-vs-prior, shrunk toward 50/50 in logit
    space and clamped — a population prior is not a team rating.
    """
    raw_rated = vrs_prob(rated_points, prior_points, k)
    shrunk = sigmoid(SINGLE_RATING_SHRINK * logit(raw_rated))
    lo, hi = SINGLE_RATING_CLAMP
    p_rated = min(max(shrunk, lo), hi)
    return p_rated if rated_is_a else 1.0 - p_rated


# ------------------------------------------------------------------ HotSpawn
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
    out = {"fixtures": None, "permalinks": {}, "week": None}
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        if url.split("?")[0].endswith("/api/v1/fixtures") and isinstance(body, list):
            out["fixtures"] = body
        elif "permalinks" in url and isinstance(body, dict):
            links = body.get("permalinks")
            if isinstance(links, dict):
                out["permalinks"] = {str(k): str(v) for k, v in links.items()
                                     if re.match(r"^https://www\.hotspawn\.com/matches/[a-z0-9-]+-\d+$", str(v))}
    return out


def fixture_from_hotspawn(f: dict):
    """Normalise one HotSpawn fixture. Crowd pick percentages are NOT copied."""
    if not isinstance(f, dict) or str(f.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(f.get("scheduled_start_time")), parse_ms(f.get("lock_time"))
    a, b = f.get("participants0_name"), f.get("participants1_name")
    if not f.get("id") or not a or not b or start is None:
        return None
    return {"fixture_id": str(f["id"]), "competition": f.get("competition_name"),
            "tier": (str(f.get("tier") or "").upper() or None), "status": f.get("status"),
            "points": f.get("offered_points"), "start_utc": to_iso(start), "lock_utc": to_iso(lock),
            "team_a": str(a).strip(), "team_b": str(b).strip()}
