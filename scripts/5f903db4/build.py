#!/usr/bin/env python3
"""EVERYPICK builder (session 5f903db4).

Input  (all committed snapshots, re-read on every run):
    data/f7279a54/board.json        canonical 30-minute board: lobby fixtures + featured book quotes
    data/fe803b80/board.json        independent collector: extra fixtures + Thunderpick quotes
    data/19d6c262/vrs_global.json   official Valve VRS global standings (2026_10_05)
    scripts/5f903db4/research.json  hand-verified joins / aliases / attempt ledger
    data/5f903db4/snapshot.json     optional live snapshot written by collect.py in CI

Output:
    data/5f903db4/board.json        one row per open HotSpawn CS2 fixture: pick, both probabilities,
                                    basis, per-source evidence, alternatives and limitations
    everypick/*.html                phone-first pages (rendered by site.py)

Rules enforced here (and re-checked by tests/test_5f903db4.py):
  * every open fixture gets a pick and two probabilities, or an explicit "unresolved" row;
  * a probability is either re-derived from a published bookmaker price (no-vig) or originated
    from the official Valve VRS points with the published formula and slope;
  * a one-sided rating becomes a labelled bound, never a point estimate;
  * HotSpawn's crowd-pick percentage is never read;
  * duplicate Valve rows are resolved by a published rule and all alternatives are kept.
"""
from __future__ import annotations

import importlib.util as _iu
import sys
from datetime import datetime, timezone
from pathlib import Path

_spec = _iu.spec_from_file_location("everpick_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["everpick_core"] = core
_spec.loader.exec_module(core)

FIX_BOARD = "data/f7279a54/board.json"
EXTRA_BOARD = "data/fe803b80/board.json"
VRS_JSON = "data/19d6c262/vrs_global.json"
RESEARCH = "scripts/5f903db4/research.json"
LIVE = "data/5f903db4/snapshot.json"
CACHED_VRS = "data/5f903db4/vrs_global.json"
OUT = "data/5f903db4/board.json"

VRS_PAGE = f"{core.VRS_BLOB}live/2026/standings_global_2026_10_05.md"
VRS_TREE = core.VRS_TREE_API
NEWEST_VRS_VERIFIED = {
    "checked_utc": "2026-10-21T19:34:00Z",
    "newest_published_file": "live/2026/standings_global_2026_10_05.md",
    "api_url": VRS_TREE,
    "note": ("GitHub contents listing of ValveSoftware/counter-strike_regional_standings/live/2026 "
             "returns 40 standings files; the newest global table is 2026_10_05. No 2026_10_12 or "
             "2026_10_19 file is published, so the 2026_10_05 table is current-by-publisher."),
}
TOLERANCE_S = 90 * 60  # quotes are joined only when the kick-off agrees to within 90 minutes


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def pct(p):
    return None if p is None else round(float(p) * 100.0, 1)


# --------------------------------------------------------------------------------- fixtures
def collect_fixtures(primary: dict, extra: dict) -> list[dict]:
    rows: dict[str, dict] = {}
    for src, board, state in (("data/f7279a54/board.json", primary, "open"),
                              ("data/fe803b80/board.json", extra, "open")):
        for m in board.get("open") or []:
            fid = str(m.get("fixture_id") or "")
            if not fid or fid in rows:
                continue
            rows[fid] = {
                "fixture_id": fid,
                "competition": m.get("competition"),
                "tier": m.get("tier"),
                "stage": m.get("stage"),
                "start_utc": m.get("start_utc"),
                "lock_utc": m.get("lock_utc"),
                "status": m.get("status"),
                "team_a": m.get("team_a"),
                "team_b": m.get("team_b"),
                "hotspawn_url": m.get("hotspawn_url"),
                "seen_in": m.get("seen_in") or [],
                "source_board": src,
                "state": state,
            }
    for row in rows.values():
        if row["fixture_id"] == "1080200":
            # listed by the fixtures API only: the lobby does not render a pick card for it and
            # the API itself reports status "started" for a fixture dated 12 Nov.
            row["state"] = "api_only"
    return sorted(rows.values(), key=lambda r: (str(r["start_utc"] or ""), r["fixture_id"]))


# ------------------------------------------------------------------------------------ quotes
def reorient(decimal_a, decimal_b, quoted_a, quoted_b, team_a, team_b,
             declared_order=None) -> tuple | None:
    """Return (decimal for fixture team_a, decimal for fixture team_b) or None if not joinable.

    A quote with no team names of its own is only accepted from a board that already published it
    against this fixture id (data/f7279a54 stores its joined quotes without repeating the names);
    in that case the published order is the fixture order.
    """
    if not decimal_a or not decimal_b:
        return None
    if not quoted_a and not quoted_b:
        return float(decimal_a), float(decimal_b)
    declared = str(declared_order or "").lower()
    if declared in ("ab", "ba"):
        return (float(decimal_a), float(decimal_b)) if declared == "ab" \
            else (float(decimal_b), float(decimal_a))
    na, nb = core.norm(quoted_a), core.norm(quoted_b)
    fa, fb = core.norm(team_a), core.norm(team_b)
    if na == fa and nb == fb:
        return float(decimal_a), float(decimal_b)
    if na == fb and nb == fa:
        return float(decimal_b), float(decimal_a)
    return None


def quote_record(fixture: dict, q: dict, origin: str) -> dict | None:
    pair = reorient(q.get("decimal_a"), q.get("decimal_b"),
                    q.get("team_a") or q.get("quoted_team_a"),
                    q.get("team_b") or q.get("quoted_team_b"),
                    fixture["team_a"], fixture["team_b"], q.get("declared_order"))
    if not pair:
        return None
    start = q.get("start_utc")
    fstart = parse_ts(fixture["start_utc"])
    if start and fstart:
        diff = abs((parse_ts(start) - fstart).total_seconds())
        if diff > TOLERANCE_S:
            return None
    else:
        diff = None
    nv = core.novig(*pair)
    if not nv:
        return None
    return {
        "source_key": q.get("source_key"),
        "source_name": q.get("source_name") or q.get("source_key"),
        "event_id": q.get("event_id"),
        "public_url": q.get("public_url"),
        "api_url": q.get("api_url"),
        "decimal_a": round(pair[0], 6),
        "decimal_b": round(pair[1], 6),
        "prob_a": round(nv["prob_a"], 6),
        "prob_b": round(nv["prob_b"], 6),
        "overround": round(nv["overround"], 6),
        "start_utc": start or fixture["start_utc"],
        "start_diff_minutes": None if diff is None else round(diff / 60.0, 1),
        "retrieved_utc": q.get("retrieved_utc"),
        "origin": origin,
        "raw_format": q.get("raw_format"),
        "raw": q.get("raw"),
        "join_note": q.get("join_note"),
        "evidence_urls": q.get("evidence_urls") or [],
        "caveats": q.get("caveats") or [],
    }


def build_quotes(fixture: dict, primary_quotes: dict, extra_quotes: dict, research: dict) -> list:
    out, seen = [], set()

    def add(rec):
        if not rec:
            return
        key = (rec["source_key"], str(rec["event_id"]))
        if key in seen:
            return
        seen.add(key)
        out.append(rec)

    for q in primary_quotes.get(fixture["fixture_id"], []):
        add(quote_record(fixture, q, "board f7279a54"))
    # the second collector publishes Thunderpick prices the primary board does not carry
    for q in extra_quotes.get(fixture["fixture_id"], []):
        if q.get("source_key") != "thunderpick":
            continue
        add(quote_record(fixture, q, "board fe803b80"))
    for q in research.get("quotes") or []:
        if str(q.get("fixture_id")) != fixture["fixture_id"]:
            continue
        add(quote_record(fixture, q, "research 5f903db4"))
    return out


# --------------------------------------------------------------------------------------- VRS
def side_rating(index: dict, name: str, aliases: dict) -> dict:
    hit = core.vrs_lookup(index, name, aliases)
    if not hit:
        return {"name": name, "listed": False, "points": None, "standing": None,
                "alternatives": [], "row": None}
    chosen = hit["chosen"]
    return {
        "name": name,
        "listed": True,
        "vrs_name": chosen.get("team"),
        "points": float(chosen.get("points")),
        "standing": chosen.get("standing"),
        "roster": chosen.get("roster"),
        "roster_size": len([p for p in str(chosen.get("roster") or "").split(",") if p.strip()]),
        "latest_match_date": chosen.get("latest_match_date"),
        "details_url": chosen.get("details_url"),
        "ambiguous": hit["ambiguous"],
        "alternatives": [
            {"vrs_name": r.get("team"), "standing": r.get("standing"), "points": r.get("points"),
             "roster": r.get("roster"), "latest_match_date": r.get("latest_match_date")}
            for r in hit["rows"][1:]
        ],
        "row": chosen,
    }


def originate(side_a: dict, side_b: dict, floor: dict | None) -> dict:
    """Originate a probability from official Valve VRS points.

    Both sides rated      -> point estimate, plus a range over Valve's other published rows.
    One side unlisted     -> the unlisted side is at or below Valve's published floor, so the
                             listed side's number is a LOWER bound and the unlisted side's number
                             is an UPPER bound. Published as a bound, never as a point estimate.
    """
    k = core.CAL_K
    if side_a["listed"] and side_b["listed"]:
        p = core.vrs_prob(side_a["points"], side_b["points"], k)
        cands = []
        for pa in [side_a["points"]] + [a["points"] for a in side_a["alternatives"]]:
            for pb in [side_b["points"]] + [a["points"] for a in side_b["alternatives"]]:
                if pa is None or pb is None:
                    continue
                cands.append(core.vrs_prob(float(pa), float(pb), k))
        return {"basis": "originated_vrs", "prob_a": p, "prob_b": 1.0 - p,
                "bound": None, "range": [min(cands), max(cands)] if cands else None,
                "delta_points": side_a["points"] - side_b["points"]}

    if not floor or not floor.get("points"):
        return {"basis": "unresolved", "prob_a": None, "prob_b": None, "bound": None,
                "range": None, "delta_points": None}

    if side_a["listed"] and not side_b["listed"]:
        p = core.vrs_prob(side_a["points"], float(floor["points"]), k)
        return {"basis": "originated_vrs_bound", "prob_a": p, "prob_b": 1.0 - p,
                "bound": {"side": "a", "relation": ">=", "floor_standing": floor.get("standing"),
                          "floor_points": floor.get("points")},
                "range": None,
                "delta_points": side_a["points"] - float(floor["points"])}
    if side_b["listed"] and not side_a["listed"]:
        p = core.vrs_prob(side_b["points"], float(floor["points"]), k)
        return {"basis": "originated_vrs_bound", "prob_a": 1.0 - p, "prob_b": p,
                "bound": {"side": "b", "relation": ">=", "floor_standing": floor.get("standing"),
                          "floor_points": floor.get("points")},
                "range": None,
                "delta_points": side_b["points"] - float(floor["points"])}
    return {"basis": "unresolved", "prob_a": None, "prob_b": None, "bound": None, "range": None,
            "delta_points": None}


# ---------------------------------------------------------------------------------------- main
def build() -> dict:
    primary = core.load(FIX_BOARD, {}) or {}
    extra = core.load(EXTRA_BOARD, {}) or {}
    vrs_doc = core.load(VRS_JSON, {}) or {}
    cached_vrs = core.load(CACHED_VRS, {}) or {}
    if cached_vrs.get("teams") and str(cached_vrs.get("snapshot") or "") > str(vrs_doc.get("snapshot") or ""):
        vrs_doc = cached_vrs  # collect.py cached a newer official Valve table than the committed one
    research = core.load(RESEARCH, {}) or {}
    live = core.load(LIVE, {}) or {}

    if not primary.get("open"):
        raise SystemExit(f"{FIX_BOARD} is missing or has no open fixtures - refusing to guess")

    fixtures = collect_fixtures(primary, extra)
    index = core.vrs_index(vrs_doc)
    floor = core.vrs_floor(vrs_doc)

    primary_quotes: dict[str, list] = {}
    for m in primary.get("open") or []:
        primary_quotes[str(m.get("fixture_id"))] = m.get("quotes") or []
    extra_quotes: dict[str, list] = {}
    for m in extra.get("open") or []:
        extra_quotes[str(m.get("fixture_id"))] = m.get("quotes") or []
    # live collector output (CI) is merged on the same dedupe keys
    for m in live.get("fixtures") or []:
        if m.get("quotes"):
            extra_quotes.setdefault(str(m.get("fixture_id")), []).extend(m["quotes"])
    for q in live.get("quotes") or []:
        if q.get("fixture_id"):
            extra_quotes.setdefault(str(q["fixture_id"]), []).append(q)

    aliases = {}
    for fid, spec in (research.get("aliases") or {}).items():
        if spec.get("team_a_vrs"):
            aliases[core.norm(spec["team_a_vrs"])] = spec["team_a_vrs"]
        if spec.get("team_b_vrs"):
            aliases[core.norm(spec["team_b_vrs"])] = spec["team_b_vrs"]
    team_aliases = research.get("team_aliases") or {}

    rows = []
    for fx in fixtures:
        quotes = build_quotes(fx, primary_quotes, extra_quotes, research)
        side_a = side_rating(index, fx["team_a"], team_aliases)
        side_b = side_rating(index, fx["team_b"], team_aliases)

        row = dict(fx)
        row["quotes"] = quotes
        row["vrs_a"] = {k: side_a[k] for k in ("name", "listed", "vrs_name", "points", "standing",
                                               "roster", "latest_match_date", "details_url",
                                               "ambiguous", "alternatives")} if side_a["listed"] else \
                        {k: side_a.get(k) for k in ("name", "listed", "ambiguous")}
        row["vrs_b"] = {k: side_b[k] for k in ("name", "listed", "vrs_name", "points", "standing",
                                               "roster", "latest_match_date", "details_url",
                                               "ambiguous", "alternatives")} if side_b["listed"] else \
                        {k: side_b.get(k) for k in ("name", "listed", "ambiguous")}
        row["vrs_floor"] = floor
        row["vrs_page_url"] = VRS_PAGE

        flags = []
        if side_a.get("ambiguous") or side_b.get("ambiguous"):
            flags.append("vrs_duplicate_rows_resolved_by_published_rule")
        if side_a["listed"] and not side_a.get("roster_size", 0) >= 5:
            flags.append(f"vrs_roster_a_incomplete")
        if side_b["listed"] and not side_b.get("roster_size", 0) >= 5:
            flags.append(f"vrs_roster_b_incomplete")

        alt = originate(side_a, side_b, floor)
        if quotes:
            pa = sum(q["prob_a"] for q in quotes) / len(quotes)
            pb = 1.0 - pa
            row["resolution"] = {
                "basis": "market",
                "prob_a": pa, "prob_b": pb,
                "n_books": len(quotes),
                "book_spread_pp": round(max(q["prob_a"] for q in quotes) * 100
                                        - min(q["prob_a"] for q in quotes) * 100, 1),
                "bound": None, "range": None, "delta_points": None,
            }
            if len(quotes) == 1:
                flags.append("single_book_quote")
            if any((q.get("raw") or {}).get("volume_dollars") == 0 for q in quotes):
                flags.append("exchange_quote_zero_volume")
            if alt.get("prob_a") is not None and (alt["prob_a"] >= 0.5) != (pa >= 0.5):
                flags.append("market_and_rating_model_disagree_on_the_pick")
        else:
            row["resolution"] = originate(side_a, side_b, floor)
            flags.append("no_external_price_any_book")
            if row["resolution"]["basis"] == "originated_vrs":
                flags.append("originated_from_official_valve_vrs")
            if row["resolution"]["basis"] == "originated_vrs_bound":
                flags.append("originated_bound_unlisted_opponent")
            if row["resolution"]["basis"] == "unresolved":
                flags.append("unresolved")

        row["alt_origination"] = alt if quotes else None
        res = row["resolution"]
        if res["prob_a"] is not None:
            if res["prob_a"] >= res["prob_b"]:
                row["pick"], row["pick_prob"], row["pick_side"] = fx["team_a"], res["prob_a"], "a"
            else:
                row["pick"], row["pick_prob"], row["pick_side"] = fx["team_b"], res["prob_b"], "b"
            row["confidence"] = core.confidence(row["pick_prob"])
            if res["basis"] == "originated_vrs_bound":
                row["confidence"] = "Bound"
            if res.get("range") and (res["range"][1] - res["range"][0]) > 0.10:
                flags.append("rating_range_wider_than_10pp")
            if res["basis"].startswith("originated"):
                row["confidence"] = row["confidence"] if res["basis"] != "originated_vrs_bound" \
                    else "Bound"
        else:
            row["pick"] = None
            row["pick_prob"] = None
            row["pick_side"] = None
            row["confidence"] = None

        if fx["state"] == "api_only":
            flags.append("fixtures_api_only_not_rendered_in_lobby")
            if str(fx.get("status")) != "scheduled" and fx.get("start_utc", "") > now_utc():
                flags.append("api_status_conflict_future_fixture_marked_started")

        row["flags"] = sorted(set(f for f in flags if f))
        sources = [{"label": "HotSpawn Pick'ems lobby (fixture discovery only - never a probability source)",
                    "url": fx["hotspawn_url"] or core.LOBBY_URL,
                    "note": "fixture identity, teams and UTC kick-off"}]
        if fx.get("seen_in") and "api" in fx["seen_in"]:
            sources.append({"label": "HotSpawn fixtures API (same public API the lobby calls)",
                            "url": core.HOTSPAWN_API,
                            "note": "kick-off, lock time and listing status"})
        for side in (side_a, side_b):
            if side["listed"]:
                sources.append({"label": f"Valve VRS standings - {side.get('vrs_name')} "
                                         f"#{side.get('standing')} ({int(side['points'])} pts)",
                                "url": side.get("details_url") or VRS_PAGE,
                                "note": "official Valve rating used in the originated line"
                                        if not quotes else "official Valve rating (context)"})
        for q in quotes:
            sources.append({"label": f"{q['source_name']} - {q['decimal_a']} / {q['decimal_b']} "
                                     f"decimal (event {q['event_id']})",
                            "url": q.get("public_url") or q.get("api_url"),
                            "note": f"no-vig {pct(q['prob_a'])}% / {pct(q['prob_b'])}%, "
                                    f"overround {q['overround']*100:.2f}%"})
        if not quotes:
            sources.append({"label": "Valve VRS published table (origination input)",
                            "url": VRS_PAGE,
                            "note": f"logistic line: k={core.CAL_K} x C={core.VALVE_C} x points delta"})
        row["sources"] = [s for s in sources if s.get("url")]
        if not any(r["fixture_id"] == fx["fixture_id"] for r in rows):
            rows.append(row)

    market = [r for r in rows if r["resolution"]["basis"] == "market"]
    orig = [r for r in rows if r["resolution"]["basis"] == "originated_vrs"]
    bound = [r for r in rows if r["resolution"]["basis"] == "originated_vrs_bound"]
    unresolved = [r for r in rows if r["resolution"]["basis"] == "unresolved"]

    board = {
        "session": "5f903db4",
        "generated_utc": now_utc(),
        "policy": {
            "ladder": ["featured market quotes (bovada / melbet / pinnacle)",
                       "exchange + secondary book quotes (kalshi, thunderpick via bo3.gg)",
                       "official Valve VRS origination with the published formula",
                       "explicit bound when only one side is rated",
                       "explicit unresolved row (never a guessed number)"],
            "never_used": "HotSpawn crowd-pick percentages",
            "formula": "p = 1 / (1 + exp(-k * C * (points_a - points_b)))",
            "k": core.CAL_K,
            "k_source": core.CAL_SOURCE,
            "k_mae_prob": core.CAL_MAE,
            "k_pairs": core.CAL_PAIRS,
            "C": core.VALVE_C,
            "C_source": core.VALVE_C_URL,
            "vrs_select_rule": core.VRS_SELECT_RULE,
            "bound_rule": ("If one side has no row in Valve's published table, that side is at or "
                           "below the published floor (#380, 381 pts). The listed side's number is "
                           "published as a lower bound and the unlisted side's number as an upper "
                           "bound. It is never presented as a point estimate."),
            "quote_join_tolerance_minutes": TOLERANCE_S // 60,
        },
        "sources": {
            "hotspawn_lobby": core.LOBBY_URL,
            "hotspawn_api": core.HOTSPAWN_API,
            "valve_vrs_page": VRS_PAGE,
            "valve_vrs_snapshot": vrs_doc.get("snapshot"),
            "valve_vrs_newest_check": NEWEST_VRS_VERIFIED,
            "kalshi_events_api": core.KALSHI_EVENTS,
            "melbet_feed": core.MELBET_FEED,
            "bo3_thunderpick_api": core.BO3_API,
            "pinnacle": core.PINNACLE_HUB,
            "bovada": core.BOVADA_CS2,
        },
        "inputs": {
            "primary_board": {"path": FIX_BOARD, "generated_utc": primary.get("generated_utc")},
            "extra_board": {"path": EXTRA_BOARD, "generated_utc": extra.get("generated_utc")},
            "vrs": {"path": CACHED_VRS if vrs_doc is cached_vrs else VRS_JSON,
                    "snapshot": vrs_doc.get("snapshot"),
                    "teams": vrs_doc.get("n_teams"), "floor": vrs_doc.get("floor")},
            "research": {"path": RESEARCH, "read_utc": (research.get("read_log") or [{}])[0].get("read_utc")},
            "live_snapshot": (live.get("generated_utc") if live else None),
        },
        "summary": {
            "rows": len(rows),
            "lobby_open": len([r for r in rows if r["state"] == "open"]),
            "api_only": len([r for r in rows if r["state"] == "api_only"]),
            "with_pick": len([r for r in rows if r["pick"]]),
            "unresolved": len(unresolved),
            "market": len(market),
            "originated_both_rated": len(orig),
            "originated_bound": len(bound),
            "single_book": len([r for r in rows if "single_book_quote" in r["flags"]]),
            "ambiguous_rating_rows": len([r for r in rows
                                          if "vrs_duplicate_rows_resolved_by_published_rule" in r["flags"]]),
        },
        "rows": rows,
        "attempted_sources": research.get("attempted_sources") or [],
        "read_log": research.get("read_log") or [],
        "calibration_check": calibration_check(),
        "limitations": limitations(rows, bound, vrs_doc),
        "irregularities": irregularities(rows, primary, extra, research, vrs_doc),
    }
    return board


def calibration_check() -> dict:
    """Re-fit the logistic slope on the published calibration pairs.

    Proves the constant used for every originated line is the best fit available on the 60
    market-vs-rating pairs this repository collected, instead of asserting it.
    """
    pairs = core.load("data/f7279a54/calibration_pairs.json", {}) or {}
    values = list(pairs.values()) if isinstance(pairs, dict) else list(pairs or [])
    values = [p for p in values if p.get("delta") is not None and p.get("market_prob_a") is not None]
    if not values:
        return {"available": False}

    def mae(k):
        return sum(abs(core.logistic(k * core.VALVE_C * float(p["delta"])) - float(p["market_prob_a"]))
                   for p in values) / len(values)

    grid = [(round(mae(k / 1000.0), 6), k / 1000.0) for k in range(5, 2001)]
    best_mae, best_k = min(grid)
    flips = sum(1 for p in values
                if abs(float(p["delta"])) > 0
                and ((core.logistic(core.CAL_K * core.VALVE_C * float(p["delta"])) >= 0.5)
                     != (float(p["market_prob_a"]) >= 0.5)))
    return {
        "available": True,
        "pairs": len(values),
        "k_used": core.CAL_K,
        "mae_at_k_used": round(mae(core.CAL_K), 6),
        "k_best_grid": best_k,
        "mae_at_best": best_mae,
        "grid": "k from 0.005 to 2.000 in steps of 0.001, fixed C = 0.0056000078",
        "favourite_flips": flips,
        "favourite_flips_note": ("pairs where the rating model's favourite differs from the market's "
                                 "favourite - the same error mode that produces the Zetta v LOS NINOS "
                                 "conflict"),
        "source": "data/f7279a54/calibration_pairs.json",
    }


def limitations(rows, bound, vrs_doc) -> list:
    out = [
        {"id": "L1", "title": "Reference books do not price tier-C CS2",
         "detail": (f"{len([r for r in rows if r['resolution']['basis'] != 'market'])} of {len(rows)} "
                    "open fixtures have no price at Bovada, Melbet, Pinnacle, Thunderpick or Kalshi "
                    "(all five read today). Those rows carry an originated line from Valve's official "
                    "rating table instead of a blank."),
         "source": core.KALSHI_EVENTS},
        {"id": "L2", "title": "Originated lines are models, not market prices",
         "detail": (f"Formula p = 1/(1+exp(-k*C*points_delta)) with Valve's published C={core.VALVE_C} "
                    f"and this project's fitted k={core.CAL_K} ({core.CAL_PAIRS} market-vs-rating pairs). "
                    f"The fit's own mean absolute error is {core.CAL_MAE*100:.2f} percentage points, so "
                    "treat originated probabilities as +/-8 pp."),
         "source": core.VALVE_C_URL},
        {"id": "L3", "title": "Valve's rating table is 16 days old",
         "detail": ("The newest published global table is 2026_10_05; Valve publishes roughly monthly. "
                    "Promotion/relegation, roster changes and results after 5 Oct are not reflected. "
                    "Valve rows also carry a latest_match_date per roster, which is published alongside "
                    "every rating used here."),
         "source": NEWEST_VRS_VERIFIED["api_url"]},
        {"id": "L4", "title": "One-sided ratings become bounds, not points",
         "detail": (f"{len(bound)} fixtures have exactly one rated side. The unrated side is at or "
                    "below Valve's published floor (#380, 381 pts), so those rows show '>=' on the "
                    "rated side and '<=' on the other. They are directional, not calibrated."),
         "source": VRS_PAGE},
        {"id": "L5", "title": "Thin exchange book on the one Kalshi-priced fixture",
         "detail": ("The Kalshi quote used for Zetta v LOS NINOS has zero traded volume and a 0.16 "
                    "wide two-way spread (Los Ninos 0.55/0.63, Alianza Lima 0.39/0.47). Our VRS "
                    "origination and bo3.gg's own model both favour the other side, so the row is "
                    "flagged as a basis conflict and the pick is shown with Lean confidence."),
         "source": "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct211800lnale"},
        {"id": "L6", "title": "Clock conflicts are not silently joined",
         "detail": ("Books occasionally list the same pairing at a different kick-off (e.g. Kalshi's "
                    "Apogee Esports vs UNiTY esports event is priced at 16:30Z while HotSpawn and two "
                    "other books have 14:00Z). Quotes are joined only when the kick-off agrees within "
                    "90 minutes; conflicts are listed on Flagged for review."),
         "source": "https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&status=open&limit=200&with_nested_markets=false"},
        {"id": "L7", "title": "HotSpawn's own listing is not always complete",
         "detail": ("Four DFRAG Invitational fixtures render a pick card with no match permalink, and "
                    "one fixture (Wildcard v DENDELE, 12 Nov) exists in the fixtures API but is not "
                    "rendered in the lobby and is marked 'started' months early. It is included here "
                    "as an API-only row so no fixture is dropped."),
         "source": core.HOTSPAWN_API},
    ]
    return out


def irregularities(rows, primary, extra, research, vrs_doc) -> list:
    out = []
    dupes = [r for r in rows if "vrs_duplicate_rows_resolved_by_published_rule" in r["flags"]]
    if dupes:
        out.append({
            "id": "R1", "severity": "data",
            "title": "Valve publishes two rows for the same organisation (different rosters)",
            "detail": (("; ".join(f"{r['fixture_id']} {r['team_a']} v {r['team_b']}"
                                  for r in dupes)) +
                       ". Both rows are in standings_global_2026_10_05.md with different points. "
                       "This build applies the published roster rule (full five, newest latest_match_date) "
                       "and keeps the alternative in the row data, so the choice is auditable."),
            "source": VRS_PAGE,
            "affected": [r["fixture_id"] for r in dupes],
        })
    blanks = [r for r in rows if not r["quotes"]]
    out.append({
        "id": "R2", "severity": "upstream",
        "title": "Two collectors disagree on the same fixture and one leaves rows blank",
        "detail": (f"data/fe803b80/board.json stores {len([m for m in (extra.get('open') or []) if m.get('pick') is None and (m.get('model') or m.get('line'))])} "
                   "open rows with the top-level pick/probability set to null while their own 'line' or "
                   "'model' block holds the numbers, and it also keeps a Kalshi quote whose sides are "
                   "inverted (Turma do Pagode labelled at 0.78 when the exchange prices Imperial there). "
                   "This build reads raw decimals and re-derives every no-vig price itself, and it does "
                   "not import that inverted quote."),
        "source": "data/fe803b80/board.json",
        "affected": [str(m.get("fixture_id")) for m in (extra.get("open") or [])
                     if m.get("pick") is None and (m.get("model") or m.get("line"))],
    })
    out.append({
        "id": "R3", "severity": "upstream",
        "title": "Primary board resolves duplicate Valve rows the other way round",
        "detail": ("Both collectors mishandle Valve's duplicate rows, in opposite ways. "
                   "data/f7279a54/board.json flags 'Banda chuya', 'The Huns' and 'benched gods' as "
                   "ambiguous and therefore publishes no rating for those sides at all; "
                   "data/fe803b80/board.json instead silently picks the older/lower rows (Banda Chuya "
                   "#373 402 pts, The Huns #213 701 pts, benched gods #329 516 pts), which flips the "
                   "Banda Chuya pick. bo3.gg's squad page for Banda Chuya lists exactly Valve's five-man "
                   "row (#165, 801 pts, latest match 2026-10-04), and Valve's own latest_match_date "
                   "column agrees, so the five-man row is the active one. Both the selected and the "
                   "alternative values are published on every affected row."),
        "source": "data/fe803b80/board.json + https://bo3.gg/teams/banda-chuya",
        "affected": ["1081600", "1082792", "1081597"],
    })
    out.append({
        "id": "R4", "severity": "upstream",
        "title": "Kalshi market timestamps are shifted against its own rules text",
        "detail": ("Two independent events show the same offset: KXCS2GAME-26OCT211800LNALE's rules text "
                   "says 'Oct 21, 2026 at 6:00 PM EDT' (22:00Z) while its occurrence_datetime says "
                   "2026-10-22T02:00:00Z, and KXCS2GAME-26OCT220100RAVA's rules text says 'Oct 22, 2026 at "
                   "1:00 AM EDT' (05:00Z) while its occurrence_datetime says 09:00Z - a +4h shift on both. "
                   "The rules text agrees with HotSpawn, HLTV and bo3.gg, so the rules-text kick-off is "
                   "used and the event clocks are treated as unreliable."),
        "source": "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=KXCS2GAME-26OCT211800LNALE",
        "affected": ["1082837"],
    })
    out.append({
        "id": "R5", "severity": "site",
        "title": "The previous root landing page was not readable on a phone",
        "detail": ("The root index.html carried 12 header links and ~30 session cards before this "
                   "session. This build adds one phone-first executive summary at the top of the root "
                   "page that links straight to the picks, unresolved, sources, method and flagged "
                   "pages, and keeps the older desks below it as an archive."),
        "source": core.LOBBY_URL,
        "affected": [],
    })
    out.append({
        "id": "R6", "severity": "repo",
        "title": "Pre-existing test failures on the base commit",
        "detail": ("On the base commit a98242a, `python3 -m unittest discover -s tests` reports 1112 "
                   "tests with 1 failure and 16 errors (missing modules test_3faf40e8, test_5468b0ba, "
                   "test_58cb2600, test_5a40690b, test_6ffacd40, test_778756a1, test_94b3d48a, "
                   "test_98dcfc7e, test_dc741cc1, test_e1b48771, test_ff88c096, test_project, plus four "
                   "assertion errors in test_69e4c06a / test_current_lines and one in test_verify_7cd2e67a). "
                   "They are unrelated to this section and are recorded, not hidden."),
        "source": "https://github.com/buffedlizard55-lab/MaltaProj2/commit/a98242a9891a3ef2c44bc3df879711a53e5cd1a8",
        "affected": [],
    })
    return out


def main() -> int:
    board = build()
    core.dump_json(OUT, board)
    s = board["summary"]
    print(f"everypick board: {s['rows']} rows ({s['lobby_open']} lobby open, {s['api_only']} API-only) | "
          f"picks {s['with_pick']} | market {s['market']} | originated {s['originated_both_rated']} | "
          f"bound {s['originated_bound']} | unresolved {s['unresolved']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
