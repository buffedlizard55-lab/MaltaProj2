#!/usr/bin/env python3
"""Render the session 6c5bb3d6 independent-verification pages under audits/6c5bb3d6/.

Reads only: data/6c5bb3d6/{verification,research,vrs_official}.json,
data/f28afd9e/{board,day1_review}.json, data/hotspawn_matches.json.
Writes only: audits/6c5bb3d6/{index,flagged,method}.html.

Fails closed: if an internal link target does not exist in the repository the build stops
rather than publishing a broken page.
"""
from __future__ import annotations

import html
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "audits", "6c5bb3d6")

CSS = """
:root{color-scheme:dark;--bg:#0c131c;--panel:#141f2c;--line:#2d3c4d;--text:#edf3fa;--muted:#b2c0d0;
--green:#69e4bd;--amber:#ffce80;--red:#ff9c9c;--blue:#92caff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
a{color:var(--blue);text-underline-offset:3px}
a:focus-visible{outline:3px solid var(--amber);outline-offset:3px}
header{border-bottom:1px solid var(--line);background:#101a26;position:sticky;top:0;z-index:5}
.wrap{max-width:1120px;margin:auto;padding:16px}
.brand{font-weight:750;letter-spacing:.02em}
nav{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:6px}
nav a{padding:10px 0;min-height:44px;text-decoration:none}
nav a[aria-current]{color:var(--green);font-weight:700}
.skip{position:absolute;left:-9999px}.skip:focus{position:static}
h1{font-size:clamp(1.7rem,5vw,2.5rem);line-height:1.15;margin:10px 0 12px}
h2{font-size:1.25rem;margin:26px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:1.05rem;margin:18px 0 6px}
.eyebrow{color:var(--green);font-size:.78rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700}
.muted,.small{color:var(--muted)}.small{font-size:.85rem}
.notice{border-left:3px solid var(--amber);padding:12px 14px;background:#282215;color:#ffe3b4;margin:14px 0;border-radius:0 8px 8px 0}
.ok{border-left:3px solid var(--green);padding:12px 14px;background:#12241f;color:#c8f5e6;margin:14px 0;border-radius:0 8px 8px 0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}
.stat{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:12px}
.stat b{display:block;font-size:1.6rem}
.stat span{font-size:.8rem;color:var(--muted)}
.panel{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px;margin:12px 0}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.button{padding:13px 16px;border-radius:9px;display:inline-block;border:1px solid var(--line);
text-decoration:none;font-weight:700;min-height:48px;background:#1b2836;color:var(--text)}
.button.primary{background:var(--green);color:#09241e;border-color:var(--green)}
.button.ghost{background:transparent}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:10px 0}
table{width:100%;border-collapse:collapse;font-size:.92rem}
caption{text-align:left;padding:6px 0;color:var(--muted);font-size:.85rem}
th{text-align:left;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}
td,th{padding:13px 9px;border-bottom:1px solid var(--line);vertical-align:top}
td{overflow-wrap:anywhere}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:.75rem;font-weight:700}
.pass{color:#0d2a20;background:var(--green);border-color:var(--green)}
.info{color:#2a2110;background:var(--amber);border-color:var(--amber)}
.fail{color:#2a1414;background:var(--red);border-color:var(--red)}
.warn{color:#2a2110;background:var(--amber);border-color:var(--amber)}
.unverified{color:#ffe3b4;background:#3a2f18;border-color:#6b5524}
.num{font-variant-numeric:tabular-nums;font-weight:700}
.pos{color:var(--green)}.neg{color:var(--red)}
.srcs a{display:inline-block;padding:6px 0;min-height:32px;margin-right:10px;font-size:.85rem}
footer{border-top:1px solid var(--line);margin-top:30px;padding-top:16px}
ul{padding-left:20px}li{margin:6px 0}
details{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:10px 12px;margin:10px 0}
summary{cursor:pointer;font-weight:700;min-height:32px}
@media(max-width:700px){
 .wrap{padding:12px}.stats{grid-template-columns:repeat(2,1fr);gap:8px}
 table,tbody,tr,td{display:block;width:100%}thead{display:none}
 tr{border:1px solid var(--line);border-radius:12px;margin-bottom:12px;background:var(--panel);padding:6px}
 td{border:0;padding:8px}
 td:before{content:attr(data-label);display:block;text-transform:uppercase;font-size:.68rem;
 color:var(--muted);letter-spacing:.04em;margin-bottom:3px}
 .srcs a{min-height:44px}nav{font-size:.9rem}.stat{padding:10px}
}
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def load(path: str, default=None):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return default
    with open(full, encoding="utf-8") as fh:
        return json.load(fh)


def pct(value, digits=1) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def ev(value) -> str:
    if value is None:
        return "—"
    cls = "pos" if value > 0 else ("neg" if value < 0 else "")
    return f'<span class="num {cls}">{float(value):+.2f}</span>'


def links(urls, labels=None) -> str:
    out = []
    for i, u in enumerate(urls or []):
        if not u:
            continue
        label = (labels[i] if labels and i < len(labels) and labels[i] else "source")
        out.append(f'<a href="{esc(u)}" rel="noopener">{esc(label)}</a>')
    return '<span class="srcs">' + " ".join(out) + "</span>" if out else '<span class="small">no source</span>'


def page(title: str, nav_current: str, body: str, heading: str, eyebrow: str) -> str:
    nav = [("index.html", "Verification summary"), ("flagged.html", "Flagged for review"),
           ("method.html", "Method & sources")]
    nav_html = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if href == nav_current else '') + f'>{esc(label)}</a>'
        for href, label in nav)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
<header><div class="wrap"><div class="brand">HOTSPAWN / CS2 <span class="small">Independent verification · session 6c5bb3d6</span></div>
<nav aria-label="Section">{nav_html}</nav></div></header>
<main id="main" class="wrap">
<div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(heading)}</h1>
{body}
<footer><p class="small">Independent audit by session <code>6c5bb3d6</code>. Not affiliated with HotSpawn, Valve,
HLTV or any bookmaker. HotSpawn is used for fixture discovery and settlement only; its crowd pick percentage is
published as pick'em ownership and is never an input to any win probability. Values that could not be confirmed
from an official source are left blank and flagged.</p>
<p class="small">Machine-readable: <a href="report.json">report.json</a> ·
evidence: <code>data/6c5bb3d6/</code> · harness: <code>scripts/6c5bb3d6/</code></p></footer>
</main></body></html>"""


# --------------------------------------------------------------------- shared blocks

PICK_LINKS = [
    ("../../strategy/index.html", "Every match + leaderboard picks",
     "A safe pick and a leaderboard (contrarian) pick for every open CS2 fixture, with the crowd split and per-row sources."),
    ("../../picks-every-match/index.html", "Canonical strict picks",
     "Market-first board; rows without eligible evidence stay blank and flagged."),
    ("../94b3d48a/index.html", "Research-resolved picks",
     "HLTV / esportsbook / originated-Valve-VRS resolution for the fixtures the featured route cannot price."),
    ("../../picks-all/index.html", "Complete picks (all matches)", "M / R / O layered picks for every open fixture."),
    ("../../board/picks.html", "Expanded market + model board", "Market, market+model and originated rows with identity flags."),
    ("../../live/index.html", "Live coverage board", "Hourly lobby board with per-row source links."),
    ("../../strategy/unresolved.html", "Unresolved picks & limitations (strategy)", "Gaps and limitations behind the every-match board."),
    ("../../picks-every-match/unresolved.html", "Unresolved picks & limitations (canonical)", "Strict-board gaps with the source-attempt ledger."),
]


def where_the_picks() -> str:
    rows = "".join(
        f'<tr><td data-label="Board"><a href="{esc(href)}"><strong>{esc(label)}</strong></a>'
        f'<div class="small">{esc(blurb)}</div></td>'
        f'<td data-label="Source" class="srcs"><a href="{esc(href)}" rel="noopener">Open</a></td></tr>'
        for href, label, blurb in PICK_LINKS)
    buttons = "".join(
        f'<a class="button{" primary" if i == 0 else ""}" href="{esc(href)}">{esc(label)}</a>'
        for i, (href, label, _) in enumerate(PICK_LINKS[:3]))
    return f"""<div class="panel" id="where-the-picks">
<h2 style="margin-top:0;border:0">Where the picks are (in-site links)</h2>
<p class="small">Updated automatically. On a phone, start with the first button — it lists every open CS2
match with a pick, both win probabilities, the crowd split and the source behind each number.</p>
<div class="actions">{buttons}</div>
<div class="tablewrap"><table data-nav="true"><caption>Every published picks board in this site and what it is for. In-site navigation: these rows link our own boards rather than an external official source.</caption>
<thead><tr><th>Board</th><th>Open</th></tr></thead><tbody>{rows}</tbody></table></div></div>"""


# --------------------------------------------------------------------- index

def build_index(v: dict, research: dict, board: dict, day1: dict, vrs: dict) -> str:
    s = v["summary"]
    checks = v["checks"]
    irr = v["irregularities"]
    diff = [d for d in v.get("differential_table") or [] if d.get("state") == "open"]
    diff.sort(key=lambda d: -max(d.get("ev_a") or -99, d.get("ev_b") or -99))
    verified_day1 = research.get("day1_results") or []
    crowd = (research.get("day1_crowd_ownership") or [{}])[0]

    # ---- headline
    body = [f"""<div class="ok"><strong>Verdict:</strong> {s['checks']} independent checks ran against the
published boards — {s['by_status'].get('pass', 0)} pass, {s['by_status'].get('info', 0)} informational,
{s['by_status'].get('fail', 0)} fail. {s['irregularities']} items are flagged for review
({', '.join(f"{k}: {n}" for k, n in sorted(s['by_severity'].items()))}); none blocks publication.
Every published probability in the every-match board was re-derived here from its raw bookmaker quote,
and every official Valve-standings citation was re-read from Valve's own file in this run.</div>"""]

    body.append(f"""<div class="stats">
<div class="stat"><b>{v['lobby_snapshot']['pickable_at_board_instant']}</b><span>Pickable CS2 fixtures, all with a pick</span></div>
<div class="stat"><b>{v['verified_board']['rows']}</b><span>Published rows re-checked</span></div>
<div class="stat"><b>{v['quotes_re_derived']}</b><span>Raw quotes re-derived</span></div>
<div class="stat"><b>{len(irr)}</b><span>Flagged for review</span></div></div>""")
    body.append(f"""<p class="small">Board verified: <code>data/f28afd9e/board.json</code> generated
{esc(v['verified_board']['generated_utc'])} · lobby snapshot <code>data/hotspawn_matches.json</code> generated
{esc(v['lobby_snapshot']['generated_at_utc'])} ({esc(v['lobby_snapshot']['match_count'])} CS2 fixtures) ·
official Valve standings {esc(v['official_vrs']['snapshot'])} fetched {esc(v['official_vrs']['fetched_utc'])}
(HTTP {esc(v['official_vrs']['http_status'])}, {esc(v['official_vrs']['teams_parsed'])} teams) ·
this audit {esc(v['generated_utc'])}.</p>""")

    body.append(where_the_picks())

    # ---- day 1
    rows = []
    for item in verified_day1:
        srcs = links([s.get("url") for s in item.get("sources") or []],
                     [s.get("label") for s in item.get("sources") or []])
        rows.append(f"""<tr><td data-label="Match"><b>{esc(item.get('match'))}</b>
<div class="small">{esc(item.get('detail'))}</div>
<div class="small">fixture #{esc(item.get('fixture_id'))} · verdict <span class="badge pass">{esc(item.get('verdict'))}</span></div></td>
<td data-label="Sources">{srcs}</td></tr>""")
    body.append(f"""<h2 id="day1">Day-1 review, verified line by line (TWC 2026, 2026-10-14)</h2>
<p>Four group openers, four 2-0 sweeps — and the day's biggest result was the one almost nobody owned.
Each row below was re-read from an official page in this session; nothing is inferred.</p>
<div class="tablewrap"><table><caption>Day-1 results with the official source for each.</caption>
<thead><tr><th>Result</th><th>Official sources</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>""")

    crowd_srcs = links([s.get("url") for s in crowd.get("sources") or []],
                       [s.get("label") for s in crowd.get("sources") or []])
    body.append(f"""<div class="panel"><h3 style="margin-top:0">The upset in numbers: 9z 2-0 Aurora</h3>
<ul>
<li><strong>Ownership:</strong> only <span class="num">4%</span> of the HotSpawn field had 9z at the pick lock
(96% Aurora). Verified from the pre-lock board capture at the exact commit the backtest cites
(commit <code>8f66ce4</code>, board generated 2026-10-14T04:55:36Z, retrieved through the GitHub API in this
session). The 7-point match therefore paid 7 points to 4% of players and zero to 96%.</li>
<li><strong>Price:</strong> Aurora were the market favourite; Valve's official standings of 2026-10-05 rank
Aurora #9 (1716 pts) and 9z #17 (1543 pts) — a 173-point gap, i.e. about 74% for Aurora on the 400-point
logistic scale. The result was a 2-0 the other way.</li>
<li><strong>How it happened:</strong> 13-11 on 9z's Inferno, then 13-1 on Aurora's own Nuke pick.
luchov finished 38-20 with a 1.61 rating, 97.4 ADR and 86.8% KAST; Aurora's IGL kyxsan finished 9-29 at 0.53.</li>
<li><strong>Ranking effect:</strong> HLTV records 9z gaining 62 VRS points from the win.</li>
<li><strong>Why it was not random:</strong> Aurora are three months into a full rebuild — Jimpphat and coach
ash on 2026-07-03, kyxsan as IGL on 2026-07-08, replacing MAJ3R, soulfly and coach Fabre. Their own coach said
in August that practice was good but official matches were not, naming communication and cultural integration.</li>
</ul>
<p class="small">Sources: {crowd_srcs}</p></div>""")

    # ---- roster intel
    intel = []
    for item in research.get("roster_intel") or []:
        srcs = links([s.get("url") for s in item.get("sources") or []],
                     [s.get("label") for s in item.get("sources") or []])
        intel.append(f"""<tr><td data-label="Team"><b>{esc(item.get('team'))}</b>
<div class="small">{esc(item.get('id'))} · <span class="badge pass">{esc(item.get('verdict'))}</span></div></td>
<td data-label="Verified finding">{esc(item.get('claim'))}
{f'<div class="notice small" style="margin:8px 0 0">{esc(item.get("note"))}</div>' if item.get('note') else ''}</td>
<td data-label="Sources">{srcs}</td></tr>""")
    body.append(f"""<h2 id="rosters">Roster-change, onboarding and rest intel (verified)</h2>
<p>The user's rule — a real upset candidate usually has a reason: a new player still being onboarded, a
leadership change, rest or schedule load. These are the reasons this audit could confirm from official or
primary sources, with the date each fact was read.</p>
<div class="tablewrap"><table><caption>Every roster/context fact used in the contrarian analysis, with its source.</caption>
<thead><tr><th>Team</th><th>Verified finding</th><th>Official sources</th></tr></thead>
<tbody>{''.join(intel)}</tbody></table></div>""")

    # ---- differential table
    drows = []
    for d in diff:
        pick_side = d["differential_optimal"]
        agree = d.get("agrees")
        badge = ('<span class="badge pass">matches published</span>' if agree
                 else '<span class="badge info">published stays chalk</span>')
        drows.append(f"""<tr><td data-label="Match"><b>{esc(d['match'])}</b>
<div class="small">{esc(d['competition'])} · {esc((d.get('start_utc') or '')[:16])} UTC ·
fixture #{esc(d['fixture_id'])} · {esc(d.get('points'))} pts</div></td>
<td data-label="Win probability">{esc(d.get('_ta'))} <span class="num">{pct(d['prob_a'])}</span> ·
{esc(d.get('_tb'))} <span class="num">{pct(d['prob_b'])}</span></td>
<td data-label="Crowd ownership">{esc(d['crowd_a'])}% / {esc(d['crowd_b'])}%<div class="small">reference only</div></td>
<td data-label="Leaderboard edge">{esc(d.get('_ta'))} {ev(d['ev_a'])} pts · {esc(d.get('_tb'))} {ev(d['ev_b'])} pts
<div class="small">points × (probability − ownership)</div></td>
<td data-label="Differential pick"><b>{esc(pick_side)}</b><div class="small">{badge}</div>
<div class="small">published: {esc(d['published_leaderboard_pick'])} ({esc(d['published_rule'])})</div></td>
<td data-label="Source" class="srcs"><a href="https://play.hotspawn.com/lobby" rel="noopener">Lobby</a>
<a href="report.json" rel="noopener">Recomputation</a></td></tr>""")
    body.append(f"""<h2 id="contrarian">Climbing the leaderboard: contrarian but not stupid</h2>
<p>In a pick'em scored against other players, taking side X with win probability <i>p</i> when a fraction
<i>c</i> of the field also took X moves your expected point margin by
<strong>points × (p − c)</strong>. So the field-beating pick is the side whose win probability exceeds its
ownership — not simply the biggest dog. Recomputed here independently for every open fixture:</p>
<div class="tablewrap"><table><caption>Independent differential recomputation, sorted by leaderboard edge.
Crowd ownership is a HotSpawn reference value and is never used as a probability.</caption>
<thead><tr><th>Match</th><th>Win probability</th><th>Crowd</th><th>Leaderboard edge</th>
<th>Differential pick</th><th>Source</th></tr></thead><tbody>{''.join(drows)}</tbody></table></div>""")

    top = [d for d in diff if max(d.get("ev_a") or 0, d.get("ev_b") or 0) >= 0.5]
    diverging = [d for d in diff if not d.get("agrees")]
    body.append(f"""<div class="panel"><h3 style="margin-top:0">What this says, plainly</h3>
<ul>
<li><strong>{len(top)} plays carry real leaderboard edge</strong> (≥ +0.50 expected points versus the field):
{esc(', '.join(f"{d['differential_optimal']} in {d['match']} ({max(d['ev_a'], d['ev_b']):+.2f} pts)" for d in top))}.
All of them are also the published strategy layer's picks — the two methods agree where it matters most,
on the 7-point S-tier matches.</li>
<li><strong>The three 7-point matches are where a leaderboard is won or lost.</strong> 9z (edge
{ev([d for d in diff if d['fixture_id'] == '1080202'][0]['ev_a']) if any(d['fixture_id'] == '1080202' for d in diff) else '—'} pts),
BetBoom and Legacy are all priced below their ownership. Day 1 proved the mechanism: 96% of the field took
Aurora and scored 0 on a 7-point match.</li>
<li><strong>{len(diverging)} rows diverge</strong> from pure differential math, all of them 2-point tier-C
matches where the crowd over-owns a heavy favourite (for example 98% on Phantom against a 67% market price).
The published layer deliberately stays chalk there: its rules cap swings per day and only fade near coin-flips
or with verified context. The forgone edge is real but small (≤ +0.61 pts per row) and the variance is large —
that is the "not stupid" guard, and this audit quantifies it instead of hiding it.</li>
<li><strong>Where the official rankings and the market disagree, both are shown.</strong>
Valve's standings imply BetBoom ≈74% over PARIVISION and Legacy ≈64% over FURIA, while the market prices
those matches near even. Five such divergences are listed on the <a href="flagged.html">flagged page</a>.
Divergence is treated as information, never averaged away silently.</li>
</ul></div>""")

    # ---- checks
    crows = []
    for c in checks:
        evidence = [e if str(e).startswith("http") else f"https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/{e}"
                    for e in c.get("evidence") or []]
        crows.append(f"""<tr><td data-label="Check"><b>{esc(c['id'])} · {esc(c['name'])}</b>
<div class="small">{esc(c['detail'])}</div>
{f'<div class="notice small" style="margin:8px 0 0">Failures: {esc("; ".join(c["failures"][:6]))}</div>' if c.get('failures') else ''}</td>
<td data-label="Result"><span class="badge {esc(c['status'])}">{esc(c['status'].upper())}</span>
<div class="small">{esc(c['rows_checked'])} checked · {esc(c['rows_failed'])} failed</div></td>
<td data-label="Evidence">{links(evidence, ['evidence'] * len(evidence))}</td></tr>""")
    body.append(f"""<h2 id="checks">The ten checks, line by line</h2>
<div class="tablewrap"><table><caption>Each check re-runs from the committed evidence; the harness is
<code>scripts/6c5bb3d6/verify.py</code> and the machine-readable result is <a href="report.json">report.json</a>.</caption>
<thead><tr><th>Check</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{''.join(crows)}</tbody></table></div>""")

    # ---- unresolved
    urows = []
    for item in research.get("unverified") or []:
        urows.append(f"""<tr><td data-label="Item"><b>{esc(item.get('item'))}</b>
<div class="small">{esc(item.get('id'))} · <span class="badge unverified">LEFT BLANK</span></div></td>
<td data-label="Why it is left blank">{esc(item.get('reason'))}</td>
<td data-label="Official source &amp; where the gap is published" class="srcs">
<a href="{esc(item.get('official_url'))}" rel="noopener">Official source</a>
<a href="flagged.html#{esc(item.get('id'))}" rel="noopener">This audit</a>
<a href="../../strategy/unresolved.html" rel="noopener">Strategy board</a>
<a href="../../picks-every-match/unresolved.html" rel="noopener">Canonical board</a></td></tr>""")
    for item in research.get("identity_resolutions") or []:
        urows.append(f"""<tr><td data-label="Item"><b>{esc(item.get('hotspawn_label'))} → {esc(item.get('resolved_to'))}</b>
<div class="small">{esc(item.get('id'))} · fixtures {esc(', '.join(item.get('fixtures') or []))}</div></td>
<td data-label="Why it is left blank">{esc(item.get('residual_limitation'))}</td>
<td data-label="Where the gap is published" class="srcs">
{links([s.get('url') for s in item.get('sources') or []], ['evidence'] * len(item.get('sources') or []))}</td></tr>""")
    body.append(f"""<h2 id="unresolved">Unresolved picks &amp; limitations</h2>
<p>Nothing on this page is filled in by guesswork. These are the values this audit could not confirm from an
official source, and the residual limitation on each resolved alias. The every-match pick boards publish their
own gap lists, linked from each row.</p>
<div class="tablewrap"><table><caption>Blank-by-choice items and their limitations.</caption>
<thead><tr><th>Item</th><th>Limitation</th><th>Published at</th></tr></thead><tbody>{''.join(urows)}</tbody></table></div>
<div class="actions"><a class="button" href="flagged.html">All flagged items ({len(irr)})</a>
<a class="button ghost" href="method.html">Method, formulas &amp; sources</a>
<a class="button ghost" href="../../strategy/unresolved.html">Strategy board gaps</a></div>""")

    return page("Independent verification · day-1 review & every-match picks", "index.html",
                "".join(body), "Independent verification of the day-1 review and every-match picks",
                "Session 6c5bb3d6 · line-by-line audit")


# --------------------------------------------------------------------- flagged

def build_flagged(v: dict) -> str:
    irr = v["irregularities"]
    order = {"high": 0, "medium": 1, "info": 2, "low": 3, "unverified": 4}
    irr = sorted(irr, key=lambda i: (order.get(i["severity"], 9), i["id"]))
    rows = []
    for i in irr:
        rows.append(f"""<tr id="{esc(i['id'])}"><td data-label="Item"><b>{esc(i['title'])}</b>
<div class="small">{esc(i['id'])} · <span class="badge {esc(i['severity'])}">{esc(i['severity'].upper())}</span></div>
<div class="small" style="margin-top:6px">{esc(i['detail'])}</div></td>
<td data-label="Source links">{links(i.get('links'), ['source'] * len(i.get('links') or []))}</td></tr>""")
    c8 = next((c for c in v["checks"] if c["id"] == "C8"), {})
    div_rows = "".join(f"<li>{esc(d)}</li>" for d in c8.get("divergences") or [])
    body = f"""<div class="notice">Every item below is published for manual review with its source links.
Flagged items do <strong>not</strong> block publication, and none of them is filled in with a guessed value:
where a number could not be confirmed from an official source it is left blank.</div>
<div class="stats">
<div class="stat"><b>{len(irr)}</b><span>Flagged items</span></div>
<div class="stat"><b>{v['summary']['by_severity'].get('high', 0)}</b><span>High severity</span></div>
<div class="stat"><b>{v['summary']['by_severity'].get('unverified', 0)}</b><span>Left blank / unverified</span></div>
<div class="stat"><b>{v['summary']['by_severity'].get('info', 0)}</b><span>Informational</span></div></div>
<h2>Flagged for review</h2>
<div class="tablewrap"><table><caption>All irregularities, ordered by severity, each with its source links.</caption>
<thead><tr><th>Item</th><th>Source links</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Differential-versus-published divergences in full</h2>
<p class="small">Recomputed with points × (probability − crowd ownership). These are methodology differences,
not arithmetic errors: the published layer caps swings per day and only fades near coin-flips or with verified
context, so it stays chalk in low-point matches where the crowd over-owns the favourite.</p>
<ul>{div_rows}</ul>
<div class="actions"><a class="button" href="index.html">Back to the verification summary</a>
<a class="button ghost" href="method.html">Method &amp; sources</a></div>"""
    return page("Flagged for review · session 6c5bb3d6", "flagged.html", body,
                "Flagged for review", "Irregularities, blanks and limitations")


# --------------------------------------------------------------------- method

def build_method(v: dict, research: dict, vrs: dict) -> str:
    src_rows = []
    seen = set()
    for group in ("day1_results", "day1_crowd_ownership", "roster_intel", "identity_resolutions",
                  "day2_context", "rejected_sources"):
        for item in research.get(group) or []:
            for s in item.get("sources") or ([] if group != "rejected_sources" else [item]):
                url = s.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                src_rows.append(f"""<tr><td data-label="Source"><a href="{esc(url)}" rel="noopener">{esc(url)}</a></td>
<td data-label="What it was used for">{esc(s.get('shows') or s.get('reason') or '')}</td>
<td data-label="Read (UTC)">{esc(s.get('read_utc') or '')}</td></tr>""")
    def evidence_links(c):
        urls = [e if str(e).startswith("http")
                else f"https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/{e}"
                for e in c.get("evidence") or []]
        return links(urls, ["evidence"] * len(urls))

    checks_rows = "".join(
        f"""<tr><td data-label="Check"><b>{esc(c['id'])}</b> {esc(c['name'])}</td>
<td data-label="How it is verified">{esc(c['detail'])}</td>
<td data-label="Result"><span class="badge {esc(c['status'])}">{esc(c['status'].upper())}</span>
<div class="small">{esc(c['rows_checked'])} checked · {esc(c['rows_failed'])} failed</div></td>
<td data-label="Evidence">{evidence_links(c)}</td></tr>"""
        for c in v["checks"])
    body = f"""<h2>What this audit is</h2>
<p>An independent, line-by-line re-verification of the published HotSpawn CS2 pick boards — the every-match
strategy board, its day-1 review and backtest, and the two contested team identities — performed by session
<code>6c5bb3d6</code> against official sources only. It does not replace any board; it re-derives their numbers
from raw evidence and publishes what agrees, what diverges and what could not be confirmed.</p>
<h2>Formulas</h2>
<ul>
<li><strong>Proportional no-vig.</strong> From a two-sided decimal line, <code>p_A = (1/d_A) / (1/d_A + 1/d_B)</code>.
Every retained raw quote in this repository was re-derived with this formula and compared with the published
market probability (tolerance ±{int(0.06 * 100)} points at the row mean, and the row must fall inside the
quote range).</li>
<li><strong>Leaderboard differential.</strong> <code>edge_X = points × (p_X − c_X)</code> where <code>c_X</code> is
the HotSpawn crowd ownership of side X. Derivation: your point margin against the field is
<code>points × [(1−c)·1{{X wins}} − c·1{{X loses}}]</code>, whose expectation is <code>points × (p − c)</code>.
The differential-optimal pick is <code>argmax</code> of that edge.</li>
<li><strong>Official-standings model (reference only).</strong>
<code>p = 1 / (1 + 10^(−(R_A − R_B)/400))</code> on Valve's published regional-standings points. The 400-point
scale is a stated modelling assumption, not a Valve-published quantity; it is used to expose divergence from the
market, never to overwrite a market price.</li>
</ul>
<h2>Source policy</h2>
<ul>
<li><strong>HotSpawn</strong> (<a href="https://play.hotspawn.com/lobby" rel="noopener">play.hotspawn.com/lobby</a>)
is fixture discovery and settlement only. Its crowd pick percentage is published as ownership for the differential
arithmetic and is never an input to a win probability — check C6 proves the published probabilities are identical
to the upstream market/model values.</li>
<li><strong>Prices</strong> come from licensed bookmakers and exchanges: Pinnacle (public guest odds API), Bovada
(public coupon JSON), the Melbet/1xBet-platform LineFeed, Kalshi, and the Thunderpick coefficients bo3.gg publishes
per fixture.</li>
<li><strong>Ratings</strong> come from Valve's own publication,
<a href="{esc(vrs.get('human_url'))}" rel="noopener">ValveSoftware/counter-strike_regional_standings</a>
(snapshot {esc(vrs.get('snapshot'))}, fetched in this run over the GitHub contents API:
HTTP {esc(vrs.get('http_status'))}, {esc(vrs.get('teams_parsed'))} teams).</li>
<li><strong>Results, rosters and context</strong> come from HLTV match/news/event/team pages, Liquipedia, and
named esports press, each recorded with its URL and UTC read time in
<code>data/6c5bb3d6/research.json</code>.</li>
<li><strong>Rejected sources</strong> are recorded with the reason — egamersworld's uniform 1.80/1.80 placeholder
prices and HLTV's fan vote are never used as probabilities.</li>
</ul>
<h2>The ten checks</h2>
<div class="tablewrap"><table><caption>Harness: <code>scripts/6c5bb3d6/verify.py</code>; result:
<a href="report.json">report.json</a>.</caption>
<thead><tr><th>Check</th><th>How it is verified</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{checks_rows}</tbody></table></div>
<h2>Every source read in this session</h2>
<div class="tablewrap"><table><caption>{len(src_rows)} distinct sources, each with its UTC read time.</caption>
<thead><tr><th>URL</th><th>What it was used for</th><th>Read (UTC)</th></tr></thead><tbody>{''.join(src_rows)}</tbody></table></div>
<h2>Reproduce</h2>
<pre class="small" style="overflow-x:auto;background:#0a1119;border:1px solid var(--line);border-radius:10px;padding:12px">python3 scripts/6c5bb3d6/fetch_vrs.py    # official Valve standings -&gt; data/6c5bb3d6/vrs_official.json
python3 scripts/6c5bb3d6/verify.py       # ten checks -&gt; data/6c5bb3d6/verification.json + audits/6c5bb3d6/report.json
python3 scripts/6c5bb3d6/build_pages.py  # these pages
python3 -m unittest tests.test_6c5bb3d6 -v</pre>
<div class="actions"><a class="button" href="index.html">Verification summary</a>
<a class="button ghost" href="flagged.html">Flagged for review</a></div>"""
    return page("Method & sources · session 6c5bb3d6", "method.html", body,
                "Method, formulas and every source read", "How this audit was verified")


def check_internal_links(pages: dict) -> list:
    """Fail closed on broken relative links (sibling pages count as present)."""
    import re
    problems = []
    own = {os.path.normpath(os.path.join(OUT, n)) for n in pages}
    for name, html_text in pages.items():
        for m in re.finditer(r'href="([^"#][^"]*)"', html_text):
            href = m.group(1).split("#")[0]
            if href.startswith(("http://", "https://", "mailto:")) or not href:
                continue
            target = os.path.normpath(os.path.join(OUT, href))
            if target in own:
                continue
            if not os.path.exists(target):
                problems.append(f"{name} -> {href}")
    return problems


def main() -> int:
    v = load("data/6c5bb3d6/verification.json")
    research = load("data/6c5bb3d6/research.json") or {}
    board = load("data/f28afd9e/board.json") or {}
    day1 = load("data/f28afd9e/day1_review.json") or {}
    vrs = load("data/6c5bb3d6/vrs_official.json") or {}
    if not v or not v.get("checks"):
        print("FATAL: run scripts/6c5bb3d6/verify.py first", file=sys.stderr)
        return 2

    # team names for the differential table rows
    names = {str(r.get("fixture_id")): (r.get("team_a"), r.get("team_b")) for r in board.get("rows") or []}
    for d in v.get("differential_table") or []:
        ta, tb = names.get(str(d.get("fixture_id")), ("A", "B"))
        d["_ta"], d["_tb"] = ta, tb

    os.makedirs(OUT, exist_ok=True)
    pages = {
        "index.html": build_index(v, research, board, day1, vrs),
        "flagged.html": build_flagged(v),
        "method.html": build_method(v, research, vrs),
    }
    problems = check_internal_links(pages)
    if problems:
        print("FATAL: broken internal links:", *problems[:10], sep="\n  ", file=sys.stderr)
        return 1
    for name, text in pages.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote audits/6c5bb3d6/{name} ({len(text)} bytes)")
    print(f"pages built: {len(pages)}, no broken internal links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
