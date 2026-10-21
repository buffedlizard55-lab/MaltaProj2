"""EVERYPICK core (session 907e9435) — pure resolution logic, no network access.

Purpose
-------
Turn one retained capture (HotSpawn lobby inventory + every external two-way price we could
observe + the official Valve Regional Standings) into exactly one row per open HotSpawn CS2
fixture, with:

* a pick (always, unless the fixture itself is unidentifiable),
* a two-sided win probability that is labelled by *how* it was obtained,
* the source link(s) behind every number,
* the limitations, explicitly, when the number is an assumption rather than evidence.

Resolution ladder (first match wins)
------------------------------------
1. ``market_multi``   two or more independent external two-way prices, de-vigged and averaged.
2. ``market_single``  exactly one external two-way price.
3. ``exchange``       a Kalshi order-book mid inside the spread gate, at a kickoff the exchange
                      itself states in ``rules_primary`` (the exchange's own timestamp field is
                      demonstrably four hours off its own rules text, so it is never used).
4. ``vrs_model``      both rosters are in the official Valve VRS table, the calibrated curve is
                      applied to the points difference and the fit is validated on 60 priced
                      fixtures (k = 0.4308).
5. ``assumption``     one side has no official rating at all: the pick is the rated side and the
                      probability is published as a *range* between two documented assumptions
                      (unrated side at the official VRS floor, and at the VRS median). This is
                      never counted as verified.
6. ``unresolved``     nothing above applies, or the fixture's opponent identity conflicts with
                      another source. Values stay blank.

Rules enforced here (and asserted by tests/test_907e9435.py)
------------------------------------------------------------
* No HotSpawn crowd "picked %" value is read anywhere: the fixture normaliser drops those fields.
* A price is joined only when both team names match after documented normalisation (plus a
  published alias with an evidence note) AND the kickoff agrees to within five minutes.
* Every published probability is re-derived from raw prices at build time; stored probabilities
  are never trusted.
* Duplicate VRS rows for one organisation are resolved only with official evidence (five-player
  roster plus the newest counted match in Valve's own details file), and the decision is published.
"""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from datetime import datetime, timezone

SESSION = "907e9435"
ISO = "%Y-%m-%dT%H:%M:%SZ"

VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_BLOB = f"https://github.com/{VRS_REPO}/blob/main/"
TIME_TOLERANCE_H = 5 / 60          # join gate: five minutes (policy, not source evidence)
KALSHI_MAX_SPREAD = 0.10           # a wider bid/ask on either side is not a usable price
CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "kalshi": 1.0}


# ------------------------------------------------------------------------------------ time
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
    if dt.tzinfo is None:      # a naive timestamp has no verifiable zone -> refuse it
        return None
    return dt.astimezone(timezone.utc)


def hours_apart(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# ------------------------------------------------------------------------------- team names
_PREFIX_TOKENS = {"team", "the"}
_SUFFIX_TOKENS = {"team", "esports", "esport", "gaming", "gg", "club"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Published alias decisions: normalised source spelling -> normalised HotSpawn spelling.
# An alias never joins on its own: the opponent AND the kickoff must also agree.
ALIASES: dict[str, tuple[str, str]] = {
    "apogee": (
        "apogeebetclic",
        "Melbet lists the opponent of UNiTY as 'Apogee Esports' in 'CS 2. Stake Ranked Closed "
        "Qualifier' at 2026-10-22T14:00:00Z; HotSpawn lists 'Apogee Betclic' in 'Stake Ranked "
        "Episode 6: Closed Qualifier' at the same kickoff with the same opponent (fixture "
        "1082882). 'Betclic' is a sponsor suffix, so the alias is applied only with the agreeing "
        "opponent and start time. Flagged for review on flagged.html.",
    ),
}


def norm(name: str | None) -> str:
    """Case/accents/punctuation-insensitive key with generic organisation words stripped."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    tokens = [t for t in re.split(r"[^a-z0-9.&]+", text) if t]
    while len(tokens) > 1 and tokens[0] in _PREFIX_TOKENS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    return _NON_ALNUM.sub("", "".join(tokens))


def canon(name: str | None) -> tuple[str, str | None]:
    key = norm(name)
    if key in ALIASES:
        return ALIASES[key][0], ALIASES[key][1]
    return key, None


def same_team(a: str | None, b: str | None) -> tuple[bool, list[str]]:
    ka, na = canon(a)
    kb, nb = canon(b)
    notes = [n for n in (na, nb) if n]
    return bool(ka) and ka == kb, notes


# ------------------------------------------------------------------------------- odds maths
def american_to_decimal(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p >= 100:
        return 1.0 + p / 100.0
    if p <= -100:
        return 1.0 + 100.0 / abs(p)
    return None


def no_vig(dec_a, dec_b) -> dict | None:
    """Proportional (multiplicative) removal of the bookmaker margin from a two-way price."""
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(da) or not math.isfinite(db) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:      # outside any plausible two-way book -> bad data
        return None
    return {"prob_a": ia / book, "prob_b": ib / book, "overround": book - 1.0}


# ---------------------------------------------------------------- Valve VRS rating model
# Valve's own code (model/glicko.js) states "rank delta of 400 points = 90% chance of victory"
# and model/fit.js evaluates expected win rates with a fixed RD of 75. Reimplemented here so the
# board does not depend on another session's module; tests cross-check the two implementations.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def vrs_prob(points_a: float, points_b: float, k: float = 1.0) -> float:
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def fit_calibration(pairs: list[dict]) -> dict:
    """Least squares of logit(market) on C * delta through the origin, with published bounds."""
    xs = [VALVE_C * float(p["delta"]) for p in pairs]
    ys = [logit(float(p["market_prob_a"])) for p in pairs]
    n = len(xs)
    out = {"n_pairs": n, "k": 1.0, "fitted": False, "k_raw": None, "min_pairs": CAL_MIN_PAIRS,
           "bounds": list(CAL_K_BOUNDS)}
    sxx = sum(x * x for x in xs)
    if n >= CAL_MIN_PAIRS and sxx > 0:
        k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
        out.update({"k_raw": k_raw, "k": min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1]),
                    "fitted": True})
    return out


def confidence_label(p_pick: float, kind: str) -> str:
    if kind == "assumption":
        return "Assumption"
    if p_pick >= 0.70:
        return "Strong"
    if p_pick >= 0.60:
        return "Solid"
    if p_pick >= 0.53:
        return "Lean"
    return "Toss-up"


# ------------------------------------------------------------------------ Kalshi exchange
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
_ZONES = {
    "EDT": "America/New_York", "EST": "America/New_York",
    "CDT": "America/Chicago", "CST": "America/Chicago",
    "MDT": "America/Denver", "MST": "America/Denver",
    "PDT": "America/Los_Angeles", "PST": "America/Los_Angeles",
}
_RULES_TIME = re.compile(
    r"scheduled for (\w{3}) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2}) (AM|PM) (\w{3,4})")


def kalshi_rules_start(rules_text: str) -> datetime | None:
    """Kickoff as *stated by the exchange itself* in rules_primary, converted to UTC.

    The exchange's ``occurrence_datetime`` field is consistently four hours later than the time
    in its own rules text for the same market (verified across all 33 open events in the retained
    payload), so it is never used as a kickoff.
    """
    m = _RULES_TIME.search(rules_text or "")
    if not m:
        return None
    mon, day, year, hour, minute, ampm, zone = m.groups()
    tzname = _ZONES.get(zone)
    if not tzname or mon not in _MONTHS:
        return None
    try:
        from zoneinfo import ZoneInfo
        h = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
        dt = datetime(int(year), _MONTHS[mon], int(day), h, int(minute), tzinfo=ZoneInfo(tzname))
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001 - a time we cannot resolve is evidence, not a crash
        return None


def _kalshi_mid(mk: dict) -> tuple[float | None, float | None]:
    def num(*keys):
        for k in keys:
            v = mk.get(k)
            if v in (None, ""):
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            return f if k.endswith("_dollars") else f / 100.0
        return None

    bid, ask = num("yes_bid_dollars", "yes_bid"), num("yes_ask_dollars", "yes_ask")
    if not bid or not ask or bid <= 0 or ask >= 1 or ask < bid:
        return None, None
    return (bid + ask) / 2.0, ask - bid


def kalshi_quotes(events: list, observed_utc: str) -> tuple[list[dict], list[dict]]:
    """Rebuild Kalshi quotes from the retained payload, keeping only usable two-sided books."""
    quotes: list[dict] = []
    rejected: list[dict] = []
    for ev in events if isinstance(events, list) else []:
        markets = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open", None)]
        if len(markets) != 2:
            continue
        names = [str(m.get("yes_sub_title") or "") for m in markets]
        mids = [_kalshi_mid(m) for m in markets]
        ticker = str(ev.get("event_ticker") or "")
        url = f"https://kalshi.com/markets/kxcs2game/{ticker.lower()}"
        start = kalshi_rules_start(str(markets[0].get("rules_primary") or ""))
        rec = {"source_key": "kalshi", "source_name": "Kalshi (exchange)", "event_id": ticker,
               "team_a": names[0], "team_b": names[1], "public_url": url,
               "rules_url": url, "title": ev.get("title"), "start_utc": to_iso(start),
               "observed_utc": observed_utc}
        if any(m[0] is None for m in mids) or any(m[1] > KALSHI_MAX_SPREAD for m in mids):
            rejected.append({**rec, "reason": "thin or one-sided order book "
                                              "(bid/ask missing or spread > 10c)"})
            continue
        if start is None:
            rejected.append({**rec, "reason": "kickoff not stated in the exchange's own rules text"})
            continue
        pa = mids[0][0] / (mids[0][0] + mids[1][0])
        quotes.append({**rec, "raw_format": "yes mid ($)",
                       "raw_a": round(mids[0][0], 4), "raw_b": round(mids[1][0], 4),
                       "decimal_a": round(1 / mids[0][0], 4), "decimal_b": round(1 / mids[1][0], 4),
                       "prob_a": pa, "prob_b": 1.0 - pa,
                       "spread_a": mids[0][1], "spread_b": mids[1][1],
                       "kickoff_source": "exchange rules_primary",
                       "time_basis": "rules_primary stated local time converted to UTC"})
    return quotes, rejected


# ------------------------------------------------------------------------------- joining
def oriented(quote: dict, swapped: bool) -> float | None:
    p = quote.get("prob_a")
    return None if p is None else (1.0 - p if swapped else p)


def match_quote(fixture: dict, quote: dict) -> dict | None:
    """Return join info when a quote prices the fixture in either orientation."""
    a_a, n1 = same_team(fixture["team_a"], quote.get("team_a"))
    b_b, n2 = same_team(fixture["team_b"], quote.get("team_b"))
    a_b, n3 = same_team(fixture["team_a"], quote.get("team_b"))
    b_a, n4 = same_team(fixture["team_b"], quote.get("team_a"))
    if a_a and b_b:
        swapped, notes = False, n1 + n2
    elif a_b and b_a:
        swapped, notes = True, n3 + n4
    else:
        return None
    diff = hours_apart(parse_iso(fixture.get("start_utc")), parse_iso(quote.get("start_utc")))
    if diff is None:
        return {"rejected": True, "swapped": swapped, "alias_notes": notes,
                "start_diff_h": None, "reason": "kickoff not established"}
    if diff > TIME_TOLERANCE_H:
        return {"rejected": True, "swapped": swapped, "alias_notes": notes,
                "start_diff_h": diff, "reason": "kickoff differs by more than five minutes"}
    return {"swapped": swapped, "alias_notes": notes, "start_diff_h": diff}


def consensus(entries: list[dict]) -> dict:
    usable = [e for e in entries if isinstance(e.get("prob_a"), float)]
    wsum = sum(SOURCE_WEIGHTS.get(e["source_key"], 1.0) for e in usable)
    pa = sum(SOURCE_WEIGHTS.get(e["source_key"], 1.0) * e["prob_a"] for e in usable) / wsum
    spread = max(e["prob_a"] for e in usable) - min(e["prob_a"] for e in usable)
    return {"prob_a": pa, "prob_b": 1.0 - pa, "n_sources": len(usable),
            "sources": sorted({str(e["source_key"]) for e in usable}),
            "spread_a": spread if len(usable) > 1 else None}


# ------------------------------------------------------------------------------- VRS rows
def roster_size(row: dict) -> int:
    return len([p for p in re.split(r",", str(row.get("roster") or "")) if p.strip()])


def choose_rating(candidates: list[dict]) -> tuple[dict | None, dict]:
    """Pick the active roster row for an organisation from duplicate official VRS entries.

    Evidence used (all from Valve's own table and details files): exactly five listed players, and
    the newest counted match date in the roster's details file. The decision is returned so the
    board can publish it; when the evidence does not separate the candidates nothing is chosen.
    """
    detail = {"candidates": [{k: c.get(k) for k in ("standing", "points", "team", "roster",
                                                    "latest_match_date", "n_matches")}
                             for c in candidates]}
    if not candidates:
        return None, {"decision": "no_rating"}
    if len(candidates) == 1:
        row = candidates[0]
        if row.get("n_matches") == 0:
            return None, {"decision": "unverified_no_counted_matches", **detail}
        return row, {"decision": "single_entry", **detail}
    full = [c for c in candidates if roster_size(c) == 5]
    if not full:
        return None, {"decision": "unverified_no_five_player_roster", **detail}
    dated = [c for c in full if c.get("latest_match_date")]
    if not dated:
        return None, {"decision": "unverified_no_counted_match_date", **detail}
    dated.sort(key=lambda c: (str(c["latest_match_date"]), int(c.get("n_matches") or 0)), reverse=True)
    top, second = dated[0], (dated[1] if len(dated) > 1 else None)
    if second and str(second.get("latest_match_date")) == str(top.get("latest_match_date")) \
            and int(second.get("n_matches") or 0) == int(top.get("n_matches") or 0):
        return None, {"decision": "unverified_tie", **detail}
    detail["decision"] = "active_roster_by_newest_counted_match"
    detail["chosen"] = top.get("standing")
    detail["rejected"] = [c.get("standing") for c in candidates if c is not top]
    return top, detail


def rating_candidates(vrs: dict, name: str) -> list[dict]:
    teams = (vrs or {}).get("teams") or []
    key = canon(name)[0]
    return [t for t in teams if canon(t.get("team"))[0] == key]


# ------------------------------------------------------------------------------- resolution
def _evidence_price(quote: dict, swapped: bool, fixture: dict) -> dict:
    pa = oriented(quote, swapped)
    return {"source_key": quote.get("source_key"), "source_name": quote.get("source_name"),
            "swapped": bool(swapped),
            "url": quote.get("public_url") or quote.get("rules_url"),
            "api_url": quote.get("api_url"), "event_id": quote.get("event_id"),
            "names_at_source": [quote.get("team_a"), quote.get("team_b")],
            "start_utc": quote.get("start_utc"), "start_diff_min": round(
                (hours_apart(parse_iso(fixture.get("start_utc")),
                             parse_iso(quote.get("start_utc"))) or 0) * 60, 1),
            "raw": [quote.get("raw_a"), quote.get("raw_b")],
            "raw_format": quote.get("raw_format"),
            "prob_a": round(pa, 4) if pa is not None else None,
            "observed_utc": quote.get("observed_utc") or quote.get("retrieved_utc"),
            "time_basis": quote.get("time_basis") or "source event start time",
            "alias_notes": []}


def resolve_fixture(fixture: dict, quotes: list[dict], vrs: dict, cal: dict,
                    vrs_floor: dict, vrs_median: float) -> dict:
    k = float(cal.get("k") or 1.0)
    row = {
        "fixture_id": str(fixture.get("fixture_id")),
        "competition": fixture.get("competition"),
        "tier": fixture.get("tier"),
        "start_utc": fixture.get("start_utc"),
        "lock_utc": fixture.get("lock_utc"),
        "team_a": fixture.get("team_a"),
        "team_b": fixture.get("team_b"),
        "hotspawn_url": fixture.get("hotspawn_url"),
        "points": fixture.get("points"),
        "tier_code": "unresolved",
        "tier_label": "Unresolved",
        "pick": None,
        "prob_a": None, "prob_b": None,
        "prob_range_a": None,
        "confidence": None,
        "verified": False,
        "evidence": [],
        "vrs": {},
        "flags": [],
        "limitations": [],
        "basis_text": "",
        "joined": [],
        "rejected_joins": [],
    }
    for quote in quotes:
        info = match_quote(fixture, quote)
        if not info:
            continue
        if info.get("rejected"):
            row["rejected_joins"].append({
                "source_key": quote.get("source_key"),
                "url": quote.get("public_url") or quote.get("rules_url"),
                "names_at_source": [quote.get("team_a"), quote.get("team_b")],
                "start_utc": quote.get("start_utc"),
                "reason": info.get("reason"),
                "diff_min": round(info["start_diff_h"] * 60, 1) if info.get("start_diff_h") else None,
            })
            row["flags"].append(f"price_rejected:{quote.get('source_key')}")
            continue
        ev = _evidence_price(quote, bool(info.get("swapped")), fixture)
        ev["alias_notes"] = info.get("alias_notes") or []
        if ev["alias_notes"]:
            row["flags"].append("alias_joined:" + str(quote.get("source_key")))
        row["joined"].append({**ev, "swapped": bool(info.get("swapped")),
                              "spread": quote.get("spread_a")})
        if quote.get("source_key") == "kalshi":
            row["flags"].append("exchange_quote_time_from_rules")
    for alias_note in sorted({n for e in row["joined"] for n in e["alias_notes"]}):
        row["limitations"].append(alias_note)

    # ---------------------------------------------------------------- 1/2: external prices
    if row["joined"]:
        market = consensus(row["joined"])
        row["prob_a"], row["prob_b"] = round(market["prob_a"], 4), round(market["prob_b"], 4)
        row["tier_code"] = "market_multi" if market["n_sources"] > 1 else "market_single"
        row["tier_label"] = ("Bookmaker consensus" if market["n_sources"] > 1
                             else "Single bookmaker line")
        row["verified"] = True
        row["evidence"] = [{kk: e[kk] for kk in ("source_name", "url", "api_url", "event_id",
                                                 "names_at_source", "start_utc", "raw",
                                                 "raw_format", "prob_a", "observed_utc",
                                                 "alias_notes", "time_basis", "start_diff_min",
                                                 "swapped")}
                           for e in row["joined"]]
        sources = ", ".join(market["sources"])
        if market["n_sources"] == 1 and row["joined"][0]["source_key"] == "kalshi":
            row["tier_code"], row["tier_label"] = "exchange", "Kalshi exchange"
            row["basis_text"] = (
                "Kalshi order-book mid (bid/ask both sides inside the 10¢ spread gate), at the "
                "kickoff stated in the exchange's own rules text.")
        else:
            row["basis_text"] = (
                f"De-vigged mean of {market['n_sources']} external two-way price(s) "
                f"({sources}); Pinnacle is weighted 2×, every other source 1×."
                if market["n_sources"] > 1 else
                f"De-vigged two-way price from {sources} (the only external price that priced "
                "this fixture at capture).")
        if market["spread_a"] is not None:
            row["flags"].append(f"book_spread_{market['spread_a'] * 100:.1f}pp")
            if market["spread_a"] > 0.05:
                row["limitations"].append(
                    f"The joined prices disagree by {market['spread_a'] * 100:.1f} percentage "
                    "points; the consensus is an average, not a single book's opinion.")
    else:
        # ------------------------------------------------------------ 3/4/5: ratings
        rating_a, info_a = choose_rating(rating_candidates(vrs, fixture["team_a"]))
        rating_b, info_b = choose_rating(rating_candidates(vrs, fixture["team_b"]))
        row["vrs"] = {
            "snapshot": (vrs or {}).get("snapshot"),
            "page_url": (vrs or {}).get("page_url"),
            "team_a": ({**rating_a, "decision": info_a.get("decision")} if rating_a
                       else {"decision": info_a.get("decision"), "candidates": info_a.get("candidates")}),
            "team_b": ({**rating_b, "decision": info_b.get("decision")} if rating_b
                       else {"decision": info_b.get("decision"), "candidates": info_b.get("candidates")}),
            "k": round(k, 4),
        }
        for side, rating, info in (("a", rating_a, info_a), ("b", rating_b, info_b)):
            name = fixture["team_a"] if side == "a" else fixture["team_b"]
            if rating and info.get("decision") == "active_roster_by_newest_counted_match":
                row["flags"].append(f"vrs_duplicate_resolved:{side}")
                row["limitations"].append(
                    f"Valve lists {rating['n_matches']} counted matches for the chosen "
                    f"{name} roster (#{rating['standing']}, latest {rating['latest_match_date']}); "
                    f"duplicate entries #{', #'.join(str(x) for x in info.get('rejected') or [])} "
                    "were rejected on roster size and match recency.")
            if not rating:
                row["flags"].append(f"not_in_vrs:{name}")
        if rating_a and rating_b:
            pa = vrs_prob(rating_a["points"], rating_b["points"], k)
            row["prob_a"], row["prob_b"] = round(pa, 4), round(1 - pa, 4)
            row["tier_code"], row["tier_label"] = "vrs_model", "Official VRS model"
            row["verified"] = False
            row["evidence"] = [
                {"source_name": "Valve Regional Standings (official)",
                 "url": (vrs or {}).get("page_url"),
                 "detail": f"{fixture['team_a']} #{rating_a['standing']} ({rating_a['points']} pts), "
                           f"{fixture['team_b']} #{rating_b['standing']} ({rating_b['points']} pts)"},
                {"source_name": "Valve roster details (official)",
                 "url": VRS_BLOB + str(rating_a.get("details_path")),
                 "detail": f"{rating_a['team']} roster {rating_a.get('roster')}"},
                {"source_name": "Valve roster details (official)",
                 "url": VRS_BLOB + str(rating_b.get("details_path")),
                 "detail": f"{rating_b['team']} roster {rating_b.get('roster')}"},
            ]
            row["basis_text"] = (
                "No external price found. Originated from the official Valve VRS points "
                f"difference (Δ = {rating_a['points'] - rating_b['points']:+d}) with the slope "
                f"k = {k:.4f} fitted on {cal.get('n_pairs')} priced fixtures.")
            row["limitations"].append(
                "This is an originated model line, not a bookmaker price: no external two-way "
                "market priced this fixture in the capture.")
            if (vrs or {}).get("snapshot"):
                row["limitations"].append(
                    f"Valve's newest published standings snapshot is {(vrs or {}).get('snapshot')}; "
                    "it is the most recent official file (verified against Valve's repository "
                    "tree), so ratings can lag recent results.")
        elif rating_a or rating_b:
            rated_side = "a" if rating_a else "b"
            rated = rating_a or rating_b
            opponent = fixture["team_b"] if rated_side == "a" else fixture["team_a"]
            opponent_info = info_b if rated_side == "a" else info_a
            points = float(rated["points"])
            p_floor = vrs_prob(points, float(vrs_floor["points"]), k)
            p_median = vrs_prob(points, float(vrs_median), k)
            lo, hi = sorted((p_floor, p_median))
            # Headline = midpoint of the two documented assumptions (not the most favourable one),
            # with both bounds published next to it.
            mid = (lo + hi) / 2.0
            pa = mid if rated_side == "a" else 1 - mid
            row["prob_a"], row["prob_b"] = round(pa, 4), round(1 - pa, 4)
            row["prob_range_a"] = [round(lo, 4), round(hi, 4)]
            row["tier_code"], row["tier_label"] = "assumption", "Assumption (opponent unrated)"
            row["verified"] = False
            row["evidence"] = [
                {"source_name": "Valve Regional Standings (official)",
                 "url": (vrs or {}).get("page_url"),
                 "detail": f"{rated['team']} #{rated['standing']} ({rated['points']} pts)"},
                {"source_name": "Valve roster details (official)",
                 "url": VRS_BLOB + str(rated.get("details_path")),
                 "detail": f"{rated['team']} roster {rated.get('roster')}"},
            ]
            row["basis_text"] = (
                f"{opponent} is not in Valve's official standings table, so it has no rating. "
                f"The pick is the rated side ({rated['team']}); the probability is a range between "
                f"two documented assumptions for the unrated side: the official VRS floor "
                f"(#{vrs_floor['standing']}, {vrs_floor['points']} pts) and the VRS median "
                f"({vrs_median:.0f} pts over {(vrs or {}).get('n_teams')} ranked teams).")
            row["flags"].append("unrated_opponent")
            row["limitations"].append(
                f"{opponent} has no official rating ({opponent_info.get('decision')}); no "
                "bookmaker or exchange priced this fixture, so no verified probability exists. "
                "The published number is an assumption, not evidence.")
            row["limitations"].append(
                "Unrated does not mean weak: in this same capture UNiTY (VRS #69) is priced at "
                "only 39.5% against unrated Apogee Betclic, so an unrated opponent can be the "
                "favourite. Treat this row as directional only.")
        else:
            row["evidence"] = []
            row["basis_text"] = ("Neither roster is in Valve's official standings table and no "
                                 "external two-way price priced this fixture.")
            row["flags"].append("no_rating_and_no_price")
            row["limitations"].append(
                "Nothing verifiable prices this fixture: no bookmaker/exchange line and no "
                "official Valve rating for either team. Values are left blank.")

    if row["prob_a"] is not None:
        side = "a" if row["prob_a"] >= row["prob_b"] else "b"
        pick_team = fixture["team_a"] if side == "a" else fixture["team_b"]
        pick_prob = row["prob_a"] if side == "a" else row["prob_b"]
        row["pick"] = {"side": side, "team": pick_team, "prob": round(pick_prob, 4),
                       "confidence": confidence_label(pick_prob, row["tier_code"]),
                       "kind": ("verified" if row["verified"] else
                                ("assumption" if row["tier_code"] == "assumption" else "originated"))}
        if row["prob_range_a"]:
            lo, hi = row["prob_range_a"]
            side_lo, side_hi = (lo, hi) if side == "a" else (1 - hi, 1 - lo)
            row["pick"]["range"] = [round(side_lo, 4), round(side_hi, 4)]
    return row


# ------------------------------------------------------------------------------- summary
def summarize(rows: list[dict]) -> dict:
    def count(code):
        return sum(1 for r in rows if r["tier_code"] == code)

    verified = [r for r in rows if r["verified"]]
    assumption = [r for r in rows if r["tier_code"] == "assumption"]
    unresolved = [r for r in rows if r["tier_code"] == "unresolved"]
    return {
        "open": len(rows),
        "with_pick": sum(1 for r in rows if r["pick"]),
        "market_multi": count("market_multi"),
        "market_single": count("market_single"),
        "exchange": count("exchange"),
        "vrs_model": count("vrs_model"),
        "assumption": count("assumption"),
        "unresolved": count("unresolved"),
        "verified_picks": len(verified),
        "assumption_picks": len(assumption),
        "verified_share": round(len(verified) / len(rows), 4) if rows else None,
        "with_pick_share": round(sum(1 for r in rows if r["pick"]) / len(rows), 4) if rows else None,
    }


def vrs_stats(vrs: dict) -> dict:
    points = sorted(int(t["points"]) for t in (vrs or {}).get("teams") or [])
    if not points:
        return {}
    return {"n_teams": len(points), "min": points[0], "median": statistics.median(points),
            "max": points[-1],
            "floor": (vrs or {}).get("floor") or {"standing": len(points),
                                                  "points": points[0]}}
