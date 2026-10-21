#!/usr/bin/env python3
"""T-FULLCOV site renderer (session fe803b80). Writes the mobile-first ``board/`` section.

Pages
-----
board/index.html        executive summary: where the picks are, coverage KPIs, in-site links
board/picks.html        every open CS2 fixture with its pick, probability, basis and source links
board/lines.html        the external market quotes actually used, one row per price
board/tournaments.html  the same picks grouped by tournament
board/results.html      track record of published picks settled from HotSpawn final scores
board/flagged.html      everything flagged for review: alias joins, originated lines, gaps, failures
board/method.html       method, formulas, sources and limitations

Design rules: mobile-first single column, 16 px minimum text, 44 px tap targets, tables that turn
into cards below 700 px, no external fonts or scripts, no tracking. Every table row carries its
source link(s) or an explicit "unverified" marker.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "fe803b80"
OUT = ROOT / "board"

CSS = """
:root{--bg:#0f1420;--panel:#171e2e;--panel2:#1e2739;--ink:#eef2f8;--dim:#9aa6bd;--line:#2b3752;
--accent:#3ea6ff;--good:#31c48d;--warn:#f0b429;--bad:#f26d6d;--pick:#31c48d}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 14px 64px}
header.top{position:sticky;top:0;z-index:20;background:rgba(15,20,32,.97);border-bottom:1px solid var(--line);
backdrop-filter:blur(6px)}
header.top .inner{max-width:1080px;margin:0 auto;padding:10px 14px}
.brand{font-weight:700;letter-spacing:.2px;display:flex;align-items:center;gap:8px;font-size:15px}
.brand .dot{width:10px;height:10px;border-radius:50%;background:var(--good);display:inline-block}
nav.pages{display:flex;gap:6px;overflow-x:auto;margin-top:8px;padding-bottom:2px;scrollbar-width:none}
nav.pages::-webkit-scrollbar{display:none}
nav.pages a{flex:0 0 auto;padding:9px 12px;border:1px solid var(--line);border-radius:999px;
color:var(--ink);text-decoration:none;font-size:14px;background:var(--panel)}
nav.pages a[aria-current=page]{background:var(--accent);border-color:var(--accent);color:#06121f;font-weight:600}
h1{font-size:1.5rem;margin:18px 0 6px}
h2{font-size:1.15rem;margin:26px 0 8px}
h3{font-size:1rem;margin:18px 0 6px}
p.sub{color:var(--dim);margin:0 0 14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px}
.card .n{font-size:1.6rem;font-weight:700}
.card .l{color:var(--dim);font-size:.86rem}
.jump{display:grid;grid-template-columns:1fr;gap:10px;margin:14px 0}
@media(min-width:620px){.jump{grid-template-columns:1fr 1fr}}
.jump a{display:block;background:var(--panel);border:1px solid var(--line);border-radius:14px;
padding:14px;text-decoration:none;color:var(--ink)}
.jump a b{display:block;font-size:1.02rem;margin-bottom:4px}
.jump a span{color:var(--dim);font-size:.88rem}
.note{background:var(--panel2);border:1px solid var(--line);border-left:4px solid var(--warn);
border-radius:10px;padding:10px 12px;color:var(--ink);font-size:.94rem;margin:12px 0}
.note.info{border-left-color:var(--accent)}
.note.good{border-left-color:var(--good)}
.fixture{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;
margin:10px 0}
.fixture .meta{color:var(--dim);font-size:.82rem;display:flex;flex-wrap:wrap;gap:6px 10px}
.teams{display:flex;flex-direction:column;gap:8px;margin:10px 0}
.team{display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px;background:var(--panel2);
border:1px solid var(--line);border-radius:10px;padding:10px}
.team.win{border-color:var(--pick);box-shadow:inset 0 0 0 1px rgba(49,196,141,.35)}
.team .nm{font-weight:600;min-width:0;overflow-wrap:anywhere}
.team .pr{font-variant-numeric:tabular-nums;font-weight:700}
.badge{display:inline-block;font-size:.74rem;padding:3px 8px;border-radius:999px;border:1px solid var(--line);
color:var(--dim);background:var(--panel2);margin:2px 4px 2px 0;white-space:nowrap}
.badge.pick{background:rgba(49,196,141,.15);border-color:var(--pick);color:var(--pick);font-weight:600}
.badge.market{background:rgba(62,166,255,.15);border-color:var(--accent);color:var(--accent)}
.badge.model{background:rgba(240,180,41,.14);border-color:var(--warn);color:var(--warn)}
.badge.bad{background:rgba(242,109,109,.15);border-color:var(--bad);color:var(--bad)}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:.93rem}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.03em}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.src{font-size:.82rem;color:var(--dim);word-break:break-word}
.src a{color:var(--accent)}
details{margin:8px 0}
summary{cursor:pointer;color:var(--accent);padding:6px 0}
@media(max-width:700px){
table.resp thead{display:none}
table.resp tr{display:block;background:var(--panel);border:1px solid var(--line);border-radius:12px;
margin:0 0 10px;padding:8px 10px}
table.resp td{display:block;border:0;padding:4px 0}
table.resp td[data-l]::before{content:attr(data-l) ": ";color:var(--dim);font-size:.82rem}
}
footer{border-top:1px solid var(--line);margin-top:26px;padding-top:12px;color:var(--dim);font-size:.84rem}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:.9rem}
.kv div:nth-child(odd){color:var(--dim)}
ul.tight{margin:6px 0 6px 18px;padding:0}
ul.tight li{margin:4px 0}
code{background:var(--panel2);padding:1px 5px;border-radius:6px;font-size:.9em;word-break:break-word}
"""

PAGES = [("index.html", "Summary"), ("picks.html", "All picks"), ("lines.html", "Lines"),
         ("tournaments.html", "Tournaments"), ("unresolved.html", "Unresolved"),
         ("results.html", "Results"),
         ("flagged.html", "Flagged"), ("method.html", "Method")]

# How a number on a row was obtained, and what that method cannot do. Published on the unresolved
# page so a reviewer sees the limitation next to the number, not only in a footnote.
BOUND_BASES = {
    "vrs_floor_bound": "One-sided Valve VRS bound",
    "vrs_alias_candidate_bound": "Valve VRS bound through an unconfirmed alias",
    "vrs_alias_candidate": "Valve VRS line through an unconfirmed alias",
}
ORIGIN_BASES = {
    "valve_vrs": "Official Valve VRS rating model",
    "originated_elo": "This project's Elo over published bo3.gg results",
    "originated_rank": "bo3.gg published world ranking mapped to the Elo scale",
    "originated_hltv_rank": "HLTV published ranking mapped to the Elo scale",
}
BOUND_SET = tuple(BOUND_BASES)
ORIGIN_SET = tuple(ORIGIN_BASES)


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pct(v) -> str:
    return "—" if v is None else f"{float(v) * 100:.1f}%"


def fmt(iso) -> str:
    return "—" if not iso else str(iso).replace("T", " ").replace("Z", " UTC")


def basis_badge(row) -> str:
    line = row.get("line") or {}
    b = line.get("basis")
    if b == "market":
        return '<span class="badge market">market</span>'
    if b == "market+model":
        return '<span class="badge market">market+model</span>'
    if b == "model":
        origin = (row.get("model") or {}).get("basis")
        label = {"valve_vrs": "originated · Valve VRS",
                 "originated_elo": "originated · Elo (bo3.gg results)",
                 "originated_rank": "originated · bo3.gg ranking",
                 "originated_hltv_rank": "originated · HLTV ranking"}.get(
                     origin, "originated · ratings")
        if origin in BOUND_BASES:
            label = "bound · " + BOUND_BASES[origin].lower()
        return f'<span class="badge model">{esc(label)}</span>'
    return '<span class="badge bad">no source</span>'


def src_links(row) -> str:
    out = []
    for s in row.get("sources") or []:
        url = s.get("url")
        if url:
            out.append(f'<a href="{esc(url)}" rel="noopener">{esc(s.get("label"))}</a>'
                       f' <span class="src">read {esc(fmt(s.get("read_utc")))}</span>')
        else:
            out.append(f'{esc(s.get("label"))} <span class="src">(no URL published)</span>')
    if not out:
        out.append('<span class="badge bad">unverified — no source</span>')
    return "<br>".join(out)


def page(title: str, active: str, body: str, board: dict) -> str:
    nav = "".join(
        f'<a href="{esc(href)}"{" aria-current=page" if href == active else ""}>{esc(label)}</a>'
        for href, label in PAGES)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Full pick coverage (HotSpawn lobby)</title>
<meta name="description" content="A pick and a probability for every open Counter-Strike 2 fixture
listed in the HotSpawn pick'em lobby, with external betting lines and clearly labelled originated lines.">
<link rel="stylesheet" href="assets/board.css">
</head>
<body>
<header class="top"><div class="inner">
  <div class="brand"><span class="dot"></span> Full pick coverage · every HotSpawn CS2 fixture</div>
  <nav class="pages" aria-label="Board sections">{nav}</nav>
</div></header>
<main class="wrap">
{body}
<footer>
  <p>Board data: <code>data/fe803b80/board.json</code> · wall clock of the last published build:
  <strong>{esc(fmt(board.get("generated_utc")))}</strong> · lobby read
  {esc(fmt(board.get("fixture_source_read_utc")))}.</p>
  <p>HotSpawn is used to discover fixtures and to settle results — never to set a probability.
  Crowd "picked %" values are not read, stored or displayed here. Originated lines are model
  output, clearly labelled, and are not betting advice or a guarantee. Model estimates only.
  If you gamble, be 18+ and use licensed operators.</p>
</footer>
</main>
</body>
</html>
"""


def row_sources_summary(board: dict) -> str:
    acc = board.get("access") or {}
    rows = []
    for key in ("hotspawn_lobby_page", "hotspawn_api", "pinnacle", "bovada", "linefeed_melbet",
                "kalshi", "bo3gg_matches", "valve_vrs"):
        meta = acc.get(key) or {}
        status = meta.get("status")
        status_txt = "ok" if status and status < 400 else (str(status) if status else "—")
        err = meta.get("error")
        rows.append(f"<tr><td>{esc(key)}</td><td class='num'>{esc(status_txt)}</td>"
                    f"<td class='num'>{esc(meta.get('bytes') or meta.get('matches') or '')}</td>"
                    f"<td class='src'>{esc(err or '')}</td></tr>")
    probes = []
    for key, meta in acc.items():
        if key.startswith("probe_"):
            status = meta.get("status")
            probes.append(f"<tr><td>{esc(key[6:])}</td>"
                          f"<td class='num'>{esc(status if status else 'blocked')}</td>"
                          f"<td class='src'>{esc(meta.get('error') or '')}</td></tr>")
    return ("<table class='resp'><thead><tr><th>Source</th><th>HTTP</th><th>Size/rows</th>"
            "<th>Error</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            + "<h3>Reachability probes (never used as prices)</h3><table class='resp'><thead>"
            "<tr><th>Probe</th><th>HTTP</th><th>Error</th></tr></thead><tbody>"
            + "".join(probes) + "</tbody></table>")


def render_index(board: dict) -> str:
    s = board["summary"]
    calib = board.get("calibration") or {}
    track = board.get("track_record") or {}
    open_rows = board.get("open") or []
    bounded = [r for r in open_rows if (r.get("model") or {}).get("basis") in BOUND_BASES]
    no_number = [r for r in open_rows if not (r.get("line") or {}).get("pick")]
    body = f"""
<h1>Executive summary</h1>
<p class="sub">Every Counter-Strike 2 fixture in the HotSpawn pick'em lobby, with a pick and a
probability for each one — including tier-C matches no bookmaker prices.</p>

<div class="cards">
  <div class="card"><div class="n">{s['open']}</div><div class="l">CS2 fixtures open for picks</div></div>
  <div class="card"><div class="n">{s['open_with_pick']}</div><div class="l">have a pick + probability</div></div>
  <div class="card"><div class="n">{s['open_with_market']}</div><div class="l">priced by a bookmaker/exchange</div></div>
  <div class="card"><div class="n">{s['open_blank']}</div><div class="l">blank &amp; flagged (no source)</div></div>
</div>

<div class="note good"><strong>Where the picks are →</strong> the live list is on
<a href="picks.html">All picks</a>. Each match shows the pick, the win probability, the basis
(market, market+model, or originated from ratings) and the source link for every number.
Fixtures that no bookmaker prices are listed with the assumption they depend on on
<a href="unresolved.html">Unresolved picks &amp; limitations</a>.</div>

<div class="jump">
  <a href="picks.html"><b>All picks — every open fixture</b>
    <span>Pick, probability, confidence and the source link for each match. Updated automatically.</span></a>
  <a href="unresolved.html"><b>Unresolved picks &amp; limitations</b>
    <span>The {len(bounded)} fixture(s) priced under a stated assumption, the {len(no_number)} with no
    number at all, and what each method can and cannot do — with the per-match source ledger.</span></a>
  <a href="lines.html"><b>Betting lines used</b>
    <span>The exact Pinnacle / Bovada / Kalshi / Melbet / Thunderpick prices behind each market row.</span></a>
  <a href="tournaments.html"><b>By tournament</b>
    <span>The same coverage grouped by event — useful when a whole event is low tier.</span></a>
  <a href="flagged.html"><b>Flagged for review</b>
    <span>Alias joins, originated lines, blocked sources and every unverified gap, with links.</span></a>
  <a href="results.html"><b>Track record</b>
    <span>Published picks graded against the final scores HotSpawn reports.</span></a>
  <a href="method.html"><b>Method &amp; sources</b>
    <span>Formulas, weights, tolerances, and what this board will not claim.</span></a>
</div>

<h2>How to read a pick</h2>
<ul class="tight">
  <li><span class="badge pick">PICK</span> the team with the higher final probability on that row.</li>
  <li><span class="badge market">market</span> the number comes from external prices only
      (bookmakers/exchange), margin removed with the proportional no-vig method.</li>
  <li><span class="badge market">market+model</span> external prices blended with the official
      Valve VRS rating model (logit blend, market weight 0.85 with 2+ sources, 0.75 with one).</li>
  <li><span class="badge model">originated</span> no reachable bookmaker prices this fixture, so the
      line is originated here: official Valve VRS points, or — when the teams have no VRS row — this
      project's own Elo built from published bo3.gg match results. Labelled, never mixed silently.</li>
  <li><span class="badge model">bound</span> the number depends on a stated assumption (an unrated
      opponent placed on Valve's published floor, or a former-name alias candidate). The assumption
      is written out on the row and on the <a href="unresolved.html">unresolved page</a>.</li>
  <li><span class="badge bad">unverified</span> nothing sourced could support a number; the cell
      stays blank and the row is on the flagged page.</li>
</ul>

<h2>Coverage right now</h2>
<table class="resp"><thead><tr><th>Measure</th><th>Value</th></tr></thead><tbody>
<tr><td>Open fixtures</td><td class="num">{s['open']}</td></tr>
<tr><td>Open · basis = market</td><td class="num">{s['open_market_only']}</td></tr>
<tr><td>Open · basis = market+model</td><td class="num">{s['open_market_model']}</td></tr>
<tr><td>Open · basis = originated model</td><td class="num">{s['open_model_only']}</td></tr>
<tr><td>Open · priced under a stated assumption (see unresolved)</td>
    <td class="num">{len(bounded)}</td></tr>
<tr><td>Open · no number at all (see unresolved)</td><td class="num">{len(no_number)}</td></tr>
<tr><td>Open · blank with a flag</td><td class="num">{s['open_blank']}</td></tr>
<tr><td>Listed but locked/past (kept for results)</td><td class="num">{s['closed']}</td></tr>
<tr><td>External quotes collected</td><td class="num">{s['quotes_total']}</td></tr>
<tr><td>Quotes that joined a lobby fixture</td><td class="num">{s['quotes_joined_events']}</td></tr>
<tr><td>Quotes unmatched (events not on the lobby)</td><td class="num">{s['quotes_unmatched']}</td></tr>
<tr><td>Valve VRS calibration pairs / k</td>
    <td class="num">{calib.get('n_pairs', 0)} / {('%.3f' % calib['k']) if calib.get('k') else '—'}</td></tr>
<tr><td>Track record settled picks</td>
    <td class="num">{track.get('settled', 0)} ({track.get('won', 0)} won)</td></tr>
</tbody></table>

<div class="note info"><strong>Mobile first.</strong> This section is built for a phone: one column,
16&nbsp;px text, tables that become cards on narrow screens, and no external scripts or fonts.
Use the pills at the top of any page to jump between sections, and
<a href="picks.html">All picks</a> for the list itself.</div>

<h2>Source health of this build</h2>
{row_sources_summary(board)}
"""
    return page("Executive summary", "index.html", body, board)


def fixture_card(row: dict) -> str:
    line = row.get("line") or {}
    pick = line.get("pick")
    a_win = pick == row["team_a"]
    meta = [f"{fmt(row.get('start_utc'))}", row.get("competition") or "",
            f"tier {row.get('tier') or '—'}", f"Bo{row.get('best_of') or '?'}",
            f"{row.get('points') or '—'} pts"]
    badges = basis_badge(row)
    if line:
        badges += f' <span class="badge pick">PICK {esc(pick)} {pct(line.get("pick_probability"))}</span>'
        badges += f' <span class="badge">{esc(line.get("confidence"))}</span>'
    badges += "".join(f' <span class="badge">{esc(f)}</span>' for f in (row.get("flags") or [])[:3])
    srcs = src_links(row)
    return f"""
<article class="fixture">
  <div class="meta">{' · '.join(esc(m) for m in meta if m)}</div>
  <div class="teams">
    <div class="team{' win' if a_win else ''}"><div class="nm">{esc(row['team_a'])}</div>
      <div class="pr">{pct(line.get('prob_a') if line else None)}</div></div>
    <div class="team{' win' if line and not a_win else ''}"><div class="nm">{esc(row['team_b'])}</div>
      <div class="pr">{pct(line.get('prob_b') if line else None)}</div></div>
  </div>
  <div>{badges}</div>
  <details><summary>Numbers and sources</summary>
    <div class="src">{srcs}</div>
    <p class="src">Fixture reference:
      <a href="{esc(row['hotspawn_url'])}" rel="noopener">{esc(row['hotspawn_url_kind'])}</a>
      · lock {esc(fmt(row.get('lock_utc')))}</p>
  </details>
</article>
"""


def render_picks(board: dict) -> str:
    rows = [r for r in board["open"]]
    priced = [r for r in rows if r.get("market")]
    body = f"""
<h1>All picks — {len(rows)} open CS2 fixtures</h1>
<p class="sub">Every fixture the HotSpawn pick'em lobby currently lists for Counter-Strike 2.
A pick and a probability are shown for each match; the basis tells you where the number comes from.
List is re-generated automatically from the lobby, so it follows HotSpawn as it adds matches.</p>
<div class="note">{len(priced)} of {len(rows)} open fixtures are priced by a reachable external
bookmaker or exchange. The other {len(rows) - len(priced)} have an <strong>originated line</strong>
(Valve VRS rating model, a bounded one-sided estimate, or this project's own Elo over published
results) — labelled on the row, with the assumption and the per-match source ledger on
<a href="unresolved.html">Unresolved picks &amp; limitations</a>.</div>
{''.join(fixture_card(r) for r in rows) if rows else '<p>No open fixtures in the current lobby read.</p>'}
<p class="src">Sorted by kickoff (UTC). Blank rows are never estimated: they appear with a flag
instead, and are counted in the executive summary.</p>
"""
    return page("All picks", "picks.html", body, board)


def attempt_table(row: dict) -> str:
    """The per-fixture source ledger: what was tried for this match and what each source said."""
    rows = []
    for entry in row.get("attempts") or []:
        rows.append(f"<tr><td>{esc(entry.get('source'))}</td><td>{esc(entry.get('state'))}</td>"
                    f"<td>{esc(entry.get('joined'))}</td></tr>")
    if not rows:
        return "<p class=\"src\">No source attempt was recorded for this row.</p>"
    return ("<table class='resp'><thead><tr><th>Source</th><th>Answer</th><th>Price joined</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def render_unresolved(board: dict) -> str:
    """The separate 'Unresolved picks & limitations' section.

    Section A lists the rows that carry no number at all. Section B lists the rows whose number is
    an estimate that depends on a stated assumption, with that assumption written out. Section C
    states what each resolution method can and cannot do, including the sources that are blocked.
    """
    rows = board.get("open") or []
    blank = [r for r in rows if not (r.get("line") or {}).get("pick")]
    bounded, originated = [], []
    for r in rows:
        origin = (r.get("model") or {}).get("basis")
        if (r.get("market") or {}).get("prob_a"):
            continue            # a bookmaker price is the published number, not an estimate
        if origin in BOUND_SET:
            bounded.append(r)
        elif origin in ORIGIN_SET:
            originated.append(r)
    access = board.get("access") or {}
    hltv = access.get("hltv_ranking") or {}
    hltv_state = ("not attempted in this build" if not hltv else
                  f"HTTP {hltv.get('status')}" + (f" — {hltv.get('error')}" if hltv.get("error") else ""))
    vrs = access.get("valve_vrs") or {}
    vrs_snapshot = vrs.get("snapshot") or "unavailable"

    blank_rows = []
    for r in blank:
        blank_rows.append(f"""<article class="fixture">
  <div class="meta">{esc(fmt(r.get('start_utc')))} · {esc(r.get('competition') or '')} ·
    tier {esc(r.get('tier') or '—')}</div>
  <div class="teams">
    <div class="team"><div class="nm">{esc(r['team_a'])}</div><div class="pr">—</div></div>
    <div class="team"><div class="nm">{esc(r['team_b'])}</div><div class="pr">—</div></div>
  </div>
  <div><span class="badge bad">no number</span>{''.join(f' <span class="badge">{esc(f)}</span>' for f in (r.get('flags') or []))}</div>
  <details open><summary>What was tried for this match</summary>
    {attempt_table(r)}
    <p class="src">Fixture reference:
      <a href="{esc(r['hotspawn_url'])}" rel="noopener">{esc(r['hotspawn_url_kind'])}</a></p>
  </details>
</article>""")

    bound_rows = []
    for r in bounded:
        floor = (r.get("model") or {}).get("floor") or {}
        line = r.get("line") or {}
        bound_rows.append(f"""<article class="fixture">
  <div class="meta">{esc(fmt(r.get('start_utc')))} · {esc(r.get('competition') or '')}</div>
  <div class="teams">
    <div class="team{' win' if line.get('pick') == r['team_a'] else ''}">
      <div class="nm">{esc(r['team_a'])}</div><div class="pr">{pct(line.get('prob_a'))}</div></div>
    <div class="team{' win' if line.get('pick') == r['team_b'] else ''}">
      <div class="nm">{esc(r['team_b'])}</div><div class="pr">{pct(line.get('prob_b'))}</div></div>
  </div>
  <div><span class="badge pick">PICK {esc(line.get('pick'))} {pct(line.get('pick_probability'))}</span>
    <span class="badge model">{esc(BOUND_BASES.get((r.get('model') or {}).get('basis'), 'bound'))}</span></div>
  <details open><summary>The assumption behind this number</summary>
    <p>{esc(floor.get('assumption') or '')}</p>
    <p class="src">Rated side: {esc(floor.get('rated_vrs_name'))} ·
      {esc(floor.get('rated_points'))} points (official Valve VRS, standing
      {esc(floor.get('rated_standing'))}) · rating source:
      {esc(floor.get('rating_source'))}. Unrated opponent placed on the
      {esc(floor.get('floor_points'))}-point floor.</p>
    {attempt_table(r)}
    <p class="src">{src_links(r)}</p>
  </details>
</article>""")

    origin_rows = []
    for r in originated:
        line = r.get("line") or {}
        origin = (r.get("model") or {}).get("basis")
        origin_rows.append(f"""<article class="fixture">
  <div class="meta">{esc(fmt(r.get('start_utc')))} · {esc(r.get('competition') or '')}</div>
  <div class="teams">
    <div class="team{' win' if line.get('pick') == r['team_a'] else ''}">
      <div class="nm">{esc(r['team_a'])}</div><div class="pr">{pct(line.get('prob_a'))}</div></div>
    <div class="team{' win' if line.get('pick') == r['team_b'] else ''}">
      <div class="nm">{esc(r['team_b'])}</div><div class="pr">{pct(line.get('prob_b'))}</div></div>
  </div>
  <div><span class="badge pick">PICK {esc(line.get('pick'))} {pct(line.get('pick_probability'))}</span>
    <span class="badge model">{esc(ORIGIN_BASES.get(origin, 'originated'))}</span></div>
  <details><summary>How this number was produced</summary>
    {attempt_table(r)}
    <p class="src">{src_links(r)}</p>
  </details>
</article>""")

    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="sub">This page exists so that no gap is hidden. It lists every open fixture whose number
is <em>not</em> a bookmaker or exchange price, the assumption each such number depends on, and
what each resolution method can and cannot do.</p>

<div class="cards">
  <div class="card"><div class="n">{len(blank)}</div><div class="l">fixtures with no number at all</div></div>
  <div class="card"><div class="n">{len(bounded)}</div><div class="l">priced under a stated assumption</div></div>
  <div class="card"><div class="n">{len(originated)}</div><div class="l">originated from ratings / results</div></div>
  <div class="card"><div class="n">{len(rows) - len(blank) - len(bounded) - len(originated)}</div>
    <div class="l">priced by a bookmaker or exchange</div></div>
</div>

<h2>A · No number at all ({len(blank)})</h2>
<p>These fixtures have no published two-way price in any reachable source and no official rating
for at least one side, and no evidence that would let this project originate one. The probability
stays blank: it is never estimated, and HotSpawn's crowd percentage is never used as a substitute.</p>
{''.join(blank_rows) if blank_rows else '<p>None in this build — every open fixture carries a number.</p>'}

<h2>B · Priced under a stated assumption ({len(bounded)})</h2>
<p>These fixtures carry a number, but the number depends on an assumption that is written out on the
row. Read them as a bounded estimate, never as a market price.</p>
{''.join(bound_rows) if bound_rows else '<p>None in this build.</p>'}

<h2>C · Originated lines ({len(originated)})</h2>
<p>No reachable bookmaker priced these fixtures, so the line is originated from published ratings or
published results with a documented formula. It is an estimate, not a price.</p>
{''.join(origin_rows) if origin_rows else '<p>None in this build.</p>'}

<h2>D · What each method can and cannot do</h2>
<table class="resp"><thead><tr><th>Method</th><th>Uses</th><th>Limitation</th></tr></thead><tbody>
<tr><td>External prices (Pinnacle, Bovada, the 1xBet platform LineFeed, Kalshi, Polymarket,
        Thunderpick via bo3.gg)</td>
    <td>The books' own two-way prices, margin removed with the proportional no-vig method.</td>
    <td>Only fixtures a book lists are covered. Tier-C qualifiers and regional cups are often
        unlisted, and a thin exchange book is refused rather than used.</td></tr>
<tr><td>Official Valve VRS</td>
    <td>Valve's published regional standings (snapshot {esc(vrs_snapshot)}), read from the official
        repository.</td>
    <td>Published roughly monthly, so it lags the lobby by up to a few weeks, and it lists rosters,
        not fixtures. A roster that is absent from the table has no published rating.</td></tr>
<tr><td>One-sided VRS bound</td>
    <td>One rated roster against an unrated opponent placed on Valve's published 400-point floor.</td>
    <td>The floor is an assumption about the unrated side; a real unlisted roster can be stronger,
        so the number is a bound, not a probability.</td></tr>
<tr><td>Alias candidate</td>
    <td>A HotSpawn listing under a former name matched against Valve's official rows for that name.</td>
    <td>The identity is a candidate, not a confirmed match: HotSpawn may list a different roster
        under that name. The weakest official row is used so the estimate stays conservative.</td></tr>
<tr><td>bo3.gg published results / ranking</td>
    <td>Finished-match results and the published world ranking of each team.</td>
    <td>Many tier-C teams have no published ranking and few finished results; the Elo over a handful
        of matches is noisy.</td></tr>
<tr><td>HLTV</td>
    <td>The public HLTV team ranking, if the page answers an automated read.</td>
    <td>Answered {esc(hltv_state)} in this build — a blocked page is published as blocked and is
        never treated as "the team has no ranking".</td></tr>
<tr><td>bo3.gg fixture identity</td>
    <td>The same slot, the same competition and the same opponent on bo3.gg.</td>
    <td>Only fires when one side's name matches exactly and the slot and competition agree; no
        substring or fuzzy matching is used.</td></tr>
<tr><td>HotSpawn</td>
    <td>Fixture discovery and the final score used to settle the track record.</td>
    <td>The crowd "picked %" is never read, stored or used as a probability.</td></tr>
</tbody></table>

<div class="note info"><strong>Every row has a source link.</strong> A row without a source link is
a bug, not a gap: the board's contract tests fail if any published row loses its link.</div>
"""
    return page("Unresolved picks & limitations", "unresolved.html", body, board)


def render_lines(board: dict) -> str:
    rows = [r for r in board["open"]]
    trs = []
    for r in rows:
        for q in r.get("quotes") or []:
            trs.append(f"""<tr>
<td data-l="Match">{esc(r['team_a'])} vs {esc(r['team_b'])}<div class="src">{esc(r.get('competition'))}</div></td>
<td data-l="Source">{esc(q['source_name'])}</td>
<td class="num" data-l="Odds A">{esc(q['decimal_a'])}</td>
<td class="num" data-l="Odds B">{esc(q['decimal_b'])}</td>
<td class="num" data-l="No-vig A">{pct(q['prob_a'])}</td>
<td class="num" data-l="Margin">{(('%.2f%%' % (float(q['overround']) * 100)) if q.get('overround') is not None else '—')}</td>
<td class="src" data-l="Source link"><a href="{esc(q['public_url'])}" rel="noopener">open</a>
  · read {esc(fmt(q.get('retrieved_utc')))}</td></tr>""")
    unmatched = board.get("unmatched_quotes") or []
    utrs = "".join(f"""<tr><td data-l="Event">{esc(u['team_a'])} vs {esc(u['team_b'])}</td>
<td data-l="Source">{esc(u['source_name'])}</td>
<td class="num" data-l="Odds">{esc(u.get('decimal_a'))} / {esc(u.get('decimal_b'))}</td>
<td class="src" data-l="Link"><a href="{esc(u['public_url'])}" rel="noopener">open</a></td></tr>"""
                     for u in unmatched[:60])
    body = f"""
<h1>Betting lines used</h1>
<p class="sub">Raw two-way prices actually read for this build, with the exact source link and UTC
read time. No-vig probability is the proportional margin removal
<code>p = (1/odds) / Σ(1/odds)</code>. HotSpawn never appears as a price source.</p>
<table class="resp"><thead><tr><th>Match</th><th>Source</th><th>Odds A</th><th>Odds B</th>
<th>No-vig A</th><th>Margin</th><th>Source link</th></tr></thead><tbody>
{''.join(trs) if trs else '<tr><td colspan="7">No market quotes joined a lobby fixture in this build.</td></tr>'}
</tbody></table>
<h2>Collected but unmatched ({len(unmatched)})</h2>
<p class="sub">Prices found on external sites for events that are not in the lobby's current CS2
list (other tournaments, feeder events, or a different lineup of the same event). They are published
for auditability and are not used in any pick.</p>
<table class="resp"><thead><tr><th>Event</th><th>Source</th><th>Odds</th><th>Link</th></tr></thead>
<tbody>{utrs or '<tr><td colspan="4">None.</td></tr>'}</tbody></table>
"""
    return page("Lines", "lines.html", body, board)


def render_tournaments(board: dict) -> str:
    groups: dict[str, list] = {}
    for r in board["open"]:
        groups.setdefault(r.get("competition") or "Unknown event", []).append(r)
    blocks = []
    for name in sorted(groups, key=lambda n: (-len(groups[n]), n)):
        rows = groups[name]
        with_pick = sum(1 for r in rows if r.get("line"))
        with_market = sum(1 for r in rows if r.get("market"))
        trs = "".join(f"""<tr>
<td data-l="Match">{esc(r['team_a'])} vs {esc(r['team_b'])}</td>
<td class="num" data-l="Kickoff (UTC)">{esc(fmt(r.get('start_utc')))}</td>
<td data-l="Pick"><strong>{esc((r.get('line') or {}).get('pick') or '—')}</strong>
  <span class="num">{pct((r.get('line') or {}).get('pick_probability'))}</span></td>
<td data-l="Basis">{basis_badge(r)}</td>
<td class="src" data-l="Sources">{src_links(r)}</td></tr>""" for r in rows)
        blocks.append(f"""<h2>{esc(name)} <span class="src">({len(rows)} fixtures,
{with_market} priced by a bookmaker, {with_pick} with a pick)</span></h2>
<table class="resp"><thead><tr><th>Match</th><th>Kickoff (UTC)</th><th>Pick</th><th>Basis</th>
<th>Sources</th></tr></thead><tbody>{trs}</tbody></table>""")
    body = ("<h1>Picks by tournament</h1><p class='sub'>The same coverage as "
            "<a href='picks.html'>All picks</a>, grouped by the event name the lobby publishes.</p>"
            + ("".join(blocks) if blocks else "<p>No open fixtures.</p>"))
    return page("Tournaments", "tournaments.html", body, board)


def render_results(board: dict) -> str:
    track = board.get("track_record") or {}
    hist = [r for r in (board.get("history") or []) if r.get("settled") in ("won", "lost")]
    pend = [r for r in (board.get("history") or []) if not r.get("settled")]
    trs = "".join(f"""<tr><td data-l="Kickoff">{esc(fmt(r.get('start_utc')))}</td>
<td data-l="Match">{esc(r['team_a'])} vs {esc(r['team_b'])}</td>
<td data-l="Pick">{esc(r['pick'])} <span class="num">{pct(r.get('pick_probability'))}</span></td>
<td data-l="Basis">{esc(r.get('basis'))}</td>
<td data-l="Result">{'won' if r['settled'] == 'won' else 'lost'} — {esc(r.get('winner'))}</td></tr>"""
                 for r in sorted(hist, key=lambda x: x.get("start_utc") or "", reverse=True))
    pends = "".join(f"""<tr><td data-l="Kickoff">{esc(fmt(r.get('start_utc')))}</td>
<td data-l="Match">{esc(r['team_a'])} vs {esc(r['team_b'])}</td>
<td data-l="Pick">{esc(r['pick'])} <span class="num">{pct(r.get('pick_probability'))}</span></td>
<td data-l="Basis">{esc(r.get('basis'))}</td></tr>""" for r in pend[:40])
    acc = ("%.1f%%" % (100 * track["won"] / track["settled"])) if track.get("settled") else "—"
    body = f"""
<h1>Track record</h1>
<p class="sub">Every pick this board publishes is appended to an append-only history file and later
graded against the final score HotSpawn reports for that fixture (settlement source, not a model).
The record starts with the first build of this section, so early numbers are small.</p>
<div class="cards">
  <div class="card"><div class="n">{track.get('settled', 0)}</div><div class="l">settled picks</div></div>
  <div class="card"><div class="n">{track.get('won', 0)}</div><div class="l">winners</div></div>
  <div class="card"><div class="n">{acc}</div><div class="l">hit rate so far</div></div>
  <div class="card"><div class="n">{('%.3f' % track['brier']) if track.get('brier') else '—'}</div>
    <div class="l">Brier score (lower is better)</div></div>
</div>
<h2>Settled</h2>
<table class="resp"><thead><tr><th>Kickoff</th><th>Match</th><th>Pick</th><th>Basis</th><th>Result</th>
</tr></thead><tbody>{trs or '<tr><td colspan="5">Nothing settled yet.</td></tr>'}</tbody></table>
<h2>Pending</h2>
<table class="resp"><thead><tr><th>Kickoff</th><th>Match</th><th>Pick</th><th>Basis</th></tr>
</thead><tbody>{pends or '<tr><td colspan="4">No pending picks.</td></tr>'}</tbody></table>
"""
    return page("Results", "results.html", body, board)


def render_flagged(board: dict) -> str:
    flags: dict[str, list] = {}
    for r in board["open"]:
        for f in r.get("flags") or []:
            flags.setdefault(f, []).append(r)
    sections = []
    for flag in sorted(flags, key=lambda f: -len(flags[f])):
        rows = flags[flag]
        items = "".join(f"""<li><strong>{esc(r['team_a'])} vs {esc(r['team_b'])}</strong>
({esc(r.get('competition'))}, {esc(fmt(r.get('start_utc')))}) — {basis_badge(r)}
<div class="src">Sources: {src_links(r)}</div>
<div class="src">Fixture: <a href="{esc(r['hotspawn_url'])}" rel="noopener">{esc(r['hotspawn_url_kind'])}</a></div>
</li>""" for r in rows[:60])
        sections.append(f"<h3>{esc(flag)} <span class='src'>({len(rows)} open fixtures)</span></h3>"
                        f"<ul class='tight'>{items}</ul>")
    alias_rows = [r for r in board["open"] + board["closed"] if r.get("alias_note")]
    alias_items = "".join(
        f"""<li><strong>{esc(r['team_a'])} vs {esc(r['team_b'])}</strong> — {esc(r['alias_note'])}
        <div class="src">Evidence: {' '.join(f'<a href="{esc(u)}" rel="noopener">{esc(u)}</a>'
                                             for u in (r.get('alias_evidence') or [])) or '(none)'}</div>
        </li>""" for r in alias_rows[:40])
    rejected = board.get("rejected_quotes") or []
    rej_items = "".join(f"""<li>{esc(q['team_a'])} vs {esc(q['team_b'])} — {esc(q['reason'])}
        <div class="src"><a href="{esc(q['public_url'])}" rel="noopener">market page</a></div></li>"""
                        for q in rejected[:20])
    vrs_amb = board.get("vrs_ambiguous_keys") or []
    unmatched = board.get("unmatched_quotes") or []
    body = f"""
<h1>Flagged for review</h1>
<p class="sub">Everything on this board that is not a plain, fully sourced number. Nothing here
blocks the board: each item is published with its source link so a human can check it.</p>

<div class="note"><strong>Open gaps.</strong> {board['summary']['open_blank']} open fixtures have no
pick: no reachable bookmaker prices them and no rating source covers both teams. Those cells stay
blank on purpose. If you can point at a source for one of them, it can be added.</div>

<h2>Row-level flags</h2>
{''.join(sections) if sections else '<p>No row-level flags in this build.</p>'}

<h2>Alias joins applied ({len(alias_rows)})</h2>
<p class="sub">The lobby and the bookmakers/exchange sometimes spell the same roster differently.
An alias is only used when a published source documents the equivalence <em>and</em> the opponent
and the kickoff time agree. Each item below records both.</p>
<ul class="tight">{alias_items or '<li>No alias was needed in this build.</li>'}</ul>

<h2>Prices rejected on purpose ({len(rejected)})</h2>
<p class="sub">Order books that are one-sided or wider than 10 cents are not treated as a price;
a mid computed from a stale or empty book would be a guess.</p>
<ul class="tight">{rej_items or '<li>None in this build.</li>'}</ul>

<h2>Unmatched external prices ({len(unmatched)})</h2>
<p class="sub">These priced events are not in the lobby's current CS2 list (other tournaments or
feeder events). They are recorded, not used — see <a href="lines.html">Lines</a> for the list.</p>

<h2>Ambiguous rating rows ({len(vrs_amb)})</h2>
<p class="sub">Teams that appear twice in Valve's regional standings with different point values
(e.g. an organisation keeping an older roster as a separate row). The global row is used and the
ambiguity is listed here rather than silently resolved.</p>
<ul class="tight">{''.join(f'<li><code>{esc(k)}</code></li>' for k in vrs_amb[:40]) or '<li>None this build.</li>'}</ul>

<h2>Source access failures in this build</h2>
{row_sources_summary(board)}
<p class="src">A blocked source is a failure of this collector, not evidence that no price exists.
The board never renders a blocked source as a blank probability without this flag.</p>
"""
    return page("Flagged for review", "flagged.html", body, board)


def render_method(board: dict) -> str:
    calib = board.get("calibration") or {}
    elo = board.get("elo") or {}
    vrs = board.get("vrs") or {}
    snaps = ", ".join(f"{e['region']} ({e['teams']} teams)" for e in (vrs.get("evidence") or []))
    body = f"""
<h1>Method &amp; sources</h1>
<p class="sub">What is measured, what is modelled, and what this board refuses to claim.</p>

<h2>1 · Fixture discovery (HotSpawn, reverse engineered)</h2>
<p>The public lobby page ships an Angular transfer state (<code>script#ng-state</code>) containing the
same <code>/api/v1/fixtures</code> response the page renders, plus the permalink map HotSpawn itself
publishes for each match. This board reads that public state and the public fixtures API — no admin
endpoint, no authentication, no scraping of the DOM. Only CS2 rows are kept. Crowd "picked %" values
are refused at the parser (<code>core.FIXTURE_KEYS</code>) and cannot reach a probability.</p>

<h2>2 · Market prices (external, never HotSpawn)</h2>
<ul class="tight">
<li><strong>Pinnacle</strong> — licensed bookmaker, public guest odds API (moneyline, period 0, not alternate, status open).</li>
<li><strong>Bovada</strong> — licensed bookmaker, public coupon JSON (moneyline, main period).</li>
<li><strong>1xBet platform (1xBet / Melbet / 22bet / Betwinner)</strong> — licensed bookmakers on the
1xBet platform (mirror family; one quote per event, cited to the mirror that published it).</li>
<li><strong>Polymarket</strong> — CFTC-regulated prediction market; only a two-outcome match market
whose outcome names match the two teams and whose event carries a start time is used.</li>
<li><strong>Kalshi</strong> — CFTC-regulated exchange, series <code>KXCS2GAME</code>; mid of the bid/ask, and books wider than 10&nbsp;cents or one-sided are rejected.</li>
<li><strong>Thunderpick</strong> — licensed esports bookmaker; its two-way coefficients are read from the
public <code>bet_updates</code> block of the bo3.gg API, which is what covers the tier-C events no other
reachable bookmaker lists. The row links to the bo3.gg match page.</li>
</ul>
<p>Margin removal is proportional: <code>p = (1/odds) / Σ(1/odds)</code>. The consensus is a
source-weighted mean (Pinnacle 2.0, Bovada 1.5, Thunderpick 1.5, Kalshi 1.0, Melbet 1.0) and the
min–max spread is published on the row when two or more sources quote it.</p>

<h2>3 · Originated lines (this project's own numbers)</h2>
<p>Where no reachable price exists, the board originates a line instead of leaving the match blank,
and labels it:</p>
<ul class="tight">
<li><strong>Valve VRS model.</strong> Valve's own published relationship applies: a 400-point rating
difference equals ~90% win probability. With <code>C = g·ln(10)/400</code>, <code>g = 1/√(1+3Q²RD²/π²)</code>,
<code>Q = ln(10)/400</code>, <code>RD = 75</code> (Valve's <code>model/glicko.js</code> and
<code>defaultGlickoParams</code>), the model probability is <code>σ(k·C·Δpoints)</code>. The slope
<code>k</code> is fitted from this build's own market/VRS pairs (<code>k = {calib.get('k')}</code> over
{calib.get('n_pairs', 0)} pairs; Valve's own curve would be k=1) because Valve's README states the
published curve is too steep at the ends.</li>
<li><strong>Our Elo (last resort).</strong> When neither team has a VRS row, an Elo is computed from the
finished matches bo3.gg publishes (result and score only — a factual record, not a price):
<code>1500 + (VRS points − anchor)</code> seeds teams that do have a VRS row, 8 passes, K=20.
This build used {elo.get('matches', 0)} finished matches and seeded {elo.get('teams_seeded', 0)} teams.</li>
<li><strong>One-sided Valve VRS bound.</strong> When exactly one roster is listed in Valve's published
standings, the unlisted opponent is placed on the <strong>400-point floor</strong> that Valve's own
model starts every roster at, and the number is published as a <em>bound under that assumption</em>
(<code>σ(k·C·(points − 400))</code>), never as a price. The row names the assumption and links the
official standings row it used.</li>
<li><strong>Alias candidate.</strong> HotSpawn sometimes lists a team under a former name
("ex-…"). When removing that prefix matches an official Valve row, the weakest official row for that
name is used and the row is flagged <code>alias_candidate_identity_unconfirmed</code>: the identity
is a candidate, not a confirmed match.</li>
<li><strong>bo3.gg fixture identity.</strong> A HotSpawn team that bo3.gg does not list can still be
mapped when bo3.gg publishes the <em>same fixture</em> — same slot, same competition and one side's
name matching exactly. The other side is then that team's bo3.gg record, and the bo3.gg match URL
is published as the evidence. No substring or fuzzy matching is used.</li>
<li><strong>HLTV.</strong> The public HLTV team ranking is read when the page answers an automated
read; the ranking positions are mapped onto the Elo scale with the same documented formula as the
bo3.gg ranking. When HLTV blocks the request the attempt is published as blocked — it is never read
as "this team has no ranking".</li>
</ul>
<p>Ratings used: Valve regional standings snapshot <strong>{esc(vrs.get('snapshot') or '—')}</strong>
({esc(snaps) or 'no snapshot read'}), fetched from the official
<a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">ValveSoftware/counter-strike_regional_standings</a>
repository.</p>

<h2>4 · Joining rules (fail closed)</h2>
<ul class="tight">
<li>Both team names must match after normalisation (case/accents/punctuation folded; a leading
"Team/The" and a trailing "Team/Esports/Gaming/GG/Club" dropped) — or a published alias must apply.</li>
<li>The source's own start time must be within 14 hours of the lobby kickoff; differences over
3 hours are flagged on the row.</li>
<li>Exactly one price per fixture and source; the first qualifying moneyline is used.</li>
<li>A quote that does not join is published as unmatched rather than forced onto a fixture.</li>
</ul>

<h2>5 · Limits of this board</h2>
<ul class="tight">
<li>Originated lines are model output, not market prices; they are labelled on every row and counted
separately in the executive summary.</li>
<li>A bounded line (one-sided VRS floor, alias candidate) depends on a stated assumption about a
roster that no official source rates. Every such row is listed on the
<a href="unresolved.html">unresolved picks &amp; limitations</a> page with its assumption and the
per-match source ledger.</li>
<li>The Valve standings snapshot is published roughly monthly, so it lags the lobby; a roster that
is not in the table has no published rating at all.</li>
<li>Sources can be blocked from the collector's network. Every failure is published on the flagged
page; a blocked source never silently becomes a blank probability.</li>
<li>Kalshi kickoff times are encoded in US Eastern time in the event ticker and are used only for
the join window — never displayed as a kickoff.</li>
<li>This is not betting advice, not a guarantee, and not a claim of validated predictive accuracy;
the track record page reports the realised hit rate as it accumulates.</li>
</ul>

<h2>6 · Reproduce it</h2>
<p><code>python3 scripts/fe803b80/collect.py</code> writes <code>data/fe803b80/snapshot.json</code>;
<code>python3 scripts/fe803b80/build.py</code> re-derives every number on this site from that snapshot
and writes <code>data/fe803b80/board.json</code>; <code>python3 scripts/fe803b80/site.py</code>
renders these pages. <code>python3 -m unittest tests.test_fe803b80 -v</code> re-checks the rules above
offline.</p>
"""
    return page("Method", "method.html", body, board)


def main() -> int:
    board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    (OUT / "assets" / "board.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    pages = {
        "index.html": render_index(board),
        "picks.html": render_picks(board),
        "lines.html": render_lines(board),
        "tournaments.html": render_tournaments(board),
        "results.html": render_results(board),
        "unresolved.html": render_unresolved(board),
        "flagged.html": render_flagged(board),
        "method.html": render_method(board),
    }
    for name, html_text in pages.items():
        (OUT / name).write_text(html_text, encoding="utf-8")
    print(f"wrote {len(pages)} pages to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
