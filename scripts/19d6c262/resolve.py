#!/usr/bin/env python3
"""Session 19d6c262 — resolve a pick for EVERY open HotSpawn CS2 fixture.

Inputs (read-only):
  * data/f7279a54/board.json  — the freshest OURLINE board: fixture list, featured market
    lines (external books/exchange, de-vigged consensus) and the fitted VRS slope k.
  * data/19d6c262/vrs_global.json — the official Valve Regional Standings + per-team details
    (counted roster, latest counted match) fetched from ValveSoftware/counter-strike_regional_standings.

The 20 fixtures the OURLINE board already prices are copied through UNCHANGED (featured).
For the fixtures it leaves `no_line` (because its VRS snapshot aged past its own 14-day
window), we originate a line from official data only:
  1. both teams resolve to an unambiguous official VRS rating  -> calibrated VRS model line;
  2. exactly one team is rated, the opponent is unrated          -> originated estimate that
     treats the unrated opponent at the VRS floor (#380 / 381 pts), labelled directional;
  3. neither team is rated                                       -> UNRESOLVED (no number invented).

HotSpawn is used only to know which matches exist; no HotSpawn crowd percentage is read.
No bookmaker price is ever fabricated or mis-joined. Every resolved row cites the official
Valve standings file + the team's details file.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "19d6c262"
BASE = ROOT / "data" / "f7279a54" / "board.json"


def canon(name: str) -> str:
    import re
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


# Documented aliases: HotSpawn spelling -> official VRS team name, with the basis for the join.
ALIASES = {
    "aurora yb": ("Aurora Young Blud",
                  "acronym 'YB' = 'Young Blud'; the only Aurora academy roster in the official "
                  "VRS (the main Aurora side is a separate #9 entry)"),
}


def build_vrs_index(vrs: dict):
    """name(canon) -> chosen rating row; duplicates resolved by most-recent counted match,
    tie-broken by higher standing (more points). The rejected candidates are kept for review."""
    groups: dict[str, list] = {}
    for t in vrs.get("teams", []):
        groups.setdefault(canon(t["team"]), []).append(t)
    idx, dupes = {}, {}
    for key, rows in groups.items():
        if len(rows) == 1:
            idx[key] = rows[0]
            continue
        chosen = sorted(rows, key=lambda r: (r.get("latest_match_date") or "0000-00-00",
                                             -r["standing"]))[-1]
        idx[key] = chosen
        dupes[key] = {"chosen_standing": chosen["standing"],
                      "candidates": [{k: r.get(k) for k in ("standing", "points", "roster",
                                                            "latest_match_date", "details_url")}
                                     for r in rows]}
    return idx, dupes


def rating_for(name: str, idx: dict):
    """Return (rating_row_or_None, how, note). Applies the documented alias table first."""
    key = canon(name)
    if key in ALIASES:
        target, basis = ALIASES[key]
        row = idx.get(canon(target))
        return row, "alias", f"{name} -> {target} ({basis})"
    row = idx.get(key)
    if row:
        return row, "exact", None
    return None, "not_in_vrs", f"{name}: no official Valve VRS rating"


def vrs_evidence(row):
    if not row:
        return None
    return {"standing": row["standing"], "points": row["points"], "team": row["team"],
            "roster": row.get("roster"), "latest_match_date": row.get("latest_match_date"),
            "details_url": row.get("details_url")}


def resolve_row(row: dict, idx: dict, dupes: dict, k: float, vrs_meta: dict) -> dict:
    row = json.loads(json.dumps(row))  # deep copy; never mutate the base board
    ta, tb = row["team_a"], row["team_b"]
    ra, how_a, note_a = rating_for(ta, idx)
    rb, how_b, note_b = rating_for(tb, idx)
    res = {
        "vrs_snapshot": vrs_meta["snapshot"], "vrs_page_url": vrs_meta["page_url"],
        "team_a": vrs_evidence(ra), "team_b": vrs_evidence(rb),
        "match_a": how_a, "match_b": how_b, "k": round(k, 4),
        "floor": vrs_meta["floor"],
    }
    notes = [n for n in (note_a, note_b) if n]
    flags = list(row.get("flags", []))
    if how_a == "alias" or how_b == "alias":
        flags.append("vrs_alias_join")
    if canon(ta) in dupes or canon(tb) in dupes:
        flags.append("vrs_duplicate_name_resolved")
    if ra and rb:
        delta = ra["points"] - rb["points"]
        prob_a = core.vrs_prob(ra["points"], rb["points"], k)
        res.update({"method": "valve_vrs_model", "delta_points": delta, "model_prob_a": round(prob_a, 4)})
        row["line"] = core.make_line(prob_a, ta, tb, "model",
                                     model_note="Calibrated Valve VRS model (both teams rated).")
    elif ra or rb:
        rated, other, side = (ra, rb, "a") if ra else (rb, ra, "b")
        floor_pts = vrs_meta["floor"]["points"]
        prob_rated = core.vrs_prob(rated["points"], floor_pts, k)
        prob_a = prob_rated if side == "a" else 1 - prob_rated
        unrated_name = ta if side == "b" else tb
        # Could the "unrated" side actually be a rated team under a name variant? If a name
        # token of the unrated team matches an official VRS team, say so and do not present a
        # high floor confidence as if the opponent were certainly weak.
        toks = [t for t in canon(unrated_name).split() if len(t) >= 3]
        alias_hits = [kk for t in toks for kk in idx
                      if kk == t or kk.startswith(t + " ") or kk.endswith(" " + t)]
        conf = "Directional"
        note = (f"Originated estimate: {rated['team']} is officially rated (VRS #{rated['standing']}, "
                f"{rated['points']} pts); the unrated opponent is assumed at the VRS floor "
                f"(#{vrs_meta['floor']['standing']}, {floor_pts} pts). The opponent's true strength is "
                f"unknown, so this is a directional pick, not a calibrated probability.")
        if alias_hits:
            flags.append("unrated_team_may_be_rated_alias")
            res["possible_alias_candidates"] = sorted({idx[kk]["team"] for kk in alias_hits})
            note += (f" NOTE: '{unrated_name}' shares a name token with official VRS team(s) "
                     f"{res['possible_alias_candidates']}; if it is that roster, the rated side is "
                     f"weaker than the floor assumes and this pick could change — see Flagged for Review.")
        res.update({"method": "valve_vrs_floor_estimate", "rated_side": side,
                    "rated_points": rated["points"], "floor_points": floor_pts,
                    "unrated_team": unrated_name, "estimate_prob_rated": round(prob_rated, 4)})
        row["line"] = core.make_line(prob_a, ta, tb, "floor_estimate", confidence=conf,
                                     directional=True, model_note=note)
        flags.append("directional_unrated_opponent")
    else:
        res.update({"method": "unresolved"})
        row["line"] = None
        flags.append("no_rating_either_team")
    res["notes"] = notes
    row["resolution"] = res
    row["flags"] = sorted(set(flags))
    return row


def main() -> int:
    base = json.loads(BASE.read_text())
    vrs = json.loads((DATA / "vrs_global.json").read_text())
    idx, dupes = build_vrs_index(vrs)
    k = base["calibration"]["k"]
    vrs_meta = {"snapshot": vrs["snapshot"], "page_url": vrs["page_url"],
                "api_url": vrs["api_url"], "floor": vrs["floor"]}

    open_rows, unresolved = [], []
    for row in base.get("open", []):
        if row.get("line"):
            open_rows.append(row)  # featured market pick, copied unchanged
            continue
        r = resolve_row(row, idx, dupes, k, vrs_meta)
        open_rows.append(r)
        if not r.get("line"):
            unresolved.append(r)

    def count(pred):
        return sum(1 for r in open_rows if pred(r))
    summary = {
        "open": len(open_rows),
        "with_pick": count(lambda r: r.get("line")),
        "featured_market": count(lambda r: r.get("line") and r["line"]["basis"] in ("market", "market+model")),
        "vrs_model": count(lambda r: r.get("line") and r["line"]["basis"] == "model"),
        "floor_estimate": count(lambda r: r.get("line") and r["line"]["basis"] == "floor_estimate"),
        "unresolved": len(unresolved),
        "resolved_this_session": count(lambda r: r.get("line") and "resolution" in r),
        "base_generated_utc": base.get("generated_utc"),
    }
    open_rows.sort(key=lambda r: (r.get("lock_utc") or r.get("start_utc") or "", r["fixture_id"]))
    board = {
        "session": "19d6c262", "generated_utc": base.get("generated_utc"),
        "base_board": "data/f7279a54/board.json", "base_generated_utc": base.get("generated_utc"),
        "week": base.get("week"), "policy": "every-match-resolution-v1",
        "vrs": vrs_meta, "calibration": {"k": round(k, 4), "n_pairs": base["calibration"]["n_pairs"],
                                         "source": "ourline f7279a54 fit on eligible priced fixtures"},
        "vrs_duplicates_resolved": dupes, "summary": summary,
        "open": open_rows, "unresolved_ids": [r["fixture_id"] for r in unresolved],
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
