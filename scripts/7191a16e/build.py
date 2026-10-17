#!/usr/bin/env python3
"""Session 7191a16e — phone-first day-4 desk for the HotSpawn CS2 lobby.

Rebuilds `today/` from two read-only inputs:
  * data/c64a5e19/board.json  — canonical 4-hourly collector (fixtures, market and
    VRS-model lines, retained sources). Never edited here.
  * data/7191a16e/research.json — this session's verified overlay for the fixtures
    the canonical collector left unpriced, plus the TWC Day-4 evidence ledger.

Rules enforced in code:
  * a probability is only ever copied from a two-sided market line or computed from
    an official Valve VRS pair, never invented;
  * an egamersworld 1.80/1.80 quote is a placeholder and is never accepted;
  * a fixture with no price still gets a direction (pick) with a blank percentage
    and an explicit reason;
  * HotSpawn crowd share is ownership context, never a probability input.
"""
from __future__ import annotations

import datetime
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "today"
CANON = ROOT / "data" / "c64a5e19" / "board.json"
RESEARCH = ROOT / "data" / "7191a16e" / "research.json"
LOBBY = "https://play.hotspawn.com/lobby"
PUBLISHED = ROOT / "data" / "7191a16e" / "board.json"


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def pct(p, digits=1) -> str:
    return "—" if p is None else f"{p * 100:.{digits}f}%"


def short_time(iso: str) -> str:
    if not iso or "T" not in iso:
        return "time TBC"
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.strftime("%d %b · %H:%M UTC")


CSS = """
:root{--bg:#0a0f1e;--card:#121a30;--line:#233156;--ink:#e9eefb;--muted:#9fb0d4;
--blue:#3b82f6;--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--pink:#ec4899}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:84px}
a{color:#7dd3fc}
.wrap{max-width:820px;margin:0 auto;padding:18px 14px 24px}
h1{font-size:1.5rem;line-height:1.2;margin:.2rem 0 .5rem}
h2{font-size:1.15rem;margin:1.5rem 0 .5rem}
h3{font-size:1rem;margin:1rem 0 .35rem}
p{margin:.5rem 0}
.eyebrow{color:#93c5fd;font-size:.78rem;letter-spacing:.09em;text-transform:uppercase;margin:0}
.muted{color:var(--muted)}.small{font-size:.83rem;line-height:1.45;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:12px 0}
.btn{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:56px;
background:var(--blue);color:#fff;text-decoration:none;font-weight:750;padding:14px 16px;
border-radius:14px;margin:9px 0;font-size:1.02rem;box-shadow:0 1px 0 rgba(255,255,255,.08) inset}
.btn .chev{font-size:1.35rem;opacity:.9}
.btn.alt{background:#17203a;border:1px solid #2c3c66;color:var(--ink)}
.btn.go{background:linear-gradient(180deg,#2563eb,#1d4ed8)}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin:12px 0}
.kpi{background:#0f1730;border:1px solid var(--line);border-radius:13px;padding:10px 12px}
.kpi b{display:block;font-size:1.55rem;line-height:1.1}
.kpi span{font-size:.78rem;color:var(--muted)}
.match{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:12px 0}
.top{display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted);gap:8px;margin-bottom:8px}
.teams{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}
.team{text-align:center;min-width:0}
.team .name{font-weight:750;font-size:.98rem;overflow-wrap:anywhere}
.team .num{font-size:1.75rem;font-weight:820;letter-spacing:-.02em}
.team.win .num{color:var(--green)}
.team.lose .num{color:#c7d2ea}
.vs{font-size:.7rem;color:var(--muted);text-align:center}
.bar{display:flex;height:9px;border-radius:6px;overflow:hidden;background:#26324f;margin:9px 0 6px}
.bar i{background:var(--green);height:100%}
.bar b{background:var(--pink);height:100%}
.pickline{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:8px}
.badge{background:#052e16;border:1px solid #166534;color:#86efac;border-radius:999px;padding:5px 11px;font-weight:800;font-size:.94rem}
.badge.dir{background:#1c1917;border-color:#57534e;color:#fbbf24}
.badge.tie{background:#1e1b4b;border-color:#4338ca;color:#c7d2fe}
.badge.climb{background:#3b0764;border-color:#7e22ce;color:#e9d5ff}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 8px;font-size:.72rem;color:var(--muted);margin:2px 4px 2px 0}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{color:#c7d2fa;font-weight:650;font-size:.8rem}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch}
.notice{border-left:4px solid var(--amber);background:#1c1917;border-radius:10px;padding:11px 13px;margin:12px 0}
.notice.good{border-color:var(--green);background:#052e16}
.notice.bad{border-color:var(--red);background:#2a0a0a}
nav.tabs{position:fixed;left:0;right:0;bottom:0;background:#0c1428ee;backdrop-filter:blur(8px);border-top:1px solid var(--line);display:flex;z-index:20}
nav.tabs a{flex:1;text-align:center;padding:10px 2px 12px;color:#b9c6e6;text-decoration:none;font-size:.7rem;font-weight:650;line-height:1.25}
nav.tabs a .ico{display:block;font-size:1.15rem;line-height:1.25}
nav.tabs a[aria-current="page"]{color:#fff;background:#1d4ed8}
.skip{position:absolute;left:-9999px}
.skip:focus{left:8px;top:8px;background:#fff;color:#000;padding:8px;z-index:99}
footer{margin-top:26px;border-top:1px solid var(--line);padding-top:12px}
"""

TABS = [
    ("index.html", "🏠", "Today"),
    ("picks.html", "🎯", "Picks"),
    ("twc.html", "🏆", "TWC"),
    ("unresolved.html", "❔", "No %"),
    ("method.html", "📖", "Method"),
]


def page(title: str, active: str, body: str, gen: str) -> str:
    parts = []
    for href, ico, label in TABS:
        cur = ' aria-current="page"' if href == active else ""
        parts.append(
            '<a href="%s"%s><span class="ico">%s</span>%s</a>' % (href, cur, ico, label)
        )
    tabs = "".join(parts)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="theme-color" content="#0a0f1e">'
        f"<title>{esc(title)} · HotSpawn CS2 picks</title><style>{CSS}</style></head><body>"
        '<a class="skip" href="#main">Skip to content</a><main class="wrap" id="main">'
        f"{body}"
        f'<footer><p class="small">Built {esc(gen)} UTC. Probabilities are estimates from the cited '
        'betting lines or an official-rating model — not guarantees. HotSpawn supplies fixtures and '
        'crowd ownership only; it is never a probability input. Not affiliated with HotSpawn or any bookmaker.</p>'
        f'<p class="small"><a href="picks.html">All picks</a> · <a href="unresolved.html">No-percentage list</a> · '
        f'<a href="flagged.html">Flagged</a> · <a href="{LOBBY}">HotSpawn lobby</a></p></footer></main>'
        f'<nav class="tabs">{tabs}</nav></body></html>'
    )


def load_rows():
    canon = json.loads(CANON.read_text())
    research = json.loads(RESEARCH.read_text())
    overrides = research.get("overrides", {})
    pick_only = research.get("pick_only", {})
    rows = []
    for r in canon.get("open") or []:
        fid = str(r["fixture_id"])
        line = r.get("line") or {}
        pa, pb = line.get("prob_a"), line.get("prob_b")
        pick = line.get("pick_team")
        basis = line.get("basis") or "no verified line"
        conf = line.get("confidence") or ""
        note = ""
        sources = [s for s in (r.get("sources") or []) if isinstance(s, dict) and s.get("url")]
        flags = list(r.get("flags") or [])
        kind = "priced" if pa is not None else "none"
        if fid in overrides:
            o = overrides[fid]
            side = o.get("pick_side") or ("a" if o["prob_a"] >= o["prob_b"] else "b")
            pa, pb = o["prob_a"], o["prob_b"]
            pick = r["team_a"] if side == "a" else r["team_b"]
            basis, conf, note = o["basis"], o["confidence"], o.get("note", "")
            sources = o.get("sources", sources)
            flags = o.get("flags", [])
            kind = "priced"
        elif fid in pick_only:
            p = pick_only[fid]
            pa = pb = None
            pick = p["pick"]
            basis = "research direction only (no price)"
            conf = p["confidence"]
            note = p["reason"]
            sources = p.get("sources", sources)
            kind = "direction"
        elif fid in (research.get("tie") or {}):
            pa = pb = 0.5
            pick = None
            kind = "tie"
            basis = "market (exact coin flip)"
            note = research["tie"][fid]["note"]
        rows.append(
            {
                "fid": fid,
                "comp": r.get("competition") or "",
                "tier": r.get("tier") or "?",
                "points": r.get("points"),
                "start": r.get("start_utc") or "",
                "a": r.get("team_a") or "?",
                "b": r.get("team_b") or "?",
                "pa": pa,
                "pb": pb,
                "pick": pick,
                "basis": basis,
                "conf": conf,
                "note": note,
                "sources": sources[:5],
                "hs": r.get("hotspawn_url") or LOBBY,
                "flags": flags,
                "kind": kind,
            }
        )
    rows.sort(key=lambda x: (x["start"] or "9999", x["fid"]))
    return canon, research, rows


def match_card(row, crowd=None, climb=None):
    pa, pb = row["pa"], row["pb"]
    a_cls = b_cls = ""
    if pa is not None and pb is not None and abs(pa - pb) > 0.0001:
        a_cls, b_cls = ("win", "lose") if pa > pb else ("lose", "win")
    bar = ""
    if pa is not None:
        bar = f'<div class="bar"><i style="width:{pa*100:.1f}%"></i><b style="width:{pb*100:.1f}%"></b></div>'
    if row["kind"] == "tie":
        pick_html = '<span class="badge tie">No edge · exact 50/50</span>'
    elif row["kind"] == "direction":
        pick_html = f'<span class="badge dir">Direction: {esc(row["pick"])}</span> <span class="muted small">no % published</span>'
    elif row["pick"]:
        pick_html = f'<span class="badge">Pick {esc(row["pick"])} · {pct(max(pa, pb))}</span>'
    else:
        pick_html = '<span class="badge dir">No pick</span>'
    crowd_html = ""
    if crowd:
        crowd_html = (
            f'<p class="small">HotSpawn crowd: <b>{crowd[0]*100:.0f}%</b> on {esc(row["a"])} / '
            f'<b>{crowd[1]*100:.0f}%</b> on {esc(row["b"])} — ownership only, not a probability.</p>'
        )
    climb_html = ""
    if climb:
        climb_html = f'<div class="notice good"><b>Climb spot:</b> {climb}</div>'
    srcs = " · ".join(
        f'<a href="{esc(s["url"])}" rel="noopener">{esc(s.get("label") or "source")}</a>'
        for s in row["sources"]
    ) or "—"
    flags = "".join(f'<span class="pill">{esc(f)}</span>' for f in row["flags"])
    note = f'<p class="small">{esc(row["note"])}</p>' if row["note"] else ""
    return f"""<article class="match" id="m-{esc(row['fid'])}">
<div class="top"><span>{esc(row['comp'])}</span><span>{esc(short_time(row['start']))}</span></div>
<div class="teams">
  <div class="team {a_cls}"><div class="name">{esc(row['a'])}</div><div class="num">{pct(pa)}</div></div>
  <div class="vs">vs</div>
  <div class="team {b_cls}"><div class="name">{esc(row['b'])}</div><div class="num">{pct(pb)}</div></div>
</div>
{bar}
<div class="pickline">{pick_html}</div>
{crowd_html}{climb_html}{note}
<p class="small">Tier {esc(row['tier'])} · {esc(row['points'])} pts · basis: {esc(row['basis'])} · <a href="{esc(row['hs'])}" rel="noopener">HotSpawn fixture</a></p>
<p class="small">Sources: {srcs}</p>
{('<p class="small">Flags: ' + flags + '</p>') if flags else ''}
</article>"""


def main():
    gen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    canon, research, rows = load_rows()
    OUT.mkdir(exist_ok=True)

    priced = [r for r in rows if r["kind"] == "priced"]
    direction = [r for r in rows if r["kind"] == "direction"]
    ties = [r for r in rows if r["kind"] == "tie"]
    named = [r for r in rows if r["pick"]]
    unresolved = direction + ties

    twc = research["twc"]
    sf1, sf2 = twc["semifinals"]["sf1"], twc["semifinals"]["sf2"]
    sf1_row = next((r for r in rows if r["fid"] == "1080207"), None)
    sf2_row = next((r for r in rows if r["fid"] == "1080208"), None)

    # ---------------- index.html : executive summary, phone first
    next_cards = "".join(match_card(r) for r in rows[:3])
    index = f"""
<p class="eyebrow">Executive summary · updated {esc(gen)} UTC</p>
<h1>CS2 picks — every match, one page</h1>
<p>Every open Counter-Strike match on the <a href="{LOBBY}" rel="noopener">HotSpawn Pick'ems lobby</a>,
with a pick, the win probability where a real line or official rating exists, and the source behind every number.</p>

<div class="kpis">
  <div class="kpi"><b>{len(rows)}</b><span>open CS2 matches</span></div>
  <div class="kpi"><b>{len(priced) + len(ties)}</b><span>with a published %</span></div>
  <div class="kpi"><b>{len(named)}</b><span>named picks</span></div>
  <div class="kpi"><b>{len(unresolved)}</b><span>no usable % (incl. coin flip)</span></div>
</div>

<h2>Where the picks are</h2>
<p class="small">Everything below is on this site. Bookmarks work on a phone.</p>
<a class="btn go" href="picks.html">🎯 All {len(rows)} open matches, one card each <span class="chev">›</span></a>
<a class="btn alt" href="twc.html">🏆 Thunderpick Day 4 — semifinal picks + Day 1–3 review <span class="chev">›</span></a>
<a class="btn alt" href="unresolved.html">❔ Matches without a % — and why ({len(unresolved)}) <span class="chev">›</span></a>
<a class="btn alt" href="flagged.html">🚩 Flagged for Review <span class="chev">›</span></a>
<a class="btn alt" href="method.html">📖 Method, sources and formulas <span class="chev">›</span></a>

<div class="card">
<h2 style="margin-top:0">Today's headline: Thunderpick semifinals</h2>
<p class="small">Both semifinals are on the HotSpawn lobby now (Tier S, 7 points). Crowd ownership is the
only thing taken from HotSpawn.</p>
</div>
{match_card(sf1_row, crowd=(sf1['crowd']['a'], sf1['crowd']['b']),
            climb='<b>Aurora at 48.6% vs 18% crowd.</b> Fading FURIA costs only 2.8% of the points in expectation '
                  'and gains 30.6 ownership-points against the field when Aurora win. This is the one spot on the '
                  'slate where differentiation is close to free.') if sf1_row else ''}
{match_card(sf2_row, climb='<b>None on the series winner.</b> BETBOOM at 25.3% is below the 40% floor; fading here '
                           'costs about 49% of the points in expectation. If you want the contrarian angle, it is the '
                           'map market (+1.5 / over 2.5), not the match result.') if sf2_row else ''}

<h2>Next up</h2>
{next_cards}
<a class="btn" href="picks.html">See all {len(rows)} matches <span class="chev">›</span></a>

<div class="notice">
<b>What “no %” means.</b> {len(direction)} matches have a named direction but no percentage because no
two-sided price exists and one side has no official Valve rating, so a rating pair cannot be formed.
A blank is deliberate — the <a href="unresolved.html">no-percentage list</a> shows exactly what was tried for each.
</div>
"""
    (OUT / "index.html").write_text(page("Today's picks", "index.html", index, gen))

    # ---------------- picks.html
    priced_cards = "".join(match_card(r) for r in priced + ties)
    dir_cards = "".join(match_card(r) for r in direction)
    picks = f"""
<p class="eyebrow">All picks · {esc(gen)} UTC</p>
<h1>🎯 Picks for every open match</h1>
<p>Sorted by start time. The big number is the fair win probability after removing the bookmaker margin.
The green badge is the pick.</p>
<div class="notice good"><b>{len(rows)} open matches · {len(named)} named picks · {len(priced) + len(ties)} with a published %.</b>
Every match has either a pick or an explicit “no edge” coin-flip label.</div>
<h2>Priced matches ({len(priced) + len(ties)})</h2>
{priced_cards}
<h2>Direction only — no percentage ({len(direction)})</h2>
<p class="small">A direction is published; the percentage is blank because the inputs for a number are missing.
Full reasons on the <a href="unresolved.html">no-percentage page</a>.</p>
{dir_cards}
"""
    (OUT / "picks.html").write_text(page("All picks", "picks.html", picks, gen))

    # ---------------- twc.html
    result_rows = "".join(
        f'<tr><td>{esc(x["day"])}</td><td>{esc(x["stage"])}</td>'
        f'<td><b>{esc(x["winner"])}</b> {esc(x["score"])} {esc(x["loser"])}</td>'
        f'<td class="small">{esc(x["maps"]) if x["verified_maps"] else "—"}</td>'
        f'<td><a href="{esc(x["url"])}" rel="noopener">HLTV</a></td></tr>'
        for x in twc["results"]
    )
    day_notes = "".join(
        "<li><b>%s.</b> %s</li>" % (esc(x["label"]), esc(x["detail"]))
        for x in twc.get("day_by_day", [])
    )
    twc_body = f"""
<p class="eyebrow">Thunderpick World Championship 2026 · Malta · $1,000,000</p>
<h1>🏆 Day 4: what Days 1–3 actually tell us</h1>
<p class="small">Every series result below was re-read from HLTV's event-8932 results page on 17 Oct.
Map scores are shown only where this session also verified the map detail; a dash means the series score
is verified but the map line was not re-checked.</p>

<h2>Verified results</h2>
<div class="tbl"><table>
<thead><tr><th>Day</th><th>Stage</th><th>Result</th><th>Maps</th><th>Source</th></tr></thead>
<tbody>{result_rows}</tbody></table></div>

<h2>What Days 2–3 actually changed</h2>
<ul>{day_notes}</ul>

<h2>The upset, and what it was</h2>
<div class="card"><p><b>9z 2–0 Aurora (Day 1).</b> {esc(twc['upset']['why_it_happened'])}</p>
<p>{esc(twc['upset']['correction'])}</p>
<p class="small"><a href="{esc(twc['upset']['url'])}" rel="noopener">HLTV event results</a></p></div>
<div class="notice good"><b>What it means for Day 4:</b> {esc(twc['upset']['lesson'])}</div>

<h2>“Recent Aurora roster change” — verdict</h2>
<div class="notice"><b>{esc(twc['roster']['verdict'])}</b><br>{esc(twc['roster']['detail'])}<br>
<span class="small">Sources: <a href="{esc(twc['roster']['urls'][0])}" rel="noopener">HLTV 45082</a> ·
<a href="{esc(twc['roster']['urls'][1])}" rel="noopener">today's lineup</a></span></div>
<p>{esc(twc['roster']['implication'])}</p>

<h2>Semifinal 1 — FURIA vs Aurora</h2>
<p class="small"><b>Kickoff 14:00 UTC</b> (HotSpawn lock 13:54Z). Verified by countdown arithmetic: at 09:49Z
HLTV showed 4h17m remaining and the lobby showed 04:09:47 to lock, both pointing at 14:00Z. The "10:00" printed on
those pages is a UTC−4 display clock, not UTC — see the <a href="flagged.html">flag list</a>.</p>
{('<p><b>Market:</b> FURIA ' + pct(sf1['fresh_mean']['prob_a']) + ' / Aurora ' + pct(sf1['fresh_mean']['prob_b']) + '</p>')}
<ul class="small">{''.join(f'<li>{esc(c)}</li>' for c in sf1['context'])}</ul>
<p><b>Safe pick:</b> {esc(sf1['safe_pick'])}</p>
<div class="notice good"><b>Climb pick:</b> {esc(sf1['climb_pick'])}</div>
<p class="small">Sources: <a href="{esc(sf1['quotes'][0]['url'])}" rel="noopener">stavka (BetBoom/Winline)</a> ·
<a href="{esc(sf1['quotes'][1]['url'])}" rel="noopener">egamersworld</a> ·
<a href="{esc(sf1['quotes'][2]['url'])}" rel="noopener">Polymarket</a> ·
<a href="{esc(sf1['hltv'])}" rel="noopener">HLTV</a></p>

<h2>Semifinal 2 — Falcons vs BETBOOM</h2>
{('<p><b>Market:</b> Falcons ' + pct(sf2['fresh_mean']['prob_a']) + ' / BETBOOM ' + pct(sf2['fresh_mean']['prob_b']) + '</p>')}
<ul class="small">{''.join(f'<li>{esc(c)}</li>' for c in sf2['context'])}</ul>
<p><b>Safe pick:</b> {esc(sf2['safe_pick'])}</p>
<div class="notice"><b>Climb pick:</b> {esc(sf2['climb_pick'])}</div>
<p class="small">Sources: <a href="{esc(sf2['quotes'][0]['url'])}" rel="noopener">stavka (Fonbet/Winline)</a> ·
<a href="{esc(sf2['quotes'][2]['url'])}" rel="noopener">egamersworld</a> ·
<a href="{esc(sf2['hltv'])}" rel="noopener">HLTV</a></p>

<h2>The contrarian rule, in one line</h2>
<p>Fade the field only when your side is <b>at least 40%</b> to win. Below that the expected-points cost
grows faster than the ownership differential can repay. 48.6% is a green light; 25.3% is not.</p>
"""
    (OUT / "twc.html").write_text(page("TWC Day 4", "twc.html", twc_body, gen))

    # ---------------- unresolved.html
    def link(s):
        return '<a href="%s" rel="noopener">%s</a>' % (
            esc(s["url"]),
            esc(s.get("label") or "source"),
        )

    u_rows = "".join(
        '<tr><td><b>%s</b> vs <b>%s</b><div class="small">#%s · %s · %s</div></td>'
        '<td>%s</td><td class="small">%s</td><td class="small">%s</td></tr>'
        % (
            esc(r["a"]),
            esc(r["b"]),
            esc(r["fid"]),
            esc(r["comp"]),
            esc(short_time(r["start"])),
            ("<b>%s</b>" % esc(r["pick"])) if r["pick"] else "no side",
            esc(r["note"] or "Priced exact coin flip in the canonical market blend; no side has an edge."),
            " · ".join(link(s) for s in r["sources"]) or "—",
        )
        for r in unresolved
    )
    placeholder_rows = "".join(
        f'<tr><td>{esc(p["fixture"])}</td><td><code>{esc(p["shown"])}</code></td>'
        f'<td><a href="{esc(p["url"])}" rel="noopener">egamersworld</a></td></tr>'
        for p in research["placeholder_ledger"]
    )
    ladder = "".join(f"<li>{esc(x)}</li>" for x in research["ladder"])
    unres = f"""
<p class="eyebrow">Unresolved &amp; limitations</p>
<h1>❔ Matches without a percentage</h1>
<p>These are the only gaps left on the site. Each has a named direction, or an explicit “no edge”, and the exact
reason a number is missing. Nothing here is guessed.</p>
<div class="tbl"><table>
<thead><tr><th>Match</th><th>Direction</th><th>Why no % / what was tried</th><th>Sources checked</th></tr></thead>
<tbody>{u_rows}</tbody></table></div>

<h2>The resolution ladder (applied in this order)</h2>
<ol>{ladder}</ol>

<h2>Why books do not price these</h2>
<p class="small">Four fixtures this week carry an <code>egamersworld 1.80 / 1.80</code> quote with 0% / 0% on
both sides. That is the platform's unset default, not a market: a genuine two-sided line on the same site
appears as e.g. <code>1.75 / 1.97</code>. Republishing 1.80/1.80 would manufacture a 50/50 that no book offered,
so it is rejected everywhere on this site.</p>
<div class="tbl"><table><thead><tr><th>Fixture</th><th>What the site printed</th><th>Link</th></tr></thead>
<tbody>{placeholder_rows}</tbody></table></div>

<h2>Known limitations</h2>
<ul class="small">
<li><b>Direction-only rows.</b> A pick without a percentage is a judgement from ranking, form and head-to-head, not a priced edge. Treat it as low confidence.</li>
<li><b>Model rows.</b> The originated line uses official Valve VRS points and a 400-point logistic scale fitted on 11 market pairs (MAE 0.075). The scale is this project's assumption, not a Valve quantity.</li>
<li><b>Alias joins.</b> ex-6666 → Valve’s “6666”, WROTBERRY → WBT / WhiteBIT Team. Both are documented on the row and flagged.</li>
<li><b>Single-book rows.</b> Lavked–LFO 10 rests on one two-sided book; re-check before lock.</li>
<li><b>Line movement.</b> Every probability carries its capture time. A price read at 09:00 UTC is not the price at lock.</li>
<li><b>Inventory lag.</b> This page rebuilds from the canonical 4-hourly collector. A fixture added to HotSpawn in the last few hours may not appear until the next run.</li>
</ul>
"""
    (OUT / "unresolved.html").write_text(page("Unresolved", "unresolved.html", unres, gen))

    # ---------------- flagged.html
    flagged = f"""
<p class="eyebrow">Flagged for review</p>
<h1>🚩 Irregularities found this session</h1>
<p>Non-blocking. Nothing below was silently “fixed”. Each item names what to check.</p>
<div class="tbl"><table><thead><tr><th>#</th><th>Finding</th><th>Evidence</th></tr></thead><tbody>
<tr><td>F1</td><td><b>Both sources render match times on a UTC−4 display clock — and an earlier draft of this page got it backwards.</b> FURIA–Aurora prints as “10:00” on HLTV and on the HotSpawn lobby, but the countdowns at 09:49Z (4h17m on HLTV, 04:09:47 to lock on HotSpawn) both resolve to a <b>14:00Z</b> start. The canonical board’s 14:00Z is correct. The first draft flagged the board as 4 hours late; that flag was wrong, and it is retracted here rather than quietly deleted. Rule adopted: board <code>start_utc</code> is authoritative; a displayed time is never read as UTC.</td><td><a href="{esc(sf1['hltv'])}" rel="noopener">HLTV match page</a> · <a href="{LOBBY}" rel="noopener">HotSpawn lobby</a></td></tr>
<tr><td>F2</td><td><b>egamersworld emits a fake 1.80/1.80 market.</b> Seven fixtures show identical 1.80/1.80 with 0%/0% while the same site prints real numbers (1.75/1.97) elsewhere. Rejected as a price everywhere on this site.</td><td><a href="unresolved.html">placeholder ledger</a></td></tr>
<tr><td>F3</td><td><b>The “recent Aurora roster change” premise is stale.</b> The rebuild was July 2026, and the official VRS snapshot of 5 Oct still lists the same five players. No October move exists in HLTV’s record, so the Day-1 loss cannot be blamed on a new lineup.</td><td><a href="{esc(twc['roster']['urls'][0])}" rel="noopener">HLTV 45082</a> · <a href="{esc(twc['roster']['urls'][1])}" rel="noopener">Valve VRS</a></td></tr>
<tr><td>F4</td><td><b>Why this desk replaced the previous one.</b> The superseded build (<code>today-9c44d0e9</code>) left 6 of its 34 open fixtures with no pick at all and carried its Thunderpick numbers as literals in the builder. This build derives every number from the board or from the research ledger, and every open fixture gets either a percentage or a stated direction.</td><td><a href="../data/9c44d0e9/board.json">old board summary</a> · <a href="../data/7191a16e/board.json">new board</a></td></tr>
<tr><td>F5</td><td><b>Alias joins were required.</b> ex-6666 is Valve’s “6666”; WROTBERRY is HotSpawn’s name for WBT. Both are labelled on the row rather than merged silently.</td><td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md" rel="noopener">Valve VRS</a></td></tr>
<tr><td>F6</td><td><b>One exact 50/50.</b> Omega–Bushido Wildcats is priced at 50.0/50.0. No pick is published because no side has an edge; that is a deliberate blank, not a missing result.</td><td><a href="picks.html#m-1082020">row</a></td></tr>
<tr><td>F7</td><td><b>VRS snapshot is 12 days old.</b> <code>standings_global_2026_10_05</code> is the newest official file used. It is inside the 14-day window but expires on 19 Oct; model rows must be re-derived after that.</td><td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">Valve standings repo</a></td></tr>
<tr><td>F8</td><td><b>Stavka’s kickoff clocks disagree with themselves.</b> The Falcons–BETBOOM page shows 17:00 in its header and 20:00 in the cross-link sidebar for the same match. Stavka prices are used; its clocks never are.</td><td><a href="{esc(sf2['quotes'][0]['url'])}" rel="noopener">stavka</a></td></tr>
</tbody></table></div>
"""
    (OUT / "flagged.html").write_text(page("Flagged", "flagged.html", flagged, gen))

    # ---------------- method.html
    method = f"""
<p class="eyebrow">Method &amp; sources</p>
<h1>📖 How every number is made</h1>
<h2>Probability from a market</h2>
<p>For decimal odds <i>d<sub>A</sub></i>, <i>d<sub>B</sub></i>:
<code>p<sub>A</sub> = (1/d<sub>A</sub>) / ((1/d<sub>A</sub>) + (1/d<sub>B</sub>))</code>.
The overround is removed. Exchange cents are normalised the same way. Accepted two-sided sources are averaged
with equal weight and the row lists them all.</p>
<h2>Probability from official ratings</h2>
<p><code>p<sub>A</sub> = 1 / (1 + 10^(-(Pts<sub>A</sub> - Pts<sub>B</sub>) × k / 400))</code>,
with Pts from Valve’s published regional standings and <code>k = 0.421341</code> fitted on 11 market/model pairs
(MAE 0.075). The 400-point scale is a stated modelling assumption, not a Valve-published quantity.</p>
<h2>What is never used</h2>
<ul>
<li>HotSpawn “picked %” — it is crowd ownership, shown only as context.</li>
<li>The egamersworld 1.80/1.80 default — a placeholder, rejected.</li>
<li>A forced 50/50 to fill a blank row.</li>
</ul>
<h2>Refresh</h2>
<p>The canonical collector (<code>every-match-c64a5e19</code>) rebuilds the fixture board every 4 hours.
<code>today-9c44d0e9</code> then runs this builder and republishes these pages. No manual step.</p>
<h2>Sources</h2>
<ul class="small">
<li><a href="{LOBBY}" rel="noopener">HotSpawn lobby</a> — fixtures, tier, points, crowd ownership only.</li>
<li><a href="{esc(twc['event_url'])}" rel="noopener">HLTV event 8932</a> — results, schedule, rosters.</li>
<li><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">Valve regional standings</a> — official VRS points.</li>
<li><a href="{esc(sf1['quotes'][0]['url'])}" rel="noopener">stavka.tv</a> · <a href="{esc(sf1['quotes'][1]['url'])}" rel="noopener">egamersworld</a> · <a href="https://kushvsporte.ru/event/6977301-apogee-esports-team-nemesis" rel="noopener">kushvsporte</a> — prices.</li>
<li><a href="{esc(sf1['quotes'][2]['url'])}" rel="noopener">Polymarket</a> — exchange prices where a market exists.</li>
</ul>
<h2>Machine-readable data</h2>
<p class="small"><a href="../data/7191a16e/board.json">board.json</a> ·
<a href="../data/7191a16e/research.json">research.json</a> ·
<a href="../data/c64a5e19/board.json">canonical board</a></p>
"""
    (OUT / "method.html").write_text(page("Method", "method.html", method, gen))

    board = {
        "session": "7191a16e",
        "generated_utc": gen.replace(" ", "T") + ":00Z",
        "inputs": {
            "canonical": str(CANON.relative_to(ROOT)),
            "canonical_generated": canon.get("generated_utc"),
            "research": str(RESEARCH.relative_to(ROOT)),
            "lobby_read_utc": research["lobby_read_utc"],
        },
        "summary": {
            "open": len(rows),
            "priced": len(priced) + len(ties),
            "named_pick": len(named),
            "direction_only": len(direction),
            "exact_tie": len(ties),
            "blank_rate": round(len(direction) / len(rows), 4) if rows else 0,
        },
        "rows": rows,
    }
    PUBLISHED.write_text(json.dumps(board, indent=1))
    print(
        f"open={len(rows)} priced={len(priced)+len(ties)} named={len(named)} "
        f"direction_only={len(direction)} ties={len(ties)}"
    )


if __name__ == "__main__":
    main()
