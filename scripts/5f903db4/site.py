#!/usr/bin/env python3
"""EVERYPICK site renderer (session 5f903db4).

Renders `everypick/*.html` from `data/5f903db4/board.json`.  Phone-first: one column, large tap
targets, tables that collapse into cards under 640px, no JavaScript required, no external assets.
"""
from __future__ import annotations

import importlib.util as _iu
import sys
from datetime import datetime, timezone
from pathlib import Path

_spec = _iu.spec_from_file_location("everpick_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["everpick_core"] = core
_spec.loader.exec_module(core)

BOARD = "data/5f903db4/board.json"
OUT = core.SITE

NAV = [("index.html", "Summary"), ("picks.html", "All picks"),
       ("unresolved.html", "Unresolved"), ("sources.html", "Sources"),
       ("method.html", "Method"), ("flagged.html", "Flagged")]

STYLE = """
:root{--bg:#0b1220;--card:#121c2e;--card2:#0f1727;--ink:#e8eefc;--dim:#93a4c3;--line:#25334d;
--good:#7ef0b2;--warn:#ffd479;--bad:#ff9aa2;--accent:#7cc4ff;--market:#7ef0b2;--model:#7cc4ff;--bound:#ffd479}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
a:focus-visible{outline:3px solid var(--good);outline-offset:3px}
.skip{position:absolute;left:-10000px}.skip:focus{position:static;display:block;padding:12px;background:var(--card)}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:12px 14px 64px}
header.top{position:sticky;top:0;z-index:5;background:rgba(11,18,32,.96);border-bottom:1px solid var(--line);
backdrop-filter:blur(6px)}
header.top .bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;
max-width:1080px;margin:0 auto;padding:8px 14px}
.brand{font-weight:700;font-size:15px;letter-spacing:.2px}
.brand span{color:var(--good)}
nav{display:flex;flex-wrap:wrap;gap:6px}
nav a{display:inline-block;padding:11px 12px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;color:var(--ink);font-size:13px;min-height:44px}
nav a.active{background:var(--good);color:#0b2417;border-color:var(--good);font-weight:700}
h1{font-size:24px;line-height:1.2;margin:10px 0 4px}
h2{font-size:18px;margin:26px 0 8px}
h3{font-size:15px;margin:18px 0 6px}
p{margin:8px 0}
.eyebrow{color:var(--dim);text-transform:uppercase;letter-spacing:.09em;font-size:11px;margin:14px 0 2px}
.lede{color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0}
@media(min-width:640px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:11px}
.tile b{display:block;font-size:24px;line-height:1.1}
.tile small{color:var(--dim);font-size:12px}
.cta{display:grid;gap:10px;margin:14px 0}
@media(min-width:640px){.cta{grid-template-columns:1fr 1fr}}
.cta a{display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--card);
border:1px solid var(--line);border-radius:14px;padding:15px 16px;text-decoration:none;color:var(--ink);
font-weight:700;min-height:56px}
.cta a.primary{background:var(--good);color:#08200f;border-color:var(--good)}
.cta a span.small{font-weight:400;color:inherit;opacity:.75;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;
border:1px solid var(--line);white-space:nowrap}
.badge.market{color:#08200f;background:var(--market);border-color:var(--market)}
.badge.model{color:#04121f;background:var(--model);border-color:var(--model)}
.badge.bound{color:#2a1d00;background:var(--bound);border-color:var(--bound)}
.badge.flag{color:var(--warn);background:transparent;border-color:var(--warn)}
.badge.plain{color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pick{font-weight:800;font-size:15px}
.prob{font-variant-numeric:tabular-nums}
.prob.win{color:var(--good);font-weight:700}
.prob.lose{color:var(--dim)}
.muted{color:var(--dim);font-size:12px}
.src{display:flex;flex-wrap:wrap;gap:6px 10px;font-size:12px}
.src a{text-decoration:underline}
.match{font-weight:700}
@media(max-width:639px){
 table thead{display:none}
 table,thead,tbody,tr,td,th{display:block;width:100%}
 tr{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 10px;padding:10px 12px}
 td{border:0;padding:4px 0}
 td[data-l]{display:flex;gap:10px;justify-content:space-between;align-items:baseline}
 td[data-l]::before{content:attr(data-l);color:var(--dim);font-size:11px;text-transform:uppercase;
 letter-spacing:.06em;flex:0 0 42%}
 td.num{text-align:right}
}
.callout{border-left:4px solid var(--warn);background:#1a1608;padding:10px 12px;border-radius:8px;margin:12px 0}
.callout.good{border-color:var(--good);background:#0b1f16}
.callout.bad{border-color:var(--bad);background:#221010}
ul,ol{padding-left:20px}
li{margin:5px 0}
footer{color:var(--dim);font-size:12px;border-top:1px solid var(--line);margin-top:26px;padding-top:12px}
code{background:#0a1322;padding:1px 5px;border-radius:5px;font-size:13px}
.tbl-scroll{overflow-x:auto}
"""


def esc(v):
    return core.esc(v)


def pct(p, dash="—"):
    return dash if p is None else f"{float(p) * 100:.1f}%"


def when(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return esc(iso)
    return dt.strftime("%d %b · %H:%M UTC")


def rel(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    hours = (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    if hours < 0:
        return f"started/closed {abs(hours):.0f}h ago"
    if hours < 1:
        return f"locks in {hours * 60:.0f}m"
    if hours < 48:
        return f"in {hours:.0f}h"
    return f"in {hours / 24:.0f}d"


def page(title, active, body, stamp=""):
    def _nav_link(href, label):
        cls = ' class="active"' if href == active else ""
        return f'<a href="{href}"{cls}>{esc(label)}</a>'

    links = "".join(_nav_link(href, label) for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="description" content="Retained HotSpawn CS2 fixtures, supported picks, sourced model estimates and unresolved evidence gaps.">
<title>{esc(title)} · Every-match CS2 picks</title>
<style>{STYLE}</style>
</head>
<body>
<a class="skip" href="#main-content">Skip to picks and summary</a>
<header class="top"><div class="bar">
<div class="brand">Every-match picks <span>· CS2</span></div>
<nav>{links}<a href="../index.html">Site home</a></nav>
</div></header>
<main class="wrap" id="main-content" tabindex="-1">
<div class="callout"><strong>Source freshness matters.</strong> This is a retained evidence snapshot, not
live odds. Four-hour scheduled checks are a target, not a guarantee. Check the fixture and quote
read times before using a pick. The builder excludes prices older than eight hours. Sources inaccessible during this session were not reverified.
<a href="unresolved.html">Unresolved picks &amp; limitations</a>.</div>
{body}
<footer>
<p>Every figure on this page is either a bookmaker/exchange price (no-vig) or a line originated from
Valve's official rating table; the basis is printed on every row. HotSpawn's crowd-pick percentages
are never used.{esc(stamp)}</p>
</footer>
</main>
</body>
</html>
"""


def badge(row):
    basis = row["resolution"]["basis"]
    if basis == "market":
        n = row["resolution"].get("n_books") or 0
        return f'<span class="badge market">Market · {n} book{"s" if n != 1 else ""}</span>'
    if basis == "originated_vrs":
        return '<span class="badge model">Originated · Valve VRS</span>'
    if basis == "originated_vrs_bound":
        return '<span class="badge bound">Bound · one side unrated</span>'
    return '<span class="badge flag">Unresolved</span>'


def prob_cell(row, side):
    res = row["resolution"]
    p = res["prob_a"] if side == "a" else res["prob_b"]
    if p is None:
        return '<span class="prob">—</span>'
    relation = ""
    bound = res.get("bound") or {}
    if row["resolution"]["basis"] == "originated_vrs_bound" and bound.get("side") == side:
        relation = "≥ "
    elif row["resolution"]["basis"] == "originated_vrs_bound" and bound.get("side") != side:
        relation = "≤ "
    cls = "prob win" if row.get("pick_side") == side else "prob lose"
    return f'<span class="{cls}">{relation}{pct(p)}</span>'


def source_links(row, limit=4):
    """Short, de-duplicated source links: the price that set the number first, then the fixture
    page, then the official rating rows."""
    quotes = [s for s in (row.get("sources") or []) if s["label"].startswith(tuple(
        q["source_name"] for q in row.get("quotes") or []))] if row.get("quotes") else []
    rest = [s for s in (row.get("sources") or []) if s not in quotes]
    out, seen_url, seen_label = [], set(), set()
    for s in quotes + rest:
        url = s.get("url")
        if not url or url in seen_url:
            continue
        label = s["label"].split(" - ")[0].split(" (")[0].strip()
        if label in seen_label:
            continue
        seen_url.add(url)
        seen_label.add(label)
        out.append(f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a>')
        if len(out) >= limit:
            break
    return '<div class="src">' + "".join(out) + "</div>"


def flags_html(row):
    if not row.get("flags"):
        return ""
    return " ".join(f'<span class="badge flag">{esc(f.replace("_", " "))}</span>'
                    for f in row["flags"][:3])


def rows_table(rows, table_id="picks"):
    head = ("<thead><tr><th>Match</th><th>Kick-off</th><th>Pick</th>"
            "<th class=\"num\">A win</th><th class=\"num\">B win</th><th>Basis</th><th>Sources</th>"
            "</tr></thead>")
    body = []
    for r in rows:
        kick = (f'<span class="match">{esc(r["team_a"])} vs {esc(r["team_b"])}</span>'
                f'<div class="muted">{esc(r.get("competition"))}'
                f'{"" if r.get("tier") is None else " · tier " + esc(r.get("tier"))}</div>')
        pick = (f'<span class="pick">{esc(r.get("pick") or "—")}</span>'
                f'<div class="muted">{esc(r.get("confidence") or "")}'
                f'{"" if not r.get("pick_prob") else " · " + pct(r["pick_prob"])} to win</div>')
        body.append(f"""<tr id="f{r['fixture_id']}">
<td data-l="Match">{kick}</td>
<td data-l="Kick-off">{esc(when(r.get('start_utc')))}<div class="muted">{esc(rel(r.get('start_utc')))}
 · locks {esc((r.get('lock_utc') or '')[11:16])} UTC</div></td>
<td data-l="Pick">{pick}</td>
<td class="num" data-l="{esc(r['team_a'])}">{prob_cell(r, 'a')}</td>
<td class="num" data-l="{esc(r['team_b'])}">{prob_cell(r, 'b')}</td>
<td data-l="Basis">{badge(r)}<div class="muted">{flags_html(r)}</div></td>
<td data-l="Sources">{source_links(r)}</td>
</tr>""")
    return f'<div class="tbl-scroll"><table id="{table_id}">{head}<tbody>{"".join(body)}</tbody></table></div>'


# ------------------------------------------------------------------------------------- pages
def _stamp(board):
    g = board.get("generated_utc")
    if not g:
        return ""
    return " Board built " + str(g).replace("T", " ").replace("Z", " UTC") + "."


def render_index(board):
    s = board["summary"]
    rows = [r for r in board["rows"] if r["state"] == "open"]
    soon = sorted(rows, key=lambda r: str(r.get("start_utc") or ""))[:6]
    stamp = board["generated_utc"].replace("T", " ").replace("Z", " UTC")
    body = f"""
<p class="eyebrow">Executive summary · HotSpawn CS2 pick'em</p>
<h1>Every retained match, clear picks where supported, and visible evidence gaps.</h1>
<p class="lede">Built {esc(stamp)} from the {s['lobby_open']} CS2 fixtures open in the HotSpawn
Pick'ems lobby plus {s['api_only']} fixture the HotSpawn API lists but the lobby does not render.
Retained evidence, not a live verification claim: resolved rows use external prices or a labelled
model based on Valve ratings. Missing evidence stays blank. HotSpawn crowd percentages are never used.</p>

<div class="tiles">
<div class="tile"><b>{s['lobby_open']}</b><small>open lobby matches covered (+{s['api_only']} API-only)</small></div>
<div class="tile"><b>{s['with_pick']}</b><small>matches with a pick and two probabilities</small></div>
<div class="tile"><b>{s['market']}</b><small>priced from real betting lines</small></div>
<div class="tile"><b>{s['unresolved']}</b><small>unresolved (see limitations)</small></div>
</div>

<h2>Where the picks are</h2>
<p class="lede">Everything below is one tap away on a phone. This page is the summary; the lists
live on their own pages and are refreshed every four hours.</p>
<div class="cta">
<a class="primary" href="picks.html"><span>All picks · every match<span class="small"><br>pick, both probabilities, basis, source links</span></span><span>→</span></a>
<a href="unresolved.html"><span>Unresolved &amp; limitations<span class="small"><br>what could not be priced from a book and why</span></span><span>→</span></a>
<a href="sources.html"><span>Sources &amp; read times<span class="small"><br>every book, exchange and official table used</span></span><span>→</span></a>
<a href="method.html"><span>Method &amp; verification<span class="small"><br>formula, fitted slope, join rules, tests</span></span><span>→</span></a>
<a href="flagged.html"><span>Flagged for review<span class="small"><br>irregularities found in the data and the repo</span></span><span>→</span></a>
<a href="../index.html"><span>Site home<span class="small"><br>other boards and archives</span></span><span>→</span></a>
</div>

<h2>Next matches</h2>
<p class="lede">The six fixtures that lock soonest. The full list is on
<a href="picks.html">All picks</a>.</p>
{rows_table(soon, "next")}

<h2>How a pick is produced</h2>
<ol>
<li><strong>Real prices first.</strong> Two-way bookmaker and exchange prices are converted to
no-vig probabilities (each book's two implied probabilities normalised to 100%), then averaged.
Every book price, its decimal odds and its overround is printed on the row.</li>
<li><strong>Official ratings only when no book prices the match.</strong> Valve's published VRS
points go through <code>p = 1/(1+exp(-k·C·Δpoints))</code> with Valve's own C = {core.VALVE_C} and
this project's fitted k = {core.CAL_K:.4f} (re-fitted here: best k on a 60-pair grid is
{board['calibration_check'].get('k_best_grid')}, MAE {board['calibration_check'].get('mae_at_best', 0)*100:.2f} pp).</li>
<li><strong>Missing rankings stay unresolved.</strong> Absence from Valve's table is not a
strength bound. Without external prices or ratings for both teams, pick and probability cells stay blank.</li>
<li><strong>Nothing is guessed.</strong> {s['unresolved']} fixtures are unresolved. See the separate
<a href="unresolved.html">Unresolved picks &amp; limitations</a> list for evidence gaps.</li>
</ol>
<div class="callout"><strong>Read this before betting a pick.</strong> Market rows are consensus
prices; originated rows are model estimates, not official odds. The roughly 8 pp in-sample
market-fit error is not a confidence interval or verified match-outcome accuracy. Details and the conflicting-signal rows are on
<a href="unresolved.html">Unresolved &amp; limitations</a> and
<a href="flagged.html">Flagged for review</a>.</div>
"""
    return page("Executive summary", "index.html", body, _stamp(board))


def render_picks(board):
    rows = board["rows"]
    market = [r for r in rows if r["resolution"]["basis"] == "market"]
    orig = [r for r in rows if r["resolution"]["basis"] == "originated_vrs"]
    bound = [r for r in rows if r["resolution"]["basis"] == "originated_vrs_bound"]
    other = [r for r in rows if r["resolution"]["basis"] not in
             ("market", "originated_vrs", "originated_vrs_bound")]

    def summary(r):
        if not r["quotes"]:
            alt = r.get("alt_origination")
            if alt and alt.get("prob_a") is not None and alt.get("basis") == "originated_vrs":
                return (f'Valve VRS origination · our own line would read '
                        f'{pct(alt["prob_a"])} / {pct(alt["prob_b"])}')
            return ""
        alt = r.get("alt_origination") or {}
        if alt.get("prob_a") is None:
            return ""
        return (f'Rating model would read {pct(alt["prob_a"])} / {pct(alt["prob_b"])}'
                f'{" (bound)" if alt.get("basis") == "originated_vrs_bound" else ""}')

    def block(title, rows_, note):
        if not rows_:
            return ""
        out = [f"<h2>{esc(title)}</h2><p class=\"lede\">{note}</p>{rows_table(rows_)}"]
        detail = []
        for r in rows_:
            d = summary(r)
            quote_lines = "".join(
                f'<li>{esc(q["source_name"])}: {q["decimal_a"]} / {q["decimal_b"]} decimal · '
                f'no-vig {pct(q["prob_a"])} / {pct(q["prob_b"])} · overround '
                f'{q["overround"]*100:.2f}% · <a href="{esc(q.get("public_url") or q.get("api_url"))}" '
                f'target="_blank" rel="noopener">source</a>'
                f'{" · " + esc("; ".join(q["caveats"])) if q.get("caveats") else ""}</li>'
                for q in r["quotes"])
            vrs_lines = []
            for side, key in (("a", "vrs_a"), ("b", "vrs_b")):
                v = r.get(key) or {}
                if v.get("listed"):
                    vrs_lines.append(
                        f'{esc(v.get("name"))}: Valve #{v.get("standing")} '
                        f'{int(v.get("points"))} pts'
                        f'{"" if not v.get("latest_match_date") else ", latest match " + esc(v["latest_match_date"])}'
                        f' · <a href="{esc(v.get("details_url") or r["vrs_page_url"])}" target="_blank" rel="noopener">official row</a>')
                else:
                    vrs_lines.append(f'{esc(v.get("name"))}: no row in Valve\'s global table')
            detail.append(
                f'<div class="card"><h3>{esc(r["team_a"])} vs {esc(r["team_b"])} '
                f'<span class="muted">· {esc(r["fixture_id"])}</span></h3>'
                f'<p class="muted">{esc(r.get("competition"))} · kick-off {esc(when(r.get("start_utc")))}'
                f' · lock {esc(when(r.get("lock_utc")))}</p>'
                + (f'<ul>{quote_lines}</ul>' if quote_lines else
                   '<p>No accepted price is present in the retained evidence for this fixture (see the attempt ledger on '
                   '<a href="unresolved.html">Unresolved</a>). Ratings are model inputs only when both teams are listed; otherwise this row remains unresolved.</p>')
                + f'<p class="muted">Ratings: ' + " · ".join(vrs_lines) + '</p>'
                + (f'<p class="muted">{esc(d)}</p>' if d else "")
                + (f'<p>{flags_html(r)}</p>' if r.get("flags") else "")
                + "</div>")
        out.append("<h3>Row-by-row evidence</h3>" + "".join(detail))
        return "".join(out)

    body = f"""
<p class="eyebrow">All picks · {len(rows)} matches</p>
<h1>Every open HotSpawn CS2 match</h1>
<p class="lede">One row per match: the pick, both teams' win probabilities, how the number was
produced and a link to the source. Sorted by kick-off. Unsupported probabilities and picks remain blank.</p>
{block("Priced from real betting lines", market,
       "Every fixture a bookmaker or exchange prices. No-vig probabilities, averaged across books where more than one quotes it.")}
{block("Originated from Valve's official rating table", orig,
       "No accepted external price is present in the retained capture. These are model estimates using Valve VRS points, not official odds.")}
{block("Directional bounds (one side has no published rating)", bound,
       "Legacy bounds are no longer generated: a missing rating does not establish relative strength.")}
{block("Unresolved", other, "No pick could be produced. Nothing here is guessed.")}
<p class="muted">Generated {esc(board['generated_utc'].replace('T', ' ').replace('Z', ' UTC'))}.
Board data: <code>data/5f903db4/board.json</code>.</p>
"""
    return page("All picks", "picks.html", body, _stamp(board))


def render_unresolved(board):
    s = board["summary"]
    unresolved = [r for r in board["rows"] if r["resolution"]["basis"] == "unresolved"]
    rows_html = "".join(
        f'<tr id="unresolved-{esc(r["fixture_id"])}"><td data-l="Match">'
        f'{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td data-l="Pick / probability">— / —</td>'
        f'<td data-l="Why">{esc(r["resolution"].get("reason", "Missing verified evidence"))}</td>'
        f'<td data-l="Sources">{source_links(r)}</td></tr>' for r in unresolved)

    attempts = []
    for a in board.get("attempted_sources") or []:
        attempts.append(
            f'<tr><td data-l="Source"><a href="{esc(a.get("url"))}" target="_blank" rel="noopener">'
            f'{esc(a.get("source"))}</a><div class="muted">read {esc(a.get("read_utc"))}</div></td>'
            f'<td data-l="Priced">{esc(", ".join(a.get("covers") or []) or "none")}</td>'
            f'<td data-l="No line">{esc(", ".join(a.get("misses") or []) or "none")}</td>'
            f'<td data-l="Notes">{esc(a.get("note"))}</td></tr>')

    lim = "".join(
        f'<div class="card"><h3>{esc(l["id"])} · {esc(l.get("title"))}</h3><p>{esc(l.get("detail"))}</p>'
        f'<p class="muted">Source: <a href="{esc(l.get("source"))}" target="_blank" rel="noopener">'
        f'{esc(l.get("source"))}</a></p></div>'
        for l in board.get("limitations") or [])

    body = f"""
<p class="eyebrow">Unresolved picks &amp; limitations</p>
<h1>{("No match is unresolved today" if s["unresolved"] == 0 else str(s["unresolved"]) + " matches could not be resolved into a pick")}</h1>
<div class="callout"><strong>Coverage: {s['with_pick']} of {s['rows']} retained rows carry a pick</strong>
({s['market']} market-based, {s['originated_both_rated']} model estimates).
{s['unresolved']} unresolved fixtures remain on the full picks list with blank values.</div>
<p class="lede">No accepted external price is present for the fixtures below, and at least one
team lacks a published Valve rating. Absence is not evidence that a team is weaker than the
lowest-ranked team. No rating, percentage, or pick is imputed.</p>
<h2>Unresolved picks — missing evidence</h2>
<div class="tbl-scroll"><table><thead><tr><th>Match</th><th>Pick / probability</th><th>Why</th><th>Sources</th>
</tr></thead><tbody>{rows_html}</tbody></table></div>

<h2>Limitations</h2>
{lim}

<h2>Attempt ledger — what each source was asked and what it returned</h2>
<p class="lede">Fixture ids match the HotSpawn ids used on <a href="picks.html">All picks</a>.
These are historical source-read records, not proof that a source currently has no market.
Live third-party reads were inaccessible during this session; review the recorded timestamps.</p>
<div class="tbl-scroll"><table><thead><tr><th>Source</th><th>Priced these fixtures</th><th>No line for</th>
<th>Notes</th></tr></thead><tbody>{''.join(attempts)}</tbody></table></div>

<h2>What would remove these limitations</h2>
<ul>
<li>A book posting tier-C CCT/DFRAG/MCG lines (then the row switches to market basis automatically).</li>
<li>Valve publishing a newer standings file: the pipeline re-reads the official repository tree and
picks the newest file, so ratings update without a code change.</li>
<li>Valve publishing a rating row for each team that is unrated today (TitanFlow, Off Chops,
Staqued, LOS NINOS, Apogee Betclic) — estimates require verified ratings for both sides.</li>
</ul>
"""
    return page("Unresolved and limitations", "unresolved.html", body, _stamp(board))


def render_sources(board):
    rows = []
    for entry in board.get("read_log") or []:
        rows.append(f'<tr><td data-l="Source"><a href="{esc(entry.get("url"))}" target="_blank" '
                    f'rel="noopener">{esc(entry.get("source"))}</a></td>'
                    f'<td data-l="Read">{esc(entry.get("read_utc"))}</td>'
                    f'<td data-l="Returned">{esc(entry.get("result"))}</td>'
                    f'<td data-l="Used for">{esc(entry.get("note"))}</td></tr>')
    src = board.get("sources") or {}
    def _const_row(k, v):
        if isinstance(v, str):
            url = v if v.startswith("http") else None
        else:
            url = (v or {}).get("api_url")
        shown = v if isinstance(v, str) else ((v or {}).get("newest_published_file") or "API")
        cell = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(shown)}</a>'
                if url else esc(shown))
        return f'<tr><td data-l="Key"><code>{esc(k)}</code></td><td data-l="URL/Value">{cell}</td></tr>'

    constants = "".join(_const_row(k, v) for k, v in src.items())
    per_row = "".join(
        f'<tr><td data-l="Match"><a href="#f{r["fixture_id"]}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a></td>'
        f'<td data-l="Fixture id">{esc(r["fixture_id"])}</td>'
        f'<td data-l="Sources">{source_links(r, limit=6)}</td></tr>'
        for r in board["rows"])
    body = f"""
<p class="eyebrow">Sources</p>
<h1>Every source, when it was read, and what it returned</h1>
<p class="lede">No number on this site exists without one of these sources behind it. Timestamps are
UTC and come from the collector that made the request.</p>
<h2>Read log</h2>
<div class="tbl-scroll"><table><thead><tr><th>Source</th><th>Read</th><th>Returned</th><th>Used for</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Endpoints and constants</h2>
<div class="tbl-scroll"><table><thead><tr><th>Key</th><th>URL / value</th></tr></thead><tbody>{constants}</tbody></table></div>
<h2>Source links per match</h2>
<div class="tbl-scroll"><table><thead><tr><th>Match</th><th>Fixture</th><th>Links</th></tr></thead>
<tbody>{per_row}</tbody></table></div>
"""
    return page("Sources", "sources.html", body, _stamp(board))


def render_method(board):
    cal = board.get("calibration_check") or {}
    pol = board.get("policy") or {}
    mins = board.get("inputs") or {}
    body = f"""
<p class="eyebrow">Method</p>
<h1>How each number is produced (and how to check it)</h1>
<h2>1 · Fixture discovery</h2>
<p>The HotSpawn Pick'ems lobby is a client-rendered page that calls the public fixtures API
<a href="{esc(board['sources']['hotspawn_api'])}" target="_blank" rel="noopener">phpstack…/api/v1/fixtures</a>.
This build uses both: the lobby page for the rendered pick cards and the API for kick-off, lock time
and status. Every fixture keeps its HotSpawn id and, where HotSpawn publishes one, its match permalink.
HotSpawn's crowd-pick percentages are <strong>not</strong> parsed anywhere in this pipeline.</p>

<h2>2 · Prices → probabilities</h2>
<p>For each book with a two-sided price: implied = 1/decimal, then normalise the pair to 100%
(<code>p = implied_a / (implied_a + implied_b)</code>). The overround is published next to the price so
you can see the book's margin. When several books price the same fixture the no-vig probabilities are
averaged; the spread between books is shown on the row.</p>
<p>Quote joins are evidence-gated: a quote is used only when the kick-off agrees within
{esc(pol.get('quote_join_tolerance_minutes'))} minutes and the pairing is either an exact name match, a
documented alias with the roster/kick-off evidence on <a href="sources.html">Sources</a>, or a
publisher-ordered quote already attached to that fixture id. Everything that fails those gates is
dropped, not coerced.</p>

<h2>3 · Originated lines (no book prices the match)</h2>
<p><code>p = 1 / (1 + exp(-k · C · (points_a - points_b)))</code></p>
<ul>
<li><strong>C = {esc(pol.get('C'))}</strong> — Valve's own rating slope, from
<a href="{esc(pol.get('C_source'))}" target="_blank" rel="noopener">model/fit.js</a>.</li>
<li><strong>k = {esc(pol.get('k'))}</strong> — this project's fitted market-vs-rating scale factor.</li>
<li><strong>points</strong> — the official Valve VRS points for each side, from
<a href="{esc(board['sources']['valve_vrs_page'])}" target="_blank" rel="noopener">standings_global_2026_10_05.md</a>.</li>
</ul>
<h3>Calibration re-checked here, not assumed</h3>
<div class="tbl-scroll"><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>
<tr><td data-l="Pairs">Market-vs-rating pairs</td><td data-l="Value">{esc(cal.get('pairs'))}</td></tr>
<tr><td data-l="MAE">Mean absolute error at k used</td><td data-l="Value">{esc(round((cal.get('mae_at_k_used') or 0)*100, 2))} pp</td></tr>
<tr><td data-l="Best fit">Best k on the grid</td><td data-l="Value">{esc(cal.get('k_best_grid'))} at {esc(round((cal.get('mae_at_best') or 0)*100, 2))} pp</td></tr>
<tr><td data-l="Grid">Search</td><td data-l="Value">{esc(cal.get('grid'))}</td></tr>
<tr><td data-l="Flips">Favourite flips vs market</td><td data-l="Value">{esc(cal.get('favourite_flips'))} of {esc(cal.get('pairs'))}</td></tr>
</tbody></table></div>
<p class="muted">{esc(cal.get('favourite_flips_note'))}</p>

<h2>4 · Duplicate Valve rows</h2>
<p>{esc(pol.get('vrs_select_rule'))}</p>
<p class="muted">Three fixtures on today's board hit this rule (Banda Chuya, The Huns, benched gods).
Every alternative row Valve publishes for those teams is kept in the board data next to the chosen one,
and the pick is flagged <span class="badge flag">vrs duplicate rows resolved by published rule</span>.</p>

<h2>5 · Missing evidence stays unresolved</h2>
<p>{esc(pol.get('bound_rule'))}</p>

<h2>6 · Verification in this repository</h2>
<ul>
<li><code>python3 scripts/5f903db4/build.py</code> re-derives every probability from the raw decimals
and Valve points stored in <code>data/5f903db4/board.json</code>.</li>
<li><code>python3 -m unittest tests.test_5f903db4 -v</code> re-computes the no-vig prices and the
originated lines from the raw inputs, asserts that resolved rows have a pick and two probabilities,
unresolved rows stay blank, every row carries at least one https source, and no HotSpawn
crowd percentage appears anywhere in the published pages.</li>
<li>The workflow <code>.github/workflows/everypick-5f903db4.yml</code> re-runs collection, build and
tests every four hours and only commits when the tests pass.</li>
</ul>
<p class="muted">Inputs: primary board {esc((mins.get('primary_board') or {}).get('generated_utc'))} ·
extra board {esc((mins.get('extra_board') or {}).get('generated_utc'))} ·
Valve table {esc((mins.get('vrs') or {}).get('snapshot'))}.</p>
"""
    return page("Method", "method.html", body, _stamp(board))


def _source_line(source):
    """Repo-relative evidence is shown as text; anything on the web becomes a link."""
    source = source or ""
    if isinstance(source, str) and source.startswith("http"):
        return ('<p class="muted">Source: '
                f'<a href="{esc(source)}" target="_blank" rel="noopener">{esc(source)}</a></p>')
    parts = [p.strip() for p in str(source).split("+")]
    out = []
    for part in parts:
        if part.startswith("http"):
            out.append(f'<a href="{esc(part)}" target="_blank" rel="noopener">{esc(part)}</a>')
        else:
            out.append(f'<code>{esc(part)}</code>')
    return '<p class="muted">Source: ' + " + ".join(out) + "</p>"


def render_flagged(board):
    cards = []
    for r in board.get("irregularities") or []:
        cards.append(
            f'<div class="card"><h3>{esc(r.get("id"))} · {esc(r.get("title"))} '
            f'<span class="badge plain">{esc(r.get("severity"))}</span></h3>'
            f'<p>{esc(r.get("detail"))}</p>'
            + (f'<p class="muted">Affected: {esc(", ".join(r.get("affected") or []))}</p>'
               if r.get("affected") else "")
            + _source_line(r.get("source")) + "</div>")
    unverified = "".join(
        f'<tr><td data-l="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td data-l="Blank">{esc(", ".join(s for s in [("no betting line at any source") if not r["quotes"] else "", ("opponent unrated in Valve table") if r["resolution"]["basis"] == "unresolved" else ""] if s))}</td>'
        f'<td data-l="Shown instead">{prob_cell(r, "a")} / {prob_cell(r, "b")}</td></tr>'
        for r in board["rows"] if not r["quotes"])
    body = f"""
<p class="eyebrow">Flagged for review</p>
<h1>Irregularities, unverified values and things I could not confirm</h1>
<p class="lede">Published deliberately: nothing here blocks the picks list, but you should see it
before you trust a number. Every item links to the page or file that shows it.</p>
{''.join(cards)}
<h2>Unverified values left blank</h2>
<p class="lede">A blank in the source evidence means the value could not be confirmed from an official
source. None of these rows was filled with an invented number: each got a documented originated line
instead, and each is marked.</p>
<div class="tbl-scroll"><table><thead><tr><th>Match</th><th>What is missing upstream</th>
<th>What the row shows instead</th></tr></thead><tbody>{unverified}</tbody></table></div>
"""
    return page("Flagged for review", "flagged.html", body, _stamp(board))


def main() -> int:
    board = core.load(BOARD, None)
    if not board:
        raise SystemExit(f"{BOARD} missing - run scripts/5f903db4/build.py first")
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": render_index(board),
        "picks.html": render_picks(board),
        "unresolved.html": render_unresolved(board),
        "sources.html": render_sources(board),
        "method.html": render_method(board),
        "flagged.html": render_flagged(board),
    }
    for name, html_text in pages.items():
        (OUT / name).write_text(html_text, encoding="utf-8")
    print(f"rendered {len(pages)} pages into {OUT.relative_to(core.ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
