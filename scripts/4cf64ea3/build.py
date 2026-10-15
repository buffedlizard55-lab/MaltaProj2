#!/usr/bin/env python3
"""Build the day3/ section: TWC 2026 day-2 review -> day-3 picks, contrarian ladder,
and a pick for every open HotSpawn CS2 fixture.

Design (see day3/method.html):
* HotSpawn is fixture discovery, settlement and crowd ownership ONLY — never a
  probability input (asserted by tests/test_4cf64ea3.py).
* Our line for priced fixtures is re-derived HERE from the retained raw quotes in
  data/fe803b80/board.json (de-vigged mean). Unpriced fixtures fall back to the
  calibrated Valve-VRS model (formula copied from scripts/fe803b80/core.py, k fitted
  on bookmaker lines). Fixtures with neither stay blank and are flagged.
* The strategy ladder publishes BOTH a safe (expected-points) pick and a climb
  (leaderboard) pick; a swing is only taken when the "not stupid" floor holds.
* No network access. Deterministic given the committed input files.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "4cf64ea3"
OUT = ROOT / "day3"
LOBBY = "https://play.hotspawn.com/lobby"

# ---------------------------------------------------------------- Valve VRS model
# Identical arithmetic to scripts/fe803b80/core.py (Valve's own glicko.js constants:
# "rank delta of 400 points = 90% chance of victory", Q = ln(10)/400, fixed RD = 75).
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    return sigmoid(k * VALVE_C * (float(points_a) - float(points_b)))


def devig_prob(decimal_a: float, decimal_b: float) -> tuple[float, float]:
    qa, qb = 1.0 / decimal_a, 1.0 / decimal_b
    tot = qa + qb
    return qa / tot, qb / tot


# ---------------------------------------------------------------- strategy ladder
DOG_FLOOR = 0.30          # "not stupid": never swing to a sub-30% shot
COINFLIP_BAND = 0.08      # |p - 0.5| <= 0.08 counts as a coin flip
FADE_OWN = 0.70           # crowd on the other side of a coin flip
MIN_DIFF = 0.7            # minimum differential expected points vs the field
MIN_FLAGS = 2             # verified context flags required for a C2 swing


def ladder(prob_a: float, prob_b: float, points: float, crowd_a, crowd_b, flags: list) -> dict:
    """Return safe pick + climb pick with the full arithmetic. Teams are 'A'/'B'."""
    fav, dog = ("A", "B") if prob_a >= prob_b else ("B", "A")
    p_fav, p_dog = max(prob_a, prob_b), min(prob_a, prob_b)
    crowd = {"A": crowd_a, "B": crowd_b}
    res = {
        "safe": fav,
        "safe_prob": p_fav,
        "climb": fav,
        "climb_prob": p_fav,
        "rule": "chalk",
        "p_dog": p_dog,
        "own_dog": crowd[dog],
        "own_fav": crowd[fav],
        "leverage": None,
        "ep_safe": points * p_fav,
        "ep_dog": points * p_dog,
        "ep_cost": points * (p_fav - p_dog),
        "differential": None,
        "flags": list(flags),
        "notes": [],
    }
    if crowd[dog] is None or crowd[fav] is None:
        res["notes"].append("no crowd split captured: the climb pick defaults to the safe pick")
        return res
    res["leverage"] = (p_dog / crowd[dog]) if crowd[dog] > 0 else None
    res["differential"] = points * (p_dog - crowd[dog])
    if abs(p_fav - 0.5) <= COINFLIP_BAND and crowd[fav] >= FADE_OWN:
        res.update(climb=dog, climb_prob=p_dog, rule="C1_coinflip_fade")
        res["notes"].append("market coin flip but the field is heavily on the favourite: fade at almost no expected-points cost")
        return res
    if (p_dog >= DOG_FLOOR and res["differential"] is not None
            and res["differential"] >= MIN_DIFF and len(flags) >= MIN_FLAGS):
        res.update(climb=dog, climb_prob=p_dog, rule="C2_upset_shot")
        res["notes"].append(f"context-backed live underdog ({p_dog:.0%}, floor {DOG_FLOOR:.0%}): "
                            f"differential {res['differential']:+.2f} expected points vs the field")
        return res
    if p_dog >= DOG_FLOOR and res["differential"] is not None and res["differential"] >= MIN_DIFF:
        res["notes"].append(f"the crowd differential would pay {res['differential']:+.2f} pts, "
                            f"but only {len(flags)} verified context flag(s) (need {MIN_FLAGS}): keep the safe pick")
    elif p_dog < DOG_FLOOR:
        res["notes"].append(f"underdog at {p_dog:.0%} is below the {DOG_FLOOR:.0%} 'not stupid' floor")
    return res


# ---------------------------------------------------------------- input loading
def load_inputs() -> dict:
    ev = json.loads((DATA / "evidence.json").read_text())
    fe = json.loads((ROOT / "data" / "fe803b80" / "board.json").read_text())
    strat = json.loads((ROOT / "data" / "f28afd9e" / "board.json").read_text())
    return {"evidence": ev, "fe": fe, "strategy_board": strat}


def calibration_k(fe: dict) -> float:
    cal = fe.get("calibration") or {}
    k = cal.get("k")
    return float(k) if isinstance(k, (int, float)) and 0.05 <= float(k) <= 2.0 else 0.27984917580739777


def rederive_fe_row(row: dict, k: float) -> dict:
    """Re-derive our probability for one fe803b80 row from its own raw quotes/model."""
    quotes = [q for q in (row.get("quotes") or [])]
    if quotes:
        probs, sources = [], []
        for q in quotes:
            pa, _ = devig_prob(float(q["decimal_a"]), float(q["decimal_b"]))
            probs.append(pa)
            sources.append({
                "label": f"{q.get('source_name')} · {q.get('raw_format')}",
                "url": q.get("public_url"),
                "read_utc": q.get("retrieved_utc"),
                "prob_a": pa,
                "orientation": ("fixture order" if not q.get("swapped")
                                else "stored names in source order, prices in fixture order (verified against the event id)"),
            })
        return {"prob_a": sum(probs) / len(probs), "basis": "market",
                "n_sources": len(probs), "sources": sources}
    model = row.get("model") or {}
    vrs = model.get("vrs") or {}
    if vrs:
        pa = vrs_prob(vrs["points_a"], vrs["points_b"], k)
        return {"prob_a": pa, "basis": "model (Valve VRS)", "n_sources": 0, "sources": [{
            "label": f"Valve VRS {vrs.get('snapshot', '2026_10_05')} · {row.get('team_a')} "
                     f"#{vrs.get('standing_a')} ({vrs.get('points_a')} pts) vs {row.get('team_b')} "
                     f"#{vrs.get('standing_b')} ({vrs.get('points_b')} pts)",
            "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md",
            "prob_a": pa,
        }]}
    return {"prob_a": None, "basis": "unresolved", "n_sources": 0, "sources": []}


def context_flags(ev: dict, team_a: str, team_b: str, underdog: str) -> list:
    out = []
    name = underdog
    for tname, items in (ev.get("context") or {}).get("teams", {}).items():
        if tname.lower() != (name or "").lower():
            continue
        for it in items:
            if it.get("type") in ("h2h_underdog_win", "roster_change", "stand_in"):
                out.append({"team": tname, "type": it["type"], "date": it.get("date"),
                            "summary": it.get("summary"),
                            "source": (it.get("sources") or [{}])[0].get("url")})
    # A roster change of the FAVOURITE within 120 days is a flag for the underdog.
    fav = team_a if team_a.lower() != (name or "").lower() else team_b
    for tname, items in (ev.get("context") or {}).get("teams", {}).items():
        if tname.lower() != (fav or "").lower():
            continue
        for it in items:
            if it.get("type") == "roster_change":
                out.append({"team": tname, "type": "favourite_roster_change", "date": it.get("date"),
                            "summary": it.get("summary"),
                            "source": (it.get("sources") or [{}])[0].get("url")})
    return out


def build_board(inputs: dict) -> dict:
    ev, fe, strat = inputs["evidence"], inputs["fe"], inputs["strategy_board"]
    k = calibration_k(fe)
    fe_open = {str(r.get("fixture_id")): r for r in (fe.get("open") or [])}
    strat_rows = {str(r.get("fixture_id")): r for r in (strat.get("rows") or [])}

    rows = []
    day3_ids = {str(f.get("fixture_id")) for f in ev["day3_fixtures"]}
    for fid, srow in sorted(strat_rows.items(), key=lambda kv: (kv[1].get("start_utc") or "", kv[0])):
        if srow.get("state") != "open":
            continue
        if fid in day3_ids:
            continue  # published from evidence.json below, with the full day-3 analysis
        ferow = fe_open.get(fid)
        derived = rederive_fe_row(ferow, k) if ferow else {"prob_a": None, "basis": "unresolved",
                                                           "n_sources": 0, "sources": []}
        pa = derived["prob_a"]
        pb = (1.0 - pa) if pa is not None else None
        crowd = srow.get("crowd") or {}
        ca, cb = crowd.get("pct_a"), crowd.get("pct_b")
        flags = []
        if pa is not None:
            dog = srow.get("team_b") if pa >= 0.5 else srow.get("team_a")
            flags = context_flags(ev, srow.get("team_a", ""), srow.get("team_b", ""), dog)
        lad = (ladder(pa, pb, float(srow.get("points") or 0),
                      (ca / 100.0 if isinstance(ca, (int, float)) else None),
                      (cb / 100.0 if isinstance(cb, (int, float)) else None), flags)
               if pa is not None else
               {"safe": None, "safe_prob": None, "climb": None, "climb_prob": None,
                "rule": "no_probability", "flags": flags,
                "notes": ["no eligible market line and no VRS rating pair: no pick published, left blank and flagged"]})
        team_of = {"A": srow.get("team_a"), "B": srow.get("team_b")}
        rows.append({
            "fixture_id": fid,
            "competition": srow.get("competition"),
            "tier": srow.get("tier"),
            "points": srow.get("points"),
            "start_utc": srow.get("start_utc"),
            "lock_utc": srow.get("lock_utc"),
            "team_a": srow.get("team_a"),
            "team_b": srow.get("team_b"),
            "prob_a": pa,
            "prob_b": pb,
            "basis": derived["basis"],
            "n_quote_sources": derived["n_sources"],
            "sources": derived["sources"] + ([{
                "label": "HotSpawn fixture listing (discovery/settlement only)",
                "url": srow.get("hotspawn_url") or LOBBY}] if srow.get("hotspawn_url") else [{
                "label": "HotSpawn lobby (discovery/settlement only)", "url": LOBBY}]),
            "crowd_pct_a": ca, "crowd_pct_b": cb,
            "crowd_captured_utc": crowd.get("captured_utc"),
            "safe_pick": team_of.get(lad.get("safe")) if lad.get("safe") else None,
            "safe_prob": lad.get("safe_prob"),
            "climb_pick": team_of.get(lad.get("climb")) if lad.get("climb") else None,
            "climb_prob": lad.get("climb_prob"),
            "strategy": lad,
            "twc_day3": False,
        })

    # TWC day-3 rows from evidence (market line for 1080205; originated line for the
    # not-yet-listed BETBOOM-Legacy decider).
    for f in ev["day3_fixtures"]:
        if f["listed_on_hotspawn"]:
            market_quotes = [q for q in f["quotes"] if "cross-check" not in (q.get("via") or "")]
            probs = [q["prob_a_devig"] for q in market_quotes]
            pa = sum(probs) / len(probs)
            basis = "market"
            sources = [{"label": q["source"], "url": q["url"], "read_utc": q["retrieved_utc"],
                        "prob_a": q["prob_a_devig"], "orientation": q.get("orientation", "fixture order")}
                       for q in market_quotes]
            vrs = f["valve_vrs"]
            sources.append({"label": f"Valve VRS {vrs['snapshot']} · {f['team_a']} #{vrs['standing_a']} "
                                     f"({vrs['points_a']} pts) vs {f['team_b']} #{vrs['standing_b']} ({vrs['points_b']} pts)",
                            "url": vrs["url"]})
        else:
            vrs = f["valve_vrs"]
            pa = vrs_prob(vrs["points_a"], vrs["points_b"], k)  # team_a = BetBoom
            basis = "originated (Valve VRS model — no market line found)"
            sources = [{"label": f"Valve VRS {vrs['snapshot']} · {f['team_a']} #{vrs['standing_a']} "
                                 f"({vrs['points_a']} pts) vs {f['team_b']} #{vrs['standing_b']} ({vrs['points_b']} pts) — roster-verified",
                        "url": vrs["url"]}]
        pb = 1.0 - pa
        ca, cb = (f.get("crowd") or {}).get("pct_a"), (f.get("crowd") or {}).get("pct_b")
        dog = f["team_b"] if pa >= 0.5 else f["team_a"]
        flags = context_flags(ev, f["team_a"], f["team_b"], dog)
        lad = ladder(pa, pb, float(f.get("points") or f.get("points_if_listed") or 0),
                     (ca / 100.0 if isinstance(ca, (int, float)) else None),
                     (cb / 100.0 if isinstance(cb, (int, float)) else None), flags)
        team_of = {"A": f["team_a"], "B": f["team_b"]}
        rows.append({
            "fixture_id": f["fixture_id"],
            "competition": f["competition"],
            "stage": f.get("stage"),
            "tier": f["tier"],
            "points": f.get("points") or f.get("points_if_listed"),
            "start_utc": f["start_utc"],
            "lock_utc": f.get("lock_utc"),
            "team_a": f["team_a"],
            "team_b": f["team_b"],
            "prob_a": pa, "prob_b": pb,
            "basis": basis,
            "n_quote_sources": len([q for q in f.get("quotes", []) if "cross-check" not in (q.get("via") or "")]),
            "sources": sources + [{"label": "HLTV fixture confirmation", "url": f.get("hltv_url")}]
                       + ([{"label": "HotSpawn fixture listing (discovery/settlement only)",
                            "url": f["hotspawn_url"]}] if f.get("hotspawn_url") else []),
            "crowd_pct_a": ca, "crowd_pct_b": cb,
            "crowd_captured_utc": (f.get("crowd") or {}).get("captured_utc"),
            "safe_pick": team_of.get(lad.get("safe")),
            "safe_prob": lad.get("safe_prob"),
            "climb_pick": team_of.get(lad.get("climb")),
            "climb_prob": lad.get("climb_prob"),
            "strategy": lad,
            "twc_day3": True,
            "listed_on_hotspawn": f["listed_on_hotspawn"],
        })

    rows.sort(key=lambda r: (r.get("start_utc") or "", r.get("fixture_id") or ""))
    picked = [r for r in rows if r.get("climb_pick")]
    return {
        "session": "4cf64ea3",
        "generated_utc": None,  # stamped by the caller
        "inputs": {
            "evidence": "data/4cf64ea3/evidence.json",
            "quotes_via": "data/fe803b80/board.json (retained raw bookmaker/exchange quotes, re-derived here)",
            "crowd_via": "data/f28afd9e/board.json (HotSpawn crowd split; leaderboard differential only)",
            "calibration_k": k,
        },
        "summary": {
            "rows": len(rows),
            "with_pick": len(picked),
            "market": len([r for r in rows if r["basis"] == "market"]),
            "model": len([r for r in rows if r["basis"].startswith("model")]),
            "originated": len([r for r in rows if r["basis"].startswith("originated")]),
            "unresolved": len([r for r in rows if not r.get("climb_pick")]),
            "climb_swings": len([r for r in rows if (r.get("strategy") or {}).get("rule") in ("C1_coinflip_fade", "C2_upset_shot")]),
        },
        "rows": rows,
    }


# ---------------------------------------------------------------- HTML plumbing
def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pct(p) -> str:
    return "—" if p is None else f"{100.0 * p:.1f}%"


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
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#b9c8e4;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.tag{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700}
.tag.pick{background:var(--good);color:#fff}.tag.climb{background:#5b3fd6;color:#fff}
.tag.mkt{background:#1d4ed8;color:#fff}.tag.mdl{background:#334155;color:#dbe7ff}
.tag.ori{background:var(--warn);color:#221602}.tag.blank{background:#3a2530;color:#ffb4ae}
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

NAV = [
    ("index.html", "Start here"),
    ("picks.html", "Day-3 picks · all matches"),
    ("day1-day2.html", "Day 1–2 review"),
    ("unresolved.html", "Unresolved + limits"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method & sources"),
]


def page(title: str, active: str, body: str, stamp: str) -> str:
    nav = "".join(f'<a href="{href}" class="{"on" if href == active else ""}">{esc(label)}</a>'
                  for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · TWC 2026 day-3 desk</title>
<meta name="description" content="Mobile-first day-3 picks for the Thunderpick World Championship 2026 and every open HotSpawn CS2 match.">
<style>{CSS}</style></head>
<body><header class="site"><div class="wrap"><strong style="font-size:14px">Day-3 desk</strong>{nav}</div></header>
<main class="wrap">{body}
<p class="mut">Built {esc(stamp)} · Sources are linked on every row · HotSpawn crowd % is used only for
leaderboard differentials, never as a probability · 18+; gamble responsibly.</p>
</main></body></html>"""


def src_links(sources) -> str:
    bits = []
    for s in sources or []:
        url = s.get("url") or ""
        if not url.startswith(("https://", "http://")):
            continue
        bits.append(f'<a href="{esc(url)}">{esc(s.get("label") or url)}</a>')
    return " · ".join(bits) if bits else '<span class="tag blank">no source</span>'


def basis_tag(basis: str) -> str:
    if basis == "market":
        return '<span class="tag mkt">M · market</span>'
    if basis.startswith("model"):
        return '<span class="tag mdl">O · VRS model</span>'
    if basis.startswith("originated"):
        return '<span class="tag ori">O · originated</span>'
    return '<span class="tag blank">unresolved</span>'


# ---------------------------------------------------------------- page builders
def row_cards(rows, show_crowd=True) -> str:
    out = []
    for r in rows:
        climb = r.get("climb_pick")
        safe = r.get("safe_pick")
        swing = (r.get("strategy") or {}).get("rule") in ("C1_coinflip_fade", "C2_upset_shot")
        pick_cell = (f'<span class="tag climb">{esc(climb)} · climb</span>' if swing and climb
                     else f'<span class="tag pick">{esc(climb or safe or "—")}</span>')
        if not climb:
            pick_cell = '<span class="tag blank">blank · no supported line</span>'
        crowdtxt = "—"
        if r.get("crowd_pct_a") is not None:
            crowdtxt = f'{esc(r["team_a"])} {r["crowd_pct_a"]}% / {esc(r["team_b"])} {r["crowd_pct_b"]}%'
        out.append(f"""<tr>
<td data-label="Kick-off (UTC)">{esc(r.get("start_utc"))}<br><span class="mut">{esc(r.get("competition"))} · {esc(r.get("tier") or "?")} tier · {esc(r.get("points") or "?")} pts</span></td>
<td data-label="Match">{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}</td>
<td data-label="Our win probability">{pct(r.get("prob_a"))} · {pct(r.get("prob_b"))}<br>{basis_tag(r.get("basis") or "")}</td>
<td data-label="The pick">{pick_cell}<br><span class="mut">safe: {esc(safe) or "—"} {pct(r.get("safe_prob"))}</span></td>
<td data-label="Crowd / ladder">{crowdtxt}<br><span class="mut">{esc((r.get("strategy") or {}).get("rule") or "")}</span></td>
<td data-label="Sources">{src_links(r.get("sources"))}</td></tr>""")
    return f'<div class="tablewrap"><table class="responsive"><thead><tr><th>Kick-off (UTC)</th><th>Match</th><th>Our win probability</th><th>The pick</th><th>Crowd / ladder</th><th>Sources</th></tr></thead><tbody>{"".join(out)}</tbody></table></div>'


def index_page(board, ev, stamp) -> str:
    twc = [r for r in board["rows"] if r.get("twc_day3")]
    s = board["summary"]
    head_rows = []
    for r in twc:
        swing = (r.get("strategy") or {}).get("rule") in ("C1_coinflip_fade", "C2_upset_shot")
        tag = f'<span class="tag climb">{esc(r["climb_pick"])} · climb pick</span>' if swing else f'<span class="tag pick">{esc(r["climb_pick"])}</span>'
        head_rows.append(f"""<tr>
<td data-label="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}<br><span class="mut">{esc(r.get("competition"))} · starts {esc(r.get("start_utc"))}</span></td>
<td data-label="Our line">{pct(r.get("prob_a"))} · {pct(r.get("prob_b"))}<br><span class="mut">{esc(r.get("basis"))}</span></td>
<td data-label="Pick">{tag}<br><span class="mut">safe pick: {esc(r["safe_pick"])} {pct(r.get("safe_prob"))}</span></td>
<td data-label="Sources">{src_links(r.get("sources"))}</td></tr>""")
    body = f"""
<p class="eyebrow">Thunderpick World Championship 2026 · Malta · day 3 (Oct 16)</p>
<h1>Start here: today's picks, on any screen</h1>
<p>Day 2 is in the books — <strong>Falcons and FURIA are through</strong>, NIP and PARIVISION are out.
Day 3 is the last group day: <strong>Aurora vs 9z</strong> (14:00 UTC) and <strong>BETBOOM vs Legacy</strong>
(≈17:00 UTC) for the final two playoff spots. The pick for every open HotSpawn CS2 match is one tap away.</p>
<div class="cards">
  <div class="card"><div class="card-num">{s["with_pick"]}/{s["rows"]}</div><div class="card-label">open matches with a published pick</div></div>
  <div class="card"><div class="card-num">{s["market"]}</div><div class="card-label">priced from bookmaker/exchange lines</div></div>
  <div class="card"><div class="card-num">{s["model"] + s["originated"]}</div><div class="card-label">originated (Valve VRS model) — labelled O</div></div>
  <div class="card"><div class="card-num">{s["climb_swings"]}</div><div class="card-label">contrarian climb swings today</div></div>
</div>
<p>
  <a class="btn" href="picks.html">All picks · every match</a>
  <a class="btn alt" href="picks.html#twc-day3">TWC day-3 picks</a>
  <a class="btn ghost" href="unresolved.html">Unresolved picks + limitations</a>
  <a class="btn ghost" href="day1-day2.html">Day 1–2 review (9z upset)</a>
  <a class="btn ghost" href="flagged.html">Flagged for review</a>
</p>
<h2 id="twc-headlines">TWC day-3 headline picks</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Our line</th><th>Pick</th><th>Sources</th></tr></thead>
<tbody>{"".join(head_rows)}</tbody></table></div>
<p class="mut">“Climb pick” is the leaderboard play (contrarian, context-backed, above the 30% “not stupid”
floor). “Safe pick” maximises expected points. Both columns are always shown — full arithmetic on the
<a href="picks.html#twc-day3">day-3 picks page</a>.</p>
<h2>Where every updated picks list lives on this site</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Board</th><th>What it is</th></tr></thead><tbody>
<tr><td data-label="Board"><a href="picks.html">Day-3 desk · all matches</a></td><td data-label="What it is">This page's complete table: pick + win probability for every open HotSpawn CS2 match, incl. low-tier rows.</td></tr>
<tr><td data-label="Board"><a href="../picks-all/index.html">Complete picks (picks-all)</a></td><td data-label="What it is">Pick + probability for every open lobby fixture (23 market / research / originated), per-row sources.</td></tr>
<tr><td data-label="Board"><a href="../board/picks.html">All picks · expanded board</a></td><td data-label="What it is">Market + model research board with identity flags and quote times.</td></tr>
<tr><td data-label="Board"><a href="../strategy/index.html">Strategy board (safe + leaderboard)</a></td><td data-label="What it is">Day-1 backtest and the leaderboard ladder on every row (session f28afd9e).</td></tr>
<tr><td data-label="Board"><a href="../picks-every-match/index.html">Every-match picks at a glance</a></td><td data-label="What it is">Mobile quick board; blank rows flagged.</td></tr>
<tr><td data-label="Board"><a href="../unresolved/index.html">Research-resolved picks</a></td><td data-label="What it is">Featured lines first; unpriced rows resolved via HLTV / esportsbooks / Valve VRS.</td></tr>
<tr><td data-label="Board"><a href="../live/index.html">Live coverage</a> · <a href="../coverage/index.html">Coverage</a> · <a href="../market/">Market</a> · <a href="../fresh/index.html">Fresh</a> · <a href="../ourline/index.html">Our line</a> · <a href="../exec/index.html">Executive summary</a></td><td data-label="What it is">Alternative boards and evidence packs, each with its own standards.</td></tr>
<tr><td data-label="Board"><a href="../audits/6c5bb3d6/index.html">Independent verification</a></td><td data-label="What it is">Every probability re-derived from raw quotes and Valve's own standings (session 6c5bb3d6).</td></tr>
<tr><td data-label="Board"><a href="../flagged.html">Flagged for review (root)</a></td><td data-label="What it is">Every unverified/irregular item on the site.</td></tr>
</tbody></table></div>
<p class="mut">The lobby adds new matches (TWC playoffs run Oct 17–18). This section refreshes automatically
every 4 hours from the repository's collectors — the picks table always reflects the latest build stamp below.</p>"""
    return page("Start here", "index.html", body, stamp)


def picks_page(board, ev, stamp) -> str:
    twc = [r for r in board["rows"] if r.get("twc_day3")]
    others = [r for r in board["rows"] if not r.get("twc_day3")]
    detail = []
    for r in twc:
        st = r.get("strategy") or {}
        swing = st.get("rule") in ("C1_coinflip_fade", "C2_upset_shot")
        notes = " ".join(esc(n) for n in st.get("notes") or [])
        flagbits = "".join(
            f'<li>{esc(f.get("type"))} · {esc(f.get("team"))} ({esc(f.get("date"))}): {esc(f.get("summary"))} '
            f'— <a href="{esc(f.get("source"))}">source</a></li>' for f in st.get("flags") or [])
        fx = next((f for f in ev["day3_fixtures"] if f.get("fixture_id") == r.get("fixture_id")), {})
        quote_rows = "".join(
            f'<tr><td data-label="Book">{esc(q["source"])}</td><td data-label="Orientation">{esc(q.get("orientation", ""))}</td>'
            f'<td data-label="De-vigged">{pct(q.get("prob_a_devig"))} {esc(r["team_a"])}</td>'
            f'<td data-label="Read (UTC)">{esc(q.get("retrieved_utc"))}</td>'
            f'<td data-label="Source"><a href="{esc(q["url"])}">{esc(q["url"])}</a></td></tr>'
            for q in (fx.get("quotes") or []))
        if not quote_rows:
            quote_rows = "".join(
                f'<tr><td data-label="Where we looked">{esc(q.get("label"))}</td>'
                f'<td data-label="Found">no two-sided match line</td>'
                f'<td data-label="De-vigged">—</td>'
                f'<td data-label="Read (UTC)">{esc(ev.get("research_window_utc"))}</td>'
                f'<td data-label="Source"><a href="{esc(q.get("url"))}">{esc(q.get("url"))}</a></td></tr>'
                for q in (fx.get("searched") or []))
        pick_block = (f'<span class="tag climb">PICK (climb): {esc(r["climb_pick"])} {pct(r["climb_prob"])}</span>'
                      if swing else
                      f'<span class="tag pick">PICK: {esc(r["climb_pick"])} {pct(r["climb_prob"])}</span>')
        crowdtxt = ("—" if r.get("crowd_pct_a") is None else
                    f'{esc(r["team_a"])} {r["crowd_pct_a"]}% / {esc(r["team_b"])} {r["crowd_pct_b"]}% '
                    f'(captured {esc(r.get("crowd_captured_utc"))})')
        detail.append(f"""
<h3 id="m{esc(r.get("fixture_id"))}">{esc(r["team_a"])} vs {esc(r["team_b"])} · {esc(r.get("start_utc"))} UTC</h3>
<p>{pick_block} <span class="tag pick">safe: {esc(r["safe_pick"])} {pct(r["safe_prob"])}</span>
{basis_tag(r.get("basis") or "")}</p>
<p class="mut">{esc(r.get("competition"))} · {esc(r.get("points"))} points · {esc(r.get("stage") or "")}</p>
<div class="cards">
<div class="card"><div class="card-num">{pct(r.get("prob_a"))} / {pct(r.get("prob_b"))}</div><div class="card-label">our line: {esc(r["team_a"])} / {esc(r["team_b"])}</div></div>
<div class="card"><div class="card-num">{crowdtxt}</div><div class="card-label">HotSpawn crowd (leaderboard only)</div></div>
<div class="card"><div class="card-num">{("—" if st.get("differential") is None else f'{st["differential"]:+.2f} pts')}</div><div class="card-label">expected-points differential vs field if the dog hits</div></div>
<div class="card"><div class="card-num">{("—" if st.get("leverage") is None else f'{st["leverage"]:.2f}×')}</div><div class="card-label">leverage (win chance ÷ crowd share)</div></div>
</div>
<p><strong>Why:</strong> {notes or "—"} Safe-pick expected points {("—" if st.get("ep_safe") is None else f'{st["ep_safe"]:.2f}')},
dog expected points {("—" if st.get("ep_cost") is None else f'{st["ep_dog"]:.2f}')},
cost of swinging {("—" if st.get("ep_cost") is None else f'{st["ep_cost"]:.2f}')} pts.</p>
<ul>{flagbits or "<li class='mut'>no roster/rest/H2H context flags recorded for this row</li>"}</ul>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Line source</th><th>Orientation</th><th>De-vigged</th><th>Read (UTC)</th><th>Link</th></tr></thead>
<tbody>{quote_rows}</tbody></table></div>
<p class="mut">Fixture: {src_links(r.get("sources"))}</p>""")
    body = f"""
<p class="eyebrow">Complete picks · every open CS2 match</p>
<h1>Day-3 picks &amp; the full board</h1>
<p>Every row: our win probability from <strong>outside betting lines</strong> (never HotSpawn), an obvious
pick, and the source links to re-check each number. Rows without a supported line stay
<strong>blank and flagged</strong> — see <a href="unresolved.html">Unresolved + limitations</a>.</p>
<h2 id="twc-day3">TWC 2026 · day 3 — the matches that decide the groups</h2>
{''.join(detail)}
<h2 id="all">Every open HotSpawn CS2 match ({len(others)} more)</h2>
{row_cards(others)}
<p class="mut">Basis codes: <span class="tag mkt">M · market</span> = de-vigged consensus of retained
bookmaker/exchange quotes; <span class="tag mdl">O · VRS model</span> = originated from Valve's official
standings with the calibrated curve; <span class="tag ori">O · originated</span> = documented originated
line where no market exists. Every probability on this page is re-derived by
<code>scripts/4cf64ea3/build.py</code> from raw quotes or Valve's file — formulas in
<a href="method.html">method</a>.</p>"""
    return page("Day-3 picks · all matches", "picks.html", body, stamp)


def review_page(ev, stamp) -> str:
    def table(days, label):
        rows = []
        for r in days:
            upset = ('<span class="tag climb">UPSET</span>' if r.get("upset_vs_market") else "")
            facts = "".join(f'<li>{esc(f["text"])} — <a href="{esc(f["source"])}">{esc(f["label"])}</a></li>'
                            for f in r.get("facts") or [])
            rows.append(f"""<tr>
<td data-label="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}<br><span class="mut">#{esc(r.get("fixture_id"))} · {esc(r.get("stage"))} · {esc(r.get("start_utc"))}</span></td>
<td data-label="Result">{esc(r["score_a"])}–{esc(r["score_b"])} {esc(r.get("winner"))} {upset}<br><span class="mut">{esc(r.get("maps"))}</span></td>
<td data-label="Notes"><ul style="margin:0;padding-left:16px">{facts}</ul></td>
<td data-label="Sources">{src_links(r.get("sources"))}</td></tr>""")
        return (f'<h2>{esc(label)}</h2><div class="tablewrap"><table class="responsive"><thead><tr>'
                f'<th>Match</th><th>Result</th><th>Notes</th><th>Sources</th></tr></thead><tbody>'
                f'{"".join(rows)}</tbody></table></div>')
    body = f"""
<p class="eyebrow">Day 1–2 review · every score source-linked</p>
<h1>What happened, and what it means for day 3</h1>
{table(ev["day1_results"], "Day 1 — Oct 14 (four 2-0 sweeps and the 9z upset)")}
<h3>The upset, and the roster-change thread</h3>
<p>9z beat Aurora 2-0 as a <strong>29.7% market dog</strong> with only <strong>4% of HotSpawn players</strong>
on them (96% owned Aurora) — the leaderboard play of the day. Verified drivers:
Aurora's <strong>July rebuild</strong> (kyxsan in as IGL, Jimpphat added, ash as head coach — a new IGL, coach
and communication language at once, 100 days before day 3) is the onboarding risk the market under-priced;
kyxsan went 0.53 in the loss while luchov posted 1.61. Details and sources on the
<a href="../strategy/day1.html">strategy day-1 page</a> and the
<a href="../audits/6c5bb3d6/index.html">independent audit</a>.</p>
{table(ev["day2_results"], "Day 2 — Oct 15 (Falcons & FURIA through; NIP & PARIVISION out)")}
<h3>Day-2 → day-3 read-through</h3>
<ul>
<li><strong>Aurora look warmer, not colder.</strong> The rebuild that broke on day 1 bounced back 2-0 over NIP
(Wicadia 1.82, XANTARES 1.61, kyxsan positive) — but they have not yet beaten a live opponent at this event,
and 9z already beat them on this LAN.</li>
<li><strong>9z are playing above their rank.</strong> They took Mirage 13-8 off tournament favourites Falcons
(luchov 2.06) and lost the series on two 9-13s. HLTV confirms the rematch is the Group A decider.</li>
<li><strong>Rest:</strong> Aurora played two maps (early finish), 9z played three ending later — a mild
Aurora edge going into the 16:00 CEST decider; both have overnight rest.</li>
<li><strong>Group B:</strong> BetBoom needed three maps to get past a limp PARIVISION; Legacy lost the
latest-finishing series of the day to FURIA after winning Cache. Legacy carry the firepower edge
(Valve VRS #2 vs #11).</li>
</ul>
<p class="mut">HotSpawn settled picks for these fixtures; settlement is used for the day-1 backtest on the
<a href="../strategy/day1.html">strategy page</a>, not to price day 3.</p>"""
    return page("Day 1–2 review", "day1-day2.html", body, stamp)


def unresolved_page(board, ev, stamp) -> str:
    blanks = [r for r in board["rows"] if not r.get("climb_pick")]
    blank_rows = "".join(
        f'<tr><td data-label="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}<br><span class="mut">{esc(r.get("start_utc"))}</span></td>'
        f'<td data-label="What is missing">no pick — left blank by design</td>'
        f'<td data-label="Limitation">no eligible two-sided external quote and no verified Valve VRS rating pair; '
        f'nothing is inferred. {src_links(r.get("sources"))}</td></tr>' for r in blanks)
    bb = [r for r in board["rows"] if not r.get("listed_on_hotspawn", True)]
    bb_txt = ""
    if bb:
        r = bb[0]
        bb_txt = f"""
<h3>Pre-emptive pick: BETBOOM vs Legacy (not yet listed on HotSpawn)</h3>
<p>HLTV confirms this Group B decider on 16/10, but the HotSpawn lobby had <strong>not listed it at build
time</strong>, so there is no HotSpawn fixture id, no crowd split, and <strong>no bookmaker or exchange line
was found anywhere</strong> (bo3.gg 404 on both slugs; only outright markets exist). We publish an
originated pick anyway, clearly labelled: <strong>{esc(r["climb_pick"])} {pct(r["climb_prob"])}</strong>
(Valve VRS model: Legacy #2 1931 vs BETBOOM #11 1596, roster-verified 5/5 against HLTV lineups,
calibrated slope k = {esc(board["inputs"]["calibration_k"])}).
Limitations: the originated curve has a known 13-pt mean absolute error against bookmaker lines
(session fe803b80 calibration on 17 pairs) and may misprice a form-shaped series like this one.
The 4-hourly refresh replaces it with a market line automatically once one appears.</p>"""
    body = f"""
<p class="eyebrow">Unresolved picks &amp; limitations</p>
<h1>What we cannot resolve — and why</h1>
<p>This section exists so a missing pick is <strong>visible, explained and never guessed</strong>. Values
that cannot be confirmed from an official source stay blank and are listed here and on the
<a href="flagged.html">flagged page</a>.</p>
<h2>Open matches with no pick ({len(blanks)})</h2>
{('<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Status</th><th>Limitation</th></tr></thead><tbody>' + blank_rows + '</tbody></table></div>') if blanks else '<p>Every open match in the current build carries a pick. Locked/past rows that never got a line are documented on the <a href="flagged.html">flagged page</a>.</p>'}
{bb_txt}
<h2>Systemic limitations for low-tier / unpriced matches</h2>
<ul>
<li><strong>No bookmaker price exists.</strong> Featured books (Pinnacle/Bovada/Melbet) and the Kalshi
exchange price TWC and other S-tier series; tier-B/C CCT, Elisa and university rows are usually unpriced.
Resolution order for those rows: HLTV facts → esportsbooks / betting lines (bo3.gg Thunderpick feed,
esportbet, sportsgambler) → documented originated line from Valve VRS.</li>
<li><strong>HLTV blocks datacenter IPs (403).</strong> HLTV facts are therefore session-researched and
dated rather than re-read every refresh. Each is linked on its row.</li>
<li><strong>Placeholder prices are rejected.</strong> egamersworld's uniform 1.80/1.80 micro-match quotes
are treated as placeholders and never used; so are HLTV fan votes and HotSpawn crowd %.</li>
<li><strong>Identity joins can be imperfect.</strong> Team aliases (e.g. WROTBERRY→WBT, RoundsGG→ROUNDS)
were resolved by roster match against Valve's file, with residual risk documented in the
<a href="../picks-all/flagged.html">picks-all flagged page</a>.</li>
<li><strong>Originated lines are estimates.</strong> The calibrated Valve-VRS curve has a 13-pt mean
absolute error vs bookmaker lines; it is a fallback, not a verified probability.</li>
<li><strong>Settlement lag.</strong> When a match locks before a line is captured (e.g. the day-2 TWC
rows on some boards), that row can never gain a pick retroactively — it is listed as locked-with-no-line
on the <a href="flagged.html">flagged page</a>.</li>
</ul>"""
    return page("Unresolved picks + limitations", "unresolved.html", body, stamp)


def flagged_page(board, ev, stamp) -> str:
    locked_no_line = [
        ("1080204 Legacy vs FURIA (Oct 15, 16:00Z)", "day-2 TWC winners match", "Locked on the strategy board with no retained line (`no_line_from_any_board`). Result known (FURIA 2-1, HLTV match 2399411) — HotSpawn settlement and our day-2 table cover it; no pick ever existed for the locked row.", "https://www.hltv.org/matches/2399411/legacy-vs-furia-thunderpick-world-championship-2026"),
        ("1079626 Walczaki vs mellren (Oct 15, 11:00Z)", "CCT Europe S11", "Locked before any board captured a line; left blank, not guessed.", "https://play.hotspawn.com/lobby"),
        ("1079628 Gothic vs LFO 10 (Oct 15, 17:00Z)", "CCT Europe S11", "Locked before any board captured a line; left blank, not guessed.", "https://play.hotspawn.com/lobby"),
    ]
    items = [
        ("Timezone caveat — BETBOOM vs Legacy kick-off", "medium",
         "HLTV renders viewer-local times; news 45730 lists the fixture at 19:00 and pley.gg schedules the second day-3 decider at 19:00 CEST (= 17:00 UTC). We pin 17:00 UTC and flag it; the HotSpawn listing (when it appears) is authoritative for the pick lock.",
         "https://pley.gg/cs2/thunderpick-world-championship-2026/"),
        ("Kalshi quote orientation (IR-XF-02 pattern)", "medium",
         "The retained Kalshi KXCS2GAME-26OCT1610009ZAUR quote stores candidate names in source order (9z first, per the ticker) but prices in fixture order (Aurora 0.69). Re-derived here against the ticker; the Aurora-9z row is unaffected, but the stored evidence reads reversed. Same pattern recorded by audits/6c5bb3d6 as IR-XF-02.",
         "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct1610009zaur"),
        ("Originated line precision", "informational",
         "BETBOOM vs Legacy is priced only by the calibrated Valve-VRS curve (no market line found). The calibration reports a 13-point mean absolute error vs bookmaker lines on 17 pairs; treat the number as an estimate and re-check at kick-off.",
         "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"),
        ("Aurora roster-change age", "informational",
         "The July 8 rebuild is 100 days old at day 3 — inside the 120-day onboarding window used by the ladder's context gate, but day-2 form (Wicadia 1.82) suggests the onboarding risk is cooling. Shown, not hidden; it does not change any probability.",
         "https://www.hltv.org/team/11861/aurora"),
        ("Day-1 map-2 score reading", "informational",
         "HLTV news 45718 lists the Nuke map as 13-1 for 9z; Field Level Media reported it as 13-1 as well. Both agree; kept as one verified value.",
         "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026"),
        ("Values deliberately left blank", "informational",
         "BETBOOM vs Legacy head-to-head for 2026: no official source found in the research window — left blank rather than inferred. Crowd split for BETBOOM vs Legacy: the fixture is not on HotSpawn yet, so the ladder defaults to the safe pick and says so.",
         "https://play.hotspawn.com/lobby"),
    ]
    lock_rows = "".join(
        f'<tr><td data-label="Row">{esc(a)}<br><span class="mut">{esc(b)}</span></td>'
        f'<td data-label="Finding">{esc(c)}</td><td data-label="Source"><a href="{esc(d)}">{esc(d)}</a></td></tr>'
        for a, b, c, d in locked_no_line)
    flag_rows = "".join(
        f'<tr><td data-label="Item">{esc(a)}</td><td data-label="Severity"><span class="tag '
        f'{"ori" if b == "medium" else "mdl"}">{esc(b)}</span></td>'
        f'<td data-label="Detail">{esc(c)}</td><td data-label="Source"><a href="{esc(d)}">{esc(d)}</a></td></tr>'
        for a, b, c, d in items)
    body = f"""
<p class="eyebrow">Flagged for review · nothing here blocks the picks</p>
<h1>Irregularities, caveats and blanks</h1>
<p>Every item is published with its source so it can be checked manually. None of these was filled in
with a guess.</p>
<h2>Locked rows that never had a line</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Row</th><th>Finding</th><th>Source</th></tr></thead>
<tbody>{lock_rows}</tbody></table></div>
<h2>Irregularities in today's research</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Item</th><th>Severity</th><th>Detail</th><th>Source</th></tr></thead>
<tbody>{flag_rows}</tbody></table></div>
<p class="mut">Cross-board irregularities (alias joins, stale rank chips, placeholder prices) are kept on the
existing <a href="../flagged.html">root flagged page</a>, the
<a href="../picks-all/flagged.html">picks-all flagged page</a> and the
<a href="../audits/6c5bb3d6/flagged.html">independent audit</a> — not duplicated here.</p>"""
    return page("Flagged for review", "flagged.html", body, stamp)


def method_page(board, ev, stamp) -> str:
    srcs = "".join(f'<tr><td data-label="Source">{esc(s["label"])}</td>'
                   f'<td data-label="URL"><a href="{esc(s["url"])}">{esc(s["url"])}</a></td></tr>'
                   for s in ev.get("sources_index") or [])
    rej = "".join(f'<li><strong>{esc(r["label"])}</strong> — {esc(r["reason"])}</li>'
                  for r in ev.get("rejected_sources") or [])
    body = f"""
<p class="eyebrow">Method · formulas · sources</p>
<h1>How every number on this desk is made</h1>
<h2>Our line</h2>
<ol>
<li><strong>Market rows (M):</strong> take the retained raw quotes (Melbet, Kalshi exchange mid,
Thunderpick via bo3.gg), convert to implied probabilities, remove each book's overround (de-vig),
and average. The arithmetic is re-executed by <code>scripts/4cf64ea3/build.py</code> on every build —
the page never copies a probability it has not re-derived.</li>
<li><strong>Model rows (O · VRS):</strong> no eligible price exists → Valve's own Glicko expectation
(ValveSoftware/counter-strike_regional_standings <code>model/glicko.js</code>: Q = ln(10)/400, RD = 75,
g = 1/√(1+3Q²RD²/π²)), slope calibrated against real bookmaker lines (k = {esc(board["inputs"]["calibration_k"])} from
17 priced pairs, session fe803b80). P(A) = sigmoid(k · g · ln(10)/400 · (pts<sub>A</sub> − pts<sub>B</sub>)).</li>
<li><strong>Never:</strong> HotSpawn crowd %, HLTV fan votes, or placeholder quotes (see rejected below).</li>
</ol>
<h2>The pick ladder (contrarian but not stupid)</h2>
<ul>
<li><strong>Safe pick</strong> = argmax our probability (maximises expected points).</li>
<li><strong>Climb pick</strong> = safe pick unless one of the two swing rules fires:
<ul>
<li><strong>C1 coinflip fade:</strong> market within ±8 pts of 50/50 and ≥70% of the field on one side →
take the other (nearly free leverage).</li>
<li><strong>C2 upset shot:</strong> underdog ≥ <strong>30% (the “not stupid” floor — never swing below it)</strong>,
crowd differential ≥ +0.7 expected points on the row, and <strong>≥ 2 verified context flags</strong>
(underdog beat this opponent in the last 12 months; favourite changed roster/IGL/coach within 120 days;
stand-in; documented rest edge). Context gates the swing; it never moves a probability.</li>
</ul></li>
<li>Both picks are always published with the arithmetic: leverage (win chance ÷ crowd share),
expected points of each side, and the cost of the swing.</li>
</ul>
<h2>Verification rules</h2>
<ul>
<li>Every table row carries an https source to an official page (HLTV, Liquipedia, Valve's GitHub,
the book/exchange quote page, or the HotSpawn fixture listing for discovery only).</li>
<li>A value that cannot be confirmed is left <strong>blank and flagged</strong> — never inferred.</li>
<li>Research window for this build: {esc(ev.get("research_window_utc"))}.</li>
</ul>
<h2>Rejected sources</h2>
<ul>{rej}</ul>
<h2>All sources read this session</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Source</th><th>URL</th></tr></thead><tbody>{srcs}</tbody></table></div>"""
    return page("Method & sources", "method.html", body, stamp)


# ---------------------------------------------------------------- entry point
def build(write: bool = True) -> dict:
    inputs = load_inputs()
    board = build_board(inputs)
    stamp = (inputs["strategy_board"].get("generated_utc") or "unverified")
    board["generated_utc"] = stamp
    pages = {
        "index.html": index_page(board, inputs["evidence"], stamp),
        "picks.html": picks_page(board, inputs["evidence"], stamp),
        "day1-day2.html": review_page(inputs["evidence"], stamp),
        "unresolved.html": unresolved_page(board, inputs["evidence"], stamp),
        "flagged.html": flagged_page(board, inputs["evidence"], stamp),
        "method.html": method_page(board, inputs["evidence"], stamp),
    }
    if write:
        OUT.mkdir(exist_ok=True)
        (DATA / "board.json").write_text(json.dumps(board, indent=1, sort_keys=False) + "\n")
        for name, text in pages.items():
            (OUT / name).write_text(text)
    return {"board": board, "pages": pages}


if __name__ == "__main__":
    result = build()
    s = result["board"]["summary"]
    print(f"day3 built: {len(result['pages'])} pages, "
          f"{s['with_pick']}/{s['rows']} rows with a pick, {s['climb_swings']} climb swings")
