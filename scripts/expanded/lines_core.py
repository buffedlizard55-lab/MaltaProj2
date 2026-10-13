#!/usr/bin/env python3
"""Shared helpers for the T-EXPAND line collector: normalisation, matching, de-vig.

Rules encoded here (and published on the site):
  * Team identity is decided by a normalised name match plus an explicit alias table.
    A quote is only used when *both* participants match a fixture.
  * Side order is not assumed: sources that list the pair the other way round have their
    prices swapped, and that swap is recorded on the row.
  * A quote is joined to a fixture when the source publishes a start time within
    ``TIME_TOLERANCE_MIN`` minutes of the fixture's start, or — when the source publishes
    no start time — when the source's competition name contains the fixture's competition
    (or vice versa) after normalisation.
  * No-vig probability is proportional: p_i = (1/d_i) / sum_j(1/d_j).
  * Consensus is the arithmetic mean over the sources that quote the same fixture.
  * Nothing is inferred: a fixture without a joined quote has no probability anywhere.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

TIME_TOLERANCE_MIN = 90

# Explicit, reviewable alias table: source spelling -> canonical spelling used by the lobby.
# Keys are normalised (see `norm`). Only add an entry when the two names are the same team;
# "Academy", "fe" (female) and "Jr" variants are deliberately NOT collapsed.
ALIASES = {
    "teamaurora": "aurora",
    "9zglobant": "9z",
    "9zte": "9z",
    "nip": "ninjasinpyjamas",
    "nipsweden": "ninjasinpyjamas",
    "sashiesport": "sashi",
    "sashiesports": "sashi",
    "bcgameesports": "bcgame",
    "teameny": "envy",
    "parivisionteam": "parivision",
    "betboomteam": "betboom",
    "gremioesports": "gremio",
    "losninosesports": "losninos",
    "eacopenhagen": "eac",
    "eacacademy": None,  # explicit non-alias: keep distinct
    "wbt": "wrotberry",
    "pcificespor": "pcific",
    "privateergaming": "privateer",
    "fnaticteam": "fnatic",
    "keydstars": "exkeydstars",
    "exkeyd": "exkeydstars",
    "exkeydstars": "exkeydstars",
    "teamfalcons": "falcons",
    "enjoyteam": "enjoy",
    "enjoygaming": "enjoy",
    "thelastresort": "thelastresort",
    "lastresort": "thelastresort",
    "g2ares": "g2ares",
    "forzereload": "forzereload",
    "lfo10": "lfo10",
    "mibrteam": "mibr",
    "havufinland": "havu",
    "roundsgg": "roundsgg",
    "vocagaming": "voca",
    "phantomgaming": "phantom",
    "whitebitteam": "wrotberry",
    "whitebit": "wrotberry",
    "bbteam": "betboom",
    "auroragaming": "aurora",
    "rounds": "roundsgg",
    "roundsggteam": "roundsgg",
    "kaisergaming": "kaiser",
}
ALIASES = {k: v for k, v in ALIASES.items() if v}

# Suffixes that are pure marketing noise on *either* side of a comparison. Stripped only
# when the remainder still matches another team exactly, which is why this is applied
# produce-a-candidate rather than as a blanket equal-name rule.
NOISE_SUFFIXES = ("esports", "esport", "gaming", "team", "club", "gg")
NOISE_PREFIXES = ("team", "the")


def norm(name: str | None) -> str:
    """Normalise a team name for comparison: casefold, strip accents and punctuation."""
    if not name:
        return ""
    txt = unicodedata.normalize("NFKD", str(name))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.casefold()
    txt = re.sub(r"[^a-z0-9]+", "", txt)
    return txt


def candidates(name: str | None) -> list[str]:
    """Normalised candidate keys for a team name (itself, its alias, noise-stripped forms)."""
    n = norm(name)
    if not n:
        return []
    out = [n]
    if n in ALIASES:
        out.append(ALIASES[n])
    stems = [n]
    for suffix in NOISE_SUFFIXES:
        if n.endswith(suffix) and len(n) > len(suffix) + 1:
            stems.append(n[: -len(suffix)])
    for prefix in NOISE_PREFIXES:
        if n.startswith(prefix) and len(n) > len(prefix) + 1:
            stems.append(n[len(prefix):])
    for stem in stems:
        if stem not in out:
            out.append(stem)
        if stem in ALIASES and ALIASES[stem] not in out:
            out.append(ALIASES[stem])
    return out


def same_team(a: str | None, b: str | None) -> bool:
    """True when two spellings can be the same team by exact normalised match or alias."""
    ca, cb = set(candidates(a)), set(candidates(b))
    if not ca or not cb:
        return False
    # Direct alias resolution: compare canonical forms.
    canon_a = {ALIASES.get(x, x) for x in ca}
    canon_b = {ALIASES.get(x, x) for x in cb}
    return bool(canon_a & canon_b)


def competition_tokens(name: str | None) -> set[str]:
    """Significant tokens of a competition name (letters/digits, length > 3, casefolded)."""
    if not name:
        return set()
    txt = unicodedata.normalize("NFKD", str(name))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch)).casefold()
    return {t for t in re.split(r"[^a-z0-9]+", txt) if len(t) > 3}


def same_competition(a: str | None, b: str | None) -> bool:
    """Competition names agree when the shorter name's significant tokens are mostly present.

    Sources abbreviate tournament names differently ("ESL Challenger League Season 52: North
    America - Cup #3" vs "ESL Challenger League North America"), so containment alone is too
    strict. The rule used is: at least 3 shared significant tokens AND at least 60% of the
    shorter name's tokens present in the longer one.
    """
    ta, tb = competition_tokens(a), competition_tokens(b)
    if len(ta) < 3 or len(tb) < 3:
        return False
    shared = ta & tb
    if len(shared) < 3:
        return False
    shorter = ta if len(ta) <= len(tb) else tb
    return len(shared) / len(shorter) >= 0.6


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / (1000 if value > 1e11 else 1),
                                           tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    txt = str(value).strip()
    if not txt:
        return None
    if txt.isdigit():  # epoch seconds or milliseconds given as a string
        return parse_iso(int(txt))
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00").replace("z", "+00:00"))
        # The lobby API mixes timezone-aware and naive timestamps; the project contract is
        # that every parsed time is UTC-aware, otherwise comparisons raise TypeError.
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"):
            try:
                return datetime.strptime(txt, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def to_utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 60.0


def american_to_decimal(price) -> float | None:
    try:
        a = float(price)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (100 / abs(a)) if a < 0 else 1 + (a / 100), 6)


def implied(dec_a: float | None, dec_b: float | None) -> tuple[float | None, float | None, float | None]:
    """Proportional no-vig probabilities plus the overround for a two-way market."""
    if not dec_a or not dec_b or dec_a <= 1.0 or dec_b <= 1.0:
        return None, None, None
    qa, qb = 1.0 / dec_a, 1.0 / dec_b
    total = qa + qb
    return round(qa / total, 4), round(qb / total, 4), round(total - 1.0, 6)


def join_quote(fixture: dict, quote: dict) -> dict | None:
    """Decide whether a raw quote belongs to a fixture; return the join record or None."""
    fa, fb = fixture.get("team_a"), fixture.get("team_b")
    qa, qb = quote.get("team_a_name"), quote.get("team_b_name")
    if not all([fa, fb, qa, qb]):
        return None

    direct = same_team(fa, qa) and same_team(fb, qb)
    swapped = same_team(fa, qb) and same_team(fb, qa)
    if not (direct or swapped):
        return None

    f_dt = parse_iso(fixture.get("scheduled_start_time"))
    q_dt = parse_iso(quote.get("start_time_utc"))
    delta = minutes_between(f_dt, q_dt)
    if delta is not None:
        if delta > TIME_TOLERANCE_MIN:
            return None
        rule = f"both teams match; source start time within {TIME_TOLERANCE_MIN} min"
    else:
        if not same_competition(fixture.get("competition_name"), quote.get("source_league")):
            return None
        rule = "both teams match; source gives no start time, competition names agree"

    return {
        "rule": rule,
        "side_order": "reversed" if swapped else "same",
        "start_time_delta_min": round(delta, 1) if delta is not None else None,
        "aliases_applied": sorted({n for n in (qa, qb)
                                   if norm(n) not in (norm(fa), norm(fb))}),
    }


def consensus(quotes: list[dict]) -> dict | None:
    """Mean of per-source no-vig probabilities for quotes already oriented to the fixture."""
    usable = [q for q in quotes if q.get("implied_prob_a") is not None]
    if not usable:
        return None
    probs_a = [q["implied_prob_a"] for q in usable]
    probs_b = [q["implied_prob_b"] for q in usable]
    means = (round(sum(probs_a) / len(probs_a), 4), round(sum(probs_b) / len(probs_b), 4))
    spread = round(max(probs_a) - min(probs_a), 4) if len(probs_a) > 1 else None
    sources = sorted({q["source_key"] for q in usable})
    return {
        "method": "arithmetic mean of per-source proportional no-vig probabilities",
        "n_sources": len(usable),
        "sources": sources,
        "prob_a": means[0],
        "prob_b": means[1],
        "spread_a": spread,
        "min_prob_a": min(probs_a),
        "max_prob_a": max(probs_a),
    }
