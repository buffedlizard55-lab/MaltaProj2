#!/usr/bin/env python3
"""Session f3e5123c — resolve a pick for EVERY open HotSpawn CS2 lobby match.

Inputs are READ-ONLY committed upstream captures (refreshed by their own bots):
  * data/f7279a54/board.json + snapshot.json — lobby fixtures, featured primary
    bookmaker lines (Pinnacle/Bovada/Melbet/Kalshi), official Valve VRS file.
  * data/fe803b80/board.json + snapshot.json — Thunderpick-via-bo3.gg quotes,
    bo3.gg registry, Independent model cross-check.

Rules (auditable, in order):
  0. Featured rows (f7279a54 already priced) are copied BYTE-FOR-BYTE. The
     fallback ladder below runs ONLY on matches with no featured pick.
  1. HLTV first: record probe/fixture-confirmation outcome (HLTV publishes no
     machine-readable two-way odds; bot probe is HTTP 403 upstream).
  2. Esportsbooks/exchange: join captured Pinnacle/Bovada/Melbet/Thunderpick/
     Kalshi quotes on BOTH teams + kickoff within 15 min. Sponsor/org aliases
     are allowed ONLY via the roster-verified ALIAS_GROUPS below (evidence
     URLs + verification date recorded per row).
  3. Official Valve VRS (both teams uniquely identified; duplicate name rows
     disambiguated to the active 5-player roster with the latest counted
     match) -> originated line with the market-calibrated slope k published
     in the f7279a54 board (least-squares fit vs bookmaker prices).
  4. Exactly one team VRS-rated -> DIRECTIONAL floor bound only: pick the
     rated team, probability = its fitted win rate vs the last VRS team.
     This is a lower bound, not a betting line, and is always listed in the
     Unresolved & Limitations section.
  5. Otherwise: no pick, blank probabilities, documented attempts.

HotSpawn crowd percentages are never used as a probability input.
Output: data/f3e5123c/board.json (this session's scope only).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

F727_BOARD = ROOT / "data/f7279a54/board.json"
F727_SNAP = ROOT / "data/f7279a54/snapshot.json"
FE80_BOARD = ROOT / "data/fe803b80/board.json"
FE80_SNAP = ROOT / "data/fe803b80/snapshot.json"
OUT = ROOT / "data/f3e5123c/board.json"

# --- Roster-verified sponsor/org alias groups (verified 2026-10-21) ---------
# Each group: canonical keys (via core.canon_team) that denote ONE roster.
# A quote may join through a group only when the OPPONENT also matches and the
# kickoff matches within 15 minutes; the evidence is copied onto the row.
ALIAS_GROUPS = [
    {
        "group": "zetta",
        "keys": ["zetta", "alianzalima"],
        "display": "Zetta = Alianza Lima Esports",
        "verified_utc": "2026-10-21",
        "roster": ["zockie", "Slayerhz", "Notjuanjo", "BabyRage", "Antuanette"],
        "evidence": [
            "https://bo3.gg/teams/alianza-lima-esports",
            "https://www.hltv.org/team/13833/zetta",
            "https://www.hltv.org/matches/2399865/zetta-vs-los-ninos-cct-2026-south-america-series-7",
            "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_americas_2026_10_05.md",
        ],
        "note": "bo3.gg lists the identical 5 starters (zockie, Slayerhz, NotJuanjo, BabyRage, Antuanette) under 'Alianza Lima Esports' that HLTV team 13833 and Valve VRS list as 'Zetta', in the same CCT South America Series 7 slot vs Los Niños at the same kickoff. Draft5's CCT page still shows a stale 1ayala roster - rejected as outdated vs bo3.gg/HLTV.",
    },
    {
        "group": "betclic-apogee",
        "keys": ["apogeebetclic", "apogee", "betclic", "betclicapogee", "apogeebetclicapogee"],
        "display": "Apogee Betclic = Betclic Apogee Esports = HLTV 'Betclic'",
        "verified_utc": "2026-10-21",
        "roster": ["Demho", "Prism", "ex1st", "ultimate", "Qlocuu"],
        "vrs_roster_key": {"demho", "ex1st", "prism", "qlocuu", "ultimate"},
        "evidence": [
            "https://liquipedia.net/counterstrike/Betclic_Apogee_Esports",
            "https://www.hltv.org/team/12916/betclic",
            "https://bo3.gg/teams/betclic-apogee-esports",
            "https://www.hltv.org/events/9399/stake-ranked-episode-6-closed-qualifier",
        ],
        "note": "HotSpawn 'Apogee Betclic', Melbet 'Apogee Esports', Thunderpick/bo3.gg 'Betclic' and HLTV team 12916 'Betclic' are one roster: Demho, Prism, ex1st, ultimate, Qlocuu (Liquipedia 'Betclic Apogee Esports' active roster; HLTV Stake Ranked Ep.6 CQ event 9399 lists Betclic vs UNiTY on 2026-10-22). That roster is Valve VRS 'Betclic' #45 (1333 pts) - NOT an unrated team.",
    },
]
KEY_TO_GROUP: dict[str, dict] = {}
for _g in ALIAS_GROUPS:
    for _k in _g["keys"]:
        KEY_TO_GROUP[_k] = _g


def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def key_of(name) -> str:
    return core.canon_team(name, allow_ex_strip=True)[0]


def keys_match(fixture_key: str, quote_key: str):
    """Return alias-group dict if matched via group, {} if exact, None if no."""
    if not fixture_key or not quote_key:
        return None
    if fixture_key == quote_key:
        return {}
    g = KEY_TO_GROUP.get(fixture_key)
    if g and quote_key in g["keys"]:
        return g
    return None


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def kalshi_start_utc(event_id, fallback):
    """KXCS2GAME-26OCT211800XX -> 2026-10-21 18:00 EDT -> 22:00Z (EDT=UTC-4)."""
    if fallback:
        return fallback, "snapshot_start_utc"
    try:
        code = str(event_id).split("-")[1]  # 26OCT211800...
        yy, mon, dd, hh, mm = int(code[0:2]), _MONTHS[code[2:5]], int(code[5:7]), int(code[7:9]), int(code[9:11])
        dt = datetime(2000 + yy, mon, dd, hh, mm, tzinfo=timezone.utc) + timedelta(hours=4)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "kalshi_ticker_edt_to_utc"
    except Exception:
        return None, None


def collect_quotes(*snaps) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for snap in snaps:
        for q in (snap.get("quotes") or []):
            if q.get("live"):
                continue
            dec = core.decimals_from_raw(q)
            if not dec:
                continue
            nv = core.no_vig(dec[0], dec[1])
            if not nv:
                continue
            start, start_src = kalshi_start_utc(q.get("event_id"), q.get("start_utc"))
            rec = {
                "source_key": q.get("source_key"),
                "source_name": q.get("source_name") or q.get("source_key"),
                "public_url": q.get("public_url"),
                "api_url": q.get("api_url"),
                "event_id": str(q.get("event_id")),
                "team_a": q.get("team_a"),
                "team_b": q.get("team_b"),
                "raw_format": q.get("raw_format"),
                "raw_a": q.get("raw_a"),
                "raw_b": q.get("raw_b"),
                "decimal_a": round(dec[0], 4),
                "decimal_b": round(dec[1], 4),
                "prob_a": nv["prob_a"],
                "overround": nv["overround"],
                "effective_start_utc": start,
                "start_time_source": start_src,
                "retrieved_utc": q.get("retrieved_utc"),
                "league": q.get("league"),
            }
            dedup = (rec["source_key"], rec["event_id"])
            prev = seen.get(dedup)
            if prev is None or str(rec["retrieved_utc"] or "") > str(prev["retrieved_utc"] or ""):
                seen[dedup] = rec
    return list(seen.values())


def match_quotes(fixture: dict, quotes: list[dict]) -> list[dict]:
    fa, fb = key_of(fixture["team_a"]), key_of(fixture["team_b"])
    out: dict[str, dict] = {}
    for q in quotes:
        qa, qb = key_of(q.get("team_a")), key_of(q.get("team_b"))
        g1 = keys_match(fa, qa)
        g2 = keys_match(fb, qb)
        swapped = False
        groups = []
        if g1 is not None and g2 is not None:
            groups = [g for g in (g1, g2) if g]
        else:
            g1s, g2s = keys_match(fa, qb), keys_match(fb, qa)
            if g1s is None or g2s is None:
                continue
            swapped, groups = True, [g for g in (g1s, g2s) if g]
        diff = core.hours_apart(fixture.get("start_utc"), q.get("effective_start_utc"))
        if diff is None or diff > 0.25:
            continue
        pa = (1.0 - float(q["prob_a"])) if swapped else float(q["prob_a"])
        entry = {
            "source_key": q["source_key"],
            "source_name": q["source_name"],
            "public_url": q["public_url"],
            "api_url": q.get("api_url"),
            "event_id": q["event_id"],
            "names_at_source": [q.get("team_a"), q.get("team_b")],
            "raw_format": q.get("raw_format"),
            "raw_a": q.get("raw_b") if swapped else q.get("raw_a"),
            "raw_b": q.get("raw_a") if swapped else q.get("raw_b"),
            "decimal_a": q["decimal_b"] if swapped else q["decimal_a"],
            "decimal_b": q["decimal_a"] if swapped else q["decimal_b"],
            "no_vig_prob_team_a": round(pa, 4),
            "overround": round(float(q.get("overround") or 0.0), 4),
            "swapped": swapped,
            "start_utc_at_source": q.get("effective_start_utc"),
            "start_time_source": q.get("start_time_source"),
            "start_diff_h": round(diff, 2),
            "retrieved_utc": q.get("retrieved_utc"),
            "alias_groups": [
                {"group": g["group"], "display": g["display"], "verified_utc": g["verified_utc"],
                 "evidence": g["evidence"], "note": g["note"]} for g in groups
            ],
        }
        prev = out.get(entry["source_key"])
        if prev is None or entry["start_diff_h"] < prev["start_diff_h"]:
            out[entry["source_key"]] = entry
    return [out[k] for k in sorted(out)]


# --- Official Valve VRS -------------------------------------------------------
def build_vrs_index(snap: dict):
    teams = ((snap.get("vrs") or {}).get("teams")) or []
    by_key: dict[str, list[dict]] = {}
    for t in teams:
        by_key.setdefault(key_of(t.get("team")), []).append(t)
    # alias-group members resolve VRS through the group's rated name too
    floor_row = max(teams, key=lambda t: t.get("standing") or 0) if teams else None
    meta = {
        "snapshot": (snap.get("vrs") or {}).get("snapshot") or "2026_10_05",
        "page_url": (snap.get("vrs") or {}).get("page_url")
        or "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md",
        "n_teams": len(teams),
        "floor": ({"standing": floor_row.get("standing"), "points": floor_row.get("points"),
                   "team": floor_row.get("team")} if floor_row else None),
    }
    return by_key, meta


def roster_set(roster: str | None) -> set[str]:
    return {p.strip().casefold() for p in str(roster or "").split(",") if p.strip()}


def vrs_lookup(name: str, by_key: dict):
    """Return (row|None, match_kind, candidates). Conservative disambiguation."""
    k = key_of(name)
    cands = list(by_key.get(k) or [])
    group = KEY_TO_GROUP.get(k)
    if not cands and group:
        for gk in group["keys"]:
            cands += list(by_key.get(gk) or [])
    if not cands:
        return None, "unrated", []
    if len(cands) == 1:
        r = cands[0]
        return (r, "exact" if key_of(r.get("team")) == k else "alias_group", cands)
    # duplicate name rows: documented current-roster override first
    if group and group.get("vrs_roster_key"):
        for r in cands:
            if roster_set(r.get("roster")) == set(group["vrs_roster_key"]):
                return r, "duplicate_roster_verified", cands
    five = [r for r in cands if len(roster_set(r.get("roster"))) >= 5]
    pool = five or cands
    pool_sorted = sorted(pool, key=lambda r: (str(r.get("latest_match_date") or ""), r.get("points") or 0), reverse=True)
    top = pool_sorted[0]
    # require a strict discriminator: unique latest date among 5-man rows
    top_date = str(top.get("latest_match_date") or "")
    same = [r for r in pool_sorted if str(r.get("latest_match_date") or "") == top_date]
    if top_date and len(same) == 1 and len(roster_set(top.get("roster"))) >= 5:
        return top, "duplicate_disambiguated", cands
    return None, "ambiguous", cands


def vrs_public(row, meta, kind):
    if not row:
        return None
    return {
        "standing": row.get("standing"),
        "points": row.get("points"),
        "team": row.get("team"),
        "roster": row.get("roster"),
        "latest_match_date": row.get("latest_match_date"),
        "details_url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
        + str(row.get("details_path") or ""),
        "match_kind": kind,
        "Snapshot": meta["snapshot"],
    }


def resolve_unpriced(fixture, quotes, by_key, vrs_meta, k, hltv_probe, n_quotes_total, fe80_row):
    row = dict(fixture)
    ta, tb = row["team_a"], row["team_b"]
    va, ka, ca = vrs_lookup(ta, by_key)
    vb, kb, cb = vrs_lookup(tb, by_key)
    pub_a, pub_b = vrs_public(va, vrs_meta, ka), vrs_public(vb, vrs_meta, kb)
    attempts = [{
        "step": 1, "source": "HLTV.org (fixture, roster & schedule confirmation)",
        "url": "https://www.hltv.org/matches",
        "status": f"automated probe HTTP {hltv_probe.get('status', 403)}",
        "outcome": "no_machine_odds",
        "detail": "HLTV confirms fixtures/rosters where listed but publishes no machine-readable two-way odds feed; the upstream bot probe is blocked (HTTP 403). Manual HLTV event/team reads for unpriced fixtures are recorded in this board's research_notes - used for identity only, never as a price.",
    }]
    matched = match_quotes(row, quotes)
    # fitted-VRS cross-check value whenever both teams are rated
    vrs_pa = None
    if va and vb:
        vrs_pa = round(core.vrs_prob(va["points"], vb["points"], k), 4)

    if matched:
        entries = [{"source_key": q["source_key"], "prob_a": q["no_vig_prob_team_a"]} for q in matched]
        mkt = core.consensus(entries)
        books = [q for q in matched if q["source_key"] != "kalshi"]
        basis = "esportsbook" if books else "exchange"
        row["quotes"] = matched
        row["line"] = core.make_line(
            mkt["prob_a"], ta, tb, basis,
            resolution_tier="fallback_esportsbook_exchange",
            resolution_note=(
                f"Fallback market line from {mkt['n_sources']} external source(s) "
                f"({', '.join(q['source_name'] for q in matched)}); opponent + kickoff verified. "
                + ("Single-source/thin market - treat as Lean-grade. " if mkt["n_sources"] == 1 else "")
                + (f"Fitted VRS cross-check P({ta})={vrs_pa:.1%}. " if vrs_pa is not None else "")
            ),
            n_sources=mkt["n_sources"], spread_a=mkt.get("spread_a"), vrs_crosscheck_prob_a=vrs_pa,
        )
        if mkt["n_sources"] == 1 and row["line"]["confidence"] in ("Strong", "Solid"):
            row["line"]["confidence"] = "Lean (single source)"
        attempts.append({
            "step": 2, "source": "Esportsbooks & exchange (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg, Kalshi)",
            "url": matched[0]["public_url"], "status": f"{len(matched)} verified quote(s) joined",
            "outcome": "priced",
            "detail": "Joined on both team names (roster-verified alias group where shown) and kickoff within 15 min; probabilities are proportional no-vig, consensus-weighted (Pinnacle x2).",
        })
        outcome = "fallback_market"
    elif va and vb:
        attempts.append({
            "step": 2, "source": "Esportsbooks & exchange (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg, Kalshi, Polymarket probe)",
            "url": "https://www.pinnacle.com/en/esports/cs2-hub", "status": "0 quotes for this pairing",
            "outcome": "no_quote",
            "detail": f"Scanned all {n_quotes_total} captured pre-match two-way quotes; no book/exchange prices this pairing at this kickoff (low-tier and/or far-future pre-market fixture). Thin/rejected exchange books are never promoted to a price.",
        })
        row["line"] = core.make_line(
            vrs_pa, ta, tb, "model",
            resolution_tier="fallback_valve_vrs_model",
            resolution_note=(
                f"Originated from official Valve VRS {vrs_meta['snapshot']}: {ta} #{va['standing']} ({va['points']} pts, {ka}) "
                f"vs {tb} #{vb['standing']} ({vb['points']} pts, {kb}); market-calibrated slope k={k}. "
                "Model line, not a bookmaker price - expect roughly +/-8-12pp error (calibration MAE in Method)."
            ),
            vrs_crosscheck_prob_a=vrs_pa,
        )
        row["line"]["confidence"] = {"Strong": "Model-Strong", "Solid": "Model-Solid",
                                      "Lean": "Model-Lean", "Toss-up": "Model Toss-up"}[row["line"]["confidence"]]
        attempts.append({
            "step": 3, "source": "Official Valve VRS standings + roster details",
            "url": vrs_meta["page_url"], "status": "both teams rated, uniquely identified",
            "outcome": "model_priced",
            "detail": f"{ta} #{va['standing']} {va['points']} pts ({ka}); {tb} #{vb['standing']} {vb['points']} pts ({kb}). Duplicate-name rows resolved to the active 5-player roster with the latest counted match where applicable.",
        })
        outcome = "fallback_model"
    elif va or vb:
        rated, unrated_name, side = (va, tb, "a") if va else (vb, ta, "b")
        floor_pts = float(vrs_meta["floor"]["points"])
        p_rated = core.vrs_prob(rated["points"], floor_pts, k)
        pa = p_rated if side == "a" else 1.0 - p_rated
        attempts.append({
            "step": 2, "source": "Esportsbooks & exchange (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg, Kalshi, Polymarket probe)",
            "url": "https://www.pinnacle.com/en/esports/cs2-hub", "status": "0 quotes for this pairing",
            "outcome": "no_quote",
            "detail": f"Scanned all {n_quotes_total} captured pre-match quotes; no verified two-way price for this pairing at this kickoff. This is the typical low-tier / pre-market coverage gap - not evidence the match is uncompetitive.",
        })
        row["line"] = core.make_line(
            pa, ta, tb, "floor_estimate", confidence="Directional",
            resolution_tier="fallback_vrs_floor_directional",
            directional=True,
            resolution_note=(
                f"DIRECTIONAL ONLY: {rated['team']} is VRS #{rated['standing']} ({rated['points']} pts); '{unrated_name}' has no row in the "
                f"{vrs_meta['n_teams']}-team official VRS table. Shown % is the rated team's fitted win rate vs the VRS floor "
                f"(#{vrs_meta['floor']['standing']} {vrs_meta['floor']['team']}, {vrs_meta['floor']['points']} pts) - a LOWER BOUND if the unrated team is "
                "weaker than every rated team, which is often false for new regional stacks. Do not treat as a betting line."
            ),
        )
        attempts.append({
            "step": 3, "source": "Official Valve VRS standings + roster details",
            "url": vrs_meta["page_url"], "status": "one team rated, opponent unrated",
            "outcome": "floor_bound_only",
            "detail": f"Rated side #{rated['standing']} {rated['points']} pts. '{unrated_name}' absent from VRS (fewer than the counted-match threshold, new stack, or name not yet registered) - no official points exist to originate a fair line.",
        })
        outcome = "fallback_floor"
    else:
        attempts.append({
            "step": 2, "source": "Esportsbooks & exchange (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg, Kalshi, Polymarket probe)",
            "url": "https://www.pinnacle.com/en/esports/cs2-hub", "status": "0 quotes for this pairing",
            "outcome": "no_quote",
            "detail": f"Scanned all {n_quotes_total} captured quotes; no verified price. Neither team is uniquely VRS-rated either (kinds: {ka}/{kb}).",
        })
        row["line"] = None
        outcome = "unresolved"
    attempts.append({
        "step": 4, "source": "bo3.gg team registry & published match history (form context)",
        "url": "https://bo3.gg/teams", "status": "context only",
        "outcome": "context_checked",
        "detail": "bo3.gg form/schedule is shown as context and for alias/schedule conflict detection only; win counts vs unrated opposition are never converted into a probability without a rating anchor.",
    })
    row["resolution"] = {
        "outcome": outcome,
        "team_a_vrs": pub_a,
        "team_b_vrs": pub_b,
        "team_a_vrs_candidates": [{"standing": c.get("standing"), "points": c.get("points"),
                                   "team": c.get("team"), "roster": c.get("roster"),
                                   "latest_match_date": c.get("latest_match_date")} for c in ca],
        "team_b_vrs_candidates": [{"standing": c.get("standing"), "points": c.get("points"),
                                   "team": c.get("team"), "roster": c.get("roster"),
                                   "latest_match_date": c.get("latest_match_date")} for c in cb],
        "k": k,
        "attempts": attempts,
        "Limitations": limitations_for(outcome, row),
    }
    # Independent cross-check (fe803b80 blends market+model with unfitted slope)
    if fe80_row and (fe80_row.get("line") or {}).get("prob_a") is not None:
        fl = fe80_row["line"]
        row["crosscheck_fe80"] = {"prob_a": round(float(fl["prob_a"]), 4), "basis": fl.get("basis"),
                                  "note": "Independent board blending market+model with UNFITTED Valve slope (k=1.0) + Elo extension; shown for disagreement detection, never blended into this board's line."}
        if row.get("line"):
            d = abs(float(fl["prob_a"]) - float(row["line"]["prob_a"]))
            fav_flip = (float(fl["prob_a"]) >= 0.5) != (float(row["line"]["prob_a"]) >= 0.5)
            if d > 0.15 or fav_flip:
                row.setdefault("flags", []).append("crosscheck_disagreement_gt15pp_or_favourite_flip")
                row["resolution"]["Limitations"].append(
                    f"Cross-check disagreement: independent fe803b80 board has P({ta})={float(fl['prob_a']):.1%} ({fl.get('basis')}) vs this board {float(row['line']['prob_a']):.1%}. "
                    "Main cause: that board's unfitted slope/Elo seeding vs this board's market-calibrated slope. Prefer the market/calibrated figure; treat the gap as model uncertainty.")
    return row


def limitations_for(outcome: str, row: dict) -> list[str]:
    base = {
        "fallback_market": [
            "Fallback market line - the featured consensus did not price this match, usually because of a sponsor-name variant or thin coverage; quotes can move quickly before lock.",
        ],
        "fallback_model": [
            "No bookmaker/exchange line exists in captured feeds; % is an originated VRS model estimate, not a tradable price.",
            "VRS points lag roster changes and reward LAN/prize-weighted results; online low-tier form can diverge from VRS order.",
        ],
        "fallback_floor": [
            "Opponent is unrated in official VRS: its true strength is UNKNOWN (new stack / <10 counted matches / unregistered Core). The floor % will overstate the favourite whenever the unrated team is mid-table strength.",
            "Use for pick direction only. Re-check closer to lock: books often post low-tier lines on match day, which will replace this bound automatically on refresh.",
        ],
        "unresolved": [
            "No verified bookmaker/exchange price and no unique official rating pair - probability left blank by rule; any % shown elsewhere for this fixture should be treated as unverified.",
        ],
    }
    return list(base.get(outcome, []))


RESEARCH_NOTES = [
    {
        "date": "2026-10-21",
        "topic": "Zetta = Alianza Lima Esports (1082837 market under alias)",
        "finding": "Kalshi KXCS2GAME-26OCT211800LNALE prices 'Los Ninos vs Alianza Lima Esports' for the exact HotSpawn/HLTV 'Zetta vs LOS NINOS' CCT SA7 slot (2026-10-21 22:00Z). bo3.gg Alianza roster = zockie/Slayerhz/NotJuanjo/BabyRage/Antuanette = HLTV Zetta (team 13833) = Valve VRS Zetta. Live Kalshi page re-read 2026-10-21 showed Los Ninos favoured (~60% chance display), consistent with the captured $0.58/$0.42 yes-mids. Polymarket also lists Alianza vs Los Niños (indexed volume $5) - listed but too thin to price from; NOT used.",
        "urls": ["https://bo3.gg/teams/alianza-lima-esports",
                 "https://www.hltv.org/team/13833/zetta",
                 "https://kalshi.com/markets/kxcs2game/counterstrike-2-game/kxcs2game-26oct211800lnale",
                 "https://polymarket.com/esports/cs2"],
    },
    {
        "date": "2026-10-21",
        "topic": "Apogee Betclic = Betclic Apogee = HLTV Betclic, VRS #45 (1082882)",
        "finding": "Liquipedia active roster (Prism/Demho/Qlocuu/Ex1st/ultimate) = HLTV team 12916 'Betclic' = Valve VRS 'Betclic' #45 (1333 pts). HLTV event 9399 (Stake Ranked Ep.6 CQ) lists Betclic vs UNiTY 22 Oct. Captured Melbet (UNiTY 2.355 / Apogee 1.54) + Thunderpick via bo3.gg (2.40/1.50) both favour Apogee ~61%; fitted VRS cross-check 59.9% agrees. The Kalshi APOGEEUNITY book (29c spreads) was correctly rejected upstream as thin and is NOT used.",
        "urls": ["https://liquipedia.net/counterstrike/Betclic_Apogee_Esports",
                 "https://www.hltv.org/team/12916/betclic",
                 "https://www.hltv.org/events/9399/stake-ranked-episode-6-closed-qualifier",
                 "https://bo3.gg/teams/betclic-apogee-esports"],
    },
    {
        "date": "2026-10-21",
        "topic": "HLTV coverage of the remaining unpriced fixtures",
        "finding": "HLTV lists the events/fixtures (CCT SA7 event 9452, CCT Challengers EU8 event 9453 incl. TitanFlow 0-2 DONSTU on 20 Oct and Banda Chuya vs DONSTU 22 Oct, Stake CQ 9399, DFRAG Invitational + GLuck Moscow Cyber Games on HLTV matches) - fixture/roster confirmation only. HLTV publishes Valve-ranking mirrors but no odds feed; aggregator 'ratings' (e.g. EGamersWorld numbers) are secondary and were rejected as pricing inputs under this board's rules.",
        "urls": ["https://www.hltv.org/events/9452/cct-2026-south-america-series-7",
                 "https://www.hltv.org/events/9453/cct-2026-challengers-europe-series-8",
                 "https://www.hltv.org/matches/2399690/titanflow-vs-donstu-cct-2026-challengers-europe-series-8",
                 "https://www.hltv.org/team/13900/banda-chuya"],
    },
    {
        "date": "2026-10-21",
        "topic": "Why DFRAG (Oct 26-27) + Moscow Cyber Games (Oct 31) have no book line yet",
        "finding": "Full captured-feed scan (Pinnacle/Bovada/Melbet/Thunderpick/Kalshi snapshots 19:24-19:29Z) contains zero quotes for Ground Zero-Off Chops, NEXVOID-Alter Ego, FlyQuest-Staqued, Rooster-Abyssal, HOTU-The Huns, 5star-1WIN - books typically post these 24-72h before start. Until then only the official VRS ladder can originate a number; the 4-hourly refresh replaces model rows automatically once a verified quote joins.",
        "urls": ["https://www.hltv.org/matches", "https://www.pinnacle.com/en/esports/cs2-hub"],
    },
]


def irregularities(f727, fe80) -> list[dict]:
    return [
        {"id": "F1", "severity": "high - pick direction",
         "title": "1082882 UNiTY vs Apogee Betclic: 'unrated opponent' treatment elsewhere picks the wrong favourite",
         "detail": "Apogee Betclic is Betclic Apogee Esports (HLTV 'Betclic', official VRS #45, 1333 pts) - see RESEARCH_NOTES. Treating it as unrated yields a spurious ~87% UNiTY floor pick (fullpicks/51197e5b); the captured Melbet + Thunderpick lines and fitted VRS all favour Apogee Betclic (~60-62%). This board resolves it as a fallback MARKET pick for Apogee Betclic.",
         "urls": ["https://liquipedia.net/counterstrike/Betclic_Apogee_Esports", "https://www.hltv.org/team/12916/betclic"]},
        {"id": "F2", "severity": "high - pick direction",
         "title": "1082837 Zetta vs LOS NINOS: exchange market hides under the Alianza Lima name; one board renders its decimals swapped",
         "detail": "Kalshi LNALE yes-mids Los Ninos $0.58 / Alianza(=Zetta) $0.42 favour LOS NINOS. fullpicks (floor method) picks Zetta; fe803b80's board line correctly picks LOS NINOS 58% but its rendered quote decimals (Los Ninos 2.381) are swapped vs its own snapshot (1.7241). Audit from snapshot raws, not board renderings. This board re-derives from raws: pick LOS NINOS.",
         "urls": ["https://kalshi.com/markets/kxcs2game/counterstrike-2-game/kxcs2game-26oct211800lnale", "https://bo3.gg/teams/alianza-lima-esports"]},
        {"id": "F3", "severity": "medium - calibration",
         "title": "Independent fe803b80 model uses unfitted Valve slope (k=1.0, 5 pairs) + Elo seeding -> extreme probabilities",
         "detail": "Examples this capture: FlyQuest 99.2%, HOTU 98.4% 'model' vs market-calibrated (k=0.4308, 60 pairs, MAE 7.7pp per f7279a54) 84.8%/76.7%. Unfitted Glicko slopes overstate favourites. Shown here only as a labelled cross-check; never blended.",
         "urls": ["https://github.com/ValveSoftware/counter-strike_regional_standings"]},
        {"id": "F4", "severity": "medium - inventory",
         "title": "Open-count disagreement: 13 lobby-visible fixtures vs 14 including API-only 1080200",
         "detail": "fe803b80 counts Wildcard vs DENDELE (1080200, seen_in=[api] only, implausible 'started'/far-future status) as open; f7279a54 correctly isolates it as a status conflict. This board follows the lobby page (what a player can actually pick): 13 open + status conflicts listed separately.",
         "urls": ["https://play.hotspawn.com/lobby"]},
        {"id": "F5", "severity": "medium - site usability (user-reported confusion)",
         "title": "Root landing page shows stale competing counts (9 open / 12 open) hours behind the 13-match lobby",
         "detail": "Multiple preserved session boards each render an 'executive summary' with different snapshot times. Fixed for this board by ONE labelled front door (hotspawn-picks/) with snapshot time + stale banner, and an additive pointer at the top of the root page; historical boards remain linked as an archive, not as competing recommendations.",
         "urls": ["https://play.hotspawn.com/lobby"]},
        {"id": "F6", "severity": "low - roster uncertainty",
         "title": "Banda Chuya (1081600): HLTV shows no active lineup vs VRS 5-man Core #165",
         "detail": "Official VRS counts a 5-player Banda Chuya Core (AdrieN/ezox/maaryy/Showk/tomiko, #165, latest counted match 2026-10-04); HLTV team 13900 currently displays no active players. The VRS-model Lean for Banda chuya assumes that Core plays; a stand-in roster would void the rating. Flagged, probability unchanged by rule.",
         "urls": ["https://www.hltv.org/team/13900/banda-chuya",
                  "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/details/2026_10_05/0165--banda_chuya--adrien-ezox-maaryy-showk-tomiko.md"]},
        {"id": "F7", "severity": "low - missing field",
         "title": "best_of is null for every open fixture in the HotSpawn feed",
         "detail": "Match-winner probabilities do not depend on BO1/BO3 labelling, but format affects upset rates in reality. HLTV/EGW list these fixtures as BO3; the HotSpawn feed value stays blank here (never inferred) - model error bars already assume mixed formats via market calibration.",
         "urls": ["https://play.hotspawn.com/lobby"]},
        {"id": "F8", "severity": "low - thin-market hygiene",
         "title": "Listed is not priced: Polymarket Alianza market (~$5 vol) and Kalshi thin books (29-88c spreads) rejected",
         "detail": "Upstream collectors already reject one-sided/>10c-spread Kalshi books (e.g. APOGEEUNITY, TITMOR); this board keeps that rule and shows rejected leads in the ledger instead of silently dropping or, worse, pricing from them. Draft5's stale Alianza roster (1ayala) likewise rejected vs bo3.gg/HLTV 5/5 identity.",
         "urls": ["https://polymarket.com/esports/cs2", "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct221230apogeeunity"]},
    ]


def main() -> int:
    f727 = load_json(F727_BOARD)
    f727s = load_json(F727_SNAP)
    fe80 = load_json(FE80_BOARD)
    fe80s = load_json(FE80_SNAP)
    if not f727.get("open"):
        print("ERROR: data/f7279a54/board.json missing/empty", file=sys.stderr)
        return 1
    by_key, vrs_meta = build_vrs_index(f727s)
    quotes = collect_quotes(f727s, fe80s)
    calib = f727.get("calibration") or {}
    k = float(calib.get("k") or 0.4308)
    hltv_probe = ((f727.get("access") or {}).get("hltv_probe")) or {"status": 403}
    fe80_by_id = {str(r.get("fixture_id")): r for r in (fe80.get("open") or []) + (fe80.get("closed") or [])}

    open_rows, featured_ids = [], []
    for raw in f727.get("open", []):
        row = dict(raw)
        if row.get("line"):
            featured_ids.append(str(row["fixture_id"]))
            # cross-check display only; featured line untouched
            fe = fe80_by_id.get(str(row["fixture_id"]))
            if fe and (fe.get("line") or {}).get("prob_a") is not None:
                row["crosscheck_fe80"] = {"prob_a": round(float(fe["line"]["prob_a"]), 4),
                                          "basis": fe["line"].get("basis"),
                                          "note": "Independent blended board (unfitted slope); featured consensus above governs."}
            open_rows.append(row)
        else:
            open_rows.append(resolve_unpriced(row, quotes, by_key, vrs_meta, k, hltv_probe,
                                              len(quotes), fe80_by_id.get(str(row["fixture_id"]))))
    open_rows.sort(key=lambda r: (str(r.get("start_utc")), str(r.get("fixture_id"))))

    sc_rows = []
    for raw in (f727.get("status_conflicts") or []):
        base = {"competition": None, "tier": None, "stage": None, "best_of": None, "points": None,
                "flags": ["api_status_conflict_not_in_lobby"], "state": "status_conflict",
                "hotspawn_url": "https://play.hotspawn.com/lobby"}
        base.update(raw)
        sc_rows.append(resolve_unpriced(base, quotes, by_key, vrs_meta, k, hltv_probe,
                                         len(quotes), fe80_by_id.get(str(base.get("fixture_id")))))

    def basis_of(r):
        return (r.get("line") or {}).get("basis")

    summary = {
        "open": len(open_rows),
        "with_pick": sum(1 for r in open_rows if r.get("line")),
        "featured_market": len(featured_ids),
        "fallback_market": sum(1 for r in open_rows if basis_of(r) in ("esportsbook", "exchange")),
        "vrs_model": sum(1 for r in open_rows if basis_of(r) == "model"),
        "floor_directional": sum(1 for r in open_rows if basis_of(r) == "floor_estimate"),
        "unresolved": sum(1 for r in open_rows if not r.get("line")),
        "status_conflicts": len(sc_rows),
        "locked_recent": len(f727.get("locked_recent") or []),
        "quotes_scanned": len(quotes),
        "base_generated_utc": f727.get("generated_utc"),
        "fe80_generated_utc": fe80.get("generated_utc"),
    }
    board = {
        "session": "f3e5123c",
        "generated_utc": f727.get("generated_utc"),
        "resolved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_board": "data/f7279a54/board.json",
        "secondary_snapshot": "data/fe803b80/snapshot.json",
        "week": f727.get("week"),
        "policy": "featured-unchanged-then-hltv-books-vrs-ladder-v1",
        "calibration": {"k": k, "n_pairs": calib.get("n_pairs"), "mae_prob": calib.get("mae_prob"),
                        "mae_prob_valve_unfitted": calib.get("mae_prob_valve"),
                        "source": "data/f7279a54/board.json (least-squares fit of fitted-VRS prob vs bookmaker no-vig prob)"},
        "vrs": vrs_meta,
        "access": f727.get("access"),
        "summary": summary,
        "open": open_rows,
        "status_conflicts": sc_rows,
        "locked_recent": f727.get("locked_recent") or [],
        "alias_groups": [{k2: (sorted(v) if isinstance(v, set) else v) for k2, v in g.items()} for g in ALIAS_GROUPS],
        "research_notes": RESEARCH_NOTES,
        "irregularities": irregularities(f727, fe80),
        "featured_ids": featured_ids,
        "fallback_ids": [str(r["fixture_id"]) for r in open_rows if r.get("resolution")],
        "unresolved_ids": [str(r["fixture_id"]) for r in open_rows if not r.get("line")],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} summary={summary}")
    for r in open_rows:
        ln = r.get("line") or {}
        print(f"  {r['fixture_id']} {r['start_utc']} {r['team_a']} vs {r['team_b']} -> "
              f"{ln.get('pick_team')} {ln.get('prob_a')}/{ln.get('prob_b')} [{ln.get('basis')}/{ln.get('confidence')}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
