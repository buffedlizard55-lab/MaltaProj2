#!/usr/bin/env python3
"""Fail-closed current CS2 moneylines from official external quote endpoints.

No crowd percentages, historical model lines or third-party quotes enter this model.
Probability = reciprocal decimal price / sum of both reciprocals (proportional
no-vig assumption). This is an estimate, never an official forecast.
"""
from __future__ import annotations
import json
import math
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_AGE_SECONDS = 4 * 3600  # published policy, not a claim of real-time prices
ALIASES = {}  # unresolved historical identity aliases are not current evidence
SOURCE_HOSTS = {
    "pinnacle": {"guest.api.arcadia.pinnacle.com", "www.pinnacle.com"},
    "bovada": {"www.bovada.lv"},
}
MARKETS = {"series/match winner (moneyline)", "match winner (moneyline, full match)"}


def norm(name):
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    if text.startswith("team "):
        text = text[5:]
    for suffix in (" esports", " esport", " gaming", " club"):
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
    return ALIASES.get(text, text)


def parse_iso(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh(value, now):
    dt = parse_iso(value)
    return dt is not None and 0 <= (now - dt).total_seconds() <= MAX_AGE_SECONDS


def official_url(line):
    for key in ("source_api_url", "source_public_url"):
        parsed = urlsplit(str(line.get(key) or ""))
        if parsed.scheme == "https" and parsed.hostname in SOURCE_HOSTS.get(line.get("source_key"), set()):
            return line[key]
    return None


def pair_order(fixture, line):
    a, b = norm(fixture.get("team_a")), norm(fixture.get("team_b"))
    sa, sb = norm(line.get("team_a_name")), norm(line.get("team_b_name"))
    if not a or not b or a == b:
        return None
    return "same" if (a, b) == (sa, sb) else "reversed" if (a, b) == (sb, sa) else None


def eligibility(fixture, quote, fixtures_time, now):
    if not fresh(fixtures_time, now):
        return "fixture_snapshot_stale_or_unverified_timestamp"
    if not fresh(quote.get("retrieved_at_utc"), now):
        return "quote_stale_or_unverified_timestamp"
    if not official_url(quote):
        return "official_bookmaker_source_not_confirmed"
    if quote.get("sport") != "cs2":
        return "quote_game_not_confirmed"
    if quote.get("market_type") not in MARKETS:
        return "full_match_moneyline_not_confirmed"
    if quote.get("market_is_live") is not False:
        return "live_or_unverified_market_state"
    if quote.get("market_status") not in {"open", "O"}:
        return "market_not_open"
    if quote.get("outcome_alignment_verified") is not True:
        return "outcome_participant_alignment_not_confirmed"
    ft, qt = parse_iso(fixture.get("scheduled_start_time")), parse_iso(quote.get("start_time_utc"))
    if ft is None or qt is None:
        return "start_time_not_confirmed"
    if ft != qt:
        return "start_time_mismatch"
    if ft <= now or str(fixture.get("status", "")).lower() not in {"scheduled", "upcoming", "open", "pending"}:
        return "fixture_not_upcoming"
    lock = parse_iso(fixture.get("lock_time"))
    if lock is None or lock <= now:
        return "pick_lock_passed_or_unverified"
    for value in (quote.get("decimal_odds_a"), quote.get("decimal_odds_b")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 1:
            return "invalid_decimal_price"
    return None


BARE_ROUTE_PREFIX = "https://www.hotspawn.com/matches/"
LOBBY_PAGE_URL = "https://play.hotspawn.com/lobby"


def _match_url(fixture):
    """The per-match URL recorded for a fixture, in either snapshot shape."""
    url = fixture.get("hotspawn_match_url")
    if url:
        return url
    return (fixture.get("source") or {}).get("hotspawn_match_url")


def fixture_source_url(fixture):
    """Official per-row source link for a HotSpawn fixture.

    Only a permalink HotSawn itself publishes on the lobby page may be used as the per-match link.
    A bare `/matches/<numeric id>` is never published by HotSawn (it resolves to the general matches
    index, verified 2026-10-14 ~01:50 UTC), so such a value is discarded and the official lobby page
    is returned instead. No slug is ever constructed.
    """
    url = _match_url(fixture)
    if url and url.startswith(BARE_ROUTE_PREFIX) and url[len(BARE_ROUTE_PREFIX):].isdigit():
        url = None
    return url or LOBBY_PAGE_URL


def fixture_source_kind(fixture):
    source = fixture.get("source") or {}
    if source.get("hotspawn_match_url_kind"):
        return source["hotspawn_match_url_kind"]
    if fixture.get("hotspawn_match_url_kind"):
        return fixture["hotspawn_match_url_kind"]
    url = _match_url(fixture) or ""
    tail = url[len(BARE_ROUTE_PREFIX):] if url.startswith(BARE_ROUTE_PREFIX) else ""
    return "lobby_published_permalink" if (url and not tail.isdigit()) else "official_lobby_fallback"


def build_document(fixtures_doc, odds_doc, now=None):
    now = now or datetime.now(timezone.utc)
    fixtures = [f for f in fixtures_doc["matches"] if f.get("sport") == "cs2"
                and str(f.get("status", "")).lower() not in {"cancelled", "ended"}]
    quotes = odds_doc.get("lines", [])
    candidates, rejects, consumed = {}, [], set()
    matched = {f["fixture_id"]: [] for f in fixtures}
    flags_by_id = {f["fixture_id"]: set() for f in fixtures}
    for index, quote in enumerate(quotes):
        possible = []
        for fx in fixtures:
            order = pair_order(fx, quote)
            if not order:
                continue
            reason = eligibility(fx, quote, fixtures_doc.get("generated_at_utc"), now)
            if reason:
                flags_by_id[fx["fixture_id"]].add(reason)
                rejects.append({"fixture_id": fx["fixture_id"], "fixture": f"{fx['team_a']} vs {fx['team_b']}",
                                "source": quote.get("source_key"), "source_event_id": quote.get("source_event_id"),
                                "source_url": official_url(quote) or quote.get("source_api_url"), "reason": reason})
            else:
                possible.append((fx, order))
        if len(possible) > 1:
            for fx, _ in possible:
                flags_by_id[fx["fixture_id"]].add("ambiguous_fixture_join")
                rejects.append({"fixture_id": fx["fixture_id"], "fixture": f"{fx['team_a']} vs {fx['team_b']}",
                                "source": quote.get("source_key"), "source_url": official_url(quote),
                                "reason": "ambiguous_fixture_join"})
        elif possible:
            fx, order = possible[0]
            candidates.setdefault((fx["fixture_id"], quote["source_key"]), []).append((index, quote, order))
    for (fixture_id, source), group in candidates.items():
        if len(group) != 1:
            flags_by_id[fixture_id].add("ambiguous_source_quotes")
            for _, quote, _ in group:
                rejects.append({"fixture_id": fixture_id, "source": source, "source_url": official_url(quote),
                                "reason": "ambiguous_source_quotes"})
            continue
        index, quote, order = group[0]
        decimals = [quote["decimal_odds_a"], quote["decimal_odds_b"]]
        if order == "reversed":
            decimals.reverse()
        shares = [1 / d for d in decimals]
        total = sum(shares)
        line = dict(quote)
        line.update({"decimal_odds_a": decimals[0], "decimal_odds_b": decimals[1],
                     "derived_probability_a": round(shares[0] / total, 4),
                     "derived_probability_b": round(shares[1] / total, 4),
                     "overround": round(total - 1, 5), "order_as_quoted": order,
                     "bookmaker_order": [quote.get("team_a_name"), quote.get("team_b_name")],
                     "source_start_time_utc": quote.get("start_time_utc"),
                     "start_time_agrees_with_fixture": True,
                     "derivation": "p_i = (1/odds_i) / sum(1/odds_j) [proportional no-vig]"})
        matched[fixture_id].append(line)
        consumed.add(index)
    output, decisions = [], []
    summary = {"fixtures_total": len(fixtures), "fixtures_with_external_line": 0,
               "fixtures_without_external_line": 0, "by_tier": {}, "by_source": {}}
    for fx in fixtures:
        found = sorted(matched[fx["fixture_id"]], key=lambda x: x["source_key"])
        flags = flags_by_id[fx["fixture_id"]]
        if not found:
            flags.add("external_odds_not_found")
        start = parse_iso(fx.get("scheduled_start_time"))
        if start is None or start <= now:
            flags.add("fixture_start_time_in_the_past_or_stale_source_status")
        if not fresh(fixtures_doc.get("generated_at_utc"), now):
            flags.add("fixture_snapshot_stale_or_unverified_timestamp")
        consensus = None
        if found:
            ps = [q["derived_probability_a"] for q in found]
            mean = round(sum(ps) / len(ps), 4)
            consensus = {"rule": "arithmetic mean of per-source proportional no-vig probabilities",
                         "sources": [q["source_key"] for q in found], "n_sources": len(ps),
                         "derived_probability_a_mean": mean, "derived_probability_b_mean": round(1 - mean, 4),
                         "derived_probability_a_min": min(ps), "derived_probability_a_max": max(ps)}
        output.append({"fixture_id": fx["fixture_id"], "competition": fx.get("competition_name"),
                       "tier": fx.get("tier"), "start_time_utc": fx.get("scheduled_start_time"),
                       "team_a": fx.get("team_a"), "team_b": fx.get("team_b"),
                       "source_reported_status": fx.get("status"),
                       "hotspawn_match_url": fixture_source_url(fx),
                       "hotspawn_match_url_kind": fixture_source_kind(fx),
                       "bookmaker_lines": found,
                       "derived": {"per_source": {q["source_key"]: {k: q[k] for k in
                                    ("derived_probability_a", "derived_probability_b", "overround")} for q in found},
                                   "consensus": consensus},
                       "verification": "source_linked_current_quote" if found else "unverified_no_eligible_external_line",
                       "review_flags": sorted(flags)})
        decisions.append({"fixture_id": fx["fixture_id"], "fixture": f"{fx['team_a']} vs {fx['team_b']}",
                          "lines_matched": len(found), "sources": [q["source_key"] for q in found]})
        summary["fixtures_with_external_line" if found else "fixtures_without_external_line"] += 1
        tier = summary["by_tier"].setdefault(fx.get("tier") or "none", {"total": 0, "with_line": 0})
        tier["total"] += 1
        tier["with_line"] += bool(found)
        for q in found:
            summary["by_source"][q["source_key"]] = summary["by_source"].get(q["source_key"], 0) + 1
    output.sort(key=lambda f: (parse_iso(f.get("start_time_utc")) is None or parse_iso(f.get("start_time_utc")) <= now,
                               f.get("start_time_utc") or "", f["fixture_id"]))
    doc = {"generated_at_utc": iso(now), "odds_collected_at_utc": odds_doc.get("generated_at_utc"),
           "fixture_list_collected_at_utc": fixtures_doc.get("generated_at_utc"),
           "method": {"match_rule": "both teams, explicit CS2, exact UTC start, unique fixture and source quote",
                      "max_age_seconds": MAX_AGE_SECONDS,
                      "probability_rule": "proportional no-vig: (1/odds_i) / sum(1/odds_j)",
                      "consensus_rule": "arithmetic mean of eligible bookmaker probabilities",
                      "note": "Derived estimates, not verified win probabilities. Prematch and unlocked only."},
           "summary": summary, "fixtures": output}
    unmatched = [{"source": q.get("source_key"), "event": f"{q.get('team_a_name')} vs {q.get('team_b_name')}",
                  "start_time_utc": q.get("start_time_utc"), "league": q.get("source_league"),
                  "source_url": official_url(q) or q.get("source_api_url"),
                  "reason": "no unique eligible current fixture join; see rejection log"}
                 for i, q in enumerate(quotes) if i not in consumed]
    evidence = {"generated_at_utc": iso(now), "decisions": decisions, "rejected_candidates": rejects,
                "unmatched_bookmaker_lines": unmatched, "summary": summary}
    return doc, evidence


def write(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, allow_nan=False)


def main():
    with open(os.path.join(ROOT, "data/hotspawn_matches.json"), encoding="utf-8") as fh:
        fixtures = json.load(fh)
    with open(os.path.join(ROOT, "data/odds.json"), encoding="utf-8") as fh:
        odds = json.load(fh)
    doc, evidence = build_document(fixtures, odds)
    write("data/lines.json", doc)
    write("evidence/matching_evidence.json", evidence)
    print("Current line coverage:", doc["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
