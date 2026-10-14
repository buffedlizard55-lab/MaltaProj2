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
    # HotSpawn lists the Ukrainian roster WROTBERRY; bo3.gg's published Thunderpick feed and its own
    # match slugs call the same roster WBT (bo3.gg team id 22734, acronym WBT). Three fixtures agree
    # on BOTH the opponent and the kick-off minute, which is the evidence used here:
    #   WROTBERRY vs EAC    2026-10-15T08:00:00Z  <-> wbt-vs-esport-academy-copenhagen-15-10-2026
    #   WROTBERRY vs ENCE   2026-10-15T12:00:00Z  <-> wbt-vs-ence-15-10-2026
    #   WROTBERRY vs BOJONG 2026-10-15T16:00:00Z  <-> wbt-vs-bojong-15-10-2026
    # "WBT Academy" is a DIFFERENT roster (Valve VRS lists WBT and WBT Academy separately) and is
    # never merged with WBT.
    "wrotberry": {
        "canonical": "wbt",
        "note": "Three fixtures match bo3.gg's published listings on both opponent and kick-off: "
                "WROTBERRY vs EAC / wbt-vs-esport-academy-copenhagen, WROTBERRY vs ENCE / "
                "wbt-vs-ence and WROTBERRY vs BOJONG / wbt-vs-bojong (all 2026-10-15).",
        "evidence": [
            "https://bo3.gg/matches/wbt-vs-esport-academy-copenhagen-15-10-2026",
            "https://bo3.gg/matches/wbt-vs-ence-15-10-2026",
            "https://bo3.gg/matches/wbt-vs-bojong-15-10-2026",
            "https://play.hotspawn.com/lobby",
        ],
    },
    # Melbet's shared 1xBet LineFeed titles the three Elisa BreakOut fixtures "WhiteBIT Team" and
    # "EA Copenhagen" where bo3.gg's Thunderpick feed titles them "WBT" and "EAC" at the identical
    # kick-offs (2026-10-15T08:00:00Z, 12:00:00Z and 16:00:00Z). bo3.gg's own team slug for EAC is
    # esport-academy-copenhagen, which is also how Kalshi spells it.
    "whitebitteam": {
        "canonical": "wbt",
        "note": "Melbet/1xBet list 'WhiteBIT Team vs EA Copenhagen' at 2026-10-15T08:00:00Z, "
                "'WhiteBIT Team vs ENCE' at 12:00:00Z and 'WhiteBIT Team vs BOJONG' at 16:00:00Z; "
                "bo3.gg's feed lists the same three kick-offs as WBT vs EAC, WBT vs ENCE and "
                "WBT vs BOJONG. Same three fixtures, one roster, two org titles.",
        "evidence": [
            "https://melbet.com/en/line/esports",
            "https://bo3.gg/matches/wbt-vs-esport-academy-copenhagen-15-10-2026",
            "https://bo3.gg/matches/wbt-vs-ence-15-10-2026",
            "https://bo3.gg/matches/wbt-vs-bojong-15-10-2026",
        ],
    },
    "eacopenhagen": {
        "canonical": "eac",
        "note": "Melbet/1xBet spell the academy out as 'EA Copenhagen'; bo3.gg's own team slug is "
                "esport-academy-copenhagen (acronym EAC) and its feed, Kalshi and HotSpawn all use "
                "EAC for the same fixtures and kick-offs.",
        "evidence": [
            "https://melbet.com/en/line/esports",
            "https://bo3.gg/matches/esport-academy-copenhagen-vs-bojong-15-10-2026",
            "https://api.bo3.gg/api/v1/teams/?filter%5Bteams.id%5D%5Beq%5D=23942",
        ],
    },
    "esportacademycopenhagen": {
        "canonical": "eac",
        "note": "Kalshi titles the roster 'Esport Academy Copenhagen'; bo3.gg's team slug of the "
                "same id is esport-academy-copenhagen and its acronym is EAC.",
        "evidence": [
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct151000bojeac",
            "https://api.bo3.gg/api/v1/teams/?filter%5Bteams.id%5D%5Beq%5D=23942",
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


# ------------------------------------------------------------------------ label disagreements
# A price source can publish the SAME fixture under a different opponent name, and that is not a
# team rename: Valve's standings list the two names as separate rosters, so aliasing them globally
# would join a price to the wrong fixture. Each entry below therefore applies to ONE fixture pair
# only, and carries the URLs a reviewer needs to check the call. Key:
# (source_key, canonical_team_1, canonical_team_2) with the two team keys sorted.
OPPONENT_LABEL_DISAGREEMENTS: dict[tuple[str, str, str], dict] = {
    ("kalshi", "6666", "loskogutos"): {
        "fixture_pair": ("6666", "bandachuya"),
        "note": "Kalshi and bo3.gg trade 6666's 11:00Z CCT Series 12 Play-In fixture as 'los "
                "kogutos vs 6666', while HotSpawn and HLTV's official bracket title the same "
                "kick-off 'Banda chuya vs 6666'. The roster settles it: bo3.gg's own match page "
                "lists the players maaryy, tomiko, AdrieN, showk and ezox, which is exactly the "
                "five Valve's standings publish for Banda Chuya (#165), while Valve's separate "
                "los kogutos entry (#276) is a different five. Published under HotSpawn's title, "
                "Banda chuya.",
        "evidence": [
            "https://bo3.gg/matches/los-kogutos-vs-sixsixsixsix-14-10-2026",
            "https://www.hltv.org/events/9456/cct-2026-europe-series-12-closed-qualifier",
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct140700unklk",
            "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/"
            "2026/standings_global_2026_10_05.md",
        ],
    },
    ("kalshi", "forzereload", "sokerorg"): {
        "fixture_pair": ("forzereload", "lfo10"),
        "note": "Kalshi trades FORZE Reload's 17:00Z fixture as 'Sokerorg vs FORZE Reload' and "
                "bo3.gg publishes the identical kick-off as forze-reload-vs-sokerorg. HLTV's "
                "official CCT 2026 Europe Series 11 bracket lists FORZE Reload's 14 October opponent "
                "as LFO 10, which is also HotSpawn's title. One team cannot play twice at the same "
                "minute, so both titles describe one fixture; the HLTV title is what is published.",
        "evidence": [
            "https://www.hltv.org/matches/2399301/forze-reload-vs-lfo-10-cct-2026-europe-series-11",
            "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct141300skrforzer",
            "https://bo3.gg/matches/forze-reload-vs-sokerorg-14-10-2026",
            "https://bo3.gg/teams/forze-reload/matches",
        ],
    },
}

# Kalshi lists the three 2026-10-15 Elisa BreakOut fixtures of the WBT roster as "WBT Academy".
# The roster in those fixtures is WBT, not WBT Academy: bo3.gg's own match page for the 08:00Z game
# prints a lineup of Psycho, DemQQ, Smash and s4ltovsk1yy, which is four of the five players Valve's
# standings list for WBT (#60), while Valve lists a completely different five for WBT Academy (#130).
# The call stays scoped to these three fixture pairs and is never applied to any other fixture.
for _opp_key, _opp_link in (("eac", "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct150400eacwbtacadem"),
                            ("ence", "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct150800encewbtacade"),
                            ("bojong", "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct151200bojwbtacadem")):
    OPPONENT_LABEL_DISAGREEMENTS[("kalshi", _opp_key, "wbtacademy")] = {
        "fixture_pair": (_opp_key, "wbt"),
        "note": "Kalshi trades this 2026-10-15T08:00Z/12:00Z/16:00Z fixture as 'WBT Academy'. "
                "bo3.gg's match page for the same kick-off prints WBT's official lineup "
                "(Psycho, DemQQ, Smash, s4ltovsk1yy) and Valve's standings list those four under WBT "
                "(#60) while WBT Academy (#130) is a different five. Published under HotSpawn's and "
                "bo3.gg's title, WBT.",
        "evidence": [
            _opp_link,
            "https://bo3.gg/matches/wbt-vs-esport-academy-copenhagen-15-10-2026",
            "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/"
            "2026/standings_global_2026_10_05.md",
        ],
    }


def label_disagreement(source_key: str, team_a: str | None, team_b: str | None) -> dict | None:
    """The reviewed label record for this source's team pair, or None."""
    ka, _, _ = canon(team_a)
    kb, _, _ = canon(team_b)
    if not ka or not kb:
        return None
    return OPPONENT_LABEL_DISAGREEMENTS.get((source_key, *sorted((ka, kb))))


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


def parse_any(value) -> datetime | None:
    """A timestamp as ISO text, epoch seconds or epoch milliseconds (used for source payloads)."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        iso_dt = parse_iso(value)
        if iso_dt:
            return iso_dt
        try:
            value = float(value)
        except ValueError:
            return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    if num > 1e11:          # milliseconds
        return datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
    if num > 1e8:           # seconds
        return datetime.fromtimestamp(num, tz=timezone.utc)
    return None


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
