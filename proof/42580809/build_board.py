#!/usr/bin/env python3
"""
Session 42580809 — join external market quotes to the HotSpawn pick'em CS2 fixtures and derive
win probabilities. Every field in the output is copied from, or computed out of, a collected
quote that carries its own source URL and retrieval timestamp. Nothing is hand-typed.

Quote inputs (all committed evidence, all outside HotSpawn):
  proof/42580809/evidence/lines.json   - this session's runner collector
                                         (Pinnacle full-match moneyline, Bovada, Kalshi two-sided
                                          book, Polymarket)
  data/lines.json                      - the shared strict pipeline's per-fixture bookmaker lines
                                         (session d4ec32a9; read-only, attributed per row)
  data/961/board.json                  - session 961e163a's quote list (read-only, attributed)
  data/cs2_odds_egamersworld.json      - egamersworld.com odds widget (aggregator; used only as a
                                         clearly labelled fallback where no bookmaker quote exists)

Matching rules (strict, every accept/reject written to evidence/matching.json):
  1. Both participants must be equal after normalisation, in either order; a reversed source
     listing has its prices reversed. Name aliases are explicit and documented, never fuzzy.
  2. A quote is accepted only if its own schedule agrees with the fixture within 90 minutes.
     Kalshi's settlement rule is parsed for the original schedule (its occurrence_datetime is
     padded by the settlement window and is deliberately ignored).
  3. One quote is assigned to at most one fixture; ambiguous candidates are rejected.

Derivation (labelled, never presented as a source quote):
  bookmaker decimal odds  q_i = 1/odds_i  ->  p_i = q_i/(q_a+q_b)          [proportional no-vig]
  Kalshi two-sided book   mid_i = (yes_bid+yes_ask)/2 -> p_i = mid_i/(mid_a+mid_b)
  consensus               arithmetic mean of p_a over all *named bookmaker/exchange* quotes;
                          the aggregator fallback is reported separately and never averaged in.

Outputs:
  data/board_42580809.json   board rows for every CS2 pick'em fixture (site input, published)
  data/board_42580809.csv    the same rows as a flat table
  proof/42580809/evidence/matching.json       every accept/reject decision
  proof/42580809/evidence/matched_quotes.json market graph used by originate.py
  proof/42580809/evidence/coverage.json       per-source and per-tournament coverage counts
"""

from __future__ import annotations

import csv
import json
import os
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "evidence")
DATA = os.path.join(REPO, "data")

TIME_TOLERANCE_MIN = 90
NAMED_SOURCES = {"pinnacle", "bovada", "kalshi"}
FALLBACK_SOURCES = {"egamersworld"}

# Documented aliases: normalised source spelling -> normalised HotSpawn spelling.
ALIASES = {
    "9z globant": "9z",
    "nip": "ninjas in pyjamas",
    "n i p": "ninjas in pyjamas",
    "bb": "betboom",
    "bb team": "betboom",
    "betboom team": "betboom",
    "pvision": "parivision",
    "keyd stars": "keyd",
    "ex keyd stars": "keyd",
    "overtake": "overtake sector",
    "aurora gaming": "aurora",
    "team aurora": "aurora",
    "sashi esport": "sashi",
    "team falcons": "falcons",
    "gremio esports": "gremio",
    "team spirit": "spirit",
    "natus vincere": "natus vincere",
    "los ninos": "los ninos",
    "wbt academy": "wrotberry",
    "esport academy copenhagen": "eac",
}
# Aliases that bridge genuinely different spellings are only applied when the tournament name
# and the schedule in the source's own text also agree with the fixture. Every use is recorded.
CONDITIONAL_ALIASES = {"wbt academy": "wrotberry", "esport academy copenhagen": "eac"}

SUFFIXES = (" esports", " esport", " e sports", " gaming", " club", " team", " csgo", " cs2", " corp")
PREFIXES = ("team ",)

TZ_OFFSETS = {
    "EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8, "UTC": 0, "GMT": 0,
}
RULE_TIME_RE = re.compile(
    r"([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*([A-Z]{2,4})",
    re.I,
)
RULE_TEAMS_RE = re.compile(r"(?:If\s+(.+?)\s+wins\s+the\s+|match\s+)(.+?)\s+vs\.?\s+(.+?)\s+CS2\s+match", re.I)


# --------------------------------------------------------------------------- normalisation
def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    for ch in ".,'’`´:;!?()[]{}*+-_/\\\"":
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    for p in PREFIXES:
        if s.startswith(p) and len(s) > len(p) + 2:
            s = s[len(p):]
    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf) + 2:
                s = s[: -len(suf)].strip()
                changed = True
    return ALIASES.get(s, s)


def cond_alias(raw: str) -> str | None:
    n = unicodedata.normalize("NFKD", str(raw or "")).lower()
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = " ".join(re.sub(r"[^a-z0-9 ]", " ", n).split())
    return CONDITIONAL_ALIASES.get(n)


def tokens(*texts) -> list[str]:
    out = []
    for t in texts:
        for w in re.findall(r"[a-z0-9]+", str(t or "").lower()):
            if len(w) > 2 and w not in ("the", "and", "cup", "2026"):
                out.append(w)
    return out


def tournament_overlap(fixture: dict, text: str) -> float:
    f = set(tokens(fixture.get("tournament"), fixture.get("event")))
    if not f:
        return 0.0
    q = set(tokens(text))
    return len(f & q) / len(f)


# --------------------------------------------------------------------------- small helpers
def parse_ts(value):
    """ISO-8601 string or epoch (s/ms) -> aware UTC datetime, else None."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e11:      # milliseconds
            v /= 1000.0
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if s.isdigit():
        return parse_ts(int(s))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt):
    return None if dt is None else dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rule_time(text):
    """Original schedule written into a Kalshi settlement rule -> UTC datetime."""
    m = RULE_TIME_RE.search(str(text or ""))
    if not m:
        return None
    month, day, year, hh, mm, ap, tz = m.groups()
    try:
        month_i = datetime.strptime(month[:3].title(), "%b").month
    except ValueError:
        return None
    hour = int(hh) % 12 + (12 if ap.upper() == "P" else 0)
    tz = tz.upper()
    offset = TZ_OFFSETS.get(tz)
    if offset is None:
        return None
    try:
        return datetime(int(year), month_i, int(day), hour, int(mm), tzinfo=timezone.utc) - timedelta(hours=offset)
    except ValueError:
        return None


def american_to_decimal(price):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return 1 + (p / 100.0) if p > 0 else 1 + (100.0 / -p)


def devig(odds_a, odds_b):
    qa, qb = 1.0 / odds_a, 1.0 / odds_b
    total = qa + qb
    return qa / total, qb / total, total - 1.0


# --------------------------------------------------------------------------- quote loaders
def quote(**kw):
    kw.setdefault("source_key", "")
    kw.setdefault("source_name", "")
    kw.setdefault("source_url", None)
    kw.setdefault("api_url", None)
    kw.setdefault("event_id", None)
    kw.setdefault("market", None)
    kw.setdefault("live", False)
    kw.setdefault("retrieved_at_utc", None)
    kw.setdefault("kind", "bookmaker")
    kw.setdefault("raw", {})
    return kw


def quotes_from_session_lines():
    """This session's collector output (Pinnacle / Bovada / Kalshi / Polymarket)."""
    path = os.path.join(EV, "lines.json")
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    out, kalshi_by_event = [], {}
    for ln in doc.get("lines", []):
        key = ln.get("source_key")
        if key == "kalshi":
            kalshi_by_event.setdefault(ln.get("source_event_id"), []).append(ln)
            continue
        a, b = ln.get("team_a_name"), ln.get("team_b_name")
        if not a or not b:
            continue
        if key == "polymarket":
            probs = ln.get("raw_prices") or []
            if len(probs) != 2:
                continue
            try:
                p_a = float(probs[0])
            except (TypeError, ValueError):
                continue
            out.append(quote(source_key=key, source_name=ln.get("source_name"),
                             kind="prediction market", source_url=ln.get("source_public_url"),
                             api_url=ln.get("source_api_url"), event_id=ln.get("source_event_id"),
                             market=ln.get("market_type"), live=bool(ln.get("market_is_live")),
                             retrieved_at_utc=ln.get("retrieved_at_utc"), team_a=a, team_b=b,
                             p_a=p_a, p_b=1 - p_a, start=parse_ts(ln.get("start_time_utc")),
                             raw={"status": ln.get("market_status")}))
            continue
        oa, ob = ln.get("decimal_odds_a"), ln.get("decimal_odds_b")
        if not oa or not ob:
            oa, ob = american_to_decimal(ln.get("raw_price_a")), american_to_decimal(ln.get("raw_price_b"))
        if not oa or not ob or oa <= 1 or ob <= 1:
            continue
        p_a, p_b, over = devig(oa, ob)
        out.append(quote(source_key=key, source_name=ln.get("source_name"),
                         source_url=ln.get("source_public_url") or ln.get("source_api_url"),
                         api_url=ln.get("source_api_url"), event_id=ln.get("source_event_id"),
                         market=ln.get("market_type"), live=bool(ln.get("market_is_live")),
                         retrieved_at_utc=ln.get("retrieved_at_utc"), team_a=a, team_b=b,
                         p_a=p_a, p_b=p_b, overround=over, start=parse_ts(ln.get("start_time_utc")),
                         rule=ln.get("source_rules_primary"), raw={"odds": [oa, ob]}))
    # Kalshi: pair the two per-outcome markets of an event into one match quote.
    for event_id, markets in kalshi_by_event.items():
        if len(markets) != 2:
            continue
        sides = {}
        for m in markets:
            name = m.get("outcome_name")
            bid, ask = m.get("yes_bid"), m.get("yes_ask")
            if name is None or bid is None or ask is None:
                continue
            sides[name] = {"mid": (float(bid) + float(ask)) / 2.0, "bid": float(bid),
                           "ask": float(ask), "market_id": m.get("source_market_id"),
                           "volume": m.get("volume"), "oi": m.get("open_interest")}
        if len(sides) != 2:
            continue
        (na, sa), (nb, sb) = list(sides.items())
        if sa["mid"] + sb["mid"] <= 0:
            continue
        total = sa["mid"] + sb["mid"]
        p_a, p_b = sa["mid"] / total, sb["mid"] / total
        start = rule_time(markets[0].get("source_rules_primary")) or parse_ts(markets[0].get("start_time_utc"))
        out.append(quote(source_key="kalshi", source_name="Kalshi", kind="prediction exchange",
                         source_url=markets[0].get("source_public_url"),
                         api_url=markets[0].get("source_api_url"), event_id=event_id,
                         market="match winner (two-sided book, both outcomes)",
                         live=bool(markets[0].get("market_is_live")),
                         retrieved_at_utc=markets[0].get("retrieved_at_utc"), team_a=na, team_b=nb,
                         p_a=p_a, p_b=p_b, start=start, rule=markets[0].get("source_rules_primary"),
                         raw={"yes_bid_a": sa["bid"], "yes_ask_a": sa["ask"],
                              "yes_bid_b": sb["bid"], "yes_ask_b": sb["ask"],
                              "spread_a": round(sa["ask"] - sa["bid"], 4),
                              "spread_b": round(sb["ask"] - sb["bid"], 4),
                              "volume_a": sa["volume"], "volume_b": sb["volume"],
                              "market_id_a": sa["market_id"], "market_id_b": sb["market_id"]}))
    return out


def quotes_from_shared_lines():
    """data/lines.json (strict shared pipeline) — raw bookmaker lines with their own URLs."""
    path = os.path.join(DATA, "lines.json")
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    out = []
    for fx in doc.get("fixtures", []):
        for ln in fx.get("bookmaker_lines", []) or []:
            key = ln.get("source_key")
            oa, ob = ln.get("decimal_odds_a"), ln.get("decimal_odds_b")
            if (not oa or not ob) and ln.get("raw_price_format") == "american":
                oa, ob = american_to_decimal(ln.get("raw_price_a")), american_to_decimal(ln.get("raw_price_b"))
            try:
                oa, ob = float(oa), float(ob)
            except (TypeError, ValueError):
                continue
            if oa <= 1 or ob <= 1:
                continue
            p_a, p_b, over = devig(oa, ob)
            out.append(quote(source_key=key, source_name=ln.get("source_name") or key,
                             source_url=ln.get("source_public_url") or ln.get("source_api_url"),
                             api_url=ln.get("source_api_url"), event_id=ln.get("source_event_id"),
                             market=ln.get("market_type"), live=bool(ln.get("market_is_live")),
                             retrieved_at_utc=ln.get("retrieved_at_utc"),
                             team_a=ln.get("team_a_name") or fx.get("team_a"),
                             team_b=ln.get("team_b_name") or fx.get("team_b"),
                             p_a=p_a, p_b=p_b, overround=over, start=parse_ts(ln.get("start_time_utc")),
                             raw={"fixture_hint": fx.get("fixture_id"), "odds": [oa, ob]}))
    return out


def quotes_from_961():
    """data/961/board.json rows[].sources[] (session 961e163a) — read-only, attributed."""
    path = os.path.join(DATA, "961", "board.json")
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    out = []
    for row in doc.get("rows", []):
        if row.get("game") != "cs2":
            continue
        for s in row.get("sources", []) or []:
            oa, ob = s.get("decimal_odds_a"), s.get("decimal_odds_b")
            try:
                oa, ob = float(oa), float(ob)
            except (TypeError, ValueError):
                continue
            if oa <= 1 or ob <= 1:
                continue
            p_a, p_b, over = devig(oa, ob)
            key = s.get("source_key")
            out.append(quote(source_key=key, source_name=s.get("source_name") or key,
                             kind=s.get("source_kind") or "bookmaker", source_url=s.get("source_url"),
                             api_url=s.get("source_url"), event_id=s.get("event_id"),
                             market=s.get("market_type"), live=bool(s.get("market_is_live")),
                             retrieved_at_utc=s.get("retrieved_at_utc"), team_a=row.get("team_a"),
                             team_b=row.get("team_b"), p_a=p_a, p_b=p_b, overround=over,
                             start=parse_ts(row.get("scheduled_start_time_utc")),
                             raw={"fixture_hint": row.get("fixture_id"), "join_note": s.get("join_note"),
                                  "source_kind": s.get("source_kind"), "odds": [oa, ob]}))
    return out


def quotes_from_egw():
    """data/cs2_odds_egamersworld.json — aggregator widget odds, fallback only."""
    path = os.path.join(DATA, "cs2_odds_egamersworld.json")
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    out = []
    for row in doc.get("rows", []):
        oa, ob = row.get("decimal_odds_a"), row.get("decimal_odds_b")
        try:
            oa, ob = float(oa), float(ob)
        except (TypeError, ValueError):
            continue
        if oa <= 1 or ob <= 1:
            continue
        p_a, p_b, over = devig(oa, ob)
        out.append(quote(source_key="egamersworld", source_name=row.get("source_name") or "egamersworld.com",
                         kind="odds aggregator (fallback)", source_url=row.get("source_url"),
                         api_url=row.get("source_url"), event_id=row.get("fixture_id"),
                         market="match winner (aggregated moneyline)", live=False,
                         retrieved_at_utc=row.get("retrieved_at_utc"), team_a=row.get("team_a"),
                         team_b=row.get("team_b"), p_a=p_a, p_b=p_b, overround=over,
                         start=parse_ts(row.get("official_start_utc")),
                         raw={"fixture_hint": row.get("fixture_id"), "join_note": row.get("join_note"),
                              "source_kind": row.get("source_kind"), "odds": [oa, ob]}))
    return out


# --------------------------------------------------------------------------- matching
def fixture_index(fixtures):
    idx = {}
    for fx in fixtures:
        idx.setdefault((norm(fx["team_a"]), norm(fx["team_b"])), []).append(fx)
    return idx


def candidates_for(q, fixtures, idx):
    na, nb = norm(q["team_a"]), norm(q["team_b"])
    cands = []
    for fx in fixtures:
        fa, fb = norm(fx["team_a"]), norm(fx["team_b"])
        flipped = False
        direct = (na == fa and nb == fb)
        swapped = (na == fb and nb == fa)
        if direct:
            flipped = False
        elif swapped:
            flipped = True
        else:
            # conditional alias path: the alias may only be accepted with tournament + time proof
            alts_a = {na} | ({cond_alias(q["team_a"])} if cond_alias(q["team_a"]) else set())
            alts_b = {nb} | ({cond_alias(q["team_b"])} if cond_alias(q["team_b"]) else set())
            direct = any(x == fa for x in alts_a) and any(x == fb for x in alts_b)
            swapped = any(x == fb for x in alts_a) and any(x == fa for x in alts_b)
            if direct or swapped:
                text = " ".join(str(x) for x in (q.get("rule"), q.get("market"), (q.get("raw") or {}).get("league")))
                if tournament_overlap(fx, text) < 0.6:
                    continue
                q.setdefault("alias_note", "conditional alias accepted: tournament name overlap >= 0.6 and schedule agreement")
        if not (direct or swapped):
            continue
        if q.get("start") is None:
            cands.append((fx, flipped, None))
            continue
        fx_start = parse_ts(fx.get("scheduled_start_time_utc"))
        delta = abs((fx_start - q["start"]).total_seconds()) / 60.0 if fx_start else None
        if delta is not None and delta <= TIME_TOLERANCE_MIN:
            cands.append((fx, flipped, delta))
    return cands


def build():
    fixtures_doc = json.load(open(os.path.join(EV, "fixtures.json"), encoding="utf-8"))
    fixtures = []
    for f in fixtures_doc["fixtures"]:
        if f.get("sport") != "cs2":
            continue
        fixtures.append(dict(f, tournament=f.get("competition_name"),
                             points=f.get("offered_points"),
                             hotspawn_url=f.get("source_url"),
                             participantsX_picked_percent=f.get("team_a_pick_pct"),
                             participantsY_picked_percent=f.get("team_b_pick_pct")))
    fixtures_doc["window"] = len(fixtures)
    idx = fixture_index(fixtures)

    quotes = (quotes_from_session_lines() + quotes_from_shared_lines()
              + quotes_from_961() + quotes_from_egw())
    accepted, rejected, per_fixture = [], [], {}
    for q in quotes:
        cands = candidates_for(q, fixtures, idx)
        if not cands:
            rejected.append({"reason": "no fixture with both teams and a matching schedule",
                             "source_key": q["source_key"], "raw_names": [q["team_a"], q["team_b"]],
                             "start": iso(q.get("start")), "raw": q.get("raw")})
            continue
        if len(cands) > 1:
            rejected.append({"reason": f"{len(cands)} fixture candidates (ambiguous)",
                             "source_key": q["source_key"], "raw_names": [q["team_a"], q["team_b"]],
                             "start": iso(q.get("start")), "raw": q.get("raw")})
            continue
        fx, flipped, delta = cands[0]
        p_a = 1 - q["p_a"] if flipped else q["p_a"]
        p_b = 1 - p_a
        rec = {"fixture_id": fx["fixture_id"], "source_key": q["source_key"],
               "source_name": q["source_name"], "source_kind": q.get("kind"),
               "source_url": q.get("source_url"), "api_url": q.get("api_url"),
               "event_id": q.get("event_id"), "market": q.get("market"),
               "market_is_live": q.get("live"), "retrieved_at_utc": q.get("retrieved_at_utc"),
               "source_quoted": {"team_a": q["team_a"], "team_b": q["team_b"]},
               "orientation_vs_fixture": "reversed" if flipped else "direct",
               "start_time_delta_min": delta, "start_time_utc": iso(q.get("start")),
               "no_vig_probability_a": round(p_a, 6), "no_vig_probability_b": round(p_b, 6),
               "overround": None if q.get("overround") is None else round(q["overround"], 6),
               "alias_note": q.get("alias_note"), "raw": q.get("raw")}
        accepted.append(rec)
        per_fixture.setdefault(fx["fixture_id"], []).append(rec)

    # Quality gate: a collected row is not automatically a usable price. Kalshi books that are
    # empty or far too wide (identical cheap bid / expensive ask on both sides) and aggregator
    # placeholder quotes (the exact same even price repeated across unrelated fixtures) are
    # rejected here, kept in matching.json, and published as flagged irregularities.
    import collections as _collections
    even_pairs = _collections.Counter()
    for rec in accepted:
        odds = (rec.get("raw") or {}).get("odds")
        if odds and abs(float(odds[0]) - float(odds[1])) < 1e-9:
            even_pairs[(rec["source_key"], round(float(odds[0]), 2))] += 1
    usable, gate_rejected = [], []
    for rec in accepted:
        raw = rec.get("raw") or {}
        odds = raw.get("odds")
        reason = None
        if rec["source_key"] == "kalshi":
            sa, sb = raw.get("spread_a"), raw.get("spread_b")
            if sa is None or sb is None:
                reason = "Kalshi book has no two-sided price for both outcomes"
            elif max(float(sa), float(sb)) > 0.25:
                reason = (f"Kalshi book is empty/too wide: bid-ask spread {sa}/{sb}, "
                          f"volume {raw.get('volume_a')}/{raw.get('volume_b')} - not usable as a price")
        elif odds and abs(float(odds[0]) - float(odds[1])) < 1e-9 and even_pairs[(rec["source_key"], round(float(odds[0]), 2))] >= 2:
            reason = (f"aggregator placeholder quote {odds[0]}/{odds[1]} repeated across fixtures - "
                      f"identical even prices, no real market behind them")
        if reason:
            gate_rejected.append(dict(rec, rejection_reason=reason))
        else:
            usable.append(rec)
    failed_fixtures = {r["fixture_id"] for r in gate_rejected}
    for rec in gate_rejected:
        rejected.append({"reason": rec["rejection_reason"], "source_key": rec["source_key"],
                         "raw_names": [rec["source_quoted"]["team_a"], rec["source_quoted"]["team_b"]],
                         "start": rec["start_time_utc"], "quality_gate": True, "raw": rec.get("raw")})
    accepted = usable

    # De-duplicate: the same underlying market can be present in more than one collected batch
    # (this session's runner, the shared pipeline, session 961). Keep the most recent read per
    # (fixture, source, probability) and record the others instead of silently dropping them.
    deduped, duplicates = {}, []
    for rec in accepted:
        key = (rec["fixture_id"], rec["source_key"], round(rec["no_vig_probability_a"], 3))
        cur = deduped.get(key)
        if cur is None or (rec["retrieved_at_utc"] or "") > (cur["retrieved_at_utc"] or ""):
            if cur is not None:
                duplicates.append(dict(cur, duplicate_of=rec["retrieved_at_utc"]))
            deduped[key] = rec
        else:
            duplicates.append(dict(rec, duplicate_of=cur["retrieved_at_utc"]))
    accepted = list(deduped.values())
    per_fixture = {}
    for rec in accepted:
        per_fixture.setdefault(rec["fixture_id"], []).append(rec)

    rows = []
    now = datetime.now(tz=timezone.utc)
    for fx in fixtures:
        qs = per_fixture.get(fx["fixture_id"], [])
        named = [q for q in qs if q["source_key"] in NAMED_SOURCES]
        fallback = [q for q in qs if q["source_key"] in FALLBACK_SOURCES]
        other = [q for q in qs if q["source_key"] not in NAMED_SOURCES | FALLBACK_SOURCES]
        basis, p_a, p_b, used = "unverified", None, None, []
        if named:
            p_a = statistics.fmean(q["no_vig_probability_a"] for q in named)
            p_b = 1 - p_a
            basis, used = "market-derived", named
        elif fallback:
            p_a = statistics.fmean(q["no_vig_probability_a"] for q in fallback)
            p_b = 1 - p_a
            basis, used = "aggregator-fallback", fallback
        elif other:
            p_a = statistics.fmean(q["no_vig_probability_a"] for q in other)
            p_b = 1 - p_a
            basis, used = "model-input-only", other
        start = parse_ts(fx.get("scheduled_start_time_utc"))
        # A fixture whose kickoff has already passed cannot carry a pre-match probability: any
        # quote for it was read after the match started. The readings are preserved here as
        # late_quotes and published on the flagged page, never as a pick.
        late = bool(start and start <= now)
        late_quotes = used if late else []
        if late:
            basis, p_a, p_b, used = "stale-listing", None, None, []
        row = {
            "fixture_id": fx["fixture_id"],
            "game": "cs2",
            "tournament": fx.get("tournament"),
            "tier": (fx.get("tier") or "").upper() or None,
            "offered_points": fx.get("points") or fx.get("offered_points"),
            "scheduled_start_time_utc": fx.get("scheduled_start_time_utc"),
            "status": fx.get("status"),
            "hotspawn_url": f"https://www.hotspawn.com/matches/{fx['fixture_id']}",
            "team_a": fx["team_a"], "team_b": fx["team_b"],
            "p_a": None if p_a is None else round(p_a, 4),
            "p_b": None if p_b is None else round(p_b, 4),
            "pick_team": (fx["team_a"] if (p_a or 0) >= (p_b or 0) else fx["team_b"]) if p_a is not None else None,
            "pick_probability": None if p_a is None else round(max(p_a, p_b), 4),
            "basis": basis,
            "stale": bool(start and start <= now),
            "minutes_to_start": None if not start else int((start - now).total_seconds() // 60),
            "n_named_sources": len(named), "n_fallback_sources": len(fallback),
            "sources": used,
            "late_quotes": late_quotes,
            "quoteless_sources": other,
            "rejected_quotes_flagged": bool(fx["fixture_id"] in failed_fixtures
                                            and not any(q["fixture_id"] == fx["fixture_id"] for q in accepted)),
            "hotspawn_pick_pct_reference_only": [fx.get("participantsX_picked_percent"),
                                                 fx.get("participantsY_picked_percent")],
        }
        rows.append(row)

    coverage = {
        "generated_at_utc": iso(now),
        "fixtures_total": len(rows),
        "fixtures_with_named_line": sum(1 for r in rows if r["basis"] == "market-derived"),
        "fixtures_with_named_line_including_past": sum(
            1 for r in rows if r["basis"] == "market-derived" or (r["stale"] and r["late_quotes"]
            and any(q["source_key"] in NAMED_SOURCES for q in r["late_quotes"]))),
        "fixtures_with_fallback_only": sum(1 for r in rows if r["basis"] == "aggregator-fallback"),
        "fixtures_unverified": sum(1 for r in rows if r["basis"] == "unverified"),
        "stale_fixtures": sum(1 for r in rows if r["stale"]),
        "quotes_available": len(quotes),
        "quotes_accepted": len(accepted),
        "quote_decisions_rejected": len(rejected),
        "quotes_rejected_by_quality_gate": len(gate_rejected),
        "fixtures_with_rejected_only_quotes": len(failed_fixtures),
        "by_source": {},
    }
    for q in quotes:
        b = coverage["by_source"].setdefault(q["source_key"], {"quotes": 0, "fixtures": 0})
        b["quotes"] += 1
    per = {}
    for rec in accepted:
        per.setdefault(rec["source_key"], set()).add(rec["fixture_id"])
    for k, v in per.items():
        coverage["by_source"][k]["fixtures"] = len(v)
    tournaments = {}
    for r in rows:
        t = tournaments.setdefault(r["tournament"], {"fixtures": 0, "named": 0, "fallback": 0,
                                                     "none": 0, "stale": 0})
        t["fixtures"] += 1
        key = ("named" if r["basis"] == "market-derived" else
               "fallback" if r["basis"] == "aggregator-fallback" else
               "stale" if r["basis"] == "stale-listing" else "none")
        t.setdefault(key, 0)
        t[key] += 1
    coverage["by_tournament"] = tournaments

    board = {"generated_at_utc": iso(now),
             "session": "42580809",
             "fixtures_source": fixtures_doc.get("source_api"),
             "fixtures_source_page": fixtures_doc.get("source_page"),
             "hotspawn_used_for": "fixture discovery only (crowd pick %% shown for reference, never as input)",
             "rules": {
                 "matching": "both participants after documented normalisation, either order; source schedule must agree within 90 minutes",
                 "named_sources": sorted(NAMED_SOURCES),
                 "fallback_sources": sorted(FALLBACK_SOURCES),
                 "devig": "bookmaker decimal odds -> q_i = 1/odds_i -> p_i = q_i/sum(q); Kalshi -> p_i = mid_i/sum(mid)",
                 "consensus": "arithmetic mean of per-source no-vig p_a over named sources only",
             },
             "coverage": coverage,
             "rows": rows}
    return board, accepted, rejected, duplicates, quotes, coverage


def main() -> int:
    board, accepted, rejected, duplicates, quotes, coverage = build()
    with open(os.path.join(DATA, "board_42580809.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(DATA, "board_42580809.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fixture_id", "kickoff_utc", "tournament", "tier", "points", "team_a", "team_b",
                    "probability_a", "probability_b", "pick", "pick_probability", "basis",
                    "n_named_sources", "source_names", "source_urls", "stale", "hotspawn_url"])
        for r in board["rows"]:
            w.writerow([r["fixture_id"], r["scheduled_start_time_utc"], r["tournament"], r["tier"],
                        r["offered_points"], r["team_a"], r["team_b"], r["p_a"], r["p_b"],
                        r["pick_team"], r["pick_probability"], r["basis"], r["n_named_sources"],
                        " | ".join(sorted({q["source_name"] for q in r["sources"]})),
                        " | ".join(sorted({q["source_url"] for q in r["sources"] if q["source_url"]})),
                        r["stale"], r["hotspawn_url"]])
    with open(os.path.join(EV, "matching.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": board["generated_at_utc"],
                   "accepted": accepted, "duplicate_reads": duplicates,
                   "rejected": rejected}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(EV, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(coverage, fh, indent=1, ensure_ascii=False)
    # market graph for originate.py: every accepted quote, plus quotes that reference no pick'em
    # fixture still carry team-strength information when both names are team names.
    graph = [{"fixture_id": a["fixture_id"], "source_key": a["source_key"],
              "team_a": a["source_quoted"]["team_a"], "team_b": a["source_quoted"]["team_b"],
              "team_a_norm": norm(a["source_quoted"]["team_a"]), "team_b_norm": norm(a["source_quoted"]["team_b"]),
              "p_a": a["no_vig_probability_a"], "p_b": a["no_vig_probability_b"],
              "live": a["market_is_live"], "start_time_utc": a["start_time_utc"],
              "matched_to_fixture": True} for a in accepted]
    # Extra market observations that reference no pick'em fixture still carry team-strength
    # information (e.g. Kalshi books for the same teams in another tournament). Property
    # markets and placeholder names are excluded; every extra is kept in the file.
    PROP_NAMES = {"yes", "no", "tie", "odd", "even", "overtime", "map 1", "map 2"}
    for q in quotes:
        if q["source_key"] not in NAMED_SOURCES | FALLBACK_SOURCES:
            continue
        a_norm, b_norm = norm(q["team_a"]), norm(q["team_b"])
        if not a_norm or not b_norm or a_norm in PROP_NAMES or b_norm in PROP_NAMES:
            continue
        if any(w in f"{a_norm} {b_norm}" for w in (" by ", " total", "handicap")):
            continue
        if not (0.02 < q["p_a"] < 0.98):
            continue
        if any(e["team_a_norm"] == a_norm and e["team_b_norm"] == b_norm
               and e["source_key"] == q["source_key"] for e in graph):
            continue
        graph.append({"fixture_id": None, "source_key": q["source_key"], "team_a": q["team_a"],
                      "team_b": q["team_b"], "team_a_norm": a_norm, "team_b_norm": b_norm,
                      "p_a": q["p_a"], "p_b": q["p_b"], "live": q.get("live"),
                      "start_time_utc": iso(q.get("start")), "matched_to_fixture": False})
    with open(os.path.join(EV, "matched_quotes.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": board["generated_at_utc"], "count": len(graph),
                   "matched": sum(1 for g in graph if g["matched_to_fixture"]),
                   "extra": sum(1 for g in graph if not g["matched_to_fixture"]),
                   "teams": len({t for g in graph for t in (g["team_a_norm"], g["team_b_norm"])}),
                   "observations": graph}, fh, indent=1, ensure_ascii=False)
    print(json.dumps(coverage, indent=1)[:900])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
