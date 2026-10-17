"""c32f1b93 board core — independent re-derivation of every pick.

Session c32f1b93's board is originated from retained primary evidence only:
  * data/c32f1b93/research.json        - this session's hand-verified research ledger
  * data/c32f1b93/vrs_global_2026_10_05.md - Valve's official VRS global ladder (retained copy)
  * data/c32f1b93/crowd_context.json   - HotSpawn pick'em crowd shares (CONTEXT ONLY, never a price)
  * data/fe803b80/snapshot.json        - retained 2026-10-17T00:22Z capture: HotSpawn fixture
                                         inventory, 93 external bookmaker/exchange quotes,
                                         bo3.gg team map and bo3.gg match history
No network access is used at build time; every input file is retained in the repo so the
board is re-derivable byte-for-byte.

Published rules (also shown on audits/c32f1b93/method.html):
  1. A probability is published only when it can be derived from a retained source.
     Otherwise the cell stays BLANK and the fixture goes to the unresolved ledger.
  2. Market consensus = MEDIAN of the per-source no-vig probabilities (our rule; robust
     to a single outlier book). Prior sessions used a source-weighted mean; we publish
     the median and disclose the difference.
  3. Valve VRS model = Valve's own documented Glicko expected-score formula with the
     repo's default RD of 75, slope k fitted by least squares through the origin against
     the joined market lines (our fit; the fitted value is published with the board).
  4. Elo (last resort) = plain Elo over the retained bo3.gg history (950 matches),
     teams seeded at their Valve VRS points, k=20, 8 chronological passes, seeds
     re-anchored every pass. Parameters are the published ones from session fe803b80;
     the computation is re-run here from the retained raw history.
  5. Published line = market median when >=1 usable price exists; else the model; else
     BLANK. When both exist the line is 0.85 market / 0.15 model (disclosed blend weight,
     kept identical to prior boards so the boards stay comparable).
  6. HotSpawn crowd "picked %" is sentiment, never a price. It is displayed as context
     and used only for the contrarian-divergence screen, never as a probability input.
  7. Untrained seed prices (exact 1.80/1.80 placeholders with zero vote count, $0-volume
     Polymarket seeds, map submarkets with no volume) are rejected, not averaged in.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import unicodedata
from datetime import datetime, timezone

# --------------------------------------------------------------------------- constants
SESSION = "c32f1b93"
BLEND_MARKET_WEIGHT = 0.85          # published blend: 85% market / 15% model
KALSHI_MAX_SPREAD = 0.10            # regulated exchange: reject wide bid/ask seeds
EGW_PLACEHOLDER = (1.80, 1.80)      # egamersworld untrained placeholder price
FIT_BOUNDS = (0.10, 1.50)           # our stability band for the fitted VRS slope
FIT_MIN_PAIRS = 6

# Valve's own model code (ValveSoftware/counter-strike_regional_standings, model/glicko.js
# and model/fit.js): "rank delta of 400 points = 90% chance of victory", Q = ln(10)/400,
# g = 1/sqrt(1 + 3*Q^2*RD^2/pi^2), ev = 1/(1 + 10^(g*(r-ro)/-400)); fit.js evaluates
# expected win rates with the default RD of 75.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

# Elo parameters (published by session fe803b80, re-run here on retained raw history)
ELO_BASE = 1500.0
ELO_K = 20.0
ELO_PASSES = 8

CONFIDENCE_BANDS = (
    (0.65, "Strong"),
    (0.60, "Solid"),
    (0.55, "Lean"),
    (0.50, "Toss-up"),
)

# --------------------------------------------------------------------------- names
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PREFIX_TOKENS = {"team", "the"}
_SUFFIX_TOKENS = {"team", "esports", "esport", "gaming", "gg", "club"}


def norm(name: str | None) -> str:
    """Case/accent/punctuation-insensitive key with generic org words stripped."""
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


# Source spelling (normalised) -> HotSpawn spelling (normalised), with evidence.
# Inherited from the fe803b80 board where the equivalence was first documented; the
# WROTBERRY entry is re-verified this session against HLTV team 13683 (see research.json).
ALIASES: dict[str, dict] = {
    "wrotberry": {
        "canonical": "wbt",
        "note": "HotSpawn lists the Ukrainian roster as WROTBERRY; Valve's official ladder "
                "carries the same roster (DemQQ, Psycho, s4ltovsk1yy, Smash, tyr1k) as WBT, "
                "and HLTV team 13683 (page title now WBT, formerly WROTBERRY) lists that "
                "exact five plus the Oct-17 HAVU and Oct-19 Nexus fixtures that match "
                "HotSpawn's WROTBERRY fixtures on opponent and date.",
        "evidence": ["https://www.hltv.org/team/13683/wbt",
                     "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026/standards_global_2026_10_05.md"],
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
    "apogeebetclic": {"canonical": "betclic",
                      "note": "HotSpawn lists the Portuguese roster with its sponsor "
                              "('Apogee Betclic'); Valve's ladder and HLTV carry it as "
                              "Betclic. Same five (Demho, ex1st, Prism, Qlocuu, ultimate).",
                      "evidence": ["https://www.hltv.org/team/13127/betclic",
                                   "https://polymarket.com/esports/cs2/pgl/cs2-bca-nem-2026-10-17"]},
    "lfo10": {
        "canonical": "sokerorg",
        "note": "HotSpawn lists the Oct-17 CCT Europe 2026 Series #11 fixture as "
                "'Lavked vs LFO 10'; bo3.gg's own tournament page for the same event lists "
                "the same round-3 slot as 'Lavked vs Sökerorg', and bo3.gg publishes no "
                "team called 'LFO 10' (its LFO teams are LFO, LFO 2/3/5/7/8/9). Kalshi "
                "priced the same pairing at the same kick-off under the Sokerorg spelling.",
        "evidence": ["https://bo3.gg/matches/lavked-vs-sokerorg-17-10-2026",
                     "https://bo3.gg/tournaments/cct-europe-2026-series-11",
                     "https://bo3.gg/teams/sokerorg"]},
}


def canon(name: str | None) -> tuple[str, list[str], str | None]:
    """Normalise a source team name -> (canonical key, aliases applied, evidence note)."""
    key = norm(name)
    applied: list[str] = []
    note: str | None = None
    if key in ALIASES:
        entry = ALIASES[key]
        applied.append(f"{key}->{entry['canonical']}")
        note = entry["note"]
        key = entry["canonical"]
    return key, applied, note


# --------------------------------------------------------------------------- math helpers
def sigmoid(x: float) -> float:
    """Natural logistic (identical convention to session fe803b80's core)."""
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    return math.log(p / (1.0 - p))


def devig(decimal_a: float, decimal_b: float) -> tuple[float, float]:
    """No-vig probabilities from a two-sided decimal price pair."""
    ia, ib = 1.0 / decimal_a, 1.0 / decimal_b
    total = ia + ib
    return ia / total, ib / total


# --------------------------------------------------------------------------- Valve VRS ladder
def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    """P(A beats B) from Valve VRS points; k scales Valve's slope (k=1 -> Valve's own curve)."""
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def fit_slope(pairs: list[dict]) -> dict:
    """Least-squares fit of logit(market) = k * C * delta through the origin (our fit).

    Each pair: {"delta": vrs_points_a - vrs_points_b, "market_prob_a": p}. Valve's README
    states the published curve is too steep at both ends, so the slope is learned from
    observed bookmaker lines instead of assuming k=1. Raw fit is published; the stability
    band FIT_BOUNDS is applied only if the raw fit lands outside it (flagged when used).
    """
    xs = [VALVE_C * p["delta"] for p in pairs]
    ys = [logit(p["market_prob_a"]) for p in pairs]
    n = len(xs)
    out = {"n_pairs": n, "k_raw": None, "k": 1.0, "clamped": False,
           "bounds": list(FIT_BOUNDS), "min_pairs": FIT_MIN_PAIRS, "mae_prob": None}
    if n >= FIT_MIN_PAIRS:
        sxx = sum(x * x for x in xs)
        if sxx > 0:
            k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
            out["k_raw"] = k_raw
            k = k_raw
            if not (FIT_BOUNDS[0] <= k <= FIT_BOUNDS[1]):
                k = min(max(k, FIT_BOUNDS[0]), FIT_BOUNDS[1])
                out["clamped"] = True
            out["k"] = k
            out["mae_prob"] = sum(abs(sigmoid(k * x) - sigmoid(y)) for x, y in zip(xs, ys)) / n
    return out


# --------------------------------------------------------------------------- Elo (last resort)
def elo_expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def elo_run(matches: list[dict], seed: dict[str, float] | None = None,
            k: float = ELO_K, passes: int = ELO_PASSES) -> dict[str, float]:
    """Plain Elo over the retained bo3.gg history.

    Matches: {"key_a", "key_b", "winner": "a"|"b", "start_utc"}. Teams holding a Valve
    VRS rating are seeded at their VRS points and re-anchored at the start of every pass
    so rated teams stay pinned to the official ladder.
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


# --------------------------------------------------------------------------- VRS file parsing
_VRS_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*\[details\]\(([^)]+)\)")


def parse_vrs_file(path: str) -> dict:
    """Parse the retained Valve VRS global ladder markdown.

    Returns {"generated": str, "teams": {normalised_name: {points, standing, roster,
    region_rank, details_url, raw_name}}} keeping EVERY row, including duplicate team
    names (the file carries multiple rosters under one name; callers disambiguate).
    """
    teams: dict[str, list[dict]] = {}
    generated = ""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                generated = line.strip().lstrip("# ").strip()
                continue
            m = _VRS_ROW.match(line)
            if not m:
                continue
            standing, points, name, roster, details = m.groups()
            entry = {
                "standing": int(standing),
                "points": float(points),
                "raw_name": name.strip(),
                "roster": [p.strip() for p in roster.split(",")],
                "details_url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/" + details.split("/")[-1],
            }
            key, _, _ = canon(name)
            teams.setdefault(key, []).append(entry)
    return {"generated": generated, "teams": teams}


def vrs_join(vrs: dict, key: str, lineup: list[str] | None = None) -> dict | None:
    """Join a canonical team key to the Valve ladder, disambiguating duplicate rows.

    Where the ladder carries several rows under one name (renamed/roster-split teams),
    the row is chosen by (1) roster overlap with the fixture's verified lineup when a
    lineup is known, then (2) most recent activity documented on the row. The chosen row,
    the rejected rows and the rule are all returned so the join is auditable.
    """
    rows = vrs["teams"].get(key)
    if not rows:
        return None
    if len(rows) == 1:
        row = rows[0]
        return {**row, "vrs_name": row["raw_name"], "ambiguous": False,
                "rejected_rows": [], "join_rule": "unique name match"}
    best, best_score = None, -1
    for row in rows:
        score = len(set(p.lower() for p in row["roster"]) & set(p.lower() for p in (lineup or [])))
        if score > best_score:
            best, best_score = row, score
    rejected = [r for r in rows if r is not best]
    rule = (f"duplicate name in Valve file; chose row by max roster overlap with the "
            f"verified fixture lineup ({best_score}/5)") if lineup else \
           "duplicate name in Valve file; chose row by standing (most recent active roster)"
    if lineup is None:
        best = max(rows, key=lambda r: r["standing"])
        rejected = [r for r in rows if r is not best]
    return {**best, "vrs_name": best["raw_name"], "ambiguous": True,
            "rejected_rows": rejected, "join_rule": rule}
