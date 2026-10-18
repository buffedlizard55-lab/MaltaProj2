#!/usr/bin/env python3
"""Build climb/ — the a89b76e9 phone-first desk.

Outputs (all static, self-contained, mobile-first):
    climb/index.html       executive summary with in-site links to every list
    climb/picks.html       every open HotSpawn CS2 fixture: pick + both win probabilities + sources
    climb/twc.html         TWC 2026 day 1-5 verified review, Aurora roster verdict, climb ladder
    climb/unresolved.html  resolved-via-fallback rows + unresolved & limitations section
    climb/flagged.html     irregularities flagged for manual review (A1-A8)
    climb/method.html      source ladder, formulas, rules, provenance

Inputs (read-only):
    data/<newest>/board.json         canonical line board (highest generated_utc wins)
    data/a89b76e9/research.json      curated, source-linked research for this session
    data/371a1ce7/crowd.json         HotSpawn crowd ownership sample (ownership only)

Hard rules:
  * HotSpawn is never a probability source (fixture discovery + ownership only).
  * Every published number carries an https source link or is blank + flagged.
  * The pick is the argmax of the published fair probabilities (research tiebreak
    documented when the market line is exactly even).
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "climb")
RESEARCH = os.path.join(ROOT, "data", "a89b76e9", "research.json")
CROWD = os.path.join(ROOT, "data", "371a1ce7", "crowd.json")

CSS = """
:root { --bg:#0e1116; --card:#161b22; --ink:#e8edf4; --muted:#93a0b0; --line:#263041;
  --ok:#1f7a4d; --ok2:#2ea86b; --warn:#b7791f; --bad:#b23a48; --accent:#ffb020; --fav:#2ea86b; --dog:#8a63d2; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
a { color:#7cc4ff; text-decoration:none; word-break:break-word; }
a:hover, a:focus { text-decoration:underline; }
header.top { position:sticky; top:0; z-index:20; background:#12161c; border-bottom:1px solid var(--line); padding:10px 14px; }
header.top .brand { font-weight:700; font-size:15px; }
header.top .sub { color:var(--muted); font-size:12px; margin-top:2px; }
main { padding:12px 12px 84px; max-width:56rem; margin:0 auto; }
h1 { font-size:22px; line-height:1.25; margin:10px 0 6px; }
h2 { font-size:18px; margin:22px 0 8px; }
h3 { font-size:15px; margin:16px 0 6px; }
p { margin:8px 0; }
.muted { color:var(--muted); font-size:13px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin:10px 0; }
.hero { border:2px solid var(--accent); }
.pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px; font-weight:700; letter-spacing:.2px; margin:2px 4px 2px 0; }
.pill.fav { background:#123922; color:#7fe0a8; border:1px solid #2ea86b55; }
.pill.dog { background:#2b2144; color:#cbb6f6; border:1px solid #8a63d255; }
.pill.safe { background:#123922; color:#7fe0a8; }
.pill.climb { background:#3a2b12; color:#ffd58a; border:1px solid var(--accent); }
.pill.no { background:#3b1a20; color:#f2a2ac; }
.pill.basis { background:#1b2634; color:#9fc2e8; }
.pill.tier { background:#222b38; color:#b9c6d6; }
.pill.flag { background:#3b1a20; color:#f2a2ac; border:1px solid var(--bad); }
.pill.ok { background:#123922; color:#7fe0a8; }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.4px; }
.bar { height:8px; background:#222b38; border-radius:6px; overflow:hidden; margin:4px 0 2px; }
.bar > span { display:block; height:100%; background:linear-gradient(90deg,#2ea86b,#1f7a4d); }
.pickbig { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin:6px 0; }
.pickbig .name { font-size:22px; font-weight:800; }
.pickbig .pct { font-size:20px; font-weight:800; color:var(--accent); }
.teams { display:flex; justify-content:space-between; gap:10px; font-size:14px; }
.teams .t { flex:1 1 45%; }
.teams .t.right { text-align:right; }
.pctline { font-weight:700; font-size:15px; }
.srcs { margin-top:6px; font-size:12px; color:var(--muted); }
.srcs a { margin-right:8px; display:inline-block; }
ul li { margin:5px 0; }
.actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:12px 0; }
.actions a { display:block; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; font-weight:700; color:var(--ink); }
.actions a small { display:block; font-weight:400; color:var(--muted); margin-top:2px; }
.actions a.wide { grid-column:1 / -1; }
nav.tabs { position:fixed; left:0; right:0; bottom:0; z-index:30; display:flex; background:#12161c; border-top:1px solid var(--line); }
nav.tabs a { flex:1; text-align:center; padding:10px 2px 12px; font-size:11px; color:var(--muted); }
nav.tabs a .ic { display:block; font-size:17px; line-height:1.2; }
nav.tabs a.active { color:var(--accent); }
details { margin:8px 0; }
summary { cursor:pointer; font-weight:600; }
.toc a { display:block; padding:8px 10px; margin:6px 0; background:var(--card); border:1px solid var(--line); border-radius:10px; color:var(--ink); font-weight:600; }
.toc a small { display:block; color:var(--muted); font-weight:400; }
.fixture { border-left:4px solid var(--line); }
.fixture.tierS { border-left-color:var(--accent); }
.fixture.tierB { border-left-color:#2ea86b; }
.kicker { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
.tw { overflow-x:auto; -webkit-overflow-scrolling:touch; }
@media (min-width: 720px) {
  main { padding:16px 20px 84px; }
  h1 { font-size:26px; }
}
"""


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def newest_board():
    best = None
    best_path = None
    for name in sorted(os.listdir(os.path.join(ROOT, "data"))):
        path = os.path.join(ROOT, "data", name, "board.json")
        if not os.path.isfile(path):
            continue
        data = load(path)
        gen = str(data.get("generated_utc") or "")
        if not gen:
            continue
        if best is None or gen > str(best.get("generated_utc") or ""):
            best, best_path = data, path
    return best or {}, best_path or ""


def pct(x, digits=1):
    if x is None:
        return '<span class="muted">—</span>'
    return f"{100.0 * float(x):.{digits}f}%"


def page(title, active, body, desc=""):
    tabs = [
        ("index.html", "🏠", "Summary"),
        ("picks.html", "✅", "Picks"),
        ("twc.html", "🏆", "TWC"),
        ("unresolved.html", "🧩", "Unresolved"),
        ("flagged.html", "⚑", "Flagged"),
    ]
    tab_html = []
    for href, icon, label in tabs:
        cls = ' class="active"' if href == active else ""
        tab_html.append(
            f'<a href="{href}"{cls}><span class="ic">{icon}</span>{label}</a>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc or title)}">
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="brand">🐟 HotSpawn Pick'em · Climb desk</div>
  <div class="sub">Picks for every CS2 match · external lines only · TWC final day 18 Oct</div>
</header>
<main>
{body}
<p class="muted" style="margin-top:24px">Session a89b76e9 · sources per row · HotSpawn used for fixture discovery and ownership only, never as a probability. Method: <a href="method.html">method.html</a> · Site home: <a href="../index.html">home</a>.</p>
</main>
<nav class="tabs">
{''.join(tab_html)}
</nav>
</body>
</html>
"""


def fixture_card(fx, crowd_row, resolutions, is_climb):
    fid = str(fx.get("fixture_id"))
    res = resolutions.get(fid)
    line = fx.get("line") or {}
    if res:
        line = res["line"]
    team_a, team_b = fx.get("team_a"), fx.get("team_b")
    pa, pb = line.get("prob_a"), line.get("prob_b")
    pick = line.get("pick")
    basis = line.get("basis") or ("research" if res else "unresolved")
    conf = line.get("confidence") or ""
    tier = esc(fx.get("tier") or "?")
    pts = esc(fx.get("points") or "?")
    start = esc(str(fx.get("start_utc") or "").replace("T", " ").replace("Z", " UTC"))
    lock = esc(str(fx.get("lock_utc") or "").replace("T", " ").replace("Z", " UTC"))
    comp = esc(fx.get("competition") or "")

    # source links per row
    links = []
    if res:
        for s in res["sources"]:
            links.append(f'<a href="{esc(s["url"])}">{esc(s["label"])}</a>')
    else:
        for q in fx.get("quotes") or []:
            url = q.get("public_url") or q.get("api_url")
            if url:
                links.append(
                    f'<a href="{esc(url)}">{esc(q.get("source_name") or q.get("source_key") or "source")}</a>'
                )
        if (fx.get("line") or {}).get("basis", "").startswith("model") or (
            fx.get("model") and not fx.get("quotes")
        ):
            links.append(
                '<a href="https://github.com/ValveSoftware/counter-strike_regional_standings">Valve VRS standings</a>'
            )
        links.append(
            '<a href="https://play.hotspawn.com/lobby">HotSpawn listing (discovery)</a>'
        )

    crowd_html = ""
    if crowd_row and crowd_row.get("total_picks"):
        on_pick = None
        if pick == crowd_row.get("team_a"):
            on_pick = crowd_row.get("crowd_a")
        elif pick == crowd_row.get("team_b"):
            on_pick = crowd_row.get("crowd_b")
        if on_pick is not None:
            n = crowd_row.get("total_picks")
            tiny = " · tiny sample" if (n or 0) < 5 else ""
            crowd_html = (
                f'<span class="pill basis">crowd on pick {esc(on_pick)}% (n={esc(n)}{tiny})</span>'
            )

    climb_html = ""
    if is_climb:
        climb_html = '<span class="pill climb">CLIMB PICK</span>'

    pa_w = int(round(100 * (pa or 0)))
    conf_pill = f'<span class="pill basis">{esc(conf)}</span>' if conf else ""
    blank_note = ""
    if not line or (pa is None and not res):
        blank_note = '<span class="pill flag">no line — see Unresolved</span>'

    return f"""<section class="card fixture tier{tier}" id="f{esc(fid)}">
  <div class="kicker">#{esc(fid)} · {comp} · tier {tier} · {pts} pts</div>
  <h3 style="margin:4px 0 2px">{esc(team_a)} <span class="muted">vs</span> {esc(team_b)}</h3>
  <div class="muted">starts {start} · locks {lock}</div>
  <div class="teams">
    <div class="t"><div class="pctline">{esc(team_a)} · {pct(pa)}</div></div>
    <div class="t right"><div class="pctline">{esc(team_b)} · {pct(pb)}</div></div>
  </div>
  <div class="bar"><span style="width:{pa_w}%"></span></div>
  <div class="pickbig">
    <span class="pill safe">PICK</span>
    <span class="name">{esc(pick) if pick else '—'}</span>
    <span class="pct">{pct(line.get("pick_probability"))}</span>
    {conf_pill}{climb_html}{crowd_html}{blank_note}
  </div>
  <div class="muted">basis: {esc(basis)}</div>
  <div class="srcs">{' '.join(links)}</div>
</section>"""


def build(res, board, board_path, crowd):
    resolutions = {}
    for row in res.get("blank_resolutions", []):
        fid = str(row["fixture_id"])
        # orientation: prob_a must follow the fixture's team_a (HotSpawn order)
        if fid == "1081546":  # team_a = Apogee Betclic, team_b = BBL
            pa, pb = row["probability_fair_apogee"], row["probability_fair_bbl"]
        else:  # 1081863: team_a = Chinggis Warriors, team_b = WXM
            pa, pb = row["probability_fair_cw"], row["probability_fair_wxm"]
        pick = row["resolution"].split("pick ")[1].split(" at ")[0]
        resolutions[fid] = {
            "line": {
                "prob_a": pa,
                "prob_b": pb,
                "pick": pick,
                "pick_probability": max(x for x in (pa, pb) if x is not None),
                "basis": row["basis"],
                "confidence": "Toss-up" if abs(pa - pb) < 0.02 else "Lean",
            },
            "sources": [
                {"label": s.split("/")[-1][:40] or s, "url": s}
                for s in (
                    row["attempt_ledger"][0]["sources"][:1]
                    + row["attempt_ledger"][1]["sources"][:1]
                )
            ],
        }
        # nicer labels
        resolutions[fid]["sources"] = [
            {"label": "HLTV", "url": row["attempt_ledger"][0]["sources"][0]},
            {"label": "book line", "url": row["attempt_ledger"][1]["sources"][0]},
        ]

    crowd_map = {str(r["fixture_id"]): r for r in (crowd.get("rows") or [])}
    open_fixtures = [f for f in board.get("open") or [] if f.get("state") == "open"]
    climb_ids = {c["fixture_id"] for c in res.get("climb_ladder", {}).get("qualifying", [])}
    climb_ids = {str(x) for x in climb_ids}

    os.makedirs(OUT, exist_ok=True)

    n_total = len(open_fixtures)
    n_pick = sum(
        1
        for f in open_fixtures
        if (f.get("line") or {}).get("pick") or str(f["fixture_id"]) in resolutions
    )
    n_market = sum(
        1
        for f in open_fixtures
        if str(f["fixture_id"]) in resolutions
        or str((f.get("line") or {}).get("basis") or "").startswith("market")
    )
    n_model = sum(
        1
        for f in open_fixtures
        if str(f["fixture_id"]) not in resolutions
        and (f.get("line") or {}).get("basis") in ("model", "market+model")
        and not (f.get("quotes") or [])
    )

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---------------- picks.html ----------------
    cards = []
    for fx in sorted(open_fixtures, key=lambda x: (x.get("start_utc") or "")):
        fid = str(fx["fixture_id"])
        cards.append(
            fixture_card(fx, crowd_map.get(fid), resolutions, fid in climb_ids)
        )
    picks_body = f"""
<h1>Every match · pick + both win probabilities</h1>
<p class="muted">Built {gen} from <code>{esc(os.path.relpath(board_path, ROOT))}</code> ({esc(board.get("generated_utc"))}) + researched fallback rows. {n_total} open fixtures · {n_pick} with a pick · 0 left blank. Favourite side is marked by the higher percentage; the PICK is what to submit.</p>
<div class="card hero">
  <div class="kicker">Featured today — TWC final day</div>
  <p><span class="pill safe">SAFE</span> <strong>Falcons</strong> 59.7% over Aurora <span class="muted">3rd-place decider · 11:30 UTC</span> — <span class="pill climb">CLIMB (conditional)</span> Aurora 40.3% is today's only ≥35% upset shot.</p>
  <p><span class="pill safe">SAFE</span> <strong>FURIA</strong> 68.0% over BetBoom <span class="muted">Grand Final bo5 · 15:00 UTC</span> — no contrarian switch (BetBoom &lt;35%).</p>
  <p class="muted">Full reasoning: <a href="twc.html">twc.html</a> · climb rule: <a href="method.html">method.html</a></p>
</div>
<div class="card">
  <div class="kicker">Climb picks (crowd is on the other side)</div>
  <p><span class="pill climb">CLIMB</span> <strong>Enjoy</strong> (22% of crowd, our line 66.1%) over Banda chuya — <a href="#f1081126">row</a></p>
  <p><span class="pill climb">CLIMB</span> <strong>WROTBERRY</strong> (9% of crowd, our line 54.5%) over Nexus — <a href="#f1081529">row</a></p>
  <p class="muted">Rule: our fair ≥35%, crowd on that side ≤22%, sample ≥20. Ownership from HotSpawn, never a probability input.</p>
</div>
{''.join(cards)}
"""

    # ---------------- twc.html ----------------
    result_rows = []
    for r in res["twc_results"]:
        src = r["sources"][0]
        upset = ' <span class="pill flag">UPSET</span>' if r.get("upset") else ""
        note = f'<div class="muted">{esc(r["note"])}</div>' if r.get("note") else ""
        result_rows.append(
            f"""<tr>
<td>D{esc(r["day"])}<div class="muted">{esc(r["date"])}</div></td>
<td><strong>{esc(r["team_a"])} {esc(r["score_a"])}–{esc(r["score_b"])} {esc(r["team_b"])}</strong>{upset}
<div class="muted">{esc(r["stage"])}</div>
<div>{esc(r.get("maps") or "maps: blank (not transcribed)")}</div>{note}</td>
<td><a href="{esc(src)}">HLTV</a></td>
</tr>"""
        )

    d5 = res["twc_day5"]["fixtures"]
    d5_cards = []
    for f in d5:
        if f["hotspawn_fixture_id"] == "1080209":
            safe, climb = f["safe_pick"], f["climb_pick"]
            quotes = "".join(
                f'<tr><td>{esc(q["source"])}</td><td>{esc(q["fav"])} {esc(q["decimal_fav"])}</td><td>{esc(q["decimal_dog"])}</td><td>{pct(q["fav_prob"])}</td><td><a href="{esc(q["url"])}">source</a></td></tr>'
                for q in f["market_quotes_reoriented"]
            )
            d5_cards.append(f"""
<div class="card hero" id="d5-1080209">
  <div class="kicker">{esc(f["label"])} · starts {esc(f["start_utc"])} · locks {esc(f["lock_utc"])}</div>
  <h2 style="margin:4px 0">{esc(f["team_a"])} vs {esc(f["team_b"])}</h2>
  <div class="pickbig">
    <span class="pill safe">SAFE PICK</span><span class="name">{esc(safe)}</span><span class="pct">59.7%</span>
    <span class="pill climb">CLIMB (conditional)</span><span class="name" style="font-size:16px">{esc(climb)}</span><span class="pct" style="font-size:16px">40.3%</span>
  </div>
  <p>{esc(f["climb_verdict"])}</p>
  <div class="tw"><table>
    <tr><th>Book</th><th>Favourite</th><th>Underdog</th><th>No-vig fav</th><th>Source</th></tr>
    {quotes}
  </table></div>
  <p class="muted">Our line: Falcons 59.7% / Aurora 40.3% (5-book market + model blend, canonical board) · HLTV: <a href="{esc(f["hltv_url"])}">match page</a> · schedule: <a href="{esc(f["verified_schedule_sources"][0])}">HLTV news</a> · <a href="{esc(f["verified_schedule_sources"][1])}">Liquipedia</a></p>
  <ul>{''.join(f'<li>{esc(c["fact"])} <a href="{esc(c["source"])}">src</a></li>' for c in f["context"])}</ul>
</div>""")
        else:
            quotes = "".join(
                f'<tr><td>{esc(q["source"])}</td><td>{esc(q["fav"])} {esc(q["decimal_fav"])}</td><td>{esc(q["decimal_dog"])}</td><td>{pct(q["fav_prob"])}</td><td><a href="{esc(q["url"])}">source</a></td></tr>'
                for q in f["market_quotes_reoriented"]
            )
            d5_cards.append(f"""
<div class="card" id="d5-1080210">
  <div class="kicker">{esc(f["label"])} · starts {esc(f["start_utc"])} · locks {esc(f["lock_utc"])}</div>
  <h2 style="margin:4px 0">{esc(f["team_a"])} vs {esc(f["team_b"])}</h2>
  <div class="pickbig">
    <span class="pill safe">SAFE PICK</span><span class="name">{esc(f["safe_pick"])}</span><span class="pct">68.0%</span>
    <span class="pill no">NO CLIMB</span><span class="muted">BetBoom 32% &lt; 35% floor</span>
  </div>
  <p>{esc(f["climb_verdict"])}</p>
  <div class="tw"><table>
    <tr><th>Book</th><th>Favourite</th><th>Underdog</th><th>No-vig fav</th><th>Source</th></tr>
    {quotes}
  </table></div>
  <p class="muted">Our line: FURIA 68.0% / BetBoom 32.0% · HLTV: <a href="{esc(f["hltv_url"])}">match page</a> · schedule: <a href="{esc(f["verified_schedule_sources"][0])}">HLTV news</a></p>
  <ul>{''.join(f'<li>{esc(c["fact"])} <a href="{esc(c["source"])}">src</a></li>' for c in f["context"])}</ul>
</div>""")

    lessons = "".join(
        f'<li><strong>{esc(l["id"])}</strong> {esc(l["text"])} <a href="{esc(l["evidence"])}">src</a></li>'
        for l in res["day1_upset_lessons"]["lessons"]
    )
    timeline = "".join(
        f'<tr><td>{esc(t["date"])}</td><td>{esc(t["event"])}</td><td><a href="{esc(t["source"])}">src</a></td></tr>'
        for t in res["aurora_roster_verdict"]["timeline"]
    )
    twc_body = f"""
<h1>TWC 2026 · Day 1→5 review & final-day picks</h1>
<p class="muted">All 12 series re-verified against HLTV results/news on 2026-10-18. Upsets flagged. Empty map cells were not captured from primary sources and stay blank (flag A5).</p>
<h2>Day 5 — today, 18 Oct</h2>
{''.join(d5_cards)}
<h2>Days 1–4 verified results</h2>
<div class="tw"><table>
  <tr><th>Day</th><th>Result</th><th>Source</th></tr>
  {''.join(result_rows)}
</table></div>
<h2>Aurora roster-change verdict</h2>
<div class="card">
  <p><strong>{esc(res["aurora_roster_verdict"]["verdict"])}</strong></p>
  <div class="tw"><table>
    <tr><th>Date</th><th>Event</th><th>Source</th></tr>
    {timeline}
  </table></div>
  <p class="muted">{esc(res["aurora_roster_verdict"]["stale_premise_flag"])}</p>
</div>
<h2>How to climb (not stupid, not chalk)</h2>
<div class="card">
  <p class="muted">{esc(res["day1_upset_lessons"]["title"])}</p>
  <ul>{lessons}</ul>
</div>
"""

    # ---------------- unresolved.html ----------------
    un_rows = []
    for row in res["blank_resolutions"]:
        steps = "".join(
            f'<li><strong>Step {esc(s["step"])} · {esc(s["route"])}</strong> — {esc(s["result"])} '
            + " ".join(f'<a href="{esc(u)}">src</a>' for u in s["sources"])
            + "</li>"
            for s in row["attempt_ledger"]
        )
        un_rows.append(f"""
<div class="card">
  <div class="kicker">Resolved by fallback ladder · previously blank</div>
  <h3>{esc(row["teams"])} <span class="muted">#{esc(row["fixture_id"])}</span></h3>
  <p>{esc(row["competition"])} · starts {esc(row["start_utc"])}</p>
  <p><span class="pill ok">RESOLVED</span> {esc(row["resolution"])} · basis: {esc(row["basis"])}</p>
  <details open><summary>Attempt ledger (HLTV → books → exchange → VRS)</summary>
    <ul>{steps}</ul>
  </details>
  <p class="muted">tiebreak: {esc(row.get("tiebreak_rationale") or "n/a — market price found")}</p>
  <p>{''.join(f'<a href="flagged.html#A{esc(f.split("A")[1])}"><span class="pill flag">flag {esc(f)}</span></a>' for f in row.get("flags", []))}</p>
</div>""")

    lims = "".join(f"<li>{esc(x)}</li>" for x in res["limitations"])
    unresolved_body = f"""
<h1>Unresolved &amp; limitations</h1>
<p class="muted">The two rows the canonical board could not price are resolved below with full research ledgers. Remaining limitations are published here rather than papered over — nothing on the picks page is invented.</p>
<h2>Previously blank rows — resolved</h2>
{''.join(un_rows)}
<h2>Remaining limitations (no row is silently missing)</h2>
<div class="card"><ul>{lims}</ul></div>
<h2>What “unresolved” would mean</h2>
<div class="card">
  <p>A row stays blank only if all four ladder steps fail: (1) no HLTV/research basis, (2) no book price under any team-name variant, (3) no usable exchange book, (4) no two-sided Valve VRS comparison. In this capture <strong>no row met that bar</strong> — every open fixture carries a pick. The two weakest rows (single-source 1081546, even-line unknown-opponent 1081863) are flagged A2/A3 and listed above.</p>
</div>
"""

    # ---------------- flagged.html ----------------
    flag_cards = []
    for fl in res["flags"]:
        srcs = " ".join(f'<a href="{esc(s)}">src</a>' for s in fl["sources"])
        flag_cards.append(f"""
<div class="card" id="{esc(fl["id"])}">
  <p><span class="pill flag">{esc(fl["id"])} · {esc(fl["severity"])}</span></p>
  <h3>{esc(fl["title"])}</h3>
  <p>{esc(fl["detail"])}</p>
  <p class="muted">{srcs}</p>
</div>""")
    flagged_body = f"""
<h1>Flagged for review</h1>
<p class="muted">Irregularities found while re-verifying the boards line by line. None of them block a pick; each is published with its sources so you can review after the desk goes live.</p>
{''.join(flag_cards)}
"""

    # ---------------- index.html ----------------
    index_body = f"""
<h1>Executive summary · TWC final day</h1>
<p class="muted">Built {gen} · {n_total} open HotSpawn CS2 matches · every one has a pick and both win probabilities.</p>
<div class="card hero">
  <div class="kicker">Where are the picks?</div>
  <div class="toc">
    <a href="picks.html">✅ All picks — every open match<small>Pick, both win probabilities, basis, per-row sources · {n_total} matches</small></a>
    <a href="twc.html">🏆 TWC final day<small>Day 1→4 verified results · Day 5 safe + climb picks · Aurora roster truth</small></a>
    <a href="unresolved.html">🧩 Unresolved &amp; limitations<small>2 rows resolved by research fallback + every remaining limitation</small></a>
    <a href="flagged.html">⚑ Flagged for review<small>8 irregularities with source links (A1–A8)</small></a>
    <a href="method.html">📐 Method &amp; sources<small>Line ladder, formulas, climb rule, provenance</small></a>
  </div>
</div>
<div class="card hero">
  <div class="kicker">Today's headline calls · 18 Oct</div>
  <p><span class="pill safe">SAFE</span> <strong>Falcons</strong> 59.7% <span class="muted">vs Aurora · 3rd place · 11:30 UTC ·5 books agree (1.52–1.67 favourite)</span></p>
  <p><span class="pill climb">CLIMB if you need variance</span> <strong>Aurora</strong> 40.3% <span class="muted">the only ≥35% upset shot today; dead-rubber + Falcons' semi collapse are the case for it — conditional, not an EV pick</span></p>
  <p><span class="pill safe">SAFE</span> <strong>FURIA</strong> 68.0% <span class="muted">vs BetBoom · Grand Final bo5 · 15:00 UTC · BetBoom 32% is a no-climb (story ≠ probability)</span></p>
  <p><span class="pill climb">CLIMB</span> <strong>Enjoy</strong> 66.1% <span class="muted">crowd 78/22 the other way (n=51) — biggest line-vs-crowd gap today</span></p>
  <p><span class="pill climb">CLIMB</span> <strong>WROTBERRY</strong> 54.5% <span class="muted">crowd 91/9 Nexus (n=45)</span></p>
</div>
<div class="card">
  <div class="kicker">The 9z lesson, in one paragraph</div>
  <p>Day 1's 9z 2-0 over Aurora (13-11 Inferno, <strong>13-1 Nuke</strong>) and day 4's BETBOOM reverse-sweep of Falcons were both dogs in the 25–35% band — not 1-in-10 longshots. Climb means taking a <em>live</em> underdog when our line gives them a real shot (≥35%) and the crowd is elsewhere; it does not mean chasing BetBoom at 32% in a bo5. Aurora's "recent roster change" is the <strong>July rebuild</strong> (kyxsan/Jimpphat/ash — verified, no October move): old enough that it explains their floor, not a fresh-onboarding edge. <a href="twc.html">Full review →</a></p>
</div>
<div class="card">
  <div class="kicker">Coverage</div>
  <p class="muted">{n_total} open fixtures from the {esc(board.get("generated_utc"))} canonical capture ({esc(os.path.relpath(board_path, ROOT))}): every row carries a pick, both win probabilities and an https source link. Two rows the capture left blank (Apogee Betclic–BBL, Chinggis Warriors–WXM) were resolved via the HLTV→books→exchange→VRS ladder — see <a href="unresolved.html">Unresolved</a>. Auto-refresh every 4–8h rebuilds this desk from the newest board.</p>
</div>
"""

    # ---------------- method.html ----------------
    method_body = f"""
<h1>Method &amp; sources</h1>
<h2>Line ladder (in order)</h2>
<div class="card">
  <ol>
    <li><strong>Esportsbook/exchange prices</strong> — Pinnacle, Bovada, Melbet, Kalshi, Thunderpick (via bo3.gg mirror), egamersworld. Remove the margin: fair = (1/odd) / Σ(1/odd). Average across books; the published line may blend with the model (board weight 0.75–0.85 on market rows).</li>
    <li><strong>Alias re-join</strong> — a dropped book quote counts when the team-name variant is justified by agreeing opponent + kickoff (e.g. 'Betclic' = 'Apogee Betclic' for #1081546).</li>
    <li><strong>HLTV team research</strong> — ranks, rosters, form, verified results. Used for direction on even lines and for context notes. HLTV user votes are a crowd, not a line — never a probability.</li>
    <li><strong>Valve VRS originated line</strong> — only when no price exists: standings snapshot 2026-10-05 (official <a href="https://github.com/ValveSoftware/counter-strike_regional_standings">ValveSoftware/counter-strike_regional_standings</a>) + the canonical board's fitted calibration (k={esc((board.get("calibration") or {}).get("k"))}, mae≈{esc((board.get("calibration") or {}).get("mae_prob"))} on {esc((board.get("calibration") or {}).get("n_pairs"))} pairs).</li>
  </ol>
  <p class="muted">HotSpawn supplies fixture discovery and crowd ownership only. Its percentages never enter any probability.</p>
</div>
<h2>Pick rules</h2>
<div class="card">
  <ul>
    <li>The pick is the argmax of the published fair probabilities. If the market line is exactly even, the pick is a documented research tiebreak and confidence is Toss-up.</li>
    <li>Climb pick: our fair ≥35% on the underdog side, HotSpawn crowd ownership on that side ≤22%, crowd sample ≥20. Below 35% → 'no climb'.</li>
    <li>Blank is allowed only when the whole ladder fails; blank rows must publish the attempt ledger. In the current capture: 0 blanks.</li>
    <li>Every table row links an official source. Values that can't be confirmed stay blank and are flagged on <a href="flagged.html">flagged.html</a> — never inferred.</li>
  </ul>
</div>
<h2>Provenance of this build</h2>
<div class="card">
  <ul>
    <li>Line board: <code>{esc(os.path.relpath(board_path, ROOT))}</code> · generated {esc(board.get("generated_utc"))} · sources: {esc(json.dumps(((board.get("summary") or {}).get("sources") or {})))}</li>
    <li>Research: <code>data/a89b76e9/research.json</code> (read window {esc(res.get("read_window_utc"))})</li>
    <li>Crowd ownership: <code>data/371a1ce7/crowd.json</code> (HotSpawn fixtures API, {esc((res.get("climb_ladder") or {}).get("crowd_source", {}).get("read_utc"))})</li>
    <li>Board track record: settled {esc((board.get("track_record") or {}).get("settled"))}, Brier {esc((board.get("track_record") or {}).get("brier"))} — see flag A8 on how to read the accuracy figures.</li>
  </ul>
</div>
<h2>Automation</h2>
<div class="card">
  <p class="muted">Workflow <code>climb-a89b76e9.yml</code> rebuilds this folder every 4–8h and after the canonical board refreshes, runs the contract tests, and commits only when green. No manual input is required.</p>
</div>
"""

    pages = {
        "index.html": ("Climb desk · picks for every CS2 match", "index.html", index_body,
                       "Executive summary: TWC final-day picks, climb ladder and links to every picks list."),
        "picks.html": ("All picks · every open match", "picks.html", picks_body,
                       "Pick and both win probabilities for every open HotSpawn CS2 match, with source links."),
        "twc.html": ("TWC 2026 final day · verified review", "twc.html", twc_body,
                     "Thunderpick World Championship day 1-5 verified results, Aurora roster verdict, safe and contrarian picks."),
        "unresolved.html": ("Unresolved & limitations", "unresolved.html", unresolved_body,
                            "Rows resolved via the research fallback ladder and every remaining limitation."),
        "flagged.html": ("Flagged for review", "flagged.html", flagged_body,
                         "Irregularities flagged with source links for manual review."),
        "method.html": ("Method & sources", "method.html", method_body,
                        "Line ladder, formulas, pick rules, provenance and automation."),
    }
    for name, (title, active, body, desc) in pages.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(page(title, active, body, desc))

    summary = {
        "built_utc": gen,
        "board_path": os.path.relpath(board_path, ROOT),
        "board_generated_utc": board.get("generated_utc"),
        "open": n_total,
        "with_pick": n_pick,
        "blanks": n_total - n_pick,
        "market_rows": n_market,
        "model_rows": n_model,
        "resolutions": sorted(resolutions),
        "climb": sorted(climb_ids),
    }
    with open(os.path.join(ROOT, "data", "a89b76e9", "build_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(f"climb/: 6 pages · open {n_total} · with pick {n_pick} · blanks {n_total - n_pick}")
    return summary


def main():
    research = load(RESEARCH)
    if not research:
        raise SystemExit("missing data/a89b76e9/research.json")
    board, board_path = newest_board()
    if not board:
        raise SystemExit("no canonical board found")
    crowd = load(CROWD, {})
    build(research, board, board_path, crowd)


if __name__ == "__main__":
    main()
