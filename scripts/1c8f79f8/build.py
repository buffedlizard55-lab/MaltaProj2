#!/usr/bin/env python3
"""Build the day4/ section and data/1c8f79f8/board.json for session 1c8f79f8.

Deterministic: no network access. Inputs are the retained fixtures API
capture (data/1c8f79f8/fixtures_raw.json) and the curated research ledger
(scripts/1c8f79f8/research.py). Every published number is either
re-derived here from retained raw prices (de-vig) or from the Valve VRS
points (canonical k=0.25 model), so tests can re-derive it too.

Outputs:
    data/1c8f79f8/board.json
    day4/index.html        executive summary (mobile-first)
    day4/picks.html        pick + probability for every open match
    day4/twc-review.html   verified day-1/2/3 review + Aurora investigation
    day4/unresolved.html   unresolved picks & limitations
    day4/flagged.html      flagged irregularities
    day4/method.html       method & sources
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "1c8f79f8"
OUT = ROOT / "day4"

_spec = importlib.util.spec_from_file_location("research_1c8f79f8",
                                               ROOT / "scripts" / "1c8f79f8" / "research.py")
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)

# ---------------------------------------------------------------- canonical
# Valve-VRS glicko model, identical arithmetic to scripts/fe803b80/core.py
# (Valve's glicko.js constants: "rank delta of 400 points = 90% chance of
# victory", Q = ln(10)/400, fixed RD = 75) with the site's fitted scale k.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0
K_FIT = 0.25  # fitted on bookmaker pairs (data/fe803b80/board.json calibration)

# Rendered stamps. Set from the retained capture + ledger by main() so a refresh
# publishes the timestamps it actually used instead of a frozen literal.
SNAPSHOT_STAMP = "2026-10-16T20:50Z"
LINES_READ_STAMP = "2026-10-16T19:35-20:50Z"


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float) -> float:
    return sigmoid(K_FIT * VALVE_C * (float(points_a) - float(points_b)))


def devig(decimal_a: float, decimal_b: float) -> tuple[float, float, float]:
    ia, ib = 1.0 / float(decimal_a), 1.0 / float(decimal_b)
    book = ia + ib
    return ia / book, ib / book, book - 1.0


def pct(x: float | None) -> str:
    return "blank" if x is None else f"{100 * x:.0f}%"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- board rows
# Inventory policy (added 2026-10-16 by the integration session, repair of the
# broken refresh path): the board is rebuilt from the *fresh* fixtures capture,
# never from the curated ledger alone.
#
#   * every open fixture in the capture gets a row, including fixtures the
#     curated ledger has never seen (new lobby listings),
#   * the curated ledger supplies context, picks and source links for the
#     fixtures it covers,
#   * a new fixture is priced from an exact fixture-id match in another
#     session's published board (retained quote + public URL + read time), else
#     from the canonical Valve-VRS model, else it stays blank and is flagged,
#   * live drift (crowd percentages, kickoff/lock times, name rendering) is
#     recorded instead of aborting the rebuild: ownership is context only and
#     the capture is authoritative for it,
#   * a capture that comes back empty or truncated keeps the retained
#     inventory and flags the degradation rather than publishing a partial board.
SIBLING_BOARDS = (
    ("c64a5e19", "data/c64a5e19/board.json", "canonical every-match board"),
    ("fe803b80", "data/fe803b80/board.json", "full-coverage board"),
    ("f7279a54", "data/f7279a54/board.json", "ourline board"),
    ("b1fb1465", "data/b1fb1465/board.json", "exec board"),
    ("7177d07f", "data/7177d07f/board.json", "research-resolved board"),
)
VALVE_STANDINGS_URL = ("https://github.com/ValveSoftware/counter-strike_regional_standings/"
                       "blob/main/live/2026/standings_global_2026_10_05.md")


def _ms(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_capture(capture_path=None) -> dict:
    path = Path(capture_path) if capture_path else (DATA / "fixtures_raw.json")
    return json.loads(path.read_text())


def model_block(team_a: str, team_b: str):
    """Canonical Valve-VRS model block, or None when a rating pair is not eligible."""
    key_a = research.vrs_key(team_a)
    key_b = research.vrs_key(team_b)
    va = research.VRS.get(key_a) if key_a else None
    vb = research.VRS.get(key_b) if key_b else None
    if not (va and vb and key_a not in research.VRS_ABSENT and key_b not in research.VRS_ABSENT):
        return None
    delta = va["points"] - vb["points"]
    return {
        "vrs": {"delta": delta, "points_a": va["points"], "points_b": vb["points"],
                "standing_a": va["standing"], "standing_b": vb["standing"],
                "region_a": "global", "region_b": "global",
                "vrs_name_a": key_a, "vrs_name_b": key_b,
                "snapshot_a": va.get("snapshot", "2026_10_05"),
                "snapshot_b": vb.get("snapshot", "2026_10_05")},
        "prob_a": round(vrs_prob(va["points"], vb["points"]), 4),
        "prob_b": round(vrs_prob(vb["points"], va["points"]), 4),
        "basis": "valve_vrs_k0.25",
    }


def sibling_market(fixture_id):
    """Exact fixture-id match in another session's published board.

    Only stored values are reused: the sibling board's no-vig pair and its raw
    quote (decimals when it retained them) with the public URL and read time.
    No alias is joined and no number is derived here.
    """
    for session, rel, label in SIBLING_BOARDS:
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for row in (doc.get("open") or []):
            if str(row.get("fixture_id")) != str(fixture_id):
                continue
            market = row.get("market") or {}
            if not market.get("prob_a") or not market.get("prob_b"):
                continue
            quote = None
            for q in (row.get("quotes") or []):
                if q.get("public_url"):
                    quote = q
                    if q.get("decimal_a") and q.get("decimal_b"):
                        break
            if quote is None or not quote.get("public_url"):
                continue
            return {
                "session": session, "board": rel, "label": label,
                "prob_a": market["prob_a"], "prob_b": market["prob_b"],
                "decimals": ((quote.get("decimal_a"), quote.get("decimal_b"))
                             if quote.get("decimal_a") and quote.get("decimal_b") else None),
                "url": quote["public_url"],
                "retrieved_utc": quote.get("retrieved_utc") or doc.get("generated_utc"),
                "source_key": quote.get("source_key") or label,
                "board_generated_utc": doc.get("generated_utc"),
            }
    return None


def auto_row(api: dict, drift: list) -> dict:
    """Row for a capture fixture the curated ledger does not cover."""
    fid = str(api.get("id"))
    team_a = api.get("participants0_name")
    team_b = api.get("participants1_name")
    start = _iso(_ms(api.get("scheduled_start_time")))
    lock = _iso(_ms(api.get("lock_time")))
    comp = api.get("competition_name")
    stage = api.get("stage") or "not published by the fixtures API"
    tier = (api.get("tier") or "").upper() or None
    points = api.get("offered_points")
    sib = sibling_market(fid)
    model = model_block(team_a, team_b)

    market = None
    quotes = []
    if sib:
        quote = {
            "source_key": sib["source_key"],
            "public_url": sib["url"],
            "retrieved_utc": sib["retrieved_utc"],
            "note": (f"Retained quote reused verbatim from the {sib['session']} {sib['label']} "
                     f"(exact HotSpawn fixture id {fid}); that board derived the no-vig pair and "
                     f"this row republishes it with the same source link and read time."),
        }
        if sib["decimals"]:
            da, db = sib["decimals"]
            pa, pb, over = devig(da, db)
            quote.update({"decimal_a": da, "decimal_b": db, "prob_a": round(pa, 4),
                          "prob_b": round(pb, 4), "overround": round(over, 4)})
            market = {"prob_a": round(pa, 4), "prob_b": round(pb, 4),
                      "overround": round(over, 4), "n_sources": 1,
                      "sources": [sib["source_key"]], "volume_usd": None,
                      "note": (f"Market line inherited from the {sib['session']} board quote "
                               f"({sib['url']}) captured {sib['retrieved_utc']}; re-de-vigged here "
                               f"from the retained decimals.")}
        else:
            quote.update({"prob_a": sib["prob_a"], "prob_b": sib["prob_b"]})
            market = {"prob_a": sib["prob_a"], "prob_b": sib["prob_b"],
                      "overround": None, "n_sources": 1, "sources": [sib["source_key"]],
                      "volume_usd": None,
                      "note": (f"No-vig pair inherited from the {sib['session']} board "
                               f"({sib['url']}, captured {sib['retrieved_utc']}); that board "
                               f"retained no raw decimals on this row.")}
        quotes.append(quote)

    flags = ["auto_row_new_listing"]
    fair_a = fair_b = pick = pick_prob = None
    basis = None
    confidence = "Low"
    blank_reason = None
    role = "directional"
    context = [
        f"This fixture is in the {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} fixtures "
        f"capture but was not in the curated research ledger, so the row is generated automatically "
        f"from the retained capture and the site's existing evidence only.",
    ]
    sources = []
    # No slug is ever constructed: HotSpawn publishes no per-match permalink for a
    # fixture the collector has not seen before, so the row links the official lobby.
    hotspawn_url = "https://play.hotspawn.com/lobby"
    if market:
        fair_a, fair_b = market["prob_a"], market["prob_b"]
        basis = "market"
        pick = team_a if fair_a >= fair_b else team_b
        pick_prob = max(fair_a, fair_b)
        confidence = "Medium"
        role = "safe"
        flags.append("market_line_inherited_from_sibling_board")
        context.append(f"Line inherited from the {sib['session']} board: {sib['url']} "
                       f"(read {sib['retrieved_utc']}).")
        sources.append((f"{sib['label']} quote ({sib['session']})", sib["url"]))
    elif model:
        fair_a, fair_b = model["prob_a"], model["prob_b"]
        basis = "model"
        pick = team_a if fair_a >= fair_b else team_b
        pick_prob = max(fair_a, fair_b)
        confidence = "Lean"
        role = "safe"
        flags.append("model_only_no_market_line")
        context.append("No market quote for this fixture was found in the retained captures, so the "
                       "line is the canonical Valve-VRS model.")
        sources.append(("Valve regional standings (official, snapshot 2026-10-05)", VALVE_STANDINGS_URL))
    else:
        blank_reason = "new_listing_no_retained_line_and_no_eligible_rating_pair"
        flags.extend(["probability_blank", "needs_research_next_refresh"])
        context.append("No retained market quote exists for this fixture and at least one team is "
                       "absent from Valve's official standings, so no model pair is eligible. "
                       "A probability is withheld rather than invented.")
        context.append("The four-hourly collector retries external venues for every open fixture; "
                       "this row will be priced as soon as one publishes an accepted two-sided line.")
        sources.append(("Valve regional standings (identity check, official)", VALVE_STANDINGS_URL))
    sources.append((
        "HotSpawn fixtures API (official listing for this competition)",
        "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
        f"?sport_alias=cs2&status=scheduled&competition_id={api.get('competition_id')}"))

    if start is None or lock is None:
        drift.append({"fixture_id": fid, "issue": "capture row without parsable start/lock time"})

    return {
        "fixture_id": fid,
        "competition": comp, "competition_id": api.get("competition_id"),
        "tier": tier, "stage": stage, "best_of": api.get("best_of"),
        "points": points,
        "status": "scheduled", "start_utc": start, "lock_utc": lock,
        "team_a": team_a, "team_b": team_b,
        "participant_a_id": api.get("participants0_id"),
        "participant_b_id": api.get("participants1_id"),
        "winner": None,
        "seen_in": ["api", "auto_row"],
        "hotspawn_url": hotspawn_url,
        "hotspawn_url_kind": "official lobby listing (no per-match permalink captured)",
        "crowd_a": api.get("participants0_picked_percent"),
        "crowd_b": api.get("participants1_picked_percent"),
        "crowd_note": "HotSpawn pick'em ownership — context only, never a probability input",
        "total_picks": api.get("total_picks"),
        "alias_note": None,
        "market": market, "quotes": quotes,
        "model": model,
        "line": {"prob_a": fair_a, "prob_b": fair_b, "basis": basis,
                 "pick": pick, "pick_probability": pick_prob,
                 "confidence": confidence},
        "ladder": {"safe": pick, "safe_prob": pick_prob, "climb": None, "climb_prob": None,
                   "climb_odds": None, "swing_cost_pts": None},
        "role": role,
        "flags": flags,
        "blank_reason": blank_reason,
        "context": context,
        "sources": sources,
        "row_origin": "auto_from_capture",
    }


def ledger_row(fx: dict, api, drift: list) -> dict:
    """Curated row, reconciled against the fresh capture (live ownership wins)."""
    fid = fx["fixture_id"]
    team_a, team_b = fx["team_a"], fx["team_b"]
    crowd_a, crowd_b = fx["crowd_a"], fx["crowd_b"]
    total_picks = fx.get("total_picks")
    start_utc, lock_utc = fx["start_utc"], fx["lock_utc"]
    flags = list(research.PICKS[fid]["flags"])
    context = list(research.PICKS[fid]["context"])
    if api is not None:
        cap_a = api.get("participants0_name")
        cap_b = api.get("participants1_name")
        if cap_a and cap_a.casefold() != team_a.casefold():
            drift.append({"fixture_id": fid, "issue": "capture name variant (team A)",
                          "ledger": team_a, "capture": cap_a})
            flags.append("capture_name_variant_verified_same_fixture")
        if cap_b and cap_b.casefold() != team_b.casefold():
            drift.append({"fixture_id": fid, "issue": "capture name variant (team B)",
                          "ledger": team_b, "capture": cap_b})
            flags.append("capture_name_variant_verified_same_fixture")
        live_a = api.get("participants0_picked_percent")
        live_b = api.get("participants1_picked_percent")
        if live_a is not None and live_b is not None:
            if (live_a, live_b) != (crowd_a, crowd_b):
                drift.append({"fixture_id": fid, "issue": "crowd ownership moved",
                              "ledger": [crowd_a, crowd_b], "capture": [live_a, live_b]})
                context.append(f"Crowd ownership moved since the research ledger capture: "
                               f"{team_a} {crowd_a}%/{team_b} {crowd_b}% → "
                               f"{team_a} {live_a}%/{team_b} {live_b}% (ownership only; it never "
                               f"enters the probability).")
            crowd_a, crowd_b = live_a, live_b
        if api.get("total_picks") is not None:
            total_picks = api.get("total_picks")
        cap_start = _iso(_ms(api.get("scheduled_start_time")))
        cap_lock = _iso(_ms(api.get("lock_time")))
        if cap_start and cap_start != start_utc:
            drift.append({"fixture_id": fid, "issue": "kickoff rescheduled",
                          "ledger": start_utc, "capture": cap_start})
            flags.append("kickoff_rescheduled_after_research")
        if cap_start:
            start_utc = cap_start
        if cap_lock:
            lock_utc = cap_lock
    return ledger_row_body(fx, team_a, team_b, crowd_a, crowd_b, total_picks,
                           start_utc, lock_utc, flags, context)


def ledger_row_body(fx, team_a, team_b, crowd_a, crowd_b, total_picks,
                    start_utc, lock_utc, flags, context) -> dict:
    fid = fx["fixture_id"]
    pick = research.PICKS[fid]
    line_entry = research.LINES.get(fid)
    market = None
    quotes = []
    if line_entry and line_entry.get("kind") == "market":
        da, db = line_entry["decimals"]
        pa, pb, over = devig(da, db)
        market = {
            "prob_a": round(pa, 4), "prob_b": round(pb, 4),
            "overround": round(over, 4),
            "n_sources": 2 if line_entry.get("url2") else 1,
            "sources": [line_entry["basis"]],
            "volume_usd": line_entry.get("volume_usd"),
            "note": line_entry["note"],
        }
        quotes.append({
            "source_key": line_entry["basis"], "decimal_a": da, "decimal_b": db,
            "prob_a": round(pa, 4), "prob_b": round(pb, 4),
            "overround": round(over, 4),
            "public_url": line_entry["url"],
            "retrieved_utc": research.RETRIEVED_UTC,
        })
        if line_entry.get("url2"):
            quotes.append({
                "source_key": line_entry["basis"] + "-second",
                "public_url": line_entry["url2"],
                "note": "second independent source; see market note",
                "retrieved_utc": research.RETRIEVED_UTC,
            })
        if line_entry.get("decimals2"):
            da2, db2 = line_entry["decimals2"]
            pa2, pb2, over2 = devig(da2, db2)
            quotes[-1].update({
                "decimal_a": da2, "decimal_b": db2,
                "prob_a": round(pa2, 4), "prob_b": round(pb2, 4),
                "overround": round(over2, 4),
            })

    model = model_block(team_a, team_b)
    fair_a, fair_b = pick["fair_a"], pick["fair_b"]
    if fair_a is not None:
        assert abs((fair_a + fair_b) - 1.0) < 1e-9, fid
    real_market = bool(market) and (
        (market.get("volume_usd") is None)
        or (market.get("volume_usd") or 0) > 0
        or market["n_sources"] >= 2)
    if real_market and (market["n_sources"] >= 2
                        or (model and abs(market["prob_a"] - model["prob_a"]) < 0.08)):
        confidence = "High"
    elif real_market:
        confidence = "Medium"
    elif model:
        confidence = "Lean"
    else:
        confidence = "Low"

    ladder = {"safe": pick["pick"], "safe_prob": pick["pick_prob"],
              "climb": None, "climb_prob": None, "climb_odds": None,
              "swing_cost_pts": None}
    if pick.get("climb"):
        ladder.update({"climb": pick["climb"]["pick"],
                       "climb_prob": pick["climb"]["pick_prob"],
                       "climb_odds": pick["climb"]["odds_ref"],
                       "climb_side": pick["climb"].get("side"),
                       "climb_gates": pick["climb"].get("gates"),
                       "swing_cost_pts": pick["climb"]["swing_cost_pts"]})

    return {
        "fixture_id": fid,
        "competition": fx["competition"], "competition_id": fx["competition_id"],
        "tier": fx["tier"], "stage": fx["stage"], "best_of": fx["best_of"],
        "points": fx["points"],
        "status": "scheduled", "start_utc": start_utc, "lock_utc": lock_utc,
        "team_a": team_a, "team_b": team_b,
        "participant_a_id": fx.get("participants_a_id"), "participant_b_id": fx.get("participants_b_id"),
        "winner": None,
        "seen_in": ["lobby_page", "api"],
        "hotspawn_url": fx["hotspawn_url"], "hotspawn_url_kind": "match page",
        "crowd_a": crowd_a, "crowd_b": crowd_b,
        "crowd_note": "HotSpawn pick'em ownership — context only, never a probability input",
        "total_picks": total_picks,
        "alias_note": fx.get("alias_note"),
        "market": market, "quotes": quotes,
        "model": model,
        "line": {"prob_a": fair_a, "prob_b": fair_b, "basis": pick["basis"],
                 "pick": pick["pick"], "pick_probability": pick["pick_prob"],
                 "confidence": confidence},
        "ladder": ladder,
        "role": pick["role"],
        "flags": flags,
        "blank_reason": pick.get("blank_reason"),
        "context": context,
        "sources": pick["sources"],
        "row_origin": "curated_ledger_reconciled",
    }


def open_for_picks(start_utc, lock_utc, now) -> bool:
    reference = lock_utc or start_utc
    if not reference:
        return False
    try:
        when = datetime.strptime(reference, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return when > now


def build_rows(capture_path=None, now=None) -> tuple[list[dict], dict]:
    """Rebuild every row from the fresh capture; return (rows, inventory report)."""
    now = now or datetime.now(timezone.utc)
    raw = load_capture(capture_path)
    fixtures = [f for f in (raw.get("fixtures") or []) if f.get("id")]
    api_rows = {str(r["id"]): r for r in fixtures}
    capture_utc = (raw.get("meta") or {}).get("captured_utc")
    drift: list[dict] = []
    rows: list[dict] = []
    dropped: list[dict] = []
    ledger_ids = [fx["fixture_id"] for fx in research.FIXTURES]
    present = [fid for fid in ledger_ids if fid in api_rows]
    degraded_reasons = []
    if not fixtures:
        degraded_reasons.append("capture returned no fixtures")
    elif len(present) * 2 < len(ledger_ids):
        degraded_reasons.append(
            f"capture covers only {len(present)} of {len(ledger_ids)} researched fixtures")
    degraded = bool(degraded_reasons)

    for fx in research.FIXTURES:
        fid = fx["fixture_id"]
        api = api_rows.get(fid)
        if api is None and not degraded:
            if open_for_picks(fx["start_utc"], fx["lock_utc"], now):
                dropped.append({"fixture_id": fid, "reason": "absent from the fresh capture"})
            else:
                dropped.append({"fixture_id": fid, "reason": "lock time has passed"})
            continue
        if api is None and degraded and not open_for_picks(fx["start_utc"], fx["lock_utc"], now):
            dropped.append({"fixture_id": fid, "reason": "lock time has passed (retained inventory)"})
            continue
        row = ledger_row(fx, None if degraded else api, drift)
        if degraded:
            row["flags"] = list(row["flags"]) + ["retained_inventory_capture_degraded"]
        if not open_for_picks(row["start_utc"], row["lock_utc"], now):
            dropped.append({"fixture_id": fid, "reason": "lock time has passed"})
            continue
        rows.append(row)

    auto_added = []
    if not degraded:
        for fid in sorted(api_rows):
            if fid in ledger_ids:
                continue
            api = api_rows[fid]
            start, lock = _iso(_ms(api.get("scheduled_start_time"))), _iso(_ms(api.get("lock_time")))
            if not open_for_picks(start, lock, now):
                dropped.append({"fixture_id": fid, "reason": "lock time has passed"})
                continue
            row = auto_row(api, drift)
            rows.append(row)
            auto_added.append({"fixture_id": fid, "teams": f"{row['team_a']} vs {row['team_b']}",
                               "basis": row["line"]["basis"], "pick": row["line"]["pick"],
                               "blank_reason": row["blank_reason"]})

    rows.sort(key=lambda r: (r["start_utc"] or "9999", r["fixture_id"]))
    inventory = {
        "mode": "retained_inventory" if degraded else "fresh_capture",
        "capture_utc": capture_utc,
        "capture_path": ("data/1c8f79f8/fixtures_raw.json" if capture_path is None
                         else str(Path(capture_path))),
        "capture_fixtures": len(fixtures),
        "researched_fixtures_present": len(present),
        "open_rows": len(rows),
        "auto_rows": len(auto_added),
        "auto_added": auto_added,
        "dropped": dropped,
        "drift": drift,
        "degraded_reasons": degraded_reasons,
        "evaluated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": ("Every fixture in the fresh capture stays on the board. New listings are priced "
                   "from an exact fixture-id quote retained in another session's published board, "
                   "else from the canonical Valve-VRS model, else blank + flagged. Ownership drift "
                   "is recorded, never fatal."),
    }
    return rows, inventory


def build_board(rows: list[dict], inventory: dict | None = None) -> dict:
    # count by the PUBLISHED basis, not by the presence of a market dict
    # (some rows carry an untrained $0-volume Polymarket seed that is
    # retained as evidence but never weighted as a line)
    inventory = inventory or {}
    n_market = sum(1 for r in rows if r["line"]["basis"] in ("market", "blend"))
    n_model_only = sum(1 for r in rows if r["line"]["basis"] == "model")
    n_blank = sum(1 for r in rows if r["line"]["basis"] is None)
    n_pick = sum(1 for r in rows if r["line"]["pick"])
    n_climb = sum(1 for r in rows if r["ladder"]["climb"])
    n_real_market = sum(1 for r in rows if r["market"] and (
        (r["market"].get("volume_usd") is None)
        or (r["market"].get("volume_usd") or 0) > 0
        or r["market"]["n_sources"] >= 2))
    n_blank_pick = sum(1 for r in rows if r["line"]["basis"] is None and not r["line"]["pick"])
    return {
        "session": "1c8f79f8",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_utc": inventory.get("capture_utc") or "2026-10-16T20:50:00Z",
        "fixture_source_read_utc": inventory.get("capture_utc") or "2026-10-16T20:50:00Z",
        "week": "TWC 2026 day 4 (2026-10-17)",
        "summary": {
            "fixtures_total": len(rows), "open": len(rows),
            "open_with_market": n_market, "open_real_market": n_real_market,
        "open_model_only": n_model_only,
            "open_blank": n_blank, "open_with_pick": n_pick,
            "open_auto_rows": inventory.get("auto_rows", 0),
            "open_without_direction": n_blank_pick,
            "climb_picks": n_climb,
            "contrarian_picks": sum(1 for r in rows if r["role"] == "contrarian"),
            "twc_semifinals": 2, "twc_not_listed_on_hotspawn": True,
        },
        "inventory": inventory,
        "calibration": {"k": K_FIT, "fitted": True,
                        "source": "data/fe803b80/board.json calibration block "
                                  "(fitted on 15 bookmaker pairs; bounds [0.25, 1.5])"},
        "vrs": {"snapshot": "2026_10_05",
                "fresher_reads": "HLTV valve-ranking pages of 2026-10-14/15 for "
                                 "ex-6666, Privateer, Phantom Academy, antidaun",
                "evidence": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"},
        "open": rows,
        "twc": {
            "sf1": research.TWC["sf1"], "sf2": research.TWC["sf2"],
            "decider": research.TWC["decider"],
            "results": research.TWC_RESULTS, "schedule": research.TWC_SCHEDULE,
            "listing": "The Thunderpick World Championship Malta playoffs are NOT "
                       "listed on HotSpawn (no TWC Malta competition_id exists in the "
                       "fixtures API; verified 2026-10-16). Both semifinals are "
                       "originated externally and flagged not-listed.",
        },
        "ghost_rows": [{
            "fixture_id": "1080200", "competition": "FRAG University 2026",
            "teams": "Wildcard vs DENDELE",
            "explanation": "Present in the fe803b80 board's open array (their 22nd row) "
                           "but absent from every fixtures API read this session. The row "
                           "is dated 2026-11-12 with status 'started' — an impossible "
                           "combination — and was first seen 2026-10-14. It is a stale "
                           "capture artifact, not a day-4 fixture. The 22-vs-21 open-row "
                           "difference between boards is fully explained by this row.",
        }],
        "notes": [
            "HotSpawn crowd percentages are ownership context only and are never used "
            "as a probability input anywhere in this board (asserted by tests).",
            "status=scheduled includes stale past-dated rows (verified: competition "
            "captures returned June-2026 DraculaN rows and an Oct-16 NODWIN row with "
            "past start times); a client-side time filter is mandatory.",
            "egamersworld match-page widgets frequently show a 1.8/1.8 placeholder pair "
            "when no bookmaker average exists; those pairs are rejected as prices.",
            "Polymarket markets with $0.00 traded volume are untrained AMM seeds; they "
            "are retained as evidence but never weighted as lines.",
        ],
    }


# ---------------------------------------------------------------- HTML chrome
CSS = """
:root{--bg:#0d1524;--card:#142138;--txt:#e8eefc;--mut:#93a4c3;--line:#27354f;--acc:#3d7dff;--good:#1f9d63;--warn:#c9861b;--bad:#c4453c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:16px}
header.site{position:sticky;top:0;background:rgba(13,21,36,.96);border-bottom:1px solid var(--line);z-index:20}
header.site .wrap{padding:10px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
header.site a{color:var(--mut);text-decoration:none;font-size:13.5px;padding:6px 8px;border-radius:8px}
header.site a.on,header.site a:hover{background:var(--card);color:var(--txt)}
h1{font-size:24px;line-height:1.2;margin:10px 0}h2{font-size:19px;margin:26px 0 8px}h3{font-size:16.5px;margin:18px 0 6px}
p{margin:8px 0}.mut{color:var(--mut);font-size:13.5px}.eyebrow{color:#7fa7ff;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:11.5px;margin:0}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.card{flex:1 1 150px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.card-num{font-size:22px;font-weight:800}.card-label{color:var(--mut);font-size:12.5px}
.btn{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;font-weight:700;border-radius:12px;padding:13px 16px;margin:6px 6px 6px 0;min-height:44px}
.btn.ghost{background:transparent;border:1.5px solid var(--acc);color:#9cc0ff}
.btn.alt{background:var(--good)} .btn.alt2{background:#5b3fd6}
.btn.warn{background:var(--warn);color:#221602}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#b9c8e4;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.tag{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700}
.tag.pick{background:var(--good);color:#fff}.tag.climb{background:#5b3fd6;color:#fff}
.tag.mkt{background:#1d4ed8;color:#fff}.tag.mdl{background:#334155;color:#dbe7ff}
.tag.ori{background:var(--warn);color:#221602}.tag.blank{background:#3a2530;color:#ffb4ae}
.tag.contra{background:#7c3aed;color:#fff}.tag.safe{background:#0f766e;color:#fff}
a{color:#8db6ff}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:0;margin:10px 0}
details>summary{cursor:pointer;padding:12px 14px;font-weight:700}
details[open]>summary{border-bottom:1px solid var(--line)}
details .inner{padding:6px 14px 12px}
.tablewrap{overflow-x:auto}
@media (max-width:640px){
  h1{font-size:20px} .wrap{padding:12px}
  table.responsive thead{display:none}
  table.responsive tr{display:block;border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:6px 4px;background:var(--card)}
  table.responsive td{display:flex;justify-content:space-between;gap:12px;border:0;padding:5px 10px}
  table.responsive td:before{content:attr(data-label);color:#9db1d4;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;font-weight:700;flex:0 0 42%}
  .btn{display:block;text-align:center}
}
"""

PAGES = [
    ("index.html", "Start here"),
    ("picks.html", "All picks · every match"),
    ("twc-review.html", "TWC day 1–3 review"),
    ("unresolved.html", "Unresolved + limits"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method & sources"),
]


def page(title: str, active: str, body: str, generated: str) -> str:
    nav = "".join(
        '<a href="{}"{}>{}</a>'.format(href, ' class="on"' if href == active else "", label)
        for href, label in PAGES)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="TWC 2026 day-4 desk: verified playoff review, semifinal picks, and a pick plus probability for every open HotSpawn CS2 match, all source-linked.">
<style>{CSS}</style></head>
<body><header class="site"><div class="wrap"><strong style="font-size:14px">Day-4 desk · 1c8f79f8</strong>{nav}</div></header>
<main class="wrap">
{body}
<p class="mut">Generated {esc(generated)} · session 1c8f79f8 · fixtures API snapshot {esc(SNAPSHOT_STAMP)} · external lines read {esc(LINES_READ_STAMP)} · <a href="method.html">method &amp; sources</a> · <a href="https://play.hotspawn.com/lobby">HotSpawn lobby</a></p>
</main></body></html>"""


def source_links(sources: list[tuple[str, str]]) -> str:
    return " ".join(f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(n)}</a>' for n, u in sources)


def flags_html(flags: list[str]) -> str:
    if not flags:
        return '<span class="mut">—</span>'
    return " ".join(f'<span class="tag ori">{esc(f)}</span>' for f in flags)


# ---------------------------------------------------------------- index.html
def index_html(board: dict) -> str:
    s = board["summary"]
    twc = board["twc"]
    sf1, sf2 = twc["sf1"], twc["sf2"]
    climbs = [r for r in board["open"] if r["ladder"]["climb"]]
    contra = [r for r in board["open"] if r["role"] == "contrarian"]
    climb_bits = []
    for r in climbs:
        cp = r["ladder"]["climb_prob"]
        own = r["crowd_b"] if r["ladder"]["climb"].casefold() == r["team_b"].casefold() else r["crowd_a"]
        climb_bits.append(
            "<li><strong>{}</strong> over {} ({}, {}) — fair {} at crowd ownership {}% "
            "({:.1f}× the crowd's share){}</li>".format(
                esc(r["ladder"]["climb"]), esc(r["ladder"]["safe"]), esc(r["competition"]),
                esc(r["start_utc"][:16].replace("T", " ")) + "Z", pct(cp), own,
                cp / (own / 100),
                " at {} (bc.game)".format(format(r["ladder"]["climb_odds"], ".2f")) if r["ladder"]["climb_odds"] else " (no market price — originated line)"))
    contra_bits = []
    for r in contra:
        contra_bits.append(
            "<li><strong>{}</strong> in {} vs {} ({}) — fair {} against a crowd at {}% ownership</li>".format(
                esc(r["line"]["pick"]), esc(r["team_a"]), esc(r["team_b"]),
                esc(r["competition"]), pct(r["line"]["pick_probability"]),
                r["crowd_b"] if r["line"]["pick"].casefold() == r["team_b"].casefold() else r["crowd_a"]))
    body = f"""
<p class="eyebrow">Thunderpick World Championship 2026 · Malta · day 4 (Oct 17) + every open HotSpawn CS2 match</p>
<h1>Day-4 picks: two semifinals, {s['open']} open lobby matches, every row sourced</h1>
<p>BetBoom beat Legacy 2-1 in the Group B decider (Mirage 13-11; Magnojez 1.17) —
<strong>semifinal 2 is Falcons vs BETBOOM</strong>, 17:00 UTC. Semifinal 1 is
<strong>FURIA vs Aurora</strong>, 14:00 UTC. Neither semifinal is listed on the
HotSpawn pick'em lobby (verified: the fixtures API has no TWC Malta competition),
so both are originated externally and flagged not-listed. The lobby itself carries
<strong>{s['open']} open CS2 fixtures</strong> across the tournaments in the {esc(SNAPSHOT_STAMP)} snapshot.</p>
<div class="cards">
  <div class="card"><div class="card-num">{s['open']}</div><div class="card-label">open lobby fixtures — every one on the board</div></div>
  <div class="card"><div class="card-num">{s['open_with_market']}</div><div class="card-label">priced from external market lines</div></div>
  <div class="card"><div class="card-num">{s['open_model_only']}</div><div class="card-label">originated from the Valve-VRS model</div></div>
  <div class="card"><div class="card-num">{s['open_blank']}</div><div class="card-label">probability blank + flagged (policy)</div></div>
  <div class="card"><div class="card-num">{s['climb_picks']}</div><div class="card-label">contrarian climb swings (gates passed)</div></div>
  <div class="card"><div class="card-num">{s.get('open_auto_rows', 0)}</div><div class="card-label">rows auto-added from the live capture (new listings)</div></div>
</div>
<h2>The two day-4 semifinal picks (TWC Malta — not on HotSpawn)</h2>
<p><a class="btn" href="picks.html#twc">Semifinal picks + probabilities</a>
<a class="btn alt" href="twc-review.html">Verified day 1–3 review</a>
<a class="btn ghost" href="unresolved.html">Unresolved + limitations</a></p>
<details open><summary>Semifinal 1 — FURIA vs Aurora, Oct 17 14:00 UTC (Bo3, HLTV 2399414)</summary><div class="inner">
<p><span class="tag contra">contrarian</span> <strong>Pick: Aurora ML at {pct(sf1['fair'][1])}</strong>
(the market leans FURIA {pct(sf1['fair'][0])}; Polymarket FURIA 53¢/Aurora 49¢, egamersworld bc.game average FURIA 1.83/Aurora 1.90).
The line against the grain, with the grain's own tools: HLTV's <em>live</em> Valve-VRS forecast now rates Aurora
#5 (1848 pt) above FURIA #6 (1824 pt); Aurora won the only 2026 meeting 2-1 on Oct 6; Aurora is on a
three-consecutive-top-four run and just avenged the day-1 9z upset 2-0 (kyxsan 1.45); FURIA lost 0-2 to MOUZ
twice at EPL S24. Buy Aurora only at ≥1.95 (break-even for 52% is 1.92). <a href="picks.html#twc">Full row with sources</a>.</p>
</div></details>
<details open><summary>Semifinal 2 — Falcons vs BETBOOM, Oct 17 17:00 UTC (Bo3, HLTV 2399415)</summary><div class="inner">
<p><span class="tag safe">safe</span> <strong>Pick: Falcons ML at {pct(sf2['fair'][0])}</strong> — no published semifinal
line exists yet (Polymarket's TWC index carries only the decider and FURIA–Aurora markets; verified by absence).
Fair estimate sits between the Valve-VRS model (Falcons 58.6%) and comparable market pricing (Falcons 1.28 vs 9z).
The contrarian watch: BETBOOM ML is only +EV at ≥2.80 (fair 34%) — Magnojez 1.17 in the decider, zorte's 51-kill
PARIVISION match and an 80% half-year Mirage winrate are real, but FURIA beat this roster 2-0 on day one.
<a href="picks.html#twc">Full row with sources</a>.</p>
</div></details>
<h2>Contrarian climb swings on the lobby (gates documented on every row)</h2>
<ul>{''.join(climb_bits)}</ul>
<h2>Contrarian leans (gates documented, not activated)</h2>
<ul>{''.join(contra_bits)}</ul>
<p class="mut">Crowd ownership is recorded on every row as context only. It is never blended into any probability:
every number on this site is a de-vigged external market price, the canonical Valve-VRS model, or a documented blank.</p>
<h2>Navigate the desk</h2>
<p><a class="btn" href="picks.html">All picks · every match</a>
<a class="btn alt" href="twc-review.html">TWC day 1–3 verified review</a>
<a class="btn alt2" href="flagged.html">Flagged irregularities</a>
<a class="btn ghost" href="method.html">Method &amp; sources</a></p>
<p>The unresolved picks and limitations live in their own section with in-site links from
<a href="unresolved.html">here</a> — including the two probability blanks, the missing semifinal-2 line,
and the unpriced TWC Sunday matches.</p>
"""
    return body


# ---------------------------------------------------------------- picks.html
def picks_html(board: dict) -> str:
    parts = [f"""
<p class="eyebrow">Every open match · {esc(SNAPSHOT_STAMP)} snapshot</p>
<h1>All picks: every open HotSpawn CS2 match</h1>
<p>One row per open fixture. Fair probability is the de-vigged external market price where a real
two-sided market exists, the canonical Valve-VRS model (k=0.25) where it does not, and a documented
blank where neither policy permits a number. Crowd % is ownership context, never an input.</p>
"""]
    # TWC block first
    twc = board["twc"]
    parts.append('<h2 id="twc">Thunderpick World Championship 2026 — Malta playoffs (not listed on HotSpawn)</h2>')
    parts.append('<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>When (UTC)</th><th>Line basis</th><th>Fair probabilities</th><th>Pick</th><th>Prob</th><th>Role</th><th>Sources</th></tr></thead><tbody>')
    for key, label in (("sf1", "Semifinal 1"), ("sf2", "Semifinal 2")):
        m = twc[key]
        a, b = m["teams"]
        fa, fb = m["fair"]
        market_note = m["market"]["note"] if m["market"] else ""
        basis = m["market"]["basis"] if m["market"] and m["market"].get("basis") else "no published line — documented estimate"
        parts.append(
            f'<tr><td data-label="Match"><strong>{esc(label)}</strong><br>{esc(a)} vs {esc(b)}<br><span class="mut">Bo3 · HLTV {esc(str(m["hltv_match_id"]))}</span></td>'
            f'<td data-label="When">{esc(m["start_utc"][:16].replace("T", " "))}</td>'
            f'<td data-label="Line basis">{esc(basis)}</td>'
            f'<td data-label="Fair probabilities">{esc(a)} {pct(fa)}<br>{esc(b)} {pct(fb)}</td>'
            f'<td data-label="Pick"><span class="tag pick">{esc(m["pick"])}</span></td>'
            f'<td data-label="Probability">{pct(m["pick_prob"])}</td>'
            f'<td data-label="Role"><span class="tag {"contra" if m["role"] == "contrarian" else "safe"}">{esc(m["role"])}</span></td>'
            f'<td data-label="Sources">{source_links(m["sources"])}</td></tr>')
    parts.append('</tbody></table></div>')
    d = twc["decider"]
    maps = ", ".join(f"{mn} {sa}-{sb}" for mn, sa, sb in d["maps"])
    parts.append(f"""
<details><summary>Verified: Group B decider — {esc(d['teams'][0])} vs {esc(d['teams'][1])} → {esc(d['result'])} ({maps})</summary>
<div class="inner"><p>{esc(d['note'])}</p><p>Sources: <a href="{esc(d['hltv_url'])}" target="_blank" rel="noopener">HLTV match page (map-level result)</a> ·
<a href="https://bo3.gg/matches/legacy-br-vs-betboom-team-16-10-2026" target="_blank" rel="noopener">bo3.gg live page (team analytics)</a> ·
<a href="https://polymarket.com/esports/cs2/thunderpick-world-championship" target="_blank" rel="noopener">Polymarket decider market (resolved)</a></p></div></details>
<p class="mut">Sunday's 3rd-place decider (Oct 18 11:30 UTC) and grand final (15:00 UTC, Bo5) cannot be priced until the
semifinals resolve — the opponents are TBD. Documented in <a href="unresolved.html">unresolved + limitations</a>.</p>
""")

    # lobby block
    parts.append(f'<h2 id="lobby">HotSpawn pick\'em lobby — all {len(board["open"])} open fixtures</h2>')
    parts.append('<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>When (UTC)</th><th>Crowd ownership (context)</th><th>Line basis</th><th>Fair probabilities</th><th>Pick</th><th>Prob</th><th>Role</th><th>Sources</th></tr></thead><tbody>')
    for r in board["open"]:
        a, b = r["team_a"], r["team_b"]
        basis = {"market": "market", "model": "VRS model", "blend": "market + model", "estimate": "estimate", None: "blank"}[r["line"]["basis"]]
        basis_tag = {"market": "mkt", "model": "mdl", "blend": "mkt", "estimate": "ori", None: "blank"}[r["line"]["basis"]]
        role_tag = {"safe": "safe", "climb": "climb", "contrarian": "contra", "directional": "ori"}[r["role"]]
        crowd = f"{a} {r['crowd_a']}%<br>{b} {r['crowd_b']}%"
        if r["line"]["prob_a"] is None:
            fair = "blank + flagged"
            prob = "blank"
        else:
            fair = f"{esc(a)} {pct(r['line']['prob_a'])}<br>{esc(b)} {pct(r['line']['prob_b'])}"
            prob = pct(r["line"]["pick_probability"])
        climb_note = ""
        if r["ladder"]["climb"]:
            gates = esc(r["ladder"].get("climb_gates") or "")
            climb_note = (f"<br><span class='tag climb'>climb: {esc(r['ladder']['climb'])} "
                          f"{pct(r['ladder']['climb_prob'])}</span>"
                          f"<br><span class='mut'>ladder gates: {gates}</span>")
        parts.append(
            f'<tr id="fx{r["fixture_id"]}"><td data-label="Match"><strong>{esc(a)} vs {esc(b)}</strong><br>'
            f'<span class="mut">{esc(r["competition"])} · {esc(r["stage"])} · tier {esc(r["tier"])} · {r["points"]} pts</span>{climb_note}</td>'
            f'<td data-label="When">{esc(r["start_utc"][:16].replace("T", " "))}<br><span class="mut">lock {esc(r["lock_utc"][11:16])}</span></td>'
            f'<td data-label="Crowd ownership (context)">{crowd}<br><span class="mut">{r["total_picks"]} picks</span></td>'
            f'<td data-label="Line basis"><span class="tag {basis_tag}">{basis}</span><br><span class="mut">{esc(r["line"]["confidence"])}</span></td>'
            f'<td data-label="Fair probabilities">{fair}</td>'
            f'<td data-label="Pick"><span class="tag pick">{esc(r["line"]["pick"])}</span></td>'
            f'<td data-label="Probability">{prob}</td>'
            f'<td data-label="Role"><span class="tag {role_tag}">{esc(r["role"])}</span></td>'
            f'<td data-label="Sources">{source_links(r["sources"])}</td></tr>')
    parts.append('</tbody></table></div>')
    parts.append("""
<details><summary>How to read a row (line-by-line verification)</summary><div class="inner">
<p><strong>Line basis</strong>: <span class="tag mkt">market</span> = de-vigged price from a real venue
(Polymarket exchange, bc.game / bookmaker averages via egamersworld, stavka.tv consensus, kushvsporte aggregate);
<span class="tag mdl">VRS model</span> = the canonical Valve-VRS model (k=0.25) on Valve's own points;
<span class="tag ori">originated/estimate</span> = documented judgment where no market exists;
<span class="tag blank">blank</span> = no eligible evidence, probability deliberately empty.</p>
<p><strong>Role</strong>: <span class="tag safe">safe</span> = expected-points pick (best available line);
<span class="tag climb">climb</span> = leaderboard swing that passed every ladder gate (underdog fair ≥30%,
crowd ownership ≤20%, probability/ownership ≥2×, ≥2 verified context flags);
<span class="tag contra">contrarian</span> = against the market or the crowd with the gates documented;
<span class="tag ori">directional</span> = pick without a publishable probability.</p>
<p>Every row expands its full context, flags and per-source links on the
<a href="method.html">method page</a>; every irregularity is on the <a href="flagged.html">flagged page</a>.</p>
</div></details>
""")
    return "\n".join(parts)


# ---------------------------------------------------------------- twc-review.html
def twc_review_html(board: dict) -> str:
    twc = board["twc"]
    rows = []
    for date, stage, team_a, score, team_b, maps in twc["results"]:
        links = research.TWC_RESULTS_SOURCES.get((date, team_a, team_b), [])
        links_html = " ".join(
            f"<a href='{esc(url)}' target='_blank' rel='noopener'>{esc(label)}</a>"
            for label, url in links) or "<span class='mut'>no official link retained</span>"
        rows.append(f"<tr><td data-label='Date'>{esc(date)}</td><td data-label='Stage'>{esc(stage)}</td>"
                    f"<td data-label='Match'><strong>{esc(team_a)} {esc(score)} {esc(team_b)}</strong></td>"
                    f"<td data-label='Maps'>{esc(maps)}</td>"
                    f"<td data-label='Sources'>{links_html}</td></tr>")
    body = f"""
<p class="eyebrow">Thunderpick World Championship 2026 · Attard, Malta · $1,000,000 · Oct 14–18</p>
<h1>Verified day 1–3 review: what actually happened</h1>
<p>Every result below was verified map-level on the HLTV results page for the event, the strafe bracket and
egamersworld's match pages (read 2026-10-16T19:55–20:40Z). This is the evidence base for both semifinal picks.</p>
<h2>All ten group-stage results</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Date</th><th>Stage</th><th>Series</th><th>Maps</th><th>Sources</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>The day-1 upset and the day-3 avenge</h2>
<p><strong>9z 2-0 Aurora (Oct 14)</strong> — the day-1 upset (Inferno 13-11, Nuke 13-1) was real: Aurora, the
Valve-#9 side, went out of the winners' bracket immediately. But it was not a new-team fluke: Aurora's roster is
unchanged since July (see the roster investigation below). On Oct 16 Aurora ran the rematch back 2-0
(Cache 13-11, Inferno 13-4) with kyxsan at 1.45 (MVP) — the same map pool, the same opponent, a decisive
performance improvement. Three consecutive top-four finishes (StarSeries runner-up, EPL S24 third, here)
make Aurora the form side of this bracket.</p>
<h2>The decider: why BetBoom's win was the upset</h2>
<p>The Group B decider was priced Legacy ~1.50–1.54 / BetBoom ~2.50–2.60 across stavka.tv, cybersport.ru,
metaratings, egamersworld and Polymarket (Legacy 62¢/BetBoom 39¢) — a 63/37 market consensus. BetBoom won
13-11 on the Mirage decider after losing Nuke 16-13 and taking Dust2 11-13. bo3.gg's analytics flagged the
tells in advance: BetBoom carried an 80% Mirage winrate over the prior half-year, and Magnojez (1.17 series,
62-50 K-D) was the best player on the server. HLTV's simulation had BetBoom at 89.1% to reach the PGL
Singapore Major before the decider — the market underpriced the team that needed it most.</p>
<h2>Aurora roster investigation (the "recent roster change" premise)</h2>
<p><strong>Premise checked and disproven for October: no October roster change exists.</strong> The last
verified change is the July 2026 rebuild — Jimpphat and coach ash signed July 3, captain kyxsan (the new IGL)
signed July 8 (HLTV team timeline; primary-confirmed by Aurora's own announcements as archived in the
day-3 desk's <a href="../twc-2026/roster.html">roster timeline</a>). The current XI — XANTARES, woxic,
Jimpphat, kyxsan, Wicadia — matches the Oct-5 Valve VRS row 5/5 and egamersworld's lineup 5/5. The "deko"
entry on HLTV's timeline is a historical (2023-era) item, not a recent move. What <em>is</em> recent is the
onboarding: a brand-new IGL and three of five players were still bedding in during the day-1 9z loss, and
the day-3 2-0 avenge (kyxsan 1.45) is the onboarding-complete signal. That timeline — not a phantom
October move — is the honest basis for the Aurora semifinal pick.</p>
<h2>Semifinal preview</h2>
<details open><summary>FURIA vs Aurora — Oct 17 14:00 UTC (Bo3)</summary><div class="inner">
<p>Market: Polymarket FURIA 53¢/Aurora 49¢ ($182 vol), egamersworld bc.game average FURIA 1.83/Aurora 1.90,
vprognoze Aurora 1.85 — a coin flip with FURIA a hair favored. Against the grain: HLTV's live VRS forecast
rates Aurora #5 (1848 pt) above FURIA #6 (1824 pt); Aurora won the only 2026 meeting 2-1 (EPL S24, Oct 6);
Aurora's three straight top-fours vs FURIA's double 0-2 MOUZ losses at EPL S24. HLTV's fan vote (Aurora 73.5%)
is sentiment, not a price. <strong>Pick: Aurora, 52%</strong> — buy at ≥1.95. Full row:
<a href="picks.html#twc">picks table</a>.</p></div></details>
<details open><summary>Falcons vs BETBOOM — Oct 17 17:00 UTC (Bo3)</summary><div class="inner">
<p>No published line exists yet (Polymarket's TWC index had only two markets at read time). Anchors:
Valve VRS Falcons #6 (1843) vs BETBOOM #11 (1596) → model 58.6% Falcons; comparable priced lines put Falcons
near 1.28 vs weaker VRS opposition (9z, #17). Falcons are the reigning Major champions (m0NESY 1.62 vs NiP);
BetBoom arrives hot (reverse-sweep of PARIVISION, decider win, zorte 51 kills) but lost 0-2 to FURIA on day one.
<strong>Pick: Falcons, 66%</strong> (documented estimate between model and comps). BETBOOM ML is only +EV at
≥2.80. Full row: <a href="picks.html#twc">picks table</a>.</p></div></details>
<h2>Remaining schedule</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Teams</th><th>When (UTC)</th><th>Format</th><th>Reference</th></tr></thead><tbody>
{''.join(f"<tr><td data-label='Match'>{esc(n)}</td><td data-label='Teams'>{esc(t)}</td><td data-label='When'>{esc(w[:16].replace('T',' '))}</td><td data-label='Format'>{esc(f)}</td><td data-label='Reference'>{esc(r)} · <a href='https://www.hltv.org/events/8932/thunderpick-world-championship-2026'>official HLTV event page</a></td></tr>" for n, t, w, f, r in twc["schedule"])}
</tbody></table></div>
<p class="mut">The 3rd-place decider and grand final cannot be priced until both semifinals resolve — the
opponents are TBD. This is a limitation, not a blank to fill later without evidence; the
<a href="unresolved.html">unresolved section</a> tracks it.</p>
"""
    return body


# ---------------------------------------------------------------- unresolved.html
def unresolved_html(board: dict) -> str:
    blanks = [r for r in board["open"] if r["line"]["prob_a"] is None]
    locks = sorted(r["lock_utc"] for r in board["open"] if r.get("lock_utc"))
    next_lock = locks[0] if locks else "unpublished"
    bits = []
    for r in blanks:
        bits.append(f"""
<details open><summary>{esc(r['team_a'])} vs {esc(r['team_b'])} — {esc(r['competition'])} ({esc(r['start_utc'][:16].replace('T',' '))}Z) — probability BLANK</summary>
<div class="inner">
<p><span class="tag blank">{esc(r['blank_reason'])}</span></p>
<p><strong>What was tried</strong> (source reads {esc(LINES_READ_STAMP)}):</p>
<ul>{''.join(f'<li>{esc(c)}</li>' for c in r['context'])}</ul>
<p><strong>Why no number is published:</strong> the row records its own reason
(<code>{esc(r['blank_reason'])}</code>). Either no venue publishes an accepted two-sided price for this
match, or at least one team is absent from Valve's official standings so no model pair is eligible. A
probability is withheld rather than invented; any pick direction shown comes from verified context only and
carries no probability.</p>
<p>Sources: {source_links(r['sources'])}</p>
</div></details>""")
    inv = board.get("inventory") or {}
    auto_rows = [r for r in board["open"] if r.get("row_origin") == "auto_from_capture"]
    auto_bits = "".join(
        f"<li><strong>{esc(r['team_a'])} vs {esc(r['team_b'])}</strong> — {esc(r['competition'] or 'competition not in capture')}, "
        f"starts {esc((r['start_utc'] or 'unpublished')[:16].replace('T',' '))}Z — "
        f"basis <code>{esc(r['line']['basis'] or 'blank')}</code>, "
        f"pick <code>{esc(r['line']['pick'] or 'none — see the blank row above')}</code></li>"
        for r in auto_rows)
    gen = (f"<p>Last local rebuild {esc(inv.get('evaluated_utc') or board.get('generated_utc') or 'unverified')} "
           f"against the {esc(inv.get('mode') or 'unrecorded')} capture "
           f"<code>{esc(inv.get('capture_path') or 'unrecorded')}</code>"
           + (f" (captured {esc(inv.get('capture_utc'))})" if inv.get("capture_utc") else "")
           + f", covering {esc(inv.get('capture_fixtures', 'unverified'))} listed fixtures.</p>")
    if inv.get("degraded_reasons"):
        gen += ("<p class='mut'><strong>Retained-inventory mode:</strong> "
                + esc("; ".join(inv["degraded_reasons"]))
                + ". The board keeps the last researched fixtures with a flag instead of shrinking "
                  "silently; every retained row carries "
                  "<code>retained_inventory_capture_degraded</code>.</p>")
    if inv.get("drift"):
        gen += ("<p class='mut'>Live drift recorded this rebuild: "
                + esc("; ".join(f"{d['fixture_id']} {d['issue']}" for d in inv["drift"][:12]))
                + (f" (+{len(inv['drift']) - 12} more)" if len(inv["drift"]) > 12 else "")
                + ". Ownership and kickoff drift are context; they never change a probability.</p>")
    auto_section = f"""
<h2>Rows generated automatically from the live capture</h2>
{gen}
{'<ul>' + auto_bits + '</ul>' if auto_bits else '<p>No fixture outside the curated ledger was listed in this capture. The path that adds them (exact fixture-id quote reuse → Valve-VRS model → blank + flag) is exercised by tests/test_1c8f79f8.py.</p>'}
<p>Every fixture the lobby lists stays on the <a href="picks.html">picks table</a>: a new listing is either
priced from an exact fixture-id quote retained in another published board, priced by the canonical Valve-VRS
model when both teams are in Valve's official standings, or published as a blank row with its reason. Nothing
is dropped for being low-tier.</p>
"""
    body = f"""
<p class="eyebrow">Unresolved picks &amp; limitations — nothing here is guessed</p>
<h1>Unresolved picks and limitations</h1>
<p>{len(blanks)} of {len(board['open'])} open lobby fixtures keep a <strong>blank probability</strong> by
policy, and several other gaps are documented rather than filled. Each blank lists everything that was tried
and the exact reason no number can be published. A blank is never a 50/50 estimate.</p>
<h2>Probability blanks ({len(blanks)} of {len(board['open'])})</h2>
{auto_section}
{''.join(bits)}
<h2>Other documented limitations</h2>
<details><summary>Semifinal 2 has no published line anywhere</summary><div class="inner">
<p>Falcons vs BETBOOM (Oct 17 17:00 UTC): Polymarket's TWC index carried only the decider and FURIA–Aurora
markets at read time; bo3.gg, stavka.tv, egamersworld and metaratings had not opened the semifinal. The 66/34
fair estimate is a documented estimate between the Valve-VRS model (58.6% Falcons) and comparable priced
lines (Falcons 1.28 vs 9z) — it is labelled an estimate on its row, not presented as a market price.
If a line publishes before kickoff, the 4-hour refresh re-derives the row from it.</p></div></details>
<details><summary>TWC Sunday matches are unpriceable until the bracket resolves</summary><div class="inner">
<p>The 3rd-place decider (Oct 18 11:30 UTC) and the grand final (15:00 UTC, Bo5) have TBD opponents. No
probability is originated for a match whose participants do not exist yet. They will be priced in the next
refresh once both semifinals settle.</p></div></details>
<details><summary>Polymarket markets with $0 traded volume are not lines</summary><div class="inner">
<p>Apogee Betclic–Nemesis, Nexus–WBT, aimclub–BASEMENT BOYS, ASTRAL–Leo and Banda chuya–Enjoy all carry
Polymarket pages at $0.00 volume. These are untrained automated-market-maker seeds (some stale — the
ASTRAL–Leo seed reads 96¢/97¢, a 193¢ book), so they are retained as evidence of the market's existence but
never weighted as prices. Where a real bookmaker average exists (egamersworld) or the Valve-VRS model applies,
that is the basis instead.</p></div></details>
<details><summary>egamersworld 1.8/1.8 placeholder pairs are not lines</summary><div class="inner">
<p>egamersworld's match-page widget renders a 1.8/1.8 default pair when no bookmaker average is available
(verified on GenOne–Butterfly, Banda chuya–Enjoy, ex-6666–Privateer, antidaun–Phantom Academy and all four
VOID Autumn Cup match pages). These are rejected as prices. Where the egamersworld <em>matches index</em>
carries a real average (Rare Atom–Alter Ego 1.62/2.15; WBT–Nexus 1.72/1.96), that fresher feed is used and
the widget discrepancy is flagged on the row.</p></div></details>
<details><summary>Crowd ownership moved during the capture session</summary><div class="inner">
<p>HotSpawn pick'em ownership is live and moved while this desk was researched (e.g. NIP–HEROIC flipped
56/44 → 43/57; Rare Atom–Alter Ego flipped 29/71 → 56/44; Eternal Fire–Nuclear TigeRES moved 35/65 → 43/57).
Ownership percentages are recorded at the 20:50Z snapshot as context only; they never enter any probability.
The 4-hour refresh re-captures them.</p></div></details>
<details><summary>Staleness bound</summary><div class="inner">
<p>Fixture snapshot {esc(SNAPSHOT_STAMP)}; external lines read {esc(LINES_READ_STAMP)}. The desk refreshes
every 4 hours (workflow <code>day4-1c8f79f8.yml</code>, cron <code>23 */4 * * *</code>). Matches lock
6 minutes before kickoff (verified lock_offset_sec=360); the next lock in this snapshot is
{esc(next_lock)}.</p></div></details>
<h2>In-site links</h2>
<p><a href="index.html">Executive summary</a> · <a href="picks.html">All picks with per-row sources</a> ·
<a href="twc-review.html">TWC day 1–3 verified review</a> · <a href="flagged.html">Flagged irregularities</a> ·
<a href="method.html">Method &amp; sources</a></p>
"""
    return body


# ---------------------------------------------------------------- flagged.html
def flagged_html(board: dict) -> str:
    items = [
        ("Identity alias: 'WROTBERRY' = WBT = WhiteBIT Team",
         "The HotSpawn fixtures API renders the DraculaN Season 7 Group B team as 'WROTBERRY'. egamersworld's "
         "team slug for the same opponent is 'wrotberry'; Liquipedia, HLTV (team 13683), strafe and tips.gg all "
         "list WhiteBIT Team (WBT) in Group B against Nexus on Oct 19 at the same slot. Same event, group, date "
         "and time — the identity is resolved with high confidence, and the egamersworld/Polymarket lines for "
         "WBT–Nexus apply to the HotSpawn row.",
         [("HLTV WBT team overview (roster verification)", "https://www.hltv.org/team/13683/wbt"),
          ("Liquipedia DraculaN Season 7 (Group B: WhiteBIT Team)", "https://liquipedia.net/counterstrike/DraculaN/Season_7"),
          ("egamersworld WBT vs Nexus Gaming (bookmaker average 1.72/1.96)", "https://egamersworld.com/counterstrike/match/V1JAWhPomg/wbt-vs-nexus-gaming-A-jHKvluZk")]),
        ("Identity: 'Apogee Betclic' = Betclic Apogee Esports = Valve's 'Betclic'",
         "The HotSpawn API renders the Polish organization as 'Apogee Betclic'; Valve's standings table lists it "
         "as 'Betclic' (#45, 1333 pt; Demho, ex1st, Prism, Qlocuu, ultimate — the PGL Bucharest 2025 qualifier "
         "org). It is NOT the French Betclic org's other entries. The Valve row is used for the model line and "
         "the identity is recorded so future refreshes join correctly.",
         [("stavka.tv team page — Betclic Apogee identity and history", "https://stavka.tv/teams/csgo/betclic-apogee-esports-7"),
          ("Valve regional standings 2026-10-05 (Betclic #45)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md")]),
        ("Aurora 'recent roster change' premise — not verified, disproven for October",
         "The premise given to this desk ('there was a recent roster change for Aurora') could not be verified "
         "for October 2026 across HLTV's team timeline, Liquipedia, egamersworld lineups and the Valve VRS "
         "roster row. The last verified change is the July 2026 rebuild (Jimpphat + coach ash, July 3; captain "
         "kyxsan, July 8 — three of five players new plus a new IGL). The July rebuild IS the onboarding story "
         "and it is published as such: the day-1 9z loss fits a new lineup's rough patch, the day-3 2-0 avenge "
         "(kyxsan 1.45) fits onboarding complete. The 'deko' entry on HLTV's timeline is a historical 2023-era "
         "item. Any October move, if one exists, is not visible in any source checked — treated as an "
         "irregularity in the premise, non-blocking.",
         [("HLTV Aurora team overview (timeline)", "https://www.hltv.org/team/11861/aurora"),
          ("HLTV news 45736 — Aurora beat 9z, semis rematch (Oct 16)", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
          ("egamersworld FURIA vs Aurora (lineups match the July rebuild 5/5)", "https://egamersworld.com/counterstrike/match/5X5sFiL7H/furia-vs-aurora-Z00JFz0dG"),
          ("Valve regional standings 2026-10-05 (Aurora roster row)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md")]),
        ("Post-snapshot roster changes on five lobby teams",
         "Alter Ego (shadiy + BloodyK in for BnTeT + Gratisfaction — two changes), Enjoy (reyoz + TBD in for "
         "roxesz + zazzer — two changes), ex-6666 (the entity itself is new: four players left the 6666 "
         "organization on Oct 14 and added stefienson), Privateer (moz in for Ariant0), Phantom Academy "
         "(stefienson out to ex-6666; fifth player unconfirmed), GenOne (SIXER listed where the Oct-5 Valve row "
         "carries Chucky), Chinggis Warriors (tikuak for yAmi), Vitalem Aerem (ProKiller for BZA), antidaun "
         "(Pedrinho2011 where the Oct-14 valve-ranking carries maddeN). Where a roster changed after the Oct-5 "
         "Valve snapshot, the model line is flagged as potentially stale on its row.",
         [("HLTV ex-6666 team overview (Oct 14 transfer log)", "https://www.hltv.org/team/14100/ex-6666"),
          ("egamersworld Alter Ego lineup evidence (Rare Atom match page)", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/rare-atom-vs-alter-ego-O8GeLuSod4"),
          ("egamersworld Enjoy lineup evidence (Banda chuya match page)", "https://egamersworld.com/counterstrike/match/1sGIL2gAYu/banda-chuya-vs-enjoy-9ru7xO5OG")]),
        ("HotSpawn API quirks (affects every refresh)",
         "(1) status=scheduled returns stale past-dated rows — verified: June-2026 DraculaN rows, an Oct-13 "
         "CCT SA row (1081105), an Oct-14 CCT EU S11 row (1079621) and an Oct-16 NODWIN row (1079167) all "
         "returned 'scheduled' at capture time; a client-side time filter is mandatory. (2) The API rejects "
         "from/limit/tier query parameters (400 'property should not exist'); only sport_alias, status and "
         "competition_id are accepted. (3) Crowd percentages can sum to 101 (NEXVOID–Vitalem Aerem row) — "
         "API rounding. (4) The fe803b80 board's 22nd open row (1080200, FRAG University, Wildcard vs DENDELE) "
         "is dated 2026-11-12 with status 'started' — an impossible combination and a stale capture artifact; "
         "it explains the 22-vs-21 open-row difference between boards and is not a day-4 fixture.",
         [("Fixtures API (per-competition capture, evidence retained in data/1c8f79f8/evidence/)", "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures?sport_alias=cs2&status=scheduled&competition_id=36412"),
          ("fe803b80 board (the 22-open capture being diffed)", "https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/data/fe803b80/board.json")]),
        ("CORRECTED: the day-1 9z-Aurora Nuke map score (13-1, not 13-4)",
         "The first published version of this desk's day-1 table read 'Nuke 13-4'. That value is wrong. "
         "Eight independent captures retained in this repository carry Nuke 13-1 for 9z (the "
         "b3b89eec verification even retains the half scores 11:1 and 2:0), and 13-4 is the day-3 "
         "Inferno score in the same table -- the two were transposed. The row is corrected to "
         "13-1 and the discrepancy is recorded here, in the integration verification page and in "
         "the research ledger comment. No probability was ever derived from the map score: results "
         "are editorial context and never enter the line.",
         [("HLTV match page for the day-1 series (result source cited by every prior session)",
           "https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"),
          ("HLTV report 45718 - 9z beat Aurora to kick off TWC 2026",
           "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026"),
          ("Official HotSpawn day-1 review (publisher report)",
           "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-day-1-review")]),
        ("HLTV's match-page percentage widget is a fan vote, not a price",
         "The 'Pick a winner — please login to vote' widget on HLTV match pages (e.g. Aurora 73.5% on the "
         "FURIA match, NIP 52.7% on the HEROIC match) is a crowd vote. It is recorded as sentiment context "
         "only and is never used as a probability, consistent with the site's policy that HotSpawn crowd "
         "percentages are ownership context only.",
         [("HLTV FURIA vs Aurora match page (fan vote visible above the lineups)", "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
          ("HLTV NIP vs HEROIC match page", "https://www.hltv.org/matches/2399266/ninjas-in-pyjamas-vs-heroic-stake-pulse-beat-iii")]),
        ("Live VRS forecast disagrees with the Oct-5 snapshot on FURIA–Aurora",
         "The Oct-5 Valve snapshot has FURIA 1829 pt (#7) above Aurora 1716 pt (#9), but HLTV's live VRS "
         "forecast on match day reads Aurora 1848 pt (#5) vs FURIA 1824 pt (#6) — the direction flips after "
         "group play. The published fair probability (Aurora 52%) follows the live forecast, the head-to-head "
         "and form; the snapshot disagreement is documented rather than hidden.",
         [("HLTV FURIA vs Aurora match page (live VRS forecast widget)", "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026"),
          ("Valve regional standings 2026-10-05 (snapshot evidence)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md")]),
    ]
    cards = "".join(
        "<details><summary>{}</summary><div class=\"inner\"><p>{}</p>"
        "<p>Sources: {}</p></div></details>".format(esc(t), esc(d), source_links(s))
        for t, d, s in items)
    return f"""
<p class="eyebrow">Every irregularity found this session — non-blocking, published</p>
<h1>Flagged for review</h1>
<p>None of these block a pick; each changes how a row should be read. Flags are also attached to the
individual rows in the <a href="picks.html">picks table</a>.</p>
{cards}
"""


# ---------------------------------------------------------------- method.html
def method_html(board: dict) -> str:
    return """
<p class="eyebrow">How every number on this desk is produced</p>
<h1>Method &amp; sources</h1>
<h2>Fixture discovery (the lobby, reverse-engineered)</h2>
<p>The HotSpawn pick'em lobby renders from a JSON state bundle; the underlying fixtures API
(<code>phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code>) accepts exactly three filter
parameters — <code>sport_alias</code>, <code>status</code> and <code>competition_id</code> (discovered this
session; <code>from</code>, <code>limit</code> and <code>tier</code> are rejected with 400 "property should
not exist"). The <code>competition_id</code> filter returns a small single-chunk JSON per tournament, which
is how this desk captures cleanly: seven per-competition captures cover every open fixture. The unfiltered
response spans 9 chunks and mixes in stale rows. Every raw response is retained verbatim under
<code>data/1c8f79f8/evidence/</code> before any derivation.</p>
<p>Verified API fields per row: <code>id</code>, <code>competition_id/name</code>,
<code>scheduled_start_time</code>/<code>lock_time</code> (ms epochs; lock = start − 360 000 ms,
i.e. the 6-minute lock verified via <code>lock_offset_sec=360</code>), <code>offered_points</code>/<code>base_points</code>
(tier B = 3 offered, tier C = 2; points_breakdown = game 1.25 × tier (B 1.5 / C 1) × series/stage/tournament 1),
<code>tier</code> (a/b/c), <code>stage</code>, <code>total_picks</code>, and per-participant
<code>id/name/picked_percent/score</code>. Epoch anchor re-verified this session: 2026-10-17T00:00Z =
1792195200 s; the lobby renders times in US-Eastern, so "Oct 17, 04:00" on a card is 08:00Z.</p>
<h2>Probability policy (three bases, never blended silently)</h2>
<ol>
<li><strong>Market</strong> — a real two-sided price from a venue (Polymarket exchange moneyline; bc.game /
bookmaker averages via egamersworld; stavka.tv Russian bookmaker consensus; kushvsporte aggregate). The
published fair share is the de-vigged price: p = (1/dec) / Σ(1/dec). Volume is recorded; $0.00-volume
Polymarket seeds are evidence, never lines.</li>
<li><strong>Model</strong> — the canonical site Valve-VRS model, identical arithmetic to
<code>scripts/fe803b80/core.py</code> (Valve's glicko constants: a 400-point rank delta = 90% win chance,
Q = ln(10)/400, fixed RD = 75) with the fitted scale k = 0.25 from the fe803b80 calibration block. Used only
when both teams are unambiguously present in Valve's official standings with matching rosters.</li>
<li><strong>Blank</strong> — where neither basis is eligible, the probability stays empty and the row says
why. A pick direction may still be given from verified context and is labelled directional.</li>
</ol>
<p><strong>HotSpawn crowd percentages are ownership context only.</strong> They are stored on every row,
displayed next to the line, and never enter any probability — asserted by tests. Where the crowd and the
line disagree, that disagreement is the contrarian signal and is documented as such.</p>
<h2>The contrarian ladder (gates, applied per row)</h2>
<ul>
<li><strong>Safe pick</strong> — the best available line (market if it exists, else model).</li>
<li><strong>Climb pick</strong> — a leaderboard swing, activated only when ALL gates hold: underdog fair
probability ≥ 30–35%; crowd ownership of the picked side ≤ 20%; fair-probability/ownership ratio ≥ 2×;
≥ 2 verified context flags; capped swings per day. Three climbs activated today: Donstu, Enjoy, WBT.</li>
<li><strong>Contrarian lean</strong> — gates documented but not all passed (e.g. ASTRAL at 24% ownership
misses the 20% gate); published as a lean, never as an activated swing.</li>
</ul>
<h2>Source hierarchy</h2>
<ol>
<li>Official: Valve VRS repo (github.com/ValveSoftware/counter-strike_regional_standings), HLTV match/event
pages (results, lineups, live VRS forecast), tournament organizer pages.</li>
<li>Prices: Polymarket exchange moneylines, egamersworld bookmaker averages (bc.game et al.), stavka.tv and
kushvsporte bookmaker aggregates, bo3.gg (Thunderpick coefficients).</li>
<li>Context: strafe (brackets, form, user votes — sentiment only), tips.gg, tribuna.com, esports.gg,
Field Level Media/Reuters, dust2.us, Liquipedia.</li>
<li>Never used as prices: HotSpawn crowd %, HLTV fan-vote widgets, strafe user votes, egamersworld
prediction-bot votes, placeholder 1.8/1.8 pairs, $0-volume Polymarket seeds.</li>
</ol>
<h2>New listings the ledger has never seen (repair, 2026-10-16)</h2>
<p>The board is rebuilt from the fresh fixtures capture, not from the curated ledger alone. A fixture that
appears in the capture but not in the ledger gets a row automatically, priced in this order:</p>
<ol>
<li>an <strong>exact fixture-id quote</strong> retained in another published board on this site (the
canonical every-match board, the full-coverage board, the o<em>urline</em> board, the exec board or the
research-resolved board) — the sibling board's raw decimals and its public URL and read time are republished
verbatim and re-de-vigged here;</li>
<li>otherwise the <strong>canonical Valve-VRS model</strong>, when both teams are unambiguously present in
Valve's official standings;</li>
<li>otherwise a <strong>blank probability with a published reason</strong> and a note that the four-hourly
collector retries every external venue.</li>
</ol>
<p>Fixture-id equality is the join key, so no alias, sibling rating or tournament-slot guess is introduced.
Live drift between the ledger and the capture — ownership percentages, rescheduled kickoffs, name rendering
— is recorded on the row (<code>inventory.drift</code>) instead of aborting the rebuild, and a capture that
returns empty or truncated keeps the last researched inventory with a
<code>retained_inventory_capture_degraded</code> flag rather than publishing a silently smaller board.</p>
<h2>Refresh cadence and evidence</h2>
<p><code>.github/workflows/day4-1c8f79f8.yml</code> re-runs the collector and this builder every 4 hours
(cron <code>23 */4 * * *</code>, inside the required 4–8 h window) and after upstream board refreshes.
The collector re-captures each competition, re-applies the client-side time filter, and refuses to publish
if any row's lock-time arithmetic or crowd-percentage sum fails its self-check. The builder is deterministic
and network-free; tests re-derive every published number from the retained raw inputs.</p>
<h2>Session scope and protocol</h2>
<p>Claimed in COORDINATION.md before any file edit (2026-10-16 19:35Z). File scope:
<code>day4/**</code>, <code>scripts/1c8f79f8/**</code>, <code>data/1c8f79f8/**</code>,
<code>tests/test_1c8f79f8.py</code>, <code>.github/workflows/day4-1c8f79f8.yml</code>, this section of
COORDINATION.md. Integration into the landing page is additive only (one NAV/exec-summary row in
<code>scripts/build_site.py</code>, one directory entry in <code>scripts/stage_site.py</code>).</p>
"""


# ---------------------------------------------------------------- main
def main() -> int:
    global SNAPSHOT_STAMP, LINES_READ_STAMP
    OUT.mkdir(parents=True, exist_ok=True)
    rows, inventory = build_rows()
    board = build_board(rows, inventory)
    if inventory.get("capture_utc"):
        SNAPSHOT_STAMP = inventory["capture_utc"][:16].replace("T", "T") + "Z"
    LINES_READ_STAMP = f"ledger read {research.RETRIEVED_UTC}"
    (DATA / "board.json").write_text(json.dumps(board, indent=1), encoding="utf-8")
    generated = board["generated_utc"]
    (OUT / "index.html").write_text(page("Start here · TWC day-4 desk", "index.html", index_html(board), generated), encoding="utf-8")
    (OUT / "picks.html").write_text(page("All picks · every match", "picks.html", picks_html(board), generated), encoding="utf-8")
    (OUT / "twc-review.html").write_text(page("TWC day 1–3 verified review", "twc-review.html", twc_review_html(board), generated), encoding="utf-8")
    (OUT / "unresolved.html").write_text(page("Unresolved picks + limitations", "unresolved.html", unresolved_html(board), generated), encoding="utf-8")
    (OUT / "flagged.html").write_text(page("Flagged irregularities", "flagged.html", flagged_html(board), generated), encoding="utf-8")
    (OUT / "method.html").write_text(page("Method & sources", "method.html", method_html(board), generated), encoding="utf-8")
    print(f"board.json: {len(board['open'])} open rows; "
          f"{board['summary']['open_with_market']} market / {board['summary']['open_model_only']} model / "
          f"{board['summary']['open_blank']} blank; "
          f"{inventory.get('auto_rows', 0)} auto-added from the capture; mode={inventory.get('mode')}")
    print(f"pages written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
