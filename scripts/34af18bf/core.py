#!/usr/bin/env python3
"""Shared arithmetic and formatting helpers for session 34af18bf (pick desk).

Everything here is deterministic and unit-tested in tests/test_34af18bf.py.
No probability is ever produced from a HotSpawn crowd percentage: the crowd
number is treated as ownership only and reaches the pages through a separate
field (``crowd_*``) that is never read by the arithmetic below.
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- time
def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso(dt: datetime) -> str:
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


def from_epoch_ms(value) -> datetime | None:
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def from_epoch_s(value) -> datetime | None:
    try:
        secs = float(value)
    except (TypeError, ValueError):
        return None
    if secs <= 0:
        return None
    return datetime.fromtimestamp(secs, tz=timezone.utc)


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return round(abs((b - a).total_seconds()) / 3600.0, 2)


# --------------------------------------------------------------------------- odds
def american_to_decimal(price) -> float | None:
    """US moneylines: +150 -> 2.5, -200 -> 1.5. Returns None when nonsense."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    if p >= 100:
        return round(1.0 + p / 100.0, 4)
    if p <= -100:
        return round(1.0 + 100.0 / abs(p), 4)
    return None


def decimal_to_prob(decimal: float | None) -> float | None:
    if not decimal or decimal <= 1.0:
        return None
    return 1.0 / float(decimal)


def no_vig(dec_a: float | None, dec_b: float | None) -> dict | None:
    """Proportional no-vig split of a two-sided decimal line."""
    pa, pb = decimal_to_prob(dec_a), decimal_to_prob(dec_b)
    if pa is None or pb is None:
        return None
    total = pa + pb
    if total <= 0:
        return None
    return {"prob_a": pa / total, "prob_b": pb / total, "overround": total}


def fair_decimal(prob: float | None) -> float | None:
    if prob is None or prob <= 0.0:
        return None
    return round(1.0 / prob, 2)


def blend(readings: list[dict]) -> dict | None:
    """Weighted mean of two-sided readings.

    ``readings`` items: {"prob_a": float, "prob_b": float, "weight": float}.
    Weights are declared on the method page; the default weight for every
    accepted source is 1.0 and Pinnacle is the only source weighted 2.0.
    """
    usable = [r for r in readings if r.get("prob_a") is not None and (r.get("weight") or 0) > 0]
    if not usable:
        return None
    wsum = sum(float(r["weight"]) for r in usable)
    pa = sum(float(r["prob_a"]) * float(r["weight"]) for r in usable) / wsum
    pb = sum(float(r["prob_b"]) * float(r["weight"]) for r in usable) / wsum
    total = pa + pb
    return {
        "prob_a": round(pa / total, 6),
        "prob_b": round(pb / total, 6),
        "sources": len(usable),
        "weight_sum": round(wsum, 4),
    }


def share(prob: float | None) -> float | None:
    if prob is None:
        return None
    return round(float(prob), 6)


def spread_from_decimals(dec_a: float | None, dec_b: float | None) -> float | None:
    """Overround of a two-sided line expressed as a fraction of 1.0."""
    nv = no_vig(dec_a, dec_b)
    return round(nv["overround"] - 1.0, 6) if nv else None


# --------------------------------------------------------------------------- text
def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


_ALIASES = {
    # canonical key -> set of spellings seen in the sources this desk reads
    "3dmax": {"3dmax", "3d max"},
    "3dmax academy": {"3dmax academy"},
    "academy13": {"academy13", "academy 13"},
    "betboom": {"betboom", "betboom team", "bb"},
    "falcons": {"falcons", "team falcons"},
    "furia": {"furia", "furia esports"},
    "aurora": {"aurora", "aurora gaming"},
    "9z": {"9z", "9z team"},
    "ninjas in pyjamas": {"ninjas in pyjamas", "nip", "ninjas in pyjamas (nip)"},
    "heroic": {"heroic"},
    "ex-6666": {"ex-6666", "ex6666", "6666"},
    "wrotberry": {"wrotberry", "wbt", "wrotberry team"},
    "wbt academy": {"wbt academy", "havu"},
    "roundsgg": {"roundsgg", "rounds"},
    "privater": {"privateer", "privateer gaming"},
    "phantom academy": {"phantom academy"},
    "antidaun": {"antidaun"},
    "nexus": {"nexus", "nexus gaming"},
    "lynx": {"lynx", "lynn vision", "lynn vision gaming"},
    "morningstar": {"morningstar"},
    "rare atom": {"rare atom"},
    "alter ego": {"alter ego"},
    "chinggis warriors": {"chinggis warriors"},
    "wxm": {"wxm"},
    "nexvoid": {"nexvoid", "nexvoid esports"},
    "vitalem aerem": {"vitalem aerem"},
    "genone": {"genone"},
    "butterfly": {"butterfly", "butterfly effect"},
    "baks": {"baks", "baks esports"},
    "fire flux": {"fire flux", "fire flux esports"},
    "eternal fire": {"eternal fire"},
    "nuclear tigeres": {"nuclear tigeres", "nuclear tigers"},
    "apogee": {"apogee", "apogee betclic", "apogee esports"},
    "nemesis": {"nemesis", "team nemesis"},
    "bebop": {"bebop"},
    "donstu": {"donstu", "donstu esports"},
    "infinite": {"infinite", "infinite gaming"},
    "insiders": {"insiders"},
    "aimclub": {"aimclub"},
    "basement boys": {"basement boys"},
    "bc.game": {"bc.game", "bcgame"},
    "drama": {"drama"},
    "iberian soul": {"iberian soul"},
    "hyperspirit": {"hyperspirit", "hyper spirit"},
    "sashi": {"sashi", "sashi esports"},
    "mouz nxt": {"mouz nxt", "mouz academy"},
    "astral": {"astral", "astral esports"},
    "leo": {"leo", "leo team"},
    "banda chuya": {"banda chuya"},
    "enjoy": {"enjoy", "enjoy gaming"},
    "ninjas in pyjamas": {"ninjas in pyjamas", "nip"},
    "betera": {"betera"},
    "just players": {"just players", "just_players"},
    "bet-m": {"bet-m", "betm", "bet m"},
}


def canon(name: str | None) -> str:
    """Canonical key for a team name (alias-aware, case/punctuation-insensitive)."""
    if not name:
        return ""
    raw = str(name).strip().casefold()
    raw = raw.replace("\u2019", "'")
    for key, spellings in _ALIASES.items():
        if raw in spellings:
            return key
    return slug(raw)


def pair_key(a: str | None, b: str | None) -> tuple[str, str]:
    return (canon(a), canon(b))


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(prob: float | None, digits: int = 0) -> str:
    if prob is None:
        return "—"
    return f"{float(prob) * 100:.{digits}f}%"


def money(prob: float | None) -> str:
    if prob is None:
        return "—"
    return f"${float(prob):.2f}"


def human_utc(value) -> str:
    dt = parse_iso(value) if isinstance(value, str) else value
    if not dt:
        return "—"
    return dt.strftime("%d %b %H:%M UTC")
