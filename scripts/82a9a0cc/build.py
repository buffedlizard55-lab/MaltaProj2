#!/usr/bin/env python3
"""Render the mobile-first HotSpawn-live static dashboard from its audited board."""
from __future__ import annotations

import html
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "data" / "82a9a0cc" / "board.json"
OUT = ROOT / "hotspawn-live"
STYLE_SOURCE = Path(__file__).resolve().parent / "style.css"

BASIS = {
    "market": ("Featured market", "market", "Two-way external market consensus retained unchanged from the strict featured board."),
    "researched_market_alias": ("2-book researched line", "market", "Bovada and Melbet agree on the exact opponent and kickoff; only HotSpawn's ex- prefix differs."),
    "vrs_model": ("Valve VRS model", "model", "Both names map uniquely to the latest official Valve VRS; the fitted transform converts their point gap."),
    "vrs_model_roster_resolved": ("Roster-resolved VRS", "model", "A current bo3.gg team rank selects the matching duplicate official VRS row before modelling."),
    "vrs_ambiguity_robust": ("VRS range · directional", "directional", "Every official duplicate-name scenario picks the same side; the published edge is the one closest to 50%."),
    "vrs_floor_scenario": ("VRS floor · directional", "directional", "Only one team is rated. The other is set to the official table floor; treat this as a sensitivity scenario."),
}


def e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def pct(value) -> str:
    return f"{100 * float(value):.1f}%"


def date_time(value: str | None, *, lock=False) -> str:
    if not value:
        return "Time unconfirmed"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    prefix = "Locks " if lock else ""
    return prefix + dt.strftime("%d %b · %H:%M UTC")


def nav(current: str) -> str:
    items = [("overview", "./", "Overview"), ("picks", "picks.html", "All picks"),
             ("unresolved", "unresolved.html", "Limits"), ("sources", "sources.html", "Sources"),
             ("method", "method.html", "Method"), ("flagged", "flagged.html", "Review")]
    top = "".join(f'<a href="{url}"' + (' aria-current="page"' if key == current else '') + f'>{label}</a>'
                  for key, url, label in items)
    bottom_items = [("overview", "./", "⌂", "Home"), ("picks", "picks.html", "✓", "Picks"),
                    ("unresolved", "unresolved.html", "!", "Limits"), ("method", "method.html", "i", "Method")]
    bottom = "".join(f'<a href="{url}"' + (' aria-current="page"' if key == current else '') + f'><b>{icon}</b>{label}</a>'
                     for key, url, icon, label in bottom_items)
    return f'''<header class="site-header"><div class="header-inner">
<a class="brand" href="./"><span class="brand-mark">CS2</span><span>Live Pick Board<small>Independent · not HotSpawn</small></span></a>
<nav class="top-nav" aria-label="Primary">{top}</nav></div></header><nav class="bottom-nav" aria-label="Mobile">{bottom}</nav>'''


def shell(title: str, description: str, current: str, body: str, *, scripts="") -> str:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)} · CS2 Live Pick Board</title><meta name="description" content="{e(description)}"><meta name="theme-color" content="#162b3a">
<link rel="stylesheet" href="style.css"></head><body><a class="skip-link" href="#main">Skip to content</a>{nav(current)}
<main id="main">{body}</main><footer class="site-footer"><div class="footer-inner"><div><strong>CS2 Live Pick Board</strong><div class="mini">Independent research. HotSpawn is used for fixtures—not probability.</div></div>
<div class="footer-links"><a href="sources.html">Source ledger</a><a href="method.html">Method</a><a href="data/board.json">Machine data</a><a href="../flagged.html">Repository review</a></div></div></footer>{scripts}</body></html>'''


def source_chips(row: dict, limit: int | None = None) -> str:
    evidence = row.get("evidence") or []
    probability = [item for item in evidence if item.get("kind") != "fixture"]
    fixture = [item for item in evidence if item.get("kind") == "fixture"]
    items = probability + fixture
    if limit:
        items = items[:limit]
    return "".join(f'<a class="source-chip" href="{e(item["url"])}" rel="noopener">↗ {e(item["label"])}</a>'
                   for item in items if item.get("url"))


def match_card(row: dict, compact=False) -> str:
    line = row.get("line")
    if not line:
        return f'''<article class="match-card" data-row data-basis="unresolved" data-search="{e((row['team_a']+' '+row['team_b']+' '+row['competition']).casefold())}">
<div class="match-top"><span class="competition">{e(row['competition'])}</span><span>{e(date_time(row['lock_utc'], lock=True))}</span></div>
<div class="match-main"><h3 class="match-title">{e(row['team_a'])} <span class="muted">vs</span> {e(row['team_b'])}</h3><div class="notice danger"><strong>Pick unresolved</strong><p>{e(row['resolution']['reason'])}</p></div></div>
<div class="match-foot"><div class="sources">{source_chips(row)}</div></div></article>'''
    basis, tag_class, explanation = BASIS[line["basis"]]
    p_a, p_b = float(line["prob_a"]), float(line["prob_b"])
    confidence = line.get("confidence") or ("Directional" if line.get("directional") else "Published")
    flags = "" if not row.get("flag_ids") else f'<span class="tag">{len(row["flag_ids"])} review note{"s" if len(row["flag_ids"]) != 1 else ""}</span>'
    detail = (f'''<div class="prob-values"><span>{e(row['team_a'])} · {pct(p_a)}</span><span>{e(row['team_b'])} · {pct(p_b)}</span></div>''' if compact else f'''<div class="prob-head"><span>Estimated win probability</span><span>100%</span></div>
<div class="prob-bar" role="img" aria-label="{e(row['team_a'])} {pct(p_a)}, {e(row['team_b'])} {pct(p_b)}"><span class="prob-a" style="width:{100*p_a:.2f}%"></span><span class="prob-b" style="width:{100*p_b:.2f}%"></span></div>
<div class="prob-values"><span>{e(row['team_a'])} · {pct(p_a)}</span><span>{e(row['team_b'])} · {pct(p_b)}</span></div>''')
    return f'''<article class="match-card" id="match-{e(row['fixture_id'])}" data-row data-basis="{e(line['basis'])}" data-lock="{e(row['lock_utc'])}" data-search="{e((row['team_a']+' '+row['team_b']+' '+row['competition']+' '+line['pick_team']).casefold())}">
<div class="match-top"><span class="competition">{e(row['competition'])}</span><span class="lock">{e(date_time(row['lock_utc'], lock=True))}</span></div>
<div class="match-main"><h3 class="match-title">{e(row['team_a'])} <span class="muted">vs</span> {e(row['team_b'])}</h3>
<div class="pick-call"><span><small>Pick</small><strong>{e(line['pick_team'])}</strong></span><span class="pick-percent">{pct(line['pick_prob'])}</span></div>{detail}</div>
<div class="match-foot"><div class="tags"><span class="tag {tag_class}">{e(basis)}</span><span class="tag">{e(confidence)}</span>{flags}</div>
<p class="explainer">{e(explanation)}</p><div class="sources">{source_chips(row, 4 if compact else None)}</div></div></article>'''


def page_intro(kicker: str, title: str, text: str) -> str:
    return f'<div class="page-intro"><p class="breadcrumb"><a href="./">Overview</a> / {e(kicker)}</p><h1>{e(title)}</h1><p>{e(text)}</p></div>'


def overview(board: dict) -> str:
    s, rows = board["summary"], board["rows"]
    preview = "".join(match_card(row, compact=True) for row in rows[:3])
    generated = date_time(board["generated_utc"])
    unresolved_label = f'{s["unresolved"]} unresolved' if s["unresolved"] else "0 unresolved"
    body = f'''<section class="hero"><p class="eyebrow">Current HotSpawn lobby · independently priced</p><h1>Every open CS2 match. One clear pick.</h1>
<p class="lede">A source-first board with both teams’ win probabilities. External lines lead; documented Valve VRS scenarios fill the strict gaps. Crowd ownership is never used.</p>
<div class="hero-meta"><span class="status-pill"><span class="live-dot"></span>{e(generated)}</span><span class="status-pill">{s['with_pick']}/{s['open']} picks resolved</span><span class="status-pill">4-hour refresh target</span></div>
<div class="hero-actions"><a class="button button-primary" href="picks.html">See all {s['open']} picks →</a><a class="button button-secondary" href="unresolved.html">{e(unresolved_label)} · read limits</a></div></section>
<div class="stats" aria-label="Board summary"><div class="stat"><strong>{s['open']}</strong><span>Open matches</span></div><div class="stat"><strong>{s['featured_market']+s['researched_market']}</strong><span>External-market picks</span></div><div class="stat"><strong>{s['vrs_pair']+s['vrs_robust']}</strong><span>Two-sided VRS picks</span></div><div class="stat"><strong>{s['vrs_floor_scenario']}</strong><span>Directional scenarios</span></div></div>
<section class="section" id="executive-summary"><div class="section-head"><div><p class="kicker">Executive summary</p><h2>What to know before the picks</h2></div></div>
<div class="summary-grid"><article class="summary-card"><p class="kicker">Coverage</p><h3>{s['with_pick']} of {s['open']} resolved</h3><p>Every currently captured open fixture has an explicit side and both probabilities.</p></article>
<article class="summary-card"><p class="kicker">Featured gaps</p><h3>{s['featured_gaps_resolved']} researched</h3><p>Missing featured-book lines were rebuilt through the published evidence ladder. <a href="unresolved.html">Inspect each one.</a></p></article>
<article class="summary-card"><p class="kicker">Hard boundary</p><h3>No crowd signal</h3><p>HotSpawn pick ownership is excluded from capture, modelling, confidence and tiebreaks.</p></article>
<article class="summary-card"><p class="kicker">Review</p><h3>{len(board['flags'])} disclosed issues</h3><p>Dated VRS, identity joins and one-sided scenarios stay visible. <a href="flagged.html">Open review queue.</a></p></article></div></section>
<section class="section"><div class="section-head"><div><p class="kicker">Next on the board</p><h2>Current picks</h2></div><a class="text-link" href="picks.html">All picks →</a></div><div class="preview-grid">{preview}</div></section>
<section class="section"><div class="notice"><strong>Unresolved picks & limitations is a first-class page.</strong><p>It currently reports {s['unresolved']} blank rows, documents how all {s['featured_gaps_resolved']} featured gaps were resolved, and states the exact source limitations. <a href="unresolved.html">Open limitations →</a></p></div></section>
<section class="section"><div class="section-head"><div><p class="kicker">Audit trail</p><h2>Follow the evidence</h2></div></div><div class="summary-grid">
<article class="info-card"><h3>All picks</h3><p>Side, two probabilities, lock, basis and source links on every card.</p><p><a class="text-link" href="picks.html">Open list →</a></p></article>
<article class="info-card"><h3>Unresolved & limits</h3><p>Blank-row policy, researched gaps and honest boundaries.</p><p><a class="text-link" href="unresolved.html">Review limits →</a></p></article>
<article class="info-card"><h3>Sources</h3><p>Collection status plus a 19-row, source-linked ledger.</p><p><a class="text-link" href="sources.html">View ledger →</a></p></article>
<article class="info-card"><h3>Method</h3><p>Market rules, duplicate handling and the exact VRS transform.</p><p><a class="text-link" href="method.html">Read method →</a></p></article></div></section>'''
    return shell("Overview", "Every current HotSpawn CS2 fixture with a clear pick, both win probabilities, and linked evidence.", "overview", body)


def picks_page(board: dict) -> str:
    cards = "".join(match_card(row) for row in board["rows"])
    body = page_intro("All picks", "The complete live board", "Every captured open HotSpawn CS2 fixture, sorted by lock time. The pick is obvious; the probability basis and source remain attached.")
    body += f'''<div class="notice warning"><strong>Read the basis, not only the percentage.</strong><p>Market estimates and dated VRS scenarios are visually labelled. Directional floor scenarios are not sportsbook-equivalent confidence.</p></div>
<div class="toolbar"><label><span class="skip-link">Search fixtures</span><input class="search" id="search" type="search" placeholder="Search team or competition…" autocomplete="off"></label><div class="filters" aria-label="Filter picks">
<button class="filter active" data-filter="all">All {board['summary']['open']}</button><button class="filter" data-filter="market">Market</button><button class="filter" data-filter="model">VRS pair</button><button class="filter" data-filter="directional">Directional</button></div></div>
<div class="match-list" id="matches">{cards}</div><p class="muted mini" id="no-results" hidden>No matches fit that filter.</p>'''
    script = '''<script>(()=>{const rows=[...document.querySelectorAll('[data-row]')],search=document.querySelector('#search'),buttons=[...document.querySelectorAll('[data-filter]')];let filter='all';function group(b){if(b==='market'||b==='researched_market_alias')return'market';if(b==='vrs_floor_scenario'||b==='vrs_ambiguity_robust')return'directional';return b.startsWith('vrs_')?'model':'unresolved'}function apply(){const q=search.value.trim().toLowerCase();let n=0;rows.forEach(r=>{const show=(!q||r.dataset.search.includes(q))&&(filter==='all'||group(r.dataset.basis)===filter);r.hidden=!show;if(show)n++});document.querySelector('#no-results').hidden=n>0}buttons.forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;buttons.forEach(x=>x.classList.toggle('active',x===b));apply()}));search.addEventListener('input',apply);const now=Date.now();rows.forEach(r=>{if(r.dataset.lock&&now>=Date.parse(r.dataset.lock)){r.classList.add('locked');const x=r.querySelector('.lock');if(x)x.textContent='Locked'}})})();</script>'''
    return shell("All picks", "All open HotSpawn CS2 fixtures with picks, both probabilities, method labels, and sources.", "picks", body, scripts=script)


def unresolved_page(board: dict) -> str:
    unresolved = [row for row in board["rows"] if not row.get("line")]
    gaps = [row for row in board["rows"] if not row["base_featured_line"]]
    status = (f'<div class="notice danger"><strong>{len(unresolved)} picks remain blank.</strong><p>No unsupported value was invented. Exact limitations appear below.</p></div>' if unresolved else
              f'<div class="notice"><strong>0 current picks are blank.</strong><p>All {len(gaps)} fixtures absent from the strict featured-market board were resolved through documented external or official evidence. This can change on the next refresh.</p></div>')
    unresolved_cards = "".join(match_card(row) for row in unresolved)
    gap_cards = "".join(match_card(row) for row in gaps)
    body = page_intro("Limits", "Unresolved picks & limitations", "The board never fills a missing value with HotSpawn crowd ownership or an undocumented hunch. Unsupported future rows stay blank here.") + status
    if unresolved:
        body += f'<section class="section"><h2>Still unresolved</h2><div class="match-list">{unresolved_cards}</div></section>'
    body += f'''<section class="section"><div class="section-head"><div><p class="kicker">Resolved featured gaps</p><h2>{len(gaps)} researched fixtures</h2><p>These had no line on the strict featured board. Their fallback basis is explicit on each card.</p></div></div><div class="match-list">{gap_cards}</div></section>
<section class="section"><div class="section-head"><div><p class="kicker">Standing limitations</p><h2>What the numbers cannot claim</h2></div></div><div class="summary-grid">
<article class="info-card"><h3>VRS dated {e(board['method']['vrs_snapshot'])}</h3><p>The latest official global file was {e(board['method']['vrs_age_days'])} days old at capture—outside the 14-day preferred window.</p></article>
<article class="info-card"><h3>HLTV returned 403</h3><p>The automated current-matches probe was blocked. No current numeric HLTV value was inferred.</p></article>
<article class="info-card"><h3>One-sided is directional</h3><p>UPGRADE–flacons and Zetta–LOS NINOS set the unrated team to the official VRS floor. That is a scenario, not a direct market.</p></article>
<article class="info-card"><h3>Future rows can be blank</h3><p>If direct lines, identity evidence and official VRS cannot establish a side, probabilities remain empty and the exact reason appears here.</p></article></div></section>
<section class="section"><div class="notice warning"><strong>Do not interpret model percentages as betting advice.</strong><p>Roster changes, map vetoes, format and late substitutions may not be reflected. Verify lock and current prices at the linked source.</p></div></section>'''
    return shell("Unresolved & limitations", "Current unresolved CS2 picks, researched featured-market gaps, and exact evidence limitations.", "unresolved", body)


def sources_page(board: dict) -> str:
    attempts = board["method"]["research_attempts"]
    source_rows = []
    labels = {"pinnacle": "Pinnacle", "bovada": "Bovada", "melbet": "Melbet", "kalshi": "Kalshi", "polymarket_probe": "Polymarket", "hltv": "HLTV"}
    combined = dict(attempts["featured_markets"]); combined["hltv"] = attempts["hltv"]
    for key, item in combined.items():
        state = "OK" if item.get("ok") else f"HTTP {item.get('status') or 'error'}"
        detail = f"{item.get('quotes')} parsed quotes" if item.get("quotes") is not None else "research probe"
        source_rows.append(f'<tr><td><strong>{e(labels.get(key,key))}</strong></td><td>{e(state)}</td><td>{e(detail)}</td><td><a href="{e(item.get("url"))}">Official/source endpoint ↗</a></td></tr>')
    ledger = []
    for row in board["rows"]:
        line = row.get("line")
        basis = BASIS.get((line or {}).get("basis"), ("Unresolved", "", ""))[0]
        non_fixture = [item for item in row["evidence"] if item.get("kind") != "fixture"]
        srcs = non_fixture or row["evidence"]
        links = " · ".join(f'<a href="{e(item["url"])}">{e(item["label"])}</a>' for item in srcs)
        pick = f'{e(line["pick_team"])} · {pct(line["pick_prob"])}' if line else "Blank"
        ledger.append(f'<tr><td><strong>{e(row["team_a"])}–{e(row["team_b"])}</strong><div class="muted mini">{e(row["fixture_id"])}</div></td><td>{pick}</td><td>{e(basis)}</td><td>{links}</td></tr>')
    official = board["method"].get("vrs_latest_check") or {}
    body = page_intro("Sources", "Source health & line-by-line ledger", "Every published row links to the probability evidence used. Collection failures are disclosed instead of silently substituted.")
    body += f'''<section class="section"><div class="section-head"><div><p class="kicker">Collection health</p><h2>Markets & research probes</h2></div></div><div class="ledger-wrap"><table><thead><tr><th>Source</th><th>Capture</th><th>Result</th><th>Link</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div></section>
<section class="section"><div class="notice"><strong>Official Valve snapshot independently checked.</strong><p>Latest global file at {e(official.get('checked_utc'))}: <a href="{e(official.get('page_url') or board['method']['vrs_source'])}">{e(official.get('path') or board['method']['vrs_snapshot'])}</a>. Blob <span class="code">{e(official.get('blob_sha'))}</span>; official commit <a href="{e(official.get('commit_url'))}">{e((official.get('commit_sha') or '')[:10])}</a>.</p></div></section>
<section class="section"><div class="section-head"><div><p class="kicker">19-row audit</p><h2>Every pick, every source</h2><p>HotSpawn fixture links are retained in machine data; this ledger foregrounds the evidence behind each probability.</p></div></div><div class="ledger-wrap"><table><thead><tr><th>Fixture</th><th>Pick</th><th>Basis</th><th>Probability sources</th></tr></thead><tbody>{''.join(ledger)}</tbody></table></div></section>
<section class="section"><p class="mini muted">Raw captured inputs: <a href="../data/82a9a0cc/input.json">input.json</a> · Audited board: <a href="data/board.json">board.json</a>. HotSpawn crowd ownership fields are excluded from both.</p></section>'''
    return shell("Sources", "Source status and a source-linked ledger for every current CS2 pick.", "sources", body)


def method_page(board: dict) -> str:
    cal = board["method"]["calibration"]
    body = page_intro("Method", "How a fixture becomes a pick", "A deterministic evidence ladder keeps markets first, identity joins strict, and low-evidence scenarios visibly different from direct lines.")
    body += f'''<section class="section"><p class="kicker">Resolution ladder</p><h2>Stop at the first supported level</h2><ol class="steps">
<li><strong>Preserve strict featured market</strong><span>Use the upstream two-way, no-vig line unchanged when exact team pair and kickoff matching succeed.</span></li>
<li><strong>Attempt current HLTV research for strict gaps</strong><span>The current matches probe is evaluated first. At this capture it returned HTTP 403, so no numeric HLTV claim was inferred.</span></li>
<li><strong>Research exact-fixture sportsbook lines</strong><span>A spelling alias needs the exact opponent, exact kickoff, competition family, raw re-price validation and at least two independent books.</span></li>
<li><strong>Use two-sided official Valve VRS</strong><span>Both names must map uniquely—or a current external rank must select one exact duplicate official row.</span></li>
<li><strong>Publish only ambiguity-robust VRS</strong><span>If duplicate rows remain, every candidate combination must pick the same winner. The closest-to-50% edge is shown.</span></li>
<li><strong>Label one-sided floor sensitivity</strong><span>The unrated side is set to the lowest official VRS points. This is directional and never labelled as a market.</span></li>
<li><strong>Leave unsupported rows blank</strong><span>No direct evidence means no invented probability. The row moves to Unresolved picks & limitations.</span></li></ol></section>
<section class="section"><div class="section-head"><div><p class="kicker">Exact transform</p><h2>Valve points → probability</h2></div></div><div class="info-card"><p><span class="code">P(A) = sigmoid(k × C × (VRS_A − VRS_B))</span></p><p>Here <span class="code">C = g(75) × ln(10) / 400</span> and <span class="code">k = {e(cal.get('k'))}</span>. The scale was fitted on {e(cal.get('n_pairs'))} contemporaneous exact-pair market observations; mean absolute probability error was {e(round(100*cal.get('mae_prob',0),2))} points. It is calibration—not team-performance data.</p><p><a href="{e(board['method']['vrs_source'])}">Official Valve {e(board['method']['vrs_snapshot'])} global standings ↗</a></p></div></section>
<section class="section"><div class="summary-grid"><article class="info-card"><h3>Fixture universe</h3><p>Lobby-listed OPEN rows inside HotSpawn's current CS2 week. API-only started/cancelled conflicts are excluded and logged.</p></article>
<article class="info-card"><h3>Market conversion</h3><p>Raw two-way odds are independently converted and overround removed. Pinnacle weight is 2; Bovada, Melbet and Thunderpick weight 1.</p></article>
<article class="info-card"><h3>Identity</h3><p>Unicode/punctuation normalization may establish exact names. Semantic aliases are prohibited except an explicit, multi-book exact-fixture rule.</p></article>
<article class="info-card"><h3>Freshness</h3><p>The fixture observation must be no older than 4 hours. The dashboard refresh workflow targets every 4 hours and keeps the page's as-of time visible.</p></article></div></section>
<section class="section"><div class="notice danger"><strong>Forbidden input: HotSpawn crowd ownership.</strong><p>Ownership percentages are popularity, not estimated match win probability. The capture fails if known crowd-field names enter its retained input.</p></div></section>
<section class="section"><h2>Lock and display policy</h2><p>Rows are published in lock order. Client-side display marks a card locked when the browser passes <span class="code">lock_utc</span>; the scheduled rebuild replaces settled rows. A lock label does not imply live-game pricing.</p></section>'''
    return shell("Method", "The exact market-first, Valve-VRS fallback methodology used for current CS2 picks.", "method", body)


def flagged_page(board: dict) -> str:
    cards = []
    for flag in board["flags"]:
        affected = [row for row in board["rows"] if flag["id"] in row.get("flag_ids", [])]
        match_links = "".join(f'<a class="source-chip" href="picks.html#match-{e(row["fixture_id"])}">{e(row["team_a"])}–{e(row["team_b"])}</a>' for row in affected)
        if not affected:
            match_links = '<span class="tag">Board-wide collection note</span>'
        cards.append(f'''<article class="flag-card"><p class="kicker">{e(flag['severity'])} · {e(flag['id'])}</p><h2>{e(flag['title'])}</h2><p>{e(flag['detail'])}</p><div class="sources" style="margin-top:12px">{match_links}<a class="source-chip" href="{e(flag['url'])}">Source ↗</a></div></article>''')
    conflicts = "".join(f'<tr><td><strong>{e(x["team_a"])}–{e(x["team_b"])}</strong></td><td>{e(x["status"])}</td><td>{e(x["fixture_id"])}</td><td><a href="https://play.hotspawn.com/lobby">HotSpawn lobby ↗</a></td></tr>' for x in board["status_conflicts_excluded"])
    body = page_intro("Review", "Flagged for Review", "Irregularities stay visible even when the documented rule produces a pick. A flag does not silently block publication or become evidence.")
    body += f'<div class="flag-grid">{"".join(cards)}</div>'
    if conflicts:
        body += f'''<section class="section"><div class="section-head"><div><p class="kicker">Excluded inventory conflicts</p><h2>Not published as open picks</h2><p>These API observations conflict with lobby-open inventory or current time and remain outside the board.</p></div></div><div class="ledger-wrap"><table><thead><tr><th>Fixture</th><th>API status</th><th>ID</th><th>Source</th></tr></thead><tbody>{conflicts}</tbody></table></div></section>'''
    body += '<section class="section"><div class="notice warning"><strong>Flags are disclosure, not a hidden adjustment.</strong><p>No manual points or confidence penalties are applied. The displayed basis remains reproducible from retained evidence.</p></div></section>'
    return shell("Flagged for Review", "Dated sources, identity joins, directional scenarios, and collection irregularities flagged for review.", "flagged", body)


def main() -> int:
    board = json.loads(BOARD_PATH.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)
    shutil.copyfile(STYLE_SOURCE, OUT / "style.css")
    shutil.copyfile(BOARD_PATH, OUT / "data" / "board.json")
    pages = {"index.html": overview(board), "picks.html": picks_page(board),
             "unresolved.html": unresolved_page(board), "sources.html": sources_page(board),
             "method.html": method_page(board), "flagged.html": flagged_page(board)}
    for filename, text in pages.items():
        (OUT / filename).write_text(text + "\n")
    print(f"built {len(pages)} pages and machine data in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
