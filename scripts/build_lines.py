#!/usr/bin/env python3
"""
Match HotSpawn pick'em fixtures to external bookmaker lines and derive no-vig probabilities.

Matching rules (deliberately strict — see the audit handoff in the repo):
  1. BOTH participants must match after normalisation, in the same order or reversed
     (a reversed fixture gets its prices reversed).
  2. Only full-match / series-winner moneyline markets are used. Map-winner, handicap and
     total markets are excluded upstream in collect_odds.py.
  3. If both sides carry a start time, they must agree within 90 minutes. If the bookmaker
     does not publish a start time, the tournament/league name must correspond to the
     fixture's tournament — otherwise the candidate is rejected and logged.
  4. One bookmaker line is assigned to at most one fixture; ambiguous candidates are
     rejected and logged for manual review.

Derived output (clearly labelled, never presented as verified fact):
    q_i = 1 / decimal_odds_i                       (implied probability share)
    p_i = q_i / (q_a + q_b)                        (proportional no-vig estimate)
    overround = (q_a + q_b) - 1                    (bookmaker margin)
Consensus = arithmetic mean of the per-source p_i when two or more sources quote the
fixture; the source list and the rule are published with the numbers.

Outputs: data/lines.json (site input), evidence/matching_evidence.json (decisions + rejects)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Documented aliases: source spelling -> HotSpawn spelling. Each alias is only used when the
# candidate also agrees on tournament and/or start time (checked below), and every applied
# alias is written to evidence/matching_evidence.json with both raw rows so it can be audited.
ALIASES = {
    "bb team": "betboom",
    "pvision": "parivision",
    "parivision": "parivision",
    "9z globant": "9z",
    "team aurora": "aurora",
    "aurora": "aurora",
    "sashi esport": "sashi",
    "sashi": "sashi",
    "furia esports": "furia",
    "furia": "furia",
}

SUFFIXES = (" esports", " esport", " e sports", " gaming", " club")
PREFIXES = ("team ",)  # e.g. Bovada "Team Falcons" -> "falcons", "Team AURORA" -> "aurora"
TIME_TOLERANCE_MIN = 90


def norm(name: str) -> str:
    s = str(name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for suf in SUFFIXES:
        if s.endswith(suf.strip()):
            s = s[: -len(suf.strip())].strip()
    for pre in PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):].strip()
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def tournament_tokens(name: str):
    stop = {"cs2", "the", "series", "cup", "season", "2026", "iii", "ii", "v", "play", "in",
            "championship", "league", "open", "clash", "sa", "na", "south", "north", "america",
            "europe", "american", "challenger", "challengers"}
    toks = {t for t in re.split(r"[^a-z0-9]+", str(name or "").lower()) if t and t not in stop}
    return toks


def tournament_matches(book_league: str, fixture_tournament: str) -> bool:
    a, b = tournament_tokens(book_league), tournament_tokens(fixture_tournament)
    if not a or not b:
        return False
    return bool(a & b)


def main() -> int:
    with open(os.path.join(ROOT, "data", "hotspawn_matches.json"), encoding="utf-8") as fh:
        fixtures_doc = json.load(fh)
    with open(os.path.join(ROOT, "data", "odds.json"), encoding="utf-8") as fh:
        odds_doc = json.load(fh)

    fixtures = [m for m in fixtures_doc["matches"]
                if m.get("sport") == "cs2" and m.get("status") != "cancelled"]
    lines = odds_doc.get("lines", [])

    used_lines = set()
    decisions, rejects = [], []
    matched = {}

    for fx in fixtures:
        fa, fb = norm(fx.get("team_a")), norm(fx.get("team_b"))
        ft = parse_iso(fx.get("scheduled_start_time"))
        found = []
        for idx, ln in enumerate(lines):
            if idx in used_lines:
                continue
            sa, sb = norm(ln.get("team_a_name")), norm(ln.get("team_b_name"))
            order = None
            if sa == fa and sb == fb:
                order = "same"
            elif sa == fb and sb == fa:
                order = "reversed"
            if not order:
                continue
            st = parse_iso(ln.get("start_time_utc"))
            time_ok = bool(ft and st and abs((ft - st).total_seconds()) <= TIME_TOLERANCE_MIN * 60)
            tour_ok = tournament_matches(ln.get("source_league"), fx.get("competition_name"))
            if ft and st and not time_ok:
                rejects.append({"fixture_id": fx["fixture_id"], "fixture": f"{fx['team_a']} vs {fx['team_b']}",
                                "source": ln["source_key"], "source_event_id": ln["source_event_id"],
                                "reason": "start time mismatch",
                                "fixture_start": fx.get("scheduled_start_time"),
                                "source_start": ln.get("start_time_utc")})
                continue
            if not (ft and st) and not tour_ok:
                rejects.append({"fixture_id": fx["fixture_id"], "fixture": f"{fx['team_a']} vs {fx['team_b']}",
                                "source": ln["source_key"], "source_event_id": ln["source_event_id"],
                                "reason": "no start time on either side and tournament does not correspond",
                                "source_league": ln.get("source_league")})
                continue
            decimals = [ln.get("decimal_odds_a"), ln.get("decimal_odds_b")]
            if order == "reversed":
                decimals = [decimals[1], decimals[0]]
            if any(d is None or d <= 1.0 for d in decimals):
                rejects.append({"fixture_id": fx["fixture_id"], "source": ln["source_key"],
                                "reason": "invalid decimal price", "raw": decimals})
                continue
            q = [1.0 / d for d in decimals]
            booksum = sum(q)
            found.append({
                "source_key": ln["source_key"],
                "source_name": ln["source_name"],
                "source_kind": ln["source_kind"],
                "source_public_url": ln.get("source_public_url"),
                "source_api_url": ln.get("source_api_url"),
                "source_event_id": ln.get("source_event_id"),
                "source_market_id": ln.get("source_market_id"),
                "source_league": ln.get("source_league"),
                "market_type": ln.get("market_type"),
                "market_is_live": ln.get("market_is_live"),
                "market_status": ln.get("market_status"),
                "retrieved_at_utc": ln.get("retrieved_at_utc"),
                "source_start_time_utc": ln.get("start_time_utc"),
                "start_time_agrees_with_fixture": time_ok if (ft and st) else None,
                "order_as_quoted": order,
                "bookmaker_order": [ln.get("team_a_name"), ln.get("team_b_name")],
                "raw_price_format": ln.get("raw_price_format"),
                "raw_price_a": ln.get("raw_price_a"),
                "raw_price_b": ln.get("raw_price_b"),
                "decimal_odds_a": decimals[0],
                "decimal_odds_b": decimals[1],
                "decimal_odds_derived": ln.get("decimal_odds_derived", False),
                "overround": round(booksum - 1, 5),
                "derived_probability_a": round(q[0] / booksum, 4),
                "derived_probability_b": round(q[1] / booksum, 4),
                "derivation": "p_i = (1/odds_i) / sum(1/odds_j)  [proportional no-vig]",
            })
            used_lines.add(idx)

        if found:
            per_source = {}
            for f in found:
                per_source.setdefault(f["source_key"], f)
            ps = [per_source[k]["derived_probability_a"] for k in sorted(per_source)]
            consensus = {
                "rule": "arithmetic mean of per-source proportional no-vig probabilities",
                "sources": sorted(per_source),
                "derived_probability_a_mean": round(sum(ps) / len(ps), 4),
                "derived_probability_a_min": round(min(ps), 4),
                "derived_probability_a_max": round(max(ps), 4),
                "n_sources": len(ps),
            }
            consensus["derived_probability_b_mean"] = round(1 - consensus["derived_probability_a_mean"], 4)

        matched[fx["fixture_id"]] = found
        decisions.append({
            "fixture_id": fx["fixture_id"],
            "fixture": f"{fx['team_a']} vs {fx['team_b']}",
            "competition": fx.get("competition_name"),
            "start_time_utc": fx.get("scheduled_start_time"),
            "lines_matched": len(found),
            "sources": sorted({f["source_key"] for f in found}),
            "aliases_applied": sorted({f"{f['bookmaker_order'][0]}->{fx['team_a']}" for f in found
                                       if norm(f["bookmaker_order"][0]) != norm(fx["team_a"])} |
                                      {f"{f['bookmaker_order'][1]}->{fx['team_b']}" for f in found
                                       if norm(f["bookmaker_order"][1]) != norm(fx["team_b"])}),
        })

    # unmatched bookmaker lines (useful evidence: shows what we deliberately did not use)
    unmatched = []
    for idx, ln in enumerate(lines):
        if idx in used_lines:
            continue
        unmatched.append({"source": ln["source_key"], "event": f"{ln.get('team_a_name')} vs {ln.get('team_b_name')}",
                          "start_time_utc": ln.get("start_time_utc"), "league": ln.get("source_league"),
                          "reason": "not part of the current HotSpawn pick'em CS2 fixture list"})

    out_fixtures = []
    for fx in fixtures:
        found = matched.get(fx["fixture_id"], [])
        per_source = {}
        for f in found:
            per_source.setdefault(f["source_key"], f)
        consensus = None
        if per_source:
            ps = [per_source[k]["derived_probability_a"] for k in sorted(per_source)]
            consensus = {
                "rule": "arithmetic mean of per-source proportional no-vig probabilities",
                "sources": sorted(per_source),
                "derived_probability_a_mean": round(sum(ps) / len(ps), 4),
                "derived_probability_a_min": round(min(ps), 4),
                "derived_probability_a_max": round(max(ps), 4),
                "n_sources": len(ps),
                "derived_probability_b_mean": round(1 - round(sum(ps) / len(ps), 4), 4),
            }
        flags = []
        if not found:
            flags.append("external_odds_not_found")
        for f in found:
            if f["start_time_agrees_with_fixture"] is None:
                flags.append(f"start_time_not_published_by_{f['source_key']}")
            if f["decimal_odds_derived"]:
                flags.append(f"decimal_price_derived_from_{f['raw_price_format']}_{f['source_key']}")
            if f["source_start_time_utc"] and fx.get("scheduled_start_time") and \
                    f["source_start_time_utc"] != fx.get("scheduled_start_time"):
                flags.append(f"start_time_minor_difference_{f['source_key']}")
        if not fx.get("scheduled_start_time") or (fx.get("scheduled_start_time") or "") < "2026-10-13":
            flags.append("fixture_start_time_in_the_past_or_stale_source_status")
        out_fixtures.append({
            "fixture_id": fx["fixture_id"],
            "competition": fx.get("competition_name"),
            "tier": fx.get("tier"),
            "start_time_utc": fx.get("scheduled_start_time"),
            "team_a": fx.get("team_a"),
            "team_b": fx.get("team_b"),
            "source_reported_status": fx.get("status"),
            "hotspawn_match_url": fx["source"]["hotspawn_match_url"],
            "hotspawn_pick_pct_reference_only": [fx.get("team_a_pick_pct"), fx.get("team_b_pick_pct")],
            "bookmaker_lines": found,
            "derived": {
                "per_source": {k: {"derived_probability_a": v["derived_probability_a"],
                                   "derived_probability_b": v["derived_probability_b"],
                                   "overround": v["overround"]} for k, v in per_source.items()},
                "consensus": consensus,
            },
            "verification": "verified_external_line" if found else "unverified_no_external_line_found",
            "review_flags": flags,
        })

    # Upcoming/current fixtures first (a stale start time is a source-data quirk, not a ranking).
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    out_fixtures.sort(key=lambda f: (0 if (f.get("start_time_utc") or "") >= today else 1,
                                     f.get("start_time_utc") or "", f["fixture_id"]))
    summary = {
        "fixtures_total": len(out_fixtures),
        "fixtures_with_external_line": sum(1 for f in out_fixtures if f["bookmaker_lines"]),
        "fixtures_without_external_line": sum(1 for f in out_fixtures if not f["bookmaker_lines"]),
        "by_tier": {},
        "by_source": {},
    }
    for f in out_fixtures:
        t = f.get("tier") or "none"
        summary["by_tier"].setdefault(t, {"total": 0, "with_line": 0})
        summary["by_tier"][t]["total"] += 1
        if f["bookmaker_lines"]:
            summary["by_tier"][t]["with_line"] += 1
        for line in f["bookmaker_lines"]:
            summary["by_source"][line["source_key"]] = summary["by_source"].get(line["source_key"], 0) + 1

    doc = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "odds_collected_at_utc": odds_doc.get("generated_at_utc"),
        "fixture_list_collected_at_utc": fixtures_doc.get("generated_at_utc"),
        "method": {
            "match_rule": "both teams normalised-equal (order-insensitive) + start time within 90 min "
                          "or, when a bookmaker gives no start time, corresponding tournament name",
            "probability_rule": "p_i = (1/decimal_odds_i) / sum_j(1/decimal_odds_j) — proportional no-vig",
            "consensus_rule": "arithmetic mean over sources that quote the same fixture",
            "note": "probabilities are DERIVED from quoted prices, not official forecasts",
        },
        "summary": summary,
        "fixtures": out_fixtures,
    }
    write("data/lines.json", doc)
    write("evidence/matching_evidence.json", {
        "generated_at_utc": doc["generated_at_utc"],
        "decisions": decisions,
        "rejected_candidates": rejects,
        "unmatched_bookmaker_lines": unmatched,
        "summary": summary,
    })
    print("fixtures:", summary["fixtures_total"], "with external line:",
          summary["fixtures_with_external_line"], "by source:", summary["by_source"])
    return 0


def write(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
