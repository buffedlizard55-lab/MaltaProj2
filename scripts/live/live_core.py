#!/usr/bin/env python3
"""Core helpers for the T-COVER current-lobby board (session 3cd9787c).

Everything in this module is pure: normalisation, odds arithmetic, join rules and the
originated-estimate model are all deterministic functions of their arguments, so every
published number can be re-derived from the raw evidence committed under `data/live/`.

Rules that the project requires and this module enforces:

* HotSpawn's crowd "picked %" is never an argument to any function here. Nothing in this file
  reads a HotSpawn pick percentage, so no HotSpawn crowd number can reach a probability.
* A market probability is only ever produced from two quoted prices of the *same* market
  (`no_vig_two_way`), and the raw prices stay attached to the row that publishes it.
* An originated estimate is emitted from the official Valve CS2 Regional Standings only, in its
  own field, with its own label, and is never mixed into a market consensus.
"""
from __future__ import annotations

import html as html_module
import json
import math
import re
import ssl
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------------------- time
ISO = "%Y-%m-%dT%H:%M:%SZ"


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def now_iso() -> str:
    return now_utc().strftime(ISO)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime(ISO)


def parse_ms(value) -> datetime | None:
    """HotSpawn serves epoch milliseconds as strings."""
    if value in (None, ""):
        return None
    try:
        ms = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    # A 10-digit value would be seconds; HotSpawn uses milliseconds (~13 digits).
    if ms < 10_000_000_000:
        ms *= 1000
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_any(value) -> datetime | None:
    """Parse a timestamp that a source may publish either as ISO text or as epoch milliseconds."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return parse_ms(value)
    text = str(value).strip()
    if text.isdigit():
        return parse_ms(text)
    return parse_iso(text)


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# ------------------------------------------------------------------------------------ fetching
UA = "MaltaProj2-TCOVER/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2; research)"
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")


def fetch(url: str, headers: dict | None = None, timeout: int = 45) -> dict:
    """Fetch a URL and always return a diagnostic dict. Never raises.

    The raw body is returned as bytes so a parser can be re-checked against exactly what the
    source served.
    """
    req_headers = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)
    out = {"url": url, "status": None, "bytes": 0, "body": b"", "error": None,
           "content_type": None, "final_url": url}
    try:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as resp:
            body = resp.read()
            out["status"] = resp.status
            out["bytes"] = len(body)
            out["body"] = body
            out["content_type"] = resp.headers.get("Content-Type")
            out["final_url"] = resp.geturl()
    except urllib.error.HTTPError as exc:  # server answered with an error status
        try:
            out["body"] = exc.read()
        except Exception:  # noqa: BLE001
            out["body"] = b""
        out["status"] = exc.code
        out["error"] = f"HTTPError {exc.code}"
        out["bytes"] = len(out["body"])
    except Exception as exc:  # noqa: BLE001 - network/TLS/DNS failures are evidence too
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def fetch_json(url: str, headers: dict | None = None, timeout: int = 45):
    res = fetch(url, headers, timeout)
    parsed = None
    if res["body"]:
        try:
            parsed = json.loads(res["body"].decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            parsed = None
    return parsed, {k: v for k, v in res.items() if k != "body"}


# -------------------------------------------------------------------------------- name joins
_ALNUM = re.compile(r"[^a-z0-9]+")


def norm(name: str | None) -> str:
    """Normalise a team name: strip accents, case and punctuation."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _ALNUM.sub("", text.casefold())


# Source spelling -> HotSpawn spelling. Every entry was added only after the same pairing was
# seen in a source payload and in the HotSpawn fixture list with an agreeing start time or
# tournament. Unknown spellings are never guessed: they stay unmatched and are flagged.
ALIASES = {
    "bbteam": "betboom",
    "pvision": "parivision",
    "9zglobant": "9z",
    "teamfalcons": "falcons",
    "teamaurora": "aurora",
    "teamlegacy": "legacy",
    "nip": "ninjasinpyjamas",
    "ninjasinpyjamas": "ninjasinpyjamas",
    "sashiesport": "sashi",
    "furiaesports": "furia",
    "heroicesports": "heroic",
    "astralisesports": "astralis",
    "g2ares": "g2ares",
    "mibresports": "mibr",
    "cloud9korea": "cloud9",
    "karminecorp": "karminecorp",
    "movistarkoi": "movistarkoi",
    "teamsecretwhales": "teamsecretwhales",
    "louisvuittondonuts": "louisvuittondonuts",
}


def canon_team(name: str | None) -> str:
    n = norm(name)
    return ALIASES.get(n, n)


def same_team(a: str | None, b: str | None) -> bool:
    na, nb = canon_team(a), canon_team(b)
    return bool(na) and na == nb


# ------------------------------------------------------------------------------ odds numbers
def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    if p > 0:
        return round(1.0 + p / 100.0, 6)
    return round(1.0 + 100.0 / abs(p), 6)


def decimal_to_implied(dec) -> float | None:
    try:
        d = float(dec)
    except (TypeError, ValueError):
        return None
    if d <= 1.0:
        return None
    return 1.0 / d


def no_vig_two_way(dec_a, dec_b) -> dict | None:
    """Proportional de-vig of a two-way market.

    q_i = 1 / odd_i ; p_i = q_i / (q_a + q_b). The overround (sum of q - 1) is published with
    every derived pair so the bookmaker margin is visible rather than hidden inside the price.
    """
    qa = decimal_to_implied(dec_a)
    qb = decimal_to_implied(dec_b)
    if qa is None or qb is None:
        return None
    total = qa + qb
    if total <= 0:
        return None
    return {"prob_a": qa / total, "prob_b": qb / total, "overround": total - 1.0,
            "q_a": qa, "q_b": qb}


def consensus(entries: list[dict]) -> dict | None:
    """Arithmetic mean of per-source no-vig probabilities plus the observed range.

    Each entry must carry `source_key`, `prob_a` and `prob_b` derived by `no_vig_two_way` from
    that source's own two quoted prices.
    """
    if not entries:
        return None
    pa = [float(e["prob_a"]) for e in entries]
    mean_a = sum(pa) / len(pa)
    mean_a = clamp(mean_a, 0.0, 1.0)
    return {
        "method": "arithmetic mean of per-source proportional no-vig probabilities",
        "n_sources": len(entries),
        "sources": sorted({e["source_key"] for e in entries}),
        "prob_a": mean_a,
        "prob_b": 1.0 - mean_a,
        "min_prob_a": min(pa),
        "max_prob_a": max(pa),
        "spread_a": (max(pa) - min(pa)) if len(pa) > 1 else None,
    }


# ---------------------------------------------------------------------- originated estimate
VRS_SCALE = 400.0
VRS_MODEL = ("p(a beats b) = 1 / (1 + 10 ** (-(R_a - R_b) / 400)) on official Valve CS2 "
             "Regional Standings points. The 400-point scale is a stated modelling assumption, "
             "not a Valve-published quantity.")


def vrs_estimate(points_a: float | None, points_b: float | None) -> dict | None:
    if points_a is None or points_b is None:
        return None
    diff = float(points_a) - float(points_b)
    p_a = 1.0 / (1.0 + 10.0 ** (-diff / VRS_SCALE))
    return {"prob_a": p_a, "prob_b": 1.0 - p_a, "rating_diff": diff, "model": VRS_MODEL,
            "scale": VRS_SCALE}


def vrs_markdown_rows(text: str) -> dict[str, dict]:
    """Parse a Valve regional-standings markdown file.

    Rows look like:  | 1 | 2046 | Spirit | donk, magixx, ... | [details](...) |
    Only rows with an integer standing and an integer points value are accepted, so a header or
    a malformed line can never invent a rating.
    """
    out: dict[str, dict] = {}
    row_re = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|", re.M)
    for m in row_re.finditer(text):
        standing, points, team = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        if not team:
            continue
        key = canon_team(team)
        if not key:
            continue
        roster = m.group(4).strip()
        prev = out.get(key)
        if prev is None or points > prev["points"]:
            out[key] = {"team": team, "points": points, "standing": standing, "roster": roster}
    return out


# ------------------------------------------------------------------------------- text dump
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)


def html_to_text(html: str) -> str:
    text = SCRIPT_RE.sub(" ", html)
    text = TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text)


def parse_lobby_counters(html: str) -> dict:
    """Read the lobby's own counters out of the served page text.

    These are the numbers the user actually sees on the site, so they are recorded verbatim and
    compared against our computed counts instead of being assumed.
    """
    text = html_to_text(html)
    out: dict = {"text_sample": text[:400]}
    m = re.search(r"(\d[\d,]*)\s*matches this week", text, re.I)
    if m:
        out["matches_this_week"] = int(m.group(1).replace(",", ""))
    m = re.search(r"Resets in ([0-9dhm\s]+?)(?:Sign in|$)", text, re.I)
    if m:
        out["resets_in"] = m.group(1).strip()
    m = re.search(r"All tiers\s*\((\d+)\)", text)
    if m:
        out["all_tiers"] = int(m.group(1))
    tiers = {}
    for tier in ("S", "B", "C"):
        m = re.search(rf"(?<![A-Za-z]){tier}\s*\((\d+)\)", text)
        if m:
            tiers[tier.lower()] = int(m.group(1))
    if tiers:
        out["tier_counts"] = tiers
    games = {}
    for game in ("CS2", "LoL"):
        m = re.search(rf"{re.escape(game)}\s*\(?(\d+)\)?", text)
        if m:
            games[game] = int(m.group(1))
    if games:
        out["game_counts"] = games
    m = re.search(r"All tournaments\s*\((\d+)\)", text)
    if m:
        out["all_tournaments"] = int(m.group(1))
    return out


LOBBY_STATE_RE = re.compile(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', re.S | re.I)
INLINE_JSON_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S | re.I)
MATCH_LINK_RE = re.compile(r"hotspawn\.com/matches/", re.I)


def extract_lobby_listing(page_html: str) -> dict:
    """Read the fixture ids the lobby page itself carries (Angular `ng-state` / inline JSON).

    The lobby is an Angular app whose server-rendered state embeds the fixture payload, so the ids
    found here ARE the fixtures the page is listing. If nothing parses, the caller must treat the
    listing as unknown — never as empty.
    """
    out: dict = {"found": False, "listed_ids": [], "listed_count": 0, "source": None,
                 "match_links_rendered": len(MATCH_LINK_RE.findall(page_html))}
    blobs: list[tuple[str, str]] = []
    m = LOBBY_STATE_RE.search(page_html)
    if m:
        blobs.append(("ng-state", html_module.unescape(m.group(1))))
    for i, mm in enumerate(INLINE_JSON_RE.finditer(page_html)):
        blobs.append((f"inline-json-{i}", html_module.unescape(mm.group(1))))
    for name, raw in blobs:
        try:
            state = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        ids: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                if "participants0_name" in node and "scheduled_start_time" in node and "id" in node:
                    ids.append(str(node["id"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(state)
        if ids:
            unique = sorted(set(ids))
            out.update({"found": True, "source": name, "listed_ids": unique,
                        "listed_count": len(unique)})
            return out
    return out


def week_window(at: datetime, weekday: int = 0, hour: int = 0) -> tuple[datetime, datetime]:
    """Monday-00:00-UTC week window containing `at` (the lobby's reset cadence is Monday-based)."""
    start = (at - timedelta(days=(at.weekday() - weekday) % 7)).replace(
        hour=hour, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def days_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (a - b).total_seconds() / 86400.0


def safe_round(value, places: int = 4):
    if value is None:
        return None
    return round(float(value), places)


def pct(value, places: int = 1) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.{places}f}%"


def pick_from_probs(prob_a, prob_b, min_edge: float = 0.0) -> dict | None:
    """Pick = higher probability. A tie inside `min_edge` is reported as a coin flip, never
    as a confident pick."""
    if prob_a is None or prob_b is None:
        return None
    edge = float(prob_a) - float(prob_b)
    if abs(edge) < min_edge:
        return {"side": None, "probability": max(prob_a, prob_b), "edge": edge,
                "reason": "probabilities equal inside the tie tolerance"}
    side = "a" if edge > 0 else "b"
    return {"side": side, "probability": prob_a if side == "a" else prob_b, "edge": edge,
            "reason": "higher no-vig probability"}


def json_dump(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write("\n")


def json_load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def log10(x: float) -> float:
    return math.log10(x)
