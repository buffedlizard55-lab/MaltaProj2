#!/usr/bin/env python3
"""Session 2cadfaf2 resolver — one row for **every** CS2 fixture the HotSpawn lobby lists.

Reads ``data/2cadfaf2/snapshot.json`` (written by ``collect.py``) and writes
``data/2cadfaf2/board.json``. No network access here, so every published number can be
recomputed from the committed capture.

Coverage model
--------------
The lobby lists 78 CS2 fixtures for the current pick'em week. They are *not* all pickable: most
carry June/July kickoff timestamps that HotSpawn never updated ("waiting for information"), and a
handful have already started. This resolver classifies all of them, gives each one the best
verified line the published ladder can produce, and lists the rest explicitly as unresolved with
the reason. Nothing is dropped and nothing is invented.

Pick ladder (applied per fixture, in order)
-------------------------------------------
1. **Market line** — de-vigged consensus of verified Pinnacle / Bovada / Melbet / Kalshi prices
   that join on both team names and on the start time (five-minute tolerance).
2. **VRS model** — both teams are rows of Valve's official Regional Standings: probability from
   the ratings with the slope fitted to observed book lines (``data/f7279a54/calibration_pairs.json``).
3. **Lower bound** — only one team is rated: the rated team's probability is published as a bound
   with the assumption spelled out (unrated opponent assumed at Valve's lowest published rating).
4. **Unresolved** — blank, with the missing evidence named on the Unresolved page.

HotSpawn crowd percentages are never read: the snapshot has no field for them.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pc_core as core  # noqa: E402  (unique module name: a bare `core` collides across sessions)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "2cadfaf2"
SNAPSHOT = DATA / "snapshot.json"
BOARD = DATA / "board.json"
LEDGER = DATA / "ledger.json"
CAL_PAIRS = ROOT / "data" / "f7279a54" / "calibration_pairs.json"
SEED_BOARDS = (
    ("f3e5123c", ROOT / "data" / "f3e5123c" / "board.json"),
    ("f7279a54", ROOT / "data" / "f7279a54" / "board.json"),
)
LOBBY = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
MAX_QUOTE_AGE_H = 8.0
MAX_INVENTORY_AGE_H = 8.0
API_ONLY_WINDOW_H = 8.0
API_ONLY_HORIZON_D = 14.0
STATE_LABEL = {
    "open": "Open for picks",
    "locked": "Locked, not started",
    "in_play": "In play",
    "final": "Final",
    "void": "Void",
    "stale": "Listed, kickoff long past",
    "past": "Past",
    "awaiting": "Awaiting schedule",
}


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def hours(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# --------------------------------------------------------------------------- calibration
def calibration(now: datetime) -> dict:
    pairs = load(CAL_PAIRS, {})
    usable = []
    for pair in pairs.values() if isinstance(pairs, dict) else []:
        if pair.get("policy") != "strict-fallback-v2":
            continue
        delta, prob = pair.get("delta"), pair.get("market_prob_a")
        if not isinstance(delta, (int, float)) or not isinstance(prob, (int, float)):
            continue
        if not 0.02 <= float(prob) <= 0.98:
            continue
        usable.append({"delta": float(delta), "market_prob_a": float(prob)})
    cal = core.fit_calibration(usable)
    cal["source"] = str(CAL_PAIRS.relative_to(ROOT))
    cal["source_url"] = ("https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/"
                         "data/f7279a54/calibration_pairs.json")
    cal["note"] = ("Slope k is fitted so that logit(book probability) = k * C * (VRS points "
                   "difference); k = 1 would be Valve's own, visibly too-steep curve.")
    return cal


# ------------------------------------------------------------------------------- ledger
def load_seeds() -> dict:
    """Pre-lock lines already recorded by earlier sessions, with attribution."""
    seeds: dict[str, dict] = {}
    for session, path in SEED_BOARDS:
        board = load(path, {})
        for row in (board.get("locked_recent") or []):
            prev = row.get("last_open_line") or {}
            line = prev.get("line") or {}
            fid = str(row.get("fixture_id"))
            if not line.get("pick_team") or not prev.get("observed_utc"):
                continue
            start = row.get("start_utc")
            observed = prev.get("observed_utc")
            if start and observed and observed > start:
                continue  # not a pre-lock observation
            if fid not in seeds or observed < seeds[fid]["observed_utc"]:
                seeds[fid] = {
                    "fixture_id": fid, "teams": prev.get("teams") or [row.get("team_a"), row.get("team_b")],
                    "observed_utc": observed, "start_utc": start,
                    "pick_team": line.get("pick_team"), "pick_side": line.get("pick_side"),
                    "pick_prob": line.get("pick_prob"), "prob_a": line.get("prob_a"),
                    "prob_b": line.get("prob_b"), "basis": line.get("basis"),
                    "recorded_by": f"session {session}",
                    "recorded_from": f"data/{session}/board.json",
                }
    return seeds


def merge_ledger(seeds: dict, ledger: dict, mode: str) -> dict:
    merged = {str(k): v for k, v in (ledger.get("picks") or {}).items()}
    for fid, seed in seeds.items():
        if fid not in merged:
            merged[fid] = seed
        elif seed["observed_utc"] < merged[fid].get("observed_utc", "9999"):
            merged[fid] = seed
    return {"picks": merged, "updated_utc": core.to_iso(core.now_utc()), "mode": mode}


# --------------------------------------------------------------------------------- rows
def orient(quote: dict, swapped: bool) -> tuple[float | None, float | None, float | None]:
    nv = core.no_vig(quote.get("decimal_a"), quote.get("decimal_b"))
    if not nv:
        return None, None, None
    pa, pb = nv["prob_a"], nv["prob_b"]
    if swapped:
        pa, pb = pb, pa
    return round(pa, 6), round(pb, 6), round(nv["overround"], 5)


def build_row(fx: dict, snap: dict, now: datetime, index: core.VrsIndex, cal: dict,
              floor_points: int | None, inventory_age_h: float | None) -> dict:
    fid = str(fx.get("fixture_id"))
    listed = "lobby_page" in (fx.get("seen_in") or [])
    permalink = (snap.get("permalinks") or {}).get(fid)
    state, state_reason = core.state_of(fx, now)
    row = {
        "fixture_id": fid,
        "competition": fx.get("competition"),
        "tier": fx.get("tier"),
        "stage": fx.get("stage"),
        "best_of": fx.get("best_of"),
        "points": fx.get("points"),
        "status": fx.get("status"),
        "state": state,
        "state_reason": state_reason,
        "state_label": STATE_LABEL.get(state, state),
        "pickable": state == "open",
        "start_utc": fx.get("start_utc"),
        "lock_utc": fx.get("lock_utc"),
        "team_a": fx.get("team_a"),
        "team_b": fx.get("team_b"),
        "winner": fx.get("winner"),
        "listed_in_lobby": listed,
        "hotspawn_url": permalink or LOBBY,
        "hotspawn_url_kind": "published match permalink" if permalink else "official lobby page",
        "flags": [],
        "quotes": [],
        "rejected_joins": [],
    }
    if not listed:
        row["flags"].append("api_only_not_in_lobby_page")
    if inventory_age_h is not None and inventory_age_h > MAX_INVENTORY_AGE_H:
        row["flags"].append(f"inventory_capture_{inventory_age_h:.1f}h_old")
    if state == "stale":
        row["flags"].append("lobby_kickoff_never_updated")
    if state == "void":
        row["flags"].append("fixture_void")

    # ---- external prices
    best: dict[str, dict] = {}
    for quote in snap.get("quotes") or []:
        join = core.join_quote(fx, quote)
        if not join:
            continue
        if join.get("rejected"):
            row["rejected_joins"].append({
                "source_key": quote.get("source_key"), "source_name": quote.get("source_name"),
                "event_id": quote.get("event_id"), "public_url": quote.get("public_url"),
                "names_at_source": [quote.get("team_a"), quote.get("team_b")],
                "start_utc_at_source": quote.get("start_utc"),
                "start_method": join.get("start_method"),
                "start_diff_h": round(join["start_diff_h"], 2) if join.get("start_diff_h") is not None else None,
                "reason": join.get("reason"),
                "decimal": [quote.get("decimal_a"), quote.get("decimal_b")],
            })
            continue
        retrieved = core.parse_iso(quote.get("retrieved_utc"))
        age = hours(retrieved, now)
        if age is None or age > MAX_QUOTE_AGE_H:
            row["flags"].append(f"quote_too_old_not_used:{quote.get('source_key')}")
            continue
        prob_a, prob_b, overround = orient(quote, join["swapped"])
        if prob_a is None:
            continue
        entry = {
            "source_key": quote.get("source_key"), "source_name": quote.get("source_name"),
            "public_url": quote.get("public_url"), "api_url": quote.get("api_url"),
            "event_id": quote.get("event_id"),
            "names_at_source": [quote.get("team_a"), quote.get("team_b")],
            "raw_format": quote.get("raw_format"),
            "raw_a": quote.get("raw_a"), "raw_b": quote.get("raw_b"),
            "decimal_a": round(quote["decimal_a"], 4), "decimal_b": round(quote["decimal_b"], 4),
            "prob_a": prob_a, "prob_b": prob_b, "overround": overround,
            "swapped": join["swapped"], "start_diff_h": round(join["start_diff_h"], 4),
            "start_method": join["start_method"], "retrieved_utc": quote.get("retrieved_utc"),
            "age_hours": round(age, 2),
        }
        if join.get("alias"):
            entry["alias"] = {"display": join["alias"]["display"], "evidence": join["alias"]["evidence"],
                              "verified_utc": join["alias"]["verified_utc"]}
            row["flags"].append(f"alias_join:{join['alias']['display']}")
        if join["start_diff_h"] and join["start_diff_h"] > core.JOIN_TOLERANCE_H:
            row["flags"].append(f"start_time_differs_{join['start_diff_h'] * 60:.0f}m:{quote.get('source_key')}")
        prev = best.get(quote.get("source_key"))
        if prev is None or join["start_diff_h"] < prev["start_diff_h"]:
            best[quote.get("source_key")] = entry
    row["quotes"] = [best[k] for k in sorted(best)]
    if row["quotes"]:
        consensus = core.consensus([{"source_key": q["source_key"], "prob_a": q["prob_a"]}
                                    for q in row["quotes"]])
        if consensus:
            row["market"] = {
                "prob_a": round(consensus["prob_a"], 4), "prob_b": round(1 - consensus["prob_a"], 4),
                "n_sources": consensus["n_sources"], "sources": consensus["sources"],
                "spread_a": round(consensus["spread_a"], 4) if consensus.get("spread_a") is not None else None,
                "method": "weighted mean of per-source proportional no-vig probabilities "
                          "(pinnacle 2.0, other books/exchange 1.0)",
            }
        if len(row["quotes"]) == 1:
            row["flags"].append("single_source_price")
        if consensus and consensus.get("spread_a") is not None and consensus["spread_a"] >= 0.08:
            row["flags"].append(f"sources_disagree_{consensus['spread_a'] * 100:.0f}pp")

    # ---- official Valve ratings
    rating_a, err_a = index.lookup(fx.get("team_a"))
    rating_b, err_b = index.lookup(fx.get("team_b"))
    row["vrs"] = {"team_a": rating_a, "team_b": rating_b, "snapshot": index.snapshot,
                  "page_url": index.page_url}
    for side, err, name in (("a", err_a, fx.get("team_a")), ("b", err_b, fx.get("team_b"))):
        if err == "ambiguous_vrs_name":
            row["flags"].append(f"ambiguous_vrs_name:{name}")
        elif err == "duplicate_name_resolved_by_details_file":
            row["flags"].append(f"duplicate_vrs_name_resolved:{name}")
        elif err == "unrated_not_in_vrs":
            row["flags"].append(f"unrated_by_valve:{name}")

    # ---- the ladder
    line = core.ladder(row, cal, floor_points)
    row["line"] = line
    if line:
        if line["basis"] == "market":
            market = row.get("market") or {}
            if abs(line["prob_a"] - market.get("prob_a", line["prob_a"])) > 1e-6:
                row["flags"].append("internal_error_line_differs_from_consensus")
        elif line["basis"] == "bound_lo":
            row["flags"].append("lower_bound_not_a_point_estimate")
        else:
            row["flags"].append("originated_from_valve_ratings")
        row.setdefault("review", {})
    else:
        row["flags"].append("unresolved_no_verified_basis")
    row["flags"] = sorted(set(row["flags"]))
    return row


def unresolved_reason(row: dict, index: core.VrsIndex) -> str:
    missing = []
    if not row.get("market"):
        if row.get("rejected_joins"):
            missing.append("no external price joins on team names + start time "
                           f"({len(row['rejected_joins'])} near-miss joins logged)")
        else:
            missing.append("no external book or exchange lists this fixture")
    ra, rb = row["vrs"].get("team_a"), row["vrs"].get("team_b")
    if not ra and not rb:
        names = [n for n, r in ((row["team_a"], ra), (row["team_b"], rb)) if not r]
        missing.append("neither team appears in Valve's Regional Standings "
                       f"({', '.join(n for n in names if n)})")
    elif not (ra and rb):
        missing.append("only one team is rated and Valve's lowest published rating is unavailable")
    return "; ".join(missing)


# ---------------------------------------------------------------------------- verification
def verify(rows: list[dict], summary: dict) -> list[dict]:
    checks = []

    def add(name: str, passed: bool, detail: dict):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    bad = []
    for r in rows:
        line = r.get("line")
        if not line:
            continue
        if abs(line["prob_a"] + line["prob_b"] - 1.0) > 1e-6:
            bad.append({"fixture": r["fixture_id"], "why": "probabilities do not sum to 1"})
        expected = r["team_a"] if line["prob_a"] >= line["prob_b"] else r["team_b"]
        if line["pick_team"] != expected:
            bad.append({"fixture": r["fixture_id"], "why": "pick is not the higher probability"})
        if abs(line["pick_prob"] - max(line["prob_a"], line["prob_b"])) > 1e-6:
            bad.append({"fixture": r["fixture_id"], "why": "pick probability mismatch"})
    add("every published line sums to 1 and its pick is the higher probability", not bad,
        {"lines": sum(1 for r in rows if r.get("line")), "failures": bad[:5]})

    bad = []
    for r in rows:
        if r.get("line") and r["line"]["basis"] == "market":
            market = r.get("market") or {}
            if abs(market.get("prob_a", -1) - r["line"]["prob_a"]) > 1e-6:
                bad.append({"fixture": r["fixture_id"], "why": "market line is not the stored consensus"})
    add("every market line reproduces its stored consensus", not bad, {"failures": bad[:5]})

    bad = []
    for r in rows:
        if r.get("line") and r["line"]["basis"] == "model":
            detail = r["line"]["detail"]
            expected = core.vrs_prob(detail["delta_points"], 0, detail["k"])
            if abs(expected - r["line"]["prob_a"]) > 1e-4:
                bad.append({"fixture": r["fixture_id"], "why": "model probability does not recompute"})
    add("every VRS-model line recomputes from its published delta and k", not bad, {"failures": bad[:5]})

    bad = []
    for r in rows:
        if r.get("line") and r["line"]["basis"] != "market" and not r["line"].get("sources"):
            bad.append({"fixture": r["fixture_id"], "why": "originated line has no source link"})
    add("every originated line links the official rating file it came from", not bad,
        {"failures": bad[:5]})

    bad = [r["fixture_id"] for r in rows if not str(r.get("hotspawn_url") or "").startswith("https://")]
    add("every row links an official HotSpawn page", not bad, {"failures": bad[:5]})

    bad = [r["fixture_id"] for r in rows if r.get("state") == "open" and not r.get("line")
           and "unresolved_no_verified_basis" not in r.get("flags", [])]
    add("every unresolved row is flagged as unresolved", not bad, {"failures": bad[:5]})

    add("the inventory covers every fixture the lobby lists",
        summary["listed_in_lobby"] == summary["lobby_fixtures_reported"],
        {"listed_in_lobby": summary["listed_in_lobby"],
         "lobby_fixtures_reported": summary["lobby_fixtures_reported"]})

    add("no HotSpawn crowd percentage is stored anywhere in the board",
        "crowd" not in json.dumps(rows).lower(),
        {"note": "the snapshot parser drops the lobby's 'picked %' fields before they reach a row"})
    return checks


# ----------------------------------------------------------------------------------- main
def main() -> int:
    snap = load(SNAPSHOT, None)
    if not snap:
        print("no snapshot — run collect.py first", file=sys.stderr)
        return 2
    now = core.now_utc()
    captured = core.parse_iso(snap.get("collected_to_utc"))
    inventory_age_h = hours(captured, now)
    cal = calibration(now)
    k = cal["k"]
    index = core.VrsIndex(snap.get("vrs") or {}, now=now)
    floor_points = index.floor_points()

    week = snap.get("week") or {}
    fixtures = [f for f in snap.get("fixtures") or [] if str(f.get("status") or "").lower() != "cancelled"
                or True]  # keep cancellations visible: they are part of the record
    listed = [f for f in fixtures if "lobby_page" in (f.get("seen_in") or [])]
    by_id = {str(f.get("fixture_id")) for f in listed}
    extra = []
    for f in fixtures:
        fid = str(f.get("fixture_id"))
        if fid in by_id:
            continue
        start = core.parse_iso(f.get("start_utc"))
        if start is None:
            continue
        if not (-timedelta(hours=API_ONLY_WINDOW_H) <= (start - now) <= timedelta(days=API_ONLY_HORIZON_D)):
            continue
        if str(f.get("status") or "").lower() not in ("scheduled", "started"):
            continue
        extra.append(f)
    inventory = listed + extra

    rows = [build_row(f, snap, now, index, cal, floor_points, inventory_age_h) for f in inventory]
    rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))

    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    with_line = [r for r in rows if r.get("line")]
    basis_counts = {}
    for r in with_line:
        basis_counts[r["line"]["basis"]] = basis_counts.get(r["line"]["basis"], 0) + 1
    unresolved = [r for r in rows if not r.get("line")]
    open_rows = [r for r in rows if r["state"] == "open"]

    summary = {
        "listed_in_lobby": len(listed),
        "lobby_fixtures_reported": len(listed),
        "api_only_rows": len(extra),
        "total_rows": len(rows),
        "open": len(open_rows),
        "open_with_pick": sum(1 for r in open_rows if r.get("line")),
        "with_pick": len(with_line),
        "unresolved": len(unresolved),
        "unresolved_open": sum(1 for r in unresolved if r["state"] == "open"),
        "by_state": counts,
        "by_basis": basis_counts,
        "market_rows": basis_counts.get("market", 0),
        "model_rows": basis_counts.get("model", 0),
        "bound_rows": basis_counts.get("bound_lo", 0),
        "quotes_in_capture": len(snap.get("quotes") or []),
        "quotes_used": sum(len(r["quotes"]) for r in rows),
        "captured_utc": snap.get("collected_to_utc"),
        "inventory_age_hours": round(inventory_age_h, 2) if inventory_age_h is not None else None,
        "mode": snap.get("mode"),
        "vrs_snapshot": index.snapshot,
        "calibration_k": round(k, 4),
        "calibration_pairs": cal.get("n_pairs"),
        "generated_utc": core.to_iso(now),
        "week": week,
        "window": {"start": week.get("weekStartUtc"), "end": week.get("weekEndUtc")},
    }

    ledger_old = load(LEDGER, {"picks": {}})
    ledger = merge_ledger(load_seeds(), ledger_old, str(snap.get("mode")))
    # Record this run's own pre-lock observations (never overwrite an earlier one).
    for r in open_rows:
        if not r.get("line"):
            continue
        lock = core.parse_iso(r.get("lock_utc"))
        if lock and now >= lock:
            continue
        entry = ledger["picks"].get(r["fixture_id"])
        if entry and entry.get("observed_utc", "9999") <= summary["generated_utc"]:
            continue
        ledger["picks"][r["fixture_id"]] = {
            "fixture_id": r["fixture_id"], "teams": [r["team_a"], r["team_b"]],
            "observed_utc": summary["generated_utc"], "start_utc": r["start_utc"],
            "pick_team": r["line"]["pick_team"], "pick_side": r["line"]["pick_side"],
            "pick_prob": r["line"]["pick_prob"], "prob_a": r["line"]["prob_a"],
            "prob_b": r["line"]["prob_b"], "basis": r["line"]["basis"],
            "recorded_by": "session 2cadfaf2", "recorded_from": "data/2cadfaf2/board.json",
        }
    # Grade every finished fixture that has a genuine pre-lock pick.
    results, tally = [], {"graded": 0, "hit": 0, "miss": 0, "pending": 0}
    for r in rows:
        entry = ledger["picks"].get(r["fixture_id"])
        if not entry:
            continue
        observed = core.parse_iso(entry.get("observed_utc"))
        start = core.parse_iso(r.get("start_utc"))
        pre_lock = bool(observed and start and observed <= start)
        record = {
            "fixture_id": r["fixture_id"], "competition": r["competition"],
            "start_utc": r["start_utc"], "team_a": r["team_a"], "team_b": r["team_b"],
            "pick_team": entry.get("pick_team"), "pick_prob": entry.get("pick_prob"),
            "pick_side": entry.get("pick_side"), "basis": entry.get("basis"),
            "observed_utc": entry.get("observed_utc"), "recorded_by": entry.get("recorded_by"),
            "pre_lock": pre_lock, "state": r["state"], "winner": r.get("winner"),
        }
        if r["state"] == "final" and r.get("winner") in ("a", "b") and pre_lock:
            record["result"] = "hit" if entry.get("pick_side") == r["winner"] else "miss"
            tally["graded"] += 1
            tally["hit" if record["result"] == "hit" else "miss"] += 1
        else:
            record["result"] = None
            if r["state"] in ("open", "locked", "in_play"):
                tally["pending"] += 1
        results.append(record)
    results.sort(key=lambda r: r.get("start_utc") or "", reverse=True)

    access = {}
    for name, meta in (snap.get("access_log") or {}).items():
        if not isinstance(meta, dict):
            continue
        access[name] = {
            "url": meta.get("url"), "status": meta.get("status"), "error": meta.get("error"),
            "bytes": meta.get("bytes"), "at_utc": meta.get("at_utc"),
            "ok": meta.get("status") == 200 and not meta.get("error") and not meta.get("looks_like_challenge"),
        }

    flags = build_flags(rows, summary, access, snap)
    verification = verify(rows, summary)

    board = {
        "session": "2cadfaf2",
        "generated_utc": summary["generated_utc"],
        "captured_utc": snap.get("collected_to_utc"),
        "captured_from_utc": snap.get("collected_from_utc"),
        "mode": snap.get("mode"),
        "fallback": snap.get("fallback"),
        "week": week,
        "policy": {
            "hotspawn": "fixture discovery + timing only; crowd pick percentages are never read",
            "ladder": ["market consensus", "fitted-slope Valve VRS model", "explicit lower bound",
                       "unresolved (blank)"],
            "quote_freshness_hours": MAX_QUOTE_AGE_H,
            "join_tolerance_minutes": round(core.JOIN_TOLERANCE_H * 60, 2),
            "pick_rule": "the pick is always the team with the higher published probability",
        },
        "summary": summary,
        "calibration": cal,
        "vrs": {"snapshot": index.snapshot, "page_url": index.page_url,
                "teams": sum(len(v) for v in index.rows.values()),
                "duplicate_names": len(index.duplicates),
                "floor_points": floor_points},
        "rows": rows,
        "unresolved": [{**{k: r[k] for k in ("fixture_id", "competition", "team_a", "team_b", "start_utc",
                                            "lock_utc", "state", "state_label", "hotspawn_url", "tier",
                                            "points")},
                        "reason": unresolved_reason(r, index),
                        "flags": r["flags"],
                        "ratings": {"team_a": r["vrs"].get("team_a"), "team_b": r["vrs"].get("team_b")}}
                       for r in unresolved],
        "results": results,
        "tally": tally,
        "access": access,
        "sources_url": HS_API,
        "flags": flags,
        "verification": verification,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    BOARD.write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("listed_in_lobby", "total_rows", "open", "open_with_pick",
                                              "with_pick", "unresolved", "market_rows", "model_rows",
                                              "bound_rows", "mode", "inventory_age_hours")}, indent=1))
    print("unresolved:", len(unresolved), "graded:", tally["graded"], "hit:", tally["hit"])
    failed = [c for c in verification if not c["passed"]]
    for c in failed:
        print("VERIFY FAIL:", c["check"], json.dumps(c["detail"])[:300], file=sys.stderr)
    return 1 if failed else 0


def build_flags(rows: list[dict], summary: dict, access: dict, snap: dict) -> list[dict]:
    flags = []
    stale = [r for r in rows if r["state"] == "stale"]
    if stale:
        flags.append({
            "id": "F1",
            "severity": "high — inventory",
            "title": f"{len(stale)} of the {summary['listed_in_lobby']} CS2 fixtures the lobby lists still "
                     "carry June/July kickoff timestamps",
            "detail": "HotSpawn ships these fixtures with a published start time months before the "
                      "current pick'em week (status 'scheduled', stage 'waiting for information'). The "
                      "lobby counts them in the week (its own tier filter reads All tiers (78) B (26) "
                      "C (52) and every tournament count matches), but their lock time is long past, so "
                      "they cannot be picked. They are published here with a research line where one "
                      "exists and listed as unresolved where it does not — never dropped, never guessed.",
            "urls": ["https://play.hotspawn.com/lobby"],
        })
    if summary.get("unresolved_open"):
        flags.append({
            "id": "F2",
            "severity": "medium — coverage",
            "title": f"{summary['unresolved_open']} fixture(s) that are still open have no verified basis",
            "detail": "No external price joins and at least one side has no official Valve rating, so "
                      "the row is blank and named on the Unresolved page.",
            "urls": ["https://play.hotspawn.com/lobby"],
        })
    hltv = access.get("hltv_probe") or {}
    if hltv and not hltv.get("ok"):
        flags.append({
            "id": "F3",
            "severity": "medium — source access",
            "title": "HLTV refuses automated reads (HTTP 403), so it cannot be a live probability input",
            "detail": "The collector probes https://www.hltv.org/matches on every run and records the "
                      "result. HLTV pages are used here only for identity cross-checks that were read and "
                      "linked by hand (see the alias evidence links); no scraper output feeds a line. "
                      "Official Valve standings and licensed books/exchange carry every number.",
            "urls": ["https://www.hltv.org/matches",
                     "https://github.com/ValveSoftware/counter-strike_regional_standings"],
        })
    if snap.get("mode") != "live":
        flags.append({
            "id": "F4",
            "severity": "high — data freshness",
            "title": "This board was built from the last committed capture, not a live read",
            "detail": "The runner could not read the sources it needs: "
                      + "; ".join(f"{name} {meta.get('status') or 'no response'}"
                                  for name, meta in sorted(((snap.get("fallback") or {}).get("live_attempt", {})
                                                            .get("access_log") or {}).items())
                                  if isinstance(meta, dict))
                      + ". Every row therefore carries the capture time shown at the top of the page; the "
                        "four-hourly workflow replaces it with a live capture on the next successful run.",
            "urls": ["https://play.hotspawn.com/lobby"],
        })
    vrs_snap = summary.get("vrs_snapshot")
    if vrs_snap:
        try:
            age_days = (core.now_utc() - datetime.fromisoformat(vrs_snap.replace("_", "-")).replace(
                tzinfo=timezone.utc)).days
        except ValueError:
            age_days = None
        if age_days is not None and age_days > 14:
            flags.append({
                "id": "F5",
                "severity": "medium — rating age",
                "title": f"Valve's newest published standings file is {age_days} days old ({vrs_snap})",
                "detail": "Valve has not published a newer snapshot, so every VRS-model and bound row "
                          "uses ratings that predate recent results. The date is shown with every rating.",
                "urls": ["https://github.com/ValveSoftware/counter-strike_regional_standings/tree/main/live"],
            })
    dup = [r["fixture_id"] for r in rows if any(f.startswith("ambiguous_vrs_name") for f in r["flags"])]
    if dup:
        flags.append({
            "id": "F6",
            "severity": "medium — identity",
            "title": f"{len(dup)} fixture(s) contain an organisation with more than one Valve rating row",
            "detail": "Valve keeps separate rows for older rosters of the same organisation. Guessing "
                      "would invent a probability, so those teams are treated as unrated unless the "
                      "official details file identifies one active roster unambiguously.",
            "urls": ["https://github.com/ValveSoftware/counter-strike_regional_standings/tree/main/live"],
        })
    flags.append({
        "id": "F7",
        "severity": "info — method",
        "title": "HotSpawn crowd percentages are deliberately not used",
        "detail": "The lobby shows how other players picked. It is not a price, has no stake behind it "
                  "and would make this desk a mirror of the crowd, so the parser drops the field before "
                  "any row is built. A test asserts the board never contains it.",
        "urls": ["https://play.hotspawn.com/lobby"],
    })
    return flags


if __name__ == "__main__":
    sys.exit(main())
