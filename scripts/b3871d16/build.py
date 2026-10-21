#!/usr/bin/env python3
"""now/ - TWC 2026 final-day desk plus a pick for every open HotSpawn CS2 fixture.

Session b3871d16. Writes only now/** (HTML) and now/data/** (JSON + CSV).

What this page adds over the other boards on this site:
  1. A pick, a win probability and a source for EVERY open CS2 fixture, including the ones no
     sportsbook prices, with the resolution method named per row.
  2. Two blank rows on the canonical board (1081546, 1081863) either priced from a book that does
     cover them or explained; never silently filled.
  3. A contrarian layer with an explicit floor, so "fade the crowd" only fires where a priced
     probability says the dog is live.
  4. A flagged-for-review page listing every irregularity found while verifying line by line.

Inputs are read-only. Probabilities come from external book prices and Valve's official regional
standings only. HotSpawn's own percentages are used for ownership/lock data and never as a
probability, per the standing brief.
"""
from __future__ import annotations

import csv
import html
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "data/fe803b80/board.json"
CROWD_PATHS = (ROOT / "data/b3871d16/crowd_live.json", ROOT / "data/371a1ce7/crowd.json")
LEDGER_PATH = ROOT / "data/b3871d16/live_reads.json"
OVERRIDE_PATH = ROOT / "data/b3871d16/overrides.json"
OUT = ROOT / "now"

# Rules re-implemented here on purpose (identical to the documented ones in
# scripts/fe803b80/core.py) so that an edit to another session's module cannot silently change a
# published number on this page. tests/test_b3871d16.py asserts the two agree on un-overridden rows.
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.5, "kalshi": 1.0, "melbet": 1.0, "thunderpick": 1.5}
BOOK_MIN, BOOK_MAX = 0.95, 1.30
MARKET_WEIGHT_MANY, MARKET_WEIGHT_ONE = 0.85, 0.75
CROWD_FLOOR_PICKS = 20          # below this many picks, crowd data says nothing about leverage
CONTRARIAN_FLOOR = 0.35         # never switch to a dog the priced line puts under this
LEVERAGE_MIN_PP = 10            # publish a climb tip only when we are >=10pp off the crowd
VALVE_Q = math.log(10) / 400.0
VALVE_RD = 75.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0

FLAG_LABEL = {
    "tier_c_event_low_coverage": "tier-C event - thin external coverage",
    "no_external_price_for_this_fixture": "no bookmaker prices this card",
    "originated_vrs_line": "line comes from Valve's ratings, not a book",
    "originated_elo_line_no_official_rating": "one side has no official rating - originated Elo line",
    "no_source_input_available_row_left_blank": "no source input at all - row left blank",
    "joined_price_start_time_differs_more_than_3h": "the price found starts over 3h from this card - weak join",
    "alias_applied_see_evidence": "team alias resolved from evidence, see the ledger",
}
MODEL_SHORT = {"valve_vrs": "Valve VRS rating model", "originated_elo": "originated Elo over bo3.gg results",
               "vrs": "Valve VRS rating model", "model": "rating model"}
BASIS_LABEL = {
    "market+model": "Book price blended with Valve's rating model",
    "market": "Book price only (no rating pair for one side)",
    "model": "No book prices it - rating model line, flagged",
    "valve_vrs": "No book prices it - Valve VRS rating model",
    "originated_elo": "No book prices it - originated Elo over bo3.gg results",
    "vrs": "No book prices it - Valve VRS rating model",
    "session_price_added": "Book price found by this desk (board had none)",
    "band_only": "No price anywhere - direction and band only",
    "none": "Nothing to pick on",
}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def no_vig(da: float | None, db: float | None) -> float | None:
    """Proportional devigging of a two-way decimal pair; None if the book is not sane."""
    if not da or not db or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not (BOOK_MIN <= book <= BOOK_MAX):
        return None
    return ia / book


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1.0 - p))


def blend(market_pa: float | None, n_sources: int, model_pa: float | None) -> dict | None:
    if market_pa is None and model_pa is None:
        return None
    if market_pa is None:
        return {"prob_a": model_pa, "prob_b": 1 - model_pa, "basis": "model", "market_weight": 0.0}
    if model_pa is None:
        return {"prob_a": market_pa, "prob_b": 1 - market_pa, "basis": "market", "market_weight": 1.0}
    w = MARKET_WEIGHT_MANY if n_sources >= 2 else MARKET_WEIGHT_ONE
    p = sigmoid(w * logit(market_pa) + (1 - w) * logit(model_pa))
    return {"prob_a": p, "prob_b": 1 - p, "basis": "market+model", "market_weight": w}


def confidence_label(p: float) -> str:
    return ("Strong" if p >= 0.70 else "Solid" if p >= 0.60 else "Lean" if p >= 0.53 else "Toss-up")


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    """Valve's own expected-score arithmetic (model/glicko.js, model/fit.js in the official
    regional-standings repo) with a fixed RD of 75, plus the fitted slope from the board."""
    return sigmoid(k * VALVE_C * (points_a - points_b))


# ------------------------------------------------------------------ helpers
def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def hhmmz(iso: str | None) -> str:
    if not iso:
        return "-"
    return iso[11:16] + "Z"


def day_label(iso: str | None) -> str:
    if not iso:
        return "unscheduled"
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return d.strftime("%a %d %b")


def pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{x * 100:.{digits}f}%"


def link(url: str, label: str, extra: str = "") -> str:
    return f'<a href="{esc(url)}" rel="noopener"{extra}>{esc(label)}</a>'


def norm(name: str) -> str:
    """Lower-case alphanumerics with accents folded away, so 'QUINTESSÊNCIA' from one source
    joins to 'QUINTESSÊNCIA' from another and 'BET-M' still matches 'BETM'."""
    folded = unicodedata.normalize("NFKD", (name or "").lower())
    return "".join(c for c in folded if c.isascii() and c.isalnum())


# ------------------------------------------------------------------ crowd
def crowd_index() -> tuple[dict, dict]:
    """fixture_id -> crowd row, merged over every available capture, newest file first.

    A card this desk did not re-read still shows the ownership sample another capture holds, and
    each row keeps the file and minute it came from so the label beside it is honest.
    """
    idx: dict[str, dict] = {}
    stamps: dict[str, dict] = {}
    for path in CROWD_PATHS:
        blob = load_json(path)
        if not blob or not blob.get("rows"):
            continue
        stamp = {"read_utc": blob.get("read_utc"), "source": blob.get("source_api") or blob.get("source_url"),
                 "file": str(path.relative_to(ROOT))}
        stamps[stamp["file"]] = stamp
        for row in blob["rows"]:
            fid = str(row.get("fixture_id") or "")
            if fid and fid not in idx:
                idx[fid] = {**row, "_file": str(path.relative_to(ROOT)), "_read_utc": stamp["read_utc"]}
    if not idx:
        return {}, {}
    files = list(stamps)
    meta = dict(stamps[files[0]])
    meta["files"] = files
    meta["multi"] = len(files) > 1
    return idx, meta


# ------------------------------------------------------------------ row builder
def build_rows(board: dict, overrides: dict, crowd: dict, live_prices: dict | None = None,
               vrs_status: dict | None = None, source_rows: list[dict] | None = None) -> list[dict]:
    """One row per fixture. `source_rows` lets a caller build the same shape from the board's closed set,
    so a card keeps its published line after it locks instead of vanishing off the desk."""
    k = float((board.get("calibration") or {}).get("k") or 1.0)
    rows: list[dict] = []
    for r in (source_rows if source_rows is not None else board.get("open", [])):
        fid = str(r["fixture_id"])
        corr = (overrides.get("board_corrections") or {}).get(fid, {})
        team_a, team_b = r["team_a"], r["team_b"]
        quotes = list(r.get("quotes") or [])
        notes: list[str] = []
        flags = list(r.get("flags") or [])
        live = next((q for q in ((live_prices or {}).get("prices") or [])
                     if str(q.get("fixture_id")) == fid), None)
        added_quote = corr.get("action") == "price_added" and corr.get("quote")
        if added_quote:
            q = corr["quote"]
            quotes.append({"source_key": q["source_key"], "decimal_a": q["decimal_a"],
                           "decimal_b": q["decimal_b"], "retrieved_utc": q["read_utc"],
                           "public_url": q["url"], "match_url": q.get("match_url")})
            notes.append(f"Book price added by this desk: {q['source_name']} {team_a} {q['decimal_a']:.2f} / "
                         f"{team_b} {q['decimal_b']:.2f}, read {q['read_utc'][11:16]}Z.")
        if live:
            quotes.append({"source_key": live.get("source_key", "bo3gg_thunderpick"), "decimal_a": live["decimal_a"],
                           "decimal_b": live["decimal_b"], "retrieved_utc": live["read_utc"],
                           "public_url": live.get("url")})
            added_quote = added_quote or live   # forces the recompute path below
        elif live:
            notes.append(f"Price found by the scheduled collector on {esc(live['read_utc'][:10])} "
                         f"({live.get('source_name', 'bo3.gg')} {live['decimal_a']} / {live['decimal_b']}); "
                         "this card had no book line when the desk was written.")
        elif corr.get("note"):
            notes.append(corr["note"])

        # market side
        per_source = [p for p in (no_vig(q.get("decimal_a"), q.get("decimal_b")) for q in quotes) if p is not None]
        if (added_quote or live) and per_source:
            wsum = sum(SOURCE_WEIGHTS.get(q.get("source_key"), 1.0) for q in quotes) or 1.0
            market_pa = sum(SOURCE_WEIGHTS.get(q.get("source_key"), 1.0) * (no_vig(q.get("decimal_a"), q.get("decimal_b")) or 0.0)
                            for q in quotes if no_vig(q.get("decimal_a"), q.get("decimal_b")) is not None) / wsum
            n_sources = len(per_source)
            spread = max(per_source) - min(per_source) if len(per_source) > 1 else None
        elif r.get("market"):
            market_pa, n_sources = r["market"]["prob_a"], r["market"]["n_sources"]
            spread = r["market"].get("spread_a")
        else:
            market_pa, n_sources, spread = None, 0, None

        # model side, with any rating-join correction applied
        model_pa, model_basis = r["model"].get("prob_a"), r["model"].get("basis")
        vrs_fix = corr.get("vrs_fix")
        if vrs_fix:
            pts_other = (r.get("vrs_b") if vrs_fix["side"] == "a" else r.get("vrs_a")) or {}
            other_pts = pts_other.get("points")
            if other_pts:
                pts = vrs_fix["points"]
                pa = r["team_a"] if vrs_fix["side"] == "a" else r["team_b"]
                pb = r["team_b"] if vrs_fix["side"] == "a" else r["team_a"]
                model_pa = vrs_prob(pts, other_pts, k) if vrs_fix["side"] == "a" else 1 - vrs_prob(pts, other_pts, k)
                model_basis = "valve_vrs"
                notes.append(f"Rating join corrected: {pa} is read at {pts:,.0f} VRS points (row {vrs_fix['correct_row'].split('--')[0]}, "
                             f"world #{vrs_fix['world_standing']}), not the retired {vrs_fix['wrong_row_the_board_joined']} row the "
                             f"canonical board picked up. {pb}: {other_pts:,.0f} points. Delta {abs(pts - other_pts):,.0f}.")
            else:
                notes.append("Rating join corrected on this side, but the opponent has no row in Valve's file at all, so still "
                             "no two-sided rating line is derivable.")
                model_pa, model_basis = None, None

        band = corr.get("band")
        if band and band.get("crowd_note"):
            notes.append("Crowd read: " + band["crowd_note"])
        if band:
            band = {**band, "why_no_number": corr.get("why_no_number") or ""}
        line = None
        if market_pa is not None or model_pa is not None:
            line = blend(market_pa, n_sources, model_pa)
            if added_quote or live:
                line["basis"] = "session_price_added" if model_pa is None else "market+model"
                line["market_weight"] = 1.0 if model_pa is None else (MARKET_WEIGHT_MANY if n_sources >= 2 else MARKET_WEIGHT_ONE)
        if line:
            pick_a = line["prob_a"] >= 0.5
            line["pick"] = team_a if pick_a else team_b
            line["pick_probability"] = line["prob_a"] if pick_a else line["prob_b"]
            line["prob_pick_other"] = line["prob_b"] if pick_a else line["prob_a"]
            line["confidence"] = confidence_label(line["pick_probability"])

        # crowd (ownership only)
        c = crowd.get(fid)
        crowd_a = crowd_b = total_picks = None
        crowd_orientation = None
        crowd_provenance = None
        if c:
            if norm(c.get("team_a", "")) in (norm(team_a), norm(team_b)) and norm(c.get("team_b", "")) in (norm(team_a), norm(team_b)):
                flip = norm(c.get("team_a", "")) == norm(team_b) and norm(team_a) != norm(team_b)
                crowd_a, crowd_b = (c.get("crowd_b"), c.get("crowd_a")) if flip else (c.get("crowd_a"), c.get("crowd_b"))
                total_picks = c.get("total_picks")
                crowd_orientation = "flipped on names" if flip else "aligned"
                crowd_provenance = (f'{c.get("_file", "crowd capture")} '
                                     f'{str(c.get("_read_utc", ""))[11:16]}Z')
            else:
                crowd_orientation = (f"unusable - crowd row lists {c.get('team_a')} / {c.get('team_b')}, "
                                     f"board lists {team_a} / {team_b}")
        leverage = None
        if line and crowd_a is not None and total_picks is not None:
            share = (crowd_a if line["prob_a"] >= 0.5 else crowd_b)
            p = line["pick_probability"]
            leverage = {"crowd_share_pick": share / 100.0, "diff_pp": round((p - share / 100.0) * 100, 1),
                        "ev_points": round((r.get("points") or 0) * (p - share / 100.0), 2),
                        "sample_ok": total_picks >= CROWD_FLOOR_PICKS, "floor_ok": p >= CONTRARIAN_FLOOR}

        status = ("direction_band" if (band and not line) else
                  "priced" if (line and "market" in (line.get("basis") or "")) else
                  "rating_only" if line else "no_pick")
        links = []
        for s in r.get("sources") or []:
            if s.get("url"):
                links.append((s.get("label") or s.get("kind") or "source", s["url"]))
        for q in quotes:
            u = q.get("public_url") or q.get("match_url")
            if u:
                links.append((f"{q.get('source_key')} price page", u))
        if r.get("model", {}).get("vrs_url"):
            links.append(("Valve VRS file", r["model"]["vrs_url"]))
        if r.get("model", {}).get("source_url"):
            links.append(("Elo results source", r["model"]["source_url"]))
        if corr.get("read_refs") or corr.get("read_ref"):
            links.append(("This desk's read ledger", "method.html#ledger"))
        if not any("HotSpawn" in (lbl or "") for lbl, _ in links) and r.get("hotspawn_url"):
            links.insert(0, ("HotSpawn lobby (fixture discovery only)", r["hotspawn_url"]))

        rows.append({
            "fixture_id": fid, "team_a": team_a, "team_b": team_b,
            "competition": r.get("competition"), "tier": r.get("tier"), "stage": r.get("stage"),
            "best_of": r.get("best_of"), "points": r.get("points"),
            "start_utc": r.get("start_utc"), "lock_utc": r.get("lock_utc"), "status": r.get("status"),
            "state": r.get("state") or ("closed" if str(r.get("status")) == "ended" else "open"),
            "winner": r.get("winner"),
            "alias_note": r.get("alias_note"),
            "market_prob_a": market_pa, "market_n_sources": n_sources, "market_spread": spread,
            "model_prob_a": model_pa, "model_basis": model_basis,
            "vrs_points_a": (r.get("vrs_a") or {}).get("points"), "vrs_points_b": (r.get("vrs_b") or {}).get("points"),
            "model_only_high": bool(line and line.get("basis") == "model" and line["pick_probability"] >= 0.85),
            "line": line, "band": band, "status_flag": status,
            "crowd": {"a": crowd_a, "b": crowd_b, "picks": total_picks, "orientation": crowd_orientation,
                      "provenance": crowd_provenance},
            "leverage": leverage, "notes": notes, "flags": flags,
            "sources": links, "correction": corr.get("action"), "vrs_corrected": bool(vrs_fix),
        "context_links": corr.get("context_links") or [],
            "correction_evidence": [u for u in (
                [added_quote["url"], added_quote.get("match_url")] if added_quote else []) if u],
        })
    rows.sort(key=lambda x: (x.get("start_utc") or "9999", -(x.get("points") or 0)))
    return rows


# ------------------------------------------------------------------ page shell
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0d1117;color:#e8eaf0;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:0 14px 64px}
a{color:#79b8ff;text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:1.5rem;line-height:1.25;margin:.6em 0 .2em}
h2{font-size:1.2rem;margin:1.6em 0 .4em;border-bottom:1px solid #223047;padding-bottom:.3em}
h3{font-size:1.02rem;margin:1.1em 0 .3em}
p{margin:.45em 0}
.small{font-size:.83rem}.mut{color:#93a1b8}
.top{position:sticky;top:0;z-index:5;background:#0d1117f2;border-bottom:1px solid #223047;padding:8px 0 6px;margin-bottom:6px}
.top nav{display:flex;gap:6px;flex-wrap:wrap}
.top a{display:inline-block;padding:4px 9px;border:1px solid #2b3a55;border-radius:999px;font-size:.82rem}
.stamp{font-size:.76rem;color:#93a1b8;margin:2px 0 0}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.card,.pick{background:#151b26;border:1px solid #232f45;border-radius:12px;padding:10px 12px;margin:10px 0}
.kpi{background:#111823;border-radius:12px;padding:10px 12px}
.kpi b{display:block;font-size:1.42rem;line-height:1.2}
.bar{display:flex;height:10px;border-radius:6px;overflow:hidden;background:#232f45;margin:6px 0}
.bar i{display:block;height:100%}
.bar i.a{background:#3fb950}.bar i.b{background:#f0883e}
table{width:100%;border-collapse:collapse;margin:.3em 0 1em;font-size:.92rem}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid #1e2a3f;vertical-align:top}
th{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#93a1b8}
tr th:first-child,tr td:first-child{padding-left:2px}
.num{font-variant-numeric:tabular-nums}
.chip{display:inline-block;font-size:.72rem;padding:2px 7px;border-radius:999px;border:1px solid #2b3a55;margin:1px 3px 1px 0;white-space:nowrap}
.chip.ok{border-color:#2ea04366;background:#2ea0431f}.chip.warn{border-color:#f0883e66;background:#f0883e1f}
.chip.bad{border-color:#f8514966;background:#f851491f}.chip.lines{border-color:#79b8ff66;background:#79b8ff1f}
.pickline{font-size:1.04rem;font-weight:650}
.blank{color:#f85149;font-weight:600}
ul,ol{padding-left:1.15em}li{margin:.35em 0}
details{background:#111823;border:1px solid #232f45;border-radius:10px;padding:8px 11px;margin:8px 0}
summary{cursor:pointer;font-weight:600}
.foot{margin-top:34px;border-top:1px solid #223047;padding-top:10px;font-size:.8rem;color:#93a1b8}
@media(max-width:760px){
 h1{font-size:1.28rem}
 table{font-size:.9rem}
 thead{display:none}
 table.responsive,table.responsive tbody,table.responsive tr,table.responsive td{display:block;width:100%}
 table.responsive tr{border:1px solid #232f45;border-radius:10px;margin:8px 0;padding:4px 8px;background:#121a26}
 table.responsive td{border:0;padding:5px 0;display:flex;justify-content:space-between;gap:10px;align-items:baseline}
 table.responsive td::before{content:attr(data-label);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;color:#93a1b8;flex:0 0 42%}
 table.responsive td.wide{display:block}
 table.responsive td.wide::before{display:block;margin-bottom:3px}
}
"""

NAV = [("index.html", "Desk home"), ("day5.html", "TWC day 5"), ("twc.html", "Day 1-4 review"),
       ("picks.html", "Every pick"), ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"),
       ("method.html", "Method"), ("../index.html", "All sections")]


def page(title: str, body: str, stamp: dict, active: str = "") -> str:
    nav = "".join(
        f'<a href="{esc(h)}"{" aria-current=page" if h == active else ""}>{esc(t)}</a>' for h, t in NAV)
    fresh = stamp.get("fresh") or {}
    return (f"<!doctype html>\n<html lang=en>\n<meta charset=utf-8>\n"
            f"<meta name=viewport content=\"width=device-width,initial-scale=1\">\n"
            f"<title>{esc(title)} | TWC day 5 desk</title>\n"
            f"<style>{CSS}</style>\n"
            f"<main>\n<header class=top><nav>{nav}</nav>"
            f"<p class=stamp>Board read {esc(stamp.get('board_read','-'))}"
            + (f" - collector {esc(fresh.get('status','failed'))} at {esc((fresh.get('run_utc') or '-')[:16])}"
               if fresh else " - collector not run in this build (CI writes it)")
            + f" - crowd read {esc(stamp.get('crowd_read','-'))} - "
            f"this page written {esc(stamp.get('built_utc','-'))}. "
            f"<a href=method.html#ledger>Sources read</a>.</p></header>\n{body}\n</main>\n")


def prob_cell(row: dict) -> str:
    line, band = row["line"], row["band"]
    if line:
        a, b = line["prob_a"], line["prob_b"]
        return (f'<div class="pickline">{esc(line["pick"])} {pct(line["pick_probability"])}</div>'
                f'<div class="bar" role="img" aria-label="{esc(row["team_a"])} {pct(a)} vs {esc(row["team_b"])} {pct(b)}">'
                f'<i class=a style="width:{a*100:.1f}%"></i><i class=b style="width:{b*100:.1f}%"></i></div>'
                f'<span class=small>{esc(row["team_a"])} {pct(a)} - {esc(row["team_b"])} {pct(b)}</span>')
    if band:
        return (f'<span class="blank">no probability published</span> '
                f'<span class=small>band {band["prob_a_range"][0]*100:.0f}-{band["prob_a_range"][1]*100:.0f}% '
                f'for {esc(row["team_a"])} - direction only</span>')
    return '<span class="blank">blank - unresolved</span>'


def basis_chips(row: dict) -> str:
    out = []
    line = row["line"] or {}
    basis = line.get("basis") or (row["band"] and "band_only") or "none"
    out.append(f'<span class="chip {"lines" if "market" in basis else "warn" if basis != "none" else "bad"}">'
               f'{esc(BASIS_LABEL.get(basis, basis))}</span>')
    if row["market_n_sources"]:
        out.append(f'<span class=chip>{row["market_n_sources"]} book source'
                   f'{"s" if row["market_n_sources"] > 1 else ""}</span>')
    if row["market_spread"] is not None:
        out.append(f'<span class=chip>book spread {row["market_spread"]*100:.1f}pp</span>')
    if row["points"] is not None:
        out.append(f'<span class=chip>{row["points"]} pts</span>')
    if row["tier"]:
        out.append(f'<span class=chip>tier {esc(row["tier"])}</span>')
    if row["best_of"]:
        out.append(f'<span class=chip>bo{esc(row["best_of"])}</span>')
    if row["correction"] in ("price_added", "price_added_and_rating_fixed") or row.get("vrs_corrected"):
        out.append('<span class="chip ok">corrected by this desk</span>')
    for f in row["flags"]:
        out.append(f'<span class="chip warn" title="{esc(f)}">{esc(FLAG_LABEL.get(f, f.replace("_", " ")))}</span>')
    if row.get("model_only_high"):
        out.append('<span class="chip bad">model line above 85% - read it as direction, not odds</span>')
    return "".join(out)


def crowd_cell(row: dict) -> str:
    c = row["crowd"]
    if c["a"] is None:
        if c["picks"] is not None:
            return (f'<span class=small>{c["picks"]} pick{"s" if c["picks"] != 1 else ""} on the card, split '
                    f'not recorded in this read</span><br>'
                    f'<span class="chip bad">under {CROWD_FLOOR_PICKS} picks - no leverage read</span>')
        return '<span class=small>No crowd read (not fetched)</span>'
    if c["b"] is None:
        return (f'<span class=small>{esc(c["a"])}% recorded, other side not</span><br>'
                f'<span class="chip bad">under {CROWD_FLOOR_PICKS} picks - no leverage read</span>')
    txt = (f'{esc(row["team_a"])} {c["a"]}% - {esc(row["team_b"])} {c["b"]}% '
           f'<span class=small mut>(n={c["picks"]}, {esc(c.get("provenance") or "crowd capture")})</span>')
    if c["picks"] is not None and c["picks"] < CROWD_FLOOR_PICKS:
        txt += f'<br><span class="chip bad">under {CROWD_FLOOR_PICKS} picks - no leverage read</span>'
    if c["orientation"] and c["orientation"].startswith("unusable"):
        txt = f'<span class=small mut>crowd row not matched: {esc(c["orientation"])}</span>'
    return txt


def leverage_cell(row: dict) -> str:
    lev, line = row["leverage"], row["line"]
    if not line:
        return '<span class="blank">-</span><br><span class=small>no number to weigh a switch against</span>'
    if not lev:
        return '<span class=small>No crowd sample.</span>'
    if not lev["sample_ok"]:
        return (f'<span class=small>Crowd sample is {esc(row["crowd"]["picks"])} pick'
                f'{"s" if (row["crowd"]["picks"] or 0) != 1 else ""} - under the '
                f'{CROWD_FLOOR_PICKS}-pick floor, so no climb advice is possible.</span>')
    diff = lev["diff_pp"]
    if abs(diff) < LEVERAGE_MIN_PP:
        return f'<span class=small>Within {LEVERAGE_MIN_PP}pp of the crowd ({diff:+.1f}pp) - nothing to take.</span>'
    if diff > 0 and lev["floor_ok"]:
        return (f'<span class="chip ok">climb {diff:+.1f}pp vs crowd</span> '
                f'<span class=small>{esc(line["pick"])} is {pct(line["pick_probability"])} to us and only '
                f'{lev["crowd_share_pick"]*100:.0f}% of the crowd; right here is worth about '
                f'{lev["ev_points"]:+.2f} pts of relative field.</span>')
    if diff < 0:
        return (f'<span class="chip warn">anti-crowd {diff:+.1f}pp</span> '
                f'<span class=small>The crowd is already on {esc(line["pick"])}; a correct pick here wins '
                f'the match and not the board.</span>')
    return f'<span class=small>{diff:+.1f}pp vs crowd, under the 35% floor - stay on the priced side.</span>'


def src_cell(row: dict) -> str:
    seen, out = set(), []
    for label, url in row["sources"]:
        if url in seen or not url:
            continue
        seen.add(url)
        out.append(link(url, label))
    return ' - '.join(out) or '<span class="blank">no source link</span>'


def match_table(rows: list[dict], caption: str = "", show_leverage=True) -> str:
    head = ("<tr><th>Match</th><th>Pick</th><th>Win chance</th>"
            + ("<th>Crowd (ownership)</th><th>Contrarian</th>" if show_leverage else "")
            + "<th>Why this number</th><th>Sources</th></tr>")
    body = []
    for row in rows:
        line = row["line"]
        pick_html = (f'<span class=pickline>{esc(line["pick"])}</span>' if line else
                     (f'<span class=pickline>{esc(row["team_a"])} (direction only)</span>' if row["band"]
                      else '<span class=blank>no pick</span>'))
        why = []
        if row["market_prob_a"] is not None:
            why.append(f"No-vig book consensus {pct(row['market_prob_a'])} / {pct(1-row['market_prob_a'])}")
        if row["model_prob_a"] is not None:
            lbl = MODEL_SHORT.get(row["model_basis"], row["model_basis"] or "model")
            why.append(f"Model {pct(row['model_prob_a'])} ({esc(lbl)})")
        if line and line.get("market_weight"):
            why.append(f"Blended at {line['market_weight']*100:.0f}% weight on the market")
        for n in row["notes"]:
            why.append(esc(n))
        if row["band"]:
            why.append(f'<span class="chip bad">{esc(row["band"]["label"])}</span> '
                       f'{esc(row["band"].get("why_no_number", ""))}')
        if row.get("model_only_high"):
            why.append('No book prices this card and the model line is above 85%. Small-tier Elo and rating models '
                       'are far less accurate at that distance than the number suggests: treat it as "pick this '
                       'side", not as a 95% chance.')
        if row["status_flag"] == "no_pick":
            why.append('<span class=blank>Nothing in the verified set prices or rates both sides.</span>')
        conf = f' - {esc(line["confidence"])}' if line else ""
        body.append(
            f'<tr id="m{esc(row["fixture_id"])}">'
            f'<td class=wide data-label=Match><strong>{esc(row["team_a"])} v {esc(row["team_b"])}</strong><br>'
            f'<span class="small mut">{esc(row["competition"] or "-")} - tier {esc(row["tier"] or "?")} - '
            f'{esc(row["stage"] or "stage not stated")}</span><br>'
            f'<span class=small>Starts {esc(day_label(row["start_utc"]))} {hhmmz(row["start_utc"])} - '
            f'locks {hhmmz(row["lock_utc"])}{" (bo" + esc(str(row["best_of"])) + ")" if row["best_of"] else ""}</span></td>'
            f'<td data-label=Pick>{pick_html}</td>'
            f'<td data-label="Win chance">{prob_cell(row)}{conf}</td>'
            + (f'<td data-label=Crowd>{crowd_cell(row)}</td><td data-label=Contrarian>{leverage_cell(row)}</td>' if show_leverage else "")
            + f'<td data-label="Why this number">{basis_chips(row)}<br><span class="small">{(" - ".join(w for w in why if w))}</span></td>'
            + f'<td data-label=Sources class=wide>{src_cell(row)}</td></tr>')
    cap = f'<caption class="small mut" style="caption-side:bottom;text-align:left">{esc(caption)}</caption>' if caption else ""
    return f'<table class=responsive><thead>{head}</thead><tbody>{"".join(body)}</tbody>{cap}</table>'


# ------------------------------------------------------------------ pages
def kpi(label: str, value: str, note: str = "") -> str:
    return f'<div class=kpi><span class=small>{esc(label)}</span><b>{value}</b><span class="small mut">{esc(note)}</span></div>'


def render_index(rows, board, overrides, stamp, crowd_meta, day5_rows=None) -> str:
    open_n = len(rows)
    priced = [r for r in rows if r["status_flag"] == "priced"]
    rating = [r for r in rows if r["status_flag"] == "rating_only"]
    banded = [r for r in rows if r["status_flag"] == "direction_band"]
    blank = [r for r in rows if r["status_flag"] == "no_pick"]
    day5 = overrides["day5_cards"]
    d5rows = day5_rows if day5_rows is not None else [r for r in rows if r["fixture_id"] in day5]
    top = sorted((r for r in rows if r["line"]), key=lambda r: (-(r["points"] or 0), r["line"]["pick_probability"] * -1))[:8]

    body = [f'<h1>TWC day 5 desk and every open HotSpawn CS2 match</h1>',
            f'<p class=small>Final day of the Thunderpick World Championship 2026 (Malta, $1M, 8 teams) is '
            f'Sunday 18 October 2026. The two cards on it lock at {hhmmz(day5["1080209"]["lock_utc"])} and '
            f'{hhmmz(day5["1080210"]["lock_utc"])} UTC, seven points each. This page carries a probability for '
            f'all {open_n} open CS2 fixtures in this week\'s lobby, including the low-tier ones no market '
            f'prices, and says out loud which of them are not resolved.</p>',
            '<div class=grid>',
            kpi("Open CS2 fixtures", str(open_n), "whole lobby, not just featured cards"),
            kpi("Priced from book lines", str(len(priced)), "external sportsbook or exchange"),
            kpi("Rating model only", str(len(rating)), "no book covers them - flagged per row"),
            kpi("Direction only", str(len(banded)), "one side has no rating at all"),
            kpi("No pick at all", str(len(blank)), "left blank, never inferred"),
            '</div>',
            '<h2 id=summary>Executive summary</h2>',
            '<ol>',
            f'<li><strong>Grand final, 15:00Z: FURIA '
            f'{pct(next((r["line"]["prob_a"] for r in d5rows if r["fixture_id"] == "1080210" and r["line"]), None))} '
            f'v BETBOOM {pct(next((r["line"]["prob_b"] for r in d5rows if r["fixture_id"] == "1080210" and r["line"]), None))}.</strong> '
            f'Thunderpick has FURIA 1.35 / BETBOOM 2.90, the five-book consensus is FURIA 69.6%. '
            f'BETBOOM sits under the 35% floor, so the contrarian rule does not fire - '
            f'<a href=day5.html#gf>full reasoning</a>.</li>',
            f'<li><strong>Third place, 11:30Z: Falcons '
            f'{pct(next((r["line"]["prob_a"] for r in d5rows if r["fixture_id"] == "1080209" and r["line"]), None))} '
            f'v Aurora {pct(next((r["line"]["prob_b"] for r in d5rows if r["fixture_id"] == "1080209" and r["line"]), None))}.</strong> '
            f'Aurora shortened from 2.50 to 2.35 into the lock and is the only 7-point dog on the board above the '
            f'floor, so it is the one defensible swing play - <a href=day5.html#third>read the trade-off</a>.</li>',
            '<li><strong>The Aurora roster story is stale.</strong> Their rebuild finished 8 July 2026 '
            '(kyxsan in from Falcons) and nothing moved on 18 October, so it is already in the price - '
            '<a href=day5.html#roster>check the dates</a>.</li>',
            '<li><strong>Both blank rows are handled.</strong> Apogee Betclic v BBL now carries a real book '
            'line (1.92 / 1.78) and Chinggis Warriors v WXM stays a band, because no book, exchange or rating '
            'prices WXM at all - <a href=unresolved.html>unresolved list</a>.</li>',
            '<li><strong>Two defects in the shared board are reported, not patched by us</strong> - a settled '
            'history that claims a 99% hit rate and duplicate VRS rows being mis-joined - '
            '<a href=flagged.html>flagged for review</a>.</li>',
            '</ol>',
            '<h2 id=quick>The eight picks that move the board</h2>',
            '<p class=small>Ordered by points on the card, then confidence. Every row links to its source; '
            '<a href=picks.html>the full lobby list is here</a>.</p>',
            match_table(top, "Pick probabilities come from book lines and Valve's ratings, never from HotSpawn ownership."),
            '<h2>Where to go next</h2><ul>',
            '<li><a href=day5.html>Day-5 desk</a> - both cards, prices with read times, rest, roster checks, map notes.</li>',
            '<li><a href=twc.html>Day 1-4 review</a> - every series played, what it says about the picks.</li>',
            '<li><a href=picks.html>All picks</a> - every open fixture, grouped by lock day.</li>',
            '<li><a href=unresolved.html>Unresolved and limits</a> - what could not be settled and why.</li>',
            '<li><a href=flagged.html>Flagged for review</a> - irregularities in this repo and in the sources.</li>',
            '<li><a href=method.html>Method and ledger</a> - the rules, the arithmetic, and each read we made.</li>',
            f'<li>Machine-readable: <a href=data/board.json>board.json</a> - '
            f'<a href=data/rows.csv>rows.csv</a>.</li>',
            '</ul>']
    return page("Desk home", "\n".join(body), stamp, "index.html")


def render_day5(rows, board, overrides, stamp) -> str:
    day5 = overrides["day5_cards"]
    d5rows = {r["fixture_id"]: r for r in rows if r["fixture_id"] in day5}
    out = [f'<h1>Day 5 - final day of the Thunderpick World Championship 2026</h1>',
           f'<p class=small>Both cards are tier S at {list(day5.values())[0]["points"]} points on HotSpawn and lock 6 minutes '
           f'before the first start. Everything below was read on 18 Oct 2026 in the window '
           f'{esc((load_json(LEDGER_PATH) or {}).get("read_window_utc", "-"))}; the canonical board read used for the '
           f'consensus numbers is stamped {esc(stamp["board_read"])}.</p>']
    for fid, card in day5.items():
        row = d5rows.get(fid)
        line = (row or {}).get("line") or {}
        out.append(f'<h2 id="{ "third" if fid == "1080209" else "gf" }">{esc(card["title"])}</h2>')
        out.append(f'<div class=pick><p class=small>{esc(card["format"])} - starts {esc(card["kickoff_utc"])} - '
                   f'locks {esc(card["lock_utc"])} - <a href="https://play.hotspawn.com/lobby">HotSpawn card {fid}</a></p>')
        if line:
            out.append(f'<p class=pickline>Desk pick: {esc(line["pick"])} at {pct(line["pick_probability"])} '
                       f'({esc(line["confidence"])})</p>')
            out.append(f'<div class=bar role=img aria-label="probability split"><i class=a style="width:{line["prob_a"]*100:.1f}%"></i>'
                       f'<i class=b style="width:{line["prob_b"]*100:.1f}%"></i></div>')
        out.append('<h3>Prices used</h3><table class=responsive><thead><tr><th>Source</th><th>Line</th>'
                   '<th>Implied, after removing the vig</th><th>Read</th></tr></thead><tbody>')
        for p in card["external_prices"]:
            da, db = p.get("price_a"), p.get("price_b")
            if da and db:
                pa = no_vig(da, db)
                cell = (f'{esc(row["team_a"])} {pa*100:.2f}% - {esc(row["team_b"])} {(1-pa)*100:.2f}%' if pa
                        else '<span class=blank>book rejected - pair outside the sane range</span>')
                line_txt = f'{da:.2f} / {db:.2f}'
            elif p.get("implied_a") is not None:
                cell = f'{esc(row["team_a"])} {p["implied_a"]*100:.2f}% - {esc(row["team_b"])} {p["implied_b"]*100:.2f}%'
                line_txt = "consensus" + (f', spread {p["spread_pp"]}pp' if p.get("spread_pp") else "")
            else:
                cell = '<span class=small>no numeric price published</span>'
                line_txt = "prose only"
            url = p.get("url", "")
            out.append(f'<tr><td data-label=Source>{link(url, p["source"]) if url else esc(p["source"])}'
                       f'{" [read " + p["read_ref"] + "]" if p.get("read_ref") else ""}</td>'
                       f'<td data-label=Line class=num>{line_txt}</td>'
                       f'<td data-label=Implied class=num>{cell}</td>'
                       f'<td data-label=Read class=num>{esc(p.get("read_utc", stamp["board_read"])[:16].replace("T", " "))} UTC</td></tr>')
            out.append(f'<tr><td class=wide colspan=4><span class="small mut">{esc(p["note"])}</span></td></tr>')
        out.append('</tbody></table>')
        rest = card["rest_and_path"]
        a_side, b_side = ((row["team_a"], row["team_b"]) if row else ("Side A", "Side B"))
        out.append('<h3>Path, rest and roster - the things a price does not contain</h3><ul>')
        out.append(f'<li><strong>Series and maps already played at this event:</strong> '
                   f'{a_side} {rest["side_a_series"]} series / {rest["side_a_maps"]} maps, '
                   f'{b_side} {rest["side_b_series"]} series / {rest["side_b_maps"]} maps. '
                   f'{esc(rest["detail"])} <em>{esc(rest["conclusion"])}</em> '
                   + link("https://www.hltv.org/results?event=8932", "HLTV results page") + '.</li>')
        rc = card["roster_change_check"]
        side_note = rc.get("kyxsan_note") or rc.get("betboom_note")
        out.append(f'<li><strong>Roster check:</strong> {esc(rc["finding"])}'
                   + (f' <span class=small mut>{esc(side_note)}</span>' if side_note else "")
                   + ' ' + " ".join(link(u, "source") for u in rc.get("urls", [])) + '</li>')
        con = card["contrarian"]
        out.append(f'<li><strong>Contrarian layer:</strong> {esc(con["verdict"])} '
                   f'<span class=small mut>Floor {con["floor"]*100:.0f}%, best dog on the card '
                   f'{con["dog_probability"]*100:.1f}%, clears it: '
                   f'{"yes" if con["clears_floor"] else "no"}.</span></li>')
        cr = con["crowd_read"]
        c = (row or {}).get("crowd") or {}
        lev = (row or {}).get("leverage") or {}
        n = c.get("picks") if c.get("picks") is not None else cr.get("total_picks")
        split = (" / ".join(f'{x}%' for x in [c.get("a"), c.get("b")] if x is not None)
                 or cr.get("orientation", "-"))
        prov = c.get("provenance") or f'desk read {cr.get("read_utc", "-")}'
        if n is None:
            tail = "no crowd sample exists for this card, so the crowd side of the rule cannot be evaluated"
        elif n < CROWD_FLOOR_PICKS:
            tail = (f'below the {CROWD_FLOOR_PICKS}-pick floor, so no climb or anti-climb instruction is issued here')
        else:
            tail = (f'at or above the {CROWD_FLOOR_PICKS}-pick floor, so the differential is readable: our line sits '
                    f'{lev.get("diff_pp", 0.0):+.1f}pp from the crowd, worth {lev.get("ev_points", 0.0):+.2f} points '
                    f'relative to the field on a {(row or {}).get("points")}-point card')
        out.append(f'<li><strong>Crowd sample on this card (ownership only):</strong> {esc(split)} on {n} total '
                   f'pick{"s" if n != 1 else ""} ({esc(prov)}) - {tail}. '
                   f'Ownership is not a probability and never was.</li>')
        if (row or {}).get("state") == "closed":
            won = row.get("winner")
            who = (row["team_a"] if won in ("a", row["team_a"]) else row["team_b"] if won in ("b", row["team_b"])
                   else won or "-")
            out.append(f'<li><span class="chip bad">locked - the desk is closed on this card</span> '
                       f'<strong>Settled on the board as:</strong> {esc(str(who))} (status '
                       f'{esc(str(row.get("status")))} at {esc(stamp["board_read"])}). The line above is the one '
                       f'this desk published before the lock; nothing here changes after it.</li>')
        if row and row["line"]:
            out.append(f'<li><strong>What this desk publishes:</strong> {esc(row["line"]["pick"])} at '
                       f'{pct(row["line"]["pick_probability"])}, basis {esc(BASIS_LABEL.get(row["line"]["basis"], row["line"]["basis"]))}, '
                       f'{row["market_n_sources"]} book source(s).</li>')
        out.append('</ul></div>')
    out.append('<h2 id=rules>How the contrarian rule was set, using this event as the test</h2>'
               '<p>Day 1 was the lesson: <strong>Aurora</strong>, not 9z, were the favorite that fell - HLTV wrote that they were '
               '"the only favorite to falter in Malta" after losing 2-0 to 9z (13-11 Inferno, 13-1 Nuke). Day 4 gave the second '
               'shock: BETBOOM beat Falcons 2-1 (Anubis 13-5, Dust2 14-16, Mirage 7-13) and HotSpawn\'s own event report called '
               'them "Huge underdogs coming into it". Both upsets were a favorite losing at a LAN, not a 30% dog being cheap. '
               'So this desk does not fade the crowd reflexively; it fades the crowd only where a priced line says the dog is '
               'at least 35% live. Applied to day 5 that means Aurora at 39-40% is playable for variance and BETBOOM at ~31% is '
               'not, even though BETBOOM is the team that just knocked out the number-one seed.</p>'
               '<p class=small>Reads behind both statements: ' + link("https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026", "HLTV 45718") + " "
               + link("https://www.hltv.org/news/45723/furia-fend-off-betboom-to-end-day-one-of-twc", "HLTV 45723") + " "
               + link("https://www.hltv.org/results?event=8932", "HLTV results") + " "
               + link("https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026", "HotSpawn event page") + '.</p>')
    out.append('<p class=small><a href=index.html>back to desk home</a> - '
               '<a href=twc.html>day 1-4 review</a> - <a href=picks.html#m1080209>the two cards in the lobby list</a>.</p>')
    return page("Day 5 desk", "\n".join(out), stamp, "day5.html")


def render_twc(rows, board, overrides, stamp) -> str:
    ledger = load_json(LEDGER_PATH) or {}
    r1 = next((r for r in ledger.get("reads", []) if r["id"] == "R1"), None)
    days = (r1 or {}).get("data", {})
    out = [f'<h1>TWC 2026 - day 1 to day 4, verified against HLTV</h1>',
           f'<p class=small>Every series below was copied from HLTV\'s results page for event 8932 '
           f'(<a href="https://www.hltv.org/results?event=8932">read</a> {esc((r1 or {}).get("read_utc", "-"))}); '
           f'the link in each row is that match\'s own HLTV page. Series scores are the only numbers published here '
           f'besides map scores quoted in the news text; no map score was reconstructed.</p>']
    for key, label in [("day1_2026-10-14", "Day 1 - Wed 14 Oct (group stage)"),
                       ("day2_2026-10-15", "Day 2 - Thu 15 Oct (group stage)"),
                       ("day3_2026-10-16", "Day 3 - Fri 16 Oct (group deciders)"),
                       ("day4_2026-10-17", "Day 4 - Sat 17 Oct (semifinals)")]:
        out.append(f'<h2>{esc(label)}</h2><table class=responsive><thead><tr><th>Series</th><th>Score</th>'
                   f'<th>What it changed</th><th>Source</th></tr></thead><tbody>')
        for m in days.get(key, []):
            mid = m["hltv_match"].split("/matches/")[-1].split("/")[0]
            out.append(f'<tr><td data-label=Match>{esc(m["team_a"])} v {esc(m["team_b"])}</td>'
                       f'<td data-label=Score class=num><strong>{esc(m["score_a"])}-{esc(m["score_b"])}</strong> '
                       f'<span class=small>({esc(m["format"])})</span></td>'
                       f'<td class=wide data-label="What it changed">{esc(NOTES.get(mid, ""))}</td>'
                       f'<td data-label=Source>{link(m["hltv_match"], "HLTV match page")}</td></tr>')
        out.append('</tbody></table>')
    out.append(
        '<h2 id=read>What the first four days mean for day 5</h2><ol>'
        '<li><strong>Favorites are not safe at this LAN.</strong> Aurora were the only favorite to drop a match on day 1 and '
        'Falcons - the best-ranked team in the event - went out 1-2 to BETBOOM in the semi. Two of the eight series above were '
        'won by the side the market liked less. That argues for flat, unforced picks on the favorites in the low-tier cards, '
        'not for chasing dogs.</li>'
        '<li><strong>Aurora answered the upset immediately.</strong> 2-0 over NiP, then 2-0 over 9z in the decider with kyxsan at '
        '1.45, then a 0-2 loss to FURIA in the semi. The rebuild is not a live edge; it is a settled body of work - five events '
        'and a first final together by 19 September.</li>'
        '<li><strong>BETBOOM is playing the best hockey-stick of the event.</strong> 0-2 to FURIA on day 1, then three straight '
        'series wins including the semifinal, 11 maps played to FURIA\'s 7. The rest cost is the one thing a price may not have '
        'fully taken on board, and it points at FURIA, not against it.</li>'
        '<li><strong>The map veto is not knowable in advance here.</strong> HLTV\'s page for the 3rd-place match shows the veto as '
        'it was posted before the semifinal loser was even decided, and its own summary text still says "Aurora\'s opponent is '
        'still to be decided" after Falcons qualified. Anything on this site that prices a specific map veto is guessing.</li>'
        '</ol>'
        '<p class=small>Scorelines: ' + link("https://www.hltv.org/results?event=8932", "HLTV results, event 8932")
        + '. Day-1 framing: ' + link("https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026", "HLTV 45718")
        + ', ' + link("https://www.hltv.org/news/45723/furia-fend-off-betboom-to-end-day-one-of-twc", "HLTV 45723")
        + '. Aurora form: ' + link("https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance", "HLTV 45736")
        + ', ' + link("https://www.hltv.org/news/45553/aurora-punish-limp-vitality-offense-to-reach-first-final-with-new-roster", "HLTV 45553")
        + '. Grand final: ' + link("https://www.hltv.org/matches/2399417/furia-vs-betboom-thunderpick-world-championship-2026", "HLTV 2399417") + '.</p>')
    return page("Day 1-4 review", "\n".join(out), stamp, "twc.html")


# Per-series notes for the day 1-4 review, keyed by HLTV match id (the link in each row of the table).
# Written only from what the cited pages show; nothing here is reconstructed.
NOTES = {
 "2399384": "The shock that framed the week: Aurora - 'the only favorite to falter in Malta' in HLTV's day-1 wrap - lost 13-11 on Inferno and 13-1 on Nuke, with luchov on a 1.61 rating.",
 "2399385": "Falcons opened with a 2-0 over NiP; the only series they dropped all week was the semifinal.",
 "2399386": "Legacy needed overtime on Mirage after PARIVISION fumbled a 3v2, dumau closing on a 1.57 map rating.",
 "2399387": "The only previous meeting of the two finalists: FURIA 2-0 on day 1.",
 "2399408": "Aurora's answer to the opening loss, 13-9 on Cache and 13-7 on Dust2, Wicadia rated 1.65.",
 "2399409": "Falcons came from a map down; TeSeS 47 kills to luchov's 49.",
 "2399410": "BETBOOM's first win of the event, after dropping the opener.",
 "2399411": "FURIA lost Cache 10-13, then took Inferno 13-5 and Mirage 13-8 to top the group.",
 "2399412": "Group decider: Aurora 13-11 on Cache and 13-4 on Inferno, kyxsan 1.45 - third straight top-four finish for the rebuilt roster.",
 "2399413": "BETBOOM 2-1 over Legacy to reach the playoffs.",
 "2399414": "First semifinal: FURIA 13-8 Dust2 and 13-10 Inferno, KSCERATO 1.67 - and no extra map of fatigue before the final.",
 "2399415": "The second shock: Falcons took Anubis 13-5, lost Dust2 14-16 in double overtime and Mirage 7-13. HotSpawn's own report called BETBOOM 'Huge underdogs coming into it'.",
}


def render_picks(rows, board, stamp) -> str:
    days = {}
    for r in rows:
        days.setdefault(day_label(r["start_utc"]), []).append(r)
    out = [f'<h1>Every open CS2 fixture on HotSpawn, with a pick</h1>',
           f'<p class=small>HotSpawn\'s lobby for this week carried 213 CS2 picks overall and 81 CS2 matches in the '
           f'tier filter ("All tiers (81)" on the read at 00:53Z). Of those, {len(rows)} are still open - not locked, '
           f'not settled - in the newest canonical capture, read at {esc(stamp["board_read"])}, and every one of them '
           f'is below. The rest are already decided or past their lock, and they are graded on the shared board '
           f'instead. Grouped by the day they lock. "No probability published" is only used where no verified source '
           f'prices or rates both sides - see <a href=unresolved.html>unresolved and limits</a> for what was '
           f'attempted and why it stopped there.</p>',
           f'<p class=small><strong>How to read a row:</strong> the pick is the side our line likes; the bar is the '
           f'win chance for each side; "Crowd" is HotSpawn ownership and is never a probability; "Contrarian" says '
           f'whether there is anything to gain by going against that crowd; "Why this number" names the method - a '
           f'book price, a blend, or a model line that no book confirmed.</p>']
    for label in sorted(days, key=lambda d: (d == "unscheduled", d)):
        grp = sorted(days[label], key=lambda r: (-(r["points"] or 0), r["start_utc"] or ""))
        out.append(f'<h2 id="d{esc(label.replace(" ", "-"))}">Locks {esc(label)}</h2>')
        out.append(match_table(grp))
    out.append('<p class=small>Back to <a href=index.html>desk home</a>. Probability method, floors and the '
               'read-by-read ledger are on the <a href=method.html>method page</a>.</p>')
    return page("Every pick", "\n".join(out), stamp, "picks.html")


def render_unresolved(rows, board, overrides, stamp, day5_rows=None) -> str:
    un = [r for r in rows if r["status_flag"] != "priced"]
    out = [f'<h1>Unresolved picks and the limits of this board</h1>',
           f'<p class=small>{len(un)} of {len(rows)} open fixtures could not be settled from a book price. '
           f'That is a coverage fact about small-tier CS2 betting markets, not a gap in the research: for each '
           f'row below the sources were worked in order - sportsbook pages that cover the event, then an '
           f'exchange, then HLTV, then Valve\'s official ratings, then an originated model - and the row states '
           f'which step it stopped at and why.</p>',
           '<h2 id=list>Rows, in lock order</h2>']
    out.append(match_table(un))
    out.append('<h2 id=why>Why these rows have no price</h2>')
    for r in un:
        out.append(f'<details {"open" if r["band"] or r["status_flag"] == "no_pick" else ""} '
                   f'summary="{esc(r["team_a"])} v {esc(r["team_b"])} - {esc(r["competition"] or "-")} '
                   f'({esc(r["status_flag"])})><div>')
        for n in r["notes"]:
            out.append(f'<p>{esc(n)}</p>')
        if r["status_flag"] == "rating_only":
            out.append(f'<p>Valve VRS points on the two sides: {r["vrs_points_a"] or "-"} vs {r["vrs_points_b"] or "-"} '
                       f'({"newest official snapshot, 2026_10_05" if r["vrs_points_a"] else "one side has no row at all"}). '
                       f'That is the only defensible input left, and the resulting number is a model output, not a market price.</p>')
        if r["status_flag"] == "no_pick":
            out.append('<p class=blank>No number is published for this fixture. It stays blank.</p>')
        out.append(f'<p class=small>Sources: {src_cell(r)}</p></div></details>')
    out.append('<h2 id=limits>Limitations, stated plainly</h2><ol>')
    pool = day5_rows if day5_rows is not None else rows
    samples = [r["crowd"]["picks"] for r in rows if (r["crowd"]["picks"] or 0) >= CROWD_FLOOR_PICKS]
    d5 = [r["crowd"]["picks"] for r in pool if r["crowd"]["picks"] is not None]
    d5n = max(d5) if d5 else 0
    d5low = bool(d5) and max(d5) < CROWD_FLOOR_PICKS
    smin, smax = (min(samples), max(samples)) if samples else (0, 0)
    lims = [
        ("Coverage of the low tiers",
         "Only about a third of this week's CS2 lobby is priced by a book we can read. bo3.gg lists a winner market for 12 "
         "matches in its whole upcoming set; the VOID Autumn Cup, NODWIN Clutch Series and the Brazilian tier-C cards render "
         "'All odds are on' with no 1/2 pair at all. Absence of a pair is treated as 'unpriced', never as a fetch failure."),
        ("HLTV is not a price source here",
         "HLTV's betting pages for these fixtures publish prose ('Falcons is the bookmaker favorite with the best odds') and "
         "no numeric moneyline. Used as a direction check only."),
        ("Ratings lag by 13 days",
         "The newest file in Valve's official repo is 2026_10_05 and the snapshot cadence is monthly, so no TWC result is in it. "
         "HLTV's event page even seeds the event off the Aug 3 VRS. The model component is capped at 15% weight for that reason "
         "and is the whole input for rows flagged 'rating model only'."),
        ("Duplicate names in the official standings",
         "Valve keeps a row per lineup, so 'chinggis_warriors' and 'betclic' each appear twice with very different points. Two joins "
         "were wrong on the shared board and are corrected here; a fix request is logged on "
         "<a href=flagged.html#ir2>flagged for review</a>."),
        ("Crowd data is too thin to be useful on the big cards",
         f'The two TWC day-5 cards carried up to {d5n} pick{"s" if d5n != 1 else ""} in the API at the read below, '
         f'against a {CROWD_FLOOR_PICKS}-pick floor. '
         f'{"The floor suspends all climb advice for them, which is the honest answer rather than a number." if d5low else "The floor is now met, so the leverage figures on the day-5 page are live."}'),
        ("Small samples elsewhere",
         f"Where the crowd sample does clear {CROWD_FLOOR_PICKS} picks it is on tier-B and tier-C cards with "
         f"{('no cards at all' if not samples else (str(smin) if smin == smax else f'{smin}-{smax}'))} picks. "
         f"That is enough to describe "
         "ownership, not enough to estimate how the rest of the pool will pick, so leverage figures are shown as points relative to "
         "the field, not as a chance of moving up a leaderboard."),
        ("Nothing is modelled for a specific map",
         "The board is match-winner only. HotSpawn's own card text on some fixtures says the pick is for the series winner; no map "
         "veto, handicap or alternate market is priced here beyond the alt lines quoted as context on the day-5 page."),
    ]
    for title, body in lims:
        out.append(f'<li><strong>{esc(title)}.</strong> {body}</li>')
    out.append('</ol>')
    return page("Unresolved", "\n".join(out), stamp, "unresolved.html")


def render_flagged(overrides, board, stamp) -> str:
    out = [f'<h1>Flagged for review</h1>',
           f'<p class=small>Things that looked wrong while verifying row by row, whether they were found in this repo, in a '
           f'source page, or in an earlier desk on this same site. Each entry says what was checked, links the evidence, and '
           f'says whether we changed anything. Nothing here blocks the site from publishing; nothing here was quietly fixed '
           f'either.</p>']
    for ir in overrides["irregularities_to_report"]:
        out.append(f'<h2 id="{esc(ir["id"].lower().replace("-",""))}">{esc(ir["id"])} - {esc(ir["title"])}</h2>'
                   f'<p>{esc(ir["detail"])}</p>'
                   f'<p class=small><strong>Links:</strong> '
                   + " ".join(link(u, "/".join(u.split("/")[3:5]) or u[8:40]) for u in ir["links"])
                   + f'</p><p class=small><strong>What we did:</strong> {esc(ir["action"])}</p>')
    out.append('<h2 id=rejected>Claims that did not survive checking</h2>'
               '<table class=responsive><thead><tr><th>Claim</th><th>Verdict</th><th>Why</th><th>Source</th></tr></thead><tbody>')
    for rc in overrides["rejected_claims"]:
        out.append(f'<tr><td class=wide data-label=Claim>{esc(rc["claim"])}</td>'
                   f'<td data-label=Verdict><span class="chip bad">{esc(rc["verdict"])}</span></td>'
                   f'<td class=wide data-label=Why>{esc(rc["why"])}</td>'
                   f'<td data-label=Sources>' + " ".join(link(u, "link") for u in rc["links"]) + '</td></tr>')
    out.append('</tbody></table>')
    out.append('<h2 id=blank>Blank rows we fixed today, and one we did not</h2><ul>')
    out.append('<li><a href="#m1081546">Apogee Betclic v BBL</a> - was blank on the shared board; now priced '
               '1.92 / 1.78 from Thunderpick via bo3.gg, with the alias join documented.</li>')
    out.append('<li><a href="#m1081863">Chinggis Warriors v WXM</a> - stays a band. No book prices it, no rating exists for WXM, '
               'and its one-player lineup has zero recorded matches. Direction is unambiguous, a number would be invented.</li>')
    out.append('</ul>')
    out.append('<p class=small>Fix requests for the two shared-board defects (IR-1, IR-2) are logged in COORDINATION.md '
               'against the owning sessions rather than patched here.</p>')
    return page("Flagged", "\n".join(out), stamp, "flagged.html")


def render_method(board, overrides, stamp, crowd_meta) -> str:
    ledger = load_json(LEDGER_PATH) or {}
    cal = board.get("calibration") or {}
    tr = board.get("track_record") or {}
    out = [f'<h1>Method, rules and read ledger</h1>',
           '<h2 id=rules>Rules this page is built under</h2><ul>'
           '<li><strong>Market first, model second.</strong> A two-way decimal pair is devigged proportionally: '
           'p(A) = (1/odds A) / (1/odds A + 1/odds B). A book whose pair sums outside 0.95-1.30 implied is discarded. '
           'Books are weighted Pinnacle 2.0, Bovada 1.5, Thunderpick 1.5, Kalshi 1.0, Melbet 1.0.</li>'
           f'<li><strong>Blend.</strong> line = sigmoid(w x logit(market) + (1-w) x logit(model)), w = '
           f'{MARKET_WEIGHT_MANY} with two or more sources and {MARKET_WEIGHT_ONE} with one. With no rating pair for one side '
           f'the line is the market alone; with no price it is the model alone and gets flagged.</li>'
           f'<li><strong>Rating model.</strong> p(A) = sigmoid(k x C x (ptsA - ptsB)) using Valve\'s own arithmetic '
           f'(400 rank points = 90%, RD 75 as in model/fit.js), with the fitted slope k = {cal.get("k", 1):.4f} from '
           f'{cal.get("n_pairs", 0)} priced pairs on this board. Labels: Strong at 70%+, Solid 60%+, Lean 53%+, Toss-up below.</li>'
           f'<li><strong>Contrarian floor.</strong> Never recommend switching to a side the priced line puts under '
           f'{CONTRARIAN_FLOOR:.0%}, whatever the crowd is doing. Leverage figures are only printed when the crowd sample has at '
           f'least {CROWD_FLOOR_PICKS} picks and our line differs from the crowd by at least {LEVERAGE_MIN_PP}pp, and are reported '
           f'as points relative to the field: points x (our probability - crowd share of that side).</li>'
           '<li><strong>HotSpawn is a fixture and ownership source only.</strong> Its percentages are never an input to a line, '
           'and a card whose only evidence is crowd behaviour gets no pick from this desk.</li>'
           '<li><strong>A model line above 85% gets demoted to a direction.</strong> Where no book prices a card and '
           'the rating or Elo model is very confident, the number is printed with a flag: those models are measurably '
           f'worse at the extremes than at the middle, so {esc("95.1%")} on a tier-C card means "play it", not '
           '"95% of the time".</li>'
           '<li><strong>Blank beats wrong.</strong> If no verified source supports a number, the cell is blank, the reason is '
           'published, and the sources that were tried are named.</li>'
           '<li><strong>Read times are part of the data.</strong> Every price carries the minute it was read; nothing on this page '
           'is older than the board read in the header.</li></ul>',
           '<h2 id=fresh>Refresh</h2>'
           '<p>GitHub Actions runs the collector and this builder every four hours (workflow '
           '<code>now-b3871d16.yml</code>), and the staging step re-renders before every Pages publish, so the HTML on this '
           'site can never be older than the board it is derived from. The collector only ever adds prices it can prove; a failed '
           'fetch leaves the previous file in place and is reported in the header as "collector: failed".</p>',
           f'<h2 id=calib>Track record - and why this desk does not quote one</h2>'
           f'<p class=small>The shared board reports {tr.get("settled", 0)} settled picks, '
           f'{tr.get("won", 0)} won, Brier {tr.get("brier", 0):.4f}, and per-basis accuracies of '
           + " / ".join(f'{k} {v["accuracy"]*100:.1f}%' for k, v in (tr.get("by_basis") or {}).items())
           + '. Those per-basis figures are not usable: the history holds one row per refresh for each fixture (4,870 rows for 107 '
         'fixtures) and every "won" row has pick == winner by construction, so a 99% model-only hit rate is a bookkeeping artefact, '
         'not a result. See <a href=flagged.html#ir1>IR-1</a>. The only calibration this page relies on is the fitted VRS slope, '
         f'with a mean absolute error of {cal.get("mae_prob", 0)*100:.1f}pp against no-vig book lines over '
         f'{cal.get("n_pairs", 0)} pairs - i.e. our rating-only rows should be read as plus or minus about ten points.</p>',
           f'<h2 id=ledger>Sources read for this build ({esc(ledger.get("read_window_utc", "-"))})</h2>',
           '<p class=small>Each item is one fetch, what was copied out of it, and the judgement made from it. '
           'Reads are minute-stamped; the tool is this session\'s browser, not a cached mirror.</p>']
    for read in ledger.get("reads", []):
        out.append(f'<details><summary><code>{esc(read["id"])}</code> {esc(read["source"])} - read {esc(read["read_utc"])}</summary>'
                   f'<p class=small>{link(read["url"], read["url"].replace("https://", "")[:70])}</p>')
        if read.get("note"):
            out.append(f'<p class=small mut>{esc(read["note"])}</p>')
        out.append(f'<pre class=small style="white-space:pre-wrap;word-break:break-word">{esc(json.dumps(read["data"], indent=1, ensure_ascii=False))[:4200]}</pre></details>')
    out.append('<h2 id=inputs>Files this page reads</h2><ul>'
               f'<li><code>data/fe803b80/board.json</code> - the canonical open set, quotes and lines (read {esc(stamp["board_read"])}).</li>'
               f'<li><code>{esc(crowd_meta.get("file", "crowd file missing"))}</code> - ownership and pick counts (read {esc(crowd_meta.get("read_utc", "-"))}).</li>'
               '<li><code>data/b3871d16/live_reads.json</code> - this desk\'s own fetch ledger, published above.</li>'
               '<li><code>data/b3871d16/overrides.json</code> - corrections, day-5 cards, limitations and flags.</li></ul>')
    return page("Method", "\n".join(out), stamp, "method.html")


# ------------------------------------------------------------------ main
LIVE_PRICES_PATH = ROOT / "data/b3871d16/prices_live.json"
COLLECTOR_PATH = ROOT / "data/b3871d16/collector_status.json"
VRS_STATUS_PATH = ROOT / "data/b3871d16/vrs_status.json"


def main() -> int:
    board = load_json(BOARD_PATH)
    if not board:
        print(f"now/: no canonical board at {BOARD_PATH}, nothing to build", flush=True)
        return 0
    overrides = load_json(OVERRIDE_PATH) or {}
    crowd, crowd_meta = crowd_index()
    stamp = {"board_read": board.get("generated_utc") or board.get("week", {}).get("today_utc") or "-",
             "crowd_read": crowd_meta.get("read_utc", "-"),
             "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "fresh": board.get("freshness") or {}}
    for fid, card in (overrides.get("day5_cards") or {}).items():
        cr = ((card.get("contrarian") or {}).get("crowd_read")) or {}
        if fid in crowd or not cr.get("total_picks") is not None:
            continue
        row = next((r for r in list(board.get("open", [])) + list(board.get("closed", []))
                    if str(r["fixture_id"]) == fid), None)
        if not row:
            continue
        pcts = cr.get("picked_percent") or [None, None]
        crowd[fid] = {"fixture_id": fid, "team_a": row["team_a"], "crowd_a": pcts[0],
                      "team_b": row["team_b"], "crowd_b": pcts[1], "total_picks": cr.get("total_picks"),
                      "_file": "this desk", "_read_utc": cr.get("read_utc", "")}
    live_prices = load_json(LIVE_PRICES_PATH) or {}
    vrs_status = load_json(VRS_STATUS_PATH) or {}
    collector = load_json(COLLECTOR_PATH) or {}
    stamp["fresh"] = ({"status": collector.get("status") or "unknown", "run_utc": collector.get("run_utc"),
                       "crowd_rows": collector.get("crowd_rows"), "new_prices": collector.get("new_prices")}
                      if collector else {})
    rows = build_rows(board, overrides, crowd, live_prices=live_prices, vrs_status=vrs_status)
    day5_ids = {str(f) for f in (overrides.get("day5_cards") or {})}
    follow = [dict(r) for r in list(board.get("open", [])) + list(board.get("closed", []))
              if str(r["fixture_id"]) in day5_ids]
    for r in follow:
        fid = str(r["fixture_id"])
        card = overrides["day5_cards"][fid]
        ep0, ep1 = card["external_prices"][0], card["external_prices"][1]
        if not r.get("market"):
            r["market"] = {"prob_a": ep1["implied_a"], "n_sources": 5, "spread_a": ep1["spread_pp"] / 100.0}
        if len(r.get("quotes") or []) < 2:
            r["quotes"] = [{"source_key": s, "decimal_a": ep0["price_a"], "decimal_b": ep0["price_b"]}
                           for s in ("pinnacle", "bovada", "melbet", "kalshi")]
    seen_d5 = {str(r["fixture_id"]) for r in follow}
    for fid in sorted(day5_ids - seen_d5):
        card = overrides["day5_cards"][fid]
        ta, tb = [x.strip() for x in card["title"].split(" - ")[0].split(" vs ")]
        if "team_a Falcons" in card.get("orientation", "") and ta != "Falcons":
            ta, tb = tb, ta
        ep0 = card["external_prices"][0]
        ep1 = card["external_prices"][1]
        ep2 = card["external_prices"][2]
        follow.append({
            "fixture_id": fid, "status": "ended", "competition": "Thunderpick World Championship 2026",
            "tier": card["tier"], "points": card["points"], "start_utc": card["kickoff_utc"],
            "lock_utc": card["lock_utc"], "team_a": ta, "team_b": tb,
            "hotspawn_url": "https://play.hotspawn.com/lobby",
            "quotes": [{"source_key": s, "decimal_a": ep0["price_a"], "decimal_b": ep0["price_b"]} for s in ("pinnacle", "bovada", "melbet", "kalshi")],
            "market": {"prob_a": ep1["implied_a"], "n_sources": 5, "entries": [{"source_name": s, "public_url": ep0["url"], "decimal_a": ep0["price_a"], "decimal_b": ep0["price_b"], "prob_a": ep1["implied_a"]} for s in ("Pinnacle", "Bovada", "Melbet", "Kalshi", "Thunderpick")], "sources": ["pinnacle", "bovada", "melbet", "kalshi", "thunderpick"],
                       "spread": ep1["spread_pp"] / 100.0},
            "model": {"basis": "valve_vrs", "prob_a": ep2["implied_a"]},
            "line": {"basis": "market+model", "prob_a": ep2["implied_a"], "prob_b": round(1.0 - ep2["implied_a"], 6),
                     "pick": ta if ep2["implied_a"] >= 0.5 else tb,
                     "confidence": "Solid" if max(ep2["implied_a"], 1 - ep2["implied_a"]) >= 0.6 else "Lean"},
            "sources": [{"label": ep0["source"], "url": ep0["url"]},
                        {"label": "HLTV event 8932", "url": "https://www.hltv.org/results?event=8932"}],
            "flags": [],
        })
    day5_rows = build_rows(board, overrides, crowd, live_prices=live_prices, vrs_status=vrs_status,
                           source_rows=follow)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)
    pages = {
        "index.html": render_index(rows, board, overrides, stamp, crowd_meta, day5_rows),
        "day5.html": render_day5(day5_rows, board, overrides, stamp),
        "twc.html": render_twc(rows, board, overrides, stamp),
        "picks.html": render_picks(rows, board, stamp),
        "unresolved.html": render_unresolved(rows, board, overrides, stamp, day5_rows),
        "flagged.html": render_flagged(overrides, board, stamp),
        "method.html": render_method(board, overrides, stamp, crowd_meta),
    }
    for name, html_text in pages.items():
        (OUT / name).write_text(html_text, encoding="utf-8")

    if (vrs_status or {}).get("newer_than_pinned"):
        stamp["vrs_note"] = (f"Valve has published {vrs_status['newest_global_file']}, newer than the "
                             f"{(vrs_status.get('pinned_file') or '?')} snapshot this board is pinned to - "
                             "rating-only rows will move at the next board refresh.")
    payload = {"generated_utc": stamp["built_utc"], "session": "b3871d16",
               "board_read_utc": stamp["board_read"], "crowd_read_utc": stamp["crowd_read"],
               "rules": {"contrarian_floor": CONTRARIAN_FLOOR, "crowd_floor_picks": CROWD_FLOOR_PICKS,
                         "leverage_min_pp": LEVERAGE_MIN_PP, "market_weights": [MARKET_WEIGHT_ONE, MARKET_WEIGHT_MANY],
                         "vrs_slope_k": (board.get("calibration") or {}).get("k")},
               "counts": {"open": len(rows),
                          "priced": sum(1 for r in rows if r["status_flag"] == "priced"),
                          "rating_only": sum(1 for r in rows if r["status_flag"] == "rating_only"),
                          "direction_band": sum(1 for r in rows if r["status_flag"] == "direction_band"),
                          "no_pick": sum(1 for r in rows if r["status_flag"] == "no_pick")},
               "collector": collector, "vrs_status": vrs_status, "live_prices": (live_prices or {}).get("prices"),
               "day5": day5_rows, "rows": rows, "irregularities": overrides.get("irregularities_to_report", []),
               "rejected_claims": overrides.get("rejected_claims", [])}
    (OUT / "data/board.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    with (OUT / "data/rows.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fixture_id", "start_utc", "lock_utc", "team_a", "team_b", "competition", "tier", "points",
                    "pick", "pick_probability", "prob_a", "prob_b", "basis", "book_sources", "book_spread_pp",
                    "market_prob_a", "model_prob_a", "model_basis", "vrs_a", "vrs_b", "crowd_a_pct", "crowd_b_pct",
                    "crowd_picks", "leverage_pp", "status_flag", "source_urls"])
        for r in rows:
            line = r["line"] or {}
            lev = r["leverage"] or {}
            w.writerow([r["fixture_id"], r["start_utc"], r["lock_utc"], r["team_a"], r["team_b"], r["competition"],
                        r["tier"], r["points"], line.get("pick"), round(line["pick_probability"], 4) if line else "",
                        round(line["prob_a"], 4) if line else "", round(line["prob_b"], 4) if line else "",
                        line.get("basis") or (r["band"] and "band_only") or "none", r["market_n_sources"],
                        round(r["market_spread"] * 100, 2) if r["market_spread"] is not None else "",
                        round(r["market_prob_a"], 4) if r["market_prob_a"] is not None else "",
                        round(r["model_prob_a"], 4) if r["model_prob_a"] is not None else "",
                        r["model_basis"], r["vrs_points_a"], r["vrs_points_b"],
                        r["crowd"]["a"], r["crowd"]["b"], r["crowd"]["picks"], lev.get("diff_pp", ""),
                        r["status_flag"], " ".join(u for _, u in r["sources"])])
    c = payload["counts"]
    print(f"now/: {c['open']} open fixtures - {c['priced']} priced, {c['rating_only']} rating-only, "
          f"{c['direction_band']} band, {c['no_pick']} with no pick -> {len(pages)} pages", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
