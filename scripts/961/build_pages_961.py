#!/usr/bin/env python3
"""Session 961e163a — mobile-first verification pages for the Hotspawn pick board.

Outputs (published at /verify961/ from the repository Pages source, repo root):
    verify961/index.html        dashboard + pick board (open fixtures first)
    verify961/cs2.html          every CS2 fixture
    verify961/lol.html          every LoL fixture
    verify961/flagged.html      unverified rows + every flag, with source links
    verify961/methodology.html  rules, sources, HOW to re-verify
    verify961/style.css         single small stylesheet

Every rendered row shows the exact external source link(s) and the UTC time the price was
read; rows without a verified external price show "unverified" and are listed on the
Flagged page. No value on these pages is estimated.
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "verify961")
BOARD = os.path.join(ROOT, "data", "961", "board.json")
SOURCES = os.path.join(ROOT, "data", "961", "sources.json")

FLAG_HELP = {
    "no_external_line": "No external bookmaker or market price could be verified for this fixture — probabilities are blank by rule.",
    "single_source": "Only one external source quoted this fixture; the consensus equals that source.",
    "scheduled_start_in_the_past_or_started": "The scheduled start time is in the past relative to the build time (fixture started or the lobby list is stale).",
    "live_market_quote": "The source reports the market as live; a live price is not an opening pre-match line.",
    "quote_older_than_6h": "The quote is older than 6 hours at build time.",
    "uses_fallback_stored_quote": "A previously stored capture was used because this run could not re-read the book directly.",
    "start_time_mismatch_over_6h": "The source's reported start time differs from Hotspawn's by more than 6 hours.",
}


def esc(v):
    return html.escape("" if v is None else str(v))


def fmt_prob(p):
    return "—" if p is None else f"{100 * p:.1f}%"


def short_time(value):
    if not value:
        return "—"
    return str(value).replace("T", " ").replace("Z", " UTC")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def source_cell(row):
    if not row["sources"]:
        return '<span class="unverified">unverified — no external line</span>'
    blocks = []
    for s in row["sources"]:
        url = s.get("source_url") or "#"
        if s.get("source_url"):
            link = f'<a href="{esc(url)}" rel="noopener">{esc(s.get("source_name") or s["source_key"])}</a>'
        else:
            link = esc(s.get("source_name") or s["source_key"])
        blocks.append(
            '<div class="src">'
            f'{link}'
            f'<span class="odds">{esc(s.get("decimal_odds_a"))} / {esc(s.get("decimal_odds_b"))}</span>'
            f'<span class="mini">no-vig {fmt_prob(s.get("no_vig_probability_a"))} / {fmt_prob(s.get("no_vig_probability_b"))}'
            f' · margin {esc(s.get("overround"))}</span>'
            f'<span class="mini">read {esc(short_time(s.get("retrieved_at_utc")))}</span>'
            + (f'<span class="mini">note: {esc(s.get("join_note"))}</span>' if s.get("join_note") else "")
            + "</div>")
    return "".join(blocks)


def flags_cell(row):
    if not row["flags"]:
        return '<span class="ok">clean</span>'
    return " ".join(f'<span class="chip">{esc(f)}</span>' for f in row["flags"])


def row_html(row, show_game=True):
    pick = row.get("pick")
    prob = row.get("pick_probability")
    if pick:
        pick_html = (f'<span class="pick">{esc(pick)}</span>'
                     f'<span class="pickprob">{fmt_prob(prob)}</span>')
    else:
        pick_html = '<span class="unverified">no pick — unverified</span>'
    match = (f'<span class="ta">{esc(row.get("team_a"))}</span>'
             f'<span class="vs">vs</span>'
             f'<span class="tb">{esc(row.get("team_b"))}</span>')
    hot = row.get("hotspawn_match_url")
    hot_link = (f'<a class="mini" href="{esc(hot)}" rel="noopener">Hotspawn fixture {esc(row.get("fixture_id"))}</a>'
                if hot else esc(row.get("fixture_id")))
    return f"""<tr class="row {'verified' if row['verified'] else 'unverified-row'}">
  <td data-label="Scheduled (UTC)">{esc(short_time(row.get('scheduled_start_time_utc')))}</td>
  <td data-label="Game">{esc((row.get('game') or '').upper())}</td>
  <td data-label="Tier">{esc((row.get('tier') or '—').upper())}</td>
  <td data-label="Tournament">{esc(row.get('competition'))}</td>
  <td data-label="Match">{match}</td>
  <td data-label="Probability A / B">{fmt_prob(row.get('probability_a'))} / {fmt_prob(row.get('probability_b'))}
    <span class="mini">{esc(row.get('n_sources'))} source(s)</span></td>
  <td data-label="Pick">{pick_html}</td>
  <td data-label="External sources">{source_cell(row)}</td>
  <td data-label="Hotspawn">{hot_link}</td>
  <td data-label="Flags">{flags_cell(row)}</td>
</tr>"""


HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Pick board verification (session 961e163a)</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="topbar"><div class="wrap">
  <div class="brand"><span class="dot"></span>HotSpawn pick&rsquo;em board · verified external lines</div>
  <nav>{nav}</nav>
</div></header>
<main class="wrap">
"""

NAV_ITEMS = [("index.html", "Dashboard"), ("cs2.html", "CS2"), ("lol.html", "LoL"),
             ("flagged.html", "Flagged for review"), ("methodology.html", "Methodology &amp; sources")]


def nav(active):
    return "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{label}</a>'
        for href, label in NAV_ITEMS)


FOOT = """
<footer class="wrap foot">
<p class="mini">Session <code>961e163a</code> · fixture list from
<a href="https://play.hotspawn.com/lobby" rel="noopener">play.hotspawn.com/lobby</a> (public fixtures API) ·
external lines only · Hotspawn crowd pick percentages are never used as probabilities.</p>
<p class="mini">Every value on this page carries the exact source URL and the UTC time it was read.
Values that could not be verified against an official external source are blank and listed on
<a href="flagged.html">Flagged for review</a>.</p>
</footer>
</body></html>
"""


def table(rows, show_game=True):
    head = ("<tr><th>Scheduled (UTC)</th>" + ("<th>Game</th>" if show_game else "") +
            "<th>Tier</th><th>Tournament</th><th>Match</th><th>Probability A / B</th>"
            "<th>Pick</th><th>External line sources</th><th>Hotspawn</th><th>Flags</th></tr>")
    body = "".join(row_html(r, show_game) for r in rows)
    return f'<div class="tablewrap"><table class="board">{head}{body}</table></div>'


def write(name, title, body):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(HEAD.format(title=title, nav=nav(name)) + body + FOOT)


def main() -> int:
    board = load(BOARD)
    rows = board["rows"]
    summary = board["summary"]
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    open_rows = [r for r in rows if not any(
        f in r["flags"] for f in ("scheduled_start_in_the_past_or_started",))]
    if not open_rows:
        open_rows = rows[:0]
    picks = [r for r in open_rows if r["verified"]]
    unverified = [r for r in rows if not r["verified"]]

    cards = f"""<div class="cards">
<div class="card"><div class="num">{summary['fixtures_total']}</div><div class="lbl">HotSpawn fixtures in window</div></div>
<div class="card"><div class="num">{summary['open_for_picks']}</div><div class="lbl">Still open for picks</div></div>
<div class="card"><div class="num">{summary['fixtures_with_external_line']}</div><div class="lbl">With verified external line</div></div>
<div class="card"><div class="num">{summary['fixtures_without_external_line']}</div><div class="lbl">Unverified (blank, flagged)</div></div>
</div>"""

    idx = f"""<h1>Pick board — verified external betting lines</h1>
<p class="sub">Built {esc(now)} · window fixtures from the live Hotspawn lobby list, prices re-read from
external sources only. A blank cell is unverified, never estimated. <a href="methodology.html">Method + sources</a>.</p>
{cards}
<h2>Open fixtures with verified external lines ({len(picks)})</h2>
<p class="sub">Pick = the higher external no-vig probability. Probability is the mean of the per-source
de-margined shares; every source link and read time is in the row.</p>
{table(picks) if picks else '<p class="note">No open fixture currently has a verified external line.</p>'}
<h2>All fixtures in the current window ({len(rows)})</h2>
{table(rows)}
<p class="note">Sources are re-read by a scheduled GitHub Actions run; the read time is shown per row so
staleness is always visible. Fixtures with no external price are on <a href="flagged.html">Flagged for review</a>.</p>"""
    write("index.html", "Pick board", idx)

    for game, fname, label in (("cs2", "cs2.html", "CS2 fixtures"), ("lol", "lol.html", "LoL fixtures")):
        grow = [r for r in rows if (r.get("game") or "").lower() == game]
        gpicks = [r for r in grow if r["verified"]]
        gopen = [r for r in grow if r not in unverified]
        body = f"""<h1>{label} ({len(grow)})</h1>
<p class="sub">{len(gpicks)} fixture(s) with a verified external line in this window ·
{len(grow) - len(gpicks)} unverified (blank, flagged).</p>
{"".join(f'<h2>Verified external lines ({len(gpicks)})</h2>' + table(gpicks)) if gpicks else '<p class="note">No verified external line for this game in the current window.</p>'}
<h2>All {label.lower()}</h2>
{table(grow)}"""
        write(fname, label, body)

    flag_rows = "".join(
        f"<tr><td>{esc(r.get('fixture_id'))}</td><td>{esc((r.get('game') or '').upper())}</td>"
        f"<td>{esc(r.get('team_a'))} vs {esc(r.get('team_b'))}</td>"
        f"<td>{esc(r.get('competition'))}</td><td>{esc(short_time(r.get('scheduled_start_time_utc')))}</td>"
        f"<td>{' '.join(f'<span class=\"chip\">{esc(f)}</span>' for f in r['flags'])}</td>"
        f"<td>{'<a href=\"' + esc(r.get('hotspawn_match_url')) + '\" rel=\"noopener\">fixture</a>' if r.get('hotspawn_match_url') else ''}</td></tr>"
        for r in unverified)
    flagged = f"""<h1>Flagged for review</h1>
<p class="sub">Nothing on this list is filled in, estimated or inferred. Unverified fixtures stay blank
until an official external source publishes a price for them.</p>
<div class="cards"><div class="card"><div class="num">{len(unverified)}</div>
<div class="lbl">Fixtures without a verified external line</div></div></div>
<h2>Flag meanings</h2>
<ul class="flags">{''.join(f'<li><code>{esc(k)}</code> — {esc(v)}</li>' for k, v in sorted(FLAG_HELP.items()))}</ul>
<h2>Unverified fixtures</h2>
<div class="tablewrap"><table class="board"><tr><th>Fixture id</th><th>Game</th><th>Match</th>
<th>Tournament</th><th>Scheduled (UTC)</th><th>Flags</th><th>Source</th></tr>{flag_rows}</table></div>
<p class="note">Requests to add a specific source can be raised against
<a href="https://github.com/buffedlizard55-lab/MaltaProj2/issues" rel="noopener">the repository issues</a>.</p>"""
    write("flagged.html", "Flagged for review", flagged)

    src_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>"
        for k, v in sorted((summary.get("by_source") or {}).items()))
    methodology = f"""<h1>Methodology &amp; sources</h1>
<h2>What is measured</h2>
<ol class="flags">
<li>The fixture list (teams, tournament, tier, lock time, Hotspawn link) is read from the lobby's own
public fixtures API behind <a href="https://play.hotspawn.com/lobby" rel="noopener">play.hotspawn.com/lobby</a>.</li>
<li>Prices are read from external, independent sources only: Pinnacle's public guest odds API, Bovada's
public coupon, HLTV's published bookmaker odds and egamersworld's public odds widget.</li>
<li>Per source the margin is removed: q = 1/decimal, p_a = q_a / (q_a + q_b). The published probability is
the arithmetic mean of the per-source no-vig shares; the pick is the higher share.</li>
<li><strong>Hotspawn's crowd pick percentage is never an input.</strong> It is stored separately in
<code>data/961/hotspawn_reference.json</code> and is not read by the builder.</li>
<li>If no external price can be verified the row is blank and flagged <code>no_external_line</code>.</li>
</ol>
<h2>Sources quoted in this build</h2>
<div class="tablewrap"><table class="board"><tr><th>Source key</th><th>Rows using it</th></tr>{src_rows}</table></div>
<h2>Re-verification</h2>
<p class="sub">Every quote is stored with its URL and read time in <code>data/961/quotes.json</code>; the join
and the arithmetic can be recomputed with <code>python3 scripts/961/build_961.py</code> and checked with
<code>python3 -m unittest tests.test_961</code>. The GitHub Actions run
<code>.github/workflows/961-collect.yml</code> re-reads every source on a schedule and commits the evidence.</p>
<p class="note">Known limitations: books publish prices for <em>their own</em> markets and can pull a market at any
time, so a quoted price is a snapshot, not a promise; HLTV rows reflect the bookmaker prices HLTV displays;
fixtures with no external market anywhere are listed unverified rather than guessed.</p>"""
    write("methodology.html", "Methodology", methodology)

    css = """/* session 961e163a — single small stylesheet, mobile first */
:root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--tx:#e8ecf3;--mut:#9aa4b2;--ok:#3ddc97;--warn:#ffb454;--pick:#59a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 14px}
a{color:var(--pick)}
.topbar{background:#12151c;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.topbar .wrap{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;padding:10px 14px}
.brand{font-weight:600;display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ok);display:inline-block}
nav{display:flex;flex-wrap:wrap;gap:6px}
nav a{padding:6px 10px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:14px;color:var(--tx)}
nav a.active{background:var(--pick);border-color:var(--pick);color:#04101f;font-weight:600}
h1{font-size:22px;margin:20px 0 6px}
h2{font-size:17px;margin:24px 0 8px}
.sub{color:var(--mut);margin:4px 0 12px;font-size:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.card .num{font-size:26px;font-weight:700}
.card .lbl{color:var(--mut);font-size:13px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table.board{border-collapse:collapse;width:100%;min-width:760px}
table.board th,table.board td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top;font-size:14px}
table.board th{background:#141821;color:var(--mut);font-weight:600;white-space:nowrap}
table.board tr:last-child td{border-bottom:0}
.ta,.tb{font-weight:600}
.vs{color:var(--mut);margin:0 4px}
.pick{display:inline-block;background:var(--pick);color:#04101f;font-weight:700;border-radius:8px;padding:2px 8px}
.pickprob{display:block;font-weight:700;color:var(--ok);margin-top:2px}
.verified{border-left:3px solid var(--ok)}
.unverified-row{border-left:3px solid var(--warn)}
.unverified{color:var(--warn)}
.ok{color:var(--ok)}
.mini{display:block;color:var(--mut);font-size:12px}
.src{margin-bottom:6px}
.src .odds{display:block;font-weight:600}
.chip{display:inline-block;background:#222836;color:var(--warn);border:1px solid #33405a;border-radius:999px;padding:1px 8px;font-size:12px;margin:0 3px 3px 0}
.flags li{margin:4px 0}
.note{background:#141821;border:1px solid var(--line);border-radius:10px;padding:10px;font-size:14px;color:var(--mut)}
.foot{margin:28px auto;color:var(--mut)}
code{background:#141821;padding:1px 4px;border-radius:4px}
@media (max-width:820px){
  .topbar .wrap{padding:8px 10px}
  table.board{min-width:0}
  table.board thead{display:none}
  table.board,table.board tbody,table.board tr,table.board td{display:block;width:100%}
  table.board tr{border-bottom:1px solid var(--line);padding:8px 4px}
  table.board td{border:0;padding:4px 10px;display:flex;gap:8px}
  table.board td::before{content:attr(data-label);color:var(--mut);font-size:12px;min-width:104px;flex:0 0 104px}
}
"""
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(css)
    print(f"pages written to {os.path.relpath(OUT, ROOT)} "
          f"(fixtures={len(rows)} verified={len(rows) - len(unverified)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
