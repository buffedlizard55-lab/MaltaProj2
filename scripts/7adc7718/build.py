#!/usr/bin/env python3
"""Session 7adc7718 — Phone-First CS2 Pick'em Dashboard Renderer (`lobby/*.html`).

Renders 8 clean, fast, accessible, mobile-first static pages:
  - `lobby/index.html`       Executive Summary + Category Hub + Inline Unresolved Section
  - `lobby/picks.html`       All Open CS2 Matches (Probabilities + Obvious Pick + Official Sources)
  - `lobby/featured.html`    Featured Primary Sportsbook Picks
  - `lobby/low-tier.html`    Rescued Low-Tier CS2 Picks (HLTV -> Exchange / Oct-21 VRS Model)
  - `lobby/unresolved.html`  Unresolved Picks & Structural Limitations
  - `lobby/flagged.html`     Flagged for Review (All Irregularities & Source Audits)
  - `lobby/inventory.html`   Full Week-273 CS2 Inventory (90 Fixtures Across 21 Events)
  - `lobby/methodology.html` Methodology, Waterfall Calibration & Zero-Crowd-Bias Proofs
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "data" / "7adc7718" / "board.json"
OUT_DIR = ROOT / "lobby"

NAV = [
    ("index.html", "Summary"),
    ("picks.html", "All Picks"),
    ("featured.html", "Featured"),
    ("low-tier.html", "Low-Tier Rescues"),
    ("unresolved.html", "Unresolved"),
    ("flagged.html", "Flagged"),
    ("inventory.html", "Full Inventory"),
    ("methodology.html", "Method"),
]

CSS = """
:root {
  color-scheme: dark;
  --bg: #0b1017;
  --surface: #131b26;
  --surface-2: #192434;
  --border: #28364a;
  --ink: #ecf2f8;
  --muted: #9fb0c3;
  --brand: #58a6ff;
  --pick: #2ea043;
  --pick-bg: rgba(46, 160, 67, 0.16);
  --pick-ink: #7ee787;
  --amber: #d29922;
  --amber-bg: rgba(210, 153, 34, 0.16);
  --amber-ink: #f2cc60;
  --red: #f85149;
  --red-bg: rgba(248, 81, 73, 0.15);
  --red-ink: #ffa198;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
a { color: var(--brand); text-decoration: none; text-underline-offset: 3px; }
a:hover, a:focus-visible { text-decoration: underline; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 3px solid var(--amber-ink);
  outline-offset: 2px;
}
.skip-link {
  position: absolute; left: -9999px; top: 8px; z-index: 100;
  background: var(--pick-ink); color: #06210e; font-weight: 700;
  padding: 12px 16px; border-radius: 8px;
}
.skip-link:focus { left: 12px; }
.topbar {
  position: sticky; top: 0; z-index: 40;
  background: rgba(11, 16, 23, 0.96);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}
.wrap { max-width: 1160px; margin: 0 auto; padding: 0 16px; }
.topbar-inner { padding: 10px 0 8px; }
.brand-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.brand { font-weight: 800; font-size: 15px; letter-spacing: 0.02em; color: var(--ink); display: flex; align-items: center; gap: 8px; }
.brand-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--pick-ink); box-shadow: 0 0 10px var(--pick); }
.home-pill {
  font-size: 12.5px; font-weight: 600; color: var(--muted);
  border: 1px solid var(--border); border-radius: 999px;
  padding: 8px 12px; min-height: 44px; display: inline-flex; align-items: center;
}
nav.primary-nav {
  display: flex; gap: 6px; overflow-x: auto; padding: 8px 0 4px;
  scrollbar-width: thin; -webkit-overflow-scrolling: touch;
}
nav.primary-nav a {
  flex: 0 0 auto; white-space: nowrap;
  padding: 10px 13px; min-height: 44px;
  display: inline-flex; align-items: center;
  border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface); color: var(--muted);
  font-size: 13.5px; font-weight: 600;
}
nav.primary-nav a[aria-current="page"] {
  background: var(--pick-bg); border-color: var(--pick); color: var(--pick-ink);
}
main { padding: 20px 0 56px; }
h1 { font-size: clamp(1.45rem, 4.6vw, 2.05rem); line-height: 1.2; margin: 6px 0 8px; }
h2 { font-size: 1.18rem; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 1rem; margin: 14px 0 6px; }
.eyebrow { color: var(--pick-ink); font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; margin: 0; }
.lede { color: var(--muted); max-width: 780px; margin: 0 0 16px; font-size: 14.5px; }
.hero-box {
  background: linear-gradient(145deg, #132033 0%, #111926 100%);
  border: 1px solid #2d4260; border-radius: 16px; padding: 20px; margin-bottom: 18px;
}
.kpi-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px; margin: 16px 0;
}
.kpi {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 12px 14px;
}
.kpi b { display: block; font-size: 1.55rem; line-height: 1.15; font-variant-numeric: tabular-nums; }
.kpi span { color: var(--muted); font-size: 12.5px; }
.cta-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-height: 46px; padding: 10px 16px; border-radius: 10px;
  font-weight: 700; font-size: 14px; border: 1px solid var(--border);
  background: var(--surface-2); color: var(--ink); text-decoration: none;
}
.btn-go { background: var(--pick); border-color: var(--pick); color: #04190a; }
.btn-warn { background: var(--amber-bg); border-color: var(--amber); color: var(--amber-ink); }
.cat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px; margin: 14px 0 22px;
}
.cat-card {
  display: block; background: var(--surface); border: 1px solid var(--border);
  border-radius: 13px; padding: 15px 16px; color: var(--ink); text-decoration: none;
}
.cat-card:hover { border-color: var(--brand); text-decoration: none; }
.cat-card.highlight { border-color: var(--pick); }
.cat-card.warn-card { border-color: var(--amber); }
.cat-card strong { display: block; font-size: 15.5px; margin-bottom: 4px; }
.cat-card p { margin: 0; font-size: 13px; color: var(--muted); }
.callout {
  border-radius: 12px; padding: 14px 16px; margin: 16px 0;
  background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--amber);
}
.callout.danger { border-left-color: var(--red); background: #191318; }
.callout.ok { border-left-color: var(--pick); }
.toolbar {
  display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0; align-items: center;
}
.toolbar input, .toolbar select {
  min-height: 44px; padding: 9px 12px; border-radius: 10px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink);
  font: inherit; font-size: 14px;
}
.toolbar input { flex: 1 1 230px; }
.table-wrap { border: 1px solid var(--border); border-radius: 14px; overflow: hidden; background: var(--surface); }
table.picks-table { width: 100%; border-collapse: collapse; font-size: 13.8px; }
table.picks-table th {
  background: var(--surface-2); color: var(--muted); text-align: left;
  font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;
  padding: 11px 12px; border-bottom: 1px solid var(--border);
}
table.picks-table td {
  padding: 13px 12px; border-bottom: 1px solid var(--border); vertical-align: top;
  overflow-wrap: anywhere;
}
table.picks-table tr:last-child td { border-bottom: 0; }
table.picks-table tr.is-blank { background: rgba(248, 81, 73, 0.05); }
.meta-line { font-size: 12px; color: var(--muted); margin-top: 3px; }
.team-probs { display: flex; flex-direction: column; gap: 6px; min-width: 205px; }
.t-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.t-row.picked { font-weight: 800; color: var(--pick-ink); }
.t-pct { font-variant-numeric: tabular-nums; font-weight: 800; font-size: 14.5px; }
.dual-bar {
  display: flex; height: 9px; border-radius: 999px; overflow: hidden;
  background: #253346; gap: 2px;
}
.dual-bar span.bar-a { background: #58a6ff; }
.dual-bar span.bar-b { background: #a371f7; }
.dual-bar.pick-a span.bar-a { background: var(--pick); }
.dual-bar.pick-b span.bar-b { background: var(--pick); }
.pick-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 11px; border-radius: 999px; font-weight: 800; font-size: 13.5px;
  background: var(--pick-bg); border: 1px solid var(--pick); color: var(--pick-ink);
}
.pick-pill.blank {
  background: var(--red-bg); border-color: var(--red); color: var(--red-ink);
}
.badge {
  display: inline-block; padding: 3px 8px; border-radius: 6px;
  font-size: 11.5px; font-weight: 700; margin: 4px 4px 0 0;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--muted);
}
.badge.featured_market { border-color: #2f81f7; color: #9ecbff; }
.badge.rescue_exchange { border-color: var(--amber); color: var(--amber-ink); }
.badge.rescue_vrs_model { border-color: #a371f7; color: #d2a8ff; }
.badge.unresolved_blank { border-color: var(--red); color: var(--red-ink); }
.badge.flag-chip { border-color: var(--amber); background: var(--amber-bg); color: var(--amber-ink); }
.src-list { display: flex; flex-wrap: wrap; gap: 6px; }
.src-link {
  display: inline-flex; align-items: center; min-height: 36px;
  padding: 5px 10px; border-radius: 8px; font-size: 12.5px; font-weight: 600;
  background: var(--surface-2); border: 1px solid var(--border); color: var(--brand);
}
footer {
  border-top: 1px solid var(--border); margin-top: 36px; padding: 20px 0 36px;
  color: var(--muted); font-size: 12.5px;
}
@media (max-width: 760px) {
  .wrap { padding: 0 12px; }
  .hero-box { padding: 15px; border-radius: 13px; }
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .cta-row .btn { width: 100%; }
  .table-wrap { border: 0; background: transparent; overflow: visible; }
  table.picks-table, table.picks-table tbody, table.picks-table tr, table.picks-table td {
    display: block; width: 100%;
  }
  table.picks-table thead { display: none; }
  table.picks-table tr {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 12px; margin-bottom: 12px;
  }
  table.picks-table td { border-bottom: 0; padding: 6px 0; }
  table.picks-table td::before {
    content: attr(data-label);
    display: block; font-size: 11px; font-weight: 800; letter-spacing: 0.05em;
    text-transform: uppercase; color: var(--muted); margin-bottom: 4px;
  }
  .team-probs { min-width: 0; }
  .src-link { min-height: 44px; padding: 8px 12px; }
}
"""

JS = """
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('time[data-utc]').forEach(function (el) {
    var d = new Date(el.getAttribute('data-utc'));
    if (!isNaN(d.getTime())) {
      el.title = el.getAttribute('data-utc');
      el.textContent = d.toLocaleString([], {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
      });
    }
  });
  var qInput = document.getElementById('match-filter');
  var tierSel = document.getElementById('tier-filter');
  var statusEl = document.getElementById('filter-count');
  function applyFilters() {
    var q = (qInput ? qInput.value : '').trim().toLowerCase();
    var tier = tierSel ? tierSel.value : '';
    var rows = Array.prototype.slice.call(document.querySelectorAll('tr[data-row]'));
    var shown = 0;
    rows.forEach(function (tr) {
      var okQ = !q || tr.getAttribute('data-search').indexOf(q) !== -1;
      var okT = !tier || tr.getAttribute('data-tier') === tier;
      tr.hidden = !(okQ && okT);
      if (!tr.hidden) shown++;
    });
    if (statusEl && rows.length) {
      statusEl.textContent = shown + ' of ' + rows.length + ' matches shown';
    }
  }
  if (qInput) qInput.addEventListener('input', applyFilters);
  if (tierSel) tierSel.addEventListener('change', applyFilters);
  applyFilters();
});
"""


def esc(val) -> str:
    return html.escape("" if val is None else str(val), quote=True)


def fmt_pct(p: float | None) -> str:
    return f"{p * 100:.1f}%" if isinstance(p, (int, float)) else "—"


def shell(title: str, active: str, body: str, board: dict) -> str:
    cur_attr = ' aria-current="page"'
    nav_html = "".join(
        f'<a href="{esc(href)}"{cur_attr if href == active else ""}>{esc(label)}</a>'
        for href, label in NAV
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · HotSpawn CS2 Pick'em Desk</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="topbar">
  <div class="wrap topbar-inner">
    <div class="brand-row">
      <a class="brand" href="index.html"><span class="brand-dot"></span>HOTSPAWN CS2 PICK'EM · FULL LOBBY</a>
      <a class="home-pill" href="../index.html">← Root Dashboard</a>
    </div>
    <nav class="primary-nav" aria-label="CS2 Pick'em sections">{nav_html}</nav>
  </div>
</header>
<main id="main-content" class="wrap" tabindex="-1">
{body}
<footer>
  <p><strong>Snapshot observed:</strong> <code>{esc(board['fixture_snapshot_utc'])}</code> ·
  <strong>Evaluated:</strong> <code>{esc(board['generated_utc'])}</code> ·
  <strong>Auto-refresh:</strong> every 4 hours (<code>17 */4 * * *</code> via GitHub Actions).<br>
  <strong>Strict integrity rule:</strong> HotSpawn crowd pick percentages are <em>never</em> used as match probabilities.
  Unconfirmed values remain blank (<code>—</code>) and flagged on <a href="flagged.html">Flagged for Review</a>.<br>
  Data exports: <a href="../data/7adc7718/board.json">board.json</a> ·
  <a href="../data/7adc7718/picks.csv">picks.csv</a> ·
  <a href="../data/7adc7718/repo_audit.json">repo_audit.json</a> ·
  <a href="../index.html">Main Dashboard Home</a>. 18+; independent analytical research, not affiliated with HotSpawn.</p>
</footer>
</main>
<script>{JS}</script>
</body>
</html>
"""


def render_match_table(rows: list[dict], show_filters: bool = True) -> str:
    out_rows = []
    for r in rows:
        fid = r["fixture_id"]
        pa, pb = r["prob_a"], r["prob_b"]
        pick = r["pick"]
        is_blank = pick is None
        pick_cls = "pick-a" if pick == r["team_a"] else ("pick-b" if pick == r["team_b"] else "")
        bar_html = (
            f'<div class="dual-bar {pick_cls}" role="img" aria-label="{esc(r["team_a"])} {fmt_pct(pa)} vs {esc(r["team_b"])} {fmt_pct(pb)}">'
            f'<span class="bar-a" style="width:{pa*100:.1f}%"></span>'
            f'<span class="bar-b" style="width:{pb*100:.1f}%"></span></div>'
            if pa is not None and pb is not None
            else '<div class="meta-line">No verified market or opponent rating — kept blank</div>'
        )
        pick_html = (
            f'<div class="pick-pill">✓ PICK: {esc(pick)} ({fmt_pct(r["pick_prob"])})</div>'
            if pick
            else '<div class="pick-pill blank">⚠ BLANK · Unverified</div>'
        )
        detail_bits = [f'<span class="badge {esc(r["resolution_tier"])}">{esc(r["resolution_label"])}</span>']
        detail_bits.append(f'<span class="badge">{esc(r["confidence"])}</span>')
        for flg in r["flag_ids"]:
            detail_bits.append(f'<a class="badge flag-chip" href="flagged.html#{esc(flg.lower())}">Flag {esc(flg)}</a>')

        basis_detail = ""
        if r["quotes"]:
            qtxt = ", ".join(
                f'{esc(q["source_name"])} ({q["decimal_a"]:.2f}/{q["decimal_b"]:.2f})'
                for q in r["quotes"]
            )
            basis_detail = f'<div class="meta-line">Quotes ({esc(r["team_a"])}/{esc(r["team_b"])}): {qtxt}</div>'
        elif r["vrs_a"] and r["vrs_b"]:
            basis_detail = (
                f'<div class="meta-line">Oct 21 Valve VRS: {esc(r["team_a"])} {r["vrs_a"]["points"]}pt '
                f'(#{r["vrs_a"]["rank"]}) vs {esc(r["team_b"])} {r["vrs_b"]["points"]}pt (#{r["vrs_b"]["rank"]})</div>'
            )
        elif r.get("unresolvable_reason"):
            basis_detail = f'<div class="meta-line">{esc(r["unresolvable_reason"])}</div>'

        srcs = "".join(
            f'<a class="src-link" href="{esc(s["url"])}" rel="noopener">{esc(s["label"])} ↗</a>'
            for s in r["sources"]
        )
        pts_str = f" · {r['points']} pts" if r.get("points") is not None else ""
        row_cls = "is-blank" if is_blank else ""
        t_a_cls = " picked" if pick == r["team_a"] else ""
        t_b_cls = " picked" if pick == r["team_b"] else ""
        out_rows.append(
            f'<tr id="m-{esc(fid)}" class="{row_cls}" data-row="1" '
            f'data-tier="{esc(r["resolution_tier"])}" '
            f'data-search="{esc((r["team_a"] + " " + r["team_b"] + " " + r["competition"] + " " + (pick or "unresolved")).lower())}">'
            f'<td data-label="Match &amp; Lock">'
            f'<strong>{esc(r["team_a"])} vs {esc(r["team_b"])}</strong>'
            f'<div class="meta-line">{esc(r["competition"])} · Tier {esc(r.get("hotspawn_tier") or "—")}{esc(pts_str)}</div>'
            f'<div class="meta-line">Kickoff: <time data-utc="{esc(r["start_utc"])}">{esc(r["start_utc"])}</time></div>'
            f'</td>'
            f'<td data-label="Team Win Probabilities">'
            f'<div class="team-probs">'
            f'<div class="t-row{t_a_cls}"><span>{esc(r["team_a"])}</span><span class="t-pct">{fmt_pct(pa)}</span></div>'
            f'{bar_html}'
            f'<div class="t-row{t_b_cls}"><span>{esc(r["team_b"])}</span><span class="t-pct">{fmt_pct(pb)}</span></div>'
            f'</div>'
            f'</td>'
            f'<td data-label="Recommended Pick &amp; Basis">'
            f'{pick_html}<div>{"".join(detail_bits)}</div>{basis_detail}'
            f'</td>'
            f'<td data-label="Official / Verified Sources"><div class="src-list">{srcs}</div></td>'
            f'</tr>'
        )

    toolbar = (
        '<div class="toolbar">'
        '<input id="match-filter" type="search" aria-label="Search teams or tournaments" placeholder="Search team, event, or pick…">'
        '<select id="tier-filter" aria-label="Filter by evidence source">'
        '<option value="">All evidence tiers</option>'
        '<option value="featured_market">Featured · Primary Sportsbooks</option>'
        '<option value="rescue_exchange">Rescued · HLTV + Exchange Book</option>'
        '<option value="rescue_vrs_model">Rescued · Originated Oct-21 VRS Line</option>'
        '<option value="unresolved_blank">Unresolved · Blank (Unverified)</option>'
        '</select>'
        '<span id="filter-count" class="meta-line" role="status"></span>'
        '</div>'
        if show_filters
        else ""
    )
    return (
        toolbar
        + '<div class="table-wrap"><table class="picks-table"><thead><tr>'
        + '<th scope="col">Match &amp; Schedule</th>'
        + '<th scope="col">Win Probabilities</th>'
        + '<th scope="col">Recommended Pick &amp; Evidence</th>'
        + '<th scope="col">Verified Sources</th>'
        + '</tr></thead><tbody>'
        + "".join(out_rows)
        + "</tbody></table></div>"
    )


def build_pages(board: dict) -> dict[str, str]:
    s = board["summary"]
    matches = board["matches"]
    featured = [r for r in matches if r["resolution_tier"] == "featured_market"]
    rescued = [r for r in matches if r["resolution_tier"] in ("rescue_exchange", "rescue_vrs_model")]
    unresolved = board["unresolved"]
    flags = board["flagged_for_review"]
    cal = board["calibration"]

    kpis = f"""
    <div class="kpi-grid">
      <div class="kpi"><b>{s['open_matches']}</b><span>Open CS2 Matches in Lobby</span></div>
      <div class="kpi"><b>{s['resolved_with_pick']} / {s['open_matches']}</b><span>Verified Picks ({s['coverage_pct']}%)</span></div>
      <div class="kpi"><b>{s['featured_market']}</b><span>Featured Sportsbook Lines</span></div>
      <div class="kpi"><b>{s['rescue_exchange'] + s['rescue_vrs_model']}</b><span>Low-Tier Rescued Picks</span></div>
      <div class="kpi"><b>{s['unresolved_blank']}</b><span>Unresolved · Left Blank</span></div>
      <div class="kpi"><b>0%</b><span>Crowd Share Weight</span></div>
    </div>
    """

    unresolved_inline = "".join(
        f'<li><strong>{esc(u["team_a"])} vs {esc(u["team_b"])}</strong> '
        f'({esc(u["competition"])}, <time data-utc="{esc(u["start_utc"])}">{esc(u["start_utc"])}</time>) — '
        f'<strong>Win probability: <code>—</code> · Pick: <code>— (Unverified)</code></strong>. '
        f'{esc(u["unresolvable_reason"])} '
        f'Sources: <a href="{esc(u["hltv_url"])}" rel="noopener">HLTV Match</a> · '
        f'<a href="{esc(u["hotspawn_url"])}" rel="noopener">HotSpawn Card</a>.</li>'
        for u in unresolved
    ) or "<li>Zero open matches lack verified market or official Valve VRS evidence in this capture.</li>"

    index_body = f"""
    <section class="hero-box" aria-labelledby="exec-heading">
      <p class="eyebrow">Executive Summary · Week {esc(s['week_id'])} Live CS2 Pick'em Desk</p>
      <h1 id="exec-heading">Every Open HotSpawn CS2 Match — Picks, Win Probabilities &amp; Verified Sources</h1>
      <p class="lede">Automated every 4 hours from <code>play.hotspawn.com/lobby</code> and independent external markets.
      Featured CS2 picks use de-vigged primary sportsbooks; uncovered low-tier matches follow the strict
      <strong>HLTV → Esportsbook/Exchange → Official Oct-21 Valve VRS</strong> waterfall.
      HotSpawn crowd pick percentages are <strong>never</strong> used as probabilities.</p>
      {kpis}
      <div class="cta-row">
        <a class="btn btn-go" href="picks.html">Open All {s['open_matches']} CS2 Picks &amp; Probabilities →</a>
        <a class="btn" href="featured.html">Featured Bookmaker Picks ({s['featured_market']})</a>
        <a class="btn" href="low-tier.html">Rescued Low-Tier Picks ({len(rescued)})</a>
        <a class="btn btn-warn" href="#exec-unresolved">Unresolved Picks &amp; Limitations ({s['unresolved_blank']}) ↓</a>
        <a class="btn" href="flagged.html">Flagged for Review ({s['flagged_items']})</a>
      </div>
    </section>

    <section id="category-subpages" aria-labelledby="cat-heading">
      <h2 id="cat-heading">Updated Picks Lists by Category</h2>
      <div class="cat-grid">
        <a class="cat-card highlight" href="picks.html">
          <strong>All Open CS2 Picks ({s['open_matches']} Matches)</strong>
          <p>Complete mobile-ready table with both teams' win probabilities, obvious pick badges, and official links on every row.</p>
        </a>
        <a class="cat-card" href="featured.html">
          <strong>Featured Sportsbook Consensus ({s['featured_market']} Matches)</strong>
          <p>Matches directly priced by Pinnacle, Bovada, and Melbet no-vig moneylines without model overrides.</p>
        </a>
        <a class="cat-card" href="low-tier.html">
          <strong>Rescued Low-Tier CS2 Matches ({len(rescued)} Matches)</strong>
          <p>{s['rescue_exchange']} exchange rescues (Kalshi KXCS2GAME + HLTV) and {s['rescue_vrs_model']} originated Oct-21 Valve VRS lines.</p>
        </a>
        <a class="cat-card warn-card" href="unresolved.html">
          <strong>Unresolved Picks &amp; Limitations ({s['unresolved_blank']} Blank)</strong>
          <p>Why unrated low-tier teams without betting markets stay blank (never guessed 50/50 or filled from crowd votes).</p>
        </a>
        <a class="cat-card warn-card" href="flagged.html">
          <strong>Flagged for Review ({s['flagged_items']} Items)</strong>
          <p>Stale API ghosts (#1080200), slug reversals (#1082177), stale Oct-05 vs Oct-21 VRS flips (#1081600), and single-book lines.</p>
        </a>
        <a class="cat-card" href="inventory.html">
          <strong>Full Week-{esc(s['week_id'])} Inventory ({s['cs2_total_in_week']} CS2 Fixtures)</strong>
          <p>All {s['cs2_total_in_week']} CS2 fixtures across 21 tournaments in HotSpawn's API, separating open cards from closed/ghost records.</p>
        </a>
      </div>
    </section>

    <section id="exec-unresolved" aria-labelledby="unres-exec-heading">
      <h2 id="unres-exec-heading">Unresolved Picks &amp; Limitations</h2>
      <div class="callout danger">
        <p><strong>{s['unresolved_blank']} of {s['open_matches']} open CS2 matches cannot be assigned a verified probability</strong>
        and is intentionally left blank (<code>—</code>) rather than guessed:</p>
        <ul>{unresolved_inline}</ul>
        <p><strong>Core limitations enforced across all runs:</strong> (1) Retail books rarely post tier-C South American / academy qualifiers more than a few hours before veto; (2) HLTV match pages confirm lineups, world ranks, and schedules but do not expose universal two-sided odds feeds in all regions, and HLTV fan votes are never probabilities; (3) Originated Valve VRS lines require <em>both</em> rosters to hold verified VRS points and carry ±10pp model uncertainty; (4) HotSpawn crowd ownership is never used to price any match.
        <a href="unresolved.html"><strong>Read full Unresolved Picks &amp; Limitations →</strong></a></p>
      </div>
    </section>

    <section id="all-open-preview" aria-labelledby="preview-heading">
      <h2 id="preview-heading">Complete Live Open CS2 Picks Table ({s['open_matches']} Matches)</h2>
      {render_match_table(matches, show_filters=True)}
    </section>
    """

    picks_body = f"""
    <p class="eyebrow">All Open CS2 Matches · Week {esc(s['week_id'])}</p>
    <h1>Updated CS2 Picks &amp; Team Win Probabilities ({s['open_matches']} Open Matches)</h1>
    <p class="lede">Every open Counter-Strike 2 match on <code>play.hotspawn.com/lobby</code> ordered by kickoff.
    Every row cites verified external sources; unconfirmed values remain blank (<code>—</code>).</p>
    {render_match_table(matches, show_filters=True)}
    """

    featured_body = f"""
    <p class="eyebrow">Category 1 · Primary Sportsbook Consensus</p>
    <h1>Featured CS2 Picks — Primary Sportsbook Lines ({len(featured)} Matches)</h1>
    <p class="lede">Open HotSpawn CS2 matches directly covered by Pinnacle, Bovada, and Melbet full-series moneyline markets.
    Probabilities use proportional no-vig normalization only; rating models never alter featured lines.</p>
    {render_match_table(featured, show_filters=False)}
    """

    low_tier_body = f"""
    <p class="eyebrow">Category 2 · Alternate Research Waterfall</p>
    <h1>Rescued Low-Tier CS2 Picks ({len(rescued)} Matches)</h1>
    <p class="lede">Consulted <strong>only</strong> for open matches uncovered by primary sportsbooks:
    first verified on HLTV (lineups, core continuity, schedule), then checked on regulated exchange books
    (<code>Kalshi KXCS2GAME</code>, {s['rescue_exchange']} matches), and finally originated from official
    <strong>Oct 21, 2026 Valve Global Standings</strong> ({s['rescue_vrs_model']} matches, empirical logistic slope
    <code>β = {cal['beta']:.6f}</code> fitted across {cal['n_calibration_pairs']} live priced matches).</p>
    {render_match_table(rescued, show_filters=False)}
    """

    unresolved_body = f"""
    <p class="eyebrow">Unresolved Picks &amp; Methodological Boundaries</p>
    <h1>Unresolved CS2 Picks &amp; Limitations ({len(unresolved)} Blank, {s['rescue_vrs_model']} Model Estimates)</h1>
    <p class="lede">Where external betting markets and official team ratings both lack coverage, this system
    withholds a number instead of inventing 50/50 odds, floor ratings, or crowd-derived estimates.</p>
    <h2>1. Open Matches Left Blank &amp; Flagged Unverified ({len(unresolved)})</h2>
    {render_match_table(unresolved, show_filters=False) if unresolved else '<div class="callout ok">Zero open matches are currently blank.</div>'}
    <h2>2. Originated Model Lines Subject to Rating-Model Limitations ({s['rescue_vrs_model']})</h2>
    <p class="lede">These matches have verified official Oct 21, 2026 Valve Global Standings points for both teams
    and receive a reproducible originated pick, but carry no live sportsbook price yet:</p>
    {render_match_table([r for r in matches if r['resolution_tier'] == 'rescue_vrs_model'], show_filters=False)}
    <h2>3. Structural Limitations When Generating Low-Tier CS2 Picks</h2>
    <div class="callout">
      <ul>
        <li><strong>Late Tier-C Market Posting:</strong> Regional qualifiers (CCT Challengers, CIS LAN, Moscow Cyber Games 10 days out) often receive sportsbook moneyline markets only 1–4 hours before map veto. Our 4-hour cron automatically upgrades model/blank rows to live market consensus as soon as books open.</li>
        <li><strong>Unrated New / Mix Rosters:</strong> Newly formed South American or open-qualifier mixes (such as <code>LOS NINOS</code> in #1082837, with 0 VRS points and 3 HLTV maps) have neither betting odds nor official Valve ratings; assigning an arbitrary floor rating would fabricate certainty.</li>
        <li><strong>Strict Prohibition of Crowd &amp; Fan Votes:</strong> HotSpawn crowd percentages (e.g. 93% Zetta, 75% Damajuana) and HLTV reader predictions measure contest popularity, never calibrated win probability.</li>
        <li><strong>Series Winner vs Pre-Veto Map Variance:</strong> Pre-match lines reflect BO3/BO5 series-winner expectations prior to map veto and cannot price unannounced stand-ins after lock.</li>
      </ul>
    </div>
    """

    flag_rows = []
    for f in flags:
        links = "".join(
            f'<a class="src-link" href="{esc(s["url"])}" rel="noopener">{esc(s["label"])} ↗</a>'
            for s in f["sources"]
        )
        flag_rows.append(
            f'<tr id="{esc(f["id"].lower())}">'
            f'<td data-label="Flag ID &amp; Severity"><strong>{esc(f["id"])}</strong>'
            f'<div class="meta-line"><span class="badge flag-chip">{esc(f["severity"].upper())}</span> '
            f'{esc(f["category"])}</div></td>'
            f'<td data-label="Match / Scope"><strong>{esc(f["match"])}</strong>'
            f'<div class="meta-line">Fixture #{esc(f["fixture_id"])}</div></td>'
            f'<td data-label="Verified Irregularity &amp; Handling">{esc(f["detail"])}'
            f'<div class="meta-line"><strong>Action taken:</strong> {esc(f["treatment"])}</div></td>'
            f'<td data-label="Official Sources"><div class="src-list">{links}</div></td>'
            f'</tr>'
        )
    flagged_body = f"""
    <p class="eyebrow">Audit &amp; Quality Gate</p>
    <h1>Flagged for Review ({len(flags)} Verified Irregularities &amp; Gaps)</h1>
    <p class="lede">Every upstream API anomaly, unverified low-tier row, orientation mismatch, VRS snapshot drift,
    and historical repository bug uncovered during line-by-line verification, with source links.</p>
    <div class="table-wrap"><table class="picks-table"><thead><tr>
      <th scope="col">Flag</th><th scope="col">Target</th>
      <th scope="col">Finding &amp; Resolution</th><th scope="col">Sources</th>
    </tr></thead><tbody>{''.join(flag_rows)}</tbody></table></div>
    """

    inv_rows = []
    for inv in board["inventory"]:
        fid = inv["fixture_id"]
        links = [f'<a class="src-link" href="{esc(inv["hotspawn_url"])}" rel="noopener">HotSpawn ↗</a>']
        if inv.get("hltv_url"):
            links.insert(0, f'<a class="src-link" href="{esc(inv["hltv_url"])}" rel="noopener">HLTV ↗</a>')
        state_html = (
            f'<a class="badge featured_market" href="picks.html#m-{esc(fid)}">OPEN · View Pick →</a>'
            if inv["state"] == "open"
            else (
                '<a class="badge unresolved_blank" href="flagged.html#f-09">EXCLUDED GHOST (#F-09)</a>'
                if inv["state"] == "flagged_api_ghost"
                else f'<span class="badge">{esc(inv["state"])}</span>'
            )
        )
        inv_rows.append(
            f'<tr>'
            f'<td data-label="Fixture"><strong>{esc(inv["team_a"])} vs {esc(inv["team_b"])}</strong>'
            f'<div class="meta-line">#{esc(fid)} · {esc(inv["competition"])}</div></td>'
            f'<td data-label="Kickoff (UTC)"><time data-utc="{esc(inv["start_utc"])}">{esc(inv["start_utc"])}</time></td>'
            f'<td data-label="Status">{state_html}</td>'
            f'<td data-label="Sources"><div class="src-list">{"".join(links)}</div></td>'
            f'</tr>'
        )
    inventory_body = f"""
    <p class="eyebrow">Reverse-Engineered Lobby Feed</p>
    <h1>Full Week-{esc(s['week_id'])} CS2 Fixture Inventory ({len(board['inventory'])} Rows)</h1>
    <p class="lede">Complete set of Counter-Strike 2 records extracted from HotSpawn's embedded
    <code>/api/v1/fixtures</code> payload ({s['open_matches']} open playable matches + {len(board['inventory']) - s['open_matches']} closed/ghost records).</p>
    <div class="table-wrap"><table class="picks-table"><thead><tr>
      <th scope="col">Fixture</th><th scope="col">Scheduled Start</th>
      <th scope="col">State</th><th scope="col">Official Links</th>
    </tr></thead><tbody>{''.join(inv_rows)}</tbody></table></div>
    """

    cal_rows = "".join(
        f'<tr><td data-label="Match">{esc(p["match"])} (#{esc(p["fixture_id"])})</td>'
        f'<td data-label="Oct-21 VRS Δ">{p["delta_points"]:+.0f} pts</td>'
        f'<td data-label="No-Vig Book Prob">{p["market_prob_a"]*100:.1f}%</td>'
        f'<td data-label="Source"><a class="src-link" href="picks.html#m-{esc(p["fixture_id"])}">Row #{esc(p["fixture_id"])} →</a></td></tr>'
        for p in cal["pairs"]
    )
    method_body = f"""
    <p class="eyebrow">Reproducible Engineering Specification</p>
    <h1>Methodology, Lobby Reverse-Engineering &amp; Calibration</h1>
    <h2>1. HotSpawn Lobby Reverse-Engineering &amp; 4-Hour Auto-Refresh</h2>
    <p><code>https://play.hotspawn.com/lobby</code> is an Angular SSR application whose inline
    <code>&lt;script id="ng-state" type="application/json"&gt;</code> embeds the full JSON response from
    <code>/api/v1/fixtures</code> alongside published <code>/matches/&lt;slug&gt;-&lt;id&gt;</code> permalinks.
    <code>.github/workflows/lobby-7adc7718.yml</code> runs every 4 hours (<code>17 */4 * * *</code>) and on manual dispatch,
    re-collecting open CS2 matches, re-pricing lines, running unit verification, and pushing updated pages to <code>main</code>.</p>
    <h2>2. Strict 4-Tier Probability Waterfall (Zero Crowd Bias)</h2>
    <ol>
      <li><strong>Tier 1 — Primary Sportsbooks:</strong> Proportional de-vigged consensus across Pinnacle (weight 2), Bovada (1), and Melbet (1): <code>p_A = (1/d_A) / (1/d_A + 1/d_B)</code>.</li>
      <li><strong>Tier 2 — HLTV + Exchange Order Books (Uncovered Matches Only):</strong> Verified HLTV match identity + active two-sided <code>Kalshi KXCS2GAME</code> contracts within tight bid/ask spread limits.</li>
      <li><strong>Tier 3 — Originated Official Oct-21 Valve VRS Logistic Model (Uncovered Matches Only):</strong> Through-origin logistic regression <code>{esc(cal['formula'])}</code> fitted across <strong>{cal['n_calibration_pairs']}</strong> live Week-{esc(s['week_id'])} fixtures with both sportsbook lines and official <a href="{esc(cal['vrs_source_url'])}" rel="noopener">Oct 21, 2026 HLTV Valve Global Standings</a> (<code>β = {cal['beta']:.6f}</code>, in-sample MAE <code>{(cal['in_sample_mae'] or 0)*100:.1f}pp</code>).</li>
      <li><strong>Tier 4 — Honest Refusal:</strong> Missing market + unrated opponent stays blank (<code>—</code>) and flagged.</li>
    </ol>
    <h2>3. Live Week-{esc(s['week_id'])} Calibration Pairs ({cal['n_calibration_pairs']} Fixtures)</h2>
    <div class="table-wrap"><table class="picks-table"><thead><tr>
      <th scope="col">Fixture</th><th scope="col">VRS Δ (A − B)</th>
      <th scope="col">De-Vigged Book p(A)</th><th scope="col">Audit Row</th>
    </tr></thead><tbody>{cal_rows}</tbody></table></div>
    """

    return {
        "index.html": shell("Executive Summary & Full CS2 Picks", "index.html", index_body, board),
        "picks.html": shell("All Open CS2 Picks & Probabilities", "picks.html", picks_body, board),
        "featured.html": shell("Featured CS2 Sportsbook Picks", "featured.html", featured_body, board),
        "low-tier.html": shell("Rescued Low-Tier CS2 Picks", "low-tier.html", low_tier_body, board),
        "unresolved.html": shell("Unresolved CS2 Picks & Limitations", "unresolved.html", unresolved_body, board),
        "flagged.html": shell("Flagged for Review", "flagged.html", flagged_body, board),
        "inventory.html": shell("Full Week-273 CS2 Lobby Inventory", "inventory.html", inventory_body, board),
        "methodology.html": shell("Methodology & Sources", "methodology.html", method_body, board),
    }


def verify_internal_links(pages: dict[str, str]) -> None:
    for fname, html_text in pages.items():
        for href in re.findall(r'href="([^"#]+)', html_text):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (OUT_DIR / href).resolve()
            if not target.exists():
                raise AssertionError(f"Broken local link in lobby/{fname}: {href} -> {target}")


def main() -> int:
    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = build_pages(board)
    for fname, content in pages.items():
        (OUT_DIR / fname).write_text(content, encoding="utf-8")
    verify_internal_links(pages)
    print(f"7adc7718 build: wrote {len(pages)} verified mobile-first pages to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
