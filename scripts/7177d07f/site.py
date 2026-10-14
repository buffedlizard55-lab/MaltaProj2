#!/usr/bin/env python3
"""Render the session-7177d07f `unresolved/` section from data/7177d07f/board.json.

Pages (all mobile-first, no external scripts, no external fonts):
  unresolved/index.html       Executive summary + a pick for every open HotSpawn CS2 fixture
  unresolved/method.html      The resolution ladder, formulas, calibration and limitations
  unresolved/flagged.html     Contested identities, low-confidence rows, cross-board disagreements
  unresolved/repo-audit.html  Line-by-line repository review and the verification performed
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "7177d07f"
OUT = ROOT / "unresolved"

LOBBY = "https://play.hotspawn.com/lobby"
VALVE_PAGE = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
              "live/2026/standings_global_2026_10_05.md")

BASIS_LABEL = {
    "featured": "Featured bookmaker line",
    "esportsbook": "Esportsbook / exchange price",
    "originated_vrs": "Originated — official Valve VRS",
    "originated_rank": "Originated — published VRS standing",
    "unresolved": "Unresolved — no defensible evidence",
}

CSS = """
:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--acc2)}
header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.brand{font-weight:700;margin-right:auto}
.bar nav{display:flex;gap:6px;flex-wrap:wrap}
.bar nav a{padding:6px 10px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px}
.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:1100px;margin:0 auto;padding:14px}
h1{font-size:22px;margin:6px 0 4px}
h2{font-size:18px;margin:26px 0 8px}
h3{font-size:15px;margin:16px 0 6px}
.mut{color:var(--mut)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.stat b{display:block;font-size:22px}
.stat span{color:var(--mut);font-size:13px}
.pickcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:11px 12px;margin:8px 0}
.pickcard .when{font-size:12.5px;color:var(--mut)}
.teams{display:flex;justify-content:space-between;gap:8px;margin:4px 0}
.team{flex:1;overflow-wrap:anywhere}
.team.pk{font-weight:700;color:var(--acc)}
.pct{font-variant-numeric:tabular-nums;font-weight:700}
.meter{height:7px;background:#2a303c;border-radius:4px;overflow:hidden;margin:3px 0 6px}
.meter i{display:block;height:100%;background:var(--acc)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700;margin-right:4px}
.b-featured{background:#1f6f4d}
.b-esportsbook{background:#1f6f4d}
.b-originated_vrs{background:#245a85}
.b-originated_rank{background:#5b3a12;color:#ffd9a3}
.b-unresolved{background:#5b2222}
.b-flag{background:#3a2c12;color:#ffd9a3}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);background:#131720}
.small{font-size:12.5px;color:var(--mut)}
.note{background:#151a22;border-left:3px solid var(--acc2);padding:10px 12px;border-radius:6px;margin:10px 0}
.warnbox{background:#221a10;border-left:3px solid var(--warn);padding:10px 12px;border-radius:6px;margin:10px 0}
.linkcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.linkcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.linkcard a{font-weight:700;font-size:16px}
.foot{margin:30px 0 10px;color:var(--mut);font-size:13px}
code{background:#11151c;padding:1px 5px;border-radius:4px}
ul.tight li{margin:3px 0}
@media (max-width:760px){
 table.cards thead{display:none}
 table.cards tr{display:block;border-bottom:2px solid var(--line);padding:6px 0}
 table.cards td{display:block;border:none;padding:4px 10px}
 table.cards td:before{content:attr(data-l);display:block;font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.05em}
}
"""

NAV = [
    ("index.html", "Picks for every match"),
    ("flagged.html", "Unresolved & contested"),
    ("method.html", "Method & sources"),
    ("repo-audit.html", "Repository review"),
    ("../index.html", "Main dashboard"),
]


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def pct(value):
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def page(title, active, body, generated):
    nav = "".join(
        f'<a href="{h}"{" class=on" if h == active else ""}>{esc(t)}</a>' for h, t in NAV
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Unresolved picks · HotSpawn CS2</title>
<meta name="description" content="A pick and win probability for every open HotSpawn CS2 fixture, with the evidence basis and limitation published for each row.">
<style>{CSS}</style></head><body>
<header><div class="bar"><div class="brand">🔎 Unresolved picks · CS2 Pick'ems</div><nav>{nav}</nav></div></header>
<main>{body}
<p class="foot">Built {esc(generated)} UTC by an automated GitHub Actions run — no manual input. Session <code>7177d07f</code>.
HotSpawn is used for fixture discovery only; its crowd pick percentage is never read or used.
Originated lines are model output with an official rating input, not bookmaker prices, and not betting advice. 18+.</p>
</main></body></html>
"""


def render_index(board):
    s = board["summary"]
    rows_cards = "".join(pick_card(r) for r in board["rows"])
    unresolved_block = (
        "".join(
            f'<div class="pickcard"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b> '
            f'<span class="small">{esc(r["competition"])} · starts {esc(r["start_utc"])}</span>'
            f'<div>Probability: <b>blank — unverified</b></div>'
            f'<div class="small">Limitation: no eligible bookmaker/exchange price, no complete official '
            f'rating for both teams, and no HLTV ranking evidence that identifies both sides.</div>'
            f'<div class="small">Official fixture source: <a href="{esc(r["hotspawn_url"])}">{esc(r["hotspawn_url"])}</a></div></div>'
            for r in board["unresolved_rows"]
        ) if board["unresolved_rows"] else
        '<p class="note">No fixture in this run is left without a pick. Every pick below is labelled with '
        'the evidence that produced it, and rows whose evidence is weak or contested are listed on the '
        '<a href="flagged.html">Unresolved &amp; contested</a> page. This is a statement about this '
        'run\'s lobby inventory, not a guarantee of permanent full coverage.</p>'
    )
    body = f"""
<h1>Executive summary — where the picks are</h1>
<p class="mut">Every Counter-Strike 2 match currently open in the HotSpawn Pick'ems lobby, each with a
pick, a win probability, the evidence that produced it and a link to the official source. Rows the
featured bookmaker route cannot price are resolved here with HLTV research, esportsbook/exchange
lines and the official Valve regional standings — never with HotSpawn's crowd percentage.</p>

<div class="stats">
<div class="stat"><b>{s['open']}</b><span>open CS2 fixtures</span></div>
<div class="stat"><b>{s['with_pick']}</b><span>with a pick</span></div>
<div class="stat"><b>{s['by_basis'].get('featured', 0)}</b><span>featured bookmaker line</span></div>
<div class="stat"><b>{s['by_basis'].get('esportsbook', 0)}</b><span>esportsbook / exchange</span></div>
<div class="stat"><b>{s['by_basis'].get('originated_vrs', 0)}</b><span>originated (Valve VRS)</span></div>
<div class="stat"><b>{s['by_basis'].get('originated_rank', 0)}</b><span>originated (VRS standing)</span></div>
<div class="stat"><b>{s['unresolved']}</b><span>unresolved / blank</span></div>
<div class="stat"><b><span class="small">{esc(board['generated_utc'])}</span></b><span>last build (UTC)</span></div>
</div>

<h2>Unresolved picks &amp; limitations</h2>
{unresolved_block}

<h2>Where to find updated pick lists on this site</h2>
<div class="linkcards">
<div class="linkcard"><a href="index.html">This page — every match</a><p class="small">All open CS2
fixtures with a pick, probability and basis. Rebuilt automatically every 4 hours.</p></div>
<div class="linkcard"><a href="../cs2.html">Source-linked CS2 picks (strict)</a><p class="small">Only
eligible primary-bookmaker prices; everything else stays blank. The conservative view.</p></div>
<div class="linkcard"><a href="../board/picks.html">Expanded picks · models included</a><p class="small">
Market + model coverage with identity flags and source times.</p></div>
<div class="linkcard"><a href="../picks-every-match/index.html">Every-match picks at a glance</a>
<p class="small">Mobile pick cards with A/B/C/D evidence tiers.</p></div>
<div class="linkcard"><a href="../ourline/index.html">Our line</a><p class="small">Market consensus
blended with a calibrated Valve VRS model, plus a graded track record.</p></div>
<div class="linkcard"><a href="../coverage/index.html">Coverage board</a><p class="small">Every lobby
fixture: market, exchange, originated estimate, or blank + flagged.</p></div>
<div class="linkcard"><a href="../summary/index.html">Where the picks are (hub)</a><p class="small">
Independent cross-checks, sources and gaps.</p></div>
<div class="linkcard"><a href="../flagged.html">Flagged for review</a><p class="small">Site-wide
unverified or irregular items with source links.</p></div>
</div>

<h2>Every open CS2 match ({s['open']})</h2>
{rows_cards if rows_cards else '<p>No open CS2 fixtures in this run.</p>'}

<p class="small">Fixture inventory: <a href="{LOBBY}">official HotSpawn Pick'ems lobby</a>
(captured {esc((board['inventory_source'] or {}).get('observed_at_utc'))}).
Official ratings: <a href="{VALVE_PAGE}">Valve regional standings</a>.
Research: <a href="https://www.hltv.org/betting/analytics">HLTV betting analytics</a>.</p>
"""
    return page("Executive summary — picks for every match", "index.html", body, board["generated_utc"])


def pick_card(r):
    pa, pb = r.get("prob_a"), r.get("prob_b")
    meter = f'<div class="meter"><i style="width:{(pa or 0.5) * 100:.0f}%"></i></div>' if pa is not None else ""
    if r["pick"]:
        headline = (f'PICK: <b>{esc(r["pick"])}</b> · {pct(r["pick_prob"])} · {esc(r["confidence"])}')
        badge = f'<span class="badge b-{r["basis"]}">{esc(BASIS_LABEL.get(r["basis"], r["basis"]))}</span>'
    else:
        headline = "NO PICK — probability left blank"
        badge = f'<span class="badge b-unresolved">{esc(BASIS_LABEL["unresolved"])}</span>'
    ev = "".join(
        f'<li class="small"><a href="{esc(e.get("url"))}" rel="noopener">{esc(e.get("source"))}</a> — '
        f'{esc(e.get("kind"))}: {esc(e.get("detail"))}'
        f'{" (read " + esc(e.get("read_utc")) + ")" if e.get("read_utc") else ""}</li>'
        for e in r["evidence"]
    )
    notes = "".join(
        f'<li class="small">{esc(n)}</li>'
        for e in r["evidence"] if e.get("notes") for n in e["notes"]
    )
    cross = ""
    if r.get("cross_check"):
        bits = " · ".join(
            f'{esc(c["board"])}: {esc(c["pick"])} {"agrees" if c["agrees"] else "<b>disagrees</b>"}'
            for c in r["cross_check"]
        )
        cross = f'<div class="small">Other boards — {bits}</div>'
    flags = "".join(f'<span class="badge b-flag">{esc(f.replace("_", " "))}</span>' for f in r["flags"])
    return (
        f'<div class="pickcard" id="m-{esc(r["fixture_id"])}">'
        f'<div class="when">{esc(r["start_utc"])} · locks {esc(r["lock_utc"])} · '
        f'{esc(r["competition"])} · Tier {esc(r["tier"] or "?")} · #{esc(r["fixture_id"])}</div>'
        f'<div class="teams">'
        f'<span class="team{" pk" if r["pick"] == r["team_a"] else ""}">{esc(r["team_a"])} '
        f'<span class="pct">{pct(pa)}</span></span>'
        f'<span class="team{" pk" if r["pick"] == r["team_b"] else ""}" style="text-align:right">'
        f'{esc(r["team_b"])} <span class="pct">{pct(pb)}</span></span></div>{meter}'
        f'<div><b>{headline}</b> {badge}</div>'
        f'<div class="small">HotSpawn source: <a href="{esc(r["hotspawn_url"])}" rel="noopener">'
        f'{esc(r["hotspawn_url_kind"])}</a></div>'
        f'{f"<ul>{ev}</ul>" if ev else ""}'
        f'{f"<ul>{notes}</ul>" if notes else ""}'
        f'{cross}{flags}</div>'
    )


def render_method(board):
    s = board["summary"]
    cal = s["calibration"]
    src_rows = "".join(
        f'<tr><td data-l="Source">{esc(x.get("key"))}</td>'
        f'<td data-l="URL"><a href="{esc(x.get("url"))}" rel="noopener">{esc(x.get("url"))}</a></td>'
        f'<td data-l="Result">{esc(x.get("http_status") if x.get("http_status") else "unreachable")}'
        f'{esc(" · " + x["error"] if x.get("error") else "")}</td>'
        f'<td data-l="Rows">{esc(x.get("rows"))}</td>'
        f'<td data-l="Read (UTC)">{esc(x.get("retrieved_utc"))}</td></tr>'
        for x in (board["snapshot_source"].get("sources") or [])
    )
    body = f"""
<h1>Method &amp; sources</h1>
<p class="mut">How each pick on the <a href="index.html">every-match page</a> was produced, in the
order the project brief requires, and what each label means.</p>

<h2>The featured route (tried first for every match)</h2>
<p>An eligible two-sided primary-bookmaker quote (Pinnacle, Bovada) joined to the fixture by both team
names after normalisation <em>and</em> the exact UTC kickoff, prematch and open, with confirmed outcome
ordering, a unique join, an unpassed pick lock and a quote/fixture snapshot no older than four hours.
Rows that meet it are labelled <span class="badge b-featured">Featured bookmaker line</span> and are
not re-derived here.</p>

<h2>The fallback ladder (only for matches the featured route cannot resolve)</h2>
<ul>
<li><b>1. HLTV.</b> Identity and ranking evidence read from official HLTV match, team and analytics
pages, archived with read times in <code>data/7177d07f/hltv_research.json</code>. HLTV 'Best Odds'
columns were empty for every unpriced fixture inspected on 2026-10-14, so HLTV contributes identity
and ranking — not a price. HLTV's logged-in user-vote split is recorded but never used as a
probability, exactly like HotSpawn's crowd percentage.</li>
<li><b>2. Esportsbooks / esports betting lines.</b> Melbet's public LineFeed, Thunderpick coefficients
as published by bo3.gg, and Kalshi exchange books. A price is used only when both team names match the
fixture; the no-vig probability is <code>p = (1/odds) / Σ(1/odds)</code>.</li>
<li><b>3. Official Valve VRS.</b> Points from Valve's own
<a href="{VALVE_PAGE}">counter-strike_regional_standings</a> file, read through the GitHub API, with
Valve's published Glicko expected-win curve and the slope re-fitted against this snapshot's
market-priced fixtures (k = {esc(cal.get('k'))}, {esc(cal.get('pairs_used'))} pairs,
MAE {esc(round(cal['mae_prob'], 4)) if cal.get('mae_prob') is not None else '—'}).</li>
<li><b>4. Published VRS standing substitution.</b> Where a team appears in no Valve file row but HLTV
publishes its Valve VRS standing, points are substituted from the file's standing-order position.
This is a documented substitution, flagged
<code>rating_from_published_standing_not_a_measured_rating</code>.</li>
</ul>

<h2>What each label means</h2>
<table class="cards"><thead><tr><th>Label</th><th>Meaning</th></tr></thead><tbody>
<tr><td data-l="Label"><span class="badge b-featured">Featured bookmaker line</span></td>
<td data-l="Meaning">Derived from eligible external bookmaker prices. Strongest evidence on the site.</td></tr>
<tr><td data-l="Label"><span class="badge b-esportsbook">Esportsbook / exchange price</span></td>
<td data-l="Meaning">Two-sided price from an esportsbook or regulated exchange read this run.</td></tr>
<tr><td data-l="Label"><span class="badge b-originated_vrs">Originated — official Valve VRS</span></td>
<td data-l="Meaning">No reachable price; the line is originated from both teams' official Valve points.</td></tr>
<tr><td data-l="Label"><span class="badge b-originated_rank">Originated — published VRS standing</span></td>
<td data-l="Meaning">One side has only a published standing; weakest evidence that still produces a number.</td></tr>
<tr><td data-l="Label"><span class="badge b-unresolved">Unresolved</span></td>
<td data-l="Meaning">No defensible evidence. The probability is left blank — never defaulted to 50/50.</td></tr>
</tbody></table>

<h2>Source access log for this build</h2>
<div style="overflow-x:auto"><table class="cards"><thead><tr><th>Source</th><th>URL</th><th>Result</th>
<th>Rows</th><th>Read (UTC)</th></tr></thead><tbody>{src_rows}</tbody></table></div>
<p class="small">This collector runs on GitHub-hosted runners. When a source cannot be read it is
recorded as unreachable and the build falls back to the last committed snapshot; a source failure
never becomes a guessed number.</p>

<h2>Limitations</h2>
<ul class="tight">
<li>Originated lines are model output with an official rating input. They are not bookmaker prices and
no bookmaker is quoting these matches.</li>
<li>Valve's published file is a snapshot ({esc(s.get('valve_snapshot'))}, {esc(s.get('valve_rows'))} rows);
rosters and ratings move between snapshots.</li>
<li>HLTV's republication of the Valve VRS rank and Valve's own file can disagree because they are
different snapshot dates. Both are published where they differ.</li>
<li>Team identity is the largest source of error on the tier-C events. Every alias used is listed with
its evidence and its counter-evidence on the <a href="flagged.html">Unresolved &amp; contested</a> page.</li>
<li>The ladder is applied to this run's lobby inventory. A new low-tier fixture with no rating and no
price anywhere would appear as <span class="badge b-unresolved">Unresolved</span> rather than be filled in.</li>
</ul>
"""
    return page("Method & sources", "method.html", body, board["generated_utc"])


def render_flagged(board):
    contested = [r for r in board["rows"] if any(
        f in r["flags"] for f in (
            "pick_disagrees_with_every_other_published_board",
            "pick_disagrees_with_at_least_one_other_board",
            "rating_from_published_standing_not_a_measured_rating",
            "multiple_official_rows_same_team",
        ))]
    cards = []
    for r in contested:
        bits = "".join(
            f'<li class="small">{esc(c["board"])} → <a href="../{esc(c["page"])}">{esc(c["pick"])}</a> '
            f'({esc(c["basis"])}) — {"agrees" if c["agrees"] else "<b>disagrees with this run</b>"}'
            f'{esc(" · " + pct(c["prob"])) if c.get("prob") else ""}</li>'
            for c in r["cross_check"]
        )
        cards.append(
            f'<div class="pickcard"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b> '
            f'<span class="small">{esc(r["competition"])} · {esc(r["start_utc"])} · #{esc(r["fixture_id"])}</span>'
            f'<div>This run: <b>{esc(r["pick"])}</b> {esc(pct(r["pick_prob"]))} '
            f'<span class="badge b-{r["basis"]}">{esc(BASIS_LABEL.get(r["basis"], r["basis"]))}</span></div>'
            f'<ul>{bits}</ul>'
            f'<div class="small">Flags: {"".join(f"<code>{esc(f)}</code> " for f in r["flags"])}</div>'
            f'<div class="small">HotSpawn: <a href="{esc(r["hotspawn_url"])}" rel="noopener">{esc(r["hotspawn_url"])}</a></div></div>'
        )
    identity = []
    for item in board.get("identity_findings") or []:
        ev = "".join(f'<li class="small"><a href="{esc(u)}" rel="noopener">{esc(u)}</a></li>' for u in item.get("evidence") or [])
        identity.append(
            f'<div class="pickcard"><b>{esc(item.get("hotspawn_name"))} → '
            f'{esc(item.get("resolved_to_valve_row") or "unresolved")}</b>'
            f'<div class="small">Confidence: {esc(item.get("confidence"))}</div><ul>{ev}</ul>'
            + (f'<div class="small"><b>Counter-evidence:</b> {esc(item.get("counter_evidence"))}</div>'
               if item.get("counter_evidence") else "")
            + "</div>"
        )
    body = f"""
<h1>Unresolved &amp; contested</h1>
<p class="mut">Everything on this page is published for review. None of it blocks the site. Where a
number is shown, the flag says how weak the evidence behind it is; where no defensible evidence exists
the probability is blank.</p>

<h2>Rows with no pick (unresolved)</h2>
{"".join(f'<div class="pickcard"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b>'
         f'<div>Probability: <b>blank — unverified</b></div>'
         f'<div class="small">Limitation: no eligible bookmaker/exchange price and no complete official '
         f'rating for both teams. Official fixture source: '
         f'<a href="{esc(r["hotspawn_url"])}" rel="noopener">{esc(r["hotspawn_url"])}</a></div></div>'
         for r in board["unresolved_rows"])
 if board["unresolved_rows"] else
 '<p class="note">This run left no row without a pick. Every remaining limitation is a weaker-evidence '
 'or contested row, listed below.</p>'}

<h2>Contested or weak-evidence rows ({len(contested)})</h2>
{"".join(cards) if cards else '<p class="note">No contested rows in this run.</p>'}

<h2>Team-identity findings</h2>
{"".join(identity) if identity else '<p class="note">No identity findings recorded.</p>'}

<div class="warnbox"><b>Why identity matters more than arithmetic.</b> On the Elisa BreakOut Series 2
slots, HotSpawn's label <b>WROTBERRY</b> is matched by HLTV to <b>WBT</b> (roster DemQQ, Psycho,
s4ltovsk1yy, Smash, tyr1k — identical to Valve's official WBT row), while Kalshi's market tickers and
bo3.gg's roster pages point to <b>WBT Academy</b> (a different five). The two candidate rosters imply
opposite picks on WROTBERRY vs EAC, so both are published instead of one being silently chosen.</div>

<p class="small">Site-wide flagged pages:
<a href="../flagged.html">Flagged for review</a> ·
<a href="../summary/gaps.html">Cross-board disagreements (c0e223d3)</a> ·
<a href="../board/flagged.html">Full-coverage board flags (fe803b80)</a> ·
<a href="../audits/5cd24fb4/index.html">Fallback-source audit (5cd24fb4)</a>.</p>
"""
    return page("Unresolved & contested", "flagged.html", body, board["generated_utc"])


def render_repo_audit(board):
    s = board["summary"]
    body = f"""
<h1>Repository review</h1>
<p class="mut">Line-by-line review of what this session read, what it verified against an official
source, and what it could not confirm. Scope: session <code>7177d07f</code> only —
<code>scripts/7177d07f/**</code>, <code>data/7177d07f/**</code>, <code>unresolved/**</code>,
<code>tests/test_7177d07f.py</code>, <code>.github/workflows/unresolved-7177d07f.yml</code>.</p>

<h2>Inputs read (read-only, owned by other sessions)</h2>
<table class="cards"><thead><tr><th>File</th><th>Used for</th><th>Check performed</th></tr></thead><tbody>
<tr><td data-l="File"><code>data/hotspawn_matches.json</code></td>
<td data-l="Used for">Open CS2 fixture inventory</td>
<td data-l="Check">Rows filtered to <code>sport == cs2</code>, <code>status == scheduled</code> and a lock time in the future at build time; {esc(s['open'])} fixtures survive. Counts cross-checked against the lobby page.</td></tr>
<tr><td data-l="File"><code>data/lines.json</code></td>
<td data-l="Used for">Featured bookmaker resolution</td>
<td data-l="Check">Consensus probabilities used only where <code>bookmaker_lines</code> is non-empty; {esc(s['by_basis'].get('featured', 0))} rows qualify.</td></tr>
<tr><td data-l="File"><code>data/c64a5e19/board.json</code>, <code>data/fe803b80/board.json</code>, <code>data/f7279a54/board.json</code>, <code>data/coverage/board.json</code></td>
<td data-l="Used for">Independent cross-check of every pick</td>
<td data-l="Check">Per-fixture pick compared; agreements and disagreements published on each row and on <a href="flagged.html">Unresolved &amp; contested</a>.</td></tr>
<tr><td data-l="File"><a href="{VALVE_PAGE}">Valve regional standings</a></td>
<td data-l="Used for">Official rating input</td>
<td data-l="Check">Fetched through the GitHub API during collection ({esc(s.get('valve_rows'))} rows, snapshot {esc(s.get('valve_snapshot'))}); every roster string used for identity is compared character-by-character with the HLTV lineup.</td></tr>
</tbody></table>

<h2>What was verified against an official source</h2>
<ul class="tight">
<li>Every open fixture's existence, teams, competition, tier and start/lock time — <a href="{LOBBY}">HotSpawn lobby</a>.</li>
<li>Every rating used in an originated line — Valve's own standings file, with the row's points, standing and roster published on the row.</li>
<li>Every identity alias — an HLTV team or match page plus the matching Valve roster row.</li>
<li>Every bookmaker price — the source's own public URL and read time.</li>
<li>Every calibration pair — market consensus and both teams' official points from the same snapshot.</li>
</ul>

<h2>Irregularities found (flagged, not filled in)</h2>
<ul class="tight">
<li><b>LFO 10.</b> Valve's 2026-10-05 global file has no LFO 10 row, but HLTV publishes 'VRS #169' for
it. Earlier boards used the sibling LFO 7/8/9 rows instead. Three different documented estimates
exist; this run uses HLTV's published standing with the flag
<code>rating_from_published_standing_not_a_measured_rating</code> and publishes the conflict.</li>
<li><b>WROTBERRY.</b> Resolved to WBT by roster identity (HLTV lineup == Valve WBT row) while exchange
tickers say WBT Academy. The two imply opposite picks on WROTBERRY vs EAC; both published.</li>
<li><b>Banda Chuya / 6666.</b> Two official rows each share these names in Valve's file; the
highest-rated row is used and the duplication is flagged.</li>
<li><b>Envy.</b> HLTV's 'Envy' lineup is identical to Valve's '3DMAX' row (standing 21, 1500 points);
the name differs between sources.</li>
<li><b>HLTV numeric pricing absent.</b> The 'Best Odds' columns on every unpriced fixture inspected on
2026-10-14 were dashes, so HLTV could not supply a price even where it supplies a ranking.</li>
</ul>

<h2>Verification performed before publication</h2>
<ul class="tight">
<li><code>python -m unittest discover -s tests</code> — the whole repository suite, including
<code>tests/test_7177d07f.py</code>.</li>
<li><code>python scripts/stage_site.py</code> — every local link across every staged section resolves.</li>
<li><code>scripts/7177d07f/collect.py</code> then <code>build.py</code> then <code>site.py</code> — the
workflow re-runs all three and refuses to publish on a non-zero exit.</li>
</ul>

<h2>Not claimed</h2>
<p>This page does not claim that every historical file in the repository was independently verified,
nor that the ladder will always resolve a future fixture. It states what this run's inventory resolved
and publishes every limitation alongside it.</p>
"""
    return page("Repository review", "repo-audit.html", body, board["generated_utc"])


def main() -> int:
    board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render_index(board), encoding="utf-8")
    (OUT / "method.html").write_text(render_method(board), encoding="utf-8")
    (OUT / "flagged.html").write_text(render_flagged(board), encoding="utf-8")
    (OUT / "repo-audit.html").write_text(render_repo_audit(board), encoding="utf-8")
    print(f"unresolved/ built: 4 pages, {len(board['rows'])} rows, {board['summary']['unresolved']} unresolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
