"""Day-5 desk (session 7900154b) — pure functions, no network access.

Everything that turns retained source payloads into a published number lives here so it can be
unit-tested against real captured payloads without touching the internet.

Rules this module enforces
--------------------------
* HotSpawn is fixture discovery and settlement only. Its crowd "picked %" is **never** a
  win probability. It is carried as leaderboard context and labelled as such.
* A bookmaker price is joined to a fixture only when BOTH team names resolve to the same
  canonical key and the source kickoff is inside the tolerance window. A one-sided match is
  never accepted.
* A probability that cannot be derived from a source is left as ``None`` and reported as
  unresolved. It is never filled in, never defaulted to 50/50.
"""
from __future__ import annotations

import importlib.util
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone

ISO = "%Y-%m-%dT%H:%M:%SZ"

# The canonical repository engine (session f7279a54) owns name normalisation, the no-vig
# maths and the Valve-VRS model. It is imported read-only so this session's published
# numbers cannot drift away from the canonical board published elsewhere on the site.
_ENGINE = None


def canonical_engine():
    """Load scripts/f7279a54/core.py as a private module (read-only input)."""
    global _ENGINE
    if _ENGINE is None:
        path = _repo_root() / "scripts" / "f7279a54" / "core.py"
        spec = importlib.util.spec_from_file_location("day5_canonical_core", path)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(path.parent))
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.pop(0)
        _ENGINE = mod
    return _ENGINE


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ time helpers
def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime(ISO) if dt else None


def parse_iso(value) -> datetime | None:
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


def parse_ms(value) -> datetime | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 1e12:
        n /= 1000.0
    return datetime.fromtimestamp(n, tz=timezone.utc)


def parse_any(value) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return parse_ms(value)
    if isinstance(value, str) and value.strip().isdigit():
        return parse_ms(value)
    return parse_iso(value)


def hours_apart(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# --------------------------------------------------------------- team name keys
_NOISE_TOKENS = {
    "gaming", "esports", "team", "cs", "cs2", "csgo", "gg", "org", "club", "the",
    "project", "academy", "ac", "squad", "roster", "official",
}

_ACCENTS = {
    "ø": "o", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe", "ł": "l", "ı": "i",
    "å": "a", "ö": "o", "ä": "a", "é": "e", "è": "e", "ê": "e", "ë": "e",
    "ü": "u", "û": "u", "ù": "u", "á": "a", "à": "a", "â": "a", "ã": "a",
    "í": "i", "ì": "i", "î": "i", "ï": "i", "ó": "o", "ò": "o", "ô": "o", "õ": "o",
    "ú": "u", "ů": "u", "ñ": "n", "ç": "c", "ś": "s", "š": "s", "ž": "z", "č": "c",
    "ř": "r", "ę": "e", "ą": "a", "ő": "o", "ű": "u", "ť": "t", "ď": "d", "ě": "e",
    "ů": "u", "ď": "d", "ľ": "l", "ĺ": "l", "ŕ": "r", "ň": "n", "ť": "t", "ď": "d",
}


def strip_accents(value: str) -> str:
    text = value
    for src, dst in _ACCENTS.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def name_tokens(name: str | None) -> tuple[str, ...]:
    """Reduce a team name to a comparable token tuple.

    Rules (published on the method page):
      * accents are folded (``Sökerorg`` -> ``sokerorg``);
      * punctuation becomes a space;
      * a small, fixed list of organisational noise words is dropped
        (``Aurora Gaming`` -> ``aurora``, ``BetBoom Team`` -> ``betboom``);
      * a leading ``ex`` is dropped because HotSpawn uses it for a rebranded roster
        (``ex-RUSTEC`` -> ``rustec``) — the same rule the canonical engine uses.
    """
    if not name:
        return ()
    text = strip_accents(str(name)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if t]
    if tokens and tokens[0] == "ex":
        tokens = tokens[1:]
    tokens = [t for t in tokens if t not in _NOISE_TOKENS]
    return tuple(sorted(tokens))


def same_team(a: str | None, b: str | None) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    return bool(ta) and ta == tb


# ------------------------------------------------------------------- odds maths
def no_vig(decimal_a, decimal_b) -> dict | None:
    """Proportional removal of the bookmaker margin from a two-way price."""
    try:
        da, db = float(decimal_a), float(decimal_b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(da) or not math.isfinite(db) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.35:
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


def blend(probabilities: list[float]) -> float | None:
    """Simple mean of independent no-vig probabilities (equal weight per book)."""
    vals = [float(p) for p in probabilities if p is not None and 0.0 < float(p) < 1.0]
    if not vals:
        return None
    return sum(vals) / len(vals)


def vrs_probability(points_a, points_b, k: float = 1.0) -> float | None:
    """P(A beats B) from official Valve VRS points, using the repository's own model.

    ``k`` scales Valve's published slope. ``k=1`` is Valve's own slope; a smaller ``k`` is
    the slope the repository's canonical engine fits to observed bookmaker lines, because
    Valve's own README says their curve is too steep.
    """
    if points_a is None or points_b is None:
        return None
    try:
        return canonical_engine().vrs_prob(float(points_a), float(points_b), float(k))
    except Exception:  # noqa: BLE001 - a model failure must not invent a number
        return None


def fit_calibration(pairs) -> dict:
    """Fit the ratings-model slope to observed market prices, with the canonical engine."""
    usable = [{"delta": float(p["delta"]), "market_prob_a": float(p["market_prob_a"])}
              for p in pairs or []
              if p.get("delta") is not None and p.get("market_prob_a") is not None]
    try:
        return canonical_engine().fit_calibration(usable)
    except Exception:  # noqa: BLE001
        return {"n_pairs": len(usable), "k": 1.0, "fitted": False, "k_raw": None,
                "mae_prob": None, "mae_prob_valve": None, "min_pairs": 6, "bounds": [0.25, 1.5]}


# ------------------------------------------------------------------ Valve ratings
def vrs_index(teams):
    """Index Valve's global standings by canonical team key."""
    idx: dict[tuple[str, ...], list[dict]] = {}
    for t in teams or []:
        idx.setdefault(name_tokens(t.get("team")), []).append(t)
    return idx


def vrs_resolve(name, idx):
    """Resolve a team name against Valve's global standings.

    A name can appear more than once in the file because the file records more than one
    roster of the same organisation at different points in time (the older rows carry an
    earlier ``latest_match_date``). The current entry is the one with the most recent
    activity; a tie falls back to the higher rating.

    Returns ``(entry, ambiguous)``. ``entry`` is ``None`` when the name is not in the list.
    """
    cands = idx.get(name_tokens(name)) or []
    if not cands:
        return None, False
    if len(cands) == 1:
        return cands[0], False
    best = max(cands, key=lambda t: (str(t.get("latest_match_date") or ""),
                                     int(t.get("points") or 0)))
    return best, True


def vrs_floor(teams):
    """The lowest rating in Valve's list: the floor for a side that is absent from it."""
    points = [int(t.get("points") or 0) for t in teams or []]
    return min(points) if points else None


def bounded_probability(rated_points, floor_points, k: float = 1.0):
    """Minimum probability for a rated side when the opponent is absent from Valve's list.

    An absent side is treated as no better than the lowest-ranked team Valve does list, so
    the rated side's probability is at least the model value against that floor. This is a
    floor, not an estimate.
    """
    if rated_points is None or floor_points is None:
        return None
    return vrs_probability(rated_points, floor_points, k)


# ------------------------------------------------------------------ pick policy
# "Contrarian but not stupid" is a published rule set, not a mood:
# A bookmaker kickoff must land inside this window of the HotSpawn kickoff to be joined.
KICKOFF_TOLERANCE_HOURS = 30.0

CONTRARIAN_FLOOR = 0.35          # never take a side we rate below 35%
CONTRARIAN_MIN_EDGE = 0.05       # our probability must beat the crowd by >= 5 points
SAFE_FLOOR = 0.55                # a "safe" pick is the side at or above this probability
CROWD_ELSEWHERE = 0.15           # the under-picked side must be at most this popular


def choose_pick(prob_a: float | None, prob_b: float | None,
                crowd_a: float | None = None, crowd_b: float | None = None) -> dict:
    """Return the pick, the contrarian layer and the reason it did or did not qualify.

    ``safe``   — the side with the higher probability.
    ``climb``  — the side the crowd under-picks, but only when it clears the floor.
    """
    out = {"safe": None, "safe_prob": None, "climb": None, "climb_prob": None,
           "climb_reason": "", "climb_rejected": "", "edge": None}
    if prob_a is None or prob_b is None:
        out["climb_rejected"] = "No probability from any source; nothing to pick."
        return out
    if prob_a >= prob_b:
        out["safe"], out["safe_prob"] = "a", prob_a
    else:
        out["safe"], out["safe_prob"] = "b", prob_b
    if crowd_a is None or crowd_b is None:
        out["climb_rejected"] = "No HotSpawn crowd split recorded; no leaderboard edge can be measured."
        return out
    crowd = {"a": float(crowd_a) / 100.0, "b": float(crowd_b) / 100.0}
    prob = {"a": float(prob_a), "b": float(prob_b)}
    # The under-picked side is the one the crowd backs less.
    side = "a" if crowd["a"] <= crowd["b"] else "b"
    other = "b" if side == "a" else "a"
    out["edge"] = prob[side] - crowd[side]
    if prob[side] < CONTRARIAN_FLOOR:
        out["climb_rejected"] = (
            f"Our own probability for that side is {prob[side] * 100:.1f}%, below the "
            f"{CONTRARIAN_FLOOR * 100:.0f}% floor. A contrarian pick below the floor is a "
            f"lottery ticket, not a climb.")
        return out
    if crowd[side] > CROWD_ELSEWHERE:
        out["climb_rejected"] = (
            f"The crowd already backs that side ({crowd[side] * 100:.0f}%); there is no "
            f"crowd disagreement left to exploit.")
        return out
    if out["edge"] < CONTRARIAN_MIN_EDGE:
        out["climb_rejected"] = (
            f"Only {out['edge'] * 100:.1f} points better than the crowd, below the "
            f"{CONTRARIAN_MIN_EDGE * 100:.0f}-point minimum edge.")
        return out
    out["climb"], out["climb_prob"] = side, prob[side]
    out["climb_reason"] = (
        f"Under-picked by the crowd ({crowd[side] * 100:.0f}% picked) and rated "
        f"{prob[side] * 100:.1f}% by our own line, {out['edge'] * 100:.1f} points of edge, "
        f"above the {CONTRARIAN_FLOOR * 100:.0f}% floor.")
    if prob[side] < prob[other]:
        out["climb_reason"] += (
            " This is the underdog, so it is a real shot at an upset rather than a safe "
            "price — take it only if the points are worth the risk.")
    return out
