#!/usr/bin/env python3
"""Session b1fb1465 render step — writes the mobile-first ``exec/`` section.

Pages
-----
* ``exec/index.html``      — **executive summary**: what is covered, what a pick is, links to every
                             in-site list of picks, and the *Unresolved picks & limitations* summary.
* ``exec/picks.html``      — one card per open CS2 fixture: obvious pick, win %, both probabilities,
                             basis, confidence and the source links behind it.
* ``exec/unresolved.html`` — the separate section the project asked for: every fixture whose pick is
                             NOT a bookmaker price, with the limitation that caused it, what was
                             tried (HLTV → esportsbooks → ratings) and what would resolve it.
* ``exec/sources.html``    — source ledger for this run, including the sources that refused it.
* ``exec/flagged.html``    — flagged for review: aliases applied, rejected joins, thin books,
                             single-source rows, schedule discrepancies.
* ``exec/method.html``     — formulas, thresholds, refresh cadence and the limits of the method.

Everything is generated from ``data/b1fb1465/board.json``; no number is typed by hand.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "b1fb1465"
OUT = ROOT / "exec"

NAV = [
    ("index.html", "Executive summary"),
    ("picks.html", "All picks"),
    ("unresolved.html", "Unresolved & limits"),
    ("sources.html", "Sources"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method"),
]

IN_SITE_LINKS = [
    ("picks.html", "Picks for every open match",
     "One card per open CS2 fixture: pick, win %, basis, source links. This section."),
    ("../picks-every-match/index.html", "Every-match picks at a glance (c64a5e19)",
     "Second, independent every-match board: pick + win % for every open fixture."),
    ("../board/picks.html", "All picks · every match (fe803b80)",
     "Full-coverage board with a per-row basis label and a graded track record."),
    ("../ourline/index.html", "Our line (f7279a54)",
     "Market consensus blended with a calibrated VRS model, plus its own track record."),
    ("../coverage/index.html", "Coverage board (6ddde224)",
     "Every lobby fixture: external line, exchange quote, originated estimate or blank."),
    ("../summary/index.html", "Verification companion (c0e223d3)",
     "Independent cross-checks, sources with read times and the repository review."),
    ("unresolved.html", "Unresolved picks & limitations",
     "The matches that no bookmaker price, why, and what was tried to resolve them."),
    ("../flagged.html", "Flagged for review (site-wide)",
     "Everything unverified or irregular, with source links."),
]


def e(value) -> str:
    return html.escape("" if value is None else str(value))


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def money(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):.3f}"


def page(title: str, body: str, active: str, built_utc: str, description: str) -> str:
    nav = "".join(
        f'<a class="navlink{" active" if href == active else ""}" href="{href}">{e(label)}</a>'
        for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{e(description)}">
<meta name="theme-color" content="#0a1526">
<title>{e(title)} · HotSpawn CS2 picks</title>
<link rel="stylesheet" href="assets/exec.css">
</head>
<body>
<header class="topbar">
  <div class="wrap">
    <a class="brand" href="index.html"><span class="dot"></span>HotSpawn CS2 · picks &amp; probabilities</a>
    <nav aria-label="Section">{nav}</nav>
  </div>
</header>
<main class="wrap">
{body}
<footer class="foot">
  <p><strong>Not affiliated with HotSpawn or any bookmaker.</strong> HotSpawn is used to discover
  fixtures and, for the track record, to read the final score. Its crowd pick percentage is never
  read, stored or used as an input. Estimates are not guarantees. 18+; gamble responsibly.</p>
  <p>Built {e(built_utc)} · rebuilt automatically every 4 hours · every row links to its source.</p>
</footer>
</main>
</body>
</html>
"""


CSS = """
:root{--bg:#0a1526;--panel:#10203a;--panel2:#0d1b30;--line:#22314e;--txt:#e8eefb;--muted:#9db0d3;
--acc:#3ea6ff;--good:#2ecc8f;--warn:#ffb648;--bad:#ff6b6b}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 14px 40px}
.topbar{background:linear-gradient(180deg,#0d1b30,#0a1526);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:5;padding:10px 0}
.brand{display:inline-flex;align-items:center;gap:8px;font-weight:700;color:var(--txt);
text-decoration:none;font-size:16px;padding:4px 2px}
.brand .dot{width:9px;height:9px;border-radius:50%;background:var(--good);display:inline-block}
nav{display:flex;gap:8px;overflow-x:auto;padding-top:8px;-webkit-overflow-scrolling:touch}
.navlink{flex:0 0 auto;color:var(--muted);text-decoration:none;border:1px solid var(--line);
background:var(--panel2);padding:10px 12px;border-radius:999px;font-size:14px;min-height:44px;
display:inline-flex;align-items:center}
.navlink.active{color:#04121f;background:var(--acc);border-color:var(--acc);font-weight:700}
h1{font-size:24px;line-height:1.25;margin:20px 0 6px}
h2{font-size:20px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:17px;margin:20px 0 6px}
p,li{color:var(--txt)}
.sub{color:var(--muted);margin:0 0 14px}
.lede{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:16px 0}
.lede p{margin:8px 0}
.status{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.stat{flex:1 1 150px;background:var(--panel2);border:1px solid var(--line);border-radius:12px;
padding:12px}
.stat b{display:block;font-size:26px;line-height:1.1}
.stat span{color:var(--muted);font-size:13px}
.btnrow{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--acc);
color:#04121f;font-weight:700;text-decoration:none;border-radius:12px;padding:14px 16px;
min-height:48px;flex:1 1 240px}
.btn.ghost{background:var(--panel2);color:var(--txt);border:1px solid var(--line);font-weight:600}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.card .match{font-size:18px;font-weight:700;margin:0 0 4px}
.card .meta{color:var(--muted);font-size:13px;margin:0 0 10px}
.pick{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:8px 0}
.pick .who{font-size:20px;font-weight:800;color:var(--good)}
.pick .prob{font-size:20px;font-weight:700}
.bar{display:flex;height:14px;border-radius:999px;overflow:hidden;border:1px solid var(--line);
background:#0b1729;margin:8px 0 4px}
.bar i{display:block;height:100%}
.bar .a{background:#4c8dff}
.bar .b{background:#f0a35e}
.legend{display:flex;justify-content:space-between;color:var(--muted);font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{font-size:12.5px;border:1px solid var(--line);background:var(--panel2);border-radius:999px;
padding:4px 9px;color:var(--muted)}
.chip.warn{border-color:#6b4d18;color:var(--warn)}
.chip.bad{border-color:#6b2626;color:var(--bad)}
.chip.good{border-color:#1f5c46;color:var(--good)}
table{width:100%;border-collapse:collapse;font-size:14.5px;margin:10px 0}
th,td{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
a{color:var(--acc)}
.srclist{margin:8px 0 0;padding-left:18px}
.srclist li{margin:4px 0;font-size:13.5px;color:var(--muted)}
.note{border-left:3px solid var(--warn);background:var(--panel2);padding:10px 12px;border-radius:0 10px 10px 0;
margin:10px 0;font-size:14.5px}
.ok{border-left-color:var(--good)}
.badnote{border-left-color:var(--bad)}
details{margin:8px 0}
summary{cursor:pointer;font-weight:600;min-height:44px;display:flex;align-items:center}
.blank{color:var(--muted);font-style:italic}
.foot{margin-top:36px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:13px}
@media (max-width:520px){h1{font-size:21px}.stat b{font-size:22px}.btn{flex:1 1 100%}}
"""


def basis_chip(row: dict) -> str:
    basis = row["basis"]
    if basis == "market":
        return '<span class="chip good">Basis: bookmaker price</span>'
    if basis == "exchange":
        return '<span class="chip warn">Basis: exchange only (thin book)</span>'
    if basis == "model":
        return '<span class="chip warn">Basis: originated model line (no bookmaker price)</span>'
    return '<span class="chip bad">Unresolved: no price and no official rating</span>'


def source_list(row: dict) -> str:
    if not row.get("sources"):
        return '<li class="blank">no source link: this row is published as unverified</li>'
    items = []
    for s in row["sources"]:
        detail = f" — {e(s.get('detail'))}" if s.get("detail") else ""
        when = f" · read {e(s.get('read_utc'))}" if s.get("read_utc") else ""
        items.append(f'<li><a href="{e(s["url"])}" rel="noopener">{e(s.get("label") or s["url"])}</a>'
                     f"{detail}{when}</li>")
    return "".join(items)


def pct_span(row: dict) -> str:
    return (f'<span class="a" style="width:{row["prob_a"] * 100:.2f}%"></span>'
            f'<span class="b" style="width:{row["prob_b"] * 100:.2f}%"></span>')


def pick_card(row: dict, show_limits: bool = True) -> str:
    prob_a, prob_b = row.get("prob_a"), row.get("prob_b")
    bar = (f'<div class="bar" role="img" aria-label="{e(row["team_a"])} '
           f'{pct(prob_a)} versus {e(row["team_b"])} {pct(prob_b)}">{pct_span(row)}</div>'
           f'<div class="legend"><span>{e(row["team_a"])} {pct(prob_a)}</span>'
           f'<span>{e(row["team_b"])} {pct(prob_b)}</span></div>') if prob_a is not None else ""
    pick = (f'<div class="pick"><span class="who">{e(row["pick"])}</span>'
            f'<span class="prob">{pct(row.get("pick_probability"))}</span>'
            f'<span class="chip">{e(row.get("confidence"))}</span></div>'
            if row.get("pick") else '<p class="blank">No pick published for this fixture.</p>')
    flags = "".join(f'<span class="chip warn">{e(f)}</span>' for f in row.get("flags", []))
    limits = ""
    if show_limits and row.get("limitations"):
        limits = ("<details><summary>Limitations for this pick</summary><ul>"
                  + "".join(f"<li>{e(x)}</li>" for x in row["limitations"]) + "</ul></details>")
    return f"""<article class="card">
  <p class="match">{e(row['team_a'])} vs {e(row['team_b'])}</p>
  <p class="meta">{e(row['competition'])} · tier {e(row['tier'])} · kick-off {e(row['start_utc'])}
  · locks {e(row['lock_utc'])} · <a href="{e(row['hotspawn_url'])}" rel="noopener">HotSpawn listing</a></p>
  {pick}
  {bar}
  <div class="chips">{basis_chip(row)}{flags}</div>
  <details><summary>Sources behind this row ({len(row.get('sources') or [])})</summary>
    <ul class="srclist">{source_list(row)}</ul></details>
  {limits}
</article>"""


def picks_table(rows: list[dict]) -> str:
    """One line per fixture. Every row carries its own source links, as the project requires."""
    body = []
    for r in sorted(rows, key=lambda x: (x["start_utc"] or "")):
        body.append(
            f'<tr><td>{e(r["start_utc"])}</td><td>{e(r["competition"])}</td>'
            f'<td>{e(r["team_a"])} vs {e(r["team_b"])}</td>'
            f'<td><strong>{e(r.get("pick") or "—")}</strong></td>'
            f'<td>{pct(r.get("prob_a"))} / {pct(r.get("prob_b"))}</td>'
            f'<td>{e(r["basis"])}</td><td>{e(r.get("confidence"))}</td>'
            f'<td>{inline_sources(r, 3)}</td></tr>')
    return ('<div class="tablewrap"><table>'
            '<thead><tr><th scope="col">Kick-off (UTC)</th><th scope="col">Event</th>'
            '<th scope="col">Match</th><th scope="col">Pick</th>'
            '<th scope="col">Win % A / B</th><th scope="col">Basis</th>'
            '<th scope="col">Confidence</th><th scope="col">Sources</th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table></div>")


def pick_limit_line(row: dict, limit: int = 2) -> str:
    """One bullet for the executive summary's unresolved list, with its first limitations."""
    extras = "".join(f'<br><span class="blank">{e(x)}</span>'
                     for x in (row.get("limitations") or [])[:limit])
    return (f'<li><strong>{e(row["team_a"])} vs {e(row["team_b"])}</strong> '
            f'({e(row["competition"])}, {e(row["start_utc"])}) — '
            f'{e(row.get("pick") or "no pick published")} {pct(row.get("pick_probability"))} · '
            f'{e(row["unresolved_category"].replace("_", " "))}{extras}</li>')


def alias_line(row: dict, note: str) -> str:
    links = " · ".join(
        f'<a href="{e(u)}" rel="noopener">{e(u)}</a>' for u in row.get("alias_evidence", []))
    return (f'<li><strong>{e(row["team_a"])} vs {e(row["team_b"])}</strong> — {e(note)}<br>'
            f'<span class="blank">{links or "no evidence URL"}</span></li>')


def render_index(board: dict) -> str:
    s = board["summary"]
    no_market = board["no_market"]
    unresolved = board["unresolved"]
    exchange_only = [r for r in no_market if r["basis"] == "exchange"]
    model_only = [r for r in no_market if r["basis"] == "model"]
    gen = board["generated_utc"]
    links = "".join(
        f'<li><a href="{href}">{e(label)}</a> — {e(desc)}</li>' for href, label, desc in IN_SITE_LINKS)
    fresh = (f'{(core.parse_iso(gen) - core.parse_iso(board["snapshot_generated_utc"])).total_seconds() / 60:.1f}'
             if board.get("snapshot_generated_utc") else "?")
    limit_rows = []
    for r in no_market:
        limit_rows.append(pick_limit_line(r))
    body = f"""
<h1>Executive summary — every HotSpawn CS2 pick, and every gap</h1>
<p class="sub">Refreshed automatically every 4 hours with no manual input. This page is the front
door: it says what is covered, links straight to the picks, and lists the matches whose pick could
not be taken from a bookmaker price.</p>

<div class="lede">
  <p><strong>Coverage right now:</strong> {s['open_for_picks']} CS2 fixtures are open for picks on
  the HotSpawn lobby. <strong>{s['with_pick']}</strong> carry a published pick and win probability;
  {s['with_blank_pick']} are published blank and flagged.</p>
  <p>{s['resolved_by_market']} picks come from a two-way bookmaker price
  (Pinnacle, Bovada, Melbet/1xBet platform, or the Thunderpick coefficient bo3.gg publishes),
  {s['resolved_by_exchange_only']} from the Kalshi exchange order book only,
  and {s['resolved_by_originated_line']} are <strong>originated</strong> model lines because no
  bookmaker, exchange or aggregator reachable from the runner prices them.</p>
  <p><strong>Unresolved:</strong> {s['unresolved']} fixture(s) have no price and no official rating
  for both teams, so their numbers stay blank on purpose and they appear in the
  <a href="unresolved.html">Unresolved picks &amp; limitations</a> section below and in full.</p>
  <p class="blank">Last build {e(gen)} · lobby snapshot {e(board.get('snapshot_generated_utc'))}
  ({e(fresh)} minutes earlier) · quotes collected {s['quotes_collected']} ·
  {s['quotes_rejected_on_time']} quote(s) refused because the kick-off time disagreed.</p>
</div>

<div class="status">
  <div class="stat"><b>{s['open_for_picks']}</b><span>open CS2 fixtures</span></div>
  <div class="stat"><b>{s['resolved_by_market']}</b><span>bookmaker-priced picks</span></div>
  <div class="stat"><b>{s['resolved_by_exchange_only']}</b><span>exchange-only picks</span></div>
  <div class="stat"><b>{s['resolved_by_originated_line']}</b><span>originated (no price)</span></div>
  <div class="stat"><b>{s['unresolved']}</b><span>unresolved / blank</span></div>
</div>

<div class="btnrow">
  <a class="btn" href="picks.html">See the picks for every open match ({s['with_pick']})</a>
  <a class="btn ghost" href="unresolved.html">Unresolved picks &amp; limitations ({len(no_market)})</a>
</div>

<h2>Where the picks are, inside this site</h2>
<p>Every link below opens a list of picks that lives on this site. The first one is this section's
own every-match list; the others are the independent boards published by the other sessions in this
repository, kept because they use different, documented methods.</p>
<ul>{links}</ul>

<h2>Unresolved picks &amp; limitations</h2>
<p>A pick is <em>resolved the same way as the featured picks</em> when at least one licensed bookmaker
quotes a two-way price for that fixture, which lets the draw-free win probability be read straight
from the market. Everything else needs a second-best source or stays blank. The categories below are
the whole of that gap; the full page lists every row with its sources and read times.</p>
<ul>
  <li><strong>{s['resolved_by_exchange_only']} fixture(s) priced only by the Kalshi exchange.</strong>
  Limitation: an exchange mid is a market observation with no bookmaker behind it; when the two legs
  are more than 10 cents wide the book is labelled thin and the pick is marked low confidence.
  {"No such fixture right now." if not exchange_only else ""}
  <ul>{"".join(f'<li>{e(r["team_a"])} vs {e(r["team_b"])} — {e(r.get("pick") or "blank")} '
               f'{pct(r.get("pick_probability"))} · spread '
               f'{money((r.get("exchange") or {{}}).get("max_spread"))}</li>' for r in exchange_only)}</ul>
  </li>
  <li><strong>{s['resolved_by_originated_line']} fixture(s) with no market price at all.</strong>
  Limitation: the pick is an <em>originated</em> line — Valve's official VRS points through Valve's
  own Glicko slope, with the slope fitted on the market pairs seen in the same run. It is a model
  estimate, not a price, and it is labelled as such on every row.
  <ul>{"".join(f'<li>{e(r["team_a"])} vs {e(r["team_b"])} — {e(r.get("pick") or "blank")} '
               f'{pct(r.get("pick_probability"))}</li>' for r in model_only)}</ul>
  </li>
  <li><strong>{s['unresolved']} fixture(s) not resolved at all.</strong> Limitation: no price and no
  official rating exists for both teams, so the cells stay blank; the row is flagged for review and
  re-checked on every refresh.
  <ul>{"".join(f'<li>{e(r["team_a"])} vs {e(r["team_b"])} — {e(r["competition"])} '
               f'{e(r["start_utc"])}</li>' for r in unresolved) or "<li>None at this build.</li>"}</ul>
  </li>
</ul>
<div class="note badnote"><strong>The three structural limitations of the whole method</strong>
<ul>
  <li><strong>HLTV refuses the collection runner.</strong> Every automated read of
  <a href="https://www.hltv.org/betting/analytics" rel="noopener">hltv.org</a> returns HTTP 403 with
  a Cloudflare challenge, so HLTV can only be cited as a dated, interactive cross-check — its odds
  cannot be refreshed automatically. The per-run HTTP status is published on
  <a href="sources.html">Sources</a>.</li>
  <li><strong>Tier-C events are structurally thin.</strong> Low-tier CCT / Elisa / university events
  are listed by few books; when coverage exists it is often a single source, which is flagged per row.</li>
  <li><strong>Estimates are not guarantees.</strong> A no-vig probability derived from prices is a
  market observation, and an originated line is this project's own number.</li>
</ul></div>

<h2>What a pick is, on this page</h2>
<p>The pick is the team with the higher derived win probability, shown in bold with its percentage.
Both sides' probabilities are always printed, so the margin is visible. No pick is ever taken from
HotSpawn's crowd percentage, and no value is filled in by inference: where a source does not exist,
the cell is blank and the row is flagged.</p>

<h2>Unresolved rows at this build ({len(no_market)})</h2>
<ul>{''.join(limit_rows) or '<li>None: every open fixture has a bookmaker price at this build.</li>'}</ul>
"""
    return page("Executive summary", body, "index.html", board["generated_utc"],
                "Executive summary of every HotSpawn CS2 pick, with in-site links and the unresolved "
                "picks and their limitations.")


def render_picks(board: dict) -> str:
    rows = board["open"]
    cards = "".join(pick_card(r) for r in sorted(rows, key=lambda x: x["start_utc"] or ""))
    s = board["summary"]
    body = f"""
<h1>Picks for every open HotSpawn CS2 match</h1>
<p class="sub">{s['with_pick']} of {s['open_for_picks']} open fixtures carry a pick.
The bold team is the pick; the percentage is its win probability. Updated {e(board['generated_utc'])}.</p>
<div class="btnrow">
  <a class="btn ghost" href="unresolved.html">Fixtures without a bookmaker price ({len(board['no_market'])})</a>
  <a class="btn ghost" href="index.html">Back to the executive summary</a>
</div>
<h2>Cards (phone view)</h2>
{cards or '<p class="blank">No open fixture at this build.</p>'}
<h2>Table (one line per match)</h2>
{picks_table(rows)}
"""
    return page("All picks", body, "picks.html", board["generated_utc"],
                "Pick and win probability for every open HotSpawn CS2 fixture, mobile-first.")


def render_unresolved(board: dict) -> str:
    attempts = board.get("source_attempts") or []
    blocked = [a for a in attempts if a.get("status") and a["status"] != 200]
    ok = [a for a in attempts if a.get("status") == 200]
    groups = {
        "exchange":   [r for r in board["no_market"] if r["basis"] == "exchange"],
        "model":      [r for r in board["no_market"] if r["basis"] == "model"],
        "unresolved": board["unresolved"],
    }
    sections = []
    titles = {
        "exchange": ("Priced only by an exchange — not a bookmaker price",
                     "These fixtures have a two-sided Kalshi order book but no licensed bookmaker "
                     "quote reachable from the runner. The pick is taken from the exchange mid, the "
                     "bid/ask width is printed, and a book wider than 10 cents is labelled thin."),
        "model": ("No market price anywhere — resolved with an originated line",
                  "No bookmaker, exchange or aggregator reachable from the runner quotes these "
                  "fixtures. The pick is therefore **originated**: Valve's official VRS points "
                  "through Valve's own Glicko slope, with the slope fitted on the market pairs seen "
                  "in the same run. This is a model estimate, not a price."),
        "unresolved": ("Not resolved — cells stay blank and flagged",
                       "No price and no official rating for both teams. Nothing is inferred: the "
                       "probabilities stay empty and the row is re-checked on every refresh."),
    }
    for key in ("exchange", "model", "unresolved"):
        rows = groups[key]
        head, blurb = titles[key]
        if rows:
            cards = "".join(pick_card(r) for r in sorted(rows, key=lambda x: x["start_utc"] or ""))
        else:
            cards = '<p class="blank">No fixture in this category at this build.</p>'
        sections.append(f"<h2>{e(head)} ({len(rows)})</h2><p>{blurb}</p>{cards}")

    alias_rows = []
    for r in board["open"]:
        for note in r.get("alias_notes", []):
            alias_rows.append((r, note))
    alias_html = "".join(alias_line(r, note) for r, note in alias_rows) or (
        "<li>No alias was needed at this build.</li>")

    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="sub">The separate section for every open fixture whose pick is <strong>not</strong> a
bookmaker price, and for every fixture with no pick at all. Nothing here is filled in by inference;
each row carries the source links and read times that were actually used or actually refused.</p>

<div class="lede">
  <p><strong>Summary.</strong> {board['summary']['resolved_by_market']} of
  {board['summary']['open_for_picks']} open fixtures are resolved the same way as the featured picks
  (a two-way licensed-bookmaker price). {len(groups['exchange'])} are resolved from the exchange only,
  {len(groups['model'])} from an originated model line, and {len(groups['unresolved'])} are not
  resolved at all.</p>
  <p><strong>Order of investigation, applied per fixture:</strong> HLTV first, then esportsbooks and
  esports betting lines, then the official Valve ratings as the documented last resort.</p>
</div>

<h2>What was tried, and what answered</h2>
<div class="tablewrap"><table>
<thead><tr><th scope="col">Source</th><th scope="col">Result this run</th>
<th scope="col">Read at (UTC)</th><th scope="col">Note</th></tr></thead><tbody>
{"".join(f'<tr><td><a href="{e(a["url"])}" rel="noopener">{e(a["url"])}</a></td>'
         f'<td>{e(a["status"] if a["status"] is not None else "no response")}</td>'
         f'<td>{e(a["at_utc"])}</td><td>{e(a["note"])}</td></tr>' for a in attempts)}
</tbody></table></div>
<p class="blank">{len(ok)} source read(s) answered with HTTP 200 and {len(blocked)} refused
({", ".join(sorted({str(a["status"]) for a in blocked})) or "none"}). A refusal is published as a
refusal: it never becomes a "no such price" claim.</p>

{''.join(sections)}

<h2>Fixtures in the categories above, line by line</h2>
{picks_table(board["no_market"]) if board["no_market"] else '<p class="blank">None.</p>'}

<h2>Team-name equivalences used to resolve these rows</h2>
<p>A pick is only joined when the two listings agree on both teams and the kick-off time. Where a
source spells a roster differently, the equivalence is listed here with its evidence; if the evidence
is not there, the join is refused and the row stays in this section.</p>
<ul>{alias_html}</ul>

<h2>Quotes refused because the kick-off time disagreed ({len(board['rejected_joins'])})</h2>
<p class="blank">These are prices that exist for the same team pairing but at a different time. They
are published here instead of being joined silently.</p>
<div class="tablewrap"><table>
<thead><tr><th scope="col">Fixture</th><th scope="col">Source</th><th scope="col">Source listing</th>
<th scope="col">HotSpawn kick-off</th><th scope="col">Source kick-off</th>
<th scope="col">Difference (h)</th></tr></thead><tbody>
{"".join(f'<tr><td>{e(r["match"])}</td><td>{e(r["source_key"])}</td>'
         f'<td><a href="{e(r["source_url"])}" rel="noopener">{e(r["source_match"])}</a></td>'
         f'<td>{e(r["fixture_start_utc"])}</td><td>{e(r["source_start_utc"])}</td>'
         f'<td>{e(r["start_diff_h"])}</td></tr>' for r in board["rejected_joins"][:60])}
</tbody></table></div>
"""
    return page("Unresolved picks & limitations", body, "unresolved.html", board["generated_utc"],
                "Every HotSpawn CS2 fixture whose pick is not a bookmaker price, with the limitation "
                "that caused it and the sources that were tried.")


def render_sources(board: dict) -> str:
    attempts = board.get("source_attempts") or []
    quotes = board["summary"]["sources_by_key"]
    rows = "".join(
        f'<tr><td>{e(a["key"])}</td><td><a href="{e(a["url"])}" rel="noopener">{e(a["url"])}</a></td>'
        f'<td>{e(a["status"] if a["status"] is not None else "no response")}</td>'
        f'<td>{e(a["bytes"])}</td><td>{e(a["at_utc"])}</td><td>{e(a["note"])}</td></tr>'
        for a in attempts)
    vrs = board.get("vrs") or {}
    body = f"""
<h1>Sources, and how this build read them</h1>
<p class="sub">Every source used or attempted in the build at {e(board['generated_utc'])}, with the
HTTP status, byte count and UTC read time the runner observed. A source that refuses the runner is
listed as a refusal.</p>

<h2>Prices that survived the join</h2>
<div class="tablewrap"><table>
<thead><tr><th scope="col">Source</th><th scope="col">Quotes collected</th>
<th scope="col">What it is</th></tr></thead><tbody>
<tr><td><a href="https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups" rel="noopener">Pinnacle</a></td><td>{quotes.get('pinnacle', 0)}</td><td>Licensed bookmaker, public guest odds API (moneyline, period 0, open, pre-match)</td></tr>
<tr><td><a href="https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2" rel="noopener">Bovada</a></td><td>{quotes.get('bovada', 0)}</td><td>Licensed bookmaker, public coupon JSON</td></tr>
<tr><td><a href="https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&amp;count=1000&amp;lng=en&amp;mode=4&amp;country=1" rel="noopener">Melbet / 1xBet platform</a></td><td>{quotes.get('melbet', 0)}</td><td>Licensed bookmaker LineFeed shared by Melbet, 22bet and Betwinner</td></tr>
<tr><td><a href="https://bo3.gg/matches/current" rel="noopener">Thunderpick (via bo3.gg)</a></td><td>{quotes.get('thunderpick', 0)}</td><td>Title-sponsor bookmaker coefficients bo3.gg publishes per fixture</td></tr>
<tr><td><a href="https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&amp;status=open&amp;with_nested_markets=true&amp;limit=200" rel="noopener">Kalshi</a></td><td>{quotes.get('kalshi', 0)}</td><td>CFTC-regulated exchange, series KXCS2GAME; bid/ask kept per leg</td></tr>
<tr><td><a href="{e(vrs.get('source_url') or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}" rel="noopener">Valve VRS</a></td><td>{vrs.get('teams')} teams</td><td>Official global standings ({e(vrs.get('snapshot'))}) used only to originate a line</td></tr>
</tbody></table></div>

<h2>Every request in this build</h2>
<div class="tablewrap"><table>
<thead><tr><th scope="col">Key</th><th scope="col">URL</th><th scope="col">Status</th>
<th scope="col">Bytes</th><th scope="col">Read at (UTC)</th><th scope="col">Note</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<h2>Why HLTV is a dated cross-check and not an automated input</h2>
<p>HLTV carries these fixtures and publishes bookmaker odds on its analytics pages, but every
automated request from the collection runner is answered with HTTP&nbsp;403 and a Cloudflare
challenge — including <a href="https://www.hltv.org/matches" rel="noopener">/matches</a>,
<a href="https://www.hltv.org/betting/analytics" rel="noopener">/betting/analytics</a> and the
per-match analytics pages. The status above is from this build. The interactive reads that were
possible are cited with their own read times on the pages that use them, and are never mixed into an
automated probability.</p>

<h2>Sources deliberately not used</h2>
<ul>
  <li><strong>HotSpawn's own crowd "picked %"</strong> — never read, stored, or used as an input. It
  is a crowd opinion, not a price.</li>
  <li><strong>Bovada's "consensus" widgets and any tipster page</strong> — opinions, not prices.</li>
  <li><strong>Sources that refuse the runner</strong> (HLTV, Thunderpick's own site, EGamersWorld,
  GG.BET, Stake, Betano, VBET, Parimatch) — recorded as refusals, never as missing prices.</li>
</ul>
"""
    return page("Sources", body, "sources.html", board["generated_utc"],
                "Source ledger for the HotSpawn CS2 picks build, including refused sources.")


def inline_sources(row: dict, limit: int = 4) -> str:
    """Compact, escaped source links for a flag line."""
    links = []
    for s in (row.get("sources") or [])[:limit]:
        url = s.get("url")
        if not url:
            continue
        links.append(f'<a href="{e(url)}" rel="noopener">{e(str(url)[:80])}</a>')
    return " · ".join(links) or "no source link"


def render_flagged(board: dict) -> str:
    items: list[str] = []
    for r in board["open"]:
        if r["basis"] != "market":
            items.append(
                f'<li><strong>{e(r["team_a"])} vs {e(r["team_b"])}</strong> '
                f'({e(r["competition"])}, {e(r["start_utc"])}) — '
                f'{e(r["unresolved_category"].replace("_", " "))}: '
                + "; ".join(e(x) for x in r.get("limitations", []))
                + f'<br><span class="blank">Sources: {inline_sources(r)}</span></li>')
        for flag in r.get("flags", []):
            if flag == "bookmaker_disagreement_over_10_points":
                items.append(f'<li><strong>{e(r["team_a"])} vs {e(r["team_b"])}</strong> — bookmaker '
                             f'disagreement wider than 10 probability points '
                             f'({pct((r.get("market") or {}).get("min_a"))} to '
                             f'{pct((r.get("market") or {}).get("max_a"))}). Re-check before use.</li>')
    thin = [k for k in board.get("kalshi_not_usable", [])]
    for t in thin[:20]:
        items.append(f'<li><strong>{e(t.get("team_a"))} vs {e(t.get("team_b"))}</strong> — Kalshi '
                     f'market {e(t.get("event_id"))} refused: {e(t.get("reason"))}. '
                     f'<a href="{e(t.get("public_url"))}" rel="noopener">Exchange market</a></li>')
    for r in board["rejected_joins"][:40]:
        items.append(f'<li><strong>{e(r["match"])}</strong> — a {e(r["source_key"])} price for '
                     f'"{e(r["source_match"])}" was refused: {e(r["reason"])} '
                     f'(HotSpawn {e(r["fixture_start_utc"])} vs source {e(r["source_start_utc"])}). '
                     f'<a href="{e(r["source_url"])}" rel="noopener">Source</a></li>')
    permalink_gaps = [r for r in board["open"] if r.get("hotspawn_url_kind") != "match page"]
    for r in permalink_gaps:
        items.append(f'<li><strong>{e(r["team_a"])} vs {e(r["team_b"])}</strong> — HotSpawn publishes '
                     f'no per-match permalink for this fixture, so the row links to the official '
                     f'lobby page instead. <a href="{e(r["hotspawn_url"])}" rel="noopener">Lobby</a></li>')
    body = f"""
<h1>Flagged for review</h1>
<p class="sub">Everything in this build that is not a plain, fully sourced price, published with its
link so it can be checked by hand. Flagged items do not block the publication of the picks.</p>
<h2>Items ({len(items)})</h2>
<ul>{''.join(items) or '<li>Nothing flagged at this build.</li>'}</ul>
<h2>Standing irregularities inherited from earlier sessions (not re-verified here)</h2>
<ul>
  <li>The landing page and the other session boards count coverage differently (13 / 14 / 15 / 23
  bookmaker-priced open fixtures were reported for the same lobby at different snapshot times, each
  with its own acceptance rule). This page publishes its own rule and its own timestamp; the
  reconciliation is described in <a href="method.html">Method</a>.</li>
  <li>HotSpawn's fixtures carry no published best-of for most rows (<span class="blank">best_of: null</span>),
  so a two-way match-winner market is the only market type used here.</li>
  <li>Kalshi event tickers encode US Eastern time without stating the offset; the offset is used only
  to widen the join window and is never displayed as a kick-off time.</li>
</ul>
"""
    return page("Flagged for review", body, "flagged.html", board["generated_utc"],
                "Flagged items for the HotSpawn CS2 picks build: thin books, aliases, rejected joins.")


def render_method(board: dict) -> str:
    cal = board.get("calibration") or {}
    s = board["summary"]
    body = f"""
<h1>Method, formulas and limits</h1>
<p class="sub">Short enough to check by hand. Every number on this site is reproduced from the
sources listed on the row that shows it.</p>

<h2>1. Fixtures</h2>
<p>The open list is read from the exact fixture response the public HotSpawn lobby page embeds. A
fixture is <em>open</em> while its published lock time has not passed and it has no winner. The
crowd "picked %" that the lobby also publishes is refused by the parser: it never reaches a table, a
model or a percentage.</p>

<h2>2. Prices</h2>
<p>Quotes are collected from public, unauthenticated endpoints only: Pinnacle's guest odds API,
Bovada's coupon JSON, the 1xBet-platform LineFeed (Melbet / 22bet / Betwinner), Kalshi's trade API
and the Thunderpick coefficient bo3.gg publishes per fixture. American odds are converted with
<span class="blank">decimal = 1 + price/100</span> (positive) or
<span class="blank">1 + 100/|price|</span> (negative); decimal prices are used as published.</p>

<h2>3. From a price to a probability</h2>
<p>For a two-way market the implied shares are <span class="blank">q = 1/odds</span> and the
bookmaker margin is removed proportionally:
<span class="blank">p = q<sub>a</sub> / (q<sub>a</sub> + q<sub>b</sub>)</span>. Where several
sources quote the same fixture the published market number is the <strong>median</strong> of the
per-source no-vig probabilities, and the minimum, maximum and width are printed. Quotes are joined
only when the canonical team names match as a pair <em>and</em> the kick-off times agree inside
{MATCH_WINDOW_TEXT}; anything else is refused and listed on
<a href="unresolved.html">Unresolved &amp; limits</a>.</p>

<h2>4. The originated line (only where no market exists)</h2>
<p>Where no reachable market prices a fixture, the line is originated from Valve's official global
standings: <span class="blank">p<sub>a</sub> = σ(k · C · (Pa − Pb))</span> with Valve's own Glicko
constants and a slope <span class="blank">k</span> fitted through the origin on the market pairs seen
in the same run (bounds {cal.get('bounds')}, minimum {cal.get('min_pairs')} pairs). This run used
<strong>k = {cal.get('k')}</strong> from {cal.get('n_pairs')} pair(s)
({"fitted" if cal.get("fitted") else "not fitted — Valve's published slope k = 1 was used"}).
The result is labelled an <em>originated model line</em> on every row; it is not a bookmaker price and
no bookmaker is quoting it.</p>

<h2>5. What the pick is</h2>
<p>The pick is the team with the higher probability. Confidence labels are derived from the distance
to 50%: ≥30 points Strong, ≥15 Solid, ≥5 Lean, otherwise Toss-up; an exchange-only row is capped at
"thin exchange book".</p>

<h2>6. Refresh cadence and no manual input</h2>
<p>The GitHub Actions workflow <span class="blank">exec-b1fb1465</span> runs every 4 hours and
commits the refreshed data and pages in one commit; nothing in this section needs to be typed in.
This build: {s['open_for_picks']} open fixtures, {s['quotes_collected']} quotes collected,
{s['with_pick']} picks published, {s['unresolved']} left blank and flagged.</p>

<h2>7. Reconciliation with the other boards on this site</h2>
<p>Different sessions publish different counts for the same lobby, because each counts "priced" by its
own rule and its own snapshot time. This section states its rule explicitly: <strong>market</strong> =
at least one licensed bookmaker two-way price joined by team pair plus kick-off inside three hours;
<strong>exchange</strong> = Kalshi order book only; <strong>originated</strong> = no price;
<strong>unresolved</strong> = no price and no official rating. Rows that another board publishes as
blank may therefore appear here as an originated line, and rows another board prices from a source
that refuses this runner may appear here as exchange-only or originated. Both facts are printed per
row rather than reconciled into a single opaque number.</p>

<h2>8. Standing limitations</h2>
<ul>
  <li>HLTV refuses the collection runner (HTTP 403), so its odds cannot refresh automatically; the
  refusal is republished on <a href="sources.html">Sources</a> every run.</li>
  <li>Tier-C events have structurally thin coverage; single-source rows are flagged.</li>
  <li>Probabilities derived from prices are market observations, not forecasts; originated lines are
  this project's own numbers.</li>
  <li>No value is inferred. A missing source leaves the cell blank and the row flagged.</li>
</ul>
"""
    return page("Method", body, "method.html", board["generated_utc"],
                "Formulas, join rules, refresh cadence and limits for the HotSpawn CS2 picks section.")


MATCH_WINDOW_TEXT = "three hours"


def main() -> int:
    board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "assets" / "exec.css").write_text(CSS, encoding="utf-8")
    pages = {
        "index.html": render_index(board),
        "picks.html": render_picks(board),
        "unresolved.html": render_unresolved(board),
        "sources.html": render_sources(board),
        "flagged.html": render_flagged(board),
        "method.html": render_method(board),
    }
    for name, text in pages.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote exec/ ({len(pages)} pages) from board {board['generated_utc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
