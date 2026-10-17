#!/usr/bin/env python3
"""finals/: TWC 2026 Day 1-4 review -> Day 5 final-day picks + every open HotSpawn CS2 pick.

Session 782adb47. Reads (never writes):
  data/c64a5e19/board.json   canonical HotSpawn capture + book quotes (inventory base)
  data/782adb47/research.json  this session's verified joins, bounds, TWC review, Day 5 case
  data/782adb47/ownership.json live-lobby crowd ownership (leverage column ONLY)

Writes only finals/** (+ finals/data/board.json). No network. Stdlib only.

Resolution order per open fixture (first hit wins, basis always labelled):
  1. canonical market line (Pinnacle/Bovada/Melbet/Kalshi no-vig consensus)
  2. proven-alias market join (research.json alias_joins; identity proof cited on the row)
  3. retained stale single-book quote (research.json stale_quotes; labelled STALE + last-seen)
  4. canonical Valve-VRS model, recalibrated to the market-fitted slope k=0.4213
     (canonical k=1.0 value kept on the row for comparison)
  5. research model row (duplicate Valve name disambiguated by roster, both rows cited)
  6. one-sided lower bound (rated team vs Valve list floor; published as ">=", never a point)
  7. blank + UNRESOLVED (no invented number; full attempt ledger on unresolved.html)

HotSpawn supplies fixtures + crowd ownership only. It never prices a match here.
"""
from __future__ import annotations

import html
import json
import math
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "finals")
CANON = "data/c64a5e19/board.json"
RESEARCH = "data/782adb47/research.json"
OWNERSHIP = "data/782adb47/ownership.json"
LOBBY = "https://play.hotspawn.com/lobby"
VRS_URL = ("https://github.com/ValveSoftware/counter-strike_regional_standings/"
           "blob/main/live/2026/standings_global_2026_10_05.md")
K_CAL = 0.4213
_Q = math.log(10) / 400.0
_G = 1.0 / math.sqrt(1.0 + 3.0 * _Q ** 2 * 75.0 ** 2 / math.pi ** 2)
C_VALVE = _G * math.log(10) / 400.0
FLOOR_P = 0.35
MIN_LEV = 0.15


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def vrs_prob(pa, pb, k=K_CAL):
    return sigmoid(k * C_VALVE * (float(pa) - float(pb)))


def devig(da, db):
    ia, ib = 1.0 / float(da), 1.0 / float(db)
    return ia / (ia + ib)


def pct(v, digits=1):
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def fmt_utc(iso):
    if not iso:
        return "—"
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.strftime("%a %d %b · %H:%M UTC")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ row build
def build_rows(canon, research, own, generated):
    alias = {a["fixture_id"]: a for a in research.get("alias_joins", [])}
    stale = {s["fixture_id"]: s for s in research.get("stale_quotes", [])}
    models = {m["fixture_id"]: m for m in research.get("model_rows", [])}
    bounds = {b["fixture_id"]: b for b in research.get("bound_rows", [])}
    floor_pts = research["vrs_floor"]["points"]
    ctx = research.get("fixture_context", {})

    rows = []
    for r in canon["open"]:
        fid = str(r["fixture_id"])
        line = r.get("line") or {}
        item = {
            "fixture_id": fid, "competition": r["competition"], "tier": r.get("tier"),
            "points": r.get("points"), "start_utc": r["start_utc"], "lock_utc": r.get("lock_utc"),
            "team_a": r["team_a"], "team_b": r["team_b"],
            "hotspawn_url": r.get("hotspawn_url") or LOBBY,
            "flags": list(r.get("flags") or []),
            "basis": None, "basis_label": None, "prob_a": None, "prob_b": None,
            "pick": None, "pick_prob": None, "bound": False, "note": None,
            "canonical_prob_a": line.get("prob_a"), "quotes": [],
            "sources": [{"label": "HotSpawn fixture", "url": r.get("hotspawn_url") or LOBBY}],
            "locked": bool(r.get("lock_utc") and r["lock_utc"] <= generated),
            "attempts": ((r.get("research") or {}).get("steps") or []),
        }
        o = own.get(fid)
        item["crowd_a"], item["crowd_b"] = (o["team_a"], o["team_b"]) if o else (None, None)

        if line.get("basis") == "market" and line.get("prob_a") is not None:
            item["basis"] = "market"
            item["prob_a"] = line["prob_a"]
            mkt = r.get("market") or {}
            books = ", ".join(sorted(set(mkt.get("sources") or []))) or "book"
            item["basis_label"] = f"Market · {mkt.get('n_sources', '?')} source(s): {books}"
            for q in r.get("quotes") or []:
                da, db = q.get("decimal_a"), q.get("decimal_b")
                if q.get("swapped"):  # decimals are source-oriented; publish fixture-oriented
                    da, db = db, da
                item["quotes"].append({
                    "book": q.get("source_name"), "decimal_a": da,
                    "decimal_b": db, "retrieved_utc": q.get("retrieved_utc"),
                    "url": q.get("public_url")})
                if q.get("public_url"):
                    item["sources"].append({"label": q.get("source_name") or "book",
                                            "url": q["public_url"]})
        elif fid in alias:
            a = alias[fid]; q = a["quote"]
            pa_src = devig(q["decimal_a_at_source"], q["decimal_b_at_source"])
            item["prob_a"] = (1 - pa_src) if q.get("swapped") else pa_src
            item["basis"] = "alias"
            item["basis_label"] = "Market · proven alias (1 book)"
            item["note"] = a["identity_proof"] + " " + a["residual_limitation"]
            item["quotes"].append({"book": q["book"], "decimal_a": q["decimal_b_at_source"] if q.get("swapped") else q["decimal_a_at_source"],
                                   "decimal_b": q["decimal_a_at_source"] if q.get("swapped") else q["decimal_b_at_source"],
                                   "retrieved_utc": q["retrieved_utc"], "url": q["public_url"]})
            item["sources"] += [{"label": "Melbet (alias quote)", "url": q["public_url"]},
                                {"label": "Identity proof (repo audit 6c5bb3d6)", "url": "https://www.hltv.org/matches/2399418/wbt-vs-eac-elisa-breakout-series-2"},
                                {"label": "Valve VRS (WBT #60)", "url": VRS_URL}]
        elif fid in stale:
            s = stale[fid]; q = s["quote"]
            item["prob_a"] = devig(q["decimal_a_at_source"], q["decimal_b_at_source"])
            item["basis"] = "stale"
            item["basis_label"] = f"Market · STALE single book (last seen {q['retrieved_utc']})"
            item["note"] = s["note"]
            item["quotes"].append({"book": q["book"], "decimal_a": q["decimal_a_at_source"],
                                   "decimal_b": q["decimal_b_at_source"],
                                   "retrieved_utc": q["retrieved_utc"], "url": q["public_url"]})
            item["sources"].append({"label": "Melbet (retained quote)", "url": q["public_url"]})
        elif line.get("basis") == "model" and (r.get("vrs") or {}).get("team_a") and (r.get("vrs") or {}).get("team_b"):
            va, vb = r["vrs"]["team_a"], r["vrs"]["team_b"]
            item["prob_a"] = vrs_prob(va["points"], vb["points"])
            item["basis"] = "model"
            item["basis_label"] = "Model · Valve VRS (calibrated)"
            item["note"] = (f"{item['team_a']} #{va['standing']} ({va['points']} pts) vs "
                            f"{item['team_b']} #{vb['standing']} ({vb['points']} pts). "
                            f"Canonical board (k=1.0) shows {pct(line.get('prob_a'))} for {item['team_a']}; "
                            f"finals recalibrates to k=0.4213 - pick unchanged.")
            item["sources"].append({"label": "Valve VRS 2026-10-05", "url": VRS_URL})
        elif fid in models:
            m = models[fid]
            item["prob_a"] = vrs_prob(m["points_a"], m["points_b"])
            item["basis"] = "model"
            item["basis_label"] = "Model · Valve VRS (disambiguated)"
            item["note"] = m["note"]
            item["sources"].append({"label": "Valve VRS 2026-10-05", "url": VRS_URL})
        elif fid in bounds:
            b = bounds[fid]
            p_rated = vrs_prob(b["points"], floor_pts)
            item["prob_a"] = p_rated if b["rated_side"] == "a" else 1 - p_rated
            item["basis"] = "bound"; item["bound"] = True
            item["basis_label"] = "Bound only · one side unrated"
            item["note"] = (b["note"] + f" Bound prices {b['unrated']} at the Valve list floor "
                            f"({floor_pts} pts, #380 Fruju): {b['rated']} win probability is AT LEAST "
                            f"{pct(p_rated)} on the calibrated curve, assuming absence from the list "
                            f"means at-or-below floor strength. A strong unranked stack would break that assumption.")
            if b.get("points_alt"):
                item["note"] += (f" Stronger duplicate row ({b['points_alt']} pts) would give "
                                 f">={pct(vrs_prob(b['points_alt'], floor_pts))} - sensitivity only, not the bound.")
            item["sources"].append({"label": "Valve VRS 2026-10-05", "url": VRS_URL})
        # else: stays None -> UNRESOLVED

        if item["prob_a"] is not None:
            item["prob_b"] = 1 - item["prob_a"]
            side = "a" if item["prob_a"] >= item["prob_b"] else "b"
            item["pick"] = item["team_a"] if side == "a" else item["team_b"]
            item["pick_prob"] = max(item["prob_a"], item["prob_b"])
        if fid in ctx:
            extra = ctx[fid].get("note") or ctx[fid].get("against_underdog") or ""
            item["note"] = ((item["note"] + " " + extra).strip() if item["note"] else extra) or None

        # leaderboard layers (ownership is crowd share, never a probability input)
        item["climb"] = None; item["watch"] = None; item["free_differential"] = False
        if item["prob_a"] is not None and item["crowd_a"] is not None:
            pa = item["prob_a"]
            fav_a = pa >= 0.5
            p_fav = pa if fav_a else 1 - pa
            c_fav = (item["crowd_a"] if fav_a else item["crowd_b"]) / 100.0
            p_dog = 1 - p_fav
            c_dog = 1 - c_fav if (item["crowd_a"] + item["crowd_b"]) == 100 else (
                (item["crowd_b"] if fav_a else item["crowd_a"]) / 100.0)
            if p_fav - c_fav >= MIN_LEV:
                item["free_differential"] = True
            if p_dog >= FLOOR_P and (p_dog - c_dog) >= MIN_LEV:
                dog = item["team_b"] if fav_a else item["team_a"]
                entry = {"team": dog, "prob": p_dog, "leverage": p_dog - c_dog}
                rejected = fid == "1082019"  # verified context AGAINST the dog (stand-ins)
                if rejected:
                    entry["rejected_reason"] = "Verified context favours the favourite (stand-ins) - switch rejected."
                    item["watch"] = entry
                else:
                    entry["rejected_reason"] = "Fewer than 2 verified context flags researched for this fixture - watchlist, not a switch."
                    item["watch"] = entry
        rows.append(item)
    rows.sort(key=lambda x: x["start_utc"])
    return rows


def day5_rows(research):
    out = []
    for d in research["day5"]:
        pa_cal = vrs_prob(d["vrs_a"]["points"], d["vrs_b"]["points"], K_CAL)
        pa_raw = vrs_prob(d["vrs_a"]["points"], d["vrs_b"]["points"], 1.0)
        fav_a = pa_cal >= 0.5
        p_fav, p_dog = (pa_cal, 1 - pa_cal) if fav_a else (1 - pa_cal, pa_cal)
        fav = d["a"] if fav_a else d["b"]
        dog = d["b"] if fav_a else d["a"]
        flags = d.get("climb_flags_underdog", 0)
        if p_dog >= FLOOR_P and flags >= 2:
            verdict = (f"CONDITIONAL CLIMB: {dog} qualifies on price ({pct(p_dog)} >= 35%) and "
                       f"{flags} verified flags, but HotSpawn does not list TWC Malta, so there is "
                       f"no crowd ownership to test leverage against. Switch only if a pick'em card "
                       f"appears with {dog} crowd <= 25% near lock; otherwise take the safe pick.")
        elif p_dog >= FLOOR_P:
            verdict = (f"NO CLIMB: {dog} pass the 35% price floor ({pct(p_dog)}) but have only "
                       f"{flags} verified flag(s) for, with head-to-head, map pool and rest against "
                       f"them. Chasing yesterday's upset team into a worse matchup is exactly the "
                       f"'stupid' contrarian play. Safe pick stands.")
        else:
            verdict = f"NO CLIMB: {dog} are below the 35% floor ({pct(p_dog)}). Safe pick stands."
        out.append({**d, "prob_a_cal": pa_cal, "prob_a_raw": pa_raw, "safe_pick": fav,
                    "safe_prob": p_fav, "dog": dog, "dog_prob": p_dog, "verdict": verdict})
    return out


# ------------------------------------------------------------------ chrome
CSS = """
:root{--bg:#0b1220;--card:#131e33;--line:#2a3a5c;--txt:#eef3ff;--mut:#a9b8d8;--acc:#ffb020;--ok:#2fbf71;--bad:#ff6b6b;--warn:#ffd166}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:#7db4ff}h1{font-size:1.45rem;margin:.2rem 0 .4rem}h2{font-size:1.15rem;margin:1.2rem 0 .5rem}h3{font-size:1rem;margin:.8rem 0 .3rem}
.wrap{max-width:860px;margin:0 auto;padding:12px 12px 40px}
.tabs{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line)}
.tabs a{flex:0 0 auto;min-height:44px;display:flex;align-items:center;padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--txt);text-decoration:none;font-size:.92rem}
.tabs a.on{background:var(--acc);color:#111;border-color:var(--acc);font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0}
.pick{font-size:1.15rem;font-weight:800}.pick b{color:var(--ok)}
.probs{display:flex;gap:8px;margin:8px 0}.probs div{flex:1;background:#0d1830;border-radius:10px;padding:8px;text-align:center}
.probs .n{font-size:1.5rem;font-weight:800}.probs .t{font-size:.85rem;color:var(--mut)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.78rem;font-weight:700;margin:2px 4px 2px 0}
.b-market{background:#123d2b;color:#7dffb0}.b-model{background:#2b2a12;color:#ffe97d}.b-bound{background:#3d2a12;color:#ffcf7d}
.b-stale{background:#3d1230;color:#ff9de2}.b-alias{background:#12303d;color:#7dd7ff}.b-none{background:#3d1212;color:#ff9d9d}
.mut{color:var(--mut);font-size:.9rem}.small{font-size:.85rem}
.btn{display:flex;justify-content:space-between;align-items:center;min-height:48px;background:#1a2a4a;color:var(--txt);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:8px 0;text-decoration:none}
.btn strong{color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.warn{border-left:4px solid var(--warn);padding:8px 10px;background:#241d08;border-radius:8px}
.good{border-left:4px solid var(--ok);padding:8px 10px;background:#0b2417;border-radius:8px}
code{background:#0d1830;padding:1px 5px;border-radius:6px}
@media (max-width:520px){.probs .n{font-size:1.25rem}h1{font-size:1.25rem}}
"""

TABS = [("index.html", "🏆 Summary"), ("picks.html", "✅ All picks"), ("twc.html", "TWC Days 1–5"),
        ("unresolved.html", "⚠️ Unresolved"), ("flagged.html", "Flagged"), ("method.html", "Method")]


def page(title, active, body, generated, capture):
    tabs = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{esc(t)}</a>' for h, t in TABS)
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body><div class=wrap>
<nav class=tabs>{tabs}</nav>
<p class="mut small">TWC 2026 finals desk · built {esc(generated)} · lobby capture {esc(capture)} ·
probabilities from external books / Valve ratings — never HotSpawn. Crowd % = ownership only.</p>
{body}
<p class="mut small">Not affiliated with HotSpawn, Thunderpick or any bookmaker. Model/bound numbers are
our originated estimates, not verified win chances. Check lock times on HotSpawn before picking.
<a href="../index.html">← Site home</a> · <a href="data/board.json">Machine-readable board (JSON)</a></p>
</div></body></html>"""


def src_links(sources):
    seen, out = set(), []
    for s in sources:
        u = s.get("url")
        if u and u not in seen:
            seen.add(u)
            out.append(f'<a href="{esc(u)}">{esc(s.get("label"))}</a>')
    return " · ".join(out)


def row_card(r):
    badge_cls = {"market": "b-market", "alias": "b-alias", "stale": "b-stale",
                 "model": "b-model", "bound": "b-bound"}.get(r["basis"], "b-none")
    ge_a = "≥" if (r["bound"] and r["prob_a"] is not None and r["prob_a"] >= 0.5) else ("≤" if r["bound"] else "")
    ge_b = "≤" if (r["bound"] and r["prob_a"] is not None and r["prob_a"] >= 0.5) else ("≥" if r["bound"] else "")
    crowd = (f'Crowd (ownership, not probability): {esc(r["crowd_a"])}% / {esc(r["crowd_b"])}%'
             if r["crowd_a"] is not None else "Crowd ownership: not captured")
    layer = ""
    if r["free_differential"]:
        layer += '<p class=good><strong>FREE DIFFERENTIAL:</strong> the safe pick is already the contrarian side vs the crowd — no switch needed to climb.</p>'
    if r["watch"]:
        w = r["watch"]
        layer += (f'<p class=warn><strong>WATCHLIST (no switch):</strong> {esc(w["team"])} {pct(w["prob"])} '
                  f'vs crowd — leverage +{w["leverage"] * 100:.0f}pp. {esc(w["rejected_reason"])}</p>')
    if r["locked"]:
        layer += '<p class=warn><strong>LOCKED</strong> since this capture — shown for the record. Do not pick.</p>'
    note = f'<p class=mut>{esc(r["note"])}</p>' if r["note"] else ""
    quotes = ""
    if r["quotes"]:
        quotes = '<p class="mut small">' + "; ".join(
            f'{esc(q["book"])} {esc(q["decimal_a"])}/{esc(q["decimal_b"])} (read {esc(q["retrieved_utc"])})'
            for q in r["quotes"]) + "</p>"
    if r["pick"]:
        pick_html = f'<p class=pick>✅ PICK: <b>{esc(r["pick"])}</b> · {pct(r["pick_prob"])}</p>'
    else:
        pick_html = '<p class=pick>⛔ NO PICK — unresolved (see Unresolved page). Probability left blank, never 50/50.</p>'
    return f"""<article class=card id="{esc(r['fixture_id'])}">
<p class="mut small">{esc(r['competition'])} · Tier {esc(r['tier'])} · {esc(r['points'])} pts · starts {esc(fmt_utc(r['start_utc']))} · locks {esc(fmt_utc(r['lock_utc']))}</p>
<div class=probs><div><div class=t>{esc(r['team_a'])}</div><div class=n>{ge_a}{pct(r['prob_a'], 0)}</div></div>
<div><div class=t>{esc(r['team_b'])}</div><div class=n>{ge_b}{pct(r['prob_b'], 0)}</div></div></div>
{pick_html}<span class="badge {badge_cls}">{esc(r['basis_label'] or 'Unresolved')}</span>
<p class="mut small">{crowd}</p>{quotes}{note}{layer}
<p class="small">Sources: {src_links(r['sources'])}</p></article>"""


# ------------------------------------------------------------------ pages
def main():
    canon = load(CANON)
    research = load(RESEARCH)
    own = load(OWNERSHIP)["ownership"]
    generated = now_iso()
    capture = canon["generated_utc"]
    rows = build_rows(canon, research, own, generated)
    d5 = day5_rows(research)
    open_rows = [r for r in rows if not r["locked"]]
    locked_rows = [r for r in rows if r["locked"]]
    counts = {}
    for r in open_rows:
        counts[r["basis"] or "none"] = counts.get(r["basis"] or "none", 0) + 1
    unresolved_rows = [r for r in open_rows if r["basis"] != "market"]
    blank_rows = [r for r in open_rows if r["prob_a"] is None]

    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    board = {"session": "782adb47", "generated_utc": generated, "canonical_capture": capture,
             "summary": {"open": len(open_rows), "locked_since_capture": len(locked_rows),
                         "with_pick": sum(1 for r in open_rows if r["pick"]),
                         "blank": len(blank_rows), "by_basis": counts},
             "rows": rows, "day5": [{k: v for k, v in d.items()} for d in d5]}
    with open(os.path.join(OUT, "data", "board.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=1)

    # ---- index (executive summary)
    soon = sorted(open_rows, key=lambda x: x["start_utc"])[:3]
    soon_html = "".join(
        f'<li><a href="picks.html#{esc(r["fixture_id"])}">{esc(r["pick"] or "No pick")} {pct(r["pick_prob"], 0)}</a> — {esc(r["team_a"])} v {esc(r["team_b"])} · locks {esc(fmt_utc(r["lock_utc"]))}</li>'
        for r in soon)
    d5_cards = ""
    for d in d5:
        d5_cards += f"""<article class=card><h3>{esc(d['stage'])} · Sun 18 Oct · ~{esc(d['start_utc_derived'][11:16])}Z*</h3>
<div class=probs><div><div class=t>{esc(d['a'])}</div><div class=n>{pct(d['prob_a_cal'], 0)}</div></div>
<div><div class=t>{esc(d['b'])}</div><div class=n>{pct(1 - d['prob_a_cal'], 0)}</div></div></div>
<p class=pick>✅ SAFE PICK: <b>{esc(d['safe_pick'])}</b> · {pct(d['safe_prob'])}</p>
<p>{esc(d['verdict'])}</p>
<p class="mut small">Originated Valve-VRS line (calibrated k=0.4213; raw Valve k=1.0 gives {pct(d['prob_a_raw'])} for {esc(d['a'])}).
No bookmaker had priced this match at research time — recheck before lock. *Start derived from UTC-4 page rendering (method page).</p>
<p class=small>Sources: <a href="{esc(d['hltv_url'])}">HLTV match</a> · <a href="{esc(d['bo3_url'])}">bo3.gg</a> · <a href="{VRS_URL}">Valve VRS</a> · <a href="twc.html">full case</a></p></article>"""
    index_body = f"""<h1>🏆 TWC 2026 finals — Day 5 picks + every HotSpawn match</h1>
<p><strong>Day 4 in one line:</strong> FURIA beat Aurora 2–0, then 26.8% underdogs BETBOOM beat Falcons 2–1 —
the event's second huge upset after 9z 2–0 Aurora on Day 1. Tomorrow (Sun 18 Oct, Malta): Aurora v Falcons
for 3rd, then the FURIA v BETBOOM Grand Final (bo5). TWC Malta is <strong>not on the HotSpawn lobby</strong>,
so those two are research picks; every actual HotSpawn card is on the All picks page.</p>
{d5_cards}
<h2>📱 Where the picks are</h2>
<a class=btn href="picks.html"><span><strong>All picks</strong> · {len(open_rows)} open HotSpawn matches, every one resolved or flagged</span><span>→</span></a>
<a class=btn href="twc.html"><span><strong>TWC Days 1–5</strong> · verified results, Aurora roster truth, Day 5 case</span><span>→</span></a>
<a class=btn href="unresolved.html"><span><strong>Unresolved &amp; limitations</strong> · {len(unresolved_rows)} rows without a fresh book price + why</span><span>→</span></a>
<a class=btn href="../desk/picks.html"><span>Yesterday's desk · Day-4 semifinal board (for the record)</span><span>→</span></a>
<a class=btn href="../picks-every-match/index.html"><span>Canonical strict board · market-only, blanks stay blank</span><span>→</span></a>
<a class=btn href="../ourline/index.html"><span>Ourline board · fastest refresh (~27 min)</span><span>→</span></a>
<h2>Coverage right now</h2>
<p>{len(open_rows)} open CS2 matches · {counts.get('market', 0)} fresh market · {counts.get('alias', 0)} proven-alias market ·
{counts.get('stale', 0)} stale single-book · {counts.get('model', 0)} Valve-VRS model · {counts.get('bound', 0)} bound-only ·
{len(blank_rows)} blank · {len(locked_rows)} locked since capture. Refreshed every 4 hours; HotSpawn adds cards between captures (see Method).</p>
<h2>Next locks</h2><ul>{soon_html}</ul>
<h2>How to climb (contrarian, not stupid)</h2>
<p>Take favourites the crowd hates first (free differential), switch to an underdog only at ≥35% win chance
with ≥15pp leverage over crowd ownership AND ≥2 verified flags. Day 4 graded honestly on the TWC page:
the Aurora climb lost, the rejected BETBOOM punt won — one result does not rewrite the rule.</p>
<p class=warn><strong>Unresolved summary:</strong> {len(unresolved_rows)} open rows have no fresh two-sided bookmaker price
(model, bound, stale or alias instead) and neither Day-5 match was priced by any book at research time.
Every such row, the sources tried, and what would resolve it: <a href="unresolved.html">Unresolved &amp; limitations</a>.
Nothing is filled in as 50/50.</p>"""
    write("index.html", page("TWC finals — Day 5 picks + every HotSpawn match", "index.html", index_body, generated, capture))

    # ---- picks
    picks_body = f"""<h1>✅ All picks — every open HotSpawn CS2 match</h1>
<p>Big number = our win probability for that team (bookmaker no-vig first, calibrated Valve rating second,
≥ bound when one side is unrated). <strong>✅ PICK</strong> is the team to select. Basis badge says exactly
what the number is. Crowd % is HotSpawn ownership for leaderboard leverage — never the probability.</p>
{''.join(row_card(r) for r in open_rows)}
<h2>Locked since capture (do not pick)</h2>
{''.join(row_card(r) for r in locked_rows) or '<p class=mut>None.</p>'}"""
    write("picks.html", page("All picks — every open match", "picks.html", picks_body, generated, capture))

    # ---- twc
    res_rows = "".join(
        f'<tr><td>D{t["day"]}<br><span class=mut>{esc(t["date"])}</span></td><td>{esc(t["stage"])}</td>'
        f'<td><strong>{esc(t["a"])} {t["sa"]}–{t["sb"]} {esc(t["b"])}</strong>'
        f'{" <strong>UPSET</strong>" if t["upset"] else ""}<br><span class=mut>{esc(t["maps"] or "maps not transcribed")}</span>'
        f'{"<br>" + esc(t["note"]) if t["note"] else ""}</td><td><a href="{esc(t["url"])}">HLTV</a></td></tr>'
        for t in research["twc_results"])
    tl = "".join(f'<tr><td>{esc(e["date"])}</td><td>{esc(e["event"])}</td><td><a href="{esc(e["url"])}">source</a></td></tr>'
                 for e in research["aurora_roster"]["timeline"])
    d5_case = ""
    for d in d5:
        ctx_items = "".join(f"<li>{esc(c)}</li>" for c in d["context"])
        d5_case += f"""<h3>{esc(d['stage'])}: {esc(d['a'])} v {esc(d['b'])} — safe {esc(d['safe_pick'])} {pct(d['safe_prob'])}</h3>
<p>Originated line: {esc(d['a'])} {pct(d['prob_a_cal'])} / {esc(d['b'])} {pct(1 - d['prob_a_cal'])}
(VRS {d['vrs_a']['points']} v {d['vrs_b']['points']} pts, calibrated k=0.4213; raw Valve k=1.0: {pct(d['prob_a_raw'])} / {pct(1 - d['prob_a_raw'])}).
{esc(d['market_note'])}</p><ul>{ctx_items}</ul><p><strong>Leaderboard verdict:</strong> {esc(d['verdict'])}</p>
<p class=small>Sources: <a href="{esc(d['hltv_url'])}">HLTV match</a> · <a href="{esc(d['bo3_url'])}">bo3.gg</a> · <a href="{VRS_URL}">Valve VRS</a></p>"""
    twc_body = f"""<h1>TWC 2026 — Days 1–4 verified → Day 5 picks</h1>
<h2>What happened (HLTV, line by line)</h2>
<table><thead><tr><th>Day</th><th>Stage</th><th>Result</th><th>Source</th></tr></thead><tbody>{res_rows}</tbody></table>
<p class="mut small">Event: <a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026">HLTV event 8932</a> ·
<a href="https://www.hltv.org/results?event=8932">HLTV results</a>. Map scores transcribed only where the match page was read in full this session (Days 3–4 + Day 1 opener via retained desk research).</p>
<h2>The Aurora roster-change premise — checked</h2>
<p>{esc(research['aurora_roster']['verdict'])}</p>
<table><thead><tr><th>Date</th><th>Move</th><th>Source</th></tr></thead><tbody>{tl}</tbody></table>
<p class=small>Current five + coach: <a href="https://www.hltv.org/team/11861/aurora">HLTV Aurora</a> ·
<a href="https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan">HLTV news 45082</a>.
Onboarding lesson: by October this was a settled top-6 team that had already beaten Spirit 2–0 (11 Oct) — the Day-1
loss to 9z prices as variance + a bad Nuke (1–13), and the same five won the rematch 2–0 two days later.
A team with a REAL fresh change (new IGL/coach inside ~2 weeks, stand-ins on the match page) is where this
angle belongs — e.g. Hacha's three stand-ins on tonight's lobby card, which is why that crowd-fade is rejected.</p>
<h2>Day 4 picks — graded honestly</h2>
<table><thead><tr><th>Match</th><th>Pre-match line</th><th>Safe pick</th><th>Climb layer</th><th>Result</th></tr></thead><tbody>
<tr><td>FURIA v Aurora</td><td>FURIA 50.7% (3 books + Thunderpick)</td><td>FURIA ✅ won</td><td>Aurora (49.3%, 18% crowd) ❌ lost</td><td>2–0 FURIA</td></tr>
<tr><td>Falcons v BETBOOM</td><td>Falcons 73.2%</td><td>Falcons ❌ lost</td><td>BETBOOM 26.8% — rejected by 35% floor ✅ would have won</td><td>1–2 BETBOOM</td></tr></tbody></table>
<p>Safe layer 1/2, climb layer 0/1 taken (+1 rejected winner). Two matches prove nothing about a 35% floor —
at true 27% a dog still loses ~3 times in 4, and HotSpawn scoring pays the same points whoever you pick, so
switching only pays via crowd differential over many picks. The rule stays pre-declared; BETBOOM's one extra
flag we underweighted (they had beaten Falcons at ESL Pro League S24) is why Day 5 requires the H2H check
explicitly instead of trusting price alone.</p>
<h2>Day 5 — Sunday 18 Oct (final day)</h2>
<p class=warn>Neither match is listed on the HotSpawn pick'em lobby (Malta main event absent from its
tournament filter at tonight's read) and no bookmaker price was rendered at research time. These are
originated research lines — if a HotSpawn card or a book price appears, the 4-hourly refresh reprices from the market first.</p>
{d5_case}
<p class="mut small">Rest note: all four teams played today (Sat); nobody plays twice tomorrow. Map-pool and H2H
claims above link to HLTV analytics / bo3.gg pages read this session; win-rate samples are small (8–31 maps) and are used as flags, never blended into the %.</p>"""
    write("twc.html", page("TWC 2026 Days 1–5", "twc.html", twc_body, generated, capture))

    # ---- unresolved
    un_rows = ""
    for r in unresolved_rows:
        attempts = r["attempts"][:6]
        att = "".join(f'<li>{esc(s.get("label"))}: {esc(s.get("result"))} (<a href="{esc(s.get("url"))}">source</a>, {esc(s.get("at_utc"))})</li>' for s in attempts) or "<li>Canonical capture attempts retained in board.json.</li>"
        what = {"alias": "Resolved via proven alias — limitation is the identity chain, not the price.",
                "stale": "Resolves fully when any book re-lists the match before lock; until then the price is hours old.",
                "model": "Resolves fully when a book prices it; until then this is a rating estimate, not a market.",
                "bound": "Resolves when a book prices it OR the unrated team earns a Valve rating; until then only a one-sided bound is honest.",
                None: "No price and no rating pair — pick withheld. Resolves only with a book price or verified ratings."}[r["basis"]]
        un_rows += f"""<article class=card id="u-{esc(r['fixture_id'])}"><h3>{esc(r['team_a'])} v {esc(r['team_b'])} — {esc(r['basis_label'] or 'UNRESOLVED')}</h3>
<p class="mut small">{esc(r['competition'])} · starts {esc(fmt_utc(r['start_utc']))} · pick: <strong>{esc(r['pick'] or 'WITHHELD')}</strong></p>
<p>{esc(r['note'] or '')}</p><p><strong>What would resolve it:</strong> {esc(what)}</p>
<p class=small><strong>Sources tried (canonical capture, in order HLTV → books/exchanges → Valve):</strong></p><ul class=small>{att}</ul>
<p class=small>Row: <a href="picks.html#{esc(r['fixture_id'])}">pick card</a> · {src_links(r['sources'])}</p></article>"""
    un_body = f"""<h1>⚠️ Unresolved picks &amp; limitations</h1>
<p>Every open match <em>without a fresh two-sided bookmaker price</em> lives here — including matches we could
still pick via a retained stale quote, a proven alias, a Valve rating model or a one-sided bound.
<strong>{len(blank_rows)} open match(es) currently have no number at all</strong>; those picks are withheld, never shown as 50/50.
Low-tier matches miss Polymarket/book coverage because books rotate small events out of their feeds between
captures (Hacha's price existed at 12:09Z and was gone by 18:26Z) — the collector retries every cycle.</p>
<h2>Day-5 TWC matches (originated lines — no market yet)</h2>
<p>Grand Final + 3rd-place match: HLTV analytics rendered only placeholder odds links and bo3.gg showed no
two-sided Thunderpick price at research time (2026-10-17 ~20:30Z). Limitation: the originated VRS line cannot
see vetoes, stand-ins or late news. Resolution: any Pinnacle/Bovada/Melbet/Kalshi/Thunderpick two-sided price
in the next capture replaces it automatically (market always outranks model here).</p>
{un_rows or '<p>None — every open row currently has a fresh market price.</p>'}
<h2>Standing limitations</h2>
<ul>
<li>Capture age: inventory is the canonical capture stamped at the top of this page; the live lobby can add/remove cards in between (it did today). Lock times always win over this page.</li>
<li>Single-book prices (much of tiers B/C) carry no cross-check; thin exchange midpoints (Kalshi) are flagged on their rows.</li>
<li>The calibrated slope k=0.4213 was fitted on a different day's book sample (session 7177d07f); raw Valve k=1.0 is shown alongside every originated number so the disagreement is visible.</li>
<li>Bounds assume an unlisted team is at-or-below the Valve floor. A newly formed stack of proven players would violate that — check the HLTV lineup before trusting a bound.</li>
<li>HotSpawn crowd % moves after our read; leverage is computed at read time and labelled as such.</li>
</ul>"""
    write("unresolved.html", page("Unresolved picks & limitations", "unresolved.html", un_body, generated, capture))

    # ---- flagged
    flags = [
        ("F1", "Aurora 'recent roster change' premise is stale", "The verifiable change is the July 2026 rebuild (HLTV news 45082, 8 Jul), ~100 days before TWC. No October move exists on HLTV transfers, Valve VRS rosters or played lineups for any of the four Day-5 teams. Published so nobody prices an onboarding penalty that does not exist.", "https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan"),
        ("F2", "TWC Malta main event is not on HotSpawn", "Tonight's lobby tournament filter lists only 'Thunderpick World Championship 2026: South American Series #1'. Day-5 picks are therefore research picks, not HotSpawn cards. If HotSpawn adds them overnight, crowd ownership appears and the conditional-climb test on the TWC page applies.", LOBBY),
        ("F3", "Day-5 start times are derived, not UTC-stamped", "HLTV/bo3.gg rendered in UTC-4 (proven against two known kickoffs + the final countdown). 11:30Z / 15:00Z carry ±15 min uncertainty until a UTC source confirms.", "https://www.hltv.org/events/8932/matches"),
        ("F4", "NEXVOID v Off Chops may already have been played", "HLTV match 2399543 shows NEXVOID 2–0 Off Chops on 17 Oct (upper semi-final) while HotSpawn sells the same pairing for 18 Oct 03:00Z. Could be a second bracket meeting or a stale card. Verify teams on the HotSpawn match page before locking; pick published as bound-only with this warning.", "https://www.hltv.org/matches/2399543/nexvoid-vs-off-chops-dfrag-logitech-g-pro-series-2026"),
        ("F5", "FORZE Reload v BakS: one book vs the crowd", "Melbet alone prices FORZE 58.3%; the HotSpawn crowd is 83% BakS. VRS sides with the book (#84 v #100) but a single low-tier price can simply be wrong. Free-differential label stands, with this caveat.", "https://melbet.com/en/line/esports"),
        ("F6", "ex-6666 91.5% is a zero-volume exchange midpoint", "Retained Kalshi contract evidence reports volume 0.00 on both outcomes (midpoints from posted bid/ask only); the calibrated VRS model says ~65% for the same side. Same pick, soft number — do not treat 91.5% as bookmaker-grade.", "https://kalshi.com/markets/kxcs2game/kxcs2game-26oct180945pgex"),
        ("F7", "WROTBERRY identity + a superseded opposite pick", "finals joins Melbet's WhiteBIT–Nexus price to Nexus–WROTBERRY on a 5/5 roster proof (audit 6c5bb3d6), flipping the pick vs the desk's Nexus bound. The literal name 'WROTBERRY' appears nowhere off HotSpawn; if the played lineup differs, the join dies. Check the lineup at lock.", "https://www.hltv.org/matches/2399418/wbt-vs-eac-elisa-breakout-series-2"),
        ("F8", "Hacha price is stale and the team has stand-ins", "Melbet 2.279/1.57 last seen 12:09Z, absent at 18:26Z. HLTV insight: three stand-ins, core has 2 matches together. The 5%-crowd fade is explicitly rejected — this is the 'stupid' side of contrarian.", "https://melbet.com/en/line/esports"),
        ("F9", "Two model slopes exist in this repo", "Canonical board publishes Valve-raw k=1.0 (its own fit is below its 6-pair minimum); sessions 7177d07f/3e1be203 fitted k=0.4213 to book lines. finals uses the calibrated slope and prints k=1.0 beside every originated number. Picks never change between the two; percentages do (up to ~16pp on the final).", VRS_URL),
        ("F10", "Placeholder odds are circulating as if real", "EGamersWorld shows 1.8/1.8 widgets and HLTV analytics shows 1.23 placeholder links for unpriced matches; bo3.gg shows single winner-price numbers. None are two-sided prices; all are excluded here. Do not copy them from other sites.", "https://egamersworld.com/counterstrike/matches"),
        ("F11", "Lobby churn between captures", "Fixture 1081519 (NEXVOID–Off Chops) was absent from the 12:09Z capture and present at 18:26Z; PCIFIC–6yuBoJlbl locked in between. Any snapshot can miss a brand-new card for up to one refresh cycle (≤4h here, ~27 min on ourline).", LOBBY),
        ("F12", "Sashi–mouz NXT crowd sums to 101%", "78% + 23% as rendered by HotSpawn (rounding at source). Transcribed verbatim; leverage math uses each side as printed.", LOBBY),
        ("F13", "Day-4 climb backtest cuts both ways", "Taken climb (Aurora 49.3%) lost; rejected dog (BETBOOM 26.8%) won. Recorded on the TWC page. The 35% floor is not retro-fitted to two matches; flagging so the record is not cherry-picked later.", "https://www.hltv.org/results?event=8932"),
    ]
    fl = "".join(f'<article class=card id="{fid.lower()}"><h3>{fid} · {esc(t)}</h3><p>{esc(b)}</p><p class=small>Source: <a href="{esc(u)}">{esc(u)}</a></p></article>' for fid, t, b, u in flags)
    flagged_body = f"<h1>Flagged for Review</h1><p>Nothing below blocks publication; everything below must be visible before you trust a number. Values that could not be confirmed were left blank or bounded — never inferred.</p>{fl}"
    write("flagged.html", page("Flagged for Review", "flagged.html", flagged_body, generated, capture))

    # ---- method
    access = canon.get("access") or {}
    acc_rows = "".join(
        f'<tr><td>{esc(k)}</td><td>{esc(v.get("status"))}</td><td>{esc(v.get("at_utc"))}</td><td><a href="{esc(v.get("url"))}">endpoint</a></td></tr>'
        for k, v in access.items())
    method_body = f"""<h1>Method &amp; sources</h1>
<h2>How the HotSpawn lobby is reverse-engineered (retained collector)</h2>
<p>The pick'em lobby at <a href="{LOBBY}">play.hotspawn.com/lobby</a> is a server-rendered page whose transfer
state embeds the week's fixtures; the same data is served by its fixtures API
(<code>phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code>). The canonical collector
(<code>scripts/c64a5e19/</code>, engine <code>scripts/f7279a54/</code>) reads both, keeps CS2 fixtures whose
lock time is still ahead, and stores the raw snapshot + every quote payload under <code>data/c64a5e19/</code>.
HotSpawn data used here: fixture identity, start/lock UTC, tier, points — and, separately labelled, crowd
picked% as <strong>ownership</strong>. HotSpawn is never a probability source.</p>
<table><thead><tr><th>Source (this capture)</th><th>HTTP</th><th>Read (UTC)</th><th>Link</th></tr></thead><tbody>{acc_rows}</tbody></table>
<h2>Refresh cadence (no manual input)</h2>
<ul>
<li><code>update-data</code> workflow: hourly lobby + quote collection to <code>main</code>.</li>
<li><code>every-match-c64a5e19</code>: canonical board rebuild ≈ every 4 hours.</li>
<li><code>finals-782adb47</code> (this desk): every 4 hours and after each canonical refresh — inside the required 4–8h window. Expired locks drop to the locked section automatically; new lobby cards enter with the capture.</li>
<li>Editorial research (TWC results, roster timeline) is dated in <code>data/782adb47/research.json</code> and never reprices a market row.</li>
</ul>
<h2>Probability rules</h2>
<ul>
<li><strong>Market:</strong> per-book no-vig <code>p = (1/da) / (1/da + 1/db)</code>, arithmetic mean across accepted books (Pinnacle, Bovada, Melbet; Kalshi exchange midpoints only as flagged fallback). A quote joins a fixture only on agreeing teams (canonical names) + kickoff; alias joins additionally require published roster/slot proof.</li>
<li><strong>Model (originated):</strong> Valve's own Glicko expected-win curve on official VRS points, <code>p = sigmoid(k·C·Δ)</code> with RD=75; k=0.4213 market-calibrated (session 7177d07f fit, retained in-repo), k=1.0 shown as sensitivity. Source: <a href="{VRS_URL}">Valve standings 2026-10-05</a>.</li>
<li><strong>Bound:</strong> exactly one side rated → opponent priced at the list floor (381 pts); published as ≥, using the weaker duplicate row where a name is duplicated.</li>
<li><strong>Blank:</strong> no price + no rating pair → no number, no pick, listed on Unresolved with the attempt ledger.</li>
<li><strong>Safe pick</strong> = argmax probability. <strong>Climb switch</strong> requires dog ≥35%, leverage (prob − crowd) ≥15pp, ≥2 verified context flags; max 3/day. Context never moves the % — it only gates the switch.</li>
</ul>
<h2>Verification</h2>
<p>Every row links its fixture + price/rating source. Tests (<code>tests/test_782adb47.py</code>) re-derive every
published probability from its retained decimals or VRS points, check pick=argmax, check every canonical open
fixture appears exactly once, and check no HotSpawn crowd value enters a probability. Research reads with URLs
and timestamps: <code>data/782adb47/research.json</code>.</p>"""
    write("method.html", page("Method & sources", "method.html", method_body, generated, capture))
    print(f"finals built: {len(open_rows)} open ({counts}), {len(blank_rows)} blank, capture {capture}")


def write(name, content):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(content)


if __name__ == "__main__":
    main()
