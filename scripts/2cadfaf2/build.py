#!/usr/bin/env python3
"""Session 2cadfaf2 site builder — the mobile pick centre (``pickcenter/``).

Reads only ``data/2cadfaf2/board.json``; writes ``pickcenter/*.html``. Every number on every page
is copied from the board, every row links the official page it came from, and a value that is
missing is rendered as an explicit blank with a link to the Unresolved page — never as a guess.

Pages
-----
index.html      executive summary: what is covered, what is not, and one-tap links to every list
picks.html      every listed match, open ones first, one card per match with both probabilities
unresolved.html the separate "Unresolved picks & limitations" section
sources.html    source ledger: what was read, when, HTTP status, and the row-level quote ledger
results.html    the pick ledger, graded only where a pre-lock pick was recorded
flagged.html    irregularities for review
method.html     the ladder, the formula, the policy and the tests
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "data/2cadfaf2" / "board.json"
OUT = ROOT / "pickcenter"
LOBBY = "https://play.hotspawn.com/lobby"

CSS = """
:root{--bg:#0a1019;--card:#131c2b;--card2:#18233a;--ink:#eef4fc;--mut:#a2b3cc;--grn:#3ee08f;
--amb:#ffcf7d;--red:#ff9d9d;--blu:#8cc9ff;--line:#26374f;--chip:#1d2b43;--violet:#c3a8ff}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;padding-bottom:78px}
a{color:var(--blu)}
.wrap{max-width:980px;margin:0 auto;padding:12px 14px 34px}
header.top{position:sticky;top:0;z-index:30;background:#0b1320f2;border-bottom:1px solid var(--line);backdrop-filter:blur(8px)}
header.top .in{max-width:980px;margin:0 auto;padding:9px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.logo{font-weight:800;font-size:18px;color:var(--ink);text-decoration:none;letter-spacing:.2px}
.logo b{color:var(--grn)}
nav.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
nav.tabs a{min-height:42px;display:inline-flex;align-items:center;padding:7px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none;font-size:14.5px;background:var(--card)}
nav.tabs a.on{background:var(--grn);color:#052416;font-weight:800;border-color:var(--grn)}
nav.bottom{position:fixed;left:0;right:0;bottom:0;z-index:40;background:#0b1320fa;border-top:1px solid var(--line);display:none}
nav.bottom a{flex:1;text-align:center;color:var(--ink);text-decoration:none;padding:10px 2px 12px;font-size:13px;min-height:58px;display:flex;flex-direction:column;justify-content:center;gap:2px}
nav.bottom a.on{color:var(--grn);font-weight:800}
nav.bottom span.ico{font-size:17px;line-height:1}
h1{font-size:27px;line-height:1.22;margin:12px 0 6px;letter-spacing:-.2px}
h2{font-size:21px;margin:26px 0 8px}
h3{font-size:18px;margin:0 0 6px}
p{margin:8px 0}
.lede{color:var(--mut);font-size:16.5px}
.stamp{font-size:14px;color:var(--mut)}
.hero{background:linear-gradient(165deg,#0d2c1f,#11203a);border:2px solid var(--grn);border-radius:16px;padding:16px;margin:14px 0}
.hero h1{margin-top:0}
.cta{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:58px;background:var(--grn);color:#052416;font-weight:800;font-size:18px;text-decoration:none;border-radius:13px;padding:14px 16px;margin:10px 0 6px}
.cta small{display:block;font-weight:600;font-size:13.5px;color:#08492c}
.cta.alt{background:var(--card);color:var(--ink);border:1px solid var(--line)}
.cta.alt small{color:var(--mut)}
.cta.warn{background:#2a200f;color:var(--amb);border:1px solid var(--amb)}
.cta.warn small{color:#e7c68f}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px;text-align:center}
.stat b{display:block;font-size:25px;line-height:1.2}
.stat span{font-size:12.5px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px;margin:11px 0}
.card.open{border-left:4px solid var(--grn)}
.card.closed{opacity:.94}
.rowtop{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.chip{display:inline-block;border-radius:999px;padding:2px 9px;font-size:12.5px;font-weight:700;border:1px solid var(--line);background:var(--chip);white-space:nowrap}
.chip.open{background:#0f3a25;border-color:var(--grn);color:#a9f7cd}
.chip.live{background:#3a1d12;border-color:#ff9d5c;color:#ffc79f}
.chip.closed{color:var(--mut)}
.chip.market{border-color:var(--grn);color:#a9f7cd}
.chip.model{border-color:var(--violet);color:#ded0ff}
.chip.bound{border-color:var(--amb);color:var(--amb)}
.chip.blank{border-color:var(--red);color:var(--red)}
.when{font-size:13.5px;color:var(--mut)}
.pickline{font-size:17px;margin:4px 0 8px}
.pickline b{background:#0f3a25;border:1px solid var(--grn);color:#c8ffe4;border-radius:999px;padding:2px 10px}
.pickline .pc{font-weight:800;color:var(--grn)}
.bar{display:flex;height:30px;border-radius:9px;overflow:hidden;border:1px solid var(--line);font-size:12.5px;font-weight:700;margin:6px 0 4px}
.bar i{display:flex;align-items:center;padding:0 7px;font-style:normal;white-space:nowrap;overflow:hidden}
.bar .a{background:#173f2c;color:#c6ffe1}
.bar .b{background:#3b2c12;color:#ffe6b6;justify-content:flex-end}
.meta{font-size:13.5px;color:var(--mut)}
details{background:var(--card2);border:1px solid var(--line);border-radius:11px;padding:9px 12px;margin:9px 0 2px}
summary{cursor:pointer;font-weight:700;min-height:40px;display:flex;align-items:center;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:14.5px;margin:8px 0}
th,td{border:1px solid var(--line);padding:7px 8px;vertical-align:top;text-align:left}
th{background:var(--card2);font-size:13px;text-transform:uppercase;letter-spacing:.3px;color:var(--mut)}
code{background:#08101a;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:13px;word-break:break-all}
.note{background:#101a29;border:1px solid var(--line);border-radius:11px;padding:11px 13px;margin:10px 0;font-size:15px}
.warnbox{background:#2a200f;border:1px solid var(--amb);border-radius:12px;padding:11px 13px;margin:10px 0}
.errbox{background:#2b1418;border:1px solid var(--red);border-radius:12px;padding:11px 13px;margin:10px 0}
.okbox{background:#0e2b1c;border:1px solid var(--grn);border-radius:12px;padding:11px 13px;margin:10px 0}
.links a{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:52px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 13px;margin:8px 0;color:var(--ink);text-decoration:none}
.links a small{display:block;color:var(--mut);font-size:13.5px}
.links a b{font-size:16.5px}
.dayhead{position:sticky;top:54px;z-index:10;background:#0b1320f4;padding:8px 2px;margin:18px 0 4px;font-weight:800;font-size:15.5px;color:var(--grn);border-bottom:1px solid var(--line)}
.blank{color:var(--red);font-weight:700}
.small{font-size:13.5px;color:var(--mut)}
footer{color:var(--mut);font-size:13.5px;margin-top:30px;border-top:1px solid var(--line);padding-top:12px}
@media(max-width:780px){
 body{font-size:16.5px}nav.tabs{display:none}nav.bottom{display:flex}
 table,thead,tbody,tr,th,td{display:block;width:100%}
 thead{display:none}tr{background:var(--card);border:1px solid var(--line);border-radius:11px;margin:9px 0;padding:4px}
 th,td{border:none;padding:5px 7px}td:before{content:attr(data-h) " ";font-weight:700;color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
 td.noH:before{content:""}.stats{grid-template-columns:1fr 1fr}.dayhead{top:50px}
}
"""

NAV = [("index.html", "Summary"), ("picks.html", "All picks"), ("unresolved.html", "Unresolved"),
       ("sources.html", "Sources"), ("results.html", "Results"), ("flagged.html", "Flagged"),
       ("method.html", "Method")]
BOTTOM = [("picks.html", "Picks", "\U0001F3AF"), ("unresolved.html", "Unresolved", "\u26A0"),
          ("sources.html", "Sources", "\U0001F517"), ("index.html", "Summary", "\U0001F4CB")]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def load_board() -> dict:
    return json.loads(BOARD.read_text(encoding="utf-8"))


def when(iso: str | None, with_date: bool = True) -> str:
    if not iso:
        return "no published time"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return str(iso)
    if with_date:
        return dt.strftime("%a %d %b · %H:%M UTC")
    return dt.strftime("%H:%M UTC")


def cap(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return str(iso)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def page(title: str, active: str, body: str, board: dict) -> str:
    on = ' class="on"'
    nav = "".join(
        '<a href="%s"%s>%s</a>' % (href, on if href == active else "", esc(label))
        for href, label in NAV)
    bottom = "".join(
        '<a href="%s"%s><span class="ico" aria-hidden="true">%s</span>%s</a>'
        % (href, on if href == active else "", ico, esc(label))
        for href, label, ico in BOTTOM)
    mode = board.get("mode")
    badge = ("live capture" if mode == "live" else "committed capture — not a live read")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a1019">
<title>{esc(title)} · HotSpawn CS2 Pick Center</title>
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="in">
<a class="logo" href="index.html">Pick<b>Center</b></a>
<nav class="tabs">{nav}</nav>
</div></header>
<main class="wrap">
<div class="stamp">Captured {esc(cap(board.get("captured_utc")))} · {esc(badge)} · refreshed every 4 hours</div>
{body}
<footer>
<p><strong>Sources.</strong> Fixtures and lock times: the official HotSpawn lobby
(<a href="{LOBBY}">play.hotspawn.com/lobby</a>). Prices: Pinnacle, Bovada, Melbet and the Kalshi
exchange, each linked on the row it prices. Ratings: Valve's official Regional Standings
(<a href="https://github.com/ValveSoftware/counter-strike_regional_standings">github.com/ValveSoftware/counter-strike_regional_standings</a>).
HotSpawn crowd percentages are never used.</p>
<p>Estimates, not guarantees. 18+. If a value is not on a row, it was not verified — the row links
the <a href="unresolved.html">Unresolved &amp; limitations</a> section instead of guessing.</p>
</footer>
</main>
<nav class="bottom" aria-label="Sections">{bottom}</nav>
</body>
</html>
"""


# ------------------------------------------------------------------------------- components
STATE_CHIP = {
    "open": ("open", "Open for picks"),
    "locked": ("closed", "Locked"),
    "in_play": ("live", "In play"),
    "final": ("closed", "Final"),
    "void": ("closed", "Void"),
    "stale": ("closed", "Listed · kickoff past"),
    "past": ("closed", "Past"),
    "awaiting": ("closed", "Awaiting time"),
}
BASIS = {"market": ("market", "Market line"), "model": ("model", "VRS model"),
         "bound_lo": ("bound", "Lower bound")}


def source_links(row: dict) -> str:
    links = [f'<a href="{esc(row["hotspawn_url"])}">HotSpawn fixture ({esc(row["hotspawn_url_kind"])})</a>']
    for q in row.get("quotes") or []:
        if q.get("public_url"):
            links.append(f'<a href="{esc(q["public_url"])}">{esc(q.get("source_name") or q.get("source_key"))}'
                         f' price</a>')
    for side in ("team_a", "team_b"):
        rating = (row.get("vrs") or {}).get(side)
        if rating and rating.get("page_url"):
            links.append(f'<a href="{esc(rating["page_url"])}">Valve standings '
                         f'(#{esc(rating.get("standing"))} {esc(rating.get("team"))})</a>')
    return " · ".join(dict.fromkeys(links))


def quote_rows(row: dict) -> str:
    if not row.get("quotes"):
        return '<p class="small">No external price joined this fixture.</p>'
    out = ["<table><thead><tr><th>Source</th><th>Price at source (A / B)</th>"
           "<th>De-vigged (A / B)</th><th>Read</th><th>Link</th></tr></thead><tbody>"]
    for q in row["quotes"]:
        out.append(
            f'<tr><td data-h="Source">{esc(q.get("source_name"))}</td>'
            f'<td data-h="Price">{esc(q.get("raw_a"))} / {esc(q.get("raw_b"))} '
            f'({esc(q.get("raw_format"))})</td>'
            f'<td data-h="De-vigged">{pct(q.get("prob_a"))} / {pct(q.get("prob_b"))}</td>'
            f'<td data-h="Read">{esc(q.get("retrieved_utc"))} · {esc(q.get("age_hours"))}h old</td>'
            f'<td data-h="Link"><a href="{esc(q.get("public_url"))}">source</a></td></tr>')
    out.append("</tbody></table>")
    if any(q.get("alias") for q in row["quotes"]):
        alias = next(q["alias"] for q in row["quotes"] if q.get("alias"))
        out.append('<p class="small"><strong>Identity decision:</strong> '
                   f'{esc(alias["display"])} (verified {esc(alias["verified_utc"])}). '
                   + " · ".join(f'<a href="{esc(u)}">evidence</a>' for u in alias["evidence"]) + "</p>")
    return "".join(out)


def detail_block(row: dict) -> str:
    rating_bits = []
    for side in ("team_a", "team_b"):
        team = row.get(side)
        rating = (row.get("vrs") or {}).get(side)
        if rating:
            rating_bits.append(f'{esc(team)}: Valve #{esc(rating.get("standing"))} · '
                               f'{esc(rating.get("points"))} pts · roster {esc(rating.get("roster"))}')
        else:
            rating_bits.append(f"{esc(team)}: not in Valve's standings (unrated)")
    detail = []
    line = row.get("line") or {}
    if line.get("detail"):
        for key, value in line["detail"].items():
            if value is None:
                continue
            detail.append(f"{esc(key.replace('_', ' '))}: <code>{esc(value)}</code>")
    flags = ", ".join(esc(f) for f in row.get("flags") or []) or "none"
    return f"""<details>
<summary>Sources, ratings and flags for this match</summary>
<p class="small">{source_links(row)}</p>
{quote_rows(row)}
<p class="small">{'<br>'.join(rating_bits)}</p>
{f'<p class="small">{"; ".join(detail)}</p>' if detail else ''}
<p class="small">Flags: {flags}</p>
</details>"""


def match_card(row: dict) -> str:
    line = row.get("line")
    state = row.get("state")
    cls, label = STATE_CHIP.get(state, ("closed", state))
    basis_cls, basis_label = BASIS.get((line or {}).get("basis"), ("blank", "No verified line"))
    tier = f'{esc(row.get("tier"))} tier' if row.get("tier") else "tier n/a"
    points = f'{esc(row.get("points"))} pts' if row.get("points") is not None else "points n/a"
    head = (f'<div class="rowtop"><span class="chip {cls}">{esc(label)}</span>'
            f'<span class="chip">{tier} · {points}</span>'
            f'<span class="chip {basis_cls}">{esc(basis_label)}</span>'
            f'<span class="when">Lock {esc(when(row.get("lock_utc")))}</span></div>')
    title = f'<h3>{esc(row.get("team_a"))} <span class="small">vs</span> {esc(row.get("team_b"))}</h3>'
    comp = f'<div class="when">{esc(row.get("competition"))} · fixture {esc(row.get("fixture_id"))}</div>'
    if line:
        bar = (f'<div class="bar"><i class="a" style="width:{line["prob_a"] * 100:.1f}%">'
               f'{esc(row.get("team_a"))} {pct(line["prob_a"])}</i>'
               f'<i class="b" style="width:{line["prob_b"] * 100:.1f}%">'
               f'{esc(row.get("team_b"))} {pct(line["prob_b"])}</i></div>')
        body = (f'<div class="pickline">Pick <b>{esc(line["pick_team"])}</b> '
                f'<span class="pc">{pct(line["pick_prob"])}</span></div>{bar}'
                f'<div class="meta">{esc(basis_label)} · {esc(line.get("confidence"))} · '
                f'fair odds {esc(line.get("fair_decimal_a"))} / {esc(line.get("fair_decimal_b"))}'
                f'{(" · " + esc(line["assumption"])) if line.get("assumption") else ""}</div>')
    else:
        body = ('<p class="pickline"><span class="blank">— no verified probability</span></p>'
                '<p class="meta">Not guessed. The missing evidence is named on the '
                '<a href="unresolved.html">Unresolved &amp; limitations</a> page.</p>')
    result = ""
    if row.get("winner") in ("a", "b"):
        result = (f'<p class="meta">Result: <strong>'
                  f'{esc(row["team_a"] if row["winner"] == "a" else row["team_b"])}</strong> won.</p>')
    return (f'<article class="card {"open" if state == "open" else "closed"}">{head}{title}{comp}'
            f'{body}{result}{detail_block(row)}</article>')


# ----------------------------------------------------------------------------------- pages
def exec_summary(b: dict) -> str:
    s = b["summary"]
    t = b.get("tally") or {}
    open_rows = [r for r in b["rows"] if r["state"] == "open"]
    next_lock = min((r for r in open_rows if r.get("lock_utc")), key=lambda r: r["lock_utc"], default=None)
    unresolved = b.get("unresolved") or []
    mode_note = ""
    if b.get("mode") != "live":
        mode_note = ('<div class="warnbox"><strong>This build used the last committed capture, not a live '
                     'read.</strong> The runner recorded the failed fetch on the '
                     '<a href="sources.html">Sources</a> page; the four-hourly workflow replaces it '
                     'with a live capture on its next successful run. Treat every time below as the '
                     f'capture time ({esc(cap(b.get("captured_utc")))}).</div>')
    unr_rows = "".join(
        f'<tr><td data-h="Match">{esc(u["team_a"])} vs {esc(u["team_b"])}'
        f'<br><span class="small">{esc(u["competition"])} · <a href="{esc(u["hotspawn_url"])}">fixture</a></span></td>'
        f'<td data-h="When">{esc(when(u.get("start_utc")))}</td>'
        f'<td data-h="Why no pick">{esc(u["reason"])}</td></tr>'
        for u in unresolved) or ('<tr><td class="noH" colspan="3">Nothing unresolved in this capture.</td></tr>')
    return f"""
<div class="hero">
<h1>Every CS2 match on HotSpawn — one pick, two probabilities, one page</h1>
<p class="lede">This desk covers <strong>every fixture the HotSpawn Pick'ems lobby lists for the
current week</strong>, not just the handful that a bookmaker prices. Each row carries the pick, both
teams' win probability, the basis it came from and a link to the official page behind it. Rows that
cannot be resolved are named, with the reason, instead of being filled in.</p>
<a class="cta" href="picks.html"><span><strong>See every pick</strong><small>{s["with_pick"]} of {s["total_rows"]} listed matches resolved · {s["open"]} open now</small></span><span aria-hidden="true">→</span></a>
<a class="cta alt" href="unresolved.html"><span><strong>Unresolved &amp; limitations</strong><small>{s["unresolved"]} matches with no verified basis, and what limits the rest</small></span><span aria-hidden="true">→</span></a>
</div>
{mode_note}
<div class="stats">
<div class="stat"><b>{s["listed_in_lobby"]}</b><span>CS2 matches listed by the lobby this week</span></div>
<div class="stat"><b>{s["open"]}</b><span>still open for picks</span></div>
<div class="stat"><b>{s["open_with_pick"]}/{s["open"]}</b><span>open matches with a pick</span></div>
<div class="stat"><b>{s["with_pick"]}</b><span>matches with a pick &amp; both probabilities</span></div>
<div class="stat"><b>{s["market_rows"]}</b><span>from real book / exchange prices</span></div>
<div class="stat"><b>{s["model_rows"]}</b><span>originated from Valve ratings</span></div>
<div class="stat"><b>{s["bound_rows"]}</b><span>published as explicit bounds</span></div>
<div class="stat"><b>{s["unresolved"]}</b><span>unresolved (blank, not guessed)</span></div>
</div>

<h2>Where everything is</h2>
<div class="links">
<a href="picks.html"><span><b>All picks — every listed match</b><small>One card per match: pick, both
probabilities, basis, sources. Open matches first.</small></span><span aria-hidden="true">→</span></a>
<a href="picks.html#open"><span><b>Open picks only ({s["open"]})</b><small>What you can still play
{f'· next lock {esc(when(next_lock.get("lock_utc")))}' if next_lock else ''}</small></span><span aria-hidden="true">→</span></a>
<a href="unresolved.html"><span><b>Unresolved &amp; limitations</b><small>Every blank row with its
reason, plus the coverage limits you should know about.</small></span><span aria-hidden="true">→</span></a>
<a href="results.html"><span><b>Results &amp; track record</b><small>Pre-lock picks graded against the
official result ({t.get("graded", 0)} graded so far).</small></span><span aria-hidden="true">→</span></a>
<a href="sources.html"><span><b>Sources</b><small>Every feed read, its HTTP status and read time,
plus the per-row quote ledger.</small></span><span aria-hidden="true">→</span></a>
<a href="flagged.html"><span><b>Flagged for review</b><small>{len(b.get("flags") or [])} irregularities
found while verifying, with source links.</small></span><span aria-hidden="true">→</span></a>
<a href="method.html"><span><b>Method</b><small>The pick ladder, the fitted slope, and the rules this
desk will not break.</small></span><span aria-hidden="true">→</span></a>
</div>

<h2>What this covers, in plain words</h2>
<p>The lobby lists <strong>{s["listed_in_lobby"]}</strong> Counter-Strike 2 fixtures for pick'em week
{esc((b.get("week") or {}).get("weekId"))}. Of those, <strong>{s["open"]}</strong> are still before
their published lock time and <strong>{s["with_pick"]}</strong> resolve to a pick with both
probabilities. <strong>{s["market_rows"]}</strong> come from real prices at Pinnacle, Bovada, Melbet
or the Kalshi exchange; <strong>{s["model_rows"]}</strong> are originated from Valve's official
Regional Standings because no book posts a price on them yet; and <strong>{s["bound_rows"]}</strong>
are published as explicit bounds because one side has no official rating.</p>
<p>The rest of the list — <strong>{(s["by_state"] or {}).get("stale", 0)} fixtures</strong> — are
listed by HotSpawn with June/July kickoff times that it never updated ("waiting for
information"). They are not pickable, but they are kept here with a research line where one is
defensible, and named as unresolved where it is not. That is the difference between a list that
says "13 of 78" and one that says "78 of 78, here is what each one is".</p>

<h2 id="unresolved-summary">Unresolved picks &amp; limitations</h2>
<p>These rows have <em>no</em> verified basis, so their probability cells are blank. The full
section, including the limits that apply to the resolved rows, is on
<a href="unresolved.html">Unresolved &amp; limitations</a>.</p>
<table><thead><tr><th>Match</th><th>When</th><th>Why there is no pick</th></tr></thead>
<tbody>{unr_rows}</tbody></table>
<p class="small">Standing limitations: HLTV blocks automated reads (HTTP 403), so it is used only
for identity cross-checks; Valve's newest published standings file is dated
{esc(b["vrs"].get("snapshot"))}, so model rows lag recent results; and a bound is a floor or
ceiling, not a point estimate. All three are spelled out on the unresolved page.</p>

<h2>How a pick is made</h2>
<ol>
<li><strong>Market first.</strong> Every verified Pinnacle / Bovada / Melbet / Kalshi price that
agrees on both team names and the start time (five-minute tolerance) is de-vigged and averaged;
the pick is the higher of the two probabilities.</li>
<li><strong>Then origin.</strong> With no external price, both teams' official Valve ratings give
the probability, using a slope fitted to {esc(b["calibration"].get("n_pairs"))} observed book lines
(k = {esc(b["calibration"].get("k"))}).</li>
<li><strong>Then bound.</strong> With one team unrated, the rated team's chance is published as a
lower bound with the assumption written on the row.</li>
<li><strong>Otherwise blank.</strong> No number is invented, and the row is listed as unresolved.</li>
</ol>
<p class="small">HotSpawn's own crowd percentages are never read, never stored and never used as a
probability. The lobby tells us <em>which matches exist</em>; the numbers come from books, the
exchange and Valve.</p>
"""


def picks_page(b: dict) -> str:
    rows = b["rows"]
    open_rows = [r for r in rows if r["state"] == "open"]
    rest = [r for r in rows if r["state"] != "open"]
    parts = [f'<h1>All picks</h1>',
             f'<p class="lede"><strong>{len(open_rows)}</strong> of the <strong>{len(rows)}</strong> '
             f'fixtures the lobby lists are still open. Every listed match is below: open ones first, '
             f'then the closed and past rows so the record is complete.</p>',
             f'<p class="small">Jump to <a href="#open">open ({len(open_rows)})</a> · '
             f'<a href="#closed">closed / past ({len(rest)})</a> · '
             f'<a href="unresolved.html">unresolved &amp; limitations</a></p>',
             f'<h2 id="open">Open for picks ({len(open_rows)})</h2>']
    if not open_rows:
        parts.append('<p class="note">No fixture is currently before its lock time.</p>')
    for r in open_rows:
        parts.append(match_card(r))
    parts.append(f'<h2 id="closed">Closed, past and not pickable ({len(rest)})</h2>')
    parts.append('<p class="small">These are still listed in the week. Most carry June/July kickoff '
                 'times HotSpawn never updated, so they cannot be picked; their lines are research '
                 'values and are labelled as such.</p>')
    day = None
    for r in rest:
        stamp = (r.get("start_utc") or "")[:10]
        if stamp != day:
            day = stamp
            parts.append(f'<div class="dayhead">{esc(day or "no date published")}</div>')
        parts.append(match_card(r))
    return "".join(parts)


def unresolved_page(b: dict) -> str:
    s = b["summary"]
    unresolved = b.get("unresolved") or []
    rows = "".join(
        f'<tr><td data-h="Match"><strong>{esc(u["team_a"])} vs {esc(u["team_b"])}</strong>'
        f'<br><span class="small">{esc(u["competition"])} · fixture {esc(u["fixture_id"])} · '
        f'<a href="{esc(u["hotspawn_url"])}">official fixture</a></span></td>'
        f'<td data-h="Scheduled">{esc(when(u.get("start_utc")))}</td>'
        f'<td data-h="Status">{esc(u.get("state_label"))}</td>'
        f'<td data-h="Why there is no pick">{esc(u["reason"])}</td></tr>'
        for u in unresolved) or '<tr><td class="noH" colspan="4">Nothing is unresolved in this capture.</td></tr>'
    stale = [r for r in b["rows"] if r["state"] == "stale"]
    stale_table = "".join(
        f'<tr><td data-h="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td data-h="HotSpawn kickoff">{esc(when(r.get("start_utc")))}</td>'
        f'<td data-h="Our line">{pct((r.get("line") or {}).get("pick_prob"))} '
        f'{esc((r.get("line") or {}).get("pick_team") or "")} '
        f'({esc(BASIS.get((r.get("line") or {}).get("basis"), ("", "blank"))[1])})</td>'
        f'<td data-h="Source"><a href="{esc(r["hotspawn_url"])}">fixture</a></td></tr>'
        for r in stale)
    return f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="lede">This is the separate section the brief asks for: every match we cannot resolve, the
reason, and the limits that apply to the picks we do publish. Nothing here is filled in.</p>
<div class="stats">
<div class="stat"><b>{s["total_rows"]}</b><span>matches listed by the lobby</span></div>
<div class="stat"><b>{s["unresolved"]}</b><span>unresolved (blank)</span></div>
<div class="stat"><b>{s["unresolved_open"]}</b><span>of them still open</span></div>
<div class="stat"><b>{len(stale)}</b><span>listed but not pickable (kickoff long past)</span></div>
</div>

<h2>Unresolved rows</h2>
<table><thead><tr><th>Match</th><th>Scheduled</th><th>Status</th><th>Why there is no pick</th></tr></thead>
<tbody>{rows}</tbody></table>

<h2>Limitations that apply to the rest of the board</h2>
<div class="warnbox"><strong>1. Most of the list is not pickable.</strong> {len(stale)} of the
{s["listed_in_lobby"]} fixtures the lobby counts for this week still carry June/July kickoff
timestamps ("waiting for information"). HotSpawn lists them and counts them in the week, but their
lock time has long passed, so no pick can be entered. They are published here with a research line
where one is defensible (labelled "VRS model" or "Lower bound") and listed as unresolved otherwise.</div>
<div class="warnbox"><strong>2. HLTV blocks automation.</strong> The collector probes
<a href="https://www.hltv.org/matches">hltv.org/matches</a> every run and records HTTP 403. HLTV is
therefore used only for identity cross-checks that were read and linked by hand; no HLTV page feeds
a probability. Official Valve standings and licensed books/exchange carry every number.</div>
<div class="warnbox"><strong>3. Valve's standings are dated
{esc(b["vrs"].get("snapshot"))}.</strong> That is the newest file Valve publishes. Model and bound
rows therefore lag results since that date; the date is shown with every rating, and rows switch to
a market line automatically as soon as a book posts one.</div>
<div class="warnbox"><strong>4. A bound is not a probability.</strong> {s["bound_rows"]} rows are
published as bounds because one team has no official rating. The assumption ("the unrated opponent
sits at Valve's lowest published rating, {esc(b["vrs"].get("floor_points"))} pts") is printed on the
row; the true value can only be more favourable to the rated team, never less.</div>
<div class="warnbox"><strong>5. Single-source prices are thin.</strong> Rows priced by one book only
are flagged "single source price". A Kalshi price is an exchange mid, not a guaranteed fill.</div>
<div class="warnbox"><strong>6. No HotSpawn crowd data.</strong> The lobby's "picked %" is not a
price and is never used; a test asserts the board never contains it.</div>

<h2>The not-pickable rows in full ({len(stale)})</h2>
<p class="small">Shown so the inventory is complete and auditable. "Our line" is research, not a
pick you can enter.</p>
<table><thead><tr><th>Match</th><th>HotSpawn kickoff</th><th>Our line</th><th>Source</th></tr></thead>
<tbody>{stale_table}</tbody></table>
"""


def sources_page(b: dict) -> str:
    access = b.get("access") or {}
    rows = "".join(
        f'<tr><td data-h="Source"><strong>{esc(name)}</strong></td>'
        f'<td data-h="Status">{esc(meta.get("status"))}{"" if meta.get("ok") else " ⚠"}</td>'
        f'<td data-h="Read at">{esc(meta.get("at_utc"))}</td>'
        f'<td data-h="Bytes">{esc(meta.get("bytes"))}</td>'
        f'<td data-h="Error">{esc(meta.get("error") or "—")}</td>'
        f'<td data-h="URL"><a href="{esc(meta.get("url"))}">open</a></td></tr>'
        for name, meta in sorted(access.items()))
    ledger = []
    for r in b["rows"]:
        for q in r.get("quotes") or []:
            ledger.append(
                f'<tr><td data-h="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}'
                f'<br><span class="small">fixture {esc(r["fixture_id"])}</span></td>'
                f'<td data-h="Source">{esc(q.get("source_name"))}</td>'
                f'<td data-h="Raw price">{esc(q.get("raw_a"))} / {esc(q.get("raw_b"))}</td>'
                f'<td data-h="De-vigged">{pct(q.get("prob_a"))} / {pct(q.get("prob_b"))}</td>'
                f'<td data-h="Start check">{esc(q.get("start_method"))} · '
                f'{esc(q.get("start_diff_h"))}h</td>'
                f'<td data-h="Link"><a href="{esc(q.get("public_url"))}">source</a></td></tr>')
    checks = "".join(
        f'<tr><td data-h="Check">{esc(c["check"])}</td>'
        f'<td data-h="Result">{"PASS" if c["passed"] else "FAIL"}</td>'
        f'<td data-h="Detail"><span class="small">{esc(json.dumps(c["detail"])[:240])}</span></td></tr>'
        for c in b.get("verification") or [])
    rejected = []
    for r in b["rows"]:
        for j in r.get("rejected_joins") or []:
            rejected.append(
                f'<tr><td data-h="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
                f'<td data-h="Source">{esc(j.get("source_name"))}</td>'
                f'<td data-h="Names at source">{esc(" / ".join(str(x) for x in j.get("names_at_source") or []))}</td>'
                f'<td data-h="Why rejected">{esc(j.get("reason"))} ({esc(j.get("start_diff_h"))}h)</td></tr>')
    return f"""
<h1>Sources</h1>
<p class="lede">Everything this board was built from, with the read time and HTTP status of each
feed, the row-level quote ledger, and the checks that run on every build.</p>

<h2>Feeds read</h2>
<table><thead><tr><th>Source</th><th>Status</th><th>Read at (UTC)</th><th>Bytes</th><th>Error</th><th>URL</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="small">Capture mode: <code>{esc(b.get("mode"))}</code> · captured
{esc(cap(b.get("captured_utc")))} · fixtures came from the lobby transfer state and the public
fixtures API.</p>

<h2>Quote ledger — every price used</h2>
<table><thead><tr><th>Match</th><th>Source</th><th>Raw price</th><th>De-vigged</th>
<th>Start-time check</th><th>Link</th></tr></thead><tbody>{''.join(ledger) or '<tr><td class="noH" colspan="6">No external quote joined any fixture in this capture.</td></tr>'}</tbody></table>

<h2>Rejected joins (never used)</h2>
<p class="small">A price is dropped when the team names match but the published start times do not,
so a similarly named fixture can never inherit a price.</p>
<table><thead><tr><th>Match</th><th>Source</th><th>Names at source</th><th>Why rejected</th></tr></thead>
<tbody>{''.join(rejected) or '<tr><td class="noH" colspan="4">None.</td></tr>'}</tbody></table>

<h2>Build checks</h2>
<table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>{checks}</tbody></table>
"""


def results_page(b: dict) -> str:
    tally = b.get("tally") or {}
    results = b.get("results") or []
    graded = [r for r in results if r.get("result") in ("hit", "miss")]
    pending = [r for r in results if r.get("result") is None and r.get("state") in ("open", "locked", "in_play")]
    other = [r for r in results if r not in graded and r not in pending]
    def table(items):
        return "".join(
            f'<tr><td data-h="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}'
            f'<br><span class="small">{esc(r.get("competition"))} · {esc(when(r.get("start_utc")))}</span></td>'
            f'<td data-h="Recorded pick">{esc(r.get("pick_team"))} {pct(r.get("pick_prob"))}</td>'
            f'<td data-h="Basis">{esc(r.get("basis"))}</td>'
            f'<td data-h="Recorded">{esc(r.get("observed_utc"))}<br><span class="small">'
            f'{esc(r.get("recorded_by"))}</span></td>'
            f'<td data-h="Result">{esc((r.get("result") or r.get("state") or "").upper())}</td></tr>'
            for r in items)
    return f"""
<h1>Results &amp; track record</h1>
<p class="lede">A pick only counts here if it was recorded <em>before</em> the match started, and it is
graded against the winner HotSpawn publishes. {tally.get("graded", 0)} graded so far:
{tally.get("hit", 0)} hit, {tally.get("miss", 0)} miss.</p>
<div class="stats">
<div class="stat"><b>{tally.get("graded", 0)}</b><span>graded picks</span></div>
<div class="stat"><b>{tally.get("hit", 0)}</b><span>correct</span></div>
<div class="stat"><b>{tally.get("miss", 0)}</b><span>wrong</span></div>
<div class="stat"><b>{tally.get("pending", 0)}</b><span>pending</span></div>
</div>
<div class="note">Pre-lock picks entered before this session existed are imported from the earlier
desks that recorded them (named in the "Recorded" column with the file they came from), so the
record starts with real history instead of zero.</div>
<h2>Graded</h2>
<table><thead><tr><th>Match</th><th>Recorded pick</th><th>Basis</th><th>Recorded</th><th>Result</th></tr></thead>
<tbody>{table(graded) or '<tr><td class="noH" colspan="5">No finished fixture has a pre-lock pick yet. This fills in as matches finish.</td></tr>'}</tbody></table>
<h2>Pending</h2>
<table><thead><tr><th>Match</th><th>Recorded pick</th><th>Basis</th><th>Recorded</th><th>Status</th></tr></thead>
<tbody>{table(pending) or '<tr><td class="noH" colspan="5">Nothing pending.</td></tr>'}</tbody></table>
{('<h2>Closed without a gradeable pick</h2><table><thead><tr><th>Match</th><th>Recorded pick</th><th>Basis</th><th>Recorded</th><th>State</th></tr></thead><tbody>' + table(other) + '</tbody></table>') if other else ''}
"""


def flagged_page(b: dict) -> str:
    flags = b.get("flags") or []
    chunks = []
    for f in flags:
        links = " · ".join('<a href="%s">source</a>' % esc(u) for u in f.get("urls") or [])
        chunks.append(
            '<article class="card"><h3>%s · %s</h3><p class="small">Severity: %s</p>'
            '<p>%s</p><p class="small">%s</p></article>'
            % (esc(f["id"]), esc(f["title"]), esc(f["severity"]), esc(f["detail"]), links))
    items = "".join(chunks)
    return f"""
<h1>Flagged for review</h1>
<p class="lede">Irregularities and limitations found while verifying this board. None of them block
publication; each is published with the source that shows it.</p>
{items or '<p class="note">No irregularities recorded.</p>'}
<h2>Checks</h2>
<p>All {len(b.get("verification") or [])} build checks are listed on the
<a href="sources.html">Sources</a> page; a failing check fails the build, so a published page means
they all passed.</p>
"""


def method_page(b: dict) -> str:
    cal = b.get("calibration") or {}
    policy = b.get("policy") or {}
    return f"""
<h1>Method</h1>
<p class="lede">The same rules every run, published so any row can be checked by hand.</p>

<h2>1. Inventory: the lobby, not a guess</h2>
<p>Every run re-reads the public lobby page's Angular transfer state
(<code>https://play.hotspawn.com/lobby</code>, the same <code>/api/v1/fixtures</code> payload the page
itself calls) and keeps every Counter-Strike 2 fixture the week lists — including the ones with
stale kickoff times. The page's own counters are recorded as the coverage check
({"listed" if b['summary']['listed_in_lobby'] == b['summary']['lobby_fixtures_reported'] else "not listed"}:
{esc(b['summary']['listed_in_lobby'])} fixtures in the inventory).</p>

<h2>2. Prices: external only</h2>
<p>Pinnacle, Bovada, Melbet and the Kalshi <code>KXCS2GAME</code> exchange are read every run. A price
joins a fixture only when <strong>both</strong> team names match after normalisation (or through a
published alias with linked evidence) <strong>and</strong> the start times agree within
{esc(policy.get("join_tolerance_minutes"))} minutes. Kalshi tickers carry US-Eastern wall-clock time
and are converted with the real New York zone, so the November DST change does not shift a price.</p>
<p>Per-source probabilities are proportional de-vig values: <code>p = (1/d) / (1/dA + 1/dB)</code>.
The consensus is a weighted mean (Pinnacle 2.0, others 1.0). Any quote older than
{esc(policy.get("quote_freshness_hours"))} hours is dropped and the row is labelled.</p>

<h2>3. Origination: Valve's own ratings</h2>
<p>Valve's official Regional Standings give each team a rating in points. Their published model uses a
logistic curve; Valve's own README says its slope is too steep, so the slope here is <em>fitted</em>
to book lines rather than assumed:</p>
<p><code>logit(p) = k · C · (points_A − points_B)</code>, with
<code>C = g · ln(10) / 400</code> for a fixed rating deviation and
<code>k = {esc(cal.get("k"))}</code> fitted from {esc(cal.get("n_pairs"))} pre-lock
(fixture, market probability) pairs
(<a href="{esc(cal.get("source_url"))}">source</a>), bounded to [{esc((cal.get("bounds") or ["?", "?"])[0])},
{esc((cal.get("bounds") or ["?", "?"])[1])}]. Mean absolute error on those pairs:
{esc(cal.get("mae_prob"))} versus {esc(cal.get("mae_prob_valve"))} for Valve's raw slope.</p>

<h2>4. Bounds instead of invented numbers</h2>
<p>When exactly one side is rated, the rated team's chance is computed against Valve's
<strong>lowest</strong> published rating ({esc(b["vrs"].get("floor_points"))} pts). That is a floor for
the rated team: a real opponent is at least as strong as the weakest rated team, so the true
probability cannot be lower. The row says so.</p>

<h2>5. What is never done</h2>
<ul>
<li>No HotSpawn crowd percentage is read, stored or used. It is a popularity poll, not a price.</li>
<li>No probability is inferred from a team name, a roster guess or a "looks stronger" judgement.</li>
<li>No price is borrowed from a differently timed fixture. Near misses are listed, not joined.</li>
<li>No missing value is filled. It stays blank and appears on the Unresolved page.</li>
</ul>

<h2>6. Refresh and verification</h2>
<p>The workflow runs every 4 hours (and on demand) and re-captures the lobby, the books and Valve's
file, then rebuilds this site. {len(b.get("verification") or [])} checks run before anything is
published: probabilities sum to 1, the pick is always the higher probability, every market line
reproduces its stored consensus, every model line recomputes from its published delta and k, every
originated line links the official file it came from, and the board contains no crowd data.</p>
<p class="small">Board JSON: <a href="../data/2cadfaf2/board.json">data/2cadfaf2/board.json</a> ·
capture: <code>{esc(b.get("captured_utc"))}</code> · generated
<code>{esc(b.get("generated_utc"))}</code>.</p>
"""


def main() -> int:
    if not BOARD.exists():
        print("no board — run resolve.py first", file=sys.stderr)
        return 2
    b = load_board()
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": page("Executive summary", "index.html", exec_summary(b), b),
        "picks.html": page("All picks", "picks.html", picks_page(b), b),
        "unresolved.html": page("Unresolved & limitations", "unresolved.html", unresolved_page(b), b),
        "sources.html": page("Sources", "sources.html", sources_page(b), b),
        "results.html": page("Results", "results.html", results_page(b), b),
        "flagged.html": page("Flagged for review", "flagged.html", flagged_page(b), b),
        "method.html": page("Method", "method.html", method_page(b), b),
    }
    for name, text in pages.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print("wrote", ", ".join(pages), "->", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
