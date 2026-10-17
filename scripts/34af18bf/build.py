#!/usr/bin/env python3
"""Session 34af18bf builder — one pickable row for every HotSpawn CS2 fixture.

Input : data/34af18bf/snapshot.json   (collector output: fixtures + external quotes + VRS)
Output: data/34af18bf/board.json, data/34af18bf/board.csv

Resolution ladder (first rung that produces a two-sided reading wins; the rung is
printed on every row so nothing is silently blended):

  1. MARKET      a bookmaker/exchange line for that exact fixture
                 (Pinnacle, Bovada, Melbet/1xBet platform, Kalshi within the
                 spread gate, Thunderpick coefficients published by bo3.gg,
                 Polymarket with a traded book) — merged by declared weights
  2. RESEARCH    a dated, source-linked reading this desk took by hand
                 (esportsbook/odds/analytics pages that refuse the runner)
  3. ORIGINATED  Valve's official regional standings (VRS) through a declared
                 Elo transform, used only when no market prices the fixture
  4. BLANK       no price and no usable ratings → published as unresolved with
                 the reason, never as an invented 50/50

HotSpawn contributes fixtures, offered points and crowd ownership. Its crowd
percentage is never an input to a probability; it is used only to compute the
leaderboard differential ``points × (probability − ownership)``.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import research  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "34af18bf"
BO3_TEAMS: dict = {}          # filled in main() from the snapshot
BO3_READ_UTC: str = ""        # read time recorded by the collector for that snapshot

# Declared source weights for the market consensus (published on method.html).
SOURCE_WEIGHTS = {"pinnacle": 2.0, "thunderpick": 1.0, "melbet": 1.0, "bovada": 1.0,
                  "kalshi": 1.0, "polymarket": 1.0, "research": 1.0}
SOURCE_LABELS = {"pinnacle": "Pinnacle", "bovada": "Bovada", "melbet": "Melbet (1xBet platform)",
                 "kalshi": "Kalshi (exchange)", "thunderpick": "Thunderpick via bo3.gg",
                 "polymarket": "Polymarket", "research": "Research reading (dated)"}
KALSHI_SPREAD_GATE = 0.10          # reject thin/untraded exchange books
VRS_ELO_SCALE = 400.0              # declared transform: p = 1/(1+10^(-Δ/400))
RANK_SCALE = 40.0                  # declared transform on bo3.gg world ranks: p = 0.5+0.5*tanh(Δ/40)
RANK_CLAMP = (0.08, 0.92)          # a rank is a coarse input: never claim more than this
C1_MIN_PROBABILITY = 0.20          # "not stupid" floor: never below one win in five
C4_MAX_CLIMB_PER_DAY = 3


# --------------------------------------------------------------------------- helpers
def index_quotes(quotes: list[dict]) -> dict[tuple[str, str], list[dict]]:
    index: dict[tuple[str, str], list[dict]] = {}
    for q in quotes:
        key = core.pair_key(q.get("team_a"), q.get("team_b"))
        index.setdefault(key, []).append(q)
    return index


def readings_for(fixture: dict, index: dict[tuple[str, str], list[dict]]) -> tuple[list[dict], list[dict]]:
    """Everything that prices this fixture, oriented to (team_a, team_b)."""
    a, b = fixture["team_a"], fixture["team_b"]
    ka, kb = core.canon(a), core.canon(b)
    accepted, refused = [], []
    for q in index.get(core.pair_key(a, b), []) + index.get((kb, ka), []):
        swapped = core.canon(q.get("team_a")) == kb and core.canon(q.get("team_b")) == ka
        prob_a = q.get("prob_a")
        prob_b = q.get("prob_b")
        if prob_a is None or prob_b is None:
            nv = core.no_vig(q.get("decimal_a"), q.get("decimal_b"))
            if not nv:
                refused.append({"source": q.get("source_key"), "reason": "no two-sided decimal line",
                                "public_url": q.get("public_url")})
                continue
            prob_a, prob_b = nv["prob_a"], nv["prob_b"]
        pa, pb = (prob_b, prob_a) if swapped else (prob_a, prob_b)
        weight = SOURCE_WEIGHTS.get(q.get("source_key"), 1.0)
        record = {"source_key": q.get("source_key"), "source_name": q.get("source_name"),
                  "public_url": q.get("public_url"), "api_url": q.get("api_url"),
                  "event_id": q.get("event_id"), "decimal_a": q.get("decimal_a"),
                  "decimal_b": q.get("decimal_b"), "raw_a": q.get("raw_a"), "raw_b": q.get("raw_b"),
                  "raw_format": q.get("raw_format"), "retrieved_utc": q.get("retrieved_utc"),
                  "start_utc": q.get("start_utc"), "prob_a": round(pa, 6), "prob_b": round(pb, 6),
                  "weight": weight, "swapped": swapped,
                  "market_prob_a": round(prob_a if not swapped else prob_b, 6)}
        if q.get("source_key") == "kalshi":
            spread = q.get("spread")
            record["spread"] = spread
            if spread is None or spread > KALSHI_SPREAD_GATE:
                refused.append({"source": "kalshi", "reason": f"exchange spread {spread} above the "
                                                              f"{KALSHI_SPREAD_GATE} gate (thin book)",
                                "public_url": q.get("public_url"), "legs": q.get("legs")})
                continue
        if q.get("source_key") == "polymarket":
            volume = q.get("volume_usd")
            record["volume_usd"] = volume
            if volume is None or volume < 25.0:
                refused.append({"source": "polymarket", "reason": f"untraded book (${volume} volume)",
                                "public_url": q.get("public_url")})
                continue
        accepted.append(record)
    return accepted, refused


def vrs_reading(team_a: str, team_b: str, vrs: dict) -> dict | None:
    teams = (vrs or {}).get("teams") or {}
    ra, rb = teams.get(core.canon(team_a)), teams.get(core.canon(team_b))
    if not ra or not rb:
        return None
    diff = float(ra["points"]) - float(rb["points"])
    prob_a = 1.0 / (1.0 + 10 ** (-diff / VRS_ELO_SCALE))
    return {"prob_a": round(prob_a, 6), "prob_b": round(1 - prob_a, 6),
            "rating_a": ra, "rating_b": rb, "delta_points": round(diff, 1)}


def rank_reading(team_a: str, team_b: str, bo3_teams: dict) -> dict | None:
    """Last-resort ORIGINATED line from the bo3.gg world rank of the two teams.

    Used only when no market prices the fixture and Valve does not rank both teams.
    The transform is declared on the method page and the source link is the bo3.gg
    team record the rank was read from.
    """
    import math
    by_name = {}
    for tid, rec in (bo3_teams or {}).items():
        if isinstance(rec, dict) and rec.get("rank"):
            by_name[core.canon(rec.get("name"))] = (rec, tid)
    ra, rb = by_name.get(core.canon(team_a)), by_name.get(core.canon(team_b))
    if not ra or not rb:
        return None
    delta = float(rb[0]["rank"]) - float(ra[0]["rank"])   # positive => team_a ranked higher
    prob_a = 0.5 + 0.5 * math.tanh(delta / RANK_SCALE)
    prob_a = min(max(prob_a, RANK_CLAMP[0]), RANK_CLAMP[1])
    return {"prob_a": round(prob_a, 6), "prob_b": round(1 - prob_a, 6),
            "rank_a": ra[0]["rank"], "rank_b": rb[0]["rank"], "delta": delta,
            "name_a": ra[0].get("name"), "name_b": rb[0].get("name"),
            "slug_a": ra[0].get("slug"), "slug_b": rb[0].get("slug")}


def crowd_of(fixture: dict, team: str) -> float | None:
    canon = core.canon(team)
    if canon == core.canon(fixture["team_a"]) and fixture.get("crowd_a_pct") is not None:
        return float(fixture["crowd_a_pct"]) / 100.0
    if canon == core.canon(fixture["team_b"]) and fixture.get("crowd_b_pct") is not None:
        return float(fixture["crowd_b_pct"]) / 100.0
    return None


def context_flags(team: str, opponent: str, res: dict) -> list[dict]:
    """Verified context flags for a climb pick (C3). Only research-backed entries count."""
    flags: list[dict] = []
    for h in res.H2H:
        pair = {core.canon(h["pair"][0]), core.canon(h["pair"][1])}
        if pair == {core.canon(team), core.canon(opponent)} and core.canon(team) in core.canon(h["result"]):
            label = res.SOURCES[h["source"]][0]
            flags.append({"kind": "head-to-head", "text": h["result"] + " — " + label + f" ({h['when']})",
                          "url": res.SOURCES[h["source"]][1]})
    audit = None
    for name, entry in res.ROSTER_AUDIT.items():
        if core.canon(name) == core.canon(team):
            audit = entry
    if audit:
        change = audit.get("last_active_lineup_change")
        if change:
            label = res.SOURCES[change["sources"][0]][0]
            flags.append({"kind": "roster change", "text": f"{change['date']}: {change['what']} — {label}",
                          "url": res.SOURCES[change["sources"][0]][1]})
        if audit.get("rest_before_semi"):
            flags.append({"kind": "rest", "text": audit["rest_before_semi"],
                          "url": res.SOURCES[audit["sources"][0]][1]})
    for m in res.MAP_POOL_NOTES:
        if core.canon(m["team"]) == core.canon(team):
            label = res.SOURCES[m["source"]][0]
            flags.append({"kind": "map pool", "text": f"{m['map']}: {m['fact']} — {label}",
                          "url": res.SOURCES[m["source"]][1]})
    return flags


def resolve(fixture: dict, index, vrs, res, basis_override: dict | None = None) -> dict:
    accepted, refused = readings_for(fixture, index)
    override = (basis_override or {}).get(fixture["fixture_id"])
    if override:
        accepted = list(accepted) + [dict(o) for o in override.get("readings", [])]
        refused = list(refused) + list(override.get("refused", []))
    merged = core.blend(accepted) if accepted else None
    row = {
        "fixture_id": fixture["fixture_id"],
        "competition": fixture.get("competition"),
        "stage": fixture.get("stage"),
        "tier": fixture.get("tier"),
        "start_utc": fixture.get("start_utc"),
        "lock_utc": fixture.get("lock_utc"),
        "team_a": fixture["team_a"],
        "team_b": fixture["team_b"],
        "offered_points": fixture.get("offered_points"),
        "crowd_a": fixture.get("crowd_a_pct"),
        "crowd_b": fixture.get("crowd_b_pct"),
        "crowd_picks_total": fixture.get("crowd_picks_total"),
        "hotspawn_url": fixture.get("hotspawn_url"),
        "lobby_card": bool(fixture.get("lobby_card")),
        "discovery": fixture.get("discovery"),
        "hotspawn_url_kind": fixture.get("hotspawn_url_kind"),
        "readings": accepted,
        "refused": refused,
        "prob_a": None, "prob_b": None, "pick": None, "probability": None, "basis": None,
        "confidence": None, "source_links": [], "notes": [], "verified": True,
    }
    if merged:
        row.update(prob_a=merged["prob_a"], prob_b=merged["prob_b"],
                   basis="market", confidence="market consensus" if merged["sources"] > 1 else "single source",
                   source_links=[{"label": r["source_name"], "url": r["public_url"],
                                  "read_utc": r["retrieved_utc"], "decimal": f"{r['decimal_a']} / {r['decimal_b']}"}
                                 for r in accepted])
        row["notes"].append(f"{merged['sources']} independent external price source(s), weighted "
                            f"(Pinnacle ×2, every other accepted source ×1).")
    else:
        vrs_read = vrs_reading(fixture["team_a"], fixture["team_b"], vrs)
        if vrs_read:
            row["rating_pair"] = {
                "kind": "valve_vrs", "transform": "p_a = 1/(1+10^(-(points_a-points_b)/400))",
                "as_of": (vrs.get("as_of") or ""), "source_url": vrs.get("source_url"),
                "read_utc": vrs.get("retrieved_utc"),
                "a": {k: vrs_read["rating_a"].get(k) for k in ("name", "rank", "points")},
                "b": {k: vrs_read["rating_b"].get(k) for k in ("name", "rank", "points")},
                "delta_points": vrs_read["delta_points"]}
            row.update(prob_a=vrs_read["prob_a"], prob_b=vrs_read["prob_b"], basis="originated",
                       confidence="originated (Valve VRS)",
                       source_links=[{"label": f"Valve VRS {vrs_read['rating_a']['name']} "
                                              f"#{vrs_read['rating_a']['rank']} ({vrs_read['rating_a']['points']:.0f}) "
                                              f"vs {vrs_read['rating_b']['name']} "
                                              f"#{vrs_read['rating_b']['rank']} ({vrs_read['rating_b']['points']:.0f})",
                                      "url": vrs.get("source_url"), "read_utc": vrs.get("retrieved_utc")}])
            row["notes"].append("No external two-sided price was reachable; the line is originated from "
                                "Valve's official standings with the declared transform "
                                "p = 1/(1+10^(-Δ/400)) and is labelled ORIGINATED.")
        else:
            rank_read = rank_reading(fixture["team_a"], fixture["team_b"], BO3_TEAMS)
            if rank_read:
                row["rating_pair"] = {
                    "kind": "bo3_rank", "transform": "p_a = clamp(0.5+0.5*tanh((rank_b-rank_a)/40), 0.08, 0.92)",
                    "as_of": BO3_READ_UTC, "source_url": ("https://bo3.gg/teams/" + str(rank_read.get("slug_a") or "")),
                    "read_utc": BO3_READ_UTC,
                    "a": {"name": rank_read["name_a"], "rank": rank_read["rank_a"]},
                    "b": {"name": rank_read["name_b"], "rank": rank_read["rank_b"]},
                    "delta_rank": rank_read["delta"]}
                row.update(prob_a=rank_read["prob_a"], prob_b=rank_read["prob_b"], basis="originated",
                           confidence="originated (bo3.gg world rank)",
                           source_links=[{
                               "label": f"bo3.gg world rank: {rank_read['name_a']} #{rank_read['rank_a']} vs "
                                        f"{rank_read['name_b']} #{rank_read['rank_b']}",
                               "url": (f"https://bo3.gg/teams/{rank_read['slug_a']}" if rank_read.get("slug_a")
                                       else "https://bo3.gg/teams"),
                               "read_utc": BO3_READ_UTC}])
                row["notes"].append("No external two-sided price and no Valve rating pair; the line is "
                                    "originated from bo3.gg's published world ranks with the declared "
                                    "transform p = 0.5 + 0.5·tanh(Δrank/40), clamped to [0.08, 0.92], and "
                                    "is labelled ORIGINATED.")
            else:
                row.update(basis="blank", verified=False)
                row["notes"].append("No external price, no unambiguous Valve rating pair and no bo3.gg "
                                    "world rank for both teams — left blank.")
    if row["prob_a"] is not None:
        prefer_a = row["prob_a"] >= row["prob_b"]
        row["pick"] = fixture["team_a"] if prefer_a else fixture["team_b"]
        row["probability"] = row["prob_a"] if prefer_a else row["prob_b"]
        row["pick_own"] = crowd_of(fixture, row["pick"])
        row["other"] = fixture["team_b"] if prefer_a else fixture["team_a"]
        row["other_probability"] = row["prob_b"] if prefer_a else row["prob_a"]
        row["other_own"] = crowd_of(fixture, row["other"])
        if row["pick_own"] is not None:
            row["differential"] = round(float(row["probability"]) - float(row["pick_own"]), 6)
        row["climb"] = None
        other_diff = (None if row["other_own"] is None
                      else round(float(row["other_probability"]) - float(row["other_own"]), 6))
        row["other_differential"] = other_diff
        if other_diff is not None and other_diff > (row["differential"] or -9):
            row["climb_candidate"] = row["other"]
            row["climb_probability"] = row["other_probability"]
            row["climb_ownership"] = row["other_own"]
            row["climb_differential"] = other_diff
            row["climb_flags"] = context_flags(row["other"], row["pick"], res)
        else:
            row["climb_candidate"] = None
    return row


def twc_rows(index, vrs, res) -> list[dict]:
    rows = []
    for sf in res.TWC_DAY4:
        fixture = {
            "fixture_id": sf["fixture_id"],
            "competition": "Thunderpick World Championship 2026 (HotSpawn pick'em 35859)",
            "stage": sf["label"], "tier": sf["tier"], "start_utc": sf["start_utc"], "lock_utc": None,
            "team_a": sf["team_a"], "team_b": sf["team_b"], "offered_points": sf["offered_points"],
            "crowd_a_pct": sf["crowd_ownership"].get(sf["team_a"]),
            "crowd_b_pct": sf["crowd_ownership"].get(sf["team_b"]),
            "crowd_picks_total": None, "hotspawn_url": sf["hotspawn_url"],
            "hotspawn_url_kind": "official match page",
        }
        row = resolve(fixture, index, vrs, res)
        row["hltv_match_url"] = res.SOURCES[sf["source"]][1]
        row["read_utc"] = research.READ_UTC
        row["official_result_link"] = (f"https://www.hltv.org/matches/{sf['hltv_match_id']}")
        rows.append(row)
    return rows


def main() -> int:
    global BO3_TEAMS, BO3_READ_UTC
    snapshot = json.loads((DATA / "snapshot.json").read_text(encoding="utf-8"))
    BO3_TEAMS = snapshot.get("bo3_teams") or {}
    BO3_READ_UTC = snapshot.get("captured_utc") or ""
    fixtures = snapshot["hotspawn"]["fixtures"]
    quotes = snapshot["quotes"]
    vrs = snapshot["vrs"]
    index = index_quotes(quotes)
    measured = core.iso(core.now_utc())

    rows = [resolve(f, index, vrs, research) for f in fixtures]
    twc = twc_rows(index, vrs, research)

    # C4: activate at most three climb picks per day, only where C1 and C3 hold.
    activated = 0
    for row in twc + rows:
        cand, prob, flags = row.get("climb_candidate"), row.get("climb_probability"), row.get("climb_flags") or []
        if not cand or prob is None:
            continue
        passes = prob >= C1_MIN_PROBABILITY and (row.get("climb_differential") or -9) > 0 and len(flags) >= 2
        row["climb_gates"] = {
            "C1_probability_floor": {"required": C1_MIN_PROBABILITY, "value": prob, "pass": prob >= C1_MIN_PROBABILITY},
            "C2_positive_differential": {"value": row.get("climb_differential"), "pass": (row.get("climb_differential") or -9) > 0},
            "C3_two_context_flags": {"count": len(flags), "pass": len(flags) >= 2},
            "C4_daily_cap": {"cap": C4_MAX_CLIMB_PER_DAY, "used_before": activated, "pass": activated < C4_MAX_CLIMB_PER_DAY},
        }
        row["climb"] = cand if all(v["pass"] for v in row["climb_gates"].values()) else None
        row["climb_activated"] = bool(row["climb"])
        if row["climb"]:
            activated += 1
            row["climb_expected_differential"] = round(
                float(row.get("offered_points") or 0) * float(row["climb_differential"]), 2)

    unresolved = [r for r in rows + twc if r["basis"] == "blank"]
    originated = [r for r in rows + twc if r["basis"] == "originated"]
    market = [r for r in rows + twc if r["basis"] == "market"]
    board = {
        "session": "34af18bf",
        "generated_utc": measured,
        "fixture_capture_utc": snapshot["captured_utc"],
        "declared_weights": SOURCE_WEIGHTS,
        "gates": {"kalshi_spread": KALSHI_SPREAD_GATE, "vrs_elo_scale": VRS_ELO_SCALE,
                  "rank_scale": RANK_SCALE, "rank_clamp": RANK_CLAMP,
                  "C1_min_probability": C1_MIN_PROBABILITY, "C4_max_climb_per_day": C4_MAX_CLIMB_PER_DAY},
        "summary": {
            "open_fixtures_total": len(rows) + len(twc),
            "from_hotspawn_lobby": len(rows),
            "twc_playoff_rows": len(twc),
            "lobby_cards": sum(1 for r in rows if r.get("lobby_card")),
            "fixtures_feed_only": sum(1 for r in rows if not r.get("lobby_card")),
            "market_rows": len(market),
            "originated_rows": len(originated),
            "blank_rows": len(unresolved),
            "climb_picks_activated": sum(1 for r in rows + twc if r.get("climb")),
            "stale_lobby_rows_excluded": len(snapshot["hotspawn"].get("stale") or []),
            "sources_accepted": sorted({r["source_key"] for row in rows + twc for r in row["readings"]}),
        },
        "fixtures": rows,
        "twc": twc,
        "stale": snapshot["hotspawn"].get("stale") or [],
        "unresolved": [{"fixture_id": r["fixture_id"], "team_a": r["team_a"], "team_b": r["team_b"],
                        "competition": r["competition"], "start_utc": r["start_utc"],
                        "reason": " ".join(r["notes"]), "refused": r["refused"],
                        "hotspawn_url": r["hotspawn_url"]} for r in unresolved],
        "flag": {
            "refused_prices": [{"fixture_id": r["fixture_id"], "team_a": r["team_a"], "team_b": r["team_b"],
                                "refused": r["refused"]} for r in rows + twc if r["refused"]],
            "hotspawn_competition_scan": snapshot["hotspawn"]["competitions_swept"],
            "sources_blocked_for_the_runner": sorted(
                k for k, v in snapshot["access"].items() if isinstance(v, dict) and v.get("error")),
        },
        "access": snapshot["access"],
        "vrs": {"file": vrs.get("file"), "source_url": vrs.get("source_url"),
                "repo_url": vrs.get("repo_url"), "retrieved_utc": vrs.get("retrieved_utc"),
                "teams_tracked": len(vrs.get("teams") or {})},
    }
    (DATA / "board.json").write_text(json.dumps(board, indent=1), encoding="utf-8")

    with (DATA / "board.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["fixture_id", "competition", "start_utc", "team_a", "team_b", "pick",
                         "win_probability", "basis", "crowd_own_pick", "differential", "climb_pick",
                         "hotspawn_url", "source_url"])
        for r in rows + twc:
            writer.writerow([r["fixture_id"], r.get("competition"), r.get("start_utc"), r["team_a"],
                             r["team_b"], r.get("pick") or "", ("" if r.get("probability") is None
                                                                else f"{r['probability']:.4f}"),
                             r.get("basis"), ("" if r.get("pick_own") is None else f"{r['pick_own']:.2f}"),
                             ("" if r.get("differential") is None else f"{r['differential']:.4f}"),
                             r.get("climb") or "",
                             r.get("hotspawn_url") or "",
                             (r["source_links"][0]["url"] if r.get("source_links") else "")])
    print(json.dumps(board["summary"], indent=1))
    print("unresolved:", [r["fixture_id"] for r in unresolved])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
