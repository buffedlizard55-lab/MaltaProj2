"""Session c0e223d3 — pure helpers. No network access, no writes.

Everything here is arithmetic and formatting. Probability comes from Valve's own published model
shape (documented in ValveSoftware/counter-strike_regional_standings, model/glicko.js) with the
slope taken from the calibration that the `ourline` board already publishes, so this session does
not invent a second model.
"""
from __future__ import annotations

import html
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

# ------------------------------------------------------------------ Valve VRS model constants
# Valve's repository: "rank delta of 400 points = 90% chance of victory"; Q = ln(10)/400
# g = 1 / sqrt(1 + 3*Q^2*RD^2/pi^2); evaluated with the fixed default RD of 75.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

DEFAULT_K = 1.0  # only used when no published calibration is available


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a, points_b, k: float = DEFAULT_K):
    """P(A beats B) from Valve VRS points, with the published calibration slope `k`."""
    if points_a is None or points_b is None:
        return None
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


# ------------------------------------------------------------------------------ Valve parsing
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(?P<team>.+?)\s*\|\s*(?P<roster>.*?)\s*\|",
    re.M,
)


def parse_valve_markdown(text: str) -> list[dict]:
    """Parse a Valve `standings_*_YYYY_MM_DD.md` table into rows. Header rows are skipped."""
    out = []
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        team = m.group("team").strip()
        if not team or team.lower() in {"team name", "team"} or set(team) <= set("-: "):
            continue
        out.append(
            {
                "standing": int(m.group(1)),
                "points": int(m.group(2)),
                "team": team,
                "roster": m.group("roster").strip(),
            }
        )
    return out


def load_valve_teams(root: Path):
    """Read Valve's official standings from the committed capture, newest snapshot first.

    Returns (teams_by_name, meta). Never fabricates: an empty list means the file was not found.
    """
    root = Path(root)
    candidates = [
        root / "data" / "expanded" / "vrs" / "standings_global_2026_10_05.md",
        root / "proof" / "42580809" / "evidence" / "vrs_global_2026_10_05.md",
        root / "verify" / "8e7a652d" / "evidence" / "standings_global_2026_10_05.md",
    ]
    for path in candidates:
        if path.is_file():
            rows = parse_valve_markdown(path.read_text(encoding="utf-8"))
            if rows:
                by_name = {r["team"].casefold(): r for r in rows}
                return by_name, {
                    "path": str(path.relative_to(root)),
                    "snapshot": "2026_10_05",
                    "n_teams": len(rows),
                }
    return {}, {"path": None, "snapshot": None, "n_teams": 0}


# ------------------------------------------------------------------------------------- format
def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "&mdash;"
    return f"{value * 100:.{digits}f}%"


def confidence_label(p_pick: float) -> str:
    """Same thresholds the `ourline` board publishes, so the two boards read identically."""
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


def hours_since(iso: str):
    if not iso:
        return None
    try:
        then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            return None
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0


BASIS_LABEL = {
    "market": "Bookmaker line",
    "market+model": "Bookmaker line + rating model",
    "model": "Rating model (Valve VRS)",
    "vrs-resolved": "Rating model (Valve VRS, name resolved)",
    "none": "No pick — flagged",
}


def basis_label(basis: str) -> str:
    return BASIS_LABEL.get(basis, basis or "No pick — flagged")


# --------------------------------------------------------------------------------- json reads
def read_json(path: Path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default
