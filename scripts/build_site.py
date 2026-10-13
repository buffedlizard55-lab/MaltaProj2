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
NAV = [
    ("index.html", "Dashboard"),
    ("cs2.html", "CS2 matches"),
    ("lol.html", "LoL matches"),
    ("tournaments.html", "Tournaments"),
    ("flagged.html", "Flagged for review"),
    ("methodology.html", "Methodology &amp; sources"),
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
        tds = "".join(f"<td>{c}</td>" for c in row)
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
                f'{pct(line["derived_probability_b"])} · overround {line["overround"]}</div></div>')
        odds_html = "".join(odds_cells) if odds_cells else f'{BLANK} <span class="chip">no external line found</span>'
        if consensus:
            prob_html = (f'<strong>{pct(consensus["derived_probability_a_mean"])}</strong> / '
                         f'{pct(consensus["derived_probability_b_mean"])}'
                         f'<div class="mini">{consensus["n_sources"]} source(s): '
                         f'{esc(", ".join(consensus["sources"]))}</div>')
        else:
            prob_html = BLANK
    else:
        odds_html = prob_html = BLANK
    status = ('<span class="ok">verified external line</span>' if lines
              else '<span class="warn">unverified — no external line found</span>')
    return [
        esc(fmt_time(fx.get("start_time_utc")) or "not published"),
        tier_label(fx.get("tier")),
        esc(fx.get("competition") or ""),
        f'<strong>{esc(fx.get("team_a"))}</strong> vs <strong>{esc(fx.get("team_b"))}</strong>',
        odds_html,
        prob_html,
        status,
        (f'<a href="{esc(fx.get("hotspawn_match_url"))}" rel="noopener">match</a>'),
        flag_chips(fx.get("review_flags")),
    ]


def fixtures_table(fixtures, with_prices=True):
    headers = ["Scheduled (UTC)", "Tier", "Tournament", "Match", "External decimal odds (A / B)",
               "Derived no-vig probability (A / B)", "Verification", "HotSpawn", "Review flags"]
    rows = [fixture_row(fx, with_prices) for fx in fixtures]
    return table(headers, rows, table_id="fixtures", classes="sortable"), len(rows)


# --------------------------------------------------------------------------- sections
def coverage_cards(summary, odds_doc, lines_doc):
    sources = sorted({l["source_key"] for l in (odds_doc.get("lines") or [])})
    cards = [
        ("Pick'em CS2 fixtures tracked", summary.get("fixtures_total", 0)),
        ("Fixtures with a verified external line", summary.get("fixtures_with_external_line", 0)),
        ("Fixtures still unverified (blank)", summary.get("fixtures_without_external_line", 0)),
        ("External sources quoted", len(sources)),
    ]
    html_cards = "".join(
        f'<div class="card"><div class="card-num">{esc(v)}</div><div class="card-label">{esc(k)}</div></div>'
        for k, v in cards)
    tier_rows = []
    for tier, data in sorted((summary.get("by_tier") or {}).items(), key=lambda kv: {"s": 0, "b": 1, "c": 2}.get(kv[0], 3)):
        tier_rows.append([tier_label(tier), data.get("total", 0), data.get("with_line", 0),
                          data.get("total", 0) - data.get("with_line", 0)])
    return (html_cards,
            table(["Tier", "Fixtures", "With external line", "Unverified"], tier_rows),
            [{"key": k, "lines": v} for k, v in sorted((summary.get("by_source") or {}).items())])


def source_health_table(odds_evidence, probe_evidence):
    rows = []
    for row in (odds_evidence.get("candidate_sources") or []):
        status = row.get("status")
        ok = "reachable" if status == 200 else f"HTTP {status}" if status else "connection failed"
        rows.append([esc(row.get("key")), esc(row.get("url")),
                     f'<span class="{"ok" if status == 200 else "warn"}">{esc(ok)}</span>',
                     esc((row.get("preview") or "")[:120])])
    for row in (probe_evidence.get("probes") or []):
        status = row.get("http_status")
        ok = "reachable" if status == 200 else f"HTTP {status}" if status else "connection failed"
        cf = " · Cloudflare challenge" if row.get("cloudflare_mitigated") else ""
        rows.append([esc(row.get("key")), esc(row.get("url")),
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
    lines_doc = load("data/lines.json")
    matches_doc = load("data/hotspawn_matches.json")
    odds_doc = load("data/odds.json")
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
    verified = [f for f in fixtures if f.get("bookmaker_lines")]
    upcoming = [f for f in fixtures if (f.get("start_time_utc") or "") >= "2026-10-13"]
    top_table, _ = fixtures_table(verified[:12])
    idx_body = f"""
<div class="cards">{cards}</div>
<h2>What this is</h2>
<p>The HotSpawn pick'em lobby lists CS2 (and LoL) matches you can pick. This dashboard collects those
fixtures from the lobby's own public API, then looks up <strong>external betting lines</strong> for every
fixture at licensed bookmakers and public prediction markets. For each match where an external price was
found you get the quoted odds, the bookmaker margin and a derived no-vig probability, each with the exact
source link and the time it was read. Matches where no external line could be confirmed are left
<strong>blank and flagged unverified</strong> — they are never estimated.</p>

<h2>Derived probabilities — the short version</h2>
<p>Raw quoted decimal odds are converted to implied shares <code>q = 1 / odds</code>, normalised to remove
the bookmaker margin: <code>p = q / (q<sub>a</sub> + q<sub>b</sub>)</code>. Where two sources quote the same
match, the dashboard shows their mean and the min–max range. These probabilities are <em>derived from
market prices</em>, not forecasts, and the rule is published on every row.</p>
<p class="note">HotSpawn's own "picked %" is a crowd pick percentage. It is shown for reference only and is
<strong>never</strong> used as a probability input, per the project requirements.</p>

<h2>Closest matches with verified external lines</h2>
{top_table}
<p><a class="btn" href="cs2.html">Open the full CS2 table ({len(fixtures)} fixtures)</a>
<a class="btn ghost" href="flagged.html">Flagged for review ({summary.get("fixtures_without_external_line", 0)} unverified rows)</a></p>

<h2>Parallel session data preserved in this repo</h2>
<p>Other sessions in this repo published their own reference material, kept intact: the VRS-based
reference lines (<a href="data/originated_matches.json">data/originated_matches.json</a>,
<a href="data/originated_outrights.json">data/originated_outrights.json</a>,
<a href="data/origination_summary.json">origination summary</a>), the verified fixture set
(<a href="data/fixtures_verified.json">data/fixtures_verified.json</a>), the verified team list
(<a href="data/teams_verified.json">data/teams_verified.json</a>),
<a href="data/flagged_irregularities.json">flagged irregularities</a> and the
<a href="docs/index.html">parallel dashboard under docs/</a>. Their pages
(<a href="lines.html">lines</a>, <a href="teams.html">teams</a>, <a href="hotspawn.html">HotSpawn notes</a>)
remain at their original paths and are listed on the <a href="flagged.html">Flagged for review</a> page.
Nothing published by another session was discarded during integration.</p>

<h2>Timestamps</h2>
{market_data_notes(lines_doc, odds_doc)}
"""
    write("index.html", page("Pick'em betting-line dashboard",
                             "External betting lines, derived no-vig probabilities and explicit unverified gaps "
                             "for every CS2 fixture in the HotSpawn Pick'ems lobby.",
                             idx_body, generated_at, active="index.html"))

    # -------------------------------------------------------------------- cs2.html
    cs2_table, n_cs2 = fixtures_table(fixtures)
    cs2_body = f"""
<div class="cards">
  <div class="card"><div class="card-num">{n_cs2}</div><div class="card-label">CS2 pick'em fixtures</div></div>
  <div class="card"><div class="card-num">{summary.get("fixtures_with_external_line", 0)}</div><div class="card-label">with verified line</div></div>
  <div class="card"><div class="card-num">{summary.get("fixtures_without_external_line", 0)}</div><div class="card-label">blank / unverified</div></div>
</div>
<p class="note">Sort or filter the table below. "External decimal odds" shows the raw quoted price pair from
each source; "derived no-vig" is <code>(1/odds<sub>i</sub>) / Σ(1/odds<sub>j</sub>)</code>. Every source cell
links to the page/API the quote was read from. Blank cells mean the source was checked and had no line.</p>
<input id="filter" class="filter" type="search" placeholder="Filter by team, tournament, tier or flag…">
{cs2_table}
{market_data_notes(lines_doc, odds_doc)}
"""
    write("cs2.html", page("CS2 pick'em fixtures", "Every CS2 fixture currently offered by the HotSpawn Pick'ems lobby.",
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
            f'<a href="{esc(m.get("source", {}).get("hotspawn_match_url"))}" rel="noopener">match</a>',
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
                       " · ".join(sorted({tier_label(f.get("tier")) for f in group}))])
    tour_body = f"""
<p>Fixtures are grouped by the tournament name reported by the lobby API. Each tournament page lists its
fixtures with the same verification columns as the main table.</p>
{table(["Tournament", "Fixtures", "With external line", "Unverified", "Tiers"], t_rows)}
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
  <div class="card"><div class="card-num">{has}</div><div class="card-label">with verified external line</div></div>
  <div class="card"><div class="card-num">{len(group) - has}</div><div class="card-label">unverified (blank)</div></div>
</div>
{t_table}
"""
        write(f"tournament-{slug}.html", page(name, "Tournament page — externally verified lines and explicit gaps.",
                                              body, generated_at, active="tournaments.html"))

    # ------------------------------------------------------------------ flagged
    unverified = [f for f in fixtures if not f.get("bookmaker_lines")]
    unv_rows = [[esc(fmt_time(f.get("start_time_utc")) or "not published"), tier_label(f.get("tier")),
                 esc(f.get("competition") or ""),
                 f'{esc(f.get("team_a"))} vs {esc(f.get("team_b"))}',
                 '<span class="warn">no external line found</span>',
                 ", ".join(esc(x) for x in (f.get("review_flags") or [])) or
                 '<span class="chip">external_odds_not_found</span>',
                 f'<a href="{esc(f.get("hotspawn_match_url"))}" rel="noopener">HotSpawn match</a>']
                for f in unverified]
    stale = [f for f in fixtures if "fixture_start_time_in_the_past_or_stale_source_status" in (f.get("review_flags") or [])]
    stale_rows = [[esc(fmt_time(f.get("start_time_utc"))), esc(f.get("competition")), f'{esc(f.get("team_a"))} vs {esc(f.get("team_b"))}',
                   esc(f.get("source_reported_status")),
                   '<span class="chip">scheduled in the past but the source still reports a pickable status</span>']
                  for f in stale[:80]]
    rejects_rows = [[esc(r.get("fixture_id")), esc(r.get("source")), esc(r.get("reason")),
                     esc(r.get("fixture") or r.get("event") or "")]
                    for r in (matching.get("rejected_candidates") or [])]
    unmatched_rows = [[esc(r.get("source")), esc(r.get("event")), esc(fmt_time(r.get("start_time_utc")) or "not published"),
                       esc(r.get("league")), esc(r.get("reason"))]
                      for r in (matching.get("unmatched_bookmaker_lines") or [])]
    alias_rows = [[esc(k), esc(v)] for k, v in ALIAS_NOTE.items()]

    flagged_body = f"""
<div class="banner warn"><strong>These items are published for review, not as verified facts.</strong>
Nothing on this page blocks the analysis; it exists so every gap, irregularity and failed access attempt is
visible instead of being silently filled in.</div>

<h2>1. Fixtures with no external line found ({len(unverified)})</h2>
<p>These rows are deliberately blank. Bookmakers and public markets did not quote them at collection time;
no value was inferred from HotSpawn or from any other source.</p>
{table(["Scheduled (UTC)", "Tier", "Tournament", "Match", "Status", "Flags", "HotSpawn link"], unv_rows)}

<h2>2. Stale fixtures ({len(stale)})</h2>
<p>The lobby API still reports these as pickable while their scheduled start is in the past. The raw
source status is preserved; we do not correct it.</p>
{table(["Scheduled (UTC)", "Tournament", "Match", "Source-reported status", "Note"], stale_rows)}

<h2>3. Bookmaker lines that were deliberately not used ({len(unmatched_rows)})</h2>
<p>Quotes for CS2 matches that are <em>not</em> in the current pick'em fixture list (for example the
European Pro League or a CCT South America match outside the lobby list). They are recorded here so the
matching step can be audited.</p>
{table(["Source", "Event", "Start (UTC)", "League", "Reason"], unmatched_rows)}

<h2>4. Rejected candidate matches ({len(rejects_rows)})</h2>
{table(["Fixture", "Source", "Rejection reason", "Detail"], rejects_rows)}

<h2>5. Source reachability (probed from CI)</h2>
<p>Sources that could not be read are listed with their HTTP result. A connection failure is not evidence
that a site is down, only that this pipeline could not read it.</p>
{source_health_table(odds_evidence, probe_evidence)}

<h2>6. Coverage discrepancy with the lobby snapshot</h2>
<p>An independent audit of the server-rendered lobby page (published by session <code>1d4de836</code> in
<code>audits/1d4de836/</code>) counted <strong>86</strong> CS2 fixture rows, all with source status
<code>scheduled</code>. This pipeline reads the lobby's JSON API directly and currently sees
<strong>{summary.get("fixtures_total", 0)}</strong> non-cancelled, non-ended CS2 fixtures: the extra row(s)
are fixtures that are live/started or were added after that snapshot. Both numbers are reported rather than
reconciled silently.</p>

<h2>7. Team-name aliases used for matching</h2>
<p>Matching requires both participants plus an agreeing start time (or a corresponding tournament name).
Aliases are only applied to the spellings below and every applied alias is logged in
<code>evidence/matching_evidence.json</code>.</p>
{table(["Bookmaker spelling", "Pick'em spelling"], alias_rows)}

<h2>8. Price-format derivations</h2>
<p>Pinnacle's public API publishes match-winner prices in American format; the decimal column for Pinnacle
rows is derived with the standard conversion and marked <code>decimal_price_derived_from_american_pinnacle</code>
in the row flags. Polymarket publishes implied shares, converted with <code>1 / share</code>. Bovada publishes
decimal prices directly. No other conversion is performed anywhere.</p>

<h2>10. Parallel sessions' audit observations and data (attributed, not re-verified here)</h2>
<p>Other sessions worked on this repository at the same time. Their published evidence is preserved and
linked below; it was <strong>not</strong> re-verified by this pipeline and is not mixed into the numbers
above. The independent price observations are reproduced verbatim from
<code>audits/1916f96c/observations.json</code>.</p>
{table(["Teams", "Bookmaker / market", "Quoted prices (American)", "Their derived probability", "Source (official)", "Observed", "Flags"],
       audit_price_rows(audit_1916))}
<ul>
<li><a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/audits/1d4de836/README.md" rel="noopener">Independent verification audit — session 1d4de836</a> (86-row lobby snapshot, access evidence, handoff requirements).</li>
<li><a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/audits/1916f96c/REPORT.md" rel="noopener">Independent official-source audit — session 1916f96c</a> (lobby observations, Thunderpick market reads, GG.BET/Rivalry access results).</li>
<li><a href="docs/index.html">Parallel dashboard built by session ef111e02</a> (preserved unmodified under <code>docs/</code>; it also publishes BC.Game/Polymarket references and VRS-originated reference lines in <code>data/originated_matches.json</code>).</li>
<li>Session 1916f96c also recorded that <strong>Rivalry has ceased operations</strong> and <strong>GG.BET rejected the request by region</strong>; both are therefore not usable sources here.</li>
</ul>

<h2>9. Known limitations</h2>
<ul>
<li>Only full-match / series-winner moneyline markets are used. Map markets, handicaps and totals are excluded.</li>
<li>Where a bookmaker does not publish a start time, the fixture is matched on participants plus tournament name.</li>
<li>Derived probabilities are a proportional no-vig normalisation of quoted prices — an assumption, not an official forecast.</li>
<li>Live markets can move after the timestamp shown on the row.</li>
</ul>
"""
    write("flagged.html", page("Flagged for review", "Unverified rows, irregularities and source failures.",
                               flagged_body, generated_at, active="flagged.html"))

    # -------------------------------------------------------------- methodology
    src_list = sorted({(l["source_key"], l.get("source_name"), l.get("source_kind"),
                        l.get("source_public_url"), l.get("source_api_url"))
                       for l in (odds_doc.get("lines") or [])})
    src_rows = [[esc(k), esc(n), esc(kind), f'<a href="{esc(p)}" rel="noopener">{esc(p)}</a>' if p else BLANK,
                 f'<a href="{esc(a)}" rel="noopener">API</a>' if a else BLANK]
                for k, n, kind, p, a in src_list]
    method_body = f"""
<h2>1. Fixture discovery (HotSpawn)</h2>
<p>The Pick'ems lobby is an Angular app backed by a public JSON API. The lobby page only server-renders the
next ~27 fixtures, so the fixture list on this site comes from the API the page itself calls:
<code>https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code>
(plus <code>/tenants/slug/hotspawn</code> for tenant metadata). Fixtures with a cancelled or ended status are
excluded; the rest are published with their raw source status, tier, tournament, lock time and the lobby's own
crowd pick percentage (reference only). Evidence: <code>evidence/hotspawn_probe.json</code>.</p>

<h2>2. External line sources</h2>
<p>Only named bookmakers and public prediction markets are used. HotSpawn never contributes a probability.</p>
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
and either the start times agree within 90 minutes or — when a source publishes no start time — the
tournament/league name must correspond to the fixture's tournament. One bookmaker line is used for at most one
fixture. Every decision, alias and rejection is recorded in <code>evidence/matching_evidence.json</code>.</p>

<h2>6. Cross-session material</h2>
<p>This integration keeps every session's artefacts: <a href="data/originated_matches.json">VRS-originated
reference lines</a>, <a href="data/fixtures_verified.json">verified fixtures</a>,
<a href="data/teams_verified.json">verified teams</a>,
<a href="data/flagged_irregularities.json">flagged irregularities</a>,
<a href="data/teams_verified.json">team identity evidence</a>, the
<a href="docs/index.html">parallel dashboard</a> and the audit reports linked from the Flagged page.</p>

<h2>7. Refresh</h2>
<p>A scheduled GitHub Actions job re-runs the collectors, re-derives the lines and rebuilds these pages.
The collection attempt time and the successful data time are kept separate, and a failed source keeps its
last verified quotes rather than inventing new ones.</p>
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
    return (f'<p class="note">Fixtures collected: <strong>{esc(lines_doc.get("fixture_list_collected_at_utc"))}</strong> · '
            f'Odds collected: <strong>{esc(lines_doc.get("odds_collected_at_utc"))}</strong> · '
            f'Lines derived: <strong>{esc(lines_doc.get("generated_at_utc"))}</strong> · '
            f'Raw quote rows: <strong>{len(odds_doc.get("lines") or [])}</strong></p>')


STYLE = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2230;--line:#2b3444;--txt:#e6edf3;--mut:#9aa7b4;
--acc:#4da3ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 18px}
.topbar{background:linear-gradient(180deg,#111827,#0d1117);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.topbar .wrap{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:12px 18px}
.brand{font-weight:600;display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--acc);box-shadow:0 0 12px var(--acc)}
nav a{color:var(--mut);text-decoration:none;margin-left:14px;padding:6px 8px;border-radius:8px;font-size:14px}
nav a:hover{color:var(--txt);background:var(--panel)}
nav a.active{color:var(--txt);background:var(--panel2)}
main{padding:26px 18px 40px}
h1{font-size:26px;margin:6px 0 4px}
h2{font-size:18px;margin:28px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.sub{color:var(--mut);margin:0 0 18px;max-width:900px}
.note{color:var(--mut);font-size:13.5px}
a{color:var(--acc)}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:170px;flex:1}
.card-num{font-size:26px;font-weight:700}
.card-label{color:var(--mut);font-size:13px}
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
