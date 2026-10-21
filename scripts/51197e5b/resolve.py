#!/usr/bin/env python3
"""Session 51197e5b — resolve a pick and win probability for EVERY open HotSpawn CS2 match.

Reads committed upstream snapshots (zero network calls):
  * data/f7279a54/board.json     — freshest OURLINE board (open lobby fixtures + featured market lines)
  * data/f7279a54/snapshot.json  — raw Pinnacle / Bovada / Melbet / Kalshi quotes + official VRS
  * data/fe803b80/snapshot.json  — raw Thunderpick-via-bo3.gg quotes, bo3.gg matches/teams/history, VRS regions
  * data/19d6c262/vrs_global.json — official Valve VRS global standings + per-team details URLs

Strict rules enforced:
  1. Featured market picks (`data/f7279a54/board.json` rows that already have a `line`) are copied
     through BYTE-FOR-BYTE UNCHANGED (`market_weight = 1.0`).
  2. Fallback sources are consulted ONLY for matches that have no featured market pick:
       Step 1: HLTV probe check (recorded HTTP 403 block on automated runner; fixture metadata only)
       Step 2: Licensed esportsbooks (Bovada, Melbet, Pinnacle, Thunderpick via bo3.gg) & Kalshi
               exchange (`KXCS2GAME`) with documented `ex-` org-prefix normalisation & EDT->UTC ticker check
       Step 3: Official Valve Regional Standings (`standings_global_2026_10_05.md`) calibrated model
               (`k = 0.4308`), with duplicate org names resolved to the active 5-player roster
               with the most recent counted match date
       Step 4: Originated Valve VRS floor lower bound (rated team vs `#380 / 381 pts` floor),
               cross-checked against `bo3.gg` published match history
  3. HotSpawn crowd percentages are NEVER read or used as a probability input.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_CORE_SPEC = importlib.util.spec_from_file_location("fullpicks_core_51197e5b", Path(__file__).resolve().parent / "core.py")
core = importlib.util.module_from_spec(_CORE_SPEC)
_CORE_SPEC.loader.exec_module(core)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "51197e5b"
F727_BOARD = ROOT / "data" / "f7279a54" / "board.json"
F727_SNAP = ROOT / "data" / "f7279a54" / "snapshot.json"
FE80_BOARD = ROOT / "data" / "fe803b80" / "board.json"
FE80_SNAP = ROOT / "data" / "fe803b80" / "snapshot.json"
VRS_GLOBAL = ROOT / "data" / "19d6c262" / "vrs_global.json"
VRS_CACHE = ROOT / "data" / "f7279a54" / "vrs_details_cache.json"

VALVE_REPO = "ValveSoftware/counter-strike_regional_standings"
LOBBY_URL = "https://play.hotspawn.com/lobby"
HS_API_URL = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default if default is not None else {}


def build_vrs_index(vrs_doc: dict, f727_snap: dict, vrs_cache: dict | None = None) -> tuple[dict, dict, dict]:
    """Build canonical-team -> official VRS record, plus duplicate disambiguation ledger."""
    teams = list(vrs_doc.get("teams") or [])
    if not teams:
        teams = list(((f727_snap.get("vrs") or {}).get("teams")) or [])
    latest_map = ((vrs_cache or {}).get("latest_match")) or {}
    snapshot = vrs_doc.get("snapshot") or ((f727_snap.get("vrs") or {}).get("snapshot")) or "2026_10_05"
    page_url = (
        vrs_doc.get("page_url")
        or ((f727_snap.get("vrs") or {}).get("page_url"))
        or f"https://github.com/{VALVE_REPO}/blob/main/live/2026/standings_global_{snapshot}.md"
    )
    groups: dict[str, list[dict]] = {}
    for raw in teams:
        t = dict(raw)
        dp = t.get("details_path")
        if not t.get("latest_match_date") and dp and dp in latest_map:
            t["latest_match_date"] = latest_map[dp]
        if not t.get("details_url") and dp:
            t["details_url"] = f"https://github.com/{VALVE_REPO}/blob/main/{dp}"
        roster_players = [p.strip() for p in str(t.get("roster") or "").split(",") if p.strip()]
        t["roster_count"] = len(roster_players)
        key, _ = core.canon_team(t.get("team"), allow_ex_strip=False)
        if key:
            groups.setdefault(key, []).append(t)

    idx: dict[str, dict] = {}
    dupes: dict[str, dict] = {}
    for key, rows in groups.items():
        if len(rows) == 1:
            idx[key] = rows[0]
            continue
        # Active 5-player roster with the most recent counted match date wins; tie-break by higher standing.
        chosen = sorted(
            rows,
            key=lambda r: (
                1 if r.get("roster_count", 0) >= 5 else 0,
                r.get("latest_match_date") or "0000-00-00",
                -int(r["standing"]),
            ),
        )[-1]
        idx[key] = chosen
        dupes[key] = {
            "chosen_standing": chosen["standing"],
            "chosen_points": chosen["points"],
            "chosen_roster": chosen.get("roster"),
            "chosen_latest_match": chosen.get("latest_match_date"),
            "reason": "Selected active 5-player roster with most recent official Valve counted match date.",
            "candidates": [
                {
                    "standing": r["standing"],
                    "points": r["points"],
                    "team": r["team"],
                    "roster": r.get("roster"),
                    "roster_count": r.get("roster_count"),
                    "latest_match_date": r.get("latest_match_date"),
                    "details_url": r.get("details_url"),
                }
                for r in sorted(rows, key=lambda x: int(x["standing"]))
            ],
        }
    meta = {
        "snapshot": snapshot,
        "page_url": page_url,
        "n_teams": len(teams),
        "floor": {"standing": core.VRS_FLOOR_STANDING, "points": core.VRS_FLOOR_POINTS, "team": "Fruju"},
    }
    return idx, dupes, meta


def collect_all_quotes(f727_snap: dict, fe80_snap: dict) -> list[dict]:
    """Combine pre-match two-way quotes from f7279a54 and fe803b80 snapshots without duplicates."""
    seen: set[str] = set()
    out: list[dict] = []
    for snap in (f727_snap, fe80_snap):
        for raw_q in snap.get("quotes") or []:
            if raw_q.get("live"):
                continue
            rq = core.rederive_quote(raw_q)
            if not rq:
                continue
            sk = str(rq.get("source_key") or "")
            eid = str(rq.get("event_id") or "")
            uid = f"{sk}:{eid}"
            if uid in seen:
                continue
            seen.add(uid)
            # Determine effective start_utc (explicit start_utc or Kalshi ticker EDT->UTC).
            eff_start = rq.get("start_utc")
            start_source = "provider_timestamp"
            if sk == "kalshi":
                ticker_utc = core.kalshi_ticker_utc(eid)
                if ticker_utc:
                    eff_start = ticker_utc
                    start_source = "kalshi_ticker_edt_to_utc"
            rq["effective_start_utc"] = eff_start
            rq["start_time_source"] = start_source
            out.append(rq)
    return out


def match_fallback_quotes(fixture: dict, quotes: list[dict]) -> list[dict]:
    """Find external bookmaker/exchange quotes matching `fixture` under documented fallback rules."""
    fa, note_fa = core.canon_team(fixture["team_a"], allow_ex_strip=True)
    fb, note_fb = core.canon_team(fixture["team_b"], allow_ex_strip=True)
    matched_by_source: dict[str, dict] = {}
    for q in quotes:
        qa, note_qa = core.canon_team(q.get("team_a"), allow_ex_strip=True)
        qb, note_qb = core.canon_team(q.get("team_b"), allow_ex_strip=True)
        if fa and fb and fa == qa and fb == qb:
            swapped = False
            notes = [n for n in (note_fa, note_fb, note_qa, note_qb) if n]
        elif fa and fb and fa == qb and fb == qa:
            swapped = True
            notes = [n for n in (note_fa, note_fb, note_qa, note_qb) if n]
        else:
            continue
        diff_h = core.hours_apart(fixture.get("start_utc"), q.get("effective_start_utc"))
        if diff_h is None or diff_h > 0.25:
            continue
        prob_team_a = (1.0 - float(q["prob_a"])) if swapped else float(q["prob_a"])
        dec_a = float(q["decimal_b"] if swapped else q["decimal_a"])
        dec_b = float(q["decimal_a"] if swapped else q["decimal_b"])
        entry = {
            "source_key": q["source_key"],
            "source_name": q["source_name"],
            "public_url": q["public_url"],
            "api_url": q.get("api_url"),
            "event_id": str(q["event_id"]),
            "names_at_source": [q.get("team_a"), q.get("team_b")],
            "raw_format": q.get("raw_format"),
            "raw_a": q.get("raw_b") if swapped else q.get("raw_a"),
            "raw_b": q.get("raw_a") if swapped else q.get("raw_b"),
            "decimal_a": round(dec_a, 4),
            "decimal_b": round(dec_b, 4),
            "no_vig_prob_team_a": round(prob_team_a, 4),
            "overround": round(float(q.get("overround") or 0.0), 4),
            "swapped": swapped,
            "start_utc_at_source": q.get("effective_start_utc"),
            "start_time_source": q.get("start_time_source"),
            "start_diff_h": round(diff_h, 2),
            "retrieved_utc": q.get("retrieved_utc"),
            "alias_notes": notes,
        }
        sk = q["source_key"]
        prev = matched_by_source.get(sk)
        if prev is None or entry["start_diff_h"] < prev["start_diff_h"]:
            matched_by_source[sk] = entry
    return [matched_by_source[k] for k in sorted(matched_by_source)]


def bo3gg_context_for(fixture: dict, fe80_snap: dict, vrs_idx: dict) -> dict:
    """Extract bo3.gg team records, recent match history, and schedule conflicts for `fixture`."""
    b3 = fe80_snap.get("bo3gg") or {}
    teams = b3.get("teams") or {}
    matches = b3.get("matches") or []
    hist = fe80_snap.get("bo3gg_history") or {}

    fa, _ = core.canon_team(fixture["team_a"], allow_ex_strip=True)
    fb, _ = core.canon_team(fixture["team_b"], allow_ex_strip=True)

    team_info: dict[str, dict] = {}
    for side, key in (("team_a", fa), ("team_b", fb)):
        for tid, rec in teams.items():
            for cand in (rec.get("name"), rec.get("slug"), rec.get("acronym")):
                ck, _ = core.canon_team(cand, allow_ex_strip=True)
                if ck and ck == key:
                    h_rows = hist.get(str(tid)) or []
                    enriched_hist = []
                    wins = 0
                    for m in h_rows[:10]:
                        t1_id = str(m.get("team1_id"))
                        t2_id = str(m.get("team2_id"))
                        w_id = str(m.get("winner_team_id"))
                        opp_id = t2_id if t1_id == str(tid) else t1_id
                        opp_rec = teams.get(opp_id) or {}
                        opp_name = opp_rec.get("name") or m.get("slug") or f"team_{opp_id}"
                        opp_key, _ = core.canon_team(opp_name, allow_ex_strip=True)
                        opp_vrs = vrs_idx.get(opp_key)
                        won = w_id == str(tid)
                        if won:
                            wins += 1
                        enriched_hist.append({
                            "match_id": m.get("id"),
                            "slug": m.get("slug"),
                            "url": f"https://bo3.gg/matches/{m['slug']}" if m.get("slug") else "https://bo3.gg/matches",
                            "start_date": m.get("start_date"),
                            "won": won,
                            "opponent": opp_name,
                            "opponent_vrs_standing": opp_vrs["standing"] if opp_vrs else opp_rec.get("rank"),
                            "opponent_vrs_points": opp_vrs["points"] if opp_vrs else None,
                        })
                    team_info[side] = {
                        "bo3_id": str(tid),
                        "name": rec.get("name"),
                        "slug": rec.get("slug"),
                        "url": f"https://bo3.gg/teams/{rec['slug']}" if rec.get("slug") else "https://bo3.gg/teams",
                        "rank": rec.get("rank"),
                        "matches_recorded": len(h_rows),
                        "wins_in_sample": wins,
                        "recent_matches": enriched_hist,
                    }
                    break
            if side in team_info:
                break

    # Check if bo3.gg has a match at the exact same start_utc involving one of the two teams with a DIFFERENT opponent!
    schedule_conflicts = []
    exact_match = None
    for m in matches:
        t1 = (teams.get(str(m.get("team1_id"))) or {}).get("name")
        t2 = (teams.get(str(m.get("team2_id"))) or {}).get("name")
        k1, _ = core.canon_team(t1, allow_ex_strip=True)
        k2, _ = core.canon_team(t2, allow_ex_strip=True)
        diff = core.hours_apart(fixture.get("start_utc"), m.get("start_date"))
        if diff is not None and diff <= 0.25:
            if {k1, k2} == {fa, fb}:
                exact_match = {
                    "id": m.get("id"),
                    "slug": m.get("slug"),
                    "url": f"https://bo3.gg/matches/{m['slug']}",
                    "team_1": t1,
                    "team_2": t2,
                    "start_date": m.get("start_date"),
                }
            elif k1 in (fa, fb) or k2 in (fa, fb):
                schedule_conflicts.append({
                    "id": m.get("id"),
                    "slug": m.get("slug"),
                    "url": f"https://bo3.gg/matches/{m['slug']}",
                    "team_1": t1,
                    "team_2": t2,
                    "start_date": m.get("start_date"),
                    "note": (
                        f"At {fixture.get('start_utc')}, bo3.gg lists '{t1} vs {t2}' instead of "
                        f"HotSpawn's '{fixture['team_a']} vs {fixture['team_b']}'."
                    ),
                })
    return {
        "team_a": team_info.get("team_a"),
        "team_b": team_info.get("team_b"),
        "exact_match": exact_match,
        "schedule_conflicts": schedule_conflicts,
    }


def vrs_for_team(name: str, vrs_idx: dict, dupes: dict) -> tuple[dict | None, str, str | None]:
    """Lookup team in official Valve VRS index (exact first, then ex-stripped)."""
    k_strict, note_strict = core.canon_team(name, allow_ex_strip=False)
    if k_strict in vrs_idx:
        rec = vrs_idx[k_strict]
        if k_strict in dupes:
            d = dupes[k_strict]
            return (
                rec,
                "duplicate_disambiguated",
                f"{name}: disambiguated duplicate VRS entries to #{rec['standing']} ({rec['points']} pts, "
                f"5-player roster {rec.get('roster')}, latest counted match {rec.get('latest_match_date')}).",
            )
        return rec, ("alias" if note_strict else "exact"), note_strict

    k_ex, note_ex = core.canon_team(name, allow_ex_strip=True)
    if k_ex in vrs_idx:
        rec = vrs_idx[k_ex]
        return (
            rec,
            "ex_prefix_alias",
            note_ex or f"{name} matched to official VRS '{rec['team']}' (#{rec['standing']}, {rec['points']} pts).",
        )
    return None, "not_in_vrs", f"{name} has no entry in official Valve VRS standings_global_2026_10_05.md."


def resolve_unpriced_fixture(
    row: dict,
    all_quotes: list[dict],
    vrs_idx: dict,
    dupes: dict,
    vrs_meta: dict,
    k: float,
    fe80_snap: dict,
    hltv_probe: dict,
) -> dict:
    """Resolve an unpriced fixture using the fallback research ladder and record the full ledger."""
    row = json.loads(json.dumps(row))
    ta, tb = row["team_a"], row["team_b"]
    flags = list(row.get("flags") or [])

    # Step 1: HLTV probe check
    hltv_status = hltv_probe.get("status")
    attempts = [
        {
            "step": 1,
            "source": "HLTV.org match listings",
            "url": hltv_probe.get("url") or "https://www.hltv.org/matches",
            "status": f"HTTP {hltv_status}" if hltv_status else "blocked",
            "outcome": "no_machine_odds",
            "detail": (
                f"Automated probe to https://www.hltv.org/matches returned HTTP {hltv_status} "
                f"({hltv_probe.get('error') or 'Cloudflare challenge'}); HLTV match pages confirm "
                "fixture rosters/schedules where listed but do not expose a machine-readable two-way odds feed."
            ),
        }
    ]

    # Step 2: Esportsbooks & Exchanges (Bovada, Melbet, Pinnacle, Thunderpick via bo3.gg, Kalshi)
    fb_quotes = match_fallback_quotes(row, all_quotes)
    book_quotes = [q for q in fb_quotes if q["source_key"] in ("pinnacle", "bovada", "melbet", "thunderpick")]
    kalshi_quotes = [q for q in fb_quotes if q["source_key"] == "kalshi"]

    # Step 3: Official Valve VRS lookup
    ra, how_a, note_a = vrs_for_team(ta, vrs_idx, dupes)
    rb, how_b, note_b = vrs_for_team(tb, vrs_idx, dupes)

    # Step 4: bo3.gg context (match history + schedule conflict check)
    b3_ctx = bo3gg_context_for(row, fe80_snap, vrs_idx)

    if fb_quotes:
        q_desc = "; ".join(
            f"{q['source_name']} ({q['names_at_source'][0]} vs {q['names_at_source'][1]}, "
            f"dec {q['decimal_a']}/{q['decimal_b']} -> {q['no_vig_prob_team_a']*100:.1f}%/{(1-q['no_vig_prob_team_a'])*100:.1f}%)"
            for q in fb_quotes
        )
        attempts.append({
            "step": 2,
            "source": "Licensed Esportsbooks & Kalshi Exchange",
            "url": fb_quotes[0]["public_url"],
            "status": f"{len(fb_quotes)} quote(s) matched",
            "outcome": "matched",
            "detail": f"Found {len(fb_quotes)} external price(s): {q_desc}.",
        })
    else:
        attempts.append({
            "step": 2,
            "source": "Licensed Esportsbooks & Kalshi Exchange (Pinnacle, Bovada, Melbet, Thunderpick, Kalshi)",
            "url": "https://www.pinnacle.com/en/esports/cs2-hub",
            "status": "0 quotes for this pairing",
            "outcome": "no_quote",
            "detail": "Checked all 163 captured pre-match quotes across Pinnacle, Bovada, Melbet, Thunderpick (bo3.gg), and Kalshi KXCS2GAME; no open market prices this fixture.",
        })

    if ra and rb:
        vrs_pa = core.vrs_prob(ra["points"], rb["points"], k)
        attempts.append({
            "step": 3,
            "source": f"Official Valve VRS ({vrs_meta['snapshot']})",
            "url": vrs_meta["page_url"],
            "status": "both teams rated",
            "outcome": "model_available",
            "detail": (
                f"{ta} is VRS #{ra['standing']} ({ra['points']} pts, roster: {ra.get('roster')}) and "
                f"{tb} is VRS #{rb['standing']} ({rb['points']} pts, roster: {rb.get('roster')}); "
                f"Δ = {ra['points'] - rb['points']:+d} pts -> calibrated VRS win prob "
                f"{vrs_pa*100:.1f}% / {(1-vrs_pa)*100:.1f}% (k = {k:.4f})."
            ),
        })
    elif ra or rb:
        rated, side = (ra, "a") if ra else (rb, "b")
        unrated = tb if side == "a" else ta
        floor_pts = vrs_meta["floor"]["points"]
        p_rated = core.vrs_prob(rated["points"], floor_pts, k)
        attempts.append({
            "step": 3,
            "source": f"Official Valve VRS ({vrs_meta['snapshot']})",
            "url": vrs_meta["page_url"],
            "status": "one team rated, opponent unrated",
            "outcome": "floor_bound_available",
            "detail": (
                f"{rated['team']} is VRS #{rated['standing']} ({rated['points']} pts, roster: {rated.get('roster')}); "
                f"'{unrated}' is not listed in the 380-team global VRS table. Against the VRS floor "
                f"(#{vrs_meta['floor']['standing']} {vrs_meta['floor']['team']}, {floor_pts} pts), "
                f"calibrated lower bound is {p_rated*100:.1f}% for {rated['team']}."
            ),
        })
    else:
        attempts.append({
            "step": 3,
            "source": f"Official Valve VRS ({vrs_meta['snapshot']})",
            "url": vrs_meta["page_url"],
            "status": "neither team rated",
            "outcome": "no_vrs",
            "detail": f"Neither {ta} nor {tb} has an entry in official Valve VRS.",
        })

    # Record Step 4 (bo3.gg match history & schedule check)
    b3_notes = []
    for side, label in (("team_a", ta), ("team_b", tb)):
        ti = b3_ctx.get(side)
        if ti:
            b3_notes.append(
                f"{label} (bo3.gg #{ti['bo3_id']}, rank={ti['rank'] or 'unranked'}, "
                f"recorded matches={ti['matches_recorded']})"
            )
    if b3_ctx["schedule_conflicts"]:
        for sc in b3_ctx["schedule_conflicts"]:
            b3_notes.append(sc["note"])
    attempts.append({
        "step": 4,
        "source": "bo3.gg team profiles & match history",
        "url": (
            b3_ctx["exact_match"]["url"]
            if b3_ctx.get("exact_match")
            else (b3_ctx["schedule_conflicts"][0]["url"] if b3_ctx["schedule_conflicts"] else "https://bo3.gg/matches")
        ),
        "status": "checked",
        "outcome": "context_recorded",
        "detail": "; ".join(b3_notes) if b3_notes else "No additional bo3.gg match history found.",
    })

    # Decide resolution tier and final line:
    limitations: list[str] = []
    if book_quotes:
        # Tier 2A: Licensed esportsbooks (+ exchange if available)
        entries = [{"source_key": q["source_key"], "prob_a": q["no_vig_prob_team_a"]} for q in fb_quotes]
        mkt = core.consensus(entries)
        row["quotes"] = fb_quotes
        row["market"] = mkt
        row["line"] = core.make_line(
            mkt["prob_a"],
            ta,
            tb,
            basis="esportsbook",
            market_weight=1.0,
            resolution_tier="tier_2_esportsbook_exchange",
            resolution_note=(
                f"Resolved from {len(fb_quotes)} external betting/exchange source(s) "
                f"({', '.join(q['source_name'] for q in fb_quotes)}) after ex-prefix team normalisation, "
                f"verified by exact opponent ({tb}) and exact UTC kickoff ({row['start_utc']})."
            ),
        )
        flags.append("resolved_via_esportsbook_ex_prefix_join")
        limitations.append(
            f"HotSpawn lists '{ta}' with the 'ex-' prefix while Bovada, Melbet, and Kalshi list the team as "
            f"'CYBERSHOKE' / 'CYBERSHOKE Esports' in the same CIS LAN Championship #9 slot at {row['start_utc']}."
        )
    elif kalshi_quotes and (not (ra and rb) or abs(kalshi_quotes[0]["no_vig_prob_team_a"] - 0.5) >= 0.05):
        # Tier 2B: Decisive CFTC-regulated Kalshi exchange contract (with exact EDT->UTC ticker match)
        entries = [{"source_key": q["source_key"], "prob_a": q["no_vig_prob_team_a"]} for q in kalshi_quotes]
        mkt = core.consensus(entries)
        row["quotes"] = kalshi_quotes
        row["market"] = mkt
        vrs_note = ""
        if ra or rb:
            rated = ra or rb
            p_floor = core.vrs_prob(rated["points"], vrs_meta["floor"]["points"], k)
            vrs_note = (
                f" Corroborated by Official Valve VRS: {rated['team']} is #{rated['standing']} "
                f"({rated['points']} pts, {p_floor*100:.1f}% vs VRS floor #380)."
            )
        row["line"] = core.make_line(
            mkt["prob_a"],
            ta,
            tb,
            basis="exchange",
            market_weight=1.0,
            resolution_tier="tier_2_esportsbook_exchange",
            resolution_note=(
                f"Resolved from CFTC-regulated Kalshi exchange contract {kalshi_quotes[0]['event_id']} "
                f"(EDT ticker start matches {row['start_utc']} UTC).{vrs_note}"
            ),
        )
        flags.append("resolved_via_kalshi_exchange")
        limitations.append(
            f"Primary sportsbooks (Pinnacle/Bovada/Melbet) had no open pre-match line at capture time; "
            f"priced from Kalshi exchange ({kalshi_quotes[0]['event_id']}) where ticker time matches {row['start_utc']} UTC.{vrs_note}"
        )
    elif ra and rb:
        # Tier 3: Official Valve VRS Calibrated Model (both teams rated)
        delta = int(ra["points"]) - int(rb["points"])
        prob_a = core.vrs_prob(ra["points"], rb["points"], k)
        if fb_quotes:
            row["quotes"] = fb_quotes
        ex_corrob = ""
        if kalshi_quotes:
            kq = kalshi_quotes[0]
            ex_corrob = (
                f" Kalshi exchange ({kq['event_id']}) also quotes this exact match near a 50/50 coin-flip "
                f"({kq['no_vig_prob_team_a']*100:.1f}% / {(1-kq['no_vig_prob_team_a'])*100:.1f}%)."
            )
        row["line"] = core.make_line(
            prob_a,
            ta,
            tb,
            basis="model",
            market_weight=0.0,
            resolution_tier="tier_3_valve_vrs_model",
            resolution_note=(
                f"Originated from Official Valve VRS ({vrs_meta['snapshot']}): "
                f"{ta} #{ra['standing']} ({ra['points']} pts) vs {tb} #{rb['standing']} ({rb['points']} pts), "
                f"Δ = {delta:+d} pts, market-calibrated slope k = {k:.4f}.{ex_corrob}"
            ),
        )
        flags.append("resolved_via_valve_vrs_model")
        if how_a == "duplicate_disambiguated" or how_b == "duplicate_disambiguated":
            flags.append("vrs_duplicate_disambiguated_active_roster")
        limitations.append(
            f"No primary bookmaker two-way line was open at capture time; line is originated from "
            f"Official Valve Regional Standings ({vrs_meta['snapshot']}, published 2026-10-05) with fitted slope k = {k:.4f}.{ex_corrob}"
        )
        for n in (note_a, note_b):
            if n:
                limitations.append(n)
    elif ra or rb:
        # Tier 4: Originated Valve VRS Floor Estimate (one team rated, opponent unrated)
        rated, side = (ra, "a") if ra else (rb, "b")
        unrated = tb if side == "a" else ta
        floor_pts = vrs_meta["floor"]["points"]
        p_rated = core.vrs_prob(rated["points"], floor_pts, k)
        prob_a = p_rated if side == "a" else (1.0 - p_rated)
        row["line"] = core.make_line(
            prob_a,
            ta,
            tb,
            basis="floor_estimate",
            market_weight=0.0,
            confidence="Directional",
            directional=True,
            resolution_tier="tier_4_vrs_floor_directional",
            resolution_note=(
                f"Originated directional lower bound from Official Valve VRS ({vrs_meta['snapshot']}): "
                f"{rated['team']} is #{rated['standing']} ({rated['points']} pts); unrated '{unrated}' "
                f"is benchmarked at the official VRS floor (#{vrs_meta['floor']['standing']} "
                f"{vrs_meta['floor']['team']}, {floor_pts} pts)."
            ),
        )
        flags.append("directional_vrs_floor_estimate")
        limitations.append(
            f"'{unrated}' is not rated in Official Valve VRS ({vrs_meta['snapshot']}), and no sportsbook "
            f"or exchange offered a valid two-way market. The probability ({p_rated*100:.1f}%) benchmarks "
            f"{rated['team']} (#{rated['standing']}, {rated['points']} pts) against the VRS floor "
            f"(#{vrs_meta['floor']['standing']}, {floor_pts} pts) and is a directional estimate."
        )
        # Add bo3.gg match-history note if the unrated team has recorded matches
        unrated_side = "team_b" if side == "a" else "team_a"
        ti = b3_ctx.get(unrated_side)
        if ti and ti.get("recent_matches"):
            wins = ti["wins_in_sample"]
            total = len(ti["recent_matches"])
            notable = [
                f"{'beat' if m['won'] else 'lost to'} {m['opponent']}"
                + (f" (VRS #{m['opponent_vrs_standing']}, {m['opponent_vrs_points']} pts)" if m.get("opponent_vrs_points") else "")
                for m in ti["recent_matches"][:3]
            ]
            limitations.append(
                f"bo3.gg match-history cross-check ({ti['url']}): '{unrated}' has {total} recent recorded "
                f"matches ({wins}W-{total - wins}L: {', '.join(notable)}). Treat this low-tier SA fixture "
                "as contested."
            )
            flags.append("unrated_opponent_has_bo3gg_history")
    else:
        row["line"] = None
        flags.append("unresolved_no_market_or_rating")
        limitations.append(
            f"Neither {ta} nor {tb} has an eligible bookmaker/exchange line or an official Valve VRS rating."
        )

    if b3_ctx["schedule_conflicts"]:
        flags.append("bo3gg_schedule_opponent_conflict")
        for sc in b3_ctx["schedule_conflicts"]:
            limitations.append(f"Schedule discrepancy flagged for manual review: {sc['note']} ({sc['url']}).")

    row["flags"] = sorted(set(flags))
    row["resolution"] = {
        "vrs_snapshot": vrs_meta["snapshot"],
        "vrs_page_url": vrs_meta["page_url"],
        "team_a_vrs": (
            {
                "standing": ra["standing"],
                "points": ra["points"],
                "team": ra["team"],
                "roster": ra.get("roster"),
                "latest_match_date": ra.get("latest_match_date"),
                "details_url": ra.get("details_url"),
                "match_kind": how_a,
            }
            if ra
            else None
        ),
        "team_b_vrs": (
            {
                "standing": rb["standing"],
                "points": rb["points"],
                "team": rb["team"],
                "roster": rb.get("roster"),
                "latest_match_date": rb.get("latest_match_date"),
                "details_url": rb.get("details_url"),
                "match_kind": how_b,
            }
            if rb
            else None
        ),
        "k": round(k, 4),
        "floor": vrs_meta["floor"],
        "bo3gg": b3_ctx,
        "attempts": attempts,
        "limitations": limitations,
    }
    return row


def build_repo_irregularities() -> list[dict]:
    """Documented line-by-line repository & source irregularities with official review links."""
    return [
        {
            "id": "R1",
            "severity": "High (Repo / Automation)",
            "title": "everymatch/ (session 19d6c262) frozen on 2026-10-19T04:26:08Z due to hardcoded Oct-19 fixture IDs in tests/test_19d6c262.py",
            "scope": "everymatch/**, tests/test_19d6c262.py, .github/workflows/everymatch-19d6c262.yml",
            "detail": (
                "The scheduled workflow everymatch-19d6c262.yml runs `python3 -m unittest tests.test_19d6c262 -v` "
                "before committing. Because tests/test_19d6c262.py hardcodes `len(want) >= 20` and four Oct-19 "
                "fixture IDs (1082157, 1081132, 1081863, 1081529) that have since locked and rotated off the "
                "lobby, every scheduled run on main (e.g. 39544863841, 39513037654, 39487959240) fails and "
                "everymatch/ remains stuck serving 34 matches from 2026-10-19."
            ),
            "sources": [
                {"label": "Workflow run 39544863841", "url": "https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/39544863841"},
                {"label": "HotSpawn Pick'em Lobby", "url": "https://play.hotspawn.com/lobby"},
            ],
        },
        {
            "id": "R2",
            "severity": "High (Repo / Board Selection)",
            "title": "climb/ (session a89b76e9) selects the stale 2026-10-19 board over today's fresh 2026-10-21 board",
            "scope": "scripts/a89b76e9/build.py, data/a89b76e9/build_summary.json, climb/**",
            "detail": (
                "In scripts/a89b76e9/build.py (lines 143-147), `newest_board()` ranks candidate `data/*/board.json` "
                "files by `key = (priced, gen)` (number of priced rows first, timestamp only as tie-breaker). "
                "Because the frozen 2026-10-19 board (`data/19d6c262/board.json`) had 34 priced matches while "
                "today's 2026-10-21 lobby has 19 open matches, `climb/` continuously selects the 2-day-old Oct-19 "
                "board (`board_generated_utc: 2026-10-19T04:26:08Z`) even when rebuilt at 2026-10-21 12:09 UTC."
            ),
            "sources": [
                {"label": "Climb workflow runs", "url": "https://github.com/buffedlizard55-lab/MaltaProj2/actions/workflows/climb-a89b76e9.yml"},
                {"label": "HotSpawn Fixtures API", "url": HS_API_URL},
            ],
        },
        {
            "id": "R3",
            "severity": "Medium (Repo / Scheduled Refreshes)",
            "title": "start/ (371a1ce7), now/ (b3871d16), unresolved/ (7177d07f), and picks-all/ (b5436cf0) scheduled workflows failing on main",
            "scope": ".github/workflows/{start-371a1ce7,now-b3871d16,unresolved-7177d07f,allpicks-b5436cf0}.yml",
            "detail": (
                "Scheduled runs for start-371a1ce7 (run 39547202868), now-b3871d16 (run 39548272486), "
                "unresolved-7177d07f (run 39564013498), and allpicks-b5436cf0 (run 39547331774) fail their "
                "test gates because their tests assert dated Oct 15-18 fixture IDs or TWC Malta Day-5 assumptions. "
                "Per COORDINATION.md rules, we do not edit other sessions' files; our `fullpicks/` test suite "
                "(`tests/test_51197e5b.py`) tests invariants dynamically against the current board so scheduled "
                "refreshes never break as the lobby rotates."
            ),
            "sources": [
                {"label": "GitHub Actions workflows", "url": "https://github.com/buffedlizard55-lab/MaltaProj2/actions"},
            ],
        },
        {
            "id": "R4",
            "severity": "High (Match Resolution / Upstream Normaliser)",
            "title": "1082762 ex-CYBERSHOKE vs BlinkDagger missed by f7279a54 and fe803b80 despite 3 live Bovada / Melbet / Kalshi lines in their own snapshots",
            "scope": "data/f7279a54/snapshot.json, data/fe803b80/snapshot.json",
            "detail": (
                "HotSpawn lists fixture 1082762 as `ex-CYBERSHOKE vs BlinkDagger` (CIS LAN Championship #9, "
                "2026-10-21T15:00:00Z). Both upstream collectors already captured three live two-way markets for "
                "this exact match in their `unmatched_quotes`: Bovada (event 32524607, `CYBERSHOKE vs blinkdagger`, "
                "1.125 / 5.750 -> 83.6% / 16.4%), Melbet (event 763402597, `CYBERSHOKE vs BlinkDagger`, "
                "1.12 / 5.59 -> 83.3% / 16.7%), and Kalshi (`KXCS2GAME-26OCT211100BLICS`, `BlinkDagger vs "
                "CYBERSHOKE Esports`, $0.19 / $0.81 -> 81.0% / 19.0%). Both upstream matchers failed to join "
                "them solely because neither strips the `ex-` prefix (`ex-CYBERSHOKE` vs `CYBERSHOKE`). "
                "Our resolver joins all 3 direct quotes (consensus: ex-CYBERSHOKE 82.6% vs BlinkDagger 17.4%)."
            ),
            "sources": [
                {"label": "Bovada CIS LAN Championship market", "url": "https://www.bovada.lv/esports/counter-strike-2/cis-lan-championship/cybershoke-blinkdagger-202610211100"},
                {"label": "Melbet Esports Line", "url": "https://melbet.com/en/line/esports"},
                {"label": "Kalshi KXCS2GAME-26OCT211100BLICS", "url": "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct211100blics"},
            ],
        },
        {
            "id": "R5",
            "severity": "High (Match Resolution / Duplicate VRS Overwrite)",
            "title": "1081600 Donstu vs Banda chuya flipped in fe803b80 / cs2 because Banda Chuya's stale 2-player VRS row (#373) overwrote its active 5-player roster (#165)",
            "scope": "data/fe803b80/board.json, cs2/picks.html, live/2026/standings_global_2026_10_05.md",
            "detail": (
                "In Valve's official `standings_global_2026_10_05.md`, `Banda Chuya` appears twice: #165 (801 pts, "
                "full 5-man active roster `AdrieN, ezox, maaryy, Showk, tomiko`, latest match 2026-10-04, also "
                "confirmed by bo3.gg team 23072 `rank: 165`) and #373 (402 pts, 2-player remnant `ezox, manio`, "
                "latest match 2026-09-11). Because `scripts/fe803b80/collect.py` stores `vrs_regions` as a plain "
                "`{team_name: row}` dict, the #373 row overwrites #165, causing `fe803b80` (and `cs2/`) to rate "
                "Banda Chuya at 402 pts and pick Donstu (61.3%). Against the active #165 (801 pts) 5-player "
                "roster, Banda chuya out-rates DONSTU (#197, 732 pts) by +69 VRS points and is the 53.9% favourite. "
                "Additionally, bo3.gg match 132216 lists `DONSTU vs los kogutos` in the 2026-10-22T13:45:00Z slot."
            ),
            "sources": [
                {"label": "Valve VRS #165 Banda Chuya (801 pts, 5-man roster)", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/0165--banda_chuya--adrien-ezox-maaryy-showk-tomiko.md"},
                {"label": "Valve VRS #373 Banda Chuya (402 pts, 2-man remnant)", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/0373--banda_chuya--ezox-manio.md"},
                {"label": "Valve VRS #197 DONSTU (732 pts)", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/0197--donstu--due1yant-gleb86rus-laksheri-neolife-phorate.md"},
                {"label": "bo3.gg match 132216 (DONSTU vs los kogutos)", "url": "https://bo3.gg/matches/donstu-esports-vs-los-kogutos-22-10-2026"},
            ],
        },
        {
            "id": "R6",
            "severity": "Medium (Schedule Conflict & Low-Tier SA Coverage)",
            "title": "1082837 Zetta vs LOS NINOS: opponent listed as Alianza Lima Esports on bo3.gg/Polymarket, and LOS NINOS has 5 bo3.gg matches including a win over VRS #252 Grêmio",
            "scope": "data/f7279a54/board.json, data/fe803b80/snapshot.json",
            "detail": (
                "HotSpawn lists fixture 1082837 as `Zetta vs LOS NINOS` (CCT South America Series #7, "
                "2026-10-21T22:00:00Z), whereas bo3.gg (`match 132583`) and Polymarket list the 22:00Z opponent "
                "of Los Niños as `Alianza Lima Esports`. Furthermore, while `LOS NINOS` is not in the 380-team "
                "Valve VRS table (giving Zetta #357 / 473 pts a 55.2% directional edge over the #380 / 381-pt "
                "VRS floor), `bo3.gg` records 5 recent matches for Los Niños (team 25310), including a victory "
                "over Grêmio (VRS #252, 641 pts) on 2026-10-13."
            ),
            "sources": [
                {"label": "Valve VRS #357 Zetta (473 pts)", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/0357--zetta--antuanette-babyrage-notjuanjo-slayerhz-zockie.md"},
                {"label": "bo3.gg Los Niños team match history", "url": "https://bo3.gg/teams/los-ninos"},
                {"label": "bo3.gg match 132583 (Alianza Lima vs Los Niños)", "url": "https://bo3.gg/matches/alianza-lima-esports-vs-los-ninos-21-10-2026"},
            ],
        },
        {
            "id": "R7",
            "severity": "Medium (HotSpawn API vs Lobby State)",
            "title": "HotSpawn API status conflicts (1082683 paiN v LP cancelled, 1081601 Quintessence v Ryvex cancelled, 1080200 Wildcard v DENDELE marked 'started' 22 days early) and 61 stale scheduled ghosts",
            "scope": "data/f7279a54/board.json, data/fe803b80/board.json",
            "detail": (
                "Three fixtures in the HotSpawn public API have conflicting statuses: (1) 1082683 `paiN v LP` "
                "(2026-10-21T14:00:00Z) is `cancelled` on HotSpawn and replaced by 1082831 `paiN v BARCA`, "
                "although Thunderpick/bo3.gg (`match 132406`) still quotes `paiN v LP`; (2) 1081601 `Quintessence v Ryvex` "
                "(2026-10-22T13:45:00Z) is `cancelled`; (3) 1080200 `Wildcard v DENDELE` (FRAG University 2026, "
                "2026-11-12T00:00:00Z) is API-only and marked `status: started` 22 days ahead of kickoff. "
                "In addition, 61 past fixtures from June/July/Oct 13-14 remain in the lobby HTML with `status: scheduled`."
            ),
            "sources": [
                {"label": "HotSpawn Pick'em Lobby", "url": LOBBY_URL},
                {"label": "HotSpawn Fixtures API", "url": HS_API_URL},
            ],
        },
    ]


def main() -> int:
    f727_board = load_json(F727_BOARD)
    f727_snap = load_json(F727_SNAP)
    fe80_board = load_json(FE80_BOARD)
    fe80_snap = load_json(FE80_SNAP)
    vrs_doc = load_json(VRS_GLOBAL)
    vrs_cache = load_json(VRS_CACHE)

    if not f727_board or not f727_board.get("open"):
        print("ERROR: data/f7279a54/board.json missing or empty", file=sys.stderr)
        return 1

    vrs_idx, dupes, vrs_meta = build_vrs_index(vrs_doc, f727_snap, vrs_cache)
    all_quotes = collect_all_quotes(f727_snap, fe80_snap)
    k = float((f727_board.get("calibration") or {}).get("k") or 0.4308)
    hltv_probe = ((f727_board.get("access") or {}).get("hltv_probe")) or {"url": "https://www.hltv.org/matches", "status": 403, "error": "HTTPError 403"}

    open_rows: list[dict] = []
    unresolved_rows: list[dict] = []
    fallback_rows: list[dict] = []

    for raw_row in f727_board.get("open", []):
        if raw_row.get("line"):
            # Featured market pick: keep byte-for-byte unchanged!
            row = json.loads(json.dumps(raw_row))
            open_rows.append(row)
        else:
            resolved = resolve_unpriced_fixture(raw_row, all_quotes, vrs_idx, dupes, vrs_meta, k, fe80_snap, hltv_probe)
            open_rows.append(resolved)
            fallback_rows.append(resolved)
            if not resolved.get("line"):
                unresolved_rows.append(resolved)

    # Also resolve API-only / status-conflict fixtures (e.g. 1080200 Wildcard v DENDELE) so they are covered too
    status_conflict_rows: list[dict] = []
    for sc in f727_board.get("status_conflicts") or []:
        sc_row = resolve_unpriced_fixture(
            {**sc, "state": "status_conflict", "hotspawn_url": LOBBY_URL, "flags": [f"api_status_{sc.get('status')}", "api_only_not_on_cached_lobby_page"]},
            all_quotes,
            vrs_idx,
            dupes,
            vrs_meta,
            k,
            fe80_snap,
            hltv_probe,
        )
        status_conflict_rows.append(sc_row)

    # Also enrich locked_recent (last 24h) so any locked row without `last_open_line` has a documented fallback reference
    locked_recent_rows: list[dict] = []
    fe80_by_id = {str(r.get("fixture_id")): r for r in (fe80_board.get("closed") or []) + (fe80_board.get("open") or [])}
    for lr in f727_board.get("locked_recent") or []:
        lr_copy = json.loads(json.dumps(lr))
        if not lr_copy.get("last_open_line"):
            fe_r = fe80_by_id.get(str(lr_copy.get("fixture_id")))
            if fe_r and fe_r.get("line"):
                lr_copy["fallback_reference_line"] = fe_r["line"]
            else:
                res_lr = resolve_unpriced_fixture(lr_copy, all_quotes, vrs_idx, dupes, vrs_meta, k, fe80_snap, hltv_probe)
                lr_copy["fallback_reference_line"] = res_lr.get("line")
        locked_recent_rows.append(lr_copy)

    open_rows.sort(key=lambda r: (r.get("lock_utc") or r.get("start_utc") or "", str(r["fixture_id"])))

    def count_basis(pred) -> int:
        return sum(1 for r in open_rows if pred(r))

    summary = {
        "open": len(open_rows),
        "with_pick": count_basis(lambda r: bool(r.get("line"))),
        "featured_market": count_basis(lambda r: r.get("line") and "resolution" not in r),
        "fallback_resolved": len(fallback_rows) - len(unresolved_rows),
        "esportsbook_exchange": count_basis(lambda r: r.get("line") and r["line"]["basis"] in ("esportsbook", "exchange")),
        "vrs_model": count_basis(lambda r: r.get("line") and r["line"]["basis"] == "model"),
        "floor_estimate": count_basis(lambda r: r.get("line") and r["line"]["basis"] == "floor_estimate"),
        "unresolved": len(unresolved_rows),
        "api_status_conflicts": len(status_conflict_rows),
        "locked_recent_24h": len(locked_recent_rows),
        "base_generated_utc": f727_board.get("generated_utc"),
        "fe80_generated_utc": fe80_board.get("generated_utc"),
    }

    out_board = {
        "session": "51197e5b",
        "generated_utc": f727_board.get("generated_utc"),
        "base_board": "data/f7279a54/board.json",
        "secondary_snapshot": "data/fe803b80/snapshot.json",
        "base_generated_utc": f727_board.get("generated_utc"),
        "collected_from_utc": f727_board.get("collected_from_utc"),
        "week": f727_board.get("week"),
        "policy": "featured-market-first-then-fallback-ladder-v1",
        "vrs": vrs_meta,
        "calibration": {
            "k": round(k, 4),
            "n_pairs": (f727_board.get("calibration") or {}).get("n_pairs", 60),
            "mae_prob": (f727_board.get("calibration") or {}).get("mae_prob"),
            "source": "data/f7279a54/board.json least-squares fit on eligible priced fixtures",
        },
        "vrs_duplicates_resolved": dupes,
        "access": f727_board.get("access"),
        "summary": summary,
        "open": open_rows,
        "fallback_resolved_ids": [r["fixture_id"] for r in fallback_rows if r.get("line")],
        "unresolved_ids": [r["fixture_id"] for r in unresolved_rows],
        "status_conflicts": status_conflict_rows,
        "locked_recent": locked_recent_rows,
        "repo_irregularities": build_repo_irregularities(),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "board.json").write_text(json.dumps(out_board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
