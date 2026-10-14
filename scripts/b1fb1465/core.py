#!/usr/bin/env python3
"""Session b1fb1465 core helpers: name canonicalisation, documented aliases, odds maths, time.

Every alias in :data:`ALIASES` was verified against at least two public listings that agree on the
fixture (both teams plus the kick-off time), and the evidence URL is published on the page that uses
it. Nothing here guesses: if two listings disagree on a team, the join is refused and the row is
published as unresolved with the reason.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# Deliberately empty: this session does NOT strip generic words such as "Academy" or "Team",
# because "B8" and "B8 Academy" are different rosters and merging them would join a price to the
# wrong fixture. Every real spelling difference observed in a source is handled by the explicit,
# evidence-backed ALIASES table below instead. (The inherited full-coverage collector does strip such
# words; this session's published counts are therefore allowed to differ from that board's.)
NOISE_TOKENS: set[str] = set()
NON_ALNUM = re.compile(r"[^a-z0-9]")

# Source spelling (normalised) -> canonical key, with the evidence that authorises the
# equivalence. Kept deliberately small: one entry per real, checked spelling difference.
ALIASES: dict[str, dict] = {
    # Kalshi and Bovada both title the Turkish roster "WRAITH PCIFIC" (sponsor prefix), while
    # HotSpawn, bo3.gg and HLTV title it PCIFIC. The fixture evidence is identical: opponent
    # Ryvex, kick-off 2026-10-14T14:00:00Z.
    "wraithpcific": {
        "canonical": "pcific",
        "note": "Kalshi event KXCS2GAME-26OCT141000RYVWRA and Bovada event 32204982 both list "
                "'WRAITH PCIFIC' against Ryvex at 2026-10-14T14:00:00Z; bo3.gg slug "
                "pcific-esport-vs-ryvex-14-10-2026 and HotSpawn both list 'PCIFIC'.",
        "evidence": [
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct141000ryvwra",
            "https://www.bovada.lv/esports/counter-strike-2/cct-europe/series-12/"
            "wraith-pcific-ryvex-202610141000",
            "https://bo3.gg/matches/pcific-esport-vs-ryvex-14-10-2026",
        ],
    },
    # bo3.gg's Thunderpick feed names the roster "ROUNDS" while its own match slug, the event
    # listing and HotSpawn call it RoundsGG (bo3.gg team id 5440, same fixture ids 131780/131781).
    "rounds": {
        "canonical": "roundsgg",
        "note": "bo3.gg match id 131780 is slugged havu-vs-roundsgg-16-10-2026 while its "
                "bet_updates team name is 'ROUNDS' (team id 5440); Kalshi titles the same fixture "
                "'RoundsGG vs. HAVU'.",
        "evidence": [
            "https://bo3.gg/matches/havu-vs-roundsgg-16-10-2026",
            "https://bo3.gg/teams/rounds",
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct160600rgghavu",
        ],
    },
    # Kalshi titles the roster "Privateer Gaming"; HotSpawn and Bovada's own URL slug say
    # "Privateer" / "Privateer Gaming" for the same fixture against mellren.
    "privateergaming": {
        "canonical": "privateer",
        "note": "Kalshi KXCS2GAME-26OCT161000PGMEL lists 'Privateer Gaming vs. mellren' at "
                "2026-10-16T14:00:00Z; HotSpawn lists 'mellren vs Privateer' at the same instant.",
        "evidence": [
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct161000pgmel",
            "https://play.hotspawn.com/lobby",
        ],
    },
}


def norm(name: str | None) -> str:
    """Case/accent/punctuation-insensitive key with generic org words stripped."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    tokens = [t for t in re.split(r"[^a-z0-9.&]+", text) if t]
    while len(tokens) > 1 and tokens[0] in NOISE_TOKENS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in NOISE_TOKENS:
        tokens.pop()
    return NON_ALNUM.sub("", "".join(tokens))


def canon(name: str | None) -> tuple[str, list[str], str | None]:
    """(canonical key, evidence URLs, note) for a team name published by any source."""
    key = norm(name)
    entry = ALIASES.get(key)
    if entry:
        return entry["canonical"], list(entry.get("evidence") or []), entry.get("note")
    return key, [], None


# --------------------------------------------------------------------------------- odds maths
def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return round(1 + p / 100.0, 6)
    if p <= -100:
        return round(1 + 100.0 / abs(p), 6)
    return None


def no_vig(dec_a: float, dec_b: float) -> dict | None:
    """Two-way implied shares with the bookmaker margin removed proportionally."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if da <= 1.0 or db <= 1.0:
        return None
    qa, qb = 1.0 / da, 1.0 / db
    total = qa + qb
    if total <= 0:
        return None
    return {"prob_a": qa / total, "prob_b": qb / total, "overround": total - 1.0}


def median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def vrs_probability(points_a: float, points_b: float, scale: float) -> float | None:
    """Bradley-Terry / Elo-style share of the official Valve regional points.

    ``p_a = 1 / (1 + 10 ** ((Pb - Pa) / scale))``. ``scale`` is published on the method page; it is
    NOT fitted to any market and is not derived from HotSpawn.
    """
    try:
        pa, pb = float(points_a), float(points_b)
    except (TypeError, ValueError):
        return None
    if scale <= 0:
        return None
    return 1.0 / (1.0 + 10 ** ((pb - pa) / scale))


def confidence(pick_prob: float | None, basis: str) -> str:
    if pick_prob is None:
        return "Unrated"
    edge = abs(pick_prob - 0.5)
    if basis.startswith("exchange"):
        return "Low (thin exchange book)" if edge < 0.25 else "Moderate (thin exchange book)"
    if edge >= 0.30:
        return "Strong"
    if edge >= 0.15:
        return "Solid"
    if edge >= 0.05:
        return "Lean"
    return "Toss-up"


# ------------------------------------------------------------------------------------- time
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_ms(value) -> datetime | None:
    """HotSpawn timestamps are epoch milliseconds; anything else is refused."""
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return round((a - b).total_seconds() / 3600.0, 3)


def within(dt_a: datetime | None, dt_b: datetime | None, hours: float) -> bool:
    diff = hours_between(dt_a, dt_b)
    return diff is not None and abs(diff) <= hours


# ---------------------------------------------------------------------------------- lobby
LOBBY_STATE_RE = re.compile(
    r'<script[^>]+id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)
CROWD_PICK_RE = re.compile(r"pick_?percent|picked_?pct|crowd", re.I)
FIXTURE_KEYS = ("id", "sport_alias", "competition_name", "tier", "stage", "best_of", "status",
                "points", "scheduled_start_time", "lock_time", "participants0_name",
                "participants1_name", "winner_participant_name", "best_of_count")


def lobby_state(page_html: str) -> dict:
    """Extract the Angular transfer state the public lobby page embeds."""
    m = LOBBY_STATE_RE.search(page_html or "")
    if not m:
        return {}
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return {}
    out: dict = {"fixtures": None, "fixtures_url": None, "permalinks": {}, "week": None}
    for value in state.values():
        if not isinstance(value, dict):
            continue
        url, body = str(value.get("u") or ""), value.get("b")
        if url.split("?")[0].endswith("/api/v1/fixtures") and isinstance(body, list):
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


def fixture_from_hotspawn(raw: dict | None) -> dict | None:
    """Normalise one HotSpawn fixture. A crowd-pick percentage is never copied."""
    if not isinstance(raw, dict) or str(raw.get("sport_alias") or "").casefold() != "cs2":
        return None
    start, lock = parse_ms(raw.get("scheduled_start_time")), parse_ms(raw.get("lock_time"))
    a, b = raw.get("participants0_name"), raw.get("participants1_name")
    if not raw.get("id") or not a or not b or start is None:
        return None
    for key in raw:
        if CROWD_PICK_RE.search(str(key)):
            raise AssertionError(f"a crowd-pick field ({key}) reached the fixture parser")
    return {
        "fixture_id": str(raw.get("id")),
        "competition": raw.get("competition_name"),
        "tier": raw.get("tier"),
        "stage": raw.get("stage"),
        "best_of": raw.get("best_of") or raw.get("best_of_count"),
        "points": raw.get("points"),
        "status": str(raw.get("status") or "").lower(),
        "start_utc": iso(start),
        "lock_utc": iso(lock),
        "team_a": str(a),
        "team_b": str(b),
        "winner": raw.get("winner_participant_name"),
    }


def is_open(fixture: dict, at: datetime | None = None) -> bool:
    """A fixture is still pickable when its lock has not passed and it has not started."""
    at = at or now_utc()
    lock = parse_iso(fixture.get("lock_utc"))
    start = parse_iso(fixture.get("start_utc"))
    if fixture.get("winner"):
        return False
    if str(fixture.get("status") or "") not in ("scheduled", ""):
        return False
    if lock and lock <= at:
        return False
    if start and start <= at - timedelta(minutes=1):
        return False
    return True
