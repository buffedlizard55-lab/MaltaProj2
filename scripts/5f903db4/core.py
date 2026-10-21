#!/usr/bin/env python3
"""Shared helpers for the `5f903db4` every-match pick pipeline.

No network access, no randomness, no inferred values.  Every function here either returns a
number that can be re-derived from a published source, or returns ``None`` so the caller can
render an explicit blank / "unresolved" row.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "5f903db4"
SITE = ROOT / "everypick"

# ----------------------------------------------------------------------------------------------
# Source URLs (all read-only, all public)
# ----------------------------------------------------------------------------------------------
LOBBY_URL = "https://play.hotspawn.com/lobby"
HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
KALSHI_EVENTS = ("https://api.elections.kalshi.com/trade-api/v2/events"
                 "?series_ticker=KXCS2GAME&status=open&limit=200&with_nested_markets=false")
KALSHI_MARKETS = "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={event}"
MELBET_FEED = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip"
               "?sports=40&count=1000&lng=en&mode=4&country=1")
PINNACLE_HUB = "https://www.pinnacle.com/en/esports/cs2-hub"
BOVADA_CS2 = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
BO3_API = "https://api.bo3.gg/api/v1"
VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_TREE_API = f"https://api.github.com/repos/{VRS_REPO}/contents/live/2026"
VRS_BLOB = f"https://github.com/{VRS_REPO}/blob/main/"

# ----------------------------------------------------------------------------------------------
# Model constants — every one of these is traceable to a published file in this repository
# ----------------------------------------------------------------------------------------------
# Valve's own published rating slope (model/fit.js constant C used by the official standings model).
VALVE_C = 0.0056000078
VALVE_C_URL = (f"https://github.com/{VRS_REPO}/blob/main/model/fit.js")
# Fitted logistic slope of this project's own market-vs-VRS calibration (60 rated pairs),
# published in data/f7279a54/board.json -> calibration.
CAL_K = 0.43077894236569164
CAL_PAIRS = 60
CAL_MAE = 0.07702503405478646
CAL_SOURCE = "data/f7279a54/board.json#calibration (60 pairs, MAE 7.70 pp)"

# Valve publishes one row per counted roster; a team can therefore appear more than once with
# different points.  This is the documented selection rule (no guessing, alternatives published).
VRS_SELECT_RULE = (
    "When Valve's standings list the same organisation more than once (one row per counted "
    "roster), select the row whose roster lists a full five and whose latest published match "
    "date is the most recent; break ties on higher points. Alternatives are published on the "
    "Flagged for review page."
)


# ----------------------------------------------------------------------------------------------
# Text / name normalisation
# ----------------------------------------------------------------------------------------------
def esc(value) -> str:
    import html as _html
    return _html.escape("" if value is None else str(value), quote=True)


def norm(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_words(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"^ex[-_ ]", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


# ----------------------------------------------------------------------------------------------
# Odds maths
# ----------------------------------------------------------------------------------------------
def implied(decimal) -> float | None:
    try:
        d = float(decimal)
    except (TypeError, ValueError):
        return None
    return 1.0 / d if d > 1.0 else None


def novig(decimal_a, decimal_b) -> dict | None:
    """Two-way no-vig normalisation of a bookmaker's decimal pair."""
    ia, ib = implied(decimal_a), implied(decimal_b)
    if ia is None or ib is None:
        return None
    total = ia + ib
    if total <= 0:
        return None
    return {"prob_a": ia / total, "prob_b": ib / total, "overround": total - 1.0}


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float = CAL_K) -> float:
    """Logistic win probability over the difference in official Valve VRS points.

    p = 1 / (1 + exp(-k * C * (points_a - points_b))), where C is Valve's own published
    slope and k is this project's fitted calibration against market prices.
    """
    return logistic(k * VALVE_C * (float(points_a) - float(points_b)))


def confidence(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.52:
        return "Lean"
    return "Toss-up"


# ----------------------------------------------------------------------------------------------
# Valve VRS handling
# ----------------------------------------------------------------------------------------------
def _roster_size(row) -> int:
    roster = str(row.get("roster") or "")
    return len([p for p in roster.split(",") if p.strip()])


def vrs_index(vrs: dict) -> dict:
    """Group Valve standings rows by normalised organisation name.

    Returns {norm_name: {"rows": [...], "chosen": row, "rule": str, "ambiguous": bool}}.
    Selection follows VRS_SELECT_RULE.  Nothing is averaged and nothing is invented.
    """
    groups: dict[str, list] = {}
    for row in vrs.get("teams") or []:
        if not isinstance(row, dict):
            continue
        key = norm(row.get("team"))
        if not key:
            continue
        groups.setdefault(key, []).append(row)

    out: dict[str, dict] = {}
    for key, rows in groups.items():
        def sort_key(r):
            return (_roster_size(r), str(r.get("latest_match_date") or ""), int(r.get("points") or 0))

        ordered = sorted(rows, key=sort_key, reverse=True)
        out[key] = {
            "rows": ordered,
            "chosen": ordered[0],
            "ambiguous": len(ordered) > 1,
            "rule": VRS_SELECT_RULE,
        }
    return out


def vrs_lookup(index: dict, name: str, aliases: dict | None = None) -> dict | None:
    """Look a HotSpawn team name up in the Valve standings index (exact normalised match)."""
    key = norm(name)
    if key in index:
        return index[key]
    alias = (aliases or {}).get(norm(name)) or (aliases or {}).get(str(name))
    if alias:
        alias_key = norm(alias)
        if alias_key in index:
            return index[alias_key]
    return None


def vrs_floor(vrs: dict) -> dict | None:
    floor = (vrs or {}).get("floor") or {}
    if floor.get("points"):
        return floor
    rows = [r for r in (vrs.get("teams") or []) if r.get("points") is not None]
    if not rows:
        return None
    worst = min(rows, key=lambda r: (float(r.get("points")), -int(r.get("standing") or 0)))
    return {"standing": worst.get("standing"), "points": worst.get("points"),
            "team": worst.get("team")}


# ----------------------------------------------------------------------------------------------
# IO
# ----------------------------------------------------------------------------------------------
def load(path, default=None):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def dump_json(path, obj) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
                 encoding="utf-8")
