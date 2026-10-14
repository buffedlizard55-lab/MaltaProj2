#!/usr/bin/env python3
"""
Static dashboard generator for the HotSpawn pick'em betting-line analysis.

Renders, at the repository root (GitHub Pages source: main branch, "/"):
    index.html              dashboard / landing page
    cs2.html                every CS2 pick'em fixture + external lines + derived probabilities
    lol.html               every LoL pick'em fixture (external line coverage: not yet collected)
    tournaments.html        tournament index with coverage per tournament
    tournament-<slug>.html  one page per tournament
    flagged.html            Flagged for Review — unverified rows, irregularities, source failures
    methodology.html        sources, rules, formulas, limitations
    research.html           preserved dated audits and alternate boards
    assets/style.css, assets/app.js

Hard rules implemented here:
  * every verified number carries its source link,
  * missing values render as an explicit blank with an "unverified" flag (never invented),
  * HotSpawn pick percentages are shown only as a labelled reference column and are never
    used to derive the analysis,
  * all source-derived text is HTML-escaped,
  * internal links are checked before the page set is written.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLANK = '<span class="blank">—</span>'


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def load(rel, default=None):
    path = os.path.join(ROOT, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def fmt_time(iso):
    if not iso:
        return None
    return str(iso).replace("T", " ").replace("Z", " UTC")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return s or "unknown"


def tier_label(tier):
    t = (tier or "").lower()
    return {"s": "S", "b": "B", "c": "C"}.get(t, "—")


def pct(value):
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else None


# ---------------------------------------------------------------- shared page chrome
# Keep the primary navigation focused. Preserved parallel-session work remains
# available from Research archive rather than crowding every mobile header.
NAV = [
    ("index.html", "Dashboard"),
    ("cs2.html", "CS2 picks"),
    ("probabilities.html", "Probabilities"),
    ("tournaments.html", "Tournaments"),
    ("flagged.html", "Flagged for review"),
    ("methodology.html", "Method &amp; sources"),
    ("research.html", "Research archive"),
]


def page(title, subtitle, body, generated_at, active=None, banner=None):
    nav_bits = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        nav_bits.append('<a href="%s"%s>%s</a>' % (href, cls, label))
    nav = "\n".join(nav_bits)
    banner_html = f'<div class="banner">{banner}</div>' if banner else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · HotSpawn Pick'ems betting-line analysis</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="topbar">
  <div class="wrap">
    <div class="brand"><span class="dot"></span>HotSpawn Pick'ems · betting-line analysis</div>
    <nav>{nav}</nav>
  </div>
</header>
<main class="wrap">
  <h1>{esc(title)}</h1>
  <p class="sub">{subtitle}</p>
  <div class="banner"><strong>Current picks vs. research snapshots.</strong> The CS2 and Probabilities tables use
  eligible primary-bookmaker quotes only; unverified values stay blank. Other linked sections preserve dated research,
  not live prices. Estimates are not guarantees. 18+; gamble responsibly.</div>
  {banner_html}
  {body}
</main>
<footer class="wrap">
  <p>Page generated <strong>{esc(generated_at)}</strong>. Fixture list and every quoted price are read from the
  public sources linked on each row; HotSpawn is used for fixture discovery only and is never used as a
  probability source. Values that could not be confirmed against an external source are left blank and
  listed on the <a href="flagged.html">Flagged for review</a> page.</p>
</footer>
<script src="assets/app.js"></script>
</body>
</html>
"""


def table(headers, rows, table_id=None, classes=""):
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f'<td data-label="{esc(headers[i]) if i < len(headers) else ""}">{c}</td>' for i, c in enumerate(row))
        trs.append(f"<tr>{tds}</tr>")
    tid = f' id="{table_id}"' if table_id else ""
    return (f'<div class="tablewrap"><table{tid} class="{classes}">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')


def source_cell(line):
    name = esc(line.get("source_name") or line.get("source_key"))
    url = line.get("source_public_url") or line.get("source_api_url")
    api = line.get("source_api_url")
    bits = [f'<a href="{esc(url)}" rel="noopener">{name}</a>' if url else name]
    if api and api != url:
        bits.append(f'<a class="mini" href="{esc(api)}" rel="noopener">quote API</a>')
    if line.get("retrieved_at_utc"):
        bits.append(f'<span class="mini">read {esc(line["retrieved_at_utc"])}</span>')
    return "<br>".join(bits)


def flag_chips(flags):
    if not flags:
        return ""
    return " ".join(f'<span class="chip">{esc(f.replace("_", " "))}</span>' for f in flags)


# ------------------------------------------------------------------------- rows/tables
def fixture_row(fx, with_prices=True):
    lines = fx.get("bookmaker_lines") or []
    consensus = (fx.get("derived") or {}).get("consensus")
    if with_prices:
        odds_cells = []
        for line in sorted(lines, key=lambda l: l["source_key"]):
            odds_cells.append(
                f'<div class="srcblock"><div class="srcname">{source_cell(line)}</div>'
                f'<div class="odds">{line["decimal_odds_a"]} / {line["decimal_odds_b"]}</div>'
                f'<div class="mini">derived p: {pct(line["derived_probability_a"])} / '
                f'{pct(line["derived_probability_b"])} · overround {line["overround"]}</div>'
                f'<div class="mini">Read {esc(fmt_time(line.get("retrieved_at_utc")))}</div></div>')
        odds_html = "".join(odds_cells) if odds_cells else f'{BLANK} <span class="chip">no external line found</span>'
        if consensus:
            prob_html = (f'<strong>{pct(consensus["derived_probability_a_mean"])}</strong> / '
                         f'{pct(consensus["derived_probability_b_mean"])}'
                         f'<div class="mini">{consensus["n_sources"]} source(s): '
                         f'{esc(", ".join(consensus["sources"]))}</div>')
            prob_html += (f'<div class="mini">Source p(A) range: '
                          f'{pct(consensus["derived_probability_a_min"])}–{pct(consensus["derived_probability_a_max"])}</div>')
            a, b = consensus["derived_probability_a_mean"], consensus["derived_probability_b_mean"]
            pick = fx.get("team_a") if a > b else fx.get("team_b") if b > a else None
            prob_html += f'<div class="ok">Pick: {esc(pick)}</div>' if pick else '<div class="chip">No edge (tie)</div>' 
        else:
            prob_html = BLANK
    else:
        odds_html = prob_html = BLANK
    status = ('<span class="ok">eligible source-linked line</span>' if lines
              else '<span class="warn">unverified — no eligible external line</span>')
    pick_state = ('<span class="ok">open for picks</span>' if fx.get("pick_status") == "open"
                  else '<span class="mini">closed, past, or source state unverified</span>')
    source_label = ("published match page" if fx.get("hotspawn_source_kind") == "published_match_permalink"
                    else "official lobby fallback")
    return [
        esc(fmt_time(fx.get("start_time_utc")) or "not published"),
        tier_label(fx.get("tier")),
        esc(fx.get("competition") or ""),
        (f'<strong>{esc(fx.get("team_a"))}</strong> vs <strong>{esc(fx.get("team_b"))}</strong>'
         f'<div class="mini">Fixture #{esc(fx.get("fixture_id"))} · {pick_state}</div>'),
        odds_html,
        prob_html,
        status,
        (f'<a href="{esc(fx.get("hotspawn_match_url"))}" rel="noopener">{source_label}</a>'),
        flag_chips(fx.get("review_flags")),
    ]


def fixtures_table(fixtures, with_prices=True, table_id="fixtures"):
    headers = ["Scheduled (UTC)", "Tier", "Tournament", "Match", "External decimal odds (A / B)",
               "Derived no-vig probability (A / B)", "Verification", "HotSpawn", "Review flags"]
    rows = [fixture_row(fx, with_prices) for fx in fixtures]
    return table(headers, rows, table_id=table_id, classes="sortable"), len(rows)


# --------------------------------------------------------------------------- sections
def coverage_cards(summary, odds_doc, lines_doc):
    sources = sorted({l["source_key"] for l in (odds_doc.get("lines") or [])})
    cards = [
        ("CS2 matches open for picks", summary.get("fixtures_open_for_picks", 0)),
        ("Open matches with an eligible line", summary.get("fixtures_open_with_external_line", 0)),
        ("Open matches blank / flagged", summary.get("fixtures_open_without_external_line", 0)),
        ("Listed but locked or past", summary.get("fixtures_locked_or_past", 0)),
    ]
    html_cards = "".join(
        f'<div class="card"><div class="card-num">{esc(v)}</div><div class="card-label">{esc(k)}</div></div>'
        for k, v in cards)
    tier_rows = []
    for tier, data in sorted((summary.get("by_tier") or {}).items(), key=lambda kv: {"s": 0, "b": 1, "c": 2}.get(kv[0], 3)):
        tier_rows.append([tier_label(tier), data.get("total", 0), data.get("open", 0),
                          data.get("open_with_line", 0), data.get("open", 0) - data.get("open_with_line", 0),
                          '<a href="https://play.hotspawn.com/lobby">official lobby inventory</a>'])
    return (html_cards,
            table(["Tier", "Listed", "Open", "Open with line", "Open blank", "Source (counts derived)"], tier_rows),
            [{"key": k, "lines": v} for k, v in sorted((summary.get("by_source") or {}).items())])


def source_health_table(odds_evidence, probe_evidence):
    rows = []
    for row in (odds_evidence.get("candidate_sources") or []):
        status = row.get("status")
        ok = "reachable" if status == 200 else f"HTTP {status}" if status else "connection failed"
        rows.append([esc(row.get("key")), f'<a href="{esc(row.get("url"))}" rel="noopener">{esc(row.get("url"))}</a>', 
                     f'<span class="{"ok" if status == 200 else "warn"}">{esc(ok)}</span>',
                     esc((row.get("preview") or "")[:120])])
    for row in (probe_evidence.get("probes") or []):
        status = row.get("http_status")
        ok = "reachable" if status == 200 else f"HTTP {status}" if status else "connection failed"
        cf = " · Cloudflare challenge" if row.get("cloudflare_mitigated") else ""
        rows.append([esc(row.get("key")), f'<a href="{esc(row.get("url"))}" rel="noopener">{esc(row.get("url"))}</a>', 
                     f'<span class="{"ok" if status == 200 else "warn"}">{esc(ok + cf)}</span>',
                     esc((row.get("body_preview") or "")[:120])])
    seen, out = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        out.append(r)
    return table(["Source", "Probed URL", "Result", "Response preview"], out)


def main() -> int:
    matches_doc = load("data/hotspawn_matches.json")
    odds_doc = load("data/odds.json")
    # Every render (including Pages staging) recalculates eligibility at render time.
    # Cached JSON must not silently keep a closed/aged market current.
    from build_lines import build_document, fixture_source_url
    lines_doc, current_matching = build_document(matches_doc, odds_doc)
    write("data/lines.json", json.dumps(lines_doc, indent=1, ensure_ascii=False, allow_nan=False))
    write("evidence/matching_evidence.json", json.dumps(current_matching, indent=1, ensure_ascii=False, allow_nan=False))
    odds_evidence = load("evidence/odds_collection.json")
    probe_evidence = load("evidence/odds_probe.json")
    html_probe = load("evidence/html_source_probe.json")
    matching = load("evidence/matching_evidence.json")
    audit_1916 = load("audits/1916f96c/observations.json")

    fixtures = lines_doc.get("fixtures") or []
    summary = lines_doc.get("summary") or {}
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_time = lines_doc.get("odds_collected_at_utc") or odds_doc.get("generated_at_utc")

    cards, tier_table, by_source = coverage_cards(summary, odds_doc, lines_doc)

    # ------------------------------------------------------------------ index.html
    open_fixtures = [f for f in fixtures if f.get("pick_status") == "open"]
    closed_fixtures = [f for f in fixtures if f.get("pick_status") != "open"]
    top_table, _ = fixtures_table(open_fixtures)
    idx_body = f"""
<div class="cards">{cards}</div>
<h2>What this is</h2>
<p>This dashboard reads the exact CS2 fixture response embedded in the public HotSpawn Pick'ems lobby,
then looks up <strong>external betting lines</strong> for every listed match at Pinnacle and Bovada.
Prediction-market snapshots are excluded from current picks. For each match where an eligible external price
was found, the table shows the quoted odds, bookmaker margin and derived no-vig probability with the exact
source link and read time. Matches where no eligible external line could be confirmed stay
<strong>blank and flagged</strong> — they are never filled from HotSpawn or guessed.</p>
<p class="note"><strong>Want a pick for every open match?</strong> The separate <a href="ourline/index.html">Our line</a>
board (session f7279a54) gives a probability and a pick for every open CS2 fixture, including ones with no
eligible bookmaker price. It blends Pinnacle, Bovada, Melbet and Kalshi prices with a Valve VRS rating model,
labels which basis each pick uses, and grades its past picks on a track-record page. It is a model estimate, so
it is kept apart from the strictly source-priced tables here.</p>

<h2>Derived probabilities — the short version</h2>
<p>Raw quoted decimal odds are converted to implied shares <code>q = 1 / odds</code>, normalised to remove
the bookmaker margin: <code>p = q / (q<sub>a</sub> + q<sub>b</sub>)</code>. Where two sources quote the same
match, the dashboard shows their mean and the min–max range. These probabilities are <em>derived from
market prices</em>, not forecasts, and the rule is published on every row.</p>
<p class="note">HotSpawn's own "picked %" is a crowd pick percentage. It is excluded from this table and is
<strong>never</strong> used as a probability input, per the project requirements.</p>

<h2>Every CS2 match currently open for picks ({len(open_fixtures)})</h2>
<p class="note">A probability appears only when a fresh, open, prematch, full-series bookmaker quote joins
uniquely by both teams and exact UTC start. Blank means unverified, not 50/50.</p>
{top_table}
<p><a class="btn" href="cs2.html">Open all {len(fixtures)} lobby-listed CS2 rows</a>
<a class="btn ghost" href="flagged.html">Review {summary.get("fixtures_open_without_external_line", 0)} open gaps</a></p>

<h2>Audit trail and prior research</h2>
<p>The primary navigation stays focused on the current fail-closed board. Dated experiments, independent
audits and alternate models remain preserved on the <a href="research.html">Research archive</a>; they do
not enter current picks. Start with the
<a href="verify/8e7a652d/index.html">independent market verification and cross-check</a>, inspect the
<a href="evidence/odds_collection.json">raw bookmaker payload evidence</a>, or review the preserved
<a href="data/fixtures_verified.json">fixture-verification snapshot</a>.</p>

<h2>Timestamps</h2>
{market_data_notes(lines_doc, odds_doc)}
"""
    write("index.html", page("Pick'em betting-line dashboard",
                             "External betting lines, derived no-vig probabilities and explicit unverified gaps "
                             "for every CS2 fixture in the HotSpawn Pick'ems lobby.",
                             idx_body, generated_at, active="index.html"))

    # -------------------------------------------------------------------- cs2.html
    open_table, n_open = fixtures_table(open_fixtures, table_id="open-fixtures")
    closed_table, n_closed = fixtures_table(closed_fixtures, table_id="closed-fixtures")
    cs2_body = f"""
<div class="cards">
  <div class="card"><div class="card-num">{n_open}</div><div class="card-label">open for picks</div></div>
  <div class="card"><div class="card-num">{summary.get("fixtures_open_with_external_line", 0)}</div><div class="card-label">open with eligible line</div></div>
  <div class="card"><div class="card-num">{summary.get("fixtures_open_without_external_line", 0)}</div><div class="card-label">open, blank / flagged</div></div>
  <div class="card"><div class="card-num">{n_closed}</div><div class="card-label">listed but closed / past</div></div>
</div>
<p class="note">"External decimal odds" is the raw quoted pair. "Derived no-vig" is
<code>(1/odds<sub>i</sub>) / Σ(1/odds<sub>j</sub>)</code>. Every row links an official HotSpawn source;
every numeric line links the exact bookmaker source. Blank means no eligible quote was confirmed.</p>
<input id="filter" class="filter" type="search" placeholder="Filter all CS2 rows by team, tournament, tier or flag…">
<h2>Open for picks ({n_open})</h2>
{open_table}
<details class="archive"><summary>Listed by the lobby but closed, past, or state unverified ({n_closed})</summary>
<p class="note">These rows remain visible for complete lobby coverage. They cannot receive a current prematch pick.</p>
{closed_table}
</details>
{market_data_notes(lines_doc, odds_doc)}
"""
    write("cs2.html", page("CS2 picks", "Every CS2 row in the observed lobby response, with playable rows first and archived anomalies separated.",
                           cs2_body, generated_at, active="cs2.html"))

    # -------------------------------------------------------------------- lol.html
    lol_fixtures = [m for m in (matches_doc.get("matches") or [])
                    if m.get("sport") == "lol" and m.get("status") != "cancelled"]
    lol_rows = []
    for m in sorted(lol_fixtures, key=lambda x: x.get("scheduled_start_time") or ""):
        lol_rows.append([
            esc(fmt_time(m.get("scheduled_start_time")) or "not published"),
            tier_label(m.get("tier")),
            esc(m.get("competition_name") or ""),
            f'<strong>{esc(m.get("team_a"))}</strong> vs <strong>{esc(m.get("team_b"))}</strong>',
            BLANK, BLANK,
            '<span class="warn">unverified — external line collection covers CS2 only</span>',
            f'<a href="{esc(fixture_source_url(m))}" rel="noopener">fixture source</a>',
            '<span class="chip">lol odds not collected</span>',
        ])
    lol_body = f"""
<div class="banner warn">The Pick'ems lobby also offers League of Legends fixtures. External line collection in
this build covers <strong>CS2 only</strong>, so every LoL row below is intentionally blank and flagged
unverified rather than estimated. {len(lol_fixtures)} LoL fixtures are listed for completeness.</div>
{fixtures_note()}
<input id="filter" class="filter" type="search" placeholder="Filter LoL fixtures…">
{table(["Scheduled (UTC)", "Tier", "Tournament", "Match", "External odds", "Derived probability", "Verification", "HotSpawn", "Review flags"], lol_rows, table_id="fixtures", classes="sortable")}
"""
    write("lol.html", page("LoL pick'em fixtures", "League of Legends fixtures in the Pick'ems lobby (no external odds collected yet).",
                           lol_body, generated_at, active="lol.html"))

    # --------------------------------------------------------------- tournaments
    by_tournament = {}
    for fx in fixtures:
        by_tournament.setdefault(fx.get("competition") or "Unknown", []).append(fx)
    with_lines = {}
    for fx in fixtures:
        if fx.get("bookmaker_lines"):
            with_lines.setdefault(fx.get("competition") or "Unknown", []).append(fx)

    t_rows = []
    for name, group in sorted(by_tournament.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        slug = slugify(name)
        has = len(with_lines.get(name, []))
        t_rows.append([f'<a href="tournament-{slug}.html">{esc(name)}</a>', len(group), has,
                       len(group) - has,
                       " · ".join(sorted({tier_label(f.get("tier")) for f in group})),
                       '<a href="https://play.hotspawn.com/lobby">official fixture inventory</a>'])
    tour_body = f"""
<p>Fixtures are grouped by the tournament name reported by the lobby API. Each tournament page lists its
fixtures with the same verification columns as the main table.</p>
{table(["Tournament", "Fixtures", "With external line", "Unverified", "Tiers", "Source (counts derived)"], t_rows)}
"""
    write("tournaments.html", page("Tournaments", "Pick'em coverage per tournament.", tour_body,
                                   generated_at, active="tournaments.html"))

    for name, group in by_tournament.items():
        slug = slugify(name)
        has = len(with_lines.get(name, []))
        t_table, _ = fixtures_table(sorted(group, key=lambda f: f.get("start_time_utc") or ""))
        body = f"""
<p><a class="mini" href="tournaments.html">← all tournaments</a></p>
<div class="cards">
  <div class="card"><div class="card-num">{len(group)}</div><div class="card-label">fixtures</div></div>
  <div class="card"><div class="card-num">{has}</div><div class="card-label">with eligible source-linked line</div></div>
  <div class="card"><div class="card-num">{len(group) - has}</div><div class="card-label">unverified (blank)</div></div>
</div>
{t_table}
"""
        write(f"tournament-{slug}.html", page(name, "Tournament page — externally verified lines and explicit gaps.",
                                              body, generated_at, active="tournaments.html"))

    # ------------------------------------------------------------------ flagged
    unverified = [f for f in fixtures if not f.get("bookmaker_lines")]
    open_unverified = [f for f in unverified if f.get("pick_status") == "open"]
    unv_rows = [[esc(fmt_time(f.get("start_time_utc")) or "not published"), tier_label(f.get("tier")),
                 esc(f.get("competition") or ""),
                 f'{esc(f.get("team_a"))} vs {esc(f.get("team_b"))}',
                 '<span class="warn">no eligible external line confirmed</span>',
                 ", ".join(esc(x) for x in (f.get("review_flags") or [])) or
                 '<span class="chip">external_odds_not_found</span>',
                 f'<a href="{esc(f.get("hotspawn_match_url"))}" rel="noopener">official fixture source</a>']
                for f in open_unverified]
    stale = [f for f in fixtures if f.get("pick_status") != "open"]
    stale_rows = [[esc(fmt_time(f.get("start_time_utc"))), esc(f.get("competition")),
                   f'{esc(f.get("team_a"))} vs {esc(f.get("team_b"))}', esc(f.get("source_reported_status")),
                   flag_chips(f.get("review_flags")),
                   f'<a href="{esc(f.get("hotspawn_match_url"))}" rel="noopener">official fixture source</a>']
                  for f in stale]
    rejects_rows = [[esc(r.get("fixture_id")), esc(r.get("source")), esc(r.get("reason")),
                     esc(r.get("fixture") or r.get("event") or ""),
                     f'<a href="{esc(r.get("source_url") or "https://play.hotspawn.com/lobby")}" rel="noopener">source</a>']
                    for r in (matching.get("rejected_candidates") or [])]
    unmatched_rows = [[esc(r.get("source")), esc(r.get("event")), esc(fmt_time(r.get("start_time_utc")) or "not published"),
                       esc(r.get("league")), esc(r.get("reason")),
                       f'<a href="{esc(r.get("source_url") or "https://play.hotspawn.com/lobby")}" rel="noopener">source</a>']
                      for r in (matching.get("unmatched_bookmaker_lines") or [])]
    alias_rows = [[esc(k), BLANK + ' <span class="warn">not independently verified</span>',
                   '<a href="https://play.hotspawn.com/lobby">official inventory reference</a>'] for k, v in ALIAS_NOTE.items()]

    flagged_body = f"""
<div class="banner warn"><strong>These items are published for review, not as verified facts.</strong>
Nothing on this page blocks the analysis; it exists so every gap, irregularity and failed access attempt is
visible instead of being silently filled in.</div>

<h2>0. Current pipeline safety and archived-source limitations</h2>
<p>Current picks require fresh primary-bookmaker quotes, exact kickoff identity, explicit game/market state,
confirmed outcome ordering, an unlocked upcoming fixture and unique joins. A rejected quote is not a confirmed line.
The <a href="current/index.html">parallel current/ board</a> has an unnamed third-party fallback and a
separate source/identity policy; it is a dated research snapshot, not this pipeline's current confirmed picks.
Its reversal handling needs owner review (derived probabilities in lines.json are already fixture-oriented).
The prior third-party combined probabilities, hypothetical VRS lines, pickem board and independent reports are
preserved research snapshots, not current picks. They have not all been re-verified in this session.
Sources for manual review: <a href="https://play.hotspawn.com/lobby">official lobby</a>,
<a href="https://www.hltv.org/betting/analytics">HLTV analytics</a>,
<a href="https://www.pinnacle.com/">Pinnacle</a>, <a href="https://www.bovada.lv/">Bovada</a>,
<a href="audits/d4ec32a9/REPORT.md">pipeline audit and limitations</a>.</p>
<p>Numeric legacy HotSpawn links such as <code>/matches/1079438</code> were tested and redirect to a generic
match listing, not a verified match permalink. Current rows use a match permalink only when that exact URL was
published in the lobby state; otherwise they use the official lobby and carry an
<code>official_match_permalink_unavailable</code> flag. No slug is synthesized.</p>
Coverage is incomplete wherever no eligible official quote exists. No claim is made that every match is priced,
that a retrieval is real-time, or that a derived probability is a verified fact. Sandbox egress does not allow
these bookmaker hosts; automatic retrieval runs in GitHub Actions. Per-attempt payloads and failures:
<a href="evidence/odds_collection.json">collection evidence</a>.</p>
<h2>1. Open CS2 picks with no eligible external line ({len(open_unverified)})</h2>
<p>These currently open rows are deliberately blank: no eligible official-source quote could be confirmed
under the published policy. Missing, rejected, unavailable or uncollected data are not proof that no betting
market exists. No probability was inferred from HotSpawn or an unconfirmed source.</p>
{table(["Scheduled (UTC)", "Tier", "Tournament", "Match", "Status", "Flags", "HotSpawn link"], unv_rows, classes="sortable")}

<h2>2. Lobby-listed rows that are closed, past, or source-state unverified ({len(stale)})</h2>
<p>The lobby response includes these rows even though their lock or scheduled start has passed, their source
status is not eligible, or a required timestamp is missing. The raw source status is preserved; no correction
is inferred and no current probability is published.</p>
{table(["Scheduled (UTC)", "Tournament", "Match", "Source-reported status", "Flags", "Source"], stale_rows, classes="sortable")}

<h2>3. Bookmaker lines that were deliberately not used ({len(unmatched_rows)})</h2>
<p>Quotes for CS2 matches that are <em>not</em> in the current pick'em fixture list (for example the
European Pro League or a CCT South America match outside the lobby list). They are recorded here so the
matching step can be audited.</p>
{table(["Source", "Event", "Start (UTC)", "League", "Reason", "Evidence"], unmatched_rows)}

<h2>4. Rejected candidate matches ({len(rejects_rows)})</h2>
{table(["Fixture", "Source", "Rejection reason", "Detail", "Evidence"], rejects_rows)}

<h2>5. Source reachability (probed from CI)</h2>
<p>Sources that could not be read are listed with their HTTP result. A connection failure is not evidence
that a site is down, only that this pipeline could not read it.</p>
{source_health_table(odds_evidence, probe_evidence)}

<h2>6. Coverage changes between lobby observations</h2>
<p>An independent earlier audit of the server-rendered lobby (session <code>1d4de836</code>, preserved under
<code>audits/1d4de836/</code>) captured <strong>86</strong> CS2 fixture rows. The current collector reads the exact
<code>/api/v1/fixtures</code> response embedded in each new public lobby render and this observation contains
<strong>{summary.get("fixtures_total", 0)}</strong> non-cancelled, non-ended CS2 rows. These are different
retrieval times. The site does not invent a reason for the change; both observations remain linked.</p>

<h2>7. Team-name aliases used for matching</h2>
<p>Historical spellings below are not independently verified identity evidence. Current matching requires
both normalized participants and an exact UTC kickoff; no tournament-name fallback is used.
Rejection reasons are published in <code>evidence/matching_evidence.json</code>.</p>
{table(["Historical spelling rule", "Verification", "Source for review"], alias_rows)}

<h2>8. Price-format derivations</h2>
<p>Pinnacle's public API publishes match-winner prices in American format; the decimal column for Pinnacle
rows is derived with the standard conversion and marked <code>decimal_price_derived_from_american_pinnacle</code>
in the row flags. Polymarket publishes implied shares, converted with <code>1 / share</code>. Bovada publishes
decimal prices directly. No other conversion is performed anywhere.</p>

<h2>9. Parallel sessions' audit observations and data (attributed, not re-verified here)</h2>
<p>Other sessions worked on this repository at the same time. Their published evidence is preserved and
linked below; it was <strong>not</strong> re-verified by this pipeline and is not mixed into the numbers
above. The independent price observations are reproduced verbatim from
<code>audits/1916f96c/observations.json</code>.</p>
{table(["Teams", "Bookmaker / market", "Quoted prices (American)", "Their derived probability", "Source (official)", "Observed", "Flags"],
       audit_price_rows(audit_1916))}
<ul>
<li><a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/audits/1d4de836/README.md" rel="noopener">Independent verification audit — session 1d4de836</a> (86-row lobby snapshot, access evidence, handoff requirements).</li>
<li><a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/audits/1916f96c/REPORT.md" rel="noopener">Independent official-source audit — session 1916f96c</a> (lobby observations, Thunderpick market reads, GG.BET/Rivalry access results).</li>
<li><a href="pickem/index.html">Parallel dashboard built by session a0fcf175</a> (preserved unmodified under <code>pickem/</code>).</li>
<li><a href="docs/index.html">Parallel dashboard built by session ef111e02</a> (preserved unmodified under <code>docs/</code>; it also publishes BC.Game/Polymarket references and VRS-originated reference lines in <code>data/originated_matches.json</code>).</li>
<li>Session 1916f96c also recorded that <strong>Rivalry has ceased operations</strong> and <strong>GG.BET rejected the request by region</strong>; both are therefore not usable sources here.</li>
</ul>

<h2>10. Known limitations</h2>
<ul>
<li>Only full-match / series-winner moneyline markets are used. Map markets, handicaps and totals are excluded.</li>
<li>An exact source-published UTC start is mandatory. A missing or different start is rejected, never matched by tournament name.</li>
<li>Derived probabilities use proportional no-vig normalisation — a disclosed modeling choice, not an official forecast.</li>
<li>Bookmaker prices can move after the row's read timestamp; in-play markets are never eligible.</li>
</ul>

<h2>11. Inventory reconciliation addendum (session 188aaa4f, 2026-10-13)</h2>
<ul>
<li>The lobby front end served contradictory replica states within one minute (CS2 filter totals 85 vs 91;
"this week" 60 vs 68). Both snapshots are recorded in <a href="data/cs2_matches.json">data/cs2_matches.json</a>;
the 30 rendered cards were identical across states for shared rows.</li>
<li>59 CS2 fixtures are counted by the lobby tournament filters but never rendered as cards — their locks are
in June/July 2026 and the corresponding www.tournament pages show the events finished. Row identities and
UTC times come from the official play API; every row links its source in
<a href="data/cs2_unrendered_flags.json">data/cs2_unrendered_flags.json</a>. They are counted, unplayable
and flagged; nothing was dropped or filled.</li>
<li>LoL external coverage: only 8 of 241 future LoL fixtures have an external quote (egamersworld marquee
list). The remaining 233 keep blank probabilities on <a href="probabilities.html">Probabilities</a>,
flagged <code>no_external_line</code> — never estimated.</li>
<li>egamersworld list-view times conflict with official play API starts on several LoL rows; the conflict is
recorded per row (<code>egw_time_conflicts_with_official_start</code>) and official times are used.</li>
<li>DACH CS Masters Season 5 (lobby count 1) has no tournament page or fixtures under that name on
www.hotspawn.com (search returns seasons 1–4 only): identity unresolved, flagged.</li>
</ul>
"""
    write("flagged.html", page("Flagged for review", "Unverified rows, irregularities and source failures.",
                               flagged_body, generated_at, active="flagged.html"))

    # --------------------------------------------------------- probabilities (session 188aaa4f)
    # Complete inventory, but only the fresh primary-bookmaker pipeline can supply a pick.
    current_by_id = {f["fixture_id"]: f for f in fixtures}
    current_rows = []
    for m in matches_doc.get("matches") or []:
        if str(m.get("status", "")).lower() in {"cancelled", "ended"}:
            continue
        fx = current_by_id.get(m["fixture_id"], {})
        c = fx.get("derived", {}).get("consensus")
        current_rows.append({"fixture_id": m["fixture_id"], "game": m.get("sport"),
            "scheduled_start_time_utc": m.get("scheduled_start_time"), "tier": m.get("tier"),
            "competition": m.get("competition_name"), "team_a": m.get("team_a"), "team_b": m.get("team_b"),
            "pick_status": fx.get("pick_status") or "closed_or_unverified",
            "probability_a": c["derived_probability_a_mean"] if c else None,
            "probability_b": c["derived_probability_b_mean"] if c else None,
            "sources": [{"source": q["source_name"], "url": q.get("source_public_url") or q.get("source_api_url"),
                        "retrieved_at_utc": q.get("retrieved_at_utc")} for q in fx.get("bookmaker_lines", [])],
            "official_source_url": fixture_source_url(m),
            "flags": fx.get("review_flags") or (["external_odds_not_collected_for_this_game"] if not fx else [])})
    probs_doc = {"generated_at_utc": lines_doc["generated_at_utc"], "rows": current_rows}
    write("data/current_probabilities.json", json.dumps(probs_doc, indent=1, ensure_ascii=False))
    open_prows, closed_prows = [], []
    p_with = p_blank_open = 0
    for r in probs_doc.get("rows") or []:
        src_bits = []
        for s in r.get("sources") or []:
            label = s.get("source") or "source"
            url = s.get("url")
            src_bits.append((f'<a href="{esc(url)}" rel="noopener">{esc(label)}</a>' if url else esc(label)) +
                            f'<div class="mini">Read {esc(fmt_time(s.get("retrieved_at_utc")))}</div>')
        if r.get("probability_a") is not None:
            p_with += 1
            prob_cell = f'<strong>{pct(r["probability_a"])}</strong> / {pct(r["probability_b"])}'
            pick = r["team_a"] if r["probability_a"] > r["probability_b"] else r["team_b"] if r["probability_b"] > r["probability_a"] else None
            prob_cell += f'<div class="ok">Pick: {esc(pick)}</div>' if pick else '<div class="chip">No edge (tie)</div>'
        elif r.get("pick_status") == "open":
            p_blank_open += 1
            prob_cell = '<span class="warn">blank — no eligible external line</span>'
        else:
            prob_cell = '<span class="mini">not current — picks closed, past, or state unverified</span>'
        rendered = [
            esc(fmt_time(r.get("scheduled_start_time_utc")) or "not published"),
            esc(r.get("game")), esc(tier_label(r.get("tier"))),
            esc(r.get("competition") or ""),
            f'{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}',
            prob_cell,
            " · ".join(src_bits) or BLANK,
            f'<a href="{esc(r.get("official_source_url"))}" rel="noopener">fixture #{esc(r.get("fixture_id"))}</a>',
            ", ".join(esc(x) for x in (r.get("flags") or [])) or '<span class="chip">ok</span>',
        ]
        (open_prows if r.get("pick_status") == "open" else closed_prows).append(rendered)
    prob_body = f"""
<div class="banner"><strong>External lines only.</strong> Probabilities are a proportional no-vig
normalisation of eligible primary-bookmaker quotes (Pinnacle and Bovada), averaged across independent
sources. Both teams, explicit CS2 game, exact UTC kickoff, an open prematch market, confirmed outcome ordering,
a unique join, an unpassed pick lock and a quote/fixture snapshot no older than four hours are required. Hotspawn crowd pick percentages are never used. Rows without an external line
stay blank and are flagged — nothing is inferred.</div>
<div class="cards">
  <div class="card"><div class="card-num">{len(open_prows)}</div><div class="card-label">CS2 matches open for picks</div></div>
  <div class="card"><div class="card-num">{p_with}</div><div class="card-label">open with external-line probability</div></div>
  <div class="card"><div class="card-num">{p_blank_open}</div><div class="card-label">open, blank / flagged</div></div>
  <div class="card"><div class="card-num">{len(closed_prows)}</div><div class="card-label">listed but not current</div></div>
</div>
<input id="filter" class="filter" type="search" placeholder="Filter all rows by team, tournament or flag…">
<h2>Current open picks</h2>
{table(["Scheduled (UTC)", "Game", "Tier", "Tournament", "Match", "p(A) / p(B) & pick", "External sources", "Official fixture", "Flags"], open_prows, classes="sortable")}
<details class="archive"><summary>Listed but closed, past, or source-state unverified ({len(closed_prows)})</summary>
{table(["Scheduled (UTC)", "Game", "Tier", "Tournament", "Match", "Current probability", "External sources", "Official fixture", "Flags"], closed_prows, classes="sortable")}
</details>
<p>Current data: <a href="data/current_probabilities.json">current probabilities</a> ·
<a href="data/hotspawn_matches.json">automatic fixture inventory</a> · <a href="data/odds.json">raw primary quotes</a> ·
<a href="evidence/odds_collection.json">quote payloads and source failures</a>.</p>
<p class="note">Preserved prior-session snapshots are not current verified inputs:
<a href="data/probabilities.json">third-party combined snapshot</a>,
<a href="data/cs2_odds_egamersworld.json">CS2 third-party odds</a>,
<a href="data/lol_odds_egamersworld.json">LoL third-party odds</a>.
Unpriced games stay blank. Archived model/pickem/audit sections retain their own dated evidence and do not supply these picks.</p>
{market_data_notes(lines_doc, odds_doc)}
"""
    write("probabilities.html", page("Probabilities",
                                     "Normalized external-line probabilities for every pick'em fixture; blanks are flagged, never filled.",
                                     prob_body, generated_at, active="probabilities.html"))

    # ----------------------------------------------------------- research archive
    research_body = """
<div class="banner warn"><strong>Dated research, not current picks.</strong> These preserved sections use
their own snapshots, source policies and model assumptions. They do not supply a number to the current CS2 or
Probabilities tables.</div>
<div class="archive-grid">
  <article class="card"><h2>Independent verification</h2><p><a href="verify/8e7a652d/index.html">Market verification &amp; cross-check</a><br>
  <a href="verify/0f71ea59/index.html">Line-by-line verification report</a><br>
  <a href="audits/d4ec32a9/REPORT.md">Current-pipeline audit</a></p></article>
  <article class="card"><h2>Preserved pick boards</h2><p><a href="pickem/index.html">Pick'em board</a><br>
  <a href="picks/index.html">Source-linked live-lines snapshot</a><br>
  <a href="verify961/index.html">Verified snapshot board</a><br>
  <a href="fresh/index.html">Fresh-board snapshot</a><br>
  <a href="reconcile/index.html">Reconciled snapshot</a></p></article>
  <article class="card"><h2>Alternate coverage studies</h2><p><a href="current/index.html">Parallel current snapshot</a><br>
  <a href="site/42580809/index.html">Coverage study 42580809</a><br>
  <a href="market/index.html">Expanded market study</a><br>
  <a href="live/index.html">VRS + market coverage study</a></p></article>
  <article class="card"><h2>Evidence-first directories</h2><p><a href="docs/index.html">LineWatch audit</a><br>
  <a href="lol.html">LoL inventory snapshot</a><br>
  <a href="hotspawn.html">HotSpawn research notes</a><br>
  <a href="lines.html">Archived lines</a> · <a href="teams.html">Archived teams</a></p></article>
</div>
<p>Official sources used for manual comparison:
<a href="https://play.hotspawn.com/lobby">HotSpawn lobby</a> ·
<a href="https://www.pinnacle.com/">Pinnacle</a> ·
<a href="https://www.bovada.lv/">Bovada</a> ·
<a href="https://www.hltv.org/betting/analytics">HLTV analytics</a>.</p>
"""
    write("research.html", page("Research archive", "Preserved audits and alternate snapshots, clearly separated from current picks.",
                                research_body, generated_at, active="research.html"))

    # -------------------------------------------------------------- methodology
    src_list = sorted({(l["source_key"], l.get("source_name"), l.get("source_kind"),
                        l.get("source_public_url"), l.get("source_api_url"))
                       for l in (odds_doc.get("lines") or [])})
    src_rows = [[esc(k), esc(n), esc("bookmaker (license not assessed)" if kind == "licensed bookmaker" else kind), f'<a href="{esc(p)}" rel="noopener">{esc(p)}</a>' if p else BLANK,
                 f'<a href="{esc(a)}" rel="noopener">API</a>' if a else BLANK]
                for k, n, kind, p, a in src_list]
    method_body = f"""
<h2>1. Fixture discovery (HotSpawn)</h2>
<p>The Pick'ems lobby is a server-rendered Angular app. Its public <code>script#ng-state</code> embeds the
response whose URL ends in <code>/api/v1/fixtures</code> and a map of HotSpawn-published match permalinks.
The collector requires exactly one embedded fixture response, copies every row, and fails closed on malformed
or ambiguous state. It never calls the admin-named permalink endpoint. Missing match permalinks fall back to
the official lobby and are flagged; no URL slug is synthesized. Crowd-picked percentage fields are deliberately
omitted from the normalized inventory. Response hash, cache age, counters, ids and fields are recorded in
<a href="evidence/hotspawn_probe.json"><code>evidence/hotspawn_probe.json</code></a>.</p>

<h2>2. External line sources</h2>
<p>Current probabilities use named bookmaker quotes from Pinnacle and Bovada only. Polymarket is collected as
separate reference evidence but is ineligible for the primary consensus. HotSpawn never contributes a probability.</p>
{table(["Key", "Source", "Type", "Public page", "Quoted from"], src_rows)}

<h2>3. What is collected per match</h2>
<ul>
<li>the source's own event and market identifiers,</li>
<li>the raw quoted prices in the source's own format (and the format name),</li>
<li>the retrieval timestamp in UTC,</li>
<li>the market type — series/match winner only, no map markets,</li>
<li>the source's reported start time and status,</li>
<li>the public URL the quote was read from.</li>
</ul>

<h2>4. Derivation</h2>
<p>Implied share <code>q<sub>i</sub> = 1 / decimal_odds<sub>i</sub></code>; bookmaker margin
<code>overround = q<sub>a</sub> + q<sub>b</sub> − 1</code>; proportional no-vig probability
<code>p<sub>i</sub> = q<sub>i</sub> / (q<sub>a</sub> + q<sub>b</sub>)</code>. With two or more sources the
dashboard shows their arithmetic mean and the min–max range, and names the sources. These numbers are
<strong>derived, not official forecasts</strong>.</p>

<h2>5. Matching rule</h2>
<p>Both participants must match after normalisation (order-insensitive; reversed pairs keep reversed prices),
and explicit UTC start times must agree exactly. Missing times are not guessed from league names.
Quotes and fixture snapshots must be no older than four hours, prematch/open, with confirmed outcome ordering,
and the fixture must be upcoming and unlocked. Ambiguous fixture joins or multiple quotes from one source
are rejected rather than assigned by input order. Every decision, alias and rejection is recorded in <code>evidence/matching_evidence.json</code>.</p>

<h2>6. Cross-session material</h2>
<p>This integration keeps every session's artefacts: <a href="data/originated_matches.json">VRS-originated
reference lines</a>, <a href="data/fixtures_verified.json">verified fixtures</a>,
<a href="data/teams_verified.json">verified teams</a>,
<a href="data/flagged_irregularities.json">flagged irregularities</a>,
<a href="data/teams_verified.json">team identity evidence</a>, the
<a href="docs/index.html">parallel dashboard</a> and the audit reports linked from the Flagged page.</p>

<h2>7. Refresh</h2>
<p>A scheduled GitHub Actions job re-runs the collectors, re-derives the lines and rebuilds these pages.
The job runs hourly and publishes its data and rendered root pages together. Collection failures are
recorded; missing or ineligible quotes leave the probability blank. Eligibility is recalculated on every
site render, including Pages staging, so old inputs cannot become current merely by rebuilding HTML.</p>
{market_data_notes(lines_doc, odds_doc)}
"""
    write("methodology.html", page("Methodology &amp; sources", "How the fixture list, the quoted odds and the derived probabilities are produced.",
                                   method_body, generated_at, active="methodology.html"))

    # --------------------------------------------------------------------- assets
    write("assets/style.css", STYLE)
    write("assets/app.js", JS)

    # ------------------------------------------------------------- link checking
    problems = check_links(list(WRITTEN))
    if problems:
        print("BROKEN INTERNAL LINKS:", problems)
        return 2
    print(f"site built: {len(WRITTEN)} files, no broken internal links")
    return 0


ALIAS_NOTE = {
    "BB Team": "BetBoom",
    "PVISION": "PARIVISION",
    "Parivision": "PARIVISION",
    "9Z Globant": "9z",
    "Team AURORA": "Aurora",
    "Sashi Esport": "Sashi",
    "FURIA Esports": "FURIA",
    "Team Falcons": "Falcons",
}


def audit_price_rows(audit):
    rows = []
    for obs in (audit.get("independent_official_price_observations") or []):
        teams = obs.get("teams") or []
        odds = obs.get("american_odds") or []
        analysis = obs.get("analysis") or {}
        probs = analysis.get("probability") or []
        rows.append([
            esc(" vs ".join(teams)),
            esc(f'{obs.get("bookmaker", "")} · {obs.get("market", "")}' + (f' · {obs.get("best_of")}' if obs.get("best_of") else "")),
            esc(" / ".join(str(o) for o in odds)) if odds else BLANK,
            (esc(" / ".join(f"{p*100:.1f}%" for p in probs)) + '<div class="mini">their ' + esc(analysis.get("kind", "")) + '</div>') if probs else BLANK,
            f'<a href="{esc(obs.get("source"))}" rel="noopener">market page</a>',
            esc(obs.get("observed_date") or ""),
            " ".join(f'<span class="chip">{esc(f)}</span>' for f in (obs.get("flags") or [])),
        ])
    if not rows:
        rows.append([BLANK] * 7)
    return rows


def fixtures_note():
    return ('<p class="note">An asterisk-free rule: if a cell is blank, the value could not be confirmed from '
            'an external source. Nothing is estimated.</p>')


def market_data_notes(lines_doc, odds_doc):
    cache_age = lines_doc.get("fixture_source_cache_age_seconds")
    cache_note = f' · Lobby cache age at retrieval: <strong>{esc(cache_age)}s</strong>' if cache_age is not None else ""
    return (f'<p class="note">Lobby retrieved: <strong>{esc(lines_doc.get("fixture_list_collected_at_utc"))}</strong> · '
            f'Lobby source observed: <strong>{esc(lines_doc.get("fixture_source_observed_at_utc"))}</strong>{cache_note} · '
            f'Odds collected: <strong>{esc(lines_doc.get("odds_collected_at_utc"))}</strong> · '
            f'Lines derived: <strong>{esc(lines_doc.get("generated_at_utc"))}</strong> · '
            f'Raw quote rows: <strong>{len(odds_doc.get("lines") or [])}</strong></p>')


STYLE = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2230;--line:#2b3444;--txt:#e6edf3;--mut:#9aa7b4;
--acc:#4da3ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{overflow-wrap:anywhere;max-width:1180px;margin:0 auto;padding:0 18px}
.topbar{background:linear-gradient(180deg,#111827,#0d1117);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.topbar .wrap{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:12px 18px}
.brand{font-weight:600;display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--acc);box-shadow:0 0 12px var(--acc)}
nav{display:flex;flex-wrap:wrap;gap:5px;max-width:100%}
nav a{color:var(--mut);text-decoration:none;padding:6px 9px;border-radius:8px;font-size:14px}
nav a:hover{color:var(--txt);background:var(--panel)}
nav a.active{color:var(--txt);background:var(--panel2)}
main{padding:26px 18px 40px}
h1{font-size:26px;margin:6px 0 4px}
h2{font-size:18px;margin:28px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.sub{color:var(--mut);margin:0 0 18px;max-width:900px}
.note{color:var(--mut);font-size:13.5px}
a{color:var(--acc)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
.card h2{margin:0 0 8px;padding:0;border:0}
.card-num{font-size:26px;font-weight:700}
.card-label{color:var(--mut);font-size:13px}
.archive-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:16px 0}
.archive{margin:20px 0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.archive>summary{cursor:pointer;padding:14px 16px;font-weight:700;color:var(--mut)}
.archive[open]>summary{border-bottom:1px solid var(--line);color:var(--txt)}
.archive>.note{padding:0 16px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:12px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}
th,td{padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{background:var(--panel2);position:sticky;top:0;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);cursor:pointer}
tr:hover td{background:#182030}
.srcblock{margin-bottom:8px}
.srcname{font-weight:600}
.srcblock .odds{font-feature-settings:"tnum";font-size:15px}
.mini{color:var(--mut);font-size:12px}
.blank{color:var(--mut)}
.chip{display:inline-block;background:#20293a;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:1px 8px;font-size:11.5px;margin:1px 2px}
.ok{color:var(--ok);font-weight:600}
.warn{color:var(--warn);font-weight:600}
.bad{color:var(--bad)}
.banner{background:#1d2433;border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:10px;padding:12px 14px;margin:14px 0}
.banner.warn{border-left-color:var(--warn)}
.filter{width:100%;max-width:420px;margin:10px 0;padding:9px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--txt)}
.btn{display:inline-block;background:var(--acc);color:#04101f;font-weight:700;text-decoration:none;padding:9px 14px;border-radius:10px;margin:6px 8px 6px 0}
.btn.ghost{background:transparent;color:var(--acc);border:1px solid var(--acc)}
code{background:#111827;border:1px solid var(--line);border-radius:6px;padding:1px 5px}
@media(max-width:640px){
.wrap{min-width:0;padding-left:12px;padding-right:12px}
.topbar{position:static}.topbar .wrap{display:block;padding:12px}.brand{margin-bottom:10px}
nav{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px;scrollbar-width:thin}
nav a{white-space:nowrap;background:var(--panel)}
h1{font-size:23px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:12px}.card-num{font-size:22px}
.tablewrap{overflow:visible;border:0;background:transparent}
table,table tbody,table tr{display:block;width:100%}
table thead{display:none}
table tbody tr{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:7px 0;overflow:hidden}
table td{display:block;padding:7px 11px;overflow-wrap:anywhere;border-bottom:0}
table td:before{display:block;content:attr(data-label);color:var(--mut);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;margin-bottom:2px}
}
footer{color:var(--mut);font-size:13px;border-top:1px solid var(--line);margin-top:40px;padding:18px}
"""

JS = """
// Table filter + click-to-sort. No external dependencies (GitHub Pages safe).
document.addEventListener('DOMContentLoaded', function () {
  var input = document.getElementById('filter');
  if (input) {
    input.addEventListener('input', function () {
      var q = input.value.toLowerCase();
      document.querySelectorAll('table tbody tr').forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
      });
    });
  }
  document.querySelectorAll('table.sortable thead th').forEach(function (th, i) {
    th.addEventListener('click', function () {
      var tb = th.closest('table').querySelector('tbody');
      var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
      var asc = th.dataset.asc !== '1';
      rows.sort(function (a, b) {
        var x = a.children[i] ? a.children[i].textContent.trim() : '';
        var y = b.children[i] ? b.children[i].textContent.trim() : '';
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      });
      th.dataset.asc = asc ? '1' : '0';
      rows.forEach(function (r) { tb.appendChild(r); });
    });
  });
});
"""


WRITTEN = []


def write(rel, content):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    if rel not in WRITTEN:
        WRITTEN.append(rel)


def check_links(files):
    """Verify every internal href target exists (audit requirement: no broken links)."""
    problems = []
    existing = set(files) | {"assets/style.css", "assets/app.js"}
    for rel in files:
        if not rel.endswith(".html"):
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            body = fh.read()
        for href in re.findall(r'href="([^"#]+)"', body):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            if href not in existing and not os.path.exists(os.path.join(ROOT, href)):
                problems.append(f"{rel} -> {href}")
    return problems


if __name__ == "__main__":
    sys.exit(main())
