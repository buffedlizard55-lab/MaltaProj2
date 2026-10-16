#!/usr/bin/env python3
"""Render the mobile desk (session 6484426f) from data/6484426f/board.json.

Self-contained pages: no external CSS or fonts, so a phone loads one file per page and the
GitHub Pages artifact has no third-party dependency. Every table row carries at least one
https source link; blank values stay blank.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "6484426f"
DESK = ROOT / "desk"
BOARD = OUT / "board.json"
VERIFY = OUT / "verification.json"
LOBBY = "https://play.hotspawn.com/lobby"
CANON = "https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/data/c64a5e19/board.json"

CSS = """
:root{color-scheme:light dark;--bg:#f7f8fa;--fg:#14181f;--muted:#5b6472;--card:#fff;--line:#e3e7ee;
--accent:#0b5fff;--good:#0f7b46;--warn:#a45b00;--bad:#b3261e;--chip:#eef2f9}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--fg:#e8ecf2;--muted:#9aa4b2;--card:#161a21;
--line:#262c36;--accent:#6ea8ff;--chip:#1d232d}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding-bottom:3rem}
a{color:var(--accent)}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);z-index:9}
.wrap{max-width:60rem;margin:0 auto;padding:0 .75rem}
header .wrap{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;padding:.55rem .75rem}
header b{font-size:1rem}
nav{display:flex;flex-wrap:wrap;gap:.35rem;width:100%}
nav a{background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:.42rem .7rem;
font-size:.86rem;text-decoration:none;white-space:nowrap}
nav a[aria-current="page"]{background:var(--accent);color:#fff;border-color:var(--accent)}
main{padding-top:.85rem}
h1{font-size:1.35rem;margin:.4rem 0 .5rem}
h2{font-size:1.1rem;margin:1.1rem 0 .4rem}
h3{font-size:1rem;margin:.9rem 0 .3rem}
p,li{overflow-wrap:anywhere}
.muted{color:var(--muted);font-size:.88rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:.5rem;margin:.6rem 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:.7rem;padding:.6rem}
.kpi b{display:block;font-size:1.4rem;line-height:1.2}
.cta{display:grid;grid-template-columns:1fr;gap:.5rem;margin:.7rem 0}
.cta a{display:block;background:var(--card);border:1px solid var(--line);border-left:.35rem solid var(--accent);
border-radius:.7rem;padding:.75rem .8rem;text-decoration:none;color:var(--fg)}
.cta a b{display:block;font-size:1.05rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:.8rem;padding:.7rem;margin:.6rem 0}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;vertical-align:top;padding:.45rem .4rem;border-bottom:1px solid var(--line)}
th{font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;
padding:.1rem .45rem;font-size:.74rem;margin:.1rem .15rem .1rem 0;white-space:nowrap}
.chip.m{background:#e6f0ff;color:#0b3d91}.chip.e{background:#e8f7ee;color:#0f5c36}
.chip.o{background:#fff2e0;color:#7a4400}.chip.u{background:#fdecec;color:#8c1d18}
@media (prefers-color-scheme:dark){.chip.m{background:#12294d;color:#cfe0ff}.chip.e{background:#123526;color:#c8f0d8}
.chip.o{background:#3a2a10;color:#ffd9a3}.chip.u{background:#3d1a18;color:#ffc9c5}}
.pick{font-weight:600}
.bar{height:.62rem;border-radius:999px;background:var(--chip);overflow:hidden;display:flex}
.bar span{display:block;height:100%}
.bar .a{background:#0b5fff}.bar .b{background:#8a94a6}
.pct{font-variant-numeric:tabular-nums}
.matches{display:grid;grid-template-columns:1fr;gap:.6rem}
.match{background:var(--card);border:1px solid var(--line);border-radius:.8rem;padding:.65rem}
.match h3{margin:0 0 .25rem;font-size:1rem;display:flex;justify-content:space-between;gap:.4rem}
.match .row{display:flex;justify-content:space-between;gap:.5rem;align-items:baseline}
.match .side{display:flex;justify-content:space-between;gap:.5rem;margin:.18rem 0}
.match .side b{font-size:.95rem}
.match .side .num{font-variant-numeric:tabular-nums;color:var(--muted)}
.match .side.chosen b{color:var(--good)}
table.cards{display:block}
table.cards thead{display:none}
table.cards tbody,table.cards tr,table.cards td{display:block;width:100%}
table.cards tr{border:1px solid var(--line);border-radius:.8rem;background:var(--card);
margin:0 0 .6rem;padding:.55rem .6rem}
table.cards td{border:0;padding:.2rem 0}
table.cards td::before{content:attr(data-label);display:block;font-size:.72rem;text-transform:uppercase;
letter-spacing:.03em;color:var(--muted)}
footer{margin-top:1.4rem;border-top:1px solid var(--line);padding-top:.6rem}
@media (min-width:48rem){.cta{grid-template-columns:1fr 1fr}.matches{grid-template-columns:1fr 1fr}}
"""

PAGES = [("index.html", "Summary"), ("picks.html", "All picks"), ("twc.html", "TWC day 3"),
         ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"),
         ("method.html", "Method"), ("verify.html", "Verification")]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value, digits=1) -> str:
    return "—" if value is None else f"{100 * float(value):.{digits}f}%"


def chip(basis: str) -> str:
    label = {"market": "M · market", "exchange": "E · exchange", "model": "O · originated (Valve VRS)",
             "unresolved": "U · unresolved"}.get(basis, basis)
    klass = {"market": "m", "exchange": "e", "model": "o", "unresolved": "u"}.get(basis, "")
    return f'<span class="chip {klass}">{esc(label)}</span>'


def source_links(row) -> str:
    parts = []
    for source in row.get("sources") or []:
        label = esc(source.get("label") or "source")
        stamp = f' <span class="muted">{esc(str(source.get("retrieved_utc"))[11:16])}Z</span>' \
            if source.get("retrieved_utc") else ""
        parts.append(f'<a href="{esc(source.get("url"))}" rel="noopener">{label}</a>{stamp}')
    return "<br>".join(parts) if parts else '<span class="muted">no source link</span>'


def page(name: str, title: str, body: str, generated: str) -> str:
    current = ' aria-current="page"'
    nav = "".join(
        f'<a href="{href}"{current if href == name else ""}>{label}</a>' for href, label in PAGES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · CS2 picks desk</title>
<meta name="description" content="Mobile CS2 pick'em desk: a pick and win probability for every open HotSpawn fixture, with source links.">
<style>{CSS}</style></head>
<body>
<header><div class="wrap"><b>CS2 picks desk</b>
<span class="muted">built {esc(generated)}</span>
<nav>{nav}</nav></div></header>
<main class="wrap">{body}
<footer class="muted">Session 6484426f · data: <a href="{LOBBY}">HotSpawn lobby</a> (fixtures, points, crowd ownership) ·
lines: <a href="https://www.pinnacle.com/en/esports/cs2-hub">Pinnacle</a>,
<a href="https://www.bovada.lv/sports/esports">Bovada</a>,
<a href="https://melbet.com/en/line/esports">Melbet</a>,
<a href="https://kalshi.com/markets/kxcs2game">Kalshi</a>,
<a href="https://bo3.gg/matches">Thunderpick coefficients via bo3.gg</a> ·
ratings: <a href="https://github.com/ValveSoftware/counter-strike_regional_standings">official Valve standings</a> ·
crowd % is ownership only and is never used as a probability.</footer></main></body></html>
"""


def match_card(row) -> str:
    pa, pb = row.get("prob_a"), row.get("prob_b")
    safe = row.get("safe_pick")
    climb = row.get("climb_pick")
    climb_differs = bool(climb and climb != safe)
    width_a = int(round(100 * pa)) if pa is not None else 50
    sides = []
    for name, prob in ((row["team_a"], pa), (row["team_b"], pb)):
        chosen = " chosen" if name == safe else ""
        sides.append(f'<div class="side{chosen}"><b>{esc(name)}</b>'
                     f'<span class="num">{pct(prob)}</span></div>')
    crowd = row.get("crowd") or {}
    own = (f'crowd {crowd.get("pct_a")}% / {crowd.get("pct_b")}%'
           f' · {crowd.get("total_picks")} picks') if crowd else "crowd share not published"
    climb_note = ""
    if climb_differs:
        u = row.get("underdog") or {}
        climb_note = (f'<div class="muted">climb pick <b>{esc(climb)}</b>'
                      f'{" at " + pct(u.get("prob")) if u.get("prob") else ""}'
                      f'{", leverage " + format(row["leverage"], ".2f") + "×" if row.get("leverage") else ""}'
                      f' — separation from the field, above the declared 30% floor</div>')
    elif row.get("leverage"):
        climb_note = (f'<div class="muted">underdog {esc((row.get("underdog") or {}).get("team") or "")}'
                      f' at {pct((row.get("underdog") or {}).get("prob"))}, leverage '
                      f'{format(row["leverage"], ".2f")}× — below the climb gate</div>')
    flags = "".join(f'<span class="chip">{esc(f)}</span>' for f in row.get("flags") or [])
    limit = (f'<div class="muted">Limitation: {esc(row.get("limitation"))}</div>'
             if row.get("limitation") else "")
    age = row.get("quote_age_hours")
    age_note = f'{"" if age is None else f"price age {age:.1f}h"}' if row.get("quotes") else "no external price"
    return f"""<div class="match">
<h3><span>{esc(row['team_a'])} vs {esc(row['team_b'])}</span>
<span class="muted">{esc(str(row.get('start_utc'))[11:16])}Z</span></h3>
<div class="row"><span class="muted">{esc(row.get('competition'))} · {esc(row.get('points'))} pts ·
{esc(str(row.get('tier')))} tier · {age_note}</span></div>
{sides[0]}{sides[1]}
<div class="bar" aria-hidden="true"><span class="a" style="width:{width_a}%"></span>
<span class="b" style="width:{100 - width_a}%"></span></div>
<div class="row"><span>{chip(row.get('basis'))} <span class="pick">pick {esc(safe) or "—"}</span></span>
<span class="muted">{esc(row.get('tie_break')) if row.get('tie_break') else ''}</span></div>
{climb_note}
<div class="muted">{esc(own)}</div>
<div class="muted">{flags}</div>
{limit}
<div class="muted">{source_links(row)}</div></div>"""


def build() -> dict:
    board = json.loads(BOARD.read_text())
    verification = None
    if VERIFY.exists():
        try:
            verification = json.loads(VERIFY.read_text())
        except ValueError:
            verification = None
    DESK.mkdir(exist_ok=True)
    generated = board["generated_utc"]
    rows = board["rows"]
    summary = board["summary"]
    twc = board.get("twc") or {}
    deciders = twc.get("rows") or {}

    idx_rows = "".join(
        f'<tr><td data-label="Match"><a href="picks.html#{esc(r["fixture_id"])}">{esc(r["team_a"])} vs '
        f'{esc(r["team_b"])}</a><br><span class="muted">{esc(str(r.get("start_utc"))[11:16])}Z · '
        f'{esc(r.get("competition"))} · {esc(r.get("points"))} pts</span></td>'
        f'<td data-label="Pick"><span class="pick">{esc(r.get("safe_pick")) or "—"}</span> '
        f'{chip(r.get("basis"))}</td>'
        f'<td data-label="Win probability" class="pct">{pct(r.get("prob_a"))} / {pct(r.get("prob_b"))}</td>'
        f'<td data-label="Climb">{esc(r.get("climb_pick")) or "—"}</td>'
        f'<td data-label="Sources">{source_links(r)}</td></tr>' for r in rows)

    unresolved = [r for r in rows if r["basis"] == "unresolved"]
    ambiguous = [r for r in rows for note in
                 ((r.get("vrs") or {}).get("team_a", {}).get("notes", [])
                  + (r.get("vrs") or {}).get("team_b", {}).get("notes", []))
                 if note.get("type") == "ambiguous_official_name"]
    alias_rows = [r for r in rows for note in
                  ((r.get("vrs") or {}).get("team_a", {}).get("notes", [])
                   + (r.get("vrs") or {}).get("team_b", {}).get("notes", []))
                  if note.get("type") == "identity_alias"]
    stale = [r for r in rows if r.get("quote_stale")]
    single = [r for r in rows if "single_book_price" in (r.get("flags") or [])]

    # ------------------------------------------------------------------ executive summary
    home = f"""
<h1>CS2 picks desk — every open HotSpawn match, sourced</h1>
<p class="muted">One pick and both win probabilities for <b>every</b> open Counter-Strike 2 fixture on the
HotSpawn pick'em lobby, plus a day-1/2 review and day-3 calls for the Thunderpick World Championship 2026.
Prices come from external bookmakers and the Kalshi exchange; matches no bookmaker prices get an
explicitly labelled line originated from Valve's official ratings. HotSpawn supplies fixtures, points and
crowd shares only — its crowd % is never a probability.</p>
<div class="kpis">
<div class="kpi"><span class="muted">Open fixtures</span><b>{summary['open']}</b></div>
<div class="kpi"><span class="muted">With a pick</span><b>{summary['with_pick']}</b></div>
<div class="kpi"><span class="muted">External line</span><b>{summary['market']}</b></div>
<div class="kpi"><span class="muted">Exchange line</span><b>{summary['exchange']}</b></div>
<div class="kpi"><span class="muted">Originated line</span><b>{summary['model']}</b></div>
<div class="kpi"><span class="muted">Unresolved</span><b>{summary['unresolved']}</b></div>
</div>
<div class="cta">
<a href="picks.html"><b>Every match: pick + probability →</b>
<span class="muted">All {summary['open']} open fixtures as cards; each row links its own sources.</span></a>
<a href="twc.html"><b>Thunderpick day 3 desk →</b>
<span class="muted">Day-1 upset review (9z 2-0 Aurora), day-2 results, safe + climb picks for both deciders.</span></a>
<a href="unresolved.html"><b>Unresolved picks &amp; limitations →</b>
<span class="muted">{len(unresolved)} row(s) without a priced source, the ambiguity decisions, and what blocks each one.</span></a>
<a href="flagged.html"><b>Flagged for review →</b>
<span class="muted">Ambiguous official team names, alias decisions, stale prices and single-book rows.</span></a>
<a href="method.html"><b>Method &amp; sources →</b>
<span class="muted">Resolution ladder, contrarian rules, refresh cadence, formulas, limits.</span></a>
<a href="verify.html"><b>Verification →</b>
<span class="muted">Independent re-derivation of every published number from the retained evidence.</span></a>
</div>
<h2>Today's contrarian (climb) calls</h2>
<p class="muted">Declared rule: take the underdog only at ≥30% win probability, ≥2× leverage against the
crowd, and at most three activations per UTC day ranked by leverage × points. Everything else keeps the
favourite.</p>
{"".join(match_card(r) for r in rows if r.get("climb_active")) or '<p class="muted">No climb activation in this build.</p>'}
<h2>Every open match</h2>
<div class="card"><table class="cards"><thead><tr><th>Match</th><th>Pick</th><th>Probability</th>
<th>Climb</th><th>Sources</th></tr></thead><tbody>{idx_rows}</tbody></table></div>
<p class="muted">Coverage note: {summary['market']} rows are priced by at least one external bookmaker,
{summary['exchange']} by the Kalshi exchange with a two-sided book, {summary['model']} by a line this
session originates from Valve's official ratings, and {summary['unresolved']} remain unresolved with a
published limitation. Prices are re-read every four hours by
<code>.github/workflows/desk-6484426f.yml</code>; nothing on this site is a guarantee.</p>
"""
    (DESK / "index.html").write_text(page("index.html", "Executive summary", home, generated))

    # -------------------------------------------------------------------------- every match
    cards = "".join(f'<div class="match" id="{esc(r["fixture_id"])}">'
                    f'{match_card(r)}</div>' if False else match_card(r).replace(
                        '<div class="match">', f'<div class="match" id="{esc(r["fixture_id"])}">', 1)
                    for r in rows)
    picks = f"""
<h1>Every open HotSpawn CS2 fixture — pick and win probability</h1>
<p class="muted">{summary['with_pick']} of {summary['open']} open fixtures carry a pick. Basis labels:
<span class="chip m">M · market</span> bookmaker price,
<span class="chip e">E · exchange</span> Kalshi two-sided book,
<span class="chip o">O · originated</span> this session's line from official Valve ratings,
<span class="chip u">U · unresolved</span> no eligible evidence.
Crowd percentages are ownership, never probabilities.</p>
<div class="matches">{cards}</div>
"""
    (DESK / "picks.html").write_text(page("picks.html", "All picks", picks, generated))

    # ------------------------------------------------------------------------------ TWC
    def decider_card(row) -> str:
        card = match_card(row)
        return card

    day1 = (twc.get("research") or {}).get("day1_results_2026_10_14") or []
    day2 = (twc.get("research") or {}).get("day2_results_2026_10_15") or []
    fixtures_r = (twc.get("research") or {}).get("day3_fixtures_2026_10_16") or []
    roster = (twc.get("research") or {}).get("roster_audit") or {}
    sched = (twc.get("research") or {}).get("playoffs_schedule") or []
    twc_html = f"""
<h1>Thunderpick World Championship 2026 — day 1 &amp; 2 review, day 3 calls</h1>
<p class="muted">Event: <a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026"
rel="noopener">HLTV event 8932</a> — LAN, Malta, 14–18 October 2026, 8 teams, $1,000,000.
Both day-3 matches are the group deciders; the winners reach Saturday's semifinals.</p>
<h2>Day 1 (14 Oct) — the upset</h2>
<ul>{"".join(f'<li><b>{esc(r["match"])}</b> — <a href="{esc(r["url"])}" rel="noopener">HLTV match page</a></li>' for r in day1)}</ul>
<p class="muted">9z beat Aurora 2–0 in the opening group match, which the crowd had priced at roughly
9 in 10 in Aurora's favour (HotSpawn ownership, read 07:29Z). That single result is why day 3 exists in
this group.</p>
<h2>Day 2 (15 Oct)</h2>
<ul>{"".join(f'<li><b>{esc(r["match"])}</b> — <a href="{esc(r["url"])}" rel="noopener">HLTV match page</a></li>' for r in day2)}</ul>
<h2>Day 3 (16 Oct) — safe pick and climb pick</h2>
{"".join(decider_card(deciders[fid]) for fid in ("1080205", "1081775") if fid in deciders)}
<h3>Why these climb calls are contrarian but not stupid</h3>
<ul>
<li><b>9z at the Aurora price.</b> External bookmakers price 9z near 33%, HotSpawn's crowd has 9z at about
10% of picks: 3.3× leverage, and 9z has already beaten Aurora 2–0 on this stage two days ago
(<a href="https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026" rel="noopener">HLTV 2399384</a>).
Above the 30% floor, so it is a swing and not a lottery ticket.</li>
<li><b>BetBoom at the Legacy price.</b> Books put BetBoom near 39% while the crowd is only ~14% on them:
2.8× leverage. BetBoom won the day-2 elimination match 2–1 over PARIVISION, so the roster is live; the
same rules keep the safe pick on Legacy.</li>
<li><b>What the model declines.</b> Every underdog below 30% keeps the favourite pick — that is the
"not stupid" half of the rule, and the per-row gate results are printed on
<a href="picks.html">the picks page</a>.</li>
</ul>
<h3>Who had a real upset shot on day 1</h3>
<ul>{"".join(f'<li>{esc(point)}</li>' for point in ((twc.get("research") or {}).get("day1_upset_review") or {}).get("why_9z_had_a_real_shot") or [])}</ul>
<h3>Day-3 context</h3>
<div class="card"><table class="cards"><thead><tr><th>Pair</th><th>Meetings in 30 days</th><th>Latest</th>
<th>Source</th></tr></thead><tbody>
{"".join(f'<tr><td data-label="Pair">{esc(p["pair"])}</td><td data-label="Meetings">{esc(p["meetings_in_30_days"])}</td><td data-label="Latest">{esc(p["latest"])}</td><td data-label="Source"><a href="{esc(p["url"])}" rel="noopener">HLTV odds &amp; prediction</a></td></tr>' for p in (twc.get("research") or {}).get("h2h_day3_pairs") or [])}
</tbody></table></div>
<div class="card"><table class="cards"><thead><tr><th>Team</th><th>HLTV rank</th><th>Form / note</th>
<th>Source</th></tr></thead><tbody>
{"".join(f'<tr><td data-label="Team">{esc(team)}</td><td data-label="Rank">#{esc(row["hltv_rank"])}</td><td data-label="Form">{esc(row.get("form") or row.get("note"))}</td><td data-label="Source"><a href="{esc(row["url"])}" rel="noopener">HLTV odds &amp; prediction</a></td></tr>' for team, row in ((twc.get("research") or {}).get("rankings_day3") or {}).items())}
</tbody></table></div>
<h3>Roster premise check</h3>
<p>{esc(roster.get("finding"))}</p>
<p class="muted">Status: <b>{esc(roster.get("status"))}</b>. Last documented moves:
{" · ".join(f'{esc(m["date"])} {esc(m["move"])} (<a href="{esc(m["url"])}" rel="noopener">source</a>)' for m in roster.get("last_documented_moves") or [])}. Sources:
{" · ".join(f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["label"])}</a>' for s in (roster.get("sources") or []))}</p>
<h3>Rest of the bracket</h3>
<ul>{"".join(f'<li>{esc(s["match"])} — {esc(s["stage"])}, {esc(str(s["kickoff_utc"])[11:16])}Z UTC · <a href="{esc(s["hltv_url"])}" rel="noopener">HLTV</a> <span class="muted">{esc(s.get("note"))}</span></li>' for s in sched)}</ul>
<h3>Kick-off time caution</h3>
<p class="muted">The HotSpawn lobby renders US-Eastern times without a zone label; each row above shows the
UTC kick-off reconciled with HLTV's display (a 4-hour offset) and with the canonical capture. A mis-read
would move the lock time, so it is published on <a href="flagged.html">Flagged</a>.</p>
"""
    (DESK / "twc.html").write_text(page("twc.html", "TWC day 3", twc_html, generated))

    # ------------------------------------------------------------------------ unresolved
    un_rows = "".join(
        f'<tr><td data-label="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}<br>'
        f'<span class="muted">{esc(str(r.get("start_utc"))[11:16])}Z · {esc(r.get("competition"))}</span></td>'
        f'<td data-label="Why no pick">{esc(r.get("limitation") or "no eligible evidence")}</td>'
        f'<td data-label="Attempted">{source_links(r)}</td></tr>' for r in unresolved)
    def vrs_notes(r):
        vrs = r.get("vrs") or {}
        return ((vrs.get("team_a") or {}).get("notes") or []) + \
               ((vrs.get("team_b") or {}).get("notes") or [])

    amb_rows = "".join(
        '<tr><td data-label="Match">%s vs %s</td><td data-label="Official entries">%s</td>'
        '<td data-label="Rule applied">%s</td></tr>'
        % (esc(r["team_a"]), esc(r["team_b"]),
           esc(", ".join(f'#{c.get("standing")} {c.get("points")} pts ({len(c.get("roster") or [])} players, {c.get("file")})'
                         for c in note.get("candidates") or [])),
           esc(note.get("rule")))
        for r in rows for note in vrs_notes(r) if note.get("type") == "ambiguous_official_name")

    def alias_cell(note):
        links = " ".join('<a href="%s" rel="noopener">%s</a>'
                         % (esc(s.get("url")), esc(s.get("label"))) for s in (note.get("sources") or []))
        return esc(note.get("evidence")) + ("<br>" + links if links else "")

    alias_rows_html = "".join(
        '<tr><td data-label="Match">%s vs %s</td><td data-label="Identity">%s → %s</td>'
        '<td data-label="Evidence">%s</td></tr>'
        % (esc(r["team_a"]), esc(r["team_b"]), esc(note.get("hotspawn_label")),
           esc(note.get("official_name")), alias_cell(note))
        for r in rows for note in vrs_notes(r) if note.get("type") == "identity_alias")

    unresolved_html = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="muted">This is the separate ledger the brief asks for: every open fixture that could not be
priced from an external source, what was attempted in order, and which single blocker stopped a pick.
A row only reaches this page with <b>no</b> invented probability — the cell stays blank.</p>
<div class="kpis">
<div class="kpi"><span class="muted">Open fixtures</span><b>{summary['open']}</b></div>
<div class="kpi"><span class="muted">Blank rows</span><b>{len(unresolved)}</b></div>
<div class="kpi"><span class="muted">Originated rows (review)</span><b>{summary['model']}</b></div>
<div class="kpi"><span class="muted">Ambiguity decisions</span><b>{len(ambiguous)}</b></div>
</div>
<h2>Rows with no pick</h2>
{"<div class='card'><table class='cards'><thead><tr><th>Match</th><th>Why</th><th>Attempted</th></tr></thead><tbody>" + un_rows + "</tbody></table></div>" if unresolved else "<p>No open fixture is unpicked in this build. " + str(summary['open']) + " of " + str(summary['open']) + " rows carry a pick; the ladder used is market → exchange → originated official-ratings line.</p>"}
<h2>Picks this session originated (labelled, not market prices)</h2>
<p class="muted">{summary['model']} fixtures have no external bookmaker price in this capture. They are
priced from Valve's official regional standings with the slope fitted here against the market lines in the
same capture (k = {board['calibration']['k']:.3f}, {board['calibration']['n_pairs']} pairs, MAE
{pct(board['calibration']['mae_prob'])}). Treat them as this site's estimate, not as a bookmaker's price.</p>
<h2>Ambiguous official team names</h2>
{"<div class='card'><table class='cards'><thead><tr><th>Match</th><th>Official entries</th><th>Rule applied</th></tr></thead><tbody>" + amb_rows + "</tbody></table></div>" if amb_rows else "<p>None in this build.</p>"}
<h2>Identity decisions applied</h2>
{"<div class='card'><table class='cards'><thead><tr><th>Match</th><th>Identity</th><th>Evidence</th></tr></thead><tbody>" + alias_rows_html + "</tbody></table></div>" if alias_rows_html else "<p>None in this build.</p>"}
<h2>Known limits of the method</h2>
<ul>
<li>Originated lines carry model error: the fitted curve misses the market by {pct(board['calibration']['mae_prob'])} on average across the pairs it was fitted on, and it is unvalidated out of sample.</li>
<li>The exchange tier requires a two-sided Kalshi book with a spread of 10¢ or less <em>and</em> a kick-off
stated in Kalshi's own rules text; thin books are rejected and listed on <a href="flagged.html">Flagged</a>.</li>
<li>Where two official entries share a team name, the rule "highest-rated entry listing at least four
players" is applied and both candidates are published above so the reader can disagree.</li>
<li>Prices age: rows whose only price is older than four hours keep the probability but are flagged
<code>quote_older_than_4h</code> rather than silently refreshed.</li>
<li>No source is ever HotSpawn for a probability, and crowd ownership is excluded from every formula.</li>
</ul>
"""
    (DESK / "unresolved.html").write_text(page("unresolved.html", "Unresolved picks", unresolved_html,
                                               generated))

    # --------------------------------------------------------------------------- flagged
    flag_rows = []
    for r in stale:
        flag_rows.append({"item": f"{r['team_a']} vs {r['team_b']}",
                          "detail": f"only price older than 4h (age {r.get('quote_age_hours')}h)",
                          "url": (r.get("quotes") or [{}])[0].get("public_url")})
    for r in single:
        flag_rows.append({"item": f"{r['team_a']} vs {r['team_b']}",
                          "detail": "priced by a single bookmaker (no cross-book check)",
                          "url": (r.get("quotes") or [{}])[0].get("public_url")})
    for r, note in [(r, n) for r in rows for n in
                    ((r.get("vrs") or {}).get("team_a", {}).get("notes", [])
                     + (r.get("vrs") or {}).get("team_b", {}).get("notes", []))]:
        if note.get("type") == "ambiguous_official_name":
            flag_rows.append({"item": f"{r['team_a']} vs {r['team_b']}",
                              "detail": f"official name '@{note.get('official_name')}' matches more than "
                                        f"one Valve entry; rule applied: {note.get('rule')}",
                              "url": "https://github.com/ValveSoftware/counter-strike_regional_standings"})
        if note.get("type") == "identity_alias":
            flag_rows.append({"item": f"{r['team_a']} vs {r['team_b']}",
                              "detail": f"alias applied: {note.get('hotspawn_label')} → {note.get('official_name')} "
                                        f"(independent audit evidence)",
                              "url": (note.get("sources") or [{}])[0].get("url")})
    flag_rows.append({"item": "Aurora roster premise",
                      "detail": "the brief's 'recent roster change' premise is not confirmed by any source "
                                "read in this session; the last documented moves are 2026-07-03/07-08 "
                                "(about 100 days before the day-3 decider)",
                      "url": "https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan"})
    flag_rows.append({"item": "Lobby time zone",
                      "detail": "the lobby renders US-Eastern tips without a zone label; UTC kick-offs here "
                                "are reconciled with HLTV's display and the canonical capture",
                      "url": LOBBY})
    flagged_html = f"""
<h1>Flagged for review</h1>
<p class="muted">Irregularities do not block publication: each one is listed with the link needed to check
it. Nothing here changes a published probability; entries are caveats on how the number was obtained.</p>
<div class="card"><table class="cards"><thead><tr><th>Item</th><th>Why flagged</th><th>Source</th></tr>
</thead><tbody>{"".join(f'<tr><td data-label="Item">{esc(f["item"])}</td><td data-label="Why">{esc(f["detail"])}</td><td data-label="Source"><a href="{esc(f["url"])}" rel="noopener">{esc(f["url"])}</a></td></tr>' for f in flag_rows)}</tbody></table></div>
<h2>Counts in this build</h2>
<ul><li>rows priced by one book only: {len(single)}</li>
<li>rows whose price is older than four hours: {len(stale)}</li>
<li>ambiguous official-name decisions: {len(ambiguous)}</li>
<li>verified alias decisions applied: {len(alias_rows)}</li>
<li>rows with no pick: {len(unresolved)}</li></ul>
"""
    (DESK / "flagged.html").write_text(page("flagged.html", "Flagged for review", flagged_html, generated))

    # ---------------------------------------------------------------------------- method
    method_html = f"""
<h1>Method, sources and limits</h1>
<h2>Resolution ladder (in order)</h2>
<ol>
<li><b>Market.</b> Full-match two-way moneyline prices from Pinnacle, Bovada, Melbet and the
Thunderpick coefficients published by bo3.gg (the esportsbook tier for matches no sharp book
covers), read from their public endpoints. No-vig probability = (1/dec_a) / (1/dec_a + 1/dec_b). Multi-book rows use the weighted
mean with Pinnacle weighted 2× (declared modelling choice). A price prices a row only if the source's own
names match the fixture and its stated kick-off is within five minutes of HotSpawn's.</li>
<li><b>Exchange.</b> Kalshi series <code>KXCS2GAME</code>: the yes-bid/yes-ask midpoints of both sides,
normalised, accepted only when both sides are two-sided, the spread is ≤ 10¢, and the market's own rules
text states the kick-off (converted from the zone it prints).</li>
<li><b>Originated (official ratings).</b> Where no bookmaker prices a match: this session's line from
Valve's official regional standings, P(A) = σ(k · C · (points_a − points_b)) with Valve's own formula
(C = g·ln10/400 at RD 75) and the slope k fitted by least squares against the market lines in the same
capture. This build: k = {board['calibration']['k']:.3f} from {board['calibration']['n_pairs']} pairs, mean
absolute error {pct(board['calibration']['mae_prob'])} (Valve's own k = 1 would miss by
{pct(board['calibration']['mae_prob_valve'])}).</li>
<li><b>Unresolved.</b> Nothing is guessed: the probabilities stay blank, the pick stays blank, and the row
is published with its blocker on <a href="unresolved.html">Unresolved picks</a>.</li>
</ol>
<h2>Contrarian (climb) rule</h2>
<ul>
<li>Safe pick = higher probability side. Climb pick = safe pick unless the underdog clears
<b>{pct(board['policy']['climb_min_prob'], 0)}</b> win probability <em>and</em>
<b>{board['policy']['climb_min_leverage']:.1f}×</b> leverage (probability ÷ crowd ownership of that side).</li>
<li>At most <b>{board['policy']['climb_max_per_day']}</b> activations per UTC day, ranked by leverage × offered
points; other qualifiers keep the favourite and still print their gate results.</li>
<li>Crowd ownership comes from the lobby's own picked percentages. It is never a probability, never part of a
price, and is printed as a percentage of picks only.</li>
<li>Exact ties (a market that prices both sides the same): the safe pick follows the official rating model
when one exists, the climb pick takes the less-owned side at zero expected-point cost.</li>
</ul>
<h2>Refresh cadence</h2>
<p>Collection, resolution, page rendering, verification and tests run every four hours in
<code>.github/workflows/desk-6484426f.yml</code> (also on demand), inside the 4–8 hour policy. Prices
older than {board['policy']['quote_max_age_hours']:.0f} hours are flagged rather than silently reused.</p>
<h2>Sources used in this build</h2>
<ul>
<li><a href="{LOBBY}" rel="noopener">HotSpawn pick'em lobby</a> — fixtures, kick-off, points, tier, crowd
ownership (read {esc(board['research_read_utc']['lobby'])}). Never a probability.</li>
<li><a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026" rel="noopener">HLTV event
8932</a> — TWC results and schedule (read {esc(board['research_read_utc']['hltv_results'])}).</li>
<li><a href="https://www.hltv.org/betting/analytics/2399412/aurora-vs-9z-thunderpick-world-championship-2026" rel="noopener">HLTV
odds &amp; prediction</a> — rankings, form and head-to-head context (read
{esc(board['research_read_utc']['hltv_analytics'])}).</li>
<li><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">Valve official
regional standings</a> — {board['valve']['entries']} team rows from
{esc(", ".join(board['valve']['files']))} (read {esc(board['research_read_utc']['valve'])}, commit
<code>eec4853d</code>).</li>
<li>External prices: Pinnacle (guest odds API), Bovada, Melbet, the Kalshi exchange and the
Thunderpick coefficients bo3.gg publishes per fixture — the esportsbook tier that gives several
low-tier matches a real two-sided price. Each row on <a href="picks.html">All picks</a> links the
exact endpoint and its read time.</li>
</ul>
<h2>Limits</h2>
<ul>
<li>{board['calibration']['n_pairs']} calibration pairs is a small sample; the originated lines are the
weakest tier and are labelled as such on every row.</li>
<li>HLTV is read manually by this session (it returns 403 to automated collection); every HLTV fact used
here carries its URL and read time in <code>data/6484426f/research.json</code>.</li>
<li>Kick-off times published by the lobby are unlabelled US-Eastern; the reconciliation is published on
<a href="flagged.html">Flagged</a>.</li>
<li>Probabilities are model estimates from prices, not guarantees, and no profit is implied.</li>
</ul>
"""
    (DESK / "method.html").write_text(page("method.html", "Method", method_html, generated))

    # -------------------------------------------------------------------------- verify
    if verification:
        checks = "".join(
            f'<tr><td data-label="Check">{esc(c["id"])} — {esc(c["name"])}</td>'
            f'<td data-label="Result"><span class="chip '
            f'{"e" if c["status"] == "pass" else "u"}">{esc(c["status"])}</span></td>'
            f'<td data-label="Detail">{esc(c["detail"])}</td></tr>' for c in verification["checks"])
        verify_html = f"""
<h1>Verification</h1>
<p class="muted">Every published probability is re-derived from the retained raw prices by
<code>scripts/6484426f/verify.py</code>, independently of the code that published it. Run
{esc(verification['generated_utc'])}: <b>{verification['summary']['passed']}</b> passed,
{verification['summary']['failed']} failed.</p>
<div class="card"><table class="cards"><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr>
</thead><tbody>{checks}</tbody></table></div>
<h2>Rows checked</h2>
<p class="muted">Quotes re-derived: {verification['quotes_re_derived']} ·
Rows re-checked: {verification['rows_checked']} ·
Blanks confirmed blank: {verification['blank_rows']} ·
Crowd-equals-probability collisions found: {verification['crowd_probability_collisions']}</p>
"""
    else:
        verify_html = ("<h1>Verification</h1><p>No verification run is published with this build yet; "
                       "the workflow runs it before publishing.</p>")
    (DESK / "verify.html").write_text(page("verify.html", "Verification", verify_html, generated))

    return {"pages": sorted(p.name for p in DESK.glob("*.html")), "generated_utc": generated}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
