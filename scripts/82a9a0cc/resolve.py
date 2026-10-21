#!/usr/bin/env python3
"""Resolve every captured HotSpawn fixture through a conservative, auditable ladder."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hotspawn_core import (  # noqa: E402
    SOURCE_WEIGHTS,
    SPORTSBOOKS,
    make_line,
    market_consensus,
    match_name,
    norm,
    quote_probability,
    vrs_probability,
)

INPUT = ROOT / "data" / "82a9a0cc" / "input.json"
OUT = ROOT / "data" / "82a9a0cc" / "board.json"
VALVE_REPO = "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def vrs_link(team: dict) -> str:
    return VALVE_REPO + team["details_path"]


def competition_family_matches(fixture_comp: str, quote_league: str) -> bool:
    stop = {"cs", "counter", "strike", "esports", "2"}
    words = lambda value: {word.casefold() for word in value.replace("#", " ").replace(".", " ").split()
                           if len(word) >= 3 and word.casefold() not in stop and not word.isdigit()}
    fixture_words, quote_words = words(fixture_comp or ""), words(quote_league or "")
    return len(fixture_words & quote_words) >= 2


def orient_quote(row: dict, quote: dict) -> dict | None:
    if quote.get("source_key") not in SPORTSBOOKS or quote.get("live"):
        return None
    if quote.get("start_utc") != row.get("start_utc"):
        return None
    if not competition_family_matches(row.get("competition", ""), quote.get("league", "")):
        return None
    direct_a, note_aa = match_name(row["team_a"], quote.get("team_a", ""))
    direct_b, note_bb = match_name(row["team_b"], quote.get("team_b", ""))
    rev_a, note_ab = match_name(row["team_a"], quote.get("team_b", ""))
    rev_b, note_ba = match_name(row["team_b"], quote.get("team_a", ""))
    p_source_a = quote_probability(quote)
    if p_source_a is None:
        return None
    if direct_a and direct_b:
        probability, notes, orientation = p_source_a, [note_aa, note_bb], "direct"
    elif rev_a and rev_b:
        probability, notes, orientation = 1.0 - p_source_a, [note_ab, note_ba], "reversed"
    else:
        return None
    alias_notes = sorted({note for note in notes if note})
    if not alias_notes:
        return None  # exact pairs were already handled by the authoritative strict board
    out = copy.deepcopy(quote)
    out.update({"prob_fixture_a": probability, "orientation": orientation, "alias_notes": alias_notes})
    return out


def market_alias_rescue(row: dict, quotes: list[dict]) -> tuple[dict, list[dict]] | None:
    candidates = [q for q in (orient_quote(row, q) for q in quotes) if q]
    by_source: dict[str, dict] = {}
    for quote in sorted(candidates, key=lambda q: q.get("retrieved_utc", ""), reverse=True):
        by_source.setdefault(quote["source_key"], quote)
    selected = list(by_source.values())
    if len(selected) < 2:  # a single spelling alias is too risky to publish
        return None
    p_a = market_consensus(selected)
    if p_a is None:
        return None
    line = make_line(
        p_a,
        row["team_a"],
        row["team_b"],
        "researched_market_alias",
        source_keys=sorted(q["source_key"] for q in selected),
        source_weights={q["source_key"]: SOURCE_WEIGHTS[q["source_key"]] for q in selected},
        alias_rule="explicit_ex_cybershoke_two_book_exact_fixture",
    )
    return line, selected


def selected_by_secondary(team_name: str, candidates: list[dict], secondary: dict) -> tuple[dict | None, dict | None]:
    matches = []
    for meta in (secondary.get("bo3gg_teams") or {}).values():
        if norm(meta.get("name")) != norm(team_name):
            continue
        for candidate in candidates:
            if meta.get("rank") == candidate.get("standing"):
                matches.append((candidate, meta))
    unique = {(item[0]["standing"], item[1].get("id")): item for item in matches}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None, None


def model_resolution(row: dict, groups: dict[str, list[dict]], secondary: dict, k: float | None,
                     floor: dict) -> tuple[dict | None, dict, list[dict], list[str]]:
    if not isinstance(k, (int, float)):
        return None, {"reason": "calibration unavailable"}, [], ["F-MODEL-UNAVAILABLE"]
    a_candidates = groups.get(norm(row["team_a"]), [])
    b_candidates = groups.get(norm(row["team_b"]), [])
    a_selected = a_candidates[0] if len(a_candidates) == 1 else None
    b_selected = b_candidates[0] if len(b_candidates) == 1 else None
    disambiguation = []
    flags: list[str] = []
    secondary_sources: list[dict] = []
    if len(a_candidates) > 1:
        a_selected, meta = selected_by_secondary(row["team_a"], a_candidates, secondary)
        if a_selected and meta:
            disambiguation.append({"side": "a", "standing": a_selected["standing"], "provider": "bo3.gg",
                                   "provider_rank": meta["rank"], "provider_team_id": meta.get("id")})
            secondary_sources.append(meta)
    if len(b_candidates) > 1:
        b_selected, meta = selected_by_secondary(row["team_b"], b_candidates, secondary)
        if b_selected and meta:
            disambiguation.append({"side": "b", "standing": b_selected["standing"], "provider": "bo3.gg",
                                   "provider_rank": meta["rank"], "provider_team_id": meta.get("id")})
            secondary_sources.append(meta)

    if a_selected and b_selected:
        p_a = vrs_probability(a_selected["points"], b_selected["points"], k)
        basis = "vrs_model_roster_resolved" if disambiguation else "vrs_model"
        if disambiguation:
            flags.append("F-DUPLICATE-VRS")
        detail = {
            "method": basis,
            "k": k,
            "valve_c": "g(75)*ln(10)/400",
            "team_a_vrs": a_selected,
            "team_b_vrs": b_selected,
            "duplicate_candidates": {"a": a_candidates, "b": b_candidates},
            "disambiguation": disambiguation,
        }
        evidence = [a_selected, b_selected]
        line = make_line(p_a, row["team_a"], row["team_b"], basis,
                         vrs_points_a=a_selected["points"], vrs_points_b=b_selected["points"],
                         vrs_standing_a=a_selected["standing"], vrs_standing_b=b_selected["standing"])
        detail["secondary_sources"] = secondary_sources
        return line, detail, evidence, flags

    # If all official duplicate combinations agree on the winner, publish only the edge closest
    # to 50%. This never chooses a roster and makes the known-name ambiguity explicit.
    if a_candidates and b_candidates:
        scenarios = []
        for a in a_candidates:
            for b in b_candidates:
                scenarios.append({"standing_a": a["standing"], "standing_b": b["standing"],
                                  "points_a": a["points"], "points_b": b["points"],
                                  "prob_a": vrs_probability(a["points"], b["points"], k)})
        all_a = all(item["prob_a"] > 0.5 for item in scenarios)
        all_b = all(item["prob_a"] < 0.5 for item in scenarios)
        if all_a or all_b:
            conservative = min(scenarios, key=lambda item: abs(item["prob_a"] - 0.5))
            flags.append("F-DUPLICATE-VRS")
            line = make_line(conservative["prob_a"], row["team_a"], row["team_b"],
                             "vrs_ambiguity_robust", directional=True,
                             scenario_prob_a_min=round(min(s["prob_a"] for s in scenarios), 4),
                             scenario_prob_a_max=round(max(s["prob_a"] for s in scenarios), 4))
            detail = {"method": "vrs_ambiguity_robust", "k": k, "scenarios": scenarios,
                      "duplicate_candidates": {"a": a_candidates, "b": b_candidates},
                      "published_scenario": conservative,
                      "rule": "publish the edge nearest 50% only when every official-name candidate combination picks the same side"}
            return line, detail, a_candidates + b_candidates, flags

    # One-sided official VRS scenario: the unknown side is assigned the published table floor.
    # This is a directional scenario, not represented as a sportsbook-equivalent confidence.
    if bool(a_candidates) != bool(b_candidates):
        rated_side = "a" if a_candidates else "b"
        rated_candidates = a_candidates or b_candidates
        probabilities = []
        for rated in rated_candidates:
            p_rated = vrs_probability(rated["points"], floor["points"], k)
            p_a = p_rated if rated_side == "a" else 1.0 - p_rated
            probabilities.append((abs(p_a - 0.5), p_a, rated))
        _, p_a, rated = min(probabilities, key=lambda item: item[0])
        flags.append("F-ONE-SIDED-VRS")
        line = make_line(p_a, row["team_a"], row["team_b"], "vrs_floor_scenario", directional=True,
                         rated_side=rated_side, rated_points=rated["points"],
                         floor_points=floor["points"], floor_standing=floor["standing"])
        detail = {"method": "vrs_floor_scenario", "k": k, "rated_side": rated_side,
                  "rated_candidate": rated, "rated_candidates": rated_candidates, "floor": floor,
                  "rule": "unrated opponent is set to the lowest published official VRS points; directional scenario only"}
        return line, detail, rated_candidates + [floor], flags

    reason = "both teams absent from the latest official VRS and no qualifying direct market line"
    if a_candidates or b_candidates:
        reason = "official duplicate-name candidates disagree on the winner and no roster identity is confirmed"
    return None, {"method": "unresolved", "reason": reason,
                  "duplicate_candidates": {"a": a_candidates, "b": b_candidates}}, [], ["F-UNRESOLVED"]


def market_evidence(row: dict) -> list[dict]:
    output = []
    for quote in row.get("quotes") or []:
        if not quote.get("public_url"):
            continue
        output.append({"kind": "market", "label": quote.get("source_name") or quote.get("source_key"),
                       "url": quote["public_url"], "observed_utc": quote.get("retrieved_utc"),
                       "note": f"retained two-way quote for {quote.get('team_a')} vs {quote.get('team_b')}"})
    return output


def research_attempts(source: dict) -> dict:
    access = source["base"].get("access") or {}
    return {
        "featured_markets": {key: {field: (access.get(key) or {}).get(field) for field in ("url", "status", "ok", "quotes", "at_utc")}
                             for key in ("pinnacle", "bovada", "melbet", "kalshi", "polymarket_probe")},
        "hltv": {field: (access.get("hltv_probe") or {}).get(field) for field in ("url", "status", "ok", "error", "at_utc")},
        "official_vrs": {field: (access.get(field and "valve_vrs_file") or {}).get(field)
                         for field in ("url", "status", "ok", "at_utc")},
    }


def main() -> int:
    source = json.loads(INPUT.read_text())
    vrs = source["vrs"]
    teams = vrs["teams"]
    groups: dict[str, list[dict]] = {}
    for team in teams:
        groups.setdefault(norm(team.get("team")), []).append(team)
    floor = min(teams, key=lambda team: (team["points"], -team["standing"]))
    calibration = source["base"].get("calibration") or {}
    k = calibration.get("k") if calibration.get("fitted") is True else None
    valve_page = vrs["page_url"]
    generated = source["captured_utc"] or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    snapshot_dt = parse_utc(vrs.get("snapshot", "").replace("_", "-") + "T00:00:00Z")
    generated_dt = parse_utc(generated)
    age_days = round((generated_dt - snapshot_dt).total_seconds() / 86400, 2) if snapshot_dt and generated_dt else None

    rows = []
    for base in source["base"]["open"]:
        row = {key: copy.deepcopy(base.get(key)) for key in
               ("fixture_id", "competition", "start_utc", "lock_utc", "team_a", "team_b", "status")}
        row["url"] = base.get("hotspawn_url")
        row["base_featured_line"] = bool(base.get("line"))
        row["flag_ids"] = []
        row["evidence"] = [{"kind": "fixture", "label": "HotSpawn fixture",
                            "url": base["hotspawn_url"], "observed_utc": source["base"].get("collected_from_utc"),
                            "note": "fixture identity, competition, kickoff, and lock only; crowd ownership excluded"}]
        if base.get("line"):
            row["line"] = copy.deepcopy(base["line"])  # authoritative lines remain byte-for-value unchanged
            row["resolution"] = {"method": "featured_market", "preserved_from": source["base"]["path"],
                                 "quote_count": len(base.get("quotes") or [])}
            row["evidence"].extend(market_evidence(base))
        else:
            # The user's requested gap-research order is explicit: after the featured market
            # misses, inspect the current HLTV probe before trying extra esportsbook recovery.
            # The retained probe is presently blocked (HTTP 403), so it contributes no number.
            hltv = (source["base"].get("access") or {}).get("hltv_probe") or {}
            row["research_before_fallback"] = {
                "hltv": {key: hltv.get(key) for key in ("url", "status", "ok", "error", "at_utc")},
                "result": "no numeric claim used; continue to esportsbooks" if not hltv.get("ok") else "availability confirmed; no unsupported numeric probability inferred",
            }
            rescued = market_alias_rescue(base, source["raw_quotes"])
            if rescued:
                line, selected = rescued
                row["line"] = line
                row["resolution"] = {"method": "researched_market_alias",
                                     "rule": line["alias_rule"], "quotes": selected,
                                     "exact_kickoff_required": True, "minimum_independent_books": 2}
                for quote in selected:
                    row["evidence"].append({"kind": "market", "label": quote["source_name"],
                                            "url": quote["public_url"], "observed_utc": quote["retrieved_utc"],
                                            "note": f"exact-start {quote['team_a']} vs {quote['team_b']}; no-vig probability re-derived from raw {quote['raw_format']} prices"})
                row["flag_ids"].append("F-ALIAS-MARKET")
            else:
                line, detail, model_teams, flags = model_resolution(base, groups, source["secondary"], k, floor)
                row["line"], row["resolution"] = line, detail
                row["flag_ids"].extend(flags)
                if line:
                    for team in model_teams:
                        row["evidence"].append({"kind": "official_vrs", "label": f"Valve VRS #{team['standing']} · {team['team']}",
                                                "url": vrs_link(team), "observed_utc": source["base"].get("generated_utc"),
                                                "note": f"{team['points']} points; roster {team['roster']}"})
                    for meta in detail.get("secondary_sources") or []:
                        row["evidence"].append({"kind": "identity", "label": f"bo3.gg · {meta['name']}",
                                                "url": "https://bo3.gg/teams/" + meta["slug"],
                                                "observed_utc": source["secondary"].get("generated_utc"),
                                                "note": f"current team id {meta['id']} reported rank #{meta['rank']}; used only to select the matching official VRS row"})
                if age_days is not None and age_days > 14 and line:
                    row["flag_ids"].append("F-VRS-STALE")
        rows.append(row)

    counts = {
        "open": len(rows),
        "with_pick": sum(bool(row.get("line")) for row in rows),
        "unresolved": sum(not row.get("line") for row in rows),
        "featured_market": sum((row.get("line") or {}).get("basis") == "market" for row in rows),
        "researched_market": sum((row.get("line") or {}).get("basis") == "researched_market_alias" for row in rows),
        "vrs_pair": sum((row.get("line") or {}).get("basis") in {"vrs_model", "vrs_model_roster_resolved"} for row in rows),
        "vrs_robust": sum((row.get("line") or {}).get("basis") == "vrs_ambiguity_robust" for row in rows),
        "vrs_floor_scenario": sum((row.get("line") or {}).get("basis") == "vrs_floor_scenario" for row in rows),
        "featured_gaps_resolved": sum(not row["base_featured_line"] and bool(row.get("line")) for row in rows),
    }
    official = source.get("official_check") or {}
    flags = [
        {"id": "F-VRS-STALE", "severity": "review", "title": "Official VRS is outside the 14-day preferred window",
         "detail": f"Valve's latest global file at capture was {vrs['snapshot']} ({age_days} days old). Model rows are labelled, not presented as sportsbook lines.",
         "url": official.get("page_url") or valve_page},
        {"id": "F-ALIAS-MARKET", "severity": "review", "title": "One exact-fixture market required a narrow ex- roster alias",
         "detail": "Bovada and Melbet both omitted HotSpawn's ex- prefix for ex-CYBERSHOKE; exact BlinkDagger opponent and exact kickoff were required.",
         "url": "https://www.bovada.lv/esports/counter-strike-2"},
        {"id": "F-DUPLICATE-VRS", "severity": "review", "title": "Duplicate official VRS team names handled without name-only joins",
         "detail": "Banda Chuya is selected only where current bo3.gg rank equals an official row; The Huns publishes the conservative edge shared by both official rows.",
         "url": valve_page},
        {"id": "F-ONE-SIDED-VRS", "severity": "limitation", "title": "Two fixtures use one-sided VRS floor scenarios",
         "detail": "The unrated opponent is set to the lowest published Valve VRS points. These are directional sensitivity scenarios, not bookmaker probabilities.",
         "url": valve_page},
        {"id": "F-HLTV-BLOCKED", "severity": "limitation", "title": "Current automated HLTV verification was blocked",
         "detail": f"HLTV returned HTTP {(source['base'].get('access', {}).get('hltv_probe') or {}).get('status')} at capture; no current numeric HLTV claim is inferred.",
         "url": "https://www.hltv.org/matches"},
        {"id": "F-HOTSPAWN-CACHE", "severity": "note", "title": "HotSpawn lobby response was cached",
         "detail": f"The fixture observation was {source['base'].get('fixture_observation_age_seconds')} seconds old but within the collector's {source['base'].get('freshness_limit_hours')}-hour gate.",
         "url": "https://play.hotspawn.com/lobby"},
    ]
    board = {
        "schema": "hotspawn-live-board-v1",
        "session": "82a9a0cc",
        "generated_utc": generated,
        "inventory": {"source": "HotSpawn lobby open fixtures as strictly normalized by f7279a54",
                      "source_path": source["base"]["path"], "fixture_observation_age_seconds": source["base"].get("fixture_observation_age_seconds"),
                      "freshness_limit_hours": source["base"].get("freshness_limit_hours"), "week": source["base"].get("week"),
                      "policy": "include lobby-listed open fixtures; exclude API-only/cancelled/started status conflicts",
                      "hotspawn_probability_policy": "never use crowd pick ownership as a probability, prior, feature, or tiebreak"},
        "method": {"ladder": ["preserved featured two-way market", "current HLTV research probe for featured gaps",
                               "two-book exact-fixture esportsbook rescue", "calibrated official Valve VRS pair",
                               "rank-resolved or ambiguity-robust Valve VRS", "one-sided official VRS floor scenario",
                               "blank plus explicit unresolved limitation"],
                   "calibration": calibration, "vrs_snapshot": vrs["snapshot"], "vrs_age_days": age_days,
                   "vrs_source": valve_page, "vrs_latest_check": official,
                   "research_attempts": research_attempts(source)},
        "summary": counts,
        "flags": flags,
        "status_conflicts_excluded": source["base"].get("status_conflicts") or [],
        "rows": rows,
    }
    OUT.write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
