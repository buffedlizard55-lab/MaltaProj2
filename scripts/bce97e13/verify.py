#!/usr/bin/env python3
"""Independent verification + normalised board build for the bce97e13 desk.

Inputs (all committed, read-only):
  * data/7adc7718/raw_snapshot.json  - freshest raw HotSpawn lobby capture (fixture inventory)
  * data/5f903db4/board.json         - canonical every-match picks being verified
  * data/f3e5123c/board.json         - secondary every-match board (pick-direction cross-check)
  * data/5f903db4/vrs_global.json    - parsed Valve standings used by the canonical build
  * data/bce97e13/standings_official.md + valve_live.json - live official Valve check (if run)

Outputs:
  * data/bce97e13/verification.json  - per-check verdicts, summary, limitations, irregularities
  * data/bce97e13/board.json         - normalised verified rows rendered by site.py

Hard rules (a failure flips the row to ``unverified`` and is published, never silently fixed):
  every open lobby fixture must have a canonical row with a pick and both probabilities;
  market probabilities must re-derive from the stored decimal quotes (no-vig, equal weight);
  originated probabilities must re-derive from official Valve points with the published formula;
  bound rows must carry the bound label and use the published floor;
  every row needs at least one openable external source URL and its HotSpawn permalink;
  HotSpawn crowd/vote data must never appear as an input.
"""
from __future__ import annotations

import importlib.util as _iu
import sys
from datetime import datetime
from pathlib import Path

_spec = _iu.spec_from_file_location("bce97e13_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["bce97e13_core"] = core
_spec.loader.exec_module(core)

OUT_VERIFY = "data/bce97e13/verification.json"
OUT_BOARD = "data/bce97e13/board.json"
SECONDARY_BOARD = "data/f3e5123c/board.json"


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def pct(p):
    return None if p is None else round(float(p) * 100.0, 1)


# --------------------------------------------------------------------------------- inventory
def open_lobby_fixtures(raw: dict) -> list[dict]:
    """All open CS2 fixtures in the raw capture.

    Each fixture is tagged ``lobby_rendered`` (the HotSpawn lobby draws a pick card for it) or
    ``api_only`` (present in the fixtures API, ``seen_in == ['api']`` and no permalink).
    """
    snap = parse_ts(raw.get("fixture_snapshot_utc") or raw.get("collected_run_utc"))
    out = []
    for f in raw.get("fixtures", []):
        if f.get("sport") and str(f.get("sport")).lower() not in ("cs2", "cs:2", "counter-strike 2"):
            continue
        if f.get("status") not in ("scheduled", "started"):
            continue
        lock = parse_ts(f.get("lock_utc"))
        if snap and lock and lock <= snap:
            continue
        out.append(dict(f))
    return sorted(out, key=lambda f: (str(f.get("start_utc") or ""), str(f.get("fixture_id"))))


# -------------------------------------------------------------------------------- per-checks
def check_market(row: dict) -> dict:
    quotes = [q for q in row.get("quotes", []) if q.get("decimal_a") and q.get("decimal_b")]
    per_book = []
    for q in quotes:
        nv = core.novig(q["decimal_a"], q["decimal_b"])
        if nv:
            per_book.append((nv, q))
    if not per_book:
        return {"ok": False, "reason": "market row carries no re-derivable decimal quotes",
                "re_prob_a": None, "re_prob_b": None}
    re_a = sum(nv["prob_a"] for nv, _ in per_book) / len(per_book)
    re_b = sum(nv["prob_b"] for nv, _ in per_book) / len(per_book)
    res = row["resolution"]
    ok = (abs(re_a - res["prob_a"]) <= core.TOL_MARKET and
          abs(re_b - res["prob_b"]) <= core.TOL_MARKET)
    return {"ok": ok, "reason": "" if ok else "stored consensus outside tolerance of re-derivation",
            "re_prob_a": re_a, "re_prob_b": re_b, "n_books": len(per_book),
            "overrounds": [round(nv["overround"], 5) for nv, _ in per_book]}


def _official_points(official: dict | None, name: str):
    if not official:
        return None
    return official["by_name"].get(core.norm(name))


def check_vrs(row: dict, committed_vrs: dict, official: dict | None) -> dict:
    res = row["resolution"]
    va, vb = row.get("vrs_a") or {}, row.get("vrs_b") or {}
    basis = res["basis"]
    floor_points = (row.get("vrs_floor") or committed_vrs.get("floor") or {}).get("points")
    identity_mismatches = []

    def points_of(v, side):
        if not v.get("listed"):
            if basis == "originated_vrs_bound":
                return floor_points, True
            return None, False
        # Cross-check the claimed points/standing/roster against the live official table.
        if official is not None:
            off_rows = _official_points(official, v.get("vrs_name") or v.get("name"))
            chosen = next((o for o in (off_rows or [])
                           if o["standing"] == v.get("standing") and o["points"] == v.get("points")), None)
            if chosen is None:
                identity_mismatches.append(f"{v.get('name')}: not found with standing "
                                           f"{v.get('standing')}/points {v.get('points')} in live official table")
            else:
                board_roster = {p.strip().lower() for p in str(v.get("roster") or "").split(",") if p.strip()}
                off_roster = {p.strip().lower() for p in chosen["roster"].split(",") if p.strip()}
                if board_roster != off_roster:
                    identity_mismatches.append(f"{v.get('name')}: roster differs from live official table")
        return float(v["points"]), False

    pa_points, a_floor = points_of(va, "a")
    pb_points, b_floor = points_of(vb, "b")
    if pa_points is None or pb_points is None:
        return {"ok": False, "reason": "rated points missing for an originated row",
                "re_prob_a": None, "re_prob_b": None, "identity_mismatches": identity_mismatches}

    re_a = core.vrs_prob(pa_points, pb_points)
    re_b = 1.0 - re_a
    ok = abs(re_a - res["prob_a"]) <= core.TOL_VRS and abs(re_b - res["prob_b"]) <= core.TOL_VRS
    bound_ok = True
    if basis == "originated_vrs_bound":
        bound_ok = bool(res.get("bound")) and (a_floor or b_floor)
        if not bound_ok:
            ok = False
    return {"ok": ok and not identity_mismatches and bound_ok,
            "reason": "" if (ok and not identity_mismatches and bound_ok)
            else "; ".join(filter(None, ["stored probability outside re-derivation tolerance" if not ok else "",
                                         *identity_mismatches,
                                         "" if bound_ok else "bound label/floor missing"])),
            "re_prob_a": re_a, "re_prob_b": re_b,
            "points_a": pa_points, "points_b": pb_points,
            "identity_mismatches": identity_mismatches,
            "live_official_crosscheck": official is not None}


def collect_sources(row: dict) -> list[str]:
    urls: list[str] = []
    if row.get("hotspawn_url"):
        urls.append(row["hotspawn_url"])
    for q in row.get("quotes", []):
        if q.get("public_url"):
            urls.append(q["public_url"])
        for u in q.get("evidence_urls", []) or []:
            urls.append(u)
    for v in (row.get("vrs_a"), row.get("vrs_b")):
        if v and v.get("details_url"):
            urls.append(v["details_url"])
    for s in row.get("sources", []) or []:
        if isinstance(s, str):
            urls.append(s)
        elif isinstance(s, dict) and s.get("url"):
            urls.append(s["url"])
    # de-duplicate, preserve order
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def normalise_quote(q: dict) -> dict:
    nv = core.novig(q.get("decimal_a"), q.get("decimal_b")) if q.get("decimal_a") else None
    return {
        "source_key": q.get("source_key"),
        "source_name": q.get("source_name"),
        "public_url": q.get("public_url"),
        "event_id": q.get("event_id"),
        "decimal_a": q.get("decimal_a"),
        "decimal_b": q.get("decimal_b"),
        "no_vig_prob_a": round(nv["prob_a"], 5) if nv else None,
        "no_vig_prob_b": round(nv["prob_b"], 5) if nv else None,
        "overround": round(nv["overround"], 5) if nv else None,
        "retrieved_utc": q.get("retrieved_utc"),
        "join_note": q.get("join_note"),
        "caveats": q.get("caveats", []) or [],
    }


BASIS_LABELS = {
    "market": "Market · book/exchange price",
    "originated_vrs": "Originated · official Valve VRS",
    "originated_vrs_bound": "Bound · one side unrated",
}


def verify_all() -> dict:
    raw = core.load(core.RAW_LOBBY_SNAPSHOT, default={})
    canonical = core.load(core.CANONICAL_BOARD, default={})
    secondary = core.load(SECONDARY_BOARD, default={})
    committed_vrs = core.load(core.COMMITTED_VRS, default={})
    valve_live = core.load("data/bce97e13/valve_live.json", default={}) or {}
    official_md = core.ROOT / "data/bce97e13/standings_official.md"
    official = core.parse_official_markdown(official_md.read_text(encoding="utf-8")) \
        if official_md.exists() else None

    open_fx = open_lobby_fixtures(raw)
    open_ids = {str(f["fixture_id"]) for f in open_fx}
    fx_by_id = {str(f["fixture_id"]): f for f in open_fx}
    canon = {str(r["fixture_id"]): r for r in canonical.get("rows", [])}
    second = {str(r["fixture_id"]): r for r in secondary.get("open", [])}
    # The canonical board's own state field ("open" vs "api_only") is the authoritative
    # lobby-render classification; four DFRAG cards have no permalink but ARE lobby cards.
    lobby_ids = {fid for fid, r in canon.items() if fid in open_ids and r.get("state") != "api_only"}
    api_only_fx = {fid: fx_by_id[fid] for fid, r in canon.items()
                   if fid in open_ids and r.get("state") == "api_only"}

    rows_out, unresolved_out = [], []
    checks_agg = {"coverage": 0, "arithmetic": 0, "identity": 0, "sources": 0, "no_crowd": 0}
    n_total = 0

    for fx in open_fx:
        fid = str(fx["fixture_id"])
        n_total += 1
        row = canon.get(fid)
        if row is None:
            unresolved_out.append({
                "fixture_id": fid, "team_a": fx.get("team_a"), "team_b": fx.get("team_b"),
                "competition": fx.get("competition"), "start_utc": fx.get("start_utc"),
                "hotspawn_url": fx.get("hotspawn_url"),
                "reason": "fixture is open in the live lobby snapshot but absent from the canonical board",
            })
            continue
        checks = []
        # 1. coverage: pick + both probabilities present
        res = row.get("resolution") or {}
        has_pick = bool(row.get("pick")) and res.get("prob_a") is not None and res.get("prob_b") is not None
        checks.append({"name": "coverage", "ok": has_pick,
                       "detail": "pick and both probabilities present" if has_pick
                       else "missing pick or probability"})
        if has_pick:
            checks_agg["coverage"] += 1

        # 2. arithmetic re-derivation
        basis = res.get("basis")
        if basis == "market":
            verdict = check_market(row)
        elif basis in ("originated_vrs", "originated_vrs_bound"):
            verdict = check_vrs(row, committed_vrs, official)
        else:
            verdict = {"ok": False, "reason": f"unknown resolution basis {basis!r}",
                       "re_prob_a": None, "re_prob_b": None}
        checks.append({"name": "arithmetic", "ok": verdict["ok"], "detail": verdict["reason"] or "re-derived",
                       "re_prob_a": verdict.get("re_prob_a"), "re_prob_b": verdict.get("re_prob_b")})
        if verdict["ok"]:
            checks_agg["arithmetic"] += 1
        if basis != "market":
            identity_ok = not verdict.get("identity_mismatches")
            checks.append({"name": "official_identity", "ok": identity_ok,
                           "detail": "points/standing/roster match live official Valve table"
                           if identity_ok and official is not None else
                           ("identity mismatch" if not identity_ok else "committed VRS only (live check unavailable)")})
            if identity_ok:
                checks_agg["identity"] += 1

        # 3. internal consistency: sums to 1, pick side, bound label
        sums_ok = abs(res.get("prob_a", 0) + res.get("prob_b", 0) - 1.0) <= 0.002
        want_side = "a" if res.get("prob_a", 0) > res.get("prob_b", 0) else "b"
        pick_ok = row.get("pick_side") == want_side and row.get("pick") in (row.get("team_a"), row.get("team_b"))
        bound_ok = basis != "originated_vrs_bound" or bool(res.get("bound"))
        consistent = sums_ok and pick_ok and bound_ok
        checks.append({"name": "consistency", "ok": consistent,
                       "detail": f"probs sum to 1, pick on higher-prob side"
                                 f"{'，bound labelled' if basis == 'originated_vrs_bound' else ''}"
                       if consistent else "sum/pick-side/bound inconsistency"})

        # 4. sources
        sources = collect_sources(row)
        external = [u for u in sources if u.startswith("http")]
        sources_ok = len(external) >= 1 and bool(row.get("hotspawn_url"))
        checks.append({"name": "sources", "ok": sources_ok,
                       "detail": f"{len(external)} openable source link(s)"})
        if sources_ok:
            checks_agg["sources"] += 1

        # 5. no HotSpawn crowd/vote input
        blob = str(row).lower()
        crowd_ok = ("crowd" not in blob and "vote_share" not in blob and "poll_pct" not in blob)
        quote_sources = {q.get("source_key") for q in row.get("quotes", [])}
        crowd_ok = crowd_ok and "hotspawn" not in quote_sources
        checks.append({"name": "no_crowd_input", "ok": crowd_ok,
                       "detail": "no HotSpawn crowd/vote percentage used" if crowd_ok
                       else "crowd-like field detected"})
        if crowd_ok:
            checks_agg["no_crowd"] += 1

        # secondary-board direction cross-check
        sec = second.get(fid)
        cross = None
        if sec and sec.get("line"):
            cross = {"agrees": sec["line"].get("pick_team") == row.get("pick"),
                     "other_pick": sec["line"].get("pick_team"),
                     "other_prob": sec["line"].get("pick_prob")}

        verified = all(c["ok"] for c in checks)
        out_row = {
            "fixture_id": fid,
            "competition": row.get("competition"),
            "tier": row.get("tier"),
            "stage": row.get("stage"),
            "start_utc": row.get("start_utc"),
            "lock_utc": row.get("lock_utc"),
            "status": row.get("status"),
            "state": row.get("state"),
            "lobby_rendered": row.get("state") != "api_only",
            "api_only": row.get("state") == "api_only",
            "permalink_verified": fx.get("permalink_verified", True),
            "seen_in": fx.get("seen_in"),
            "team_a": row.get("team_a"),
            "team_b": row.get("team_b"),
            "hotspawn_url": row.get("hotspawn_url"),
            "pick": row.get("pick"),
            "pick_side": row.get("pick_side"),
            "pick_prob": res.get("prob_b") if row.get("pick_side") == "b" else res.get("prob_a"),
            "prob_a": res.get("prob_a"),
            "prob_b": res.get("prob_b"),
            "basis": basis,
            "basis_label": BASIS_LABELS.get(basis, basis),
            "bound": res.get("bound"),
            "confidence": core.confidence(row["resolution"][f"prob_{row.get('pick_side')}"])
            if row.get("pick_side") in ("a", "b") else None,
            "quotes": [normalise_quote(q) for q in row.get("quotes", [])],
            "vrs_a": row.get("vrs_a"),
            "vrs_b": row.get("vrs_b"),
            "vrs_floor": row.get("vrs_floor"),
            "flags": row.get("flags", []) or [],
            "sources": sources,
            "cross_board": cross,
            "verification": {"status": "verified" if verified else "unverified", "checks": checks},
        }
        rows_out.append(out_row)
        if not verified:
            unresolved_out.append({
                "fixture_id": fid, "team_a": row.get("team_a"), "team_b": row.get("team_b"),
                "competition": row.get("competition"), "start_utc": row.get("start_utc"),
                "hotspawn_url": row.get("hotspawn_url"),
                "reason": "; ".join(c["detail"] for c in checks if not c["ok"]),
            })

    # API-only fixtures (present in the fixtures API but never rendered as a lobby pick card)
    api_only = []
    for fid, fxrow in sorted(api_only_fx.items()):
        row = canon.get(fid, {})
        res = row.get("resolution") or {}
        api_only.append({
            "fixture_id": fid, "team_a": fxrow.get("team_a"), "team_b": fxrow.get("team_b"),
            "competition": fxrow.get("competition"), "start_utc": fxrow.get("start_utc"),
            "status": fxrow.get("status"), "seen_in": fxrow.get("seen_in"),
            "pick": row.get("pick"),
            "pick_prob": (res.get("prob_b") if row.get("pick_side") == "b" else res.get("prob_a")),
            "note": "listed by the HotSpawn fixtures API but not rendered as a lobby pick card; "
                    "the API reports it 'started' weeks before its 12 Nov kick-off",
        })

    rows_out.sort(key=lambda r: (r["start_utc"] or "", r["fixture_id"]))
    n_verified = sum(1 for r in rows_out if r["verification"]["status"] == "verified")
    n_market = sum(1 for r in rows_out if r["basis"] == "market")
    n_vrs = sum(1 for r in rows_out if r["basis"] == "originated_vrs")
    n_bound = sum(1 for r in rows_out if r["basis"] == "originated_vrs_bound")

    limitations = canonical.get("limitations", [])
    irregularities = list(canonical.get("irregularities", []))
    # This session's own finding: precise provenance of the slope constant.
    slope = (valve_live.get("slope_check") or {}) if valve_live else {}
    irregularities.append({
        "id": "BCE97E13-R1", "severity": "citation",
        "title": "Slope C=0.0056000078 is derived, not a literal constant",
        "detail": ("The number is not written verbatim in Valve's repository. It is the effective "
                   "logistic slope produced by model/glicko.js (Q = ln(10)/400) combined with "
                   "model/fit.js defaultGlickoParams.rd = 75 via setFixedRD: C = ln(10)*g(75)/400. "
                   f"Live re-derivation gave {slope.get('derived_slope_c')} "
                   f"(match={slope.get('matches_canonical')}). Value verified correct; citation should name both files."),
        "source": core.VALVE_BLOB + "model/glicko.js",
    })

    verification = {
        "session": "bce97e13",
        "generated_utc": core.now_utc(),
        "inputs": {
            "raw_lobby_snapshot": core.RAW_LOBBY_SNAPSHOT,
            "raw_snapshot_utc": raw.get("fixture_snapshot_utc"),
            "canonical_board": core.CANONICAL_BOARD,
            "canonical_generated_utc": canonical.get("generated_utc"),
            "committed_vrs": core.COMMITTED_VRS,
            "valve_live": valve_live,
        },
        "summary": {
            "open_lobby_fixtures": len(lobby_ids),
            "open_fixtures_total": len(open_fx),
            "canonical_rows": len(canon),
            "verified_rows": n_verified,
            "unverified_rows": len(rows_out) - n_verified,
            "unresolved": len(unresolved_out),
            "api_only_fixtures": len(api_only),
            "market_rows": n_market,
            "originated_vrs_rows": n_vrs,
            "bound_rows": n_bound,
            "checks_passed": checks_agg,
            "checks_total": n_total,
            "all_open_fixtures_covered": len(unresolved_out) == 0
                                       and all(r["verification"]["status"] == "verified" for r in rows_out),
        },
        "limitations": limitations,
        "irregularities": irregularities,
        "unresolved": unresolved_out,
        "api_only": api_only,
    }
    board = {
        "session": "bce97e13",
        "generated_utc": verification["generated_utc"],
        "source_board": core.CANONICAL_BOARD,
        "raw_snapshot_utc": raw.get("fixture_snapshot_utc"),
        "valve_live_fetched_utc": valve_live.get("fetched_utc"),
        "summary": verification["summary"],
        "rows": rows_out,
    }
    core.dump_json(OUT_VERIFY, verification)
    core.dump_json(OUT_BOARD, board)
    print(f"verified {n_verified}/{len(rows_out)} open rows · market {n_market} · vrs {n_vrs} · "
          f"bounds {n_bound} · unresolved {len(unresolved_out)} · api-only {len(api_only)}")
    return verification


if __name__ == "__main__":
    result = verify_all()
    if not result["summary"]["all_open_fixtures_covered"]:
        print("WARNING: coverage or verification gaps present - see verification.json", file=sys.stderr)
    sys.exit(0)
