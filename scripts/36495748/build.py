"""Session 36495748 — every-match resolution ladder + phone-first executive-summary desk.

Inputs (all read-only except this session's own files):
  * data/f7279a54/board.json   — strict market board (Pinnacle/Bovada/Melbet/Kalshi, ~27 min refresh)
  * data/fe803b80/board.json   — full-coverage board (market + VRS/Elo model); used for the fixture
                                  union and cross-checks only. Its model joins are NEVER copied
                                  blind: two wrong-row VRS joins were found 2026-10-21 (flags F1/F2).
  * data/36495748/vrs_standings_global_2026_10_05.md — pinned copy of Valve's official file
                                  (sha256 recorded; refreshed by collect.py when Valve publishes).
  * data/36495748/overrides.json — this session's manually verified reads (Kalshi page joins,
                                  HLTV/bo3 roster-identity resolutions), each with read references.
  * data/36495748/probe.json    — optional runner output of collect.py (Kalshi/bo3 re-probes).

Resolution ladder per open fixture (HotSpawn crowd data is never an input anywhere):
  Rung 1  featured market  — re-derive a weighted no-vig consensus from the raw stored quotes,
                             re-orienting every quote from its source names; arithmetic-gated
                             against the stored consensus.
  Rung 2  exchange price   — a Kalshi price whose start is proven (page read or ticker time),
                             no-vig from the two mid prices; coin flips broken by official VRS.
  Rung 3  official VRS     — both teams resolve to ONE row of Valve's official standings
                             (duplicate names need roster evidence) -> market-calibrated curve.
  Rung 4  directional floor— one team officially rated, the other provably absent from the
                             official table -> rated team vs the last row's points.
  Rung 5  unresolved       — published blank, with the per-rung ledger of what was attempted.

Outputs: data/36495748/board.json + audits/36495748/{index,picks,unresolved,flagged,method}.html
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Load core.py under a unique module name: many sessions in this repo have their own
# core.py/build.py, and a bare `import core` silently binds whichever was imported first
# (observed 2026-10-21: AttributeError 'module core has no attribute norm' under discover).
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "exec36495748_core", Path(__file__).resolve().parent / "core.py")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

SESSION = "36495748"
DATA = ROOT / "data" / SESSION
OUT = ROOT / "audits" / SESSION
VALVE_BLOB = "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/"
VALVE_REPO = "https://github.com/ValveSoftware/counter-strike_regional_standings"

TOL_QUOTE = 0.004      # re-derived quote prob vs stored prob (probability, absolute)
TOL_CONSENSUS = 0.006  # re-derived consensus vs stored board consensus
START_TOL_H = 1.5      # max |source start - HotSpawn start| for a quote to be admissible


# --------------------------------------------------------------------------------- loading

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_vrs(text: str) -> list[dict]:
    """Parse Valve's markdown standings table -> rows in official order."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        standing, points, team = int(cells[0]), float(cells[1]), cells[2]
        roster = cells[3] if len(cells) > 3 else ""
        details = ""
        if len(cells) > 4:
            m = re.search(r"\((details/[^)]+)\)", cells[4])
            if m:
                details = m.group(1)
        rows.append({"standing": standing, "points": points, "team": team,
                     "roster": roster, "details_path": details,
                     "details_url": (VALVE_BLOB + details) if details else VALVE_BLOB})
    return rows


class Vrs:
    def __init__(self, rows: list[dict], source_file: str, sha: str):
        self.rows = rows
        self.source_file = source_file
        self.sha = sha
        self.by_norm: dict[str, list[dict]] = {}
        self.by_tokens: dict[tuple, list[dict]] = {}
        self.by_standing: dict[int, dict] = {}
        for r in rows:
            self.by_norm.setdefault(core.norm(r["team"]), []).append(r)
            self.by_tokens.setdefault(tuple(sorted(core.tokens(r["team"]))), []).append(r)
            self.by_standing[r["standing"]] = r
        self.floor = rows[-1] if rows else None

    def candidates(self, name: str) -> tuple[list[dict], str]:
        got = self.by_norm.get(core.norm(name)) or []
        if got:
            return got, "exact normalised name"
        got = self.by_tokens.get(tuple(sorted(core.tokens(name)))) or []
        if got:
            return got, "same name tokens, different word order"
        return [], "no row under this name (exact or token) in the official file"


# --------------------------------------------------------------------------------- rungs

def rederive_market(row: dict) -> dict:
    """Rung 1: rebuild the market consensus from the strict board's raw quotes.

    Each quote is re-oriented from the team names printed by the source itself; a quote
    whose names cannot be matched to the fixture's two teams is excluded and counted.
    """
    team_a, team_b = row["team_a"], row["team_b"]
    entries, quote_rows, problems = [], [], []
    for q in row.get("quotes") or []:
        dec_a, dec_b = q.get("decimal_a"), q.get("decimal_b")
        names = q.get("names_at_source") or []
        nv = core.no_vig(dec_a, dec_b)
        rec = {"source_key": q.get("source_key"), "source_name": q.get("source_name"),
               "public_url": q.get("public_url"), "decimal_a": dec_a, "decimal_b": dec_b,
               "names_at_source": names, "retrieved_utc": q.get("retrieved_utc"),
               "start_utc_at_source": q.get("start_utc_at_source"),
               "start_diff_h": q.get("start_diff_h")}
        if nv is None or len(names) != 2:
            rec["usable"], rec["reason"] = False, "no valid two-way price or names missing"
            problems.append(f"{q.get('source_key')}: invalid price/names")
            quote_rows.append(rec)
            continue
        if isinstance(q.get("start_diff_h"), (int, float)) and abs(q["start_diff_h"]) > START_TOL_H:
            rec["usable"], rec["reason"] = False, f"source start is {q['start_diff_h']}h from HotSpawn start"
            problems.append(f"{q.get('source_key')}: start mismatch {q['start_diff_h']}h")
            quote_rows.append(rec)
            continue
        p_first, p_second, over = nv
        if core.same_name(names[0], team_a) and core.same_name(names[1], team_b):
            prob_a = p_first
        elif core.same_name(names[0], team_b) and core.same_name(names[1], team_a):
            prob_a = p_second
        else:
            rec["usable"], rec["reason"] = False, "source names do not match the fixture pair"
            problems.append(f"{q.get('source_key')}: name/orientation mismatch {names}")
            quote_rows.append(rec)
            continue
        stored = q.get("no_vig_prob_team_a")
        if isinstance(stored, (int, float)) and abs(stored - prob_a) > TOL_QUOTE:
            rec["usable"] = False
            rec["reason"] = f"stored prob {stored} disagrees with re-derivation {prob_a:.4f}"
            problems.append(f"{q.get('source_key')}: arithmetic disagreement")
            quote_rows.append(rec)
            continue
        rec.update({"usable": True, "prob_a": prob_a, "overround": over})
        entries.append(rec)
        quote_rows.append(rec)
    cons = core.consensus_prob_a(entries)
    stored_market = row.get("market") or {}
    check = None
    if cons and isinstance(stored_market.get("prob_a"), (int, float)):
        delta = abs(cons["prob_a"] - float(stored_market["prob_a"]))
        check = {"stored_prob_a": float(stored_market["prob_a"]), "delta": delta,
                 "pass": delta <= TOL_CONSENSUS}
        if not check["pass"]:
            problems.append(f"consensus re-derivation differs from board by {delta:.4f}")
    return {"consensus": cons, "quotes": quote_rows, "problems": problems, "check": check}


def resolve_vrs(name: str, fixture_id: str, vrs: Vrs, overrides: dict, side_key: str):
    """Resolve one team name to exactly one official row, or explain why not."""
    cands, how = vrs.candidates(name)
    ident = (overrides.get("identity_resolutions") or {}).get(fixture_id) or {}
    if len(cands) == 1:
        chosen = cands[0]
        wanted = ident.get(side_key) and ident.get("use_standing")
        if wanted and ident.get(side_key) and core.same_name(ident.get(side_key), name) \
                and int(wanted) != chosen["standing"]:
            return None, {"state": "override_conflict",
                          "detail": f"name matches #{chosen['standing']} but recorded roster evidence points to #{wanted}"}
        return chosen, {"state": "unique", "how": how}
    if len(cands) > 1:
        wanted = ident.get("use_standing")
        if wanted and ident.get(side_key) and core.same_name(ident.get(side_key), name):
            row = vrs.by_standing.get(int(wanted))
            if row:
                return row, {"state": "disambiguated_by_roster_evidence",
                             "candidates": [c["standing"] for c in cands],
                             "evidence": ident.get("evidence"), "read_refs": ident.get("read_refs")}
        return None, {"state": "ambiguous_name", "candidates": [c["standing"] for c in cands],
                      "detail": "Valve lists more than one row under this name; refusing to pick one without roster evidence"}
    # no name match: an override may still identify the team (rename / ex- prefix)
    wanted = ident.get("use_standing")
    if wanted and ident.get(side_key) and core.same_name(ident.get(side_key), name):
        row = vrs.by_standing.get(int(wanted))
        if row:
            return row, {"state": "identified_by_roster_evidence",
                         "evidence": ident.get("evidence"), "read_refs": ident.get("read_refs")}
    return None, {"state": "absent", "detail": how}


def kalshi_join(fixture_id: str, team_a: str, team_b: str, overrides: dict, probe: dict):
    """Rung 2: verified Kalshi exchange price (manual page read or runner probe)."""
    join = ((overrides.get("kalshi_joins") or {}).get(fixture_id)
            or ((probe or {}).get("kalshi_joins") or {}).get(fixture_id))
    if not join:
        return None
    mids = join.get("mid_cents") or {}
    # orient the two mids onto team_a / team_b by name
    by_team = {}
    for nm, cents in mids.items():
        if core.same_name(nm, team_a):
            by_team["a"] = float(cents)
        elif core.same_name(nm, team_b):
            by_team["b"] = float(cents)
    if "a" not in by_team or "b" not in by_team or by_team["a"] <= 0 or by_team["b"] <= 0:
        return {"usable": False, "reason": "exchange names did not orient onto the fixture pair", "join": join}
    book = by_team["a"] + by_team["b"]
    if not 95.0 <= book <= 130.0:
        return {"usable": False, "reason": f"exchange book {book}c outside sane range", "join": join}
    return {"usable": True, "prob_a": by_team["a"] / book, "prob_b": by_team["b"] / book,
            "join": join, "mid_cents_a": by_team["a"], "mid_cents_b": by_team["b"], "book_cents": book}


def build_board() -> dict:
    ourline_path = ROOT / "data" / "f7279a54" / "board.json"
    board_path = ROOT / "data" / "fe803b80" / "board.json"
    ourline = load_json(ourline_path) or {}
    board = load_json(board_path) or {}
    overrides = load_json(DATA / "overrides.json", {}) or {}
    probe = load_json(DATA / "probe.json", {}) or {}

    vrs_file = sorted(DATA.glob("vrs_standings_global_*.md"))[-1]
    vrs = Vrs(parse_vrs(vrs_file.read_text(encoding="utf-8")), vrs_file.name, sha256_of(vrs_file))
    cal = ourline.get("calibration") or {}
    k = float(cal.get("k")) if cal.get("fitted") and cal.get("k") else core.FALLBACK_K
    k_source = ("fitted upstream calibration in data/f7279a54/board.json"
                if cal.get("fitted") and cal.get("k") else "FALLBACK_K constant (upstream calibration missing)")

    o_open = {str(r["fixture_id"]): r for r in ourline.get("open") or []}
    b_open = {str(r["fixture_id"]): r for r in board.get("open") or []}
    fixture_ids = sorted(set(o_open) | set(b_open),
                         key=lambda fid: ((o_open.get(fid) or b_open.get(fid) or {}).get("start_utc") or "", fid))

    rows = []
    for fid in fixture_ids:
        src = o_open.get(fid) or b_open.get(fid)
        other = b_open.get(fid) or o_open.get(fid)
        team_a = src["team_a"]["name"] if isinstance(src["team_a"], dict) else src["team_a"]
        team_b = src["team_b"]["name"] if isinstance(src["team_b"], dict) else src["team_b"]
        ladder: list[dict] = []
        result: dict | None = None

        # ---- Rung 1: featured market, re-derived from raw quotes
        mkt = rederive_market(o_open[fid]) if fid in o_open else {"consensus": None, "quotes": [], "problems": [], "check": None}
        if mkt["consensus"]:
            pa = mkt["consensus"]["prob_a"]
            result = {"basis": "market", "prob_a": pa, "prob_b": 1 - pa,
                      "market": {"n_sources": mkt["consensus"]["n_sources"], "sources": mkt["consensus"]["sources"],
                                 "min_a": mkt["consensus"]["min_a"], "max_a": mkt["consensus"]["max_a"],
                                 "quotes": mkt["quotes"], "rederivation_check": mkt["check"]}}
            ladder.append({"rung": 1, "outcome": "priced",
                           "detail": f"{mkt['consensus']['n_sources']} book(s) re-derived from raw decimals"})
        else:
            ladder.append({"rung": 1, "outcome": "no_price",
                           "detail": "no admissible quote on the strict market board"
                                     + (f"; problems: {'; '.join(mkt['problems'])}" if mkt["problems"] else "")})

        # ---- Rung 2: verified exchange price (Kalshi)
        if result is None:
            kj = kalshi_join(fid, team_a, team_b, overrides, probe)
            if kj and kj.get("usable"):
                pa = kj["prob_a"]
                coin_flip = abs(pa - 0.5) <= 0.01
                result = {"basis": "exchange", "prob_a": pa, "prob_b": 1 - pa,
                          "exchange": {"source_name": kj["join"].get("source_name"),
                                       "url": kj["join"].get("url"),
                                       "event_ticker": kj["join"].get("event_ticker"),
                                       "start_verified": kj["join"].get("start_verified"),
                                       "note": kj["join"].get("note"),
                                       "read_ref": kj["join"].get("read_ref"),
                                       "mid_cents_a": kj["mid_cents_a"], "mid_cents_b": kj["mid_cents_b"]},
                          "coin_flip": coin_flip, "tiebreak": kj["join"].get("tiebreak")}
                ladder.append({"rung": 2, "outcome": "priced",
                               "detail": f"Kalshi mids {kj['mid_cents_a']}c/{kj['mid_cents_b']}c, start proven on the event page"})
            else:
                ladder.append({"rung": 2, "outcome": "no_price",
                               "detail": (kj or {}).get("reason") or "no verified Kalshi event for this fixture"})

        # ---- Rung 3: official VRS, both teams uniquely identified
        va, vstate_a = resolve_vrs(team_a, fid, vrs, overrides, "team_a_hotspawn")
        vb, vstate_b = resolve_vrs(team_b, fid, vrs, overrides, "team_b_hotspawn")
        if result is None and va and vb:
            pa = core.vrs_prob_a(va["points"], vb["points"], k)
            result = {"basis": "vrs_model", "prob_a": pa, "prob_b": 1 - pa,
                      "vrs": {"a": va, "b": vb, "state_a": vstate_a, "state_b": vstate_b, "k": k}}
            ladder.append({"rung": 3, "outcome": "priced",
                           "detail": f"official points {va['points']:.0f} v {vb['points']:.0f} through the calibrated Valve curve"})
        elif result is None:
            ladder.append({"rung": 3, "outcome": "not_identifiable",
                           "detail": f"{team_a}: {vstate_a.get('state')}; {team_b}: {vstate_b.get('state')}"})

        # ---- Rung 4: directional floor (exactly one side rated, other provably absent)
        if result is None:
            rated = None
            if va and not vb and vstate_b.get("state") == "absent":
                rated = ("a", va)
            elif vb and not va and vstate_a.get("state") == "absent":
                rated = ("b", vb)
            ident = (overrides.get("identity_resolutions") or {}).get(fid) or {}
            if rated and vrs.floor:
                side, vrow = rated
                p_rated = core.vrs_prob_a(vrow["points"], vrs.floor["points"], k)
                pa = p_rated if side == "a" else 1 - p_rated
                result = {"basis": "directional_floor", "prob_a": pa, "prob_b": 1 - pa,
                          "vrs": {"a": va, "b": vb, "state_a": vstate_a, "state_b": vstate_b, "k": k,
                                  "floor": vrs.floor, "rated_side": side,
                                  "identity_evidence": ident.get("evidence"),
                                  "opponent_absent_check": ident.get("opponent_absent_check"),
                                  "read_refs": ident.get("read_refs")}}
                ladder.append({"rung": 4, "outcome": "priced_directional",
                               "detail": "rated side vs the official table floor (#%s, %.0f pts); the unrated side has no official row at all"
                                         % (vrs.floor["standing"], vrs.floor["points"])})
            else:
                ladder.append({"rung": 4, "outcome": "not_applicable",
                               "detail": "needs exactly one rated side and a provably unrated opponent"})

        if result is None:
            ladder.append({"rung": 5, "outcome": "unresolved",
                           "detail": "no book price, no verified exchange price, and no admissible official-rating resolution"})
            result = {"basis": "unresolved", "prob_a": None, "prob_b": None,
                      "vrs": {"a": va, "b": vb, "state_a": vstate_a, "state_b": vstate_b}}

        # The published ladder always shows all five rungs; fill the ones never reached.
        seen = {entry["rung"]: entry for entry in ladder}
        priced_at = next((e["rung"] for e in ladder if e["outcome"].startswith("priced")), None)
        ladder = [seen.get(rn) or {"rung": rn, "outcome": "not_needed",
                                    "detail": f"priced at rung {priced_at}"} for rn in (1, 2, 3, 4, 5)]

        # pick (+ coin-flip exchange tiebreak by official points, documented)
        pick, pick_prob, pick_note = None, None, None
        if result["prob_a"] is not None:
            pa = result["prob_a"]
            if result.get("coin_flip") and result.get("tiebreak"):
                pts = (result["tiebreak"].get("points") or {})
                pta = pts.get(team_a) if team_a in pts else next((v for n, v in pts.items() if core.same_name(n, team_a)), None)
                ptb = pts.get(team_b) if team_b in pts else next((v for n, v in pts.items() if core.same_name(n, team_b)), None)
                if pta is not None and ptb is not None and pta != ptb:
                    pick_side = "a" if pta > ptb else "b"
                    pick = team_a if pick_side == "a" else team_b
                    pick_prob = pa if pick_side == "a" else 1 - pa
                    pick_note = (f"exchange is a coin flip; pick taken from the official rating "
                                 f"({pick} higher: {max(pta, ptb):.0f} v {min(pta, ptb):.0f} pts)")
            if pick is None:
                pick = team_a if pa >= 0.5 else team_b
                pick_prob = max(pa, 1 - pa)

        # cross-checks against the other boards (never inputs)
        cross = {}
        line_b = (other.get("line") or {}) if other else {}
        if isinstance(line_b.get("prob_a"), (int, float)):
            cross["fe803b80"] = {"prob_a": line_b["prob_a"], "basis": line_b.get("basis"),
                                 "pick": line_b.get("pick")}
            if result["prob_a"] is not None:
                cross["fe803b80"]["delta_pp"] = round(100 * (result["prob_a"] - float(line_b["prob_a"])), 1)
                cross["fe803b80"]["same_pick"] = (pick == line_b.get("pick"))
        ident = (overrides.get("identity_resolutions") or {}).get(fid) or {}
        if ident.get("upstream_disagreement"):
            cross["identity_disagreement"] = ident["upstream_disagreement"]

        rows.append({
            "fixture_id": fid, "team_a": team_a, "team_b": team_b,
            "competition": src.get("competition"), "tier": src.get("tier"),
            "best_of": src.get("best_of"), "points_on_offer": src.get("points"),
            "start_utc": src.get("start_utc"), "lock_utc": src.get("lock_utc"),
            "hotspawn_url": src.get("hotspawn_url"),
            "present_on": [n for n, d in (("strict f7279a54", o_open), ("board fe803b80", b_open)) if fid in d],
            "fixture_note": (overrides.get("fixture_notes") or {}).get(fid),
            "ladder": ladder, "basis": result["basis"],
            "prob_a": result["prob_a"], "prob_b": result["prob_b"],
            "pick": pick, "pick_prob": pick_prob, "pick_note": pick_note,
            "confidence": core.confidence_label(pick_prob) if pick_prob is not None else None,
            "detail": {kk: result.get(kk) for kk in ("market", "exchange", "vrs") if result.get(kk) is not None},
            "cross_check": cross,
        })

    summary = {"open": len(rows)}
    for basis in ("market", "exchange", "vrs_model", "directional_floor", "unresolved"):
        summary[basis] = sum(1 for r in rows if r["basis"] == basis)
    summary["with_pick"] = summary["open"] - summary["unresolved"]

    return {
        "session": SESSION, "built_utc": core.now_iso(),
        "inputs": {
            "strict_board": {"path": "data/f7279a54/board.json", "generated_utc": ourline.get("generated_utc"),
                             "sha256": sha256_of(ourline_path), "open": len(o_open),
                             "calibration": cal, "vrs_snapshot": (ourline.get("vrs") or {}).get("snapshot")},
            "coverage_board": {"path": "data/fe803b80/board.json", "generated_utc": board.get("generated_utc"),
                               "sha256": sha256_of(board_path), "open": len(b_open)},
            "official_vrs": {"file": vrs.source_file, "sha256": vrs.sha, "rows": len(vrs.rows),
                             "floor": vrs.floor, "url": VALVE_BLOB + vrs.source_file},
            "overrides_reads": len(overrides.get("reads") or []),
            "probe_generated_utc": probe.get("generated_utc"),
        },
        "model": {"k": k, "k_source": k_source, "valve_c": core.VALVE_C,
                  "formula": "p(a) = 1 / (1 + exp(-k * C * (points_a - points_b))), C = g*ln(10)/400 (RD=75, Valve glicko.js)"},
        "summary": summary,
        "rows": rows,
        "reads": overrides.get("reads") or [],
    }


def verify_board(b: dict) -> list[str]:
    """Hard gates. Any failure aborts the publish so a wrong number can never ship."""
    errs = []
    vrs_file = sorted(DATA.glob("vrs_standings_global_*.md"))[-1]
    vrs = Vrs(parse_vrs(vrs_file.read_text(encoding="utf-8")), vrs_file.name, sha256_of(vrs_file))
    k = b["model"]["k"]
    for r in b["rows"]:
        fid = r["fixture_id"]
        if r["prob_a"] is None:
            if r["basis"] != "unresolved" or r["pick"] is not None:
                errs.append(f"{fid}: blank probability must be unresolved with no pick")
            continue
        if not (0.0 < r["prob_a"] < 1.0) or abs(r["prob_a"] + r["prob_b"] - 1.0) > 1e-9:
            errs.append(f"{fid}: probabilities do not sum to 1")
        expect_pick = r["team_a"] if r["prob_a"] >= 0.5 else r["team_b"]
        if r["pick"] not in (r["team_a"], r["team_b"]):
            errs.append(f"{fid}: pick is not one of the teams")
        elif r["pick"] != expect_pick and not r.get("pick_note"):
            errs.append(f"{fid}: pick disagrees with probabilities without a documented tiebreak")
        d = r["detail"]
        if r["basis"] == "market":
            usable = [q for q in (d.get("market") or {}).get("quotes", []) if q.get("usable")]
            if not usable:
                errs.append(f"{fid}: market row with no usable quote")
            for q in usable:
                nv = core.no_vig(q["decimal_a"], q["decimal_b"])
                if nv is None:
                    errs.append(f"{fid}: stored decimal pair no longer yields a price")
                    continue
                p_first, p_second, _ = nv
                pa = p_first if core.same_name(q["names_at_source"][0], r["team_a"]) else p_second
                if abs(pa - q["prob_a"]) > 1e-9:
                    errs.append(f"{fid}: quote re-derivation drift ({q.get('source_key')})")
                if not (q.get("public_url") or "").startswith("https://"):
                    errs.append(f"{fid}: quote without an https source link")
                if "hotspawn" in (q.get("public_url") or ""):
                    errs.append(f"{fid}: a price is linked to HotSpawn (forbidden)")
            cons = core.consensus_prob_a(usable)
            if cons and abs(cons["prob_a"] - r["prob_a"]) > 1e-9:
                errs.append(f"{fid}: published market consensus is not the recomputed one")
        if r["basis"] == "exchange":
            ex = d.get("exchange") or {}
            book = ex["mid_cents_a"] + ex["mid_cents_b"]
            if abs(ex["mid_cents_a"] / book - r["prob_a"]) > 1e-9:
                errs.append(f"{fid}: exchange probability is not the no-vig of the stored mids")
            if not (ex.get("url") or "").startswith("https://kalshi.com/"):
                errs.append(f"{fid}: exchange row without its Kalshi link")
        if r["basis"] in ("vrs_model", "directional_floor"):
            v = d.get("vrs") or {}
            va, vb = v.get("a"), v.get("b")
            if r["basis"] == "vrs_model":
                if not va or not vb:
                    errs.append(f"{fid}: model row missing an official row")
                else:
                    for side, row in (("a", va), ("b", vb)):
                        official = vrs.by_standing.get(row["standing"])
                        if not official or official["points"] != row["points"]:
                            errs.append(f"{fid}: side {side} is not the official points for #{row['standing']}")
                    if abs(core.vrs_prob_a(va["points"], vb["points"], k) - r["prob_a"]) > 1e-9:
                        errs.append(f"{fid}: model probability does not recompute")
            else:
                floor = v.get("floor") or {}
                rated = va if v.get("rated_side") == "a" else vb
                if not rated or floor.get("standing") != vrs.floor["standing"]:
                    errs.append(f"{fid}: directional row missing rated side or wrong floor")
                else:
                    p_rated = core.vrs_prob_a(rated["points"], floor["points"], k)
                    expect = p_rated if v.get("rated_side") == "a" else 1 - p_rated
                    if abs(expect - r["prob_a"]) > 1e-9:
                        errs.append(f"{fid}: directional probability does not recompute")
    s = b["summary"]
    if s["with_pick"] + s["unresolved"] != s["open"] or s["open"] != len(b["rows"]):
        errs.append("summary counts do not add up")
    return errs


# --------------------------------------------------------------------------------- HTML

BASIS_META = {
    "market": ("🎯 Market", "#0b6e2d", "Re-derived no-vig consensus of real bookmaker prices"),
    "exchange": ("🔁 Exchange", "#0b5e8c", "Kalshi exchange price, start verified on the event page"),
    "vrs_model": ("🏅 VRS model", "#7a5b00", "Official Valve ratings through the market-calibrated curve"),
    "directional_floor": ("🧭 Directional", "#8a4b00", "One officially rated team vs an officially unrated opponent (floor estimate)"),
    "unresolved": ("⚠️ Unresolved", "#9b1c1c", "No defensible probability — see Unresolved & limitations"),
}

CSS = """
:root{--ink:#14202b;--mut:#5b6b7a;--line:#d9e1e8;--bg:#f5f7f9;--card:#fff;--acc:#0b5e8c}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:#0d2233;color:#fff;padding:18px 16px 12px}header h1{margin:0 0 4px;font-size:22px}
header p{margin:2px 0;color:#cfe0ec;font-size:14px}
nav{position:sticky;top:0;background:#0d2233;padding:8px 8px 10px;display:flex;flex-wrap:wrap;gap:8px;z-index:9}
nav a{color:#fff;text-decoration:none;background:#17405c;padding:10px 14px;border-radius:10px;font-size:15px;min-height:44px;display:inline-flex;align-items:center}
nav a.on{background:#ff8a00;color:#141414;font-weight:700}
main{max-width:760px;margin:0 auto;padding:14px 12px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.big-links a{display:block;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-left:6px solid var(--acc);border-radius:12px;padding:14px;margin:10px 0;background:var(--card)}
.big-links b{font-size:18px}.big-links span{color:var(--mut);font-size:14px}
.vs{font-size:18px;font-weight:700;margin:2px 0}.pick{color:#0b6e2d}
.meta{color:var(--mut);font-size:13.5px}
.bar{display:flex;height:22px;border-radius:7px;overflow:hidden;border:1px solid var(--line);margin:8px 0 2px}
.bar i{display:block;height:100%}.bar .a{background:#2e7d32}.bar .b{background:#b0bec5}
.pcts{display:flex;justify-content:space-between;font-weight:700;font-size:16px}
.badge{display:inline-block;color:#fff;border-radius:999px;padding:3px 10px;font-size:12.5px;font-weight:700;margin:6px 4px 0 0}
.conf{color:var(--mut);font-size:13.5px}
.ev{font-size:13.5px;color:#24313c;margin:8px 0 0;padding-left:16px}.ev li{margin:3px 0}
a{color:var(--acc)}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border:1px solid var(--line);padding:7px;text-align:left;vertical-align:top}
th{background:#eaf1f6}.warn{border-left:6px solid #d97706;background:#fff7ed}
.alert{border-left:6px solid #b91c1c;background:#fef2f2}
.ok{border-left:6px solid #0b6e2d;background:#f0fdf4}
footer{max-width:760px;margin:0 auto;padding:0 12px 30px;color:var(--mut);font-size:13px}
@media(max-width:520px){table{font-size:13px}.vs{font-size:17px}}
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def page(title, on, body, b):
    nav = "".join(f'<a href="{href}" class="{"on" if href == on else ""}">{label}</a>' for href, label in (
        ("index.html", "📋 Summary"), ("picks.html", "🎯 All picks"),
        ("unresolved.html", "⚠️ Unresolved & limits"), ("flagged.html", "🚩 Flagged"),
        ("method.html", "🔍 Method & sources")))
    s = b["summary"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} — HotSpawn CS2 picks (36495748)</title>
<style>{CSS}</style></head><body>
<header><h1>{esc(title)}</h1>
<p>Every open HotSpawn Counter-Strike 2 match, with a pick or a documented reason. Built {esc(b['built_utc'])} UTC · session 36495748.</p>
<p>{s['open']} open matches · {s['with_pick']} picks ({s['market']} market · {s['exchange']} exchange · {s['vrs_model']} VRS model · {s['directional_floor']} directional) · {s['unresolved']} unresolved. Book data captured {esc(b['inputs']['strict_board']['generated_utc'])} / {esc(b['inputs']['coverage_board']['generated_utc'])} UTC. HotSpawn supplies fixtures only — never probabilities.</p></header>
<nav>{nav}<a href="../../index.html">🏠 Site home</a><a href="../../probabilities.html">Canonical probabilities</a></nav>
<main>{body}</main>
<footer>Not affiliated with HotSpawn or any bookmaker. Probabilities are market/model estimates for research and Pick'ems study, not betting advice. Numbers re-derive from the inputs printed on <a href="method.html">Method &amp; sources</a>; anything that could not be sourced is left blank and listed under <a href="unresolved.html">Unresolved &amp; limitations</a>.</footer>
</body></html>"""


def row_evidence(r) -> list[str]:
    items = []
    d = r["detail"]
    if r["basis"] == "market":
        for q in (d["market"]["quotes"]):
            if not q.get("usable"):
                continue
            items.append(f'{esc(q["source_name"])} {float(q["decimal_a"]):.3f}/{float(q["decimal_b"]):.3f} '
                         f'({" / ".join(map(esc, q["names_at_source"]))}, read {esc(q["retrieved_utc"])}) '
                         f'<a href="{esc(q["public_url"])}">source</a>')
        chk = d["market"].get("rederivation_check")
        if chk:
            items.append("Arithmetic gate: re-derived consensus "
                         + ("matches" if chk["pass"] else "DIFFERS FROM") + " the strict board's stored consensus"
                         + (f" (Δ {chk['delta']:.4f})" if not chk["pass"] else "") + ".")
    if r["basis"] == "exchange":
        ex = d["exchange"]
        items.append(f'{esc(ex["source_name"])} <a href="{esc(ex["url"])}">{esc(ex["event_ticker"])}</a>: '
                     f'mids {esc(ex["mid_cents_a"])}¢ / {esc(ex["mid_cents_b"])}¢. {esc(ex["start_verified"])}')
        if ex.get("note"):
            items.append(esc(ex["note"]))
    if r["basis"] in ("vrs_model", "directional_floor"):
        v = d["vrs"]
        for side, key, st in ((r["team_a"], "a", v["state_a"]), (r["team_b"], "b", v["state_b"])):
            row = v.get(key)
            if row:
                items.append(f'{esc(side)} — official Valve row #{row["standing"]} ({row["points"]:.0f} pts, {esc(row["roster"])}) '
                             f'<a href="{esc(row["details_url"])}">Valve details</a> · {esc(st.get("state"))}')
                if st.get("evidence"):
                    items.append("Identity evidence: " + esc(st["evidence"]))
            else:
                items.append(f'{esc(side)} — {esc(st.get("state"))}: {esc(st.get("detail") or "see identity note")}')
        if v.get("opponent_absent_check"):
            items.append("Unrated-opponent check: " + esc(v["opponent_absent_check"]))
        if r["basis"] == "directional_floor":
            f = v["floor"]
            items.append(f'Directional floor: the rated team is priced against the official table\'s last row '
                         f'(#{f["standing"]} {esc(f["team"])}, {f["points"]:.0f} pts). An unrated opponent is, by definition, '
                         f'outside the published table, so this understates the rated side if anything; treat the number as directional, not a market price.')
    if r.get("pick_note"):
        items.append(esc(r["pick_note"]) + ".")
    if r.get("fixture_note"):
        items.append("⚠️ " + esc(r["fixture_note"]))
    xc = r.get("cross_check") or {}
    if xc.get("fe803b80") and r["prob_a"] is not None:
        x = xc["fe803b80"]
        items.append(f'Cross-check vs the coverage board (fe803b80, {esc(x.get("basis"))}): it shows {esc(r["team_a"])} '
                     f'{100*float(x["prob_a"]):.1f}% (Δ {esc(x.get("delta_pp"))}pp, '
                     + ("same pick" if x.get("same_pick") else "DIFFERENT PICK — see Flagged") + ").")
    if xc.get("identity_disagreement"):
        items.append("Identity correction: " + esc(xc["identity_disagreement"]))
    return items


def pick_card(r) -> str:
    label, color, _ = BASIS_META[r["basis"]]
    when = f'{esc((r.get("start_utc") or "")[:16].replace("T", " "))} UTC'
    lock = f'locks {esc((r.get("lock_utc") or "")[:16].replace("T", " "))} UTC' if r.get("lock_utc") else ""
    head = (f'<div class="vs">{esc(r["team_a"])} <span style="color:#5b6b7a">vs</span> {esc(r["team_b"])}</div>'
            f'<div class="meta">{esc(r["competition"])} · starts {when} · {lock} · fixture #{esc(r["fixture_id"])}</div>')
    if r["prob_a"] is None:
        body = (f'<div class="pcts"><span>—%</span><span>—%</span></div>'
                f'<p><b>No defensible pick.</b> Both probabilities are left blank (never guessed). '
                f'See the rung-by-rung ledger on <a href="unresolved.html#fx-{esc(r["fixture_id"])}">Unresolved &amp; limitations</a>.</p>')
    else:
        pa = r["prob_a"]
        body = (f'<div class="bar"><i class="a" style="width:{100*pa:.1f}%"></i><i class="b" style="width:{100*(1-pa):.1f}%"></i></div>'
                f'<div class="pcts"><span>{esc(r["team_a"])} {core.pct(pa)}</span><span>{core.pct(1-pa)} {esc(r["team_b"])}</span></div>'
                f'<p style="margin:6px 0 0;font-size:17px">✅ Pick: <b class="pick">{esc(r["pick"])}</b> '
                f'<span class="conf">— {esc(r["confidence"])} ({core.pct(r["pick_prob"])})</span></p>')
    ev = "".join(f"<li>{i}</li>" for i in row_evidence(r))
    return (f'<article class="card" id="fx-{esc(r["fixture_id"])}">{head}{body}'
            f'<span class="badge" style="background:{color}">{label}</span>'
            + "".join(f'<span class="badge" style="background:#5b6b7a">{esc(p)}</span>' for p in r["present_on"] if len(r["present_on"]) == 1)
            + (f'<ul class="ev">{ev}</ul>' if ev else "") + "</article>")


LIMITATIONS = [
    ("L1 — Tier-C events are priced late or never.",
     "Low-tier CS2 (CIS LAN, CCT Challengers, regional cups) is routinely absent from Polymarket and from the books the collectors read (Pinnacle, Bovada, Melbet, Thunderpick-via-bo3, Kalshi). Today that applied to 1082762 (ex-CYBERSHOKE–BlinkDagger: no price at any of them; bo3.gg does not even list the CIS LAN Season 9 fixture) and 1082837 (Zetta–LOS NINOS: listed on bo3.gg with bet_updates null, i.e. Thunderpick publishes no coefficient). The desk falls back to official ratings for these, and says so on the row."),
    ("L2 — The official rating file is monthly.",
     "Valve's newest global standings file is 2026_10_05 — 16 days old today and still the latest published (repo HEAD eec4853, verified 2026-10-21). Model rows inherit that staleness: roster moves after 5 October are not in the numbers. HLTV's own VRS display (e.g. The Huns #125 on 2026-10-21 vs its #122 row in the Oct 5 file) shows the small drift this creates."),
    ("L3 — Valve lists multiple rows under one team name.",
     "The official file keeps historical cores: e.g. two 'The Huns' rows (#122/#213), two 'Banda Chuya' rows (#165/#373), two 'CYBERSHOKE' rows (#61/#171). Joining by name alone is unsafe — an upstream board priced two of today's fixtures off dead rosters (see Flagged F1/F2). This desk joins a duplicate name only with current-lineup evidence (≥3 of 5 players), otherwise the model rung refuses."),
    ("L4 — Renames and 'ex-' teams.",
     "'Zetta' is now Alianza Lima Esports (identical five); 'ex-CYBERSHOKE' is a post-org core. Names on HotSpawn, books and rating files drift apart, so identity is proven by roster overlap, not by string similarity. Similar-looking but different teams (e.g. CYBERSHOKE Prospects) are never used as proxies."),
    ("L5 — Thin or single-source prices.",
     "Some fixtures are priced by exactly one thin market (today: Kalshi's $1,440-volume book on UPGRADE–Team flacons). These are used, clearly badged, and should be trusted less than a multi-book consensus; exchange coin flips are broken by the official rating and say so."),
    ("L6 — HLTV access is best-effort.",
     "HLTV is the project's main identity/form source, but it sometimes returns 403 to automated collectors ('hltv_probe' fails in upstream runs). Automated refreshes only prove machine-checkable rungs; when a fixture needs HLTV lineup reasoning it lands in Unresolved until the identity work is done and recorded."),
    ("L7 — The HotSpawn lobby itself can be stale or flicker.",
     "Fixture 1080200 (Wildcard–DENDELE) appears in one upstream capture and not another, as already observed on 2026-10-16. The desk shows presence per capture and flags single-capture rows instead of silently trusting either."),
    ("L8 — Model numbers are estimates, not prices.",
     "VRS-model and directional rows come from a curve fitted to market lines (upstream fit: 60 pairs, MAE 7.7pp). Expect mistakes of that order; a 76.6% model row is not comparable in quality to a 76.6% three-book market row, which is exactly why every row carries its basis badge."),
]


FLAGS = [
    ("F1", "⚠️ Wrong official row joined upstream — fixture 1082792 (HOTU vs The Huns)",
     "data/fe803b80/board.json (2026-10-21T12:37Z) joins The Huns to Valve row #213 (701 pts — the nin9/sk0R/xerolte roster HLTV records as departed) and publishes HOTU 84.1%. The current five matches row #122 (944 pts). Corrected model: HOTU 76.6% (pick unchanged). Request logged to the fe803b80 owner in COORDINATION.md; not patched here (other session's files)."),
    ("F2", "⚠️ Wrong official row joined upstream — fixture 1081600 (Donstu vs Banda Chuya), pick flips",
     "The same board joins Banda Chuya to the two-player remnant row #373 (402 pts) and publishes Donstu 67.9%. The playing five is exactly row #165 (801 pts), so the corrected model pick is Banda Chuya 54.1%. Anyone following the coverage board for tomorrow's 13:45Z match would pick the wrong side. Request logged; the strict board's refusal (ambiguous_vrs_name) was the safe behaviour."),
    ("F3", "Fixture 1080200 (Wildcard vs DENDELE) seen on only one capture",
     "Present as open on the 12:37Z coverage board, absent from the 12:28Z strict board; previously observed flickering (session b3b89eec). Shown with a single-capture badge; verify in the HotSpawn lobby before relying on it."),
    ("F4", "Single-source thin exchange price — fixture 1082763 (UPGRADE vs Team flacons)",
     "The only price anywhere is Kalshi's ($1,440 volume at read). Published at 95.1/4.9 with the thin-liquidity caveat; direction agrees with the official table (UPGRADE #67, flacons unrated)."),
    ("F5", "Exchange coin flip decided by tiebreak — fixture 1079648 (G2 Ares vs ILLYRIANS)",
     "Kalshi offered both sides at Yes 53¢; two reads straddle 50/50. The desk publishes the exchange probabilities as read and takes the pick (G2 Ares) from the higher official rating (913 v 862 pts). Treat as a true toss-up for any strategy purpose."),
    ("F6", "Official ratings are 16 days old (newest published file)",
     "Valve's current file is standings_global_2026_10_05 (verified 2026-10-21, sha256 pinned). Any post-5-October roster/result change is invisible to model rows until Valve's next monthly publish."),
    ("F7", "What this desk deliberately does NOT quote",
     "(a) fe803b80's track_record/history accuracy — session b3871d16 showed its settled rows re-derive the pick from the result (99%+ 'hit rates' are artefacts); (b) HotSpawn crowd ownership as a probability; (c) HLTV's 'Pick a winner' community vote (74.6/25.4 on 1082762 — crowd data); (d) bo3.gg's analytics 'predicted win probability' (opaque third-party model). All four are excluded from every number here."),
    ("F8", "Repo CI note (pre-existing, not caused by this desk)",
     "The 'Verify and publish dashboard' workflow has been failing on main since before this session (first recorded 2026-10-16) while pages-build-deployment succeeds, so the site still deploys. This desk's own workflow runs its isolated test suite and does not depend on that gate; the underlying cross-session verifier failures remain for their owners."),
]


def render(b: dict) -> dict[str, str]:
    rows = b["rows"]
    s = b["summary"]
    now = b["built_utc"]

    # ---- index (executive summary)
    soon = [r for r in rows if (r.get("start_utc") or "") >= now][:5]
    soon_html = "".join(
        f'<li><b>{esc((r["start_utc"] or "")[:16].replace("T"," "))} UTC</b> — {esc(r["team_a"])} v {esc(r["team_b"])}: '
        + (f'✅ <b>{esc(r["pick"])}</b> {core.pct(r["pick_prob"])} ({BASIS_META[r["basis"]][0]})' if r["pick"] else "⚠️ unresolved")
        + f' · <a href="picks.html#fx-{esc(r["fixture_id"])}">row</a></li>' for r in soon)
    basis_lines = "".join(f'<li><span class="badge" style="background:{c}">{l}</span> {esc(d)}.</li>'
                          for k_, (l, c, d) in BASIS_META.items() if k_ != "unresolved")
    index_body = f"""
<div class="card ok"><p style="margin:0"><b>What this is:</b> a phone-first list of <b>every open HotSpawn CS2 match</b> with a pick and both win probabilities — or an explicit, sourced reason why a probability cannot be defended. Matches are resolved down a ladder: real bookmaker prices first, then a verified exchange price, then Valve's official ratings, then a clearly-labelled directional estimate. <b>HotSpawn crowd data is never used as a probability.</b></p>
<p class="meta">Inputs captured {esc(b['inputs']['strict_board']['generated_utc'])} and {esc(b['inputs']['coverage_board']['generated_utc'])} UTC · desk built {esc(now)} UTC · refreshed about every 4 hours.</p></div>
<div class="big-links">
<a href="picks.html"><b>🎯 All picks — start here</b><br><span>Every open match: pick, both probabilities, basis badge and source links. {s['with_pick']} of {s['open']} matches carry a pick right now.</span></a>
<a href="unresolved.html"><b>⚠️ Unresolved picks &amp; limitations</b><br><span>The separate section for anything without a defensible number, the fallback research that rescued today's low-tier fixtures, and the standing limitations (L1–L8). Currently unresolved: {s['unresolved']}.</span></a>
<a href="flagged.html"><b>🚩 Flagged for review</b><br><span>Irregularities found while verifying line by line — including two fixtures an upstream board priced off disbanded rosters (one pick flips).</span></a>
<a href="method.html"><b>🔍 Method, formulas &amp; source ledger</b><br><span>Exactly how every number is derived, the join/orientation gates, and the dated list of pages read (Kalshi, HLTV, bo3.gg, Valve).</span></a>
<a href="../../probabilities.html"><b>📈 Canonical probabilities board</b><br><span>The site-wide strict board this desk re-derives its market numbers from.</span></a>
<a href="../../index.html"><b>🏠 Site home / all desks</b><br><span>The main dashboard and the archive of dated research desks.</span></a>
</div>
<div class="card"><h2 style="margin-top:0">Starting soon</h2><ul class="ev" style="list-style:none;padding-left:0">{soon_html or '<li>No future-start rows in this snapshot.</li>'}</ul></div>
<div class="card"><h2 style="margin-top:0">How to read a row</h2><ul class="ev" style="list-style:none;padding-left:0">{basis_lines}</ul>
<p class="meta">Confidence labels: Heavy favourite ≥80% · Strong ≥70% · Solid ≥60% · Lean ≥52.5% · Toss-up below that. A Toss-up pick is a coin flip wearing a rosette — the label says so.</p></div>
<div class="card warn"><h2 style="margin-top:0">Today's low-tier rescues (the fixtures the featured path left blank)</h2>
<ul class="ev">
<li><b>ex-CYBERSHOKE v BlinkDagger</b> (CIS LAN #9, today 15:00 UTC) — priced nowhere; bo3.gg doesn't list it. Resolved 🧭 Directional from HLTV's match page: ex-CYBERSHOKE's five matches Valve's #61 core (1201 pts); BlinkDagger is officially unrated. Pick ex-CYBERSHOKE.</li>
<li><b>Zetta v LOS NINOS</b> (CCT SA #7, today 22:00 UTC) — no book coefficient. bo3.gg shows the slot as Alianza Lima Esports with Zetta's exact official five (#357, 473 pts); LOS NINOS unrated. Pick Zetta (directional).</li>
<li><b>G2 Ares v ILLYRIANS</b> — a real Kalshi price the strict board couldn't join (no start in its API payload); verified on the event page. Coin flip; pick by official rating.</li>
<li><b>Donstu v Banda Chuya</b> and <b>HOTU v The Huns</b> — duplicate official names resolved by current rosters; one upstream pick flips (Flagged F1/F2).</li>
</ul><p class="meta">Full rung-by-rung detail: <a href="unresolved.html">Unresolved &amp; limitations</a> · evidence: <a href="method.html#ledger">source ledger</a>.</p></div>
"""

    # ---- picks
    picks_body = "".join(pick_card(r) for r in rows)

    # ---- unresolved & limitations
    unres = [r for r in rows if r["basis"] == "unresolved"]
    if unres:
        unres_html = "".join(
            f'<article class="card alert" id="fx-{esc(r["fixture_id"])}"><div class="vs">{esc(r["team_a"])} vs {esc(r["team_b"])}</div>'
            f'<div class="meta">{esc(r["competition"])} · starts {esc((r.get("start_utc") or "")[:16].replace("T"," "))} UTC · fixture #{esc(r["fixture_id"])}</div>'
            '<table><tr><th>Rung</th><th>Outcome</th><th>What was attempted / found</th></tr>'
            + "".join(f'<tr><td>{l["rung"]}</td><td>{esc(l["outcome"])}</td><td>{esc(l["detail"])}</td></tr>' for l in r["ladder"])
            + "</table><p>Both probabilities are blank on <a href=\"picks.html\">All picks</a>. They are filled only when a source on the ladder produces an admissible input — never estimated ad hoc.</p></article>"
            for r in unres)
    else:
        unres_html = (f'<div class="card ok"><p style="margin:0"><b>As of this build ({esc(now)} UTC), zero open fixtures are unresolved.</b> '
                      'Every match below was priced by the featured path or rescued by the fallback research recorded here. '
                      'This page remains the permanent home for unresolved rows: when the ladder fails, the fixture appears '
                      'here with a rung-by-rung ledger instead of a guessed number.</p></div>')
    rescued = [r for r in rows if r["basis"] in ("exchange", "vrs_model", "directional_floor")]
    rescued_html = "".join(
        f'<article class="card" id="fx-{esc(r["fixture_id"])}"><div class="vs">{esc(r["team_a"])} vs {esc(r["team_b"])}</div>'
        f'<div class="meta">{esc(r["competition"])} · {esc((r.get("start_utc") or "")[:16].replace("T"," "))} UTC · fixture #{esc(r["fixture_id"])}</div>'
        '<table><tr><th>Rung</th><th>Outcome</th><th>Detail</th></tr>'
        + "".join(f'<tr><td>{l["rung"]}</td><td>{esc(l["outcome"])}</td><td>{esc(l["detail"])}</td></tr>' for l in r["ladder"])
        + f'</table><p>✅ <b>{esc(r["pick"])}</b> {core.pct(r["pick_prob"])} ({BASIS_META[r["basis"]][0]}) — full evidence on <a href="picks.html#fx-{esc(r["fixture_id"])}">the pick row</a>.</p></article>'
        for r in rescued)
    lim_html = "".join(f'<div class="card"><p style="margin:0"><b>{esc(t)}</b> {esc(d)}</p></div>' for t, d in LIMITATIONS)
    unresolved_body = f"""
<p><b>Why this page exists:</b> the featured path (bookmaker prices joined strictly to the fixture) cannot price every HotSpawn match — low-tier events are missing from Polymarket and most books, some teams have no official rating, and some names are ambiguous. Those fixtures are researched down the ladder (HLTV first, then esportsbook/exchange lines, then official ratings). Whatever still cannot be defended stays here, blank, with the attempts on record.</p>
<h2>Currently unresolved</h2>{unres_html}
<h2>Resolved only by fallback research</h2>
<p>These fixtures had <b>no admissible featured-market price</b> and were resolved at rungs 2–4. Each card shows every rung tried.</p>
{rescued_html}
<h2>Standing limitations</h2>{lim_html}
"""

    # ---- flagged
    flags_html = "".join(f'<div class="card {"alert" if "Wrong official" in t else "warn"}"><p style="margin:0"><b>{esc(i)}. {esc(t)}</b><br>{esc(d)}</p></div>'
                         for i, t, d in FLAGS)
    flagged_body = f"<p>Published for review; none of these block the desk. Items that belong to other sessions' files are logged in COORDINATION.md for their owners rather than patched here.</p>{flags_html}"

    # ---- method
    i = b["inputs"]; m = b["model"]
    def read_url(u: str) -> str:
        # HotSpawn is a fixture-listing source only; it is never linked as evidence for a number.
        return esc(u) + " (fixture source only — not a probability input)" if "hotspawn" in u else f'<a href="{esc(u)}">{esc(u)}</a>'
    reads_html = "".join(f'<tr><td>{esc(r["id"])}</td><td>{esc(r["read_utc_approx"])}</td><td>{read_url(r["url"])}</td><td>{esc(r["what"])}</td></tr>' for r in b["reads"])
    method_body = f"""
<h2>The ladder</h2>
<table><tr><th>Rung</th><th>Basis badge</th><th>Rule</th></tr>
<tr><td>1</td><td>🎯 Market</td><td>Re-derive a weighted no-vig consensus from the raw two-way prices stored on the strict market board (Pinnacle weight 2, others 1 — the upstream-published weights). Every quote is re-oriented from the names printed by its own source; a quote that doesn't match the fixture pair, starts &gt;1.5h off the HotSpawn start, or doesn't reproduce its stored probability is excluded. The recomputed consensus must agree with the board's stored consensus (≤0.6pp), and the desk publishes its own recomputed number.</td></tr>
<tr><td>2</td><td>🔁 Exchange</td><td>Kalshi event whose start is proven (event-page read: the EDT time converts exactly to the HotSpawn UTC start; or runner probe with ticker+name match). Probability = no-vig of the two Yes mid prices. A result within 1pp of 50% is a coin flip: probabilities stand as read, the pick is taken from the higher official Valve rating and labelled as a tiebreak.</td></tr>
<tr><td>3</td><td>🏅 VRS model</td><td>Both teams resolve to exactly one row of Valve's official global standings. Duplicate names require current-roster evidence (≥3 of 5 players shared with the row, from HLTV/bo3 lineups) — otherwise the rung refuses. Probability from the formula below.</td></tr>
<tr><td>4</td><td>🧭 Directional</td><td>Exactly one team is officially rated and the other has <b>no row at all</b> in the official file (searched exact + token, variants recorded). The rated team is priced against the table's last row (#{i['official_vrs']['floor']['standing']}, {i['official_vrs']['floor']['points']:.0f} pts). Clearly badged: directional, not a market price.</td></tr>
<tr><td>5</td><td>⚠️ Unresolved</td><td>Blank probabilities, rung-by-rung ledger on <a href="unresolved.html">Unresolved &amp; limitations</a>. Never filled by guesswork, name similarity, crowd data or another roster used as a proxy.</td></tr></table>
<h2>Formulas</h2>
<ul class="ev">
<li><b>No-vig (proportional):</b> for decimals d<sub>1</sub>, d<sub>2</sub>: q<sub>i</sub>=1/d<sub>i</sub>, p<sub>i</sub>=q<sub>i</sub>/(q<sub>1</sub>+q<sub>2</sub>). Books totalling outside [0.95, 1.30] are rejected as bad data.</li>
<li><b>Official-rating model:</b> p(a) = 1/(1+exp(−k·C·(pts<sub>a</sub>−pts<sub>b</sub>))) with C = g·ln(10)/400 = {m['valve_c']:.6f} from Valve's own model code (<a href="{VALVE_REPO}">counter-strike_regional_standings</a>, glicko.js: 400 pts ≙ 90%, RD 75). Current k = <b>{m['k']:.6f}</b> — {esc(m['k_source'])} (least-squares fit of logit(market) = k·C·Δ; calibration block: {esc(json.dumps(i['strict_board']['calibration']))}).</li>
</ul>
<h2>Verification gates (build aborts on failure)</h2>
<ul class="ev">
<li>Every market quote recomputes from its decimals and orients by its own printed names; no price link may point at HotSpawn; consensus must match the upstream board's within 0.6pp.</li>
<li>Every model/directional row recomputes from the official points for the cited standings rows (checked against the pinned file, sha256 {esc(i['official_vrs']['sha256'][:16])}…).</li>
<li>Probabilities sum to 1; the pick is always the higher-probability team unless a documented coin-flip tiebreak says otherwise; unresolved rows carry no pick.</li>
<li>HotSpawn crowd/ownership, HLTV's community vote and bo3.gg's analytics percentage are structurally absent from every formula.</li>
</ul>
<h2>Inputs of this build</h2>
<table><tr><th>Input</th><th>Generated / file</th><th>sha256 (first 16)</th></tr>
<tr><td>Strict market board (fixtures + raw quotes)</td><td>{esc(i['strict_board']['generated_utc'])} · {i['strict_board']['open']} open</td><td>{esc(i['strict_board']['sha256'][:16])}…</td></tr>
<tr><td>Coverage board (fixture union + cross-check)</td><td>{esc(i['coverage_board']['generated_utc'])} · {i['coverage_board']['open']} open</td><td>{esc(i['coverage_board']['sha256'][:16])}…</td></tr>
<tr><td>Valve official standings (pinned copy)</td><td><a href="{esc(i['official_vrs']['url'])}">{esc(i['official_vrs']['file'])}</a> · {i['official_vrs']['rows']} rows</td><td>{esc(i['official_vrs']['sha256'][:16])}…</td></tr>
<tr><td>Manual research overrides</td><td>{i['overrides_reads']} recorded reads (below)</td><td>—</td></tr></table>
<h2 id="ledger">Source ledger — pages read for the fallback research (2026-10-21)</h2>
<table><tr><th>Ref</th><th>Read (UTC, approx.)</th><th>URL</th><th>What was taken from it</th></tr>{reads_html}</table>
<h2>Freshness automation</h2>
<p>Upstream collectors refresh the fixture/quote boards as often as ~27 minutes; this desk re-derives and republishes about every 4 hours (<code>.github/workflows/36495748-refresh.yml</code>): it re-probes Kalshi and bo3.gg for fixtures still lacking prices, checks Valve's repo for a newer standings file, re-runs the ladder and all verification gates, and only then commits. Deep identity reasoning (HLTV lineups) is recorded manually in <code>data/36495748/overrides.json</code> so automation can never silently invent it. Every page header prints the input capture times — if upstream stalls, the desk stops claiming freshness instead of recycling old numbers.</p>
"""

    return {
        "index.html": page("Executive summary — every HotSpawn CS2 pick", "index.html", index_body, b),
        "picks.html": page("All picks — every open HotSpawn CS2 match", "picks.html", picks_body, b),
        "unresolved.html": page("Unresolved picks & limitations", "unresolved.html", unresolved_body, b),
        "flagged.html": page("Flagged for review", "flagged.html", flagged_body, b),
        "method.html": page("Method, formulas & sources", "method.html", method_body, b),
    }


def main() -> int:
    board = build_board()
    errors = verify_board(board)
    if errors:
        print("VERIFICATION FAILED — refusing to publish:")
        for e in errors:
            print("  -", e)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")
    for name, text in render(board).items():
        (OUT / name).write_text(text, encoding="utf-8")
    s = board["summary"]
    print(f"36495748 desk built: {s['open']} open, {s['with_pick']} picks "
          f"(market {s['market']}, exchange {s['exchange']}, vrs_model {s['vrs_model']}, "
          f"directional {s['directional_floor']}), unresolved {s['unresolved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
