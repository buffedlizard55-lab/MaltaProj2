#!/usr/bin/env python3
"""Session 2cadfaf2 core (module name ``pc_core``) — pure functions, no network access.

Everything that turns raw source payloads into numbers lives here so it can be unit-tested
against the committed captures without touching the internet.

The audited maths and team-join helpers of session f7279a54
(``scripts/f7279a54/core.py``) are imported by path under a unique module name so that parallel
sessions cannot shadow each other through ``sys.path``. This module adds only what the
full-inventory desk needs:

* ``state_of``  — the status of **every** fixture the lobby lists (open / locked / in play /
  final / void / stale), derived from the published lock time and status, never guessed;
* ``ALIAS_GROUPS`` — each alias is a published matching decision with its evidence URLs, applied
  only when the other side of the fixture matches exactly;
* ``kalshi_start_utc`` — Kalshi tickers carry US-Eastern wall-clock times, converted with the real
  zone (so fixtures after the 1 November DST change are not shifted by an hour);
* ``VrsIndex`` — Valve VRS lookup that refuses duplicate organisation names unless the official
  per-team details file proves which roster is active;
* ``ladder`` — the documented pick ladder: market consensus -> calibrated VRS model -> explicit
  lower/upper bound -> unresolved (blank), never an invented number.

Rules enforced here
-------------------
* HotSpawn is used for fixture discovery and timing only. No HotSpawn crowd "picked %" value is
  read by any function in this module.
* A value that cannot be derived from a source stays ``None`` and is flagged, never filled.
"""
from __future__ import annotations

import importlib.util
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISO = "%Y-%m-%dT%H:%M:%SZ"


# ------------------------------------------------------------------ shared audited helpers
def _load_upstream_core():
    name = "core_f7279a54"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "scripts" / "f7279a54" / "core.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load_upstream_core()

norm = core.norm
canon = core.canon
same_team = core.same_team
no_vig = core.no_vig
logit = core.logit
sigmoid = core.sigmoid
vrs_prob = core.vrs_prob
fit_calibration = core.fit_calibration
confidence_label = core.confidence_label
decimal_to_american = core.decimal_to_american
SOURCE_WEIGHTS = core.SOURCE_WEIGHTS
VALVE_C = core.VALVE_C
consensus = core.consensus
KALSHI_MAX_SPREAD = core.KALSHI_MAX_SPREAD


def now_utc() -> datetime:
    return core.now_utc()


def to_iso(dt) -> str | None:
    return core.to_iso(dt)


def parse_iso(value) -> datetime | None:
    return core.parse_iso(value)


# --------------------------------------------------------------------- alias decisions
# Every entry is a published identity decision with the evidence that supports it. An alias is
# applied only when one side of a fixture resolves through the group and the other side matches
# the bookmaker's other team exactly. ``verified_utc`` is the date the evidence was read.
ALIAS_GROUPS: list[dict] = [
    {
        "keys": ["zetta", "alianzalima", "alianzalimaesports"],
        "display": "Zetta = Alianza Lima Esports",
        "verified_utc": "2026-10-21",
        "note": "HotSpawn/HLTV team 13833 'Zetta' is listed as 'Alianza Lima Esports' / 'Alianza "
                "Lima' by bo3.gg and by the Kalshi contract title; identical five starters "
                "(Antuanette, BabyRage, Notjuanjo, Slayerhz, zockie) in the same CCT South "
                "America Series 7 slot at the same kickoff.",
        "evidence": [
            "https://www.hltv.org/team/13833/zetta",
            "https://bo3.gg/teams/alianza-lima-esports",
            "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_americas_2026_10_05.md",
        ],
    },
    {
        "keys": ["apogeebetclic", "betclic", "betclicapogee", "betclicapogeeesports", "apogee"],
        "display": "Apogee Betclic = Betclic Apogee Esports",
        "verified_utc": "2026-10-21",
        "note": "HotSpawn 'Apogee Betclic', Melbet 'Apogee Esports', Thunderpick/bo3.gg 'Betclic' "
                "and HLTV team 12916 'Betclic' are one roster; that roster is Valve VRS 'Betclic'.",
        "evidence": [
            "https://www.hltv.org/team/12916/betclic",
            "https://liquipedia.net/counterstrike/Betclic_Apogee_Esports",
            "https://bo3.gg/teams/betclic-apogee-esports",
        ],
    },
    {
        "keys": ["b8", "b8esports"],
        "display": "B8 = B8 Esports",
        "verified_utc": "2026-10-21",
        "note": "Organisation suffix only; the exact pairing and start time must also agree.",
        "evidence": ["https://www.hltv.org/team/4549/b8"],
    },
    {
        "keys": ["losninos", "losninos"],
        "display": "LOS NINOS = Los Ninos",
        "verified_utc": "2026-10-21",
        "note": "Accent/spacing variant of the same team; the normaliser already folds accents.",
        "evidence": ["https://www.hltv.org/matches/2399865/zetta-vs-los-ninos-cct-2026-south-america-series-7"],
    },
]
KEY_TO_GROUP: dict[str, dict] = {}
for _group in ALIAS_GROUPS:
    for _k in _group["keys"]:
        KEY_TO_GROUP[_k] = _group

EX_PREFIX = re.compile(r"^ex[-_ ]", re.I)


def team_key(name: str | None) -> str:
    """Canonical key for a team name (ex- prefix folded away, 'esports' suffix stripped)."""
    if not name:
        return ""
    text = EX_PREFIX.sub("", str(name).strip())
    key = norm(text)
    if key in KEY_TO_GROUP:
        return key
    return core.canon(text)[0]


def alias_for(fixture_key: str, quote_key: str) -> dict | None:
    if not fixture_key or not quote_key or fixture_key == quote_key:
        return None
    group = KEY_TO_GROUP.get(fixture_key)
    if group and quote_key in group["keys"]:
        return group
    group = KEY_TO_GROUP.get(quote_key)
    if group and fixture_key in group["keys"]:
        return group
    return None


# --------------------------------------------------------------------------- Kalshi timing
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def kalshi_start_utc(event_ticker: str | None) -> tuple[str | None, str]:
    """``KXCS2GAME-26OCT211800LNALE`` -> the UTC instant of 18:00 US Eastern on 21 Oct 2026.

    Kalshi titles its CS2 contracts with Eastern wall-clock time. The conversion uses the real
    America/New_York zone when the system has tzdata, so the 1 November DST change is handled;
    otherwise it falls back to a fixed EDT offset and says so in the returned method string.
    """
    if not event_ticker:
        return None, "missing_ticker"
    code = str(event_ticker).split("-")
    if len(code) < 2:
        return None, "unparsable_ticker"
    code = code[1]
    try:
        yy, mon = int(code[0:2]), _MONTHS[code[2:5]]
        dd, hh, mm = int(code[5:7]), int(code[7:9]), int(code[9:11])
    except (KeyError, ValueError, IndexError):
        return None, "unparsable_ticker"
    try:
        from zoneinfo import ZoneInfo
        local = datetime(2000 + yy, mon, dd, hh, mm, tzinfo=ZoneInfo("America/New_York"))
        return local.astimezone(timezone.utc).strftime(ISO), "kalshi_ticker_america_new_york"
    except Exception:  # noqa: BLE001 - tzdata missing in a minimal image
        dt = datetime(2000 + yy, mon, dd, hh, mm, tzinfo=timezone.utc) + timedelta(hours=4)
        return dt.strftime(ISO), "kalshi_ticker_edt_assumed"


# ------------------------------------------------------------------------------ join quotes
JOIN_TOLERANCE_H = 5 / 60.0      # books and HotSpawn must agree to within five minutes
JOIN_WARN_H = 1.0                # accepted but published as a review flag
NEAR_MISS_H = 72.0               # logged for review, never joined


def quote_start_utc(quote: dict) -> tuple[str | None, str]:
    key = quote.get("source_key")
    if key == "kalshi":
        derived, method = kalshi_start_utc(quote.get("event_id"))
        if derived:
            return derived, method
    return quote.get("start_utc"), "source_start_time"


def join_quote(fixture: dict, quote: dict) -> dict | None:
    """Return join info when ``quote`` prices ``fixture``, else ``None``.

    Team identity is exact after normalisation, or through a published alias group **and** an
    exact other-side match. Start times must agree within ``JOIN_TOLERANCE_H``.
    """
    fa, fb = team_key(fixture.get("team_a")), team_key(fixture.get("team_b"))
    qa, qb = team_key(quote.get("team_a")), team_key(quote.get("team_b"))
    if not all((fa, fb, qa, qb)):
        return None
    via = None
    if fa == qa and fb == qb:
        swapped = False
    elif fa == qb and fb == qa:
        swapped = True
    else:
        a_a = fa == qa or alias_for(fa, qa) is not None
        b_b = fb == qb or alias_for(fb, qb) is not None
        a_b = fa == qb or alias_for(fa, qb) is not None
        b_a = fb == qa or alias_for(fb, qa) is not None
        if a_a and b_b:
            swapped = False
        elif a_b and b_a:
            swapped = True
        else:
            return None
        pairs = [(fa, qa), (fb, qb)] if not swapped else [(fa, qb), (fb, qa)]
        via = next((g for g in (alias_for(x, y) for x, y in pairs) if g), None)
    start, method = quote_start_utc(quote)
    f_start = parse_iso(fixture.get("start_utc"))
    q_start = parse_iso(start)
    if f_start is None or q_start is None:
        return {"rejected": True, "reason": "unverified_start_time", "swapped": swapped,
                "alias": via, "start_method": method, "start_diff_h": None}
    diff = abs((f_start - q_start).total_seconds()) / 3600.0
    info = {"swapped": swapped, "alias": via, "start_method": method, "start_diff_h": diff}
    if diff > JOIN_TOLERANCE_H:
        info["rejected"] = True
        info["reason"] = "start_time_mismatch"
        return info if diff <= NEAR_MISS_H else None
    return info


# ------------------------------------------------------------------------------- VRS index
class VrsIndex:
    """Valve Regional Standings lookup that refuses ambiguous organisation names.

    Valve's file can contain more than one row for an organisation (an older roster keeps its own
    rating). Guessing between them would silently invent a probability, so a duplicated name is
    left unrated unless the official per-team details file shows a clear, recent active roster.
    """

    def __init__(self, vrs: dict, now: datetime | None = None, max_age_days: int = 120):
        self.snapshot = (vrs or {}).get("snapshot")
        self.page_url = (vrs or {}).get("page_url")
        self.base_url = "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
        self.now = now or now_utc()
        self.max_age_days = max_age_days
        self.rows: dict[str, list[dict]] = {}
        for team in (vrs or {}).get("teams") or []:
            key = team_key(team.get("team"))
            if key:
                self.rows.setdefault(key, []).append(team)
        self.duplicates = {k: v for k, v in self.rows.items() if len(v) > 1}

    def _fresh(self, row: dict) -> bool:
        latest = row.get("latest_match_date")
        if not latest:
            return False
        try:
            seen = datetime.fromisoformat(latest).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return 0 <= (self.now - seen).days <= self.max_age_days and self._roster_size(row) >= 5

    @staticmethod
    def _roster_size(row: dict) -> int:
        roster = str(row.get("roster") or "")
        return len([p for p in re.split(r"[,;/]", roster) if p.strip()])

    def lookup(self, name: str | None) -> tuple[dict | None, str | None]:
        key = team_key(name)
        if not key:
            return None, "unrated_no_name"
        rows = self.rows.get(key) or []
        if not rows:
            # A published alias group can also settle the organisation name (e.g. HotSpawn
            # "Apogee Betclic" is Valve's "Betclic"). Only a unique alias row is accepted.
            group = KEY_TO_GROUP.get(key)
            if group:
                candidates = [k for k in group["keys"] if k != key and self.rows.get(k)]
                if len(candidates) == 1:
                    rows = self.rows[candidates[0]]
        if not rows:
            return None, "unrated_not_in_vrs"
        if len(rows) == 1:
            return self._decorate(rows[0]), None
        fresh = [r for r in rows if self._fresh(r)]
        if len(fresh) == 1:
            return self._decorate(fresh[0]), "duplicate_name_resolved_by_details_file"
        return None, "ambiguous_vrs_name"

    def _decorate(self, row: dict) -> dict:
        out = {k: row.get(k) for k in ("standing", "points", "team", "roster", "latest_match_date")}
        if row.get("details_path"):
            out["details_url"] = self.base_url + str(row["details_path"])
        out["snapshot"] = self.snapshot
        out["page_url"] = self.page_url
        return out

    def floor_points(self) -> int | None:
        points = [r.get("points") for rows in self.rows.values() for r in rows
                  if isinstance(r.get("points"), int)]
        return min(points) if points else None


# --------------------------------------------------------------------------- state machine
def state_of(fixture: dict, now: datetime) -> tuple[str, str]:
    """Return (state, plain-language reason) for one listed fixture.

    States: ``final`` (HotSpawn reports a winner), ``void`` (cancelled/forfeited without a
    winner), ``open`` (before its published lock time), ``locked`` (lock passed, not started),
    ``in_play`` (started, within eight hours), ``stale`` (status still 'scheduled' long after its
    published start - the lobby never updated it) and ``awaiting`` (no usable start time).
    """
    status = str(fixture.get("status") or "").lower()
    lock = parse_iso(fixture.get("lock_utc")) or parse_iso(fixture.get("start_utc"))
    start = parse_iso(fixture.get("start_utc"))
    if fixture.get("winner") in ("a", "b"):
        return "final", "HotSpawn reports a final result"
    if status in ("cancelled", "canceled"):
        return "void", "HotSpawn reports the fixture cancelled"
    if status == "forfeited":
        return "void", "HotSpawn reports the fixture forfeited without a winner"
    if start is None:
        return "awaiting", "HotSpawn publishes no usable start time"
    if lock and now < lock and status in ("scheduled", ""):
        return "open", "before the published lock time"
    if now < start:
        return "locked", "lock time has passed, the match has not started"
    if now - start <= timedelta(hours=8):
        return "in_play", "started less than eight hours ago"
    if status in ("scheduled", "started"):
        return "stale", "still 'scheduled' long after its published start time"
    return "past", "started more than eight hours ago"


PICKABLE_STATES = {"open"}


# ---------------------------------------------------------------------------------- ladder
def ladder(row: dict, calibration: dict, floor_points: int | None) -> dict | None:
    """Apply the published pick ladder to one row.

    1. ``market``    — no-vig consensus of every verified book/exchange quote (always wins).
    2. ``model``     — both teams rated by Valve: fitted-slope VRS probability.
    3. ``bound_lo``  — exactly one team rated: that team's probability is a LOWER bound, because
       the unrated opponent is assumed to sit at the lowest rating Valve publishes
       (``floor_points``). Published with the assumption spelled out, never as a point estimate.
    4. ``None``      — nothing verifiable; the row is published blank and listed as unresolved.
    """
    k = float(calibration.get("k") or 1.0)
    market = row.get("market")
    if market and isinstance(market.get("prob_a"), (int, float)):
        prob_a = float(market["prob_a"])
        return _line(row, prob_a, "market",
                     sources=[q["public_url"] for q in row.get("quotes") or [] if q.get("public_url")],
                     detail={"n_sources": market.get("n_sources"), "spread_a": market.get("spread_a"),
                             "k": None})
    ra, rb = row["vrs"].get("team_a"), row["vrs"].get("team_b")
    if ra and rb:
        delta = ra["points"] - rb["points"]
        prob_a = vrs_prob(delta, 0, k)
        return _line(row, prob_a, "model",
                     sources=[u for u in (ra.get("page_url"), rb.get("page_url")) if u],
                     detail={"delta_points": delta, "k": round(k, 4),
                             "team_a_points": ra["points"], "team_b_points": rb["points"],
                             "valve_uncalibrated_prob_a": round(vrs_prob(delta, 0, 1.0), 4)})
    if (ra or rb) and floor_points is not None:
        rated_is_a = bool(ra)
        rated = ra or rb
        delta = rated["points"] - floor_points
        p_rated = vrs_prob(delta, 0, k)
        prob_a = p_rated if rated_is_a else 1.0 - p_rated
        return _line(row, prob_a, "bound_lo",
                     sources=[u for u in (rated.get("page_url"),) if u],
                     detail={"rated_team": rated["team"], "rated_points": rated["points"],
                             "assumed_opponent_points": floor_points, "k": round(k, 4),
                             "bound_side": "lower bound for the rated team"},
                     assumption=(f"the unrated opponent is assumed to sit at Valve's lowest published "
                                 f"rating ({floor_points} pts), so the rated team's true probability "
                                 f"is at least this value"))
    return None


def _line(row: dict, prob_a: float, basis: str, sources: list[str], detail: dict,
          assumption: str | None = None) -> dict:
    prob_a = min(max(prob_a, 0.02), 0.98)
    prob_b = 1.0 - prob_a
    side = "a" if prob_a >= prob_b else "b"
    pick_prob = prob_a if side == "a" else prob_b
    fair_a, fair_b = 1 / prob_a, 1 / prob_b
    return {
        "basis": basis,
        "prob_a": round(prob_a, 4), "prob_b": round(prob_b, 4),
        "pick_side": side,
        "pick_team": row["team_a"] if side == "a" else row["team_b"],
        "pick_prob": round(pick_prob, 4),
        "confidence": confidence_label(pick_prob),
        "fair_decimal_a": round(fair_a, 3), "fair_decimal_b": round(fair_b, 3),
        "fair_american_a": decimal_to_american(fair_a),
        "fair_american_b": decimal_to_american(fair_b),
        "sources": [s for s in dict.fromkeys(sources) if s],
        "detail": detail,
        **({"assumption": assumption} if assumption else {}),
    }


BASIS_LABEL = {
    "market": "Market line",
    "model": "VRS model",
    "bound_lo": "Lower bound",
}

BASIS_NOTE = {
    "market": "De-vigged consensus of the book/exchange prices listed on this row.",
    "model": "Derived from Valve's official Regional Standings points with the slope fitted to "
             "observed book lines; no external price exists for this fixture yet.",
    "bound_lo": "One side has no official rating, so this is an explicit bound, not a point "
                "estimate. Read the assumption before using it.",
}
