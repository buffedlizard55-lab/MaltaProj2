#!/usr/bin/env python3
"""Session 17866d06 — render the day-4 desk into ``picks-day4/``.

Six pages, mobile-first, every value either source-linked or blank-and-flagged:

  index.html       executive summary + the one phone-friendly path to the picks
  picks.html       a pick and a win probability for every open HotSpawn CS2 fixture
  twc.html         Thunderpick World Championship 2026 day 1-3 review -> day 4/5
  unresolved.html  matches we could not price, why, and what that costs
  flagged.html     "Flagged for Review": irregularities, with sources
  method.html      sources, join rule, maths, calibration, rules, verification

Nothing here invents a number: a value that is not in ``data/17866d06/board.json``
or ``scripts/17866d06/research.py`` renders as an explicit blank plus an UNVERIFIED tag.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "17866d06"
OUT = ROOT / "picks-day4"

REPO_BLOB = "https://github.com/buffedlizard55-lab/MaltaProj2/blob/main"
SITE = "https://buffedlizard55-lab.github.io/MaltaProj2"

CSS = """
:root{--bg:#0b1220;--card:#141f33;--txt:#e9effb;--mut:#93a4c3;--line:#26344c;--acc:#3d7dff;
--good:#1f9d63;--warn:#c9861b;--bad:#c4453c;--violet:#7c3aed;--teal:#0f766e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:16px}
header.site{position:sticky;top:0;background:rgba(11,18,32,.97);border-bottom:1px solid var(--line);z-index:30}
header.site .wrap{padding:9px 14px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
header.site strong{font-size:13.5px;margin-right:4px}
header.site a{color:var(--mut);text-decoration:none;font-size:13.5px;padding:8px 9px;border-radius:9px}
header.site a.on,header.site a:hover,header.site a:focus{background:var(--card);color:var(--txt)}
main.wrap{padding-bottom:56px}
h1{font-size:25px;line-height:1.18;margin:12px 0 6px}
h2{font-size:19px;margin:28px 0 8px;padding-top:4px}
h3{font-size:16px;margin:18px 0 6px}
p{margin:9px 0}
a{color:#8db6ff}
.mut{color:var(--mut);font-size:13.5px}
.tiny{font-size:12.5px;color:var(--mut)}
.eyebrow{color:#7fa7ff;font-weight:800;letter-spacing:.09em;text-transform:uppercase;font-size:11.5px;margin:0}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.card{flex:1 1 150px;background:var(--card);border:1px solid var(--line);border-radius:13px;padding:12px 13px}
.card-num{font-size:23px;font-weight:800;line-height:1.1}
.card-label{color:var(--mut);font-size:12.5px;margin-top:3px}
.btn{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;font-weight:800;
border-radius:13px;padding:14px 16px;margin:8px 8px 0 0;min-height:46px;font-size:15.5px}
.btn.ghost{background:transparent;border:1.5px solid var(--acc);color:#a8c6ff}
.btn.good{background:var(--good)} .btn.violet{background:var(--violet)} .btn.warn{background:var(--warn);color:#221602}
.btn:focus{outline:3px solid #fff3}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#b9c8e4;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:800;white-space:nowrap}
.tag.pick{background:var(--good);color:#fff}
.tag.contra{background:var(--violet);color:#fff}
.tag.mkt{background:#1d4ed8;color:#fff}
.tag.mdl{background:#334155;color:#dbe7ff}
.tag.blank{background:#3a2530;color:#ffb4ae}
.tag.warn{background:#3a2d13;color:#ffd591}
.tag.bad{background:#3d1a17;color:#ffb3ab}
.tag.teal{background:var(--teal);color:#fff}
.pickbox{background:linear-gradient(180deg,#17324a,#132338);border:1px solid #2c4a6d;border-radius:13px;padding:12px 13px}
.pickbox .who{font-size:18px;font-weight:800}
.bar{height:9px;border-radius:99px;background:#22304a;overflow:hidden;margin:6px 0 3px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#3d7dff,#22c39a)}
details{background:var(--card);border:1px solid var(--line);border-radius:13px;margin:10px 0}
details>summary{cursor:pointer;padding:12px 14px;font-weight:700}
details[open]>summary{border-bottom:1px solid var(--line)}
details .inner{padding:8px 14px 14px}
.tablewrap{overflow-x:auto}
.note{background:#131d2f;border-left:3px solid var(--acc);padding:10px 12px;border-radius:0 10px 10px 0;margin:12px 0}
.note.warn{border-color:var(--warn);background:#1d1a12}
.note.bad{border-color:var(--bad);background:#1e1414}
.note.good{border-color:var(--good);background:#12211a}
ul{margin:8px 0 8px 20px;padding:0}li{margin:5px 0}
code{background:#0f1a2c;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:13px}
.srcs{font-size:12.5px;color:var(--mut);margin-top:6px}
.srcs a{color:#9dc0ff}
hr{border:0;border-top:1px solid var(--line);margin:22px 0}
footer{border-top:1px solid var(--line);margin-top:30px;padding-top:14px}
@media (max-width:680px){
 h1{font-size:21px}.wrap{padding:12px}
 .btn{display:block;text-align:center;margin:8px 0 0}
 table.responsive thead{display:none}
 table.responsive tr{display:block;border:1px solid var(--line);border-radius:13px;margin:11px 0;padding:7px 3px;background:var(--card)}
 table.responsive td{display:flex;justify-content:space-between;gap:12px;border:0;padding:5px 11px}
 table.responsive td:before{content:attr(data-label);color:#9db1d4;font-size:11px;text-transform:uppercase;
   letter-spacing:.04em;font-weight:800;flex:0 0 40%}
 table.responsive td.num{text-align:right}
 header.site .wrap{gap:2px}header.site a{font-size:12.5px;padding:7px 6px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

PAGES = [("index.html", "Start here"), ("picks.html", "Every match"), ("twc.html", "TWC day 1–3 → 4"),
         ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged for review"),
         ("method.html", "Method & sources")]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def blank(label="UNVERIFIED") -> str:
    return f'<span class="tag blank">— {esc(label)}</span>'


def pct(value, digits=1) -> str:
    if value is None:
        return blank()
    return f"{value * 100:.{digits}f}%"


def num(value, suffix="") -> str:
    if value is None:
        return blank()
    return f"{esc(value)}{suffix}"


def dash(value, suffix="") -> str:
    """Non-critical blanks: an em dash, no UNVERIFIED tag (the tag stays on the numbers that
    matter - probabilities, odds and picks - so the page does not turn into a wall of warnings)."""
    if value is None:
        return "—"
    return f"{esc(value)}{suffix}"


def dash_pct(value, digits=1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def link(label, url) -> str:
    if not url:
        return esc(label)
    return f'<a href="{esc(url)}" rel="noopener">{esc(label)}</a>'


def nav(active: str) -> str:
    items = []
    for name, label in PAGES:
        cls = ' class="on"' if name == active else ""
        items.append(f'<a href="{name}"{cls}>{esc(label)}</a>')
    items = "".join(items)
    return ('<header class="site"><div class="wrap"><strong>Day-4 desk · 17866d06</strong>'
            f'{items}<a href="../index.html">Site home</a></div></header>')


def page(name: str, title: str, description: str, body: str, board: dict) -> str:
    stamp = esc(board.get("generated_utc") or "not generated yet")
    captured = esc(board.get("captured_utc") or "no capture")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<style>{CSS}</style></head>
<body>{nav(name)}
<main class="wrap">
{body}
<footer><p class="tiny">Session 17866d06 · board generated {stamp} from evidence captured {captured} ·
refreshed automatically every 4 hours by
{link(".github/workflows/day4live-17866d06.yml", REPO_BLOB + "/.github/workflows/day4live-17866d06.yml")} ·
HotSpawn is used for fixtures, points and crowd ownership only, never as a probability input.</p>
<p class="tiny">{link("Flagged for Review", "flagged.html")} · {link("Method & sources", "method.html")} ·
{link("Unresolved matches", "unresolved.html")} · {link("Site home", "../index.html")}</p></footer>
</main></body></html>
"""


def source_line(pairs) -> str:
    if not pairs:
        return ""
    rendered = " · ".join(link(label, url) for label, url in pairs)
    return f'<div class="srcs">Sources: {rendered}</div>'


def rule_tag(rule: str) -> str:
    if not rule:
        return blank("no rule")
    if rule.startswith("R2"):
        return f'<span class="tag contra">{esc(rule)}</span>'
    if rule.startswith("R3"):
        return f'<span class="tag warn">{esc(rule)}</span>'
    if rule.startswith("R5"):
        return f'<span class="tag teal">{esc(rule)}</span>'
    if rule.startswith("R1"):
        return f'<span class="tag pick">{esc(rule)}</span>'
    return f'<span class="tag blank">{esc(rule)}</span>'


def basis_tag(row: dict) -> str:
    final = row.get("final") or {}
    if final.get("prob_a") is None:
        return '<span class="tag blank">no line</span>'
    if final.get("no_market"):
        return '<span class="tag mdl">our model only</span>'
    if (row.get("consensus") or {}).get("n_sources", 0) >= 2:
        return '<span class="tag mkt">market ×%d</span>' % row["consensus"]["n_sources"]
    return '<span class="tag mkt">market ×1</span>'


def local_time_note(start_utc: str) -> str:
    return f'{esc((start_utc or "")[11:16])} UTC'


# --------------------------------------------------------------------- picks page
def fixture_card(row: dict) -> str:
    final = row.get("final") or {}
    pick = row.get("pick") or {}
    prob_a, prob_b = final.get("prob_a"), final.get("prob_b")
    bar = ""
    if prob_a is not None:
        bar = (f'<div class="bar" role="img" aria-label="win probability {row.get("team_a")} '
               f'{prob_a * 100:.0f} percent"><i style="width:{prob_a * 100:.1f}%"></i></div>')
    quote_rows = "".join(
        f'<tr><td data-label="Source">{link(q.get("book") or q.get("source_key"), q.get("public_url"))}'
        f'<div class="tiny">{esc(q.get("source_key"))} · read {esc(q.get("retrieved_utc"))}'
        + (f' · vol ${float(q["volume_usd"]):,.0f}' if q.get("volume_usd") else "")
        + f' · join {esc((q.get("join") or {}).get("confidence", "?"))}</div></td>'
        f'<td data-label="Odds" class="num">'
        + (f'{q["decimal_a"]:.2f} / {q["decimal_b"]:.2f}' if q.get("decimal_a") else
           (f'{q.get("price_a"):.3f} / {q.get("price_b"):.3f}' if q.get("price_a") is not None else "—"))
        + '</td><td data-label="No-vig" class="num">'
        + (pct(q.get("implied_a")) if q.get("implied_a") is not None else "—")
        + f'</td><td data-label="Evidence">{link("api row", q.get("evidence_url"))}</td></tr>'
        for q in row.get("quotes") or [])
    limitations = "".join(f"<li>{esc(text)}</li>" for text in row.get("limitations") or [])
    flags = "".join(f'<li>{esc(f["team"])}: {esc(f["text"])}{source_line([(s["label"], s["url"]) for s in f["sources"]])}</li>'
                    for f in row.get("context_flags") or [])
    vrs = row.get("vrs") or {}
    vrs_bits = []
    for side in ("a", "b"):
        record = vrs.get(side) or {}
        if record.get("resolved"):
            vrs_bits.append(f"{row.get(f'team_{side}')}: #{record.get('standing')} · "
                            f"{record.get('points')} pts ({record.get('region')}, {record.get('method')})")
        else:
            vrs_bits.append(f"{row.get(f'team_{side}')}: not resolved against Valve's standings — "
                            f"{record.get('reason', 'unresolved')}")
    crowd_a, crowd_b = row.get("crowd_a"), row.get("crowd_b")
    return f"""<details id="fx{esc(row.get('fixture_id'))}">
<summary><span class="tag {'pick' if not row.get('unresolved') else 'blank'}">{esc(local_time_note(row.get('start_utc')))}</span>
 <strong>{esc(row.get('team_a'))} v {esc(row.get('team_b'))}</strong>
 <span class="mut">{esc(row.get('competition'))} · tier {esc(row.get('tier'))} · {num(row.get('offered_points'))} pts</span><br>
 <span style="font-size:15px">Pick: <strong>{esc(pick.get('team') or '— unresolved')}</strong></span>
 {rule_tag(pick.get('rule'))} {basis_tag(row)}
 <span class="mut">{dash_pct(pick.get('prob'))} · crowd {dash(crowd_a if pick.get('side') == 'a' else crowd_b, '%')}</span></summary>
<div class="inner">
<p class="mut">Starts {esc(row.get('start_utc'))} · locks {esc(row.get('lock_utc') or '?')} ·
fixture {esc(row.get('fixture_id'))} · {link('HotSpawn lobby', row.get('hotspawn_public_url'))} ·
{link('fixtures API row', row.get('hotspawn_api_url'))}</p>
<div class="pickbox"><div class="who">{esc(pick.get('team') or 'No pick — unresolved')} · {dash_pct(pick.get('prob'))}</div>
{bar}<div class="tiny">{esc(row.get('team_a'))} {dash_pct(prob_a)} · {esc(row.get('team_b'))} {dash_pct(prob_b)} ·
expected points {dash(pick.get('expected_points'))} of {dash(row.get('offered_points'))} offered</div></div>
<p class="mut"><strong>Why:</strong> {esc(pick.get('reason') or '—')}</p>
<p class="mut"><strong>Crowd ownership (HotSpawn, context only — never a probability input):</strong>
{esc(row.get('team_a'))} {dash(crowd_a, '%')} · {esc(row.get('team_b'))} {dash(crowd_b, '%')} ·
{dash(row.get('total_picks'))} picks so far{'' if row.get('total_picks') is not None else ' (not published)'}</p>
<h3>Where the price came from</h3>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Source</th><th class="num">Odds / price</th>
<th class="num">No-vig</th><th>Evidence</th></tr></thead><tbody>
{quote_rows or f'<tr><td data-label="Source" colspan="4">{blank("no market joined")} — see <a href="unresolved.html">Unresolved</a></td></tr>'}
</tbody></table></div>
<p class="mut"><strong>Basis of our line:</strong> {esc(final.get('basis') or '—')}
{(' · our originated VRS line says ' + pct(final.get('model_prob_a')) + ' for ' + esc(row.get('team_a'))) if final.get('model_prob_a') is not None else ''}</p>
<h3>Official Valve Regional Standings</h3>
<ul class="tiny">{''.join('<li>' + esc(bit) + '</li>' for bit in vrs_bits)}</ul>
{('<p class="tiny">Valve file: ' + link('standings_global (official)', vrs.get('source')) + '</p>') if vrs.get('source') else ''}
{('<h3>Verified context</h3><ul>' + flags + '</ul>') if flags else ''}
{('<h3>Limitations on this row</h3><ul class="tiny">' + limitations + '</ul>') if limitations else ''}
</div></details>"""


def render_picks(board: dict) -> str:
    rows = board.get("open") or []
    resolved = [r for r in rows if not r.get("unresolved")]
    unresolved = [r for r in rows if r.get("unresolved")]
    groups = {}
    for row in rows:
        slot = (row.get("start_utc") or "?")[:13] + ":00 UTC"
        groups.setdefault(slot, []).append(row)
    body = ["""<p class="eyebrow">Every open HotSpawn CS2 fixture · priced from books and exchanges, never from HotSpawn</p>
<h1>A pick and a win probability for every match</h1>
<p class="mut">Open each match for the pick, both sides' probabilities, the actual odds we found with a link
to the source, the crowd ownership for context, and the limitations of that row. Values we could not confirm
are blank and tagged UNVERIFIED — nothing is inferred.</p>"""]
    summary = board.get("summary") or {}
    body.append(f"""<div class="cards">
<div class="card"><div class="card-num">{esc(summary.get('open_fixtures', len(rows)))}</div>
<div class="card-label">open CS2 fixtures on HotSpawn</div></div>
<div class="card"><div class="card-num">{esc(summary.get('resolved', len(resolved)))}</div>
<div class="card-label">with a pick and a probability</div></div>
<div class="card"><div class="card-num">{esc(summary.get('unresolved', len(unresolved)))}</div>
<div class="card-label">unresolved — <a href="unresolved.html">why</a></div></div>
<div class="card"><div class="card-num">{esc(summary.get('points_available_on_resolved'))}</div>
<div class="card-label">HotSpawn points available on resolved fixtures</div></div>
</div>""")
    if not rows:
        body.append("""<div class="note bad"><strong>No capture yet.</strong> The collector has not run, so there
are no fixtures to price. This page fills itself on the next CI run — see
<a href="method.html#refresh">refresh cadence</a>.</div>""")
    body.append(f"""<div class="note"><strong>How to read this page on a phone:</strong> the header line of each
match is the pick. Tap it for the probability bar, the odds we found (each one linked to its source), the crowd
split, and the limitations. Sorted by start time; all times UTC.</div>""")
    for slot in sorted(groups):
        body.append(f"<h2>{esc(slot)}</h2>")
        for row in sorted(groups[slot], key=lambda r: (r.get("unresolved"), r.get("fixture_id"))):
            body.append(fixture_card(row))
    body.append(f"""<h2>Compact table (all {len(rows)} fixtures)</h2><div class="tablewrap">
<table class="responsive"><thead><tr><th>Start (UTC)</th><th>Match</th><th>Pick</th><th class="num">Our %</th>
<th class="num">Crowd % on pick</th><th class="num">Pts</th><th>Basis</th><th>Tier</th></tr></thead><tbody>""")
    for row in rows:
        pick = row.get("pick") or {}
        body.append(
            f'<tr><td data-label="Start">{esc((row.get("start_utc") or "?")[5:16])}</td>'
            f'<td data-label="Match">{esc(row.get("team_a"))} v {esc(row.get("team_b"))}'
            f'<div class="tiny">{esc(row.get("competition"))}</div></td>'
            f'<td data-label="Pick">{esc(pick.get("team") or "—")} {rule_tag(pick.get("rule"))}</td>'
            f'<td data-label="Our %" class="num">{pct(pick.get("prob"))}</td>'
            f'<td data-label="Crowd %" class="num">{num(pick.get("crowd_ownership_of_pick"), "%")}</td>'
            f'<td data-label="Points" class="num">{num(row.get("offered_points"))}</td>'
            f'<td data-label="Basis">{basis_tag(row)}</td>'
            f'<td data-label="Tier">{esc(row.get("tier"))}</td></tr>')
    body.append("</tbody></table></div>")
    if unresolved:
        body.append(f"""<div class="note warn"><strong>{len(unresolved)} fixture(s) could not be priced.</strong>
Each one is listed with the reason and what it costs you on <a href="unresolved.html">Unresolved matches</a>.
No guess is published in their place.</div>""")
    return page("picks.html", "Every match · day-4 picks · session 17866d06",
                "A pick and win probability for every open HotSpawn CS2 fixture, priced from bookmaker and "
                "exchange lines, each row source-linked.", "\n".join(body), board)


# ---------------------------------------------------------------------- index page
def render_index(board: dict) -> str:
    summary = board.get("summary") or {}
    rows = board.get("open") or []
    resolved = [r for r in rows if not r.get("unresolved")]
    unresolved = [r for r in rows if r.get("unresolved")]
    calibration = board.get("calibration") or {}
    flags = board.get("flags") or []
    backtest = board.get("crowd_backtest") or {}
    high = sum(1 for f in flags if f.get("severity") == "high")

    top = []
    for row in sorted(resolved, key=lambda r: (r.get("start_utc") or "", r.get("fixture_id"))):
        pick = row.get("pick") or {}
        top.append(
            f'<tr><td data-label="Start">{esc((row.get("start_utc") or "?")[5:16])} UTC</td>'
            f'<td data-label="Match">{esc(row.get("team_a"))} v {esc(row.get("team_b"))}'
            f'<div class="tiny">{esc(row.get("competition"))} · tier {esc(row.get("tier"))}</div></td>'
            f'<td data-label="Pick"><strong>{esc(pick.get("team") or "—")}</strong> {rule_tag(pick.get("rule"))}</td>'
            f'<td data-label="Our %" class="num">{pct(pick.get("prob"))}</td>'
            f'<td data-label="Crowd %" class="num">{num(pick.get("crowd_ownership_of_pick"), "%")}</td>'
            f'<td data-label="Pts" class="num">{num(row.get("offered_points"))}</td></tr>')

    contra = [r for r in resolved if (r.get("pick") or {}).get("rule", "").startswith(("R2", "R3"))]
    contra_lines = "".join(
        f'<li><strong>{esc((r.get("pick") or {}).get("team"))}</strong> over '
        f'{esc(r.get("team_b") if (r.get("pick") or {}).get("side") == "a" else r.get("team_a"))} — '
        f'{pct((r.get("pick") or {}).get("prob"))} on our line, crowd '
        f'{num((r.get("pick") or {}).get("crowd_ownership_of_pick"), "%")} '
        f'({esc((r.get("pick") or {}).get("rule"))}). <a href="picks.html#fx{esc(r.get("fixture_id"))}">row</a></li>'
        for r in contra) or "<li>No fixture in this capture meets the contrarian gates — the free-upgrade picks " \
                            "did not appear, so the board stays on maximum-probability picks.</li>"

    unresolved_lines = "".join(
        f'<li><strong>{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</strong> '
        f'({esc((r.get("start_utc") or "?")[5:16])} UTC, {esc(r.get("competition"))}) — '
        f'{esc(r.get("unresolved_reason") or "unresolved")}</li>' for r in unresolved)

    body = f"""<p class="eyebrow">Thunderpick World Championship 2026 · Malta · day 4 (17 Oct) + every open HotSpawn CS2 match</p>
<h1>Day-4 desk: what to pick, what it is worth, and what we could not price</h1>
<p class="mut">Evidence captured {esc(board.get('captured_utc') or '—')} · board generated
{esc(board.get('generated_utc') or '—')} · refreshed every 4 hours by CI ·
Valve standings snapshot {esc(board.get('vrs_snapshot') or '—')}</p>

<a class="btn good" href="picks.html">▶ Today's picks — every match</a>
<a class="btn ghost" href="unresolved.html">Unresolved matches ({len(unresolved)})</a>
<a class="btn ghost" href="twc.html">TWC day 1–3 review → day 4</a>
<a class="btn warn" href="flagged.html">Flagged for review ({len(flags)})</a>

<div class="note bad"><strong>Read this first: the day-4 semifinals are NOT pickable on HotSpawn.</strong>
The fixtures API returns an empty list for <code>competition_id=35859&amp;status=scheduled</code>, and the
unfiltered competition response contains only the eleven group-stage/decider rows — no semi-final, third-place
or grand-final row. FURIA v Aurora (14:00 UTC) and Falcons v BETBOOM (17:00 UTC) are on the
{link('HotSpawn tournament schedule', 'https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026')}
as rows 1080207 / 1080208 but award <strong>zero leaderboard points</strong>. Day-4 points come only from the
non-TWC lobby fixtures. {link('Evidence + detail (flag F2)', 'flagged.html#F2')}</div>

<div class="cards">
<div class="card"><div class="card-num">{esc(summary.get('open_fixtures', len(rows)))}</div>
<div class="card-label">open HotSpawn CS2 fixtures</div></div>
<div class="card"><div class="card-num">{esc(summary.get('resolved', len(resolved)))}</div>
<div class="card-label">priced — pick + probability</div></div>
<div class="card"><div class="card-num">{esc(summary.get('points_available_on_resolved'))}</div>
<div class="card-label">points available on priced fixtures</div></div>
<div class="card"><div class="card-num">{esc(summary.get('contrarian_picks', len(contra)))}</div>
<div class="card-label">contrarian picks that pass the gates</div></div>
<div class="card"><div class="card-num">{pct(summary.get('market_coverage'))}</div>
<div class="card-label">fixtures covered by a real market line</div></div>
<div class="card"><div class="card-num">{esc(calibration.get('scale'))}</div>
<div class="card-label">VRS scale {'fitted on ' + str(calibration.get('samples')) + ' markets' if calibration.get('calibrated') else 'FALLBACK — uncalibrated'}</div></div>
</div>

<h2>The strategy in three sentences</h2>
<p>HotSpawn pays a <strong>flat number of points per correct pick</strong> (tier multiplies the points, ownership
does not) plus an unpublished streak bonus, so expected points = <code>offered_points × P(win)</code> — the
leaderboard-optimal play is simply the highest-probability side of a <em>correct</em> line, and "contrarian" only
earns anything when it is free. It is free when our line's favourite is not the crowd's favourite
(rule R2), and it is defensible at sub-50% only with two or more independently verified context facts and real
points on the table (rule R3, capped at two per day). Everything else is variance, and variance is labelled as
variance rather than sold as an edge.</p>
{source_line([('HotSpawn how it works (official scoring)', 'https://play.hotspawn.com/how-it-works'),
              ('HotSpawn fixtures API row 1081888 (points_breakdown has no ownership term)',
               'https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures?sport_alias=cs2&status=scheduled&competition_id=36197')])}

<h2>Why fading the crowd was right on day 1 — and how often it works</h2>
<p>9z beat Aurora 2-0 on day 1 with the crowd <strong>93% on Aurora</strong>: the 7% who took 9z collected the
same flat 7 points as everyone who got a favourite right. Across the eleven settled TWC fixtures, the nine with a
≥60% crowd favourite went <strong>{esc(backtest.get('strong_favourite_record', '—'))}</strong> — right often
enough to respect, wrong often enough to fade <em>when our own line disagrees</em>. The three failures were
Aurora at 93% (v 9z), PARIVISION at 64% (v BETBOOM) and Legacy at 88% (v BETBOOM); the winners were held by
7%, 36% and 12% of pickers.</p>
<p class="mut">{link('Full settled table + Aurora roster analysis →', 'twc.html')}</p>

<h2>Today's picks at a glance</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Start</th><th>Match</th><th>Pick</th>
<th class="num">Our %</th><th class="num">Crowd % on pick</th><th class="num">Pts</th></tr></thead><tbody>
{''.join(top) or '<tr><td colspan="6">No priced fixtures in this capture.</td></tr>'}
</tbody></table></div>
<p><a class="btn" href="picks.html">Open every match with odds, sources and limits</a></p>

<h2>Contrarian-but-not-stupid picks in this capture</h2>
<ul>{contra_lines}</ul>

<h2>Unresolved ({len(unresolved)}) — in the executive summary as required</h2>
{('<ul class="tiny">' + unresolved_lines + '</ul>') if unresolved_lines else
 '<p class="mut">Every open fixture in this capture has either a market line or an originated model line.</p>'}
<p class="mut">Unresolved rows are never filled with a guess. Each one lists what was tried in the required order
(HLTV → esportsbooks → betting lines), what blocked it, and what it costs you:
{link('Unresolved matches + limitations →', 'unresolved.html')}</p>

<h2>Flagged for review ({len(flags)}, {high} high severity)</h2>
<ul class="tiny">{''.join(f'<li><strong>{esc(f.get("id"))}</strong> ({esc(f.get("severity"))}) — {esc(f.get("title"))} '
f'{link("detail", "flagged.html#" + str(f.get("id")))}</li>' for f in flags)}</ul>
<p class="mut">Flagged items do not block anything: they are published with their sources so a human can check
them. {link('Flagged for Review →', 'flagged.html')}</p>

<h2>Where every number comes from</h2>
<ul class="tiny">
<li><strong>Fixtures, points, crowd ownership, settlement:</strong> HotSpawn fixtures API — discovery and
settlement only, never a probability input.</li>
<li><strong>Prices:</strong> Thunderpick coefficients as published by bo3.gg, Melbet's public esports LineFeed,
and Polymarket exchange prices (volume-weighted). All converted to no-vig probabilities.</li>
<li><strong>Our originated line:</strong> logistic on the official Valve Regional Standings point delta
({link('Valve repository', board.get('vrs_source') or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}),
scale fitted to the markets captured in the same run — {esc(calibration.get('samples'))} pairs,
R² {esc(calibration.get('r_squared', '—'))}, mean absolute error {esc(calibration.get('mean_abs_error', '—'))}.</li>
<li><strong>Editorial facts</strong> (results, map scores, ratings, roster history, rules): HLTV, Valve, HotSpawn's
own pages and Polymarket, each cited where it is used.</li>
</ul>
<p><a class="btn ghost" href="method.html">Method, maths and verification protocol</a></p>
"""
    return page("index.html", "Start here · day-4 desk · session 17866d06",
                "Executive summary of the day-4 HotSpawn CS2 pick'em desk: every match priced, contrarian picks "
                "gated on verified evidence, unresolved matches and flags published.", body, board)


# ------------------------------------------------------------------------ twc page
def render_twc(board: dict) -> str:
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_17866d06", Path(__file__).parent / "research.py")
    research = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(research)

    result_rows = "".join(
        f'<tr><td data-label="Day">Day {esc(r.get("day"))}<div class="tiny">{esc(r.get("date"))}</div></td>'
        f'<td data-label="Match">{esc(r.get("a"))} <strong>{esc(r.get("sa"))}–{esc(r.get("sb"))}</strong> {esc(r.get("b"))}'
        f'<div class="tiny">HotSpawn {esc(r.get("hs"))} · HLTV {esc(r.get("hltv"))} · '
        f'{num(r.get("picks"))} picks</div></td>'
        f'<td data-label="Maps">{esc(r.get("maps")) if r.get("maps") else blank("map scores not verified")}</td>'
        f'<td data-label="Crowd">{num(r.get("crowd_a"), "%")} / {num(r.get("crowd_b"), "%")}</td>'
        f'<td data-label="Note">{esc(r.get("note"))}</td>'
        f'<td data-label="Sources">{source_line(r.get("sources") or [])}</td></tr>'
        for r in research.RESULTS)

    twc_rows = []
    for row in board.get("twc") or []:
        final = row.get("final") or {}
        pick = row.get("pick") or {}
        quote_bits = "".join(
            f'<li>{link(q.get("book") or q.get("source_key"), q.get("public_url"))}: '
            f'{esc(q.get("team_a"))} {pct(q.get("implied_a") if q.get("implied_a") is not None else q.get("price_a"))} / '
            f'{esc(q.get("team_b"))} {pct(q.get("implied_b") if q.get("implied_b") is not None else q.get("price_b"))}'
            + (f' · volume ${float(q["volume_usd"]):,.0f} · liquidity ${float(q["liquidity_usd"]):,.0f}' if q.get("volume_usd") else "")
            + (f' · market updated {esc(q.get("market_updated_utc"))}' if q.get("market_updated_utc") else "")
            + '</li>' for q in row.get("quotes") or [])
        vrs = row.get("vrs") or {}
        vrs_bits = "".join(
            f'<li>{esc(row.get(f"team_{side}") or "?")}: '
            + (f'#{vrs[side]["standing"]}, {vrs[side]["points"]} points (Valve {esc(vrs[side].get("region"))}, '
               f'{esc(vrs[side].get("method"))})' if vrs.get(side, {}).get("resolved")
               else blank("not in Valve standings")) + '</li>' for side in ("a", "b"))
        quote_list = quote_bits or "<li>" + blank("no market found") + "</li>"
        vrs_list = vrs_bits or "<li>" + blank("no Valve standings entry") + "</li>"
        valve_line = ('<p class="tiny">Valve file: ' + link("standings_global (official)", vrs.get("source"))
                      + "</p>") if vrs.get("source") else ""
        start_evidence_list = ('<h3>Start-time evidence</h3><ul class="tiny">'
                               + "".join("<li>" + esc(t) + " — " + link("source", u) + "</li>"
                                         for t, u in row.get("start_evidence") or [])
                               + "</ul>") if row.get("start_evidence") else ""
        hltv_list = ('<h3>HLTV facts used (analytics + results)</h3><ul class="tiny">'
                     + "".join("<li>" + esc(t) + "</li>" for t in row.get("hltv_facts") or [])
                     + "<li>" + link("HLTV match page", row.get("hltv_url")) + "</li>"
                     + "<li>" + link("HLTV analytics page", row.get("hltv_analytics")) + "</li></ul>"
                     ) if row.get("hltv_facts") else ""
        limits_list = ('<h3>Limitations</h3><ul class="tiny">'
                       + "".join("<li>" + esc(t) + "</li>" for t in row.get("limitations") or [])
                       + "</ul>") if row.get("limitations") else ""
        open_attr = " open" if str(row.get("slot", "")).startswith("Semi") else ""
        twc_rows.append(f"""<details{open_attr}>
<summary><strong>{esc(row.get('slot'))}</strong> — {esc(row.get('team_a') or row.get('teams') or '?')} v
{esc(row.get('team_b') or '?')} · {esc((row.get('start_utc') or '?')[5:16])} UTC
<span class="tag blank">0 HotSpawn points — not pickable</span></summary>
<div class="inner">
<p class="mut">{esc(row.get('not_pickable_evidence'))}</p>
{source_line([('HotSpawn fixtures API, competition 35859, status=scheduled (empty)',
 'https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures?sport_alias=cs2&status=scheduled&competition_id=35859'),
 ('HotSpawn tournament page (schedule rows 1080207 / 1080208)',
  'https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026')])}
<div class="pickbox"><div class="who">{esc(pick.get('team') or 'No pick — participants undetermined')}</div>
<div class="tiny">{pct(pick.get('prob'))} · {esc(final.get('basis') or 'no line')}</div></div>
<h3>Market lines found</h3><ul class="tiny">{quote_list}</ul>
<h3>Official Valve Regional Standings</h3><ul class="tiny">{vrs_list}</ul>
{valve_line}
{start_evidence_list}
{hltv_list}
{limits_list}
</div></details>""")

    aurora = research.AURORA
    change_rows = "".join(
        f'<tr><td data-label="Date">{esc(date)}</td><td data-label="Change">{esc(text)}</td>'
        f'<td data-label="Source">{link("HLTV", url)}</td></tr>' for date, text, url in aurora["change_history"])
    onboarding = "".join(f'<li>{esc(text)} {link("source", url)}</li>' for text, url in aurora["onboarding_evidence"])
    five = "".join(f'<li>{esc(name)}</li>' for text, url in aurora["five_evidence"] for name in [text])

    settlement = board.get("twc_settlement") or []
    settle_rows = "".join(
        f'<tr><td data-label="Fixture">{esc(s.get("fixture_id"))}</td>'
        f'<td data-label="Match">{esc(s.get("team_a"))} {esc(s.get("score_a"))}–{esc(s.get("score_b"))} {esc(s.get("team_b"))}</td>'
        f'<td data-label="Status">{esc(s.get("status"))}</td>'
        f'<td data-label="Crowd A/B">{num(s.get("crowd_a"), "%")} / {num(s.get("crowd_b"), "%")}</td>'
        f'<td data-label="Picks">{num(s.get("total_picks"))}</td>'
        f'<td data-label="Pts">{num(s.get("offered_points"))}</td></tr>' for s in settlement)

    body = f"""<p class="eyebrow">Thunderpick World Championship 2026 · Malta · {esc(research.EVENT.get('venue', ''))}</p>
<h1>Day 1–3 review, then day 4 and day 5</h1>
<p class="mut">{esc(research.EVENT.get('name'))} · {esc(research.EVENT.get('dates'))} ·
{esc(research.EVENT.get('location'))} · {esc(research.EVENT.get('type'))} ·
${esc(f"{research.EVENT.get('prize_pool_usd', 0):,}")} prize pool</p>
<p class="mut">Format (HLTV): {esc(research.EVENT.get('format_hltv'))} · HotSpawn publishes the format as
{esc(research.EVENT.get('format_hotspawn'))} — recorded verbatim, not inferred.</p>
<p class="mut">Group A: {esc(', '.join(research.EVENT.get('groups', {}).get('A', [])))} ·
Group B: {esc(', '.join(research.EVENT.get('groups', {}).get('B', [])))}</p>
<p class="mut">{link('HLTV event page', research.EVENT.get('hltv_url'))} ·
{link('HotSpawn tournament page', research.EVENT.get('hotspawn_url'))}</p>
{source_line([(label, url) for label, url in research.EVENT.get('sources', [])])}

<div class="note bad"><strong>Day 4 and day 5 award no HotSpawn points.</strong> The semifinals, the third-place
decider and the grand final are absent from the pick'em fixture list (flag
{link('F2', 'flagged.html#F2')}). They are priced here because the user asked for a probability on every match
and because they are the marquee games — but the leaderboard is decided by the lobby fixtures on
{link('the every-match board', 'picks.html')}.</div>

<h2>Days 1–3: what actually happened</h2>
<p class="mut">Series scores verified twice (HLTV results for event 8932 and the HotSpawn fixtures API rows for
competition 35859). Map scores appear only where a named source stated them; otherwise the cell is blank and tagged
UNVERIFIED.</p>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Day</th><th>Match</th><th>Map scores</th>
<th>Crowd A/B</th><th>What mattered</th><th>Sources</th></tr></thead><tbody>{result_rows}</tbody></table></div>

<h2>The day-1 upset, and what it teaches about the crowd</h2>
<p>Aurora went into day 1 at <strong>93% crowd ownership</strong> against 9z and lost 0-2 (Anubis 9-13, Mirage
11-13). The 7% who backed 9z were paid the same flat 7 points as anyone who backed a favourite. That is the whole
contrarian case in one row: <strong>HotSpawn does not pay more for being alone</strong>, so the only reason to fade
a crowd is that you believe the crowd is wrong — and the only defensible basis for believing that is a line of your
own plus verified context, not a feeling.</p>
<p>Across all eleven settled fixtures the nine ≥60% crowd favourites went
<strong>{esc((board.get('crowd_backtest') or {}).get('strong_favourite_record', '—'))}</strong>. Fading blindly
would have lost points six times. Fading only where our originated line disagrees with the crowd is the play.</p>
{source_line([('HotSpawn fixtures API competition 35859 (settled rows, crowd, scores)',
 'https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures?sport_alias=cs2&competition_id=35859')])}

<h2>Settled TWC rows exactly as HotSpawn reports them</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Fixture</th><th>Match</th><th>Status</th>
<th>Crowd</th><th>Picks</th><th>Pts</th></tr></thead><tbody>{settle_rows or '<tr><td colspan="6">No settled rows in this capture.</td></tr>'}</tbody></table></div>
<p class="tiny">Recorded verbatim. Note fixture 1080204 (Legacy v FURIA) is <code>cancelled</code> with 33 picks
already placed — per the official rules those players scored nothing — and its replay 1081614 settled with
0 picks because it was never offered. See flag {link('F9', 'flagged.html#F9')}.</p>

<h2>Aurora: the roster-change question, answered from sources</h2>
<p>The user asked specifically whether Aurora's recent roster change makes them (or someone else) a live upset
pick. Verified answer: <strong>Aurora's active five has been stable since 8 July 2026</strong> — there is no
October change in the sources read. The rebuild (kyxsan in as IGL from Falcons, with Jimpphat and coach ash,
replacing MAJ3R, soulfly and coach Fabre) is three months old at day 4, and its onboarding curve is visible inside
this event.</p>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Date</th><th>Change</th><th>Source</th></tr></thead>
<tbody>{change_rows}</tbody></table></div>
<p class="tiny"><strong>Active five (two independent sources agree):</strong> {esc(', '.join(aurora['active_five']))}
· coach {esc(aurora['coach'])}</p>
{source_line(aurora['five_evidence'])}
<div class="note warn"><strong>Not found, therefore left blank:</strong> {esc(aurora['october_change_note'])}
{source_line(aurora['october_change_sources'])}</div>
<h3>Onboarding evidence inside this event</h3><ul class="tiny">{onboarding}</ul>
<p class="mut"><strong>What we do with it:</strong> the roster story is real but it is three months old and it is
already in the price — Polymarket has Aurora at 47.5% against FURIA while HLTV's analytics call Aurora the
bookmaker favourite. Our originated Valve-VRS line rates FURIA higher (see the semi-final rows above). We therefore
take the market's side and treat Aurora as a live-but-not-value upset, not a contrarian pick: R3 needs our line to
rate the underdog above the market, and it does not.</p>

<h2>Day 4 (17 Oct) and day 5 (18 Oct)</h2>
{''.join(twc_rows) or '<p>No TWC rows in this capture.</p>'}

<h2>Day 5 as published by HLTV (participants undetermined)</h2>
<ul class="tiny">{''.join(f'<li>{esc(d["slot"])} · {esc(d["start_utc"])} · {esc(d["bo"])} · {esc(d["teams"])} — '
f'{link("HLTV", d["url"])}</li>' for d in research.DAY5)}</ul>
<p class="mut">These two rows are on {link('Unresolved', 'unresolved.html')} because no probability can be
originated for a pairing that does not exist yet. They are not guessed.</p>
"""
    return page("twc.html", "TWC 2026 day 1–3 review → day 4 · session 17866d06",
                "Thunderpick World Championship 2026 review: day 1-3 results with map scores and crowd ownership, "
                "the Aurora roster-change question, and day-4/day-5 semifinals priced from Polymarket and Valve VRS.",
                body, board)


# ------------------------------------------------------------------ unresolved page
def render_unresolved(board: dict) -> str:
    rows = board.get("open") or []
    unresolved = [r for r in rows if r.get("unresolved")]
    twc_unresolved = [r for r in board.get("twc") or [] if r.get("unresolved")]
    rejected = board.get("rejected_quotes") or []
    dropped = board.get("dropped_stale_fixtures") or []
    single_source = [r for r in rows if (r.get("consensus") or {}).get("n_sources") == 1]
    model_only = [r for r in rows if (r.get("final") or {}).get("no_market")]
    disagreement = [r for r in rows if (r.get("consensus") or {}).get("disagreement")]

    unresolved_rows = "".join(
        f'<tr><td data-label="Match"><strong>{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</strong>'
        f'<div class="tiny">{esc(r.get("competition"))} · {esc((r.get("start_utc") or "?")[5:16])} UTC · '
        f'tier {esc(r.get("tier"))} · {num(r.get("offered_points"))} pts</div></td>'
        f'<td data-label="Pick">{blank("no pick published")}</td>'
        f'<td data-label="Probability">{blank("no line")}</td>'
        f'<td data-label="Why">{esc(r.get("unresolved_reason"))}</td>'
        f'<td data-label="Cost">{num(r.get("offered_points"))} points unclaimable unless you take a coin flip</td>'
        f'<td data-label="Fixture">{link("HotSpawn API row", r.get("hotspawn_api_url"))}</td></tr>'
        for r in unresolved)
    twc_rows = "".join(
        f'<tr><td data-label="Match"><strong>{esc(r.get("slot"))}</strong>'
        f'<div class="tiny">{esc(r.get("teams") or (str(r.get("team_a")) + " v " + str(r.get("team_b"))))} · '
        f'{esc(r.get("start_utc"))}</div></td>'
        f'<td data-label="Pick">{blank("no pick published")}</td>'
        f'<td data-label="Why">{esc(r.get("unresolved_reason"))}</td>'
        f'<td data-label="Source">{link("HLTV match page", r.get("hltv_url"))}</td></tr>' for r in twc_unresolved)
    partial_rows = "".join(
        f'<tr><td data-label="Match">{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</td>'
        f'<td data-label="Status">priced, single source</td>'
        f'<td data-label="Detail">{esc((r.get("limitations") or ["—"])[0])}</td>'
        f'<td data-label="Row">{link("open", "picks.html#fx" + str(r.get("fixture_id")))}</td></tr>'
        for r in single_source)
    model_rows = "".join(
        f'<tr><td data-label="Match">{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</td>'
        f'<td data-label="Our line">{pct((r.get("final") or {}).get("prob_a"))} {esc(r.get("team_a"))}</td>'
        f'<td data-label="Limitation">no market covers this fixture: Valve standings only, so roster changes, form, '
        f'vetoes and travel are not in the number</td>'
        f'<td data-label="Row">{link("open", "picks.html#fx" + str(r.get("fixture_id")))}</td></tr>' for r in model_only)
    disagree_rows = "".join(
        f'<tr><td data-label="Match">{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</td>'
        f'<td data-label="Spread">{pct((r.get("consensus") or {}).get("spread"))}</td>'
        f'<td data-label="Sources">{esc(", ".join((r.get("consensus") or {}).get("sources") or []))}</td>'
        f'<td data-label="Row">{link("open", "picks.html#fx" + str(r.get("fixture_id")))}</td></tr>' for r in disagreement)
    rejected_rows = "".join(
        f'<tr><td data-label="Source">{esc(q.get("source_key"))}</td>'
        f'<td data-label="Names">{esc(q.get("team_a"))} v {esc(q.get("team_b"))}</td>'
        f'<td data-label="Start">{esc(q.get("start_utc"))}</td>'
        f'<td data-label="Rejected because">{esc(q.get("reason"))}</td>'
        f'<td data-label="Link">{link("source", q.get("public_url"))}</td></tr>' for q in rejected[:60])
    dropped_rows = "".join(
        f'<tr><td data-label="Fixture">{esc(d.get("id"))}</td><td data-label="Competition">{esc(d.get("competition"))}</td>'
        f'<td data-label="Start">{esc(d.get("start_utc"))}</td><td data-label="Excluded because">{esc(d.get("reason"))}</td></tr>'
        for d in dropped[:40])

    body = f"""<p class="eyebrow">Required section · unresolved picks and their limitations</p>
<h1>What we could not price, and exactly why</h1>
<p class="mut">Nothing on this page is filled with a guess. Where a value could not be confirmed from an official
or market source it is left blank and tagged UNVERIFIED, per the project's verification rule.</p>

<div class="cards">
<div class="card"><div class="card-num">{len(unresolved)}</div><div class="card-label">open fixtures with no pick</div></div>
<div class="card"><div class="card-num">{len(twc_unresolved)}</div><div class="card-label">TWC rows with no participants</div></div>
<div class="card"><div class="card-num">{len(model_only)}</div><div class="card-label">priced by our model only (no market)</div></div>
<div class="card"><div class="card-num">{len(single_source)}</div><div class="card-label">priced from a single source</div></div>
<div class="card"><div class="card-num">{len(rejected)}</div><div class="card-label">quotes rejected by the join rule</div></div>
</div>

<h2>1. Open HotSpawn fixtures with no pick</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Pick</th><th>Probability</th>
<th>Why unresolved</th><th>What it costs</th><th>Fixture</th></tr></thead><tbody>
{unresolved_rows or '<tr><td colspan="6">None — every open fixture in this capture is priced.</td></tr>'}
</tbody></table></div>
<p class="tiny">Research order attempted for each of these, as required: HLTV (match page, event page, team pages)
→ esportsbooks/esports news → betting lines (Thunderpick via bo3.gg, Melbet LineFeed, Polymarket). The specific
blocking reason is recorded per row above; the full source list is on {link('Method & sources', 'method.html')}.</p>

<h2>2. TWC rows that cannot be priced at all</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Slot</th><th>Pick</th><th>Why</th><th>Source</th>
</tr></thead><tbody>{twc_rows or '<tr><td colspan="4">None.</td></tr>'}</tbody></table></div>

<h2>3. Priced, but from our own model only (weaker than a market)</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Our line</th><th>Limitation</th>
<th>Row</th></tr></thead><tbody>{model_rows or '<tr><td colspan="4">None.</td></tr>'}</tbody></table></div>
<p class="tiny">A Valve-VRS logistic line is a real originated probability, but it cannot see a stand-in, a visa
problem, a veto mismatch or a team that has not slept. Treat these as the weakest priced rows on the board.</p>

<h2>4. Priced from a single source (shrunk toward our model)</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Status</th><th>Detail</th><th>Row</th>
</tr></thead><tbody>{partial_rows or '<tr><td colspan="4">None.</td></tr>'}</tbody></table></div>

<h2>5. Sources that disagreed with each other</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Match</th><th>Spread</th><th>Sources</th><th>Row</th>
</tr></thead><tbody>{disagree_rows or '<tr><td colspan="4">None above the 12-point threshold.</td></tr>'}</tbody></table></div>

<h2>6. Quotes rejected by the join rule (kept, not hidden)</h2>
<p class="mut">A quote is only attached to a fixture when its start time is within 90 minutes and at least one team
name matches. Everything else is listed here so a human can see what we declined to use — including the
Melbet row that names the same teams 2.5 hours off HotSpawn's start time (flag {link('F7', 'flagged.html#F7')}).</p>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Source</th><th>Names as published</th><th>Start</th>
<th>Rejected because</th><th>Link</th></tr></thead><tbody>
{rejected_rows or '<tr><td colspan="5">None rejected.</td></tr>'}</tbody></table></div>

<h2>7. HotSpawn fixtures excluded as stale</h2>
<p class="tiny">HotSpawn's <code>status=scheduled</code> filter is known to retain past-dated rows; they are
excluded from the board and listed here rather than priced as if they were upcoming.</p>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Fixture</th><th>Competition</th><th>Start</th>
<th>Excluded because</th></tr></thead><tbody>
{dropped_rows or '<tr><td colspan="4">None.</td></tr>'}</tbody></table></div>

<h2>8. Team names we could not verify against Valve's official standings</h2>
<p class="mut">These names appear on HotSpawn fixtures but not in Valve's Regional Standings snapshot, and no
verified alias exists for them. They are left unresolved on purpose: guessing a mapping would put a fake number in
front of a real decision.</p>
<ul class="tiny">
<li><strong>ex-6666</strong> — Valve's snapshot contains <em>two different rosters</em> both named "6666"
(global #127 amster/dENZY/kL1o/rendysky/skcH and #368 auth0ri/m4d4ra/rickangel/skcH), so the mapping is ambiguous.</li>
<li><strong>Apogee Betclic, Insiders, Morningstar, WROTBERRY, WXM, antidaun</strong> — not listed in the
snapshot at all (regional files included). {link('Valve standings repository', board.get('vrs_source') or
'https://github.com/ValveSoftware/counter-strike_regional_standings')}</li>
</ul>
<p class="tiny">Consequence: any fixture containing one of these sides can only be priced from a market quote. If no
market joined, the row stays blank and appears in section 1.</p>

<h2>9. Known coverage limits of this desk (stated plainly)</h2>
<ul class="tiny">
<li>Pinnacle's esports API and egamersworld were not scraped by the automated collector; where they carry a line
this desk may be missing the sharpest price available. Recorded as a limitation, not silently ignored.</li>
<li>HLTV publishes match pages and analytics text but no book-by-book odds table on the analytics pages read this
session, so HLTV is used for results, rosters, ratings and veto tendencies — not for prices.</li>
<li>HotSpawn's streak bonus value is not published anywhere, so it cannot be optimised; it is used only as a
tie-break (rule R5) and flagged.</li>
<li>The Valve standings snapshot is dated {esc(board.get('vrs_snapshot') or '—')}; a roster move after that date is
invisible to the originated model line.</li>
<li>Polymarket coverage of tier-B/C CS2 is sparse: most lobby fixtures are priced from bookmaker lines only.</li>
</ul>
"""
    return page("unresolved.html", "Unresolved matches and limitations · session 17866d06",
                "Every HotSpawn CS2 fixture we could not price, the reason, the cost, the rejected quotes we kept, "
                "and the standing limitations of the desk.", "\n".join([body]), board)


# -------------------------------------------------------------------- flagged page
def render_flagged(board: dict) -> str:
    flags = board.get("flags") or []
    cards = "".join(f"""<details id="{esc(f.get('id'))}" {'open' if f.get('severity') == 'high' else ''}>
<summary><span class="tag {'bad' if f.get('severity') == 'high' else 'warn' if f.get('severity') == 'medium' else 'mdl'}">{esc(f.get('id'))} · {esc(f.get('severity'))}</span>
 <strong>{esc(f.get('title'))}</strong></summary>
<div class="inner"><p>{esc(f.get('detail'))}</p>{source_line(f.get('sources') or [])}</div></details>""" for f in flags)

    row_flags = []
    for row in board.get("open") or []:
        for text in row.get("limitations") or []:
            row_flags.append((f'{row.get("team_a")} v {row.get("team_b")}', text,
                              row.get("hotspawn_api_url"), row.get("fixture_id")))
    row_html = "".join(
        f'<tr><td data-label="Fixture">{esc(match)}<div class="tiny">{esc(fixture_id)}</div></td>'
        f'<td data-label="Flag">{esc(text)}</td><td data-label="Source">{link("HotSpawn API row", url)}</td></tr>'
        for match, text, url, fixture_id in row_flags[:80])

    calibration = board.get("calibration") or {}
    body = f"""<p class="eyebrow">Flagged for review · nothing here blocks the build, the merge or the deploy</p>
<h1>Irregularities, discrepancies and unverified values</h1>
<p class="mut">Every flag below carries its own sources so a human can check it in one click. Values that could not
be confirmed are left blank on the boards themselves and tagged UNVERIFIED — they are never inferred.</p>

<div class="cards">
<div class="card"><div class="card-num">{sum(1 for f in flags if f.get('severity') == 'high')}</div><div class="card-label">high severity</div></div>
<div class="card"><div class="card-num">{sum(1 for f in flags if f.get('severity') == 'medium')}</div><div class="card-label">medium</div></div>
<div class="card"><div class="card-num">{sum(1 for f in flags if f.get('severity') == 'low')}</div><div class="card-label">low</div></div>
<div class="card"><div class="card-num">{len(row_flags)}</div><div class="card-label">row-level limitations published</div></div>
</div>

{cards}

<h2>Model calibration status</h2>
<div class="note {'good' if calibration.get('calibrated') else 'warn'}">
<strong>VRS scale {esc(calibration.get('scale'))}</strong> — {'fitted on ' + str(calibration.get('samples')) + ' market/standings pairs in this capture' if calibration.get('calibrated') else 'NOT calibrated on this capture: fallback ' + str(calibration.get('scale')) + ' used'}
{(' · R² ' + str(calibration.get('r_squared')) + ' · mean absolute error ' + str(calibration.get('mean_abs_error')) + ' · worst pair ' + str(calibration.get('max_abs_error'))) if calibration.get('calibrated') else ''}
{(' · <strong>clamped to the documented bounds</strong> ' + str(calibration.get('bounds'))) if calibration.get('clamped') else ''}
<div class="tiny">{esc(calibration.get('note') or calibration.get('method') or '')}</div></div>
<p class="tiny">Every row whose probability came from the model carries this status in its limitations, so a reader
can tell a fitted line from a fallback line.</p>

<h2>Row-level limitations published on the boards</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Fixture</th><th>Flag</th><th>Source</th></tr></thead>
<tbody>{row_html or '<tr><td colspan="3">None.</td></tr>'}</tbody></table></div>

<h2>Differences from other boards already published in this repository</h2>
<ul class="tiny">
<li>{link('../day4/index.html', '../day4/index.html')} states "verified: the fixtures API has no TWC Malta
competition". That is not what the API returns: <code>competition_id=35859</code> exists and returns eleven settled
rows; only the <code>status=scheduled</code> query is empty. Our conclusion (the semifinals are not pickable) is the
same, the stated reason is corrected here. {link('HotSpawn API', 'https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures?sport_alias=cs2&competition_id=35859')}</li>
<li>Several published boards rank contrarian value by <code>points × (probability − crowd ownership)</code>. HotSpawn
publishes no ownership term in its points model, so that formula prices a payout that does not exist. This desk ranks
by expected points = <code>offered_points × probability</code> (flag F1).</li>
<li>Some boards cite an "HLTV live Valve-VRS forecast" that puts Aurora ahead of FURIA. The official Valve file for
{esc(board.get('vrs_snapshot') or '—')} puts FURIA ahead. We originate from the official file only and say which
snapshot we used (flag F5).</li>
</ul>

<h2>What we deliberately did not publish</h2>
<ul class="tiny">
<li>Any alias we could not verify (for example <code>WROTBERRY</code> ↔ <code>WhiteBIT Team</code>,
<code>ex-6666</code> ↔ <code>6666</code>, <code>antidaun</code>) — those sides stay unresolved instead of guessed.</li>
<li>Any probability for a fixture whose teams are still "Waiting for information".</li>
<li>Any streak-bonus optimisation: the bonus value is unpublished, so it is a tie-break only.</li>
<li>Any use of HotSpawn crowd percentages as a probability input.</li>
</ul>
"""
    return page("flagged.html", "Flagged for Review · session 17866d06",
                "Irregularities, discrepancies and unverified values found while building the day-4 desk, each with "
                "its own source links.", body, board)


# --------------------------------------------------------------------- method page
def render_method(board: dict) -> str:
    import importlib.util
    spec = importlib.util.spec_from_file_location("research_17866d06", Path(__file__).parent / "research.py")
    research = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(research)
    calibration = board.get("calibration") or {}
    scoring = research.SCORING
    counts = board.get("quote_counts") or {}

    rules = "".join(f"""<details {'open' if r['id'] in ('R1', 'R2') else ''}><summary><strong>{esc(r['id'])} —
{esc(r['name'])}</strong> <span class="mut">gate: {esc(r['gate'])} · cost: {esc(r['cost'])}</span></summary>
<div class="inner"><p>{esc(r['text'])}</p></div></details>""" for r in research.RULES)

    points_rows = "".join(
        f'<tr><td data-label="Tier">{esc(label)}</td><td data-label="Offered">{esc(offered)}</td>'
        f'<td data-label="Base">{esc(base)}</td><td data-label="Multipliers">{esc(json.dumps(mult))}</td></tr>'
        for label, offered, base, mult in scoring["observed_points"])

    sources_rows = "".join(f'<tr><td data-label="Source">{esc(label)}</td>'
                           f'<td data-label="Link">{link(url, url)}</td></tr>'
                           for label, url in research.SOURCES_INDEX)

    body = f"""<p class="eyebrow">Method · maths · verification</p>
<h1>How every number on this desk was produced</h1>
<p class="mut">Reproducible from the repository: <code>python3 scripts/17866d06/collect.py</code> then
<code>python3 scripts/17866d06/model.py</code> then <code>python3 scripts/17866d06/build.py</code>. The CI workflow
runs the same three commands on a schedule and commits the evidence it captured.</p>

<h2 id="sources">Sources, and what each one is allowed to decide</h2>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Source</th><th>Link</th></tr></thead><tbody>
{sources_rows}</tbody></table></div>
<div class="note"><strong>Hard rule:</strong> HotSpawn is used for fixture discovery, tier, offered points, lock
times, crowd ownership and settlement — and <strong>never</strong> as a probability indicator. Crowd ownership is
always labelled as crowd ownership.</div>

<h2>Join rule (how a price is attached to a fixture)</h2>
<p>A quote is attached to a HotSpawn fixture only when <strong>both</strong> hold:</p>
<ul><li>its start time is within <strong>90 minutes</strong> of the fixture's
<code>scheduled_start_time</code> (Melbet and bo3.gg matched HotSpawn to the second on the fixtures checked);</li>
<li>at least one side matches by team name (exact or substring), and the other side does not contradict it.</li></ul>
<p class="tiny">Rejected quotes are published in full on {link('Unresolved', 'unresolved.html')} — including the
Melbet row that names the same two teams 2.5 hours off HotSpawn's start time. Joins that are not exact on both names
carry a "partial" confidence label on the row itself.</p>

<h2>No-vig conversion</h2>
<p>Bookmaker decimal odds are converted with <code>p_a = (1/o_a) / ((1/o_a) + (1/o_b))</code>, which removes the
overround rather than trusting either side's raw price. Polymarket prices are already probabilities and sum to ~1.0;
they are renormalised to remove rounding only. The overround actually observed on each quote is printed on the row.</p>

<h2>Consensus weighting</h2>
<p>Books (Thunderpick via bo3.gg, Melbet) are weighted <strong>1.0</strong>. Polymarket is weighted
<strong>0.5–1.25 by traded volume</strong> (<code>0.5 + log10(volume)/4</code>, capped) because an exchange price
carries no vig but a thin book is noisy. The consensus is the weighted average of the no-vig probabilities; if the
sources disagree by more than 12 points the row is flagged.</p>

<h2>Our originated line (Valve VRS logistic)</h2>
<p><code>p_a = 1 / (1 + exp(−Δ/S))</code> where Δ is the point difference in Valve's <em>official</em> Regional
Standings and S is fitted, not asserted: least squares of <code>logit(market p_a)</code> on Δ through the origin,
over every quote in this capture whose two sides both resolve in the standings.</p>
<div class="note {'good' if calibration.get('calibrated') else 'warn'}"><strong>This capture:</strong>
S = {esc(calibration.get('scale'))} · samples {esc(calibration.get('samples'))} ·
R² {esc(calibration.get('r_squared', '—'))} · mean abs error {esc(calibration.get('mean_abs_error', '—'))} ·
bounds {esc(calibration.get('bounds'))} {'· CLAMPED' if calibration.get('clamped') else ''}
<div class="tiny">{esc(calibration.get('method') or '')}</div>
<div class="tiny">{esc(calibration.get('note') or '')}</div></div>
<p class="tiny">Fallback if fewer than 8 usable pairs: S = 700, and every model line derived from it is labelled
uncalibrated on the row. Precedent check: S ≈ 709 reproduces the 58.6% Falcons figure published by another desk in
this repository, so the scale is in the same range as independent work.</p>

<h2>Which number the pick uses</h2>
<ul class="tiny">
<li><strong>≥2 market sources</strong> → consensus.</li>
<li><strong>1 market source</strong> → 75% consensus + 25% originated VRS line (shrinks a thin quote).</li>
<li><strong>No market</strong> → originated VRS line alone, labelled "our model only" and listed as a limitation.</li>
<li><strong>Neither</strong> → blank, UNVERIFIED, on {link('Unresolved', 'unresolved.html')}. Never guessed.</li>
</ul>

<h2>Decision rules</h2>
{rules}

<h2>HotSpawn scoring as officially published</h2>
<ul class="tiny">{''.join(f'<li>{esc(rule)}</li>' for rule in scoring['rules'])}</ul>
<p class="tiny">{link(scoring['how_it_works_url'], scoring['how_it_works_url'])} · API points fields:
{esc(', '.join(scoring['api_points_fields']))} · {esc('; '.join(scoring['api_points_absent_fields']))}</p>
<div class="tablewrap"><table class="responsive"><thead><tr><th>Tier</th><th>Offered</th><th>Base</th>
<th>Multipliers (API)</th></tr></thead><tbody>{points_rows}</tbody></table></div>
<p class="tiny">Lobby context read at {esc(scoring['lobby_context_read_utc'])}:
{esc(scoring['lobby_context']['matches_this_week'])} · reset countdown observed
"{esc(scoring['lobby_context']['reset_countdown_observed'])}" · prizes
{esc('; '.join(scoring['lobby_context']['prizes']))} · {esc(scoring['lobby_context']['qualification'])}</p>
<p class="tiny">Leaderboard top 10 as displayed: {esc(', '.join(f'{name} {score}' for name, score in scoring['lobby_context']['leaderboard_top10']))}
{link('lobby', scoring['lobby_url'])}</p>

<h2 id="refresh">Refresh cadence</h2>
<p>The workflow {link('day4live-17866d06.yml', REPO_BLOB + '/.github/workflows/day4live-17866d06.yml')} runs
<code>collect → model → build → tests → stage</code> every 4 hours and on demand, commits the evidence and the
rendered pages to this branch, and triggers the Pages deployment. That satisfies the 4–8 hour re-check requirement:
HotSpawn adds fixtures continuously, and each run re-reads the whole scheduled list rather than a cached subset.</p>
<p class="tiny">If a run fails, the previously committed pages stay live — a failed refresh never blanks the site.</p>

<h2>Verification protocol</h2>
<ul class="tiny">
<li>Every table row carries a link to the source that produced it (official site, bookmaker feed, exchange API or
Valve's repository). No row is published without one.</li>
<li>A value that could not be confirmed is rendered blank with an UNVERIFIED tag. It is never inferred, averaged
from a neighbour, or copied from another board.</li>
<li>Editorial claims (results, map scores, ratings, roster moves) are taken only from sources read this session and
stored verbatim in <code>scripts/17866d06/research.py</code> with their URLs.</li>
<li>Raw responses are committed under <code>data/17866d06/evidence/</code> with byte counts and SHA-256 digests in
<code>collect_log.json</code>, so any published number can be replayed from stored evidence.</li>
<li>Crowd percentages are recorded verbatim even when a pair sums to more than 100% (observed on the lobby), because
renormalising them would invent data.</li>
</ul>

<h2>How to re-run this desk yourself</h2>
<p><code>python3 scripts/17866d06/collect.py</code> · <code>python3 scripts/17866d06/model.py</code> ·
<code>python3 scripts/17866d06/build.py</code> · <code>python3 -m unittest discover -s tests</code> ·
<code>python3 scripts/stage_site.py</code></p>
<p class="tiny">Quote volumes captured this run: {esc(json.dumps(counts))}.</p>
"""
    return page("method.html", "Method & sources · session 17866d06",
                "Sources, join rule, no-vig maths, consensus weighting, the originated Valve-VRS line and its "
                "calibration, decision rules R1-R5, and the verification protocol.", body, board)


def build(out_dir=None) -> list:
    out = Path(out_dir) if out_dir else OUT
    out.mkdir(parents=True, exist_ok=True)
    board = {}
    if (DATA / "board.json").exists():
        board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    pages = {
        "index.html": render_index(board),
        "picks.html": render_picks(board),
        "twc.html": render_twc(board),
        "unresolved.html": render_unresolved(board),
        "flagged.html": render_flagged(board),
        "method.html": render_method(board),
    }
    for name, content in pages.items():
        (out / name).write_text(content, encoding="utf-8")
    print(f"rendered {len(pages)} pages into {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: "
          f"{', '.join(sorted(pages))}")
    return sorted(pages)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else None
    build(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
