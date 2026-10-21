#!/usr/bin/env python3
"""Core helpers for the bce97e13 independent verification desk (``cs2-picks/``).

Everything here is stdlib-only, deterministic and offline-capable.  The desk does not invent a
single number: it re-derives every probability on the canonical every-match board
(``data/5f903db4/board.json``) from raw book/exchange quotes or the official Valve regional
standings table, and records a per-row verdict.  A value that cannot be re-derived is published as
unverified, never patched.
"""
from __future__ import annotations

import html as _html
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "bce97e13"
SITE = ROOT / "cs2-picks"

# Read-only canonical inputs (owned by other sessions; never written here).
CANONICAL_BOARD = "data/5f903db4/board.json"
RAW_LOBBY_SNAPSHOT = "data/7adc7718/raw_snapshot.json"
COMMITTED_VRS = "data/5f903db4/vrs_global.json"

# Public source URLs.
HOTSPAWN_LOBBY = "https://play.hotspawn.com/lobby"
HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
VALVE_REPO = "ValveSoftware/counter-strike_regional_standings"
VALVE_CONTENTS = f"https://api.github.com/repos/{VALVE_REPO}/contents"
VALVE_BLOB = f"https://github.com/{VALVE_REPO}/blob/main/"

# Formula constants published by Valve in model/glicko.js (Q = ln(10)/400) and model/fit.js
# (defaultGlickoParams.rd = 75, applied through setFixedRD).  The effective logistic slope on a
# rank-difference is C = ln(10) * g(75) / 400 where g is Glicko's RD term.  verify_slope() below
# re-derives the number instead of trusting it.
VALVE_Q = math.log(10.0) / 400.0
VALVE_FIXED_RD = 75.0
CANONICAL_C = 0.0056000078
# Project calibration slope fitted on 60 market-vs-VRS pairs (data/f7279a54/board.json#calibration).
CANONICAL_K = 0.43077894236569164

TOL_MARKET = 0.0025   # 0.25 pp: equal-weight consensus vs stored market probability
TOL_VRS = 0.0006      # 0.06 pp: re-derived logistic vs stored originated probability


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def esc(value) -> str:
    return _html.escape("" if value is None else str(value), quote=True)


def norm(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


# --------------------------------------------------------------------------------- odds maths
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


def glicko_g(rd: float = VALVE_FIXED_RD) -> float:
    return 1.0 / math.sqrt(1.0 + (3.0 * VALVE_Q ** 2 * rd ** 2) / (math.pi ** 2))


def valve_slope(rd: float = VALVE_FIXED_RD) -> float:
    """Effective logistic slope implied by Valve's published Glicko implementation."""
    return math.log(10.0) * glicko_g(rd) / 400.0


def vrs_prob(points_a: float, points_b: float,
             k: float = CANONICAL_K, c: float = CANONICAL_C) -> float:
    return logistic(k * c * (float(points_a) - float(points_b)))


def confidence(p_pick: float) -> str:
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.52:
        return "Lean"
    return "Toss-up"


# --------------------------------------------------------------------------- official VRS parse
def parse_official_markdown(text: str) -> dict:
    """Parse a Valve standings_global_YYYY_MM_DD.md table into typed rows."""
    teams: list[dict] = []
    for line in text.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if not m:
            continue
        standing, points, team, roster = (int(m.group(1)), int(m.group(2)),
                                          m.group(3).strip(), m.group(4).strip())
        details = re.search(r"\((details/[^)]+)\)", line)
        teams.append({
            "standing": standing,
            "points": points,
            "team": team,
            "roster": roster,
            "details_path": details.group(1) if details else None,
        })
    by_name: dict[str, list[dict]] = {}
    for row in teams:
        by_name.setdefault(norm(row["team"]), []).append(row)
    floor = None
    if teams:
        worst = min(teams, key=lambda r: (r["points"], -r["standing"]))
        floor = {"standing": worst["standing"], "points": worst["points"], "team": worst["team"]}
    return {"teams": teams, "by_name": by_name, "floor": floor, "n_teams": len(teams)}


# ------------------------------------------------------------------------------------------- IO
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


def http_get(url: str, headers: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    """Stdlib GET.  Returns (status, body).  Network failures surface as (0, b'')."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "malta-bce97e13-verifier"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URLs)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""
