#!/usr/bin/env python3
"""Resolver for the HotSpawn CS2 every-match picks board (session d9d7627b).
import importlib.util as _ilu, sys as _sys
from pathlib import Path as _Path
def _load_d9(name):
    key = f"d9d7627b_{name}"
    if key in _sys.modules:
        return _sys.modules[key]
    p = _Path(__file__).resolve().parent / f"{name}.py" if (_Path(__file__).resolve().parent / f"{name}.py").exists() else _Path(__file__).resolve().parents[1] / "scripts" / "d9d7627b" / f"{name}.py"
    spec = _ilu.spec_from_file_location(key, p)
    mod = _ilu.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


Reads `data/d9d7627b/snapshot.json`, applies the published resolution chain to every
fixture, and writes `data/d9d7627b/board.json` (+ appends calibration observations).

Resolution chain (first tier that resolves wins; every open fixture lands in exactly one):
  1. market    — >=1 external bookmaker/exchange price joined strictly (both team names
                 + start time). Pick probability = median no-vig consensus. HotSpawn is
                 never a price source.
  2. model     — originated line: both teams uniquely matched in the official Valve VRS
                 standings; probability from Valve's Glicko expected-win formula with a
                 slope fitted to observed market pairs (capped 3%-97%).
  3. direction — only one side carries a verified rating signal (or rating ranges do not
                 overlap). The rated side is the pick; the probability stays BLANK.
  4. unresolved— no price and no usable rating signal. Published with the per-source
                 limitations that prevented a pick. Nothing is invented.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
core = _load_d9('core')

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "d9d7627b"
LOBBY = "https://play.hotspawn.com/lobby"
BOOK_SOURCES = ["pinnacle", "bovada", "melbet", "kalshi", "polymarket"]


def classify(fx: dict, now: datetime) -> str:
    status = str(fx.get("status") or "")
    if fx.get("winner") in ("a", "b") or status in ("ended", "forfeited"):
        return "finished"
    if status == "cancelled":
        return "cancelled"
    if status == "started":
        return "locked"
    start = core.parse_iso(fx.get("start_utc"))
    lock = core.parse_iso(fx.get("lock_utc")) or start
    if lock and lock > now:
        return "open"
    if start and start >= now - timedelta(hours=24):
        return "locked"
    return "stale"


class VrsIndex:
    """Exact-name index over one Valve VRS standings snapshot."""

    def __init__(self, vrs: dict):
        self.meta = {k: vrs.get(k) for k in ("snapshot", "path", "page_url", "api_url")}
        self.teams = vrs.get("teams") or []
        self.by_key: dict[str, list[dict]] = {}
        self.by_tokens: dict[str, list[dict]] = {}
        for t in self.teams:
            self.by_key.setdefault(core.canon(t["team"])[0], []).append(t)
            self.by_tokens.setdefault(core.token_key(t["team"]), []).append(t)

    def lookup(self, name: str) -> dict:
        """-> {state: unique|ambiguous|missing, rows: [...], notes: [...]}"""
        key, note = core.canon(name)
        rows = self.by_key.get(key) or []
        notes = [note] if note else []
        if not rows:
            tk = core.token_key(name)
            trows = self.by_tokens.get(tk) or []
            if trows and len(tk.split()) > 1:
                rows = trows
                notes.append(f"VRS name word-order variant joined exactly: '{name}'")
        if len(rows) == 1:
            return {"state": "unique", "rows": rows, "notes": notes}
        if len(rows) > 1:
            return {"state": "ambiguous", "rows": rows, "notes": notes}
        return {"state": "missing", "rows": [], "notes": notes}


def _vrs_block(vrs: VrsIndex, name_a: str, name_b: str) -> tuple[dict, dict, dict]:
    la, lb = vrs.lookup(name_a), vrs.lookup(name_b)
    block = {
        "snapshot": vrs.meta.get("snapshot"), "page_url": vrs.meta.get("page_url"),
        "team_a": la["rows"][0] if la["state"] == "unique" else None,
        "team_b": lb["rows"][0] if lb["state"] == "unique" else None,
        "ambiguous": {},
        "notes": la["notes"] + lb["notes"],
    }
    if la["state"] == "ambiguous":
        block["ambiguous"]["team_a"] = la["rows"]
    if lb["state"] == "ambiguous":
        block["ambiguous"]["team_b"] = lb["rows"]
    return block, la, lb


def _direction_pick(la: dict, lb: dict, fx: dict) -> tuple[str | None, str | None]:
    """Direction-only logic from rating evidence alone. Returns (side, reason)."""
    pa = [r["points"] for r in la["rows"]]
    pb = [r["points"] for r in lb["rows"]]
    a, b = fx["team_a"], fx["team_b"]
    def fmt(rows):
        return "; ".join("#{0[standing]}, {0[points]} pts".format(r) for r in rows)
    if pa and not pb:
        return "a", (f"Only {a} has a verified official Valve VRS standing "
                     f"({fmt(la['rows'])}); "
                     f"{b} has no VRS entry under this name and no bookmaker price joined.")
    if pb and not pa:
        return "b", (f"Only {b} has a verified official Valve VRS standing "
                     f"({fmt(lb['rows'])}); "
                     f"{a} has no VRS entry under this name and no bookmaker price joined.")
    if pa and pb:
        if min(pa) > max(pb):
            return "a", (f"Every VRS roster listed for {a} outranks every roster listed "
                         f"for {b}; exact roster unconfirmed, so no probability is published.")
        if min(pb) > max(pa):
            return "b", (f"Every VRS roster listed for {b} outranks every roster listed "
                         f"for {a}; exact roster unconfirmed, so no probability is published.")
    return None, None


def _limitations(fx, joined_n, rejected, la, lb, vrs: VrsIndex, access, poly_stats,
                 hltv_meta) -> list[str]:
    """Human-readable, evidence-backed reasons a stronger pick could not be made."""
    out: list[str] = []
    checked = []
    for key in BOOK_SOURCES:
        meta = access.get(key) or {}
        when = (meta.get("at_utc") or "")[11:19]
        if meta.get("status") == 200:
            checked.append(f"{key} (HTTP 200{f', {when} UTC' if when else ''})")
        elif meta:
            checked.append(f"{key} (FAILED: {meta.get('error') or meta.get('status')})")
    if joined_n == 0:
        out.append("No external bookmaker/exchange price could be joined to this fixture "
                   "under the strict matching rules (both team names exact + start time "
                   "within 30 min). Sources collected this run: "
                   + ("; ".join(checked) if checked else "none recorded") + ". "
                   "Low-tier online qualifiers are routinely not priced by these books.")
    for rj in rejected:
        out.append(f"{rj['source_name']} lists a matching team pairing but was NOT joined: "
                   f"{rj.get('reason')}.")
    if poly_stats is not None and joined_n == 0:
        if poly_stats.get("events") is not None:
            out.append(f"Polymarket check: {poly_stats.get('events')} open Counter-Strike "
                       f"events / {poly_stats.get('two_outcome')} two-outcome markets scanned; "
                       f"{poly_stats.get('with_game_start')} carried a verified game start — "
                       "no joinable price for this fixture.")
        else:
            out.append("Polymarket Gamma API was reachable this run, but no joinable CS2 "
                       "match-winner market for this fixture was recorded.")
    snap = vrs.meta.get("snapshot") or "unknown"
    n_teams = len(vrs.teams)
    for side, lk, name in (("team_a", la, fx["team_a"]), ("team_b", lb, fx["team_b"])):
        if lk["state"] == "missing":
            out.append(f"{name} has no entry in the official Valve VRS global standings "
                       f"(snapshot {snap}, {n_teams} teams) under this name, so no rating "
                       "line can be originated for them.")
        elif lk["state"] == "ambiguous":
            cand = "; ".join("#{0[standing]} {0[points]} pts ({1})".format(
                r, r.get("roster") or "roster n/a") for r in lk["rows"])
            out.append(f"{name} matches {len(lk['rows'])} different VRS rosters ({cand}); "
                       "which roster plays this fixture is not verified, so no single "
                       "rating is used.")
    if hltv_meta and hltv_meta.get("status") not in (200, None):
        out.append(f"HLTV returned HTTP {hltv_meta.get('status')} to automated collection "
                   f"at {hltv_meta.get('at_utc')}; HLTV form/head-to-head could not be read "
                   "programmatically — use the manual HLTV link on this row.")
    return out


def resolve_fixture(fx, quotes, vrs: VrsIndex, fit, access, poly_stats, hltv_meta, now):
    joined, rejected = [], []
    for q in quotes:
        info = core.match_quote(fx, q)
        if info is None:
            continue
        if info.get("rejected"):
            rejected.append({**{k: q.get(k) for k in
                                ("source_key", "source_name", "public_url", "api_url",
                                 "event_id", "team_a", "team_b", "decimal_a", "decimal_b",
                                 "raw_format", "raw_a", "raw_b", "start_utc", "league",
                                 "retrieved_utc")},
                             "start_diff_h": info.get("start_diff_h"),
                             "reason": info.get("reason")})
            continue
        if q.get("live"):
            rejected.append({**{k: q.get(k) for k in
                                ("source_key", "source_name", "public_url", "api_url",
                                 "event_id", "team_a", "team_b", "decimal_a", "decimal_b",
                                 "raw_format", "raw_a", "raw_b", "start_utc", "league",
                                 "retrieved_utc")},
                             "start_diff_h": info.get("start_diff_h"),
                             "reason": "in-play (live) price — pre-match picks never use live odds"})
            continue
        rq = core.rederive_quote(q)
        if rq is None:
            continue
        pa = core.oriented_prob(rq, info["swapped"])
        joined.append({**rq, "prob_a": pa, "swapped": info["swapped"],
                       "alias_notes": info.get("alias_notes") or [],
                       "start_diff_h": info.get("start_diff_h"),
                       "loose_time": bool(info.get("loose_time"))})
    vrs_block, la, lb = _vrs_block(vrs, fx["team_a"], fx["team_b"])
    flags: list[str] = []
    for j in joined:
        flags += [f"alias_join:{j['source_key']}" for _ in j.get("alias_notes") or []]
        if j.get("loose_time"):
            flags.append(f"loose_start_time_join:{j['source_key']}:{j['start_diff_h']:.2f}h")
    res: dict = {"tier": None, "pick_side": None, "pick_team": None,
                 "prob_a": None, "prob_b": None, "pick_prob": None,
                 "confidence": None, "fair_decimal_a": None, "fair_decimal_b": None,
                 "fair_american_a": None, "fair_american_b": None,
                 "market": None, "model": None, "direction_reason": None,
                 "limitations": []}

    market = core.consensus(joined)
    if market:
        res.update({"tier": "market", "market": market,
                    "prob_a": market["prob_a"], "prob_b": market["prob_b"]})
        if market.get("spread_a") is not None and market["spread_a"] > 0.25:
            flags.append(f"books_disagree:spread={market['spread_a']:.2f}")
    elif la["state"] == "unique" and lb["state"] == "unique" and fit.get("fitted"):
        pa_pts, pb_pts = la["rows"][0]["points"], lb["rows"][0]["points"]
        pa = core.vrs_prob(pa_pts, pb_pts, fit["k"])
        res.update({"tier": "model", "prob_a": pa, "prob_b": 1.0 - pa,
                    "model": {"prob_a": pa, "k": fit["k"], "delta_points": pa_pts - pb_pts,
                              "points_a": pa_pts, "points_b": pb_pts,
                              "fit_n_pairs": fit["n_pairs"], "fit_mae": fit["mae_prob"]}})
        res["limitations"] = _limitations(fx, 0, rejected, la, lb, vrs, access,
                                          poly_stats, hltv_meta)
    else:
        side, reason = _direction_pick(la, lb, fx)
        if la["state"] == "unique" and lb["state"] == "unique" and side is None:
            # both rated, equal points, but calibration unfitted -> higher-points direction
            side = "a" if la["rows"][0]["points"] >= lb["rows"][0]["points"] else "b"
            reason = ("Both teams are VRS-rated but the calibration fit is unavailable "
                      f"({fit['n_pairs']} pairs < {core.CAL_MIN_PAIRS} minimum), so only "
                      "the higher-rated side is picked; probability left blank.")
        if side:
            res.update({"tier": "direction", "pick_side": side, "direction_reason": reason})
        else:
            res["tier"] = "unresolved"
        res["limitations"] = _limitations(fx, 0, rejected, la, lb, vrs, access,
                                          poly_stats, hltv_meta)

    if res["prob_a"] is not None:
        pa = res["prob_a"]
        side = "a" if pa >= 0.5 else "b"
        res["pick_side"] = side
        res["pick_prob"] = pa if side == "a" else 1.0 - pa
        res["confidence"] = core.confidence_label(res["pick_prob"])
        res["fair_decimal_a"] = core.fair_decimal(pa)
        res["fair_decimal_b"] = core.fair_decimal(1.0 - pa)
        res["fair_american_a"] = core.decimal_to_american(res["fair_decimal_a"])
        res["fair_american_b"] = core.decimal_to_american(res["fair_decimal_b"])
        if abs(pa - 0.5) < 1e-9:
            flags.append("exact_coin_flip")
    if res["pick_side"]:
        res["pick_team"] = fx["team_a"] if res["pick_side"] == "a" else fx["team_b"]
    start = core.parse_iso(fx.get("start_utc"))
    lock = core.parse_iso(fx.get("lock_utc"))
    if start and lock and start < now < lock:
        flags.append("past_start_but_not_locked_at_source")
    if la["state"] == "ambiguous":
        flags.append(f"ambiguous_vrs_name:{fx['team_a']}")
    if lb["state"] == "ambiguous":
        flags.append(f"ambiguous_vrs_name:{fx['team_b']}")
    if la["state"] == "missing":
        flags.append(f"not_in_vrs:{fx['team_a']}")
    if lb["state"] == "missing":
        flags.append(f"not_in_vrs:{fx['team_b']}")
    return res, {"quotes": joined, "rejected_joins": rejected, "vrs": vrs_block}, flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="ISO override for 'now' (tests/replay)")
    args = ap.parse_args()
    now = core.parse_iso(args.now) if args.now else core.now_utc()
    snap = json.loads((DATA / "snapshot.json").read_text())
    cal_path = DATA / "calibration.json"
    cal = json.loads(cal_path.read_text()) if cal_path.exists() else {"pairs": {}}
    pairs: dict = cal.get("pairs") or {}
    fit = core.fit_calibration(list(pairs.values()))

    vrs = VrsIndex(snap.get("vrs") or {})
    access = snap.get("access_log") or {}
    poly_stats = None
    pm = access.get("polymarket") or access.get("polymarket_probe") or {}
    if pm:
        poly_stats = {"events": pm.get("events"), "two_outcome": pm.get("two_outcome"),
                      "with_game_start": pm.get("with_game_start")}
    hltv_meta = access.get("hltv_probe") or {}
    quotes = snap.get("quotes") or []
    fixtures = (snap.get("hotspawn") or {}).get("fixtures") or []

    rows, counts = [], {"open": 0, "locked": 0, "finished": 0, "cancelled": 0, "stale": 0}
    by_tier = {"market": 0, "model": 0, "direction": 0, "unresolved": 0}
    joined_ids: set[int] = set()
    new_pairs = 0
    collected_to = snap.get("collected_to_utc")
    for fx in fixtures:
        state = classify(fx, now)
        counts[state] = counts.get(state, 0) + 1
        row = {**fx, "state": state, "resolution": None, "evidence": None, "flags": []}
        if state in ("open", "locked"):
            res, ev, flags = resolve_fixture(fx, quotes, vrs, fit, access, poly_stats,
                                             hltv_meta, now)
            row["resolution"], row["evidence"], row["flags"] = res, ev, flags
            by_tier[res["tier"]] += 1
            for j in ev["quotes"]:
                joined_ids.add(id(j))
            # calibration: latest pre-lock market observation with both sides VRS-unique
            va, vb = ev["vrs"].get("team_a"), ev["vrs"].get("team_b")
            if res.get("market") and va and vb:
                start = core.parse_iso(fx.get("start_utc"))
                observed = core.parse_iso(collected_to)
                if start and observed and observed < start:
                    prev = pairs.get(fx["fixture_id"])
                    if not prev or (prev.get("observed_utc") or "") < collected_to:
                        pairs[fx["fixture_id"]] = {
                            "fixture_id": fx["fixture_id"],
                            "teams": [fx["team_a"], fx["team_b"]],
                            "delta": va["points"] - vb["points"],
                            "points_a": va["points"], "points_b": vb["points"],
                            "market_prob_a": res["market"]["prob_a"],
                            "n_sources": res["market"]["n_sources"],
                            "observed_utc": collected_to,
                            "start_utc": fx.get("start_utc"),
                            "origin": "d9d7627b"}
                        new_pairs += 1
        rows.append(row)

    if new_pairs:
        cal["pairs"] = pairs
        cal["updated_utc"] = core.to_iso(now)
        cal_path.write_text(json.dumps(cal, indent=1, ensure_ascii=False) + "\n")
        fit = core.fit_calibration(list(pairs.values()))

    # quotes accounting (identity-based: joined quote dicts are copies -> recount by join)
    n_joined_quotes = sum(len(r["evidence"]["quotes"]) for r in rows if r.get("evidence"))
    board = {
        "session": "d9d7627b",
        "generated_utc": core.to_iso(now),
        "collected_from_utc": snap.get("collected_from_utc"),
        "collected_to_utc": collected_to,
        "seed": snap.get("seed"),
        "hotspawn_fallback_from": snap.get("hotspawn_fallback_from"),
        "week": (snap.get("hotspawn") or {}).get("week"),
        "vrs": {**vrs.meta, "n_teams": len(vrs.teams)},
        "calibration": fit,
        "counts": {**counts, "fixtures_total": len(rows), "by_tier": by_tier,
                   "quotes_collected": len(quotes), "quotes_joined": n_joined_quotes,
                   "rejected_source_quotes": len(snap.get("rejected_quotes") or [])},
        "access": access,
        "rejected_source_quotes": snap.get("rejected_quotes") or [],
        "rows": rows,
    }
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    print("states:", counts, "| tiers (open+locked):", by_tier,
          "| quotes joined:", n_joined_quotes, "/", len(quotes),
          "| calibration pairs:", fit["n_pairs"], "k:", fit["k"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
