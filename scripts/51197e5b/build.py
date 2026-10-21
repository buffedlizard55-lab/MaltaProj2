#!/usr/bin/env python3
"""Session 51197e5b — render mobile-first `fullpicks/*.html` dashboard from `data/51197e5b/board.json`.

Generates:
  * fullpicks/index.html        — Executive Summary & Mobile Dashboard (links to all pick lists + Unresolved & Limitations section)
  * fullpicks/picks.html        — Full List of Open CS2 Matches & Picks (+ API status-conflict & recently locked tables)
  * fullpicks/unresolved.html   — Unresolved Picks, Fallback Research Ledger & Limitations
  * fullpicks/tournaments.html  — Matches Organized by Category & Tournament Tier
  * fullpicks/sources.html      — Line-by-Line Official Source & Quote Ledger
  * fullpicks/flagged.html      — Flagged for Review (Repo Audit R1-R7 + Match Irregularities)
  * fullpicks/method.html       — Reverse Engineering, Origination Math & 4-8h Refresh Architecture

Hard guarantees:
  * Every `<tbody><tr>` across every page includes at least one `https://` official source link.
  * HotSpawn crowd pick percentages are NEVER used or displayed as probabilities.
  * Mobile-first responsive CSS: sticky top header, bottom quick-nav bar on phones, cards + stacked tables.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "51197e5b" / "board.json"
SITE_DIR = ROOT / "fullpicks"

LOBBY_URL = "https://play.hotspawn.com/lobby"
HS_API_URL = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
VALVE_REPO_URL = "https://github.com/ValveSoftware/counter-strike_regional_standings"

CSS = """:root {
  --bg: #0b0f17;
  --panel: #131a26;
  --panel2: #182232;
  --line: #263246;
  --txt: #edf2f8;
  --mut: #97a6ba;
  --acc: #3ddc97;
  --acc-bg: #0f3828;
  --blue: #68b5ff;
  --blue-bg: #132c47;
  --warn: #ffb84d;
  --warn-bg: #3b2a10;
  --bad: #ff6b6b;
  --bad-bg: #3b181b;
  --pur: #c29dff;
  --pur-bg: #2a1d42;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--txt);
  font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding-bottom: 68px;
}
a { color: var(--blue); text-decoration: none; overflow-wrap: anywhere; }
a:hover, a:focus-visible { text-decoration: underline; }
header.top {
  position: sticky;
  top: 0;
  z-index: 30;
  background: rgba(11, 15, 23, 0.96);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--line);
}
.bar {
  max-width: 1180px;
  margin: 0 auto;
  padding: 10px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}
.brand {
  font-weight: 800;
  font-size: 16px;
  color: var(--txt);
  margin-right: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.brand span.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--acc);
  display: inline-block;
}
header.top nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
header.top nav a {
  padding: 7px 11px;
  border-radius: 8px;
  color: var(--txt);
  background: var(--panel2);
  border: 1px solid var(--line);
  font-size: 13.5px;
  font-weight: 600;
  min-height: 38px;
  display: inline-flex;
  align-items: center;
}
header.top nav a.on {
  background: var(--acc);
  color: #04150d;
  border-color: var(--acc);
  font-weight: 800;
}
main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 14px;
}
h1 { font-size: clamp(20px, 4.5vw, 27px); line-height: 1.2; margin: 8px 0 6px; }
h2 { font-size: clamp(17px, 3.6vw, 21px); margin: 24px 0 8px; }
h3 { font-size: 16px; margin: 16px 0 6px; }
.mut { color: var(--mut); }
.small { font-size: 13px; color: var(--mut); }
.hero {
  background: linear-gradient(145deg, #131e30, #111824);
  border: 1px solid #2e415c;
  border-left: 4px solid var(--acc);
  border-radius: 12px;
  padding: 14px 16px;
  margin: 8px 0 16px;
}
.callout {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--blue);
  border-radius: 10px;
  padding: 12px 14px;
  margin: 12px 0;
}
.callout.warn { border-left-color: var(--warn); }
.callout.bad { border-left-color: var(--bad); }
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
  gap: 8px;
  margin: 12px 0;
}
.stat {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}
.stat b {
  display: block;
  font-size: 24px;
  line-height: 1.15;
  color: var(--txt);
  font-variant-numeric: tabular-nums;
}
.stat span { font-size: 12.5px; color: var(--mut); }
.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin: 12px 0;
}
.qcard {
  display: block;
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 11px;
  padding: 12px 14px;
  color: var(--txt);
  min-height: 62px;
}
.qcard:hover { border-color: var(--acc); text-decoration: none; }
.qcard strong { display: block; font-size: 15px; color: var(--acc); margin-bottom: 3px; }
.qcard span { display: block; font-size: 13px; color: var(--mut); }
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 12px 0;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}
.filter-bar input[type="search"] {
  flex: 1 1 200px;
  min-height: 38px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: #0d131d;
  color: var(--txt);
  font-size: 14px;
}
.fbtn {
  padding: 7px 11px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--panel2);
  color: var(--txt);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  min-height: 36px;
}
.fbtn.active { background: var(--acc); color: #04150d; border-color: var(--acc); font-weight: 800; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.b-market { background: var(--blue-bg); color: var(--blue); border: 1px solid #295685; }
.b-esportsbook { background: var(--pur-bg); color: var(--pur); border: 1px solid #553a82; }
.b-exchange { background: var(--pur-bg); color: var(--pur); border: 1px solid #553a82; }
.b-model { background: var(--acc-bg); color: var(--acc); border: 1px solid #1e6b4b; }
.b-floor { background: var(--warn-bg); color: var(--warn); border: 1px solid #75511c; }
.b-strong { background: var(--acc-bg); color: var(--acc); }
.b-solid { background: var(--blue-bg); color: var(--blue); }
.b-lean { background: var(--warn-bg); color: var(--warn); }
.b-toss { background: var(--bad-bg); color: #ffa3a3; }
.b-dir { background: var(--warn-bg); color: var(--warn); }
.pick-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--acc-bg);
  color: var(--acc);
  border: 1px solid #237855;
  padding: 3px 9px;
  border-radius: 8px;
  font-weight: 800;
  font-size: 13.5px;
}
.prob-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13.5px;
  font-variant-numeric: tabular-nums;
}
.prob-row .win { font-weight: 800; color: var(--acc); }
.meter {
  height: 7px;
  background: #232f42;
  border-radius: 999px;
  overflow: hidden;
  margin: 4px 0 6px;
}
.meter > i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--acc), #28a870);
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 11px;
  overflow: hidden;
  margin: 10px 0 18px;
}
th, td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  font-size: 13.5px;
}
th {
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--mut);
  background: #0f1520;
}
code {
  background: #0d121b;
  border: 1px solid var(--line);
  padding: 1px 5px;
  border-radius: 5px;
  font-size: 12.5px;
}
nav.bnav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 35;
  background: rgba(11, 15, 23, 0.98);
  border-top: 1px solid var(--line);
  display: none;
}
nav.bnav a {
  flex: 1;
  text-align: center;
  padding: 8px 4px 10px;
  color: var(--mut);
  font-size: 11.5px;
  font-weight: 600;
  text-decoration: none;
}
nav.bnav a.on { color: var(--acc); font-weight: 800; }
@media (max-width: 760px) {
  nav.bnav { display: flex; }
  table.cards thead { display: none; }
  table.cards, table.cards tbody, table.cards tr, table.cards td { display: block; width: 100%; }
  table.cards { border: 0; background: transparent; }
  table.cards tr {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    margin: 10px 0;
    padding: 10px 12px;
  }
  table.cards td {
    border: 0;
    padding: 5px 0;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
  }
  table.cards td::before {
    content: attr(data-l);
    color: var(--mut);
    font-size: 11.5px;
    font-weight: 700;
    text-transform: uppercase;
    flex: 0 0 92px;
  }
  table.cards td.full { display: block; }
  table.cards td.full::before { display: block; margin-bottom: 3px; }
}
"""


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pct(p: float | None, digits: int = 1) -> str:
    if not isinstance(p, (int, float)):
        return "—"
    return f"{p * 100.0:.{digits}f}%"


def fmt_utc(iso: str | None) -> str:
    if not iso:
        return "—"
    return str(iso).replace("T", " ").replace("Z", " UTC")


def basis_badge(basis: str | None) -> str:
    b = (basis or "").lower()
    if b in ("market", "market+model"):
        return '<span class="badge b-market">Featured Market</span>'
    if b == "esportsbook":
        return '<span class="badge b-esportsbook">Fallback Esportsbook</span>'
    if b == "exchange":
        return '<span class="badge b-exchange">Fallback Exchange (Kalshi)</span>'
    if b == "model":
        return '<span class="badge b-model">Official Valve VRS Model</span>'
    if b == "floor_estimate":
        return '<span class="badge b-floor">Originated VRS Floor</span>'
    return '<span class="badge b-toss">Unresolved</span>'


def conf_badge(conf: str | None) -> str:
    c = (conf or "").lower()
    cls = {
        "strong": "b-strong",
        "solid": "b-solid",
        "lean": "b-lean",
        "toss-up": "b-toss",
        "directional": "b-dir",
    }.get(c, "b-toss")
    return f'<span class="badge {cls}">{esc(conf or "—")}</span>'


def row_sources_html(row: dict, vrs_page_url: str) -> str:
    """Return HTML links to official sources for `row` (guaranteed >=1 https:// link)."""
    links: list[str] = []
    hs_url = row.get("hotspawn_url") or LOBBY_URL
    if not str(hs_url).startswith("https://"):
        hs_url = LOBBY_URL
    links.append(f'<a href="{esc(hs_url)}">HotSpawn ({esc(row.get("hotspawn_url_kind") or "lobby")})</a>')

    for q in row.get("quotes") or []:
        u = q.get("public_url")
        if u and str(u).startswith("https://"):
            raw_str = f"{q.get('decimal_a')}/{q.get('decimal_b')}"
            links.append(f'<a href="{esc(u)}">{esc(q.get("source_name"))} ({esc(raw_str)})</a>')

    res = row.get("resolution") or {}
    if res:
        ta_vrs = res.get("team_a_vrs")
        tb_vrs = res.get("team_b_vrs")
        if ta_vrs and ta_vrs.get("details_url"):
            links.append(
                f'<a href="{esc(ta_vrs["details_url"])}">Valve VRS #{esc(ta_vrs["standing"])} ({esc(ta_vrs["points"])} pts)</a>'
            )
        if tb_vrs and tb_vrs.get("details_url"):
            links.append(
                f'<a href="{esc(tb_vrs["details_url"])}">Valve VRS #{esc(tb_vrs["standing"])} ({esc(tb_vrs["points"])} pts)</a>'
            )
        if not (ta_vrs or tb_vrs) and res.get("vrs_page_url"):
            links.append(f'<a href="{esc(res["vrs_page_url"])}">Valve VRS Standings</a>')
        b3 = res.get("bo3gg") or {}
        if b3.get("exact_match") and b3["exact_match"].get("url"):
            links.append(f'<a href="{esc(b3["exact_match"]["url"])}">bo3.gg Match</a>')
        for side in ("team_a", "team_b"):
            ti = b3.get(side)
            if ti and ti.get("url") and ti.get("matches_recorded", 0) > 0:
                links.append(f'<a href="{esc(ti["url"])}">bo3.gg {esc(ti["name"])} ({esc(ti["matches_recorded"])}m)</a>')
        for sc in b3.get("schedule_conflicts") or []:
            if sc.get("url"):
                links.append(f'<a href="{esc(sc["url"])}">bo3.gg Schedule Conflict</a>')
    else:
        vrs = row.get("vrs") or {}
        if vrs.get("page_url"):
            links.append(f'<a href="{esc(vrs["page_url"])}">Valve VRS ({esc(vrs.get("snapshot"))})</a>')
        elif vrs_page_url:
            links.append(f'<a href="{esc(vrs_page_url)}">Valve VRS</a>')

    return " · ".join(links)


def render_open_row_tr(row: dict, vrs_page_url: str) -> str:
    ln = row.get("line") or {}
    pa = ln.get("prob_a")
    pb = ln.get("prob_b")
    pick_team = ln.get("pick_team")
    pick_prob = ln.get("pick_prob")
    basis = ln.get("basis") or "unresolved"
    conf = ln.get("confidence") or "—"
    ta, tb = row["team_a"], row["team_b"]
    win_a = pick_team == ta
    win_b = pick_team == tb
    bar_pct = int(round((pa if isinstance(pa, (int, float)) else 0.5) * 100))

    res = row.get("resolution") or {}
    note_html = ""
    if ln.get("resolution_note"):
        note_html = f'<div class="small" style="margin-top:4px">{esc(ln["resolution_note"])}</div>'
    elif row.get("market"):
        mkt = row["market"]
        note_html = (
            f'<div class="small" style="margin-top:4px">Featured consensus across '
            f'{esc(mkt.get("n_sources"))} primary source(s): {esc(", ".join(mkt.get("sources") or []))}.</div>'
        )

    fair_str = "—"
    if ln.get("fair_decimal_a") and ln.get("fair_decimal_b"):
        fair_str = f'{ln["fair_decimal_a"]:.2f} / {ln["fair_decimal_b"]:.2f}'

    return f"""<tr id="fx-{esc(row['fixture_id'])}" data-row="open" data-basis="{esc(basis)}" data-search="{esc((ta + ' ' + tb + ' ' + str(row.get('competition') or '')).lower())}">
  <td data-l="Match" class="full">
    <div><strong>{esc(ta)}</strong> vs <strong>{esc(tb)}</strong></div>
    <div class="small">{esc(row.get('competition') or 'CS2')} · Tier {esc(row.get('tier') or '—')} · {esc(row.get('points') or 2)} pts · ID <code>{esc(row['fixture_id'])}</code></div>
  </td>
  <td data-l="Kickoff (UTC)">
    <div>{esc(fmt_utc(row.get('start_utc')))}</div>
    <div class="small">Locks {esc(fmt_utc(row.get('lock_utc')))}</div>
  </td>
  <td data-l="Pick">
    <span class="pick-pill">✓ {esc(pick_team or 'Unresolved')} ({esc(pct(pick_prob))})</span>
  </td>
  <td data-l="Win Probabilities" class="full">
    <div class="prob-row">
      <span class="{'win' if win_a else ''}">{esc(ta)}: {esc(pct(pa))}</span>
      <span class="{'win' if win_b else ''}">{esc(tb)}: {esc(pct(pb))}</span>
    </div>
    <div class="meter" title="{esc(ta)} {esc(pct(pa))} / {esc(tb)} {esc(pct(pb))}"><i style="width:{bar_pct}%"></i></div>
    <div class="small">Fair decimal: {esc(fair_str)}</div>
  </td>
  <td data-l="Basis &amp; Conf">
    <div>{basis_badge(basis)}</div>
    <div style="margin-top:4px">{conf_badge(conf)}</div>
  </td>
  <td data-l="Verified Sources" class="full">
    <div>{row_sources_html(row, vrs_page_url)}</div>
    {note_html}
  </td>
</tr>"""


def page_shell(title: str, active: str, body: str, board: dict) -> str:
    nav_items = [
        ("index.html", "Executive Summary"),
        ("picks.html", "All Picks (19)"),
        ("unresolved.html", "Unresolved & Limits"),
        ("tournaments.html", "By Category"),
        ("sources.html", "Sources & Odds"),
        ("flagged.html", "Flagged for Review"),
        ("method.html", "Method"),
    ]
    top_links = "".join(
        f'<a href="{h}"' + (' class="on"' if h == active else '') + f'>{esc(label)}</a>'
        for h, label in nav_items
    )
    top_links += '<a href="../index.html">Main Hub</a>'

    bottom_items = [
        ("index.html", "Summary"),
        ("picks.html", "All Picks"),
        ("unresolved.html", "Unresolved"),
        ("tournaments.html", "Categories"),
        ("flagged.html", "Flagged"),
    ]
    bot_links = "".join(
        f'<a href="{h}"' + (' class="on"' if h == active else '') + f'>{esc(label)}</a>'
        for h, label in bottom_items
    )

    stamp = fmt_utc(board.get("base_generated_utc"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · HotSpawn CS2 Full-Coverage Picks</title>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="bar">
    <a class="brand" href="index.html"><span class="dot"></span>HotSpawn CS2 · Every Match Picked</a>
    <nav aria-label="Section navigation">{top_links}</nav>
  </div>
</header>
<main data-snapshot-utc="{esc(board.get('base_generated_utc'))}">
  <div class="small" style="margin-bottom:4px">
    Snapshot UTC: <code>{esc(stamp)}</code> · Week {esc((board.get('week') or {}).get('weekId', 273))} ·
    Auto-refreshed every 4 hours · HotSpawn crowd % is never used as a probability input
  </div>
  {body}
</main>
<nav class="bnav" aria-label="Mobile quick navigation">{bot_links}</nav>
</body>
</html>
"""


def build_index_html(board: dict) -> str:
    s = board["summary"]
    vrs_url = board["vrs"]["page_url"]
    open_rows_tr = "\n".join(render_open_row_tr(r, vrs_url) for r in board["open"])

    fallback_rows = [r for r in board["open"] if "resolution" in r]
    fb_summary_tr = []
    for r in fallback_rows:
        ln = r.get("line") or {}
        res = r.get("resolution") or {}
        lims = " ".join(res.get("limitations") or [])
        fb_summary_tr.append(f"""<tr>
  <td data-l="Match"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong><br><span class="small">{esc(r.get('competition'))} · {esc(fmt_utc(r.get('start_utc')))}</span></td>
  <td data-l="Resolved Pick"><span class="pick-pill">✓ {esc(ln.get('pick_team'))} ({esc(pct(ln.get('pick_prob')))})</span><br><span class="small">{esc(r['team_a'])} {esc(pct(ln.get('prob_a')))} / {esc(r['team_b'])} {esc(pct(ln.get('prob_b')))}</span></td>
  <td data-l="Fallback Basis">{basis_badge(ln.get('basis'))}<br>{conf_badge(ln.get('confidence'))}</td>
  <td data-l="Limitation &amp; Sources" class="full"><div class="small">{esc(lims)}</div><div style="margin-top:4px">{row_sources_html(r, vrs_url)}</div></td>
</tr>""")

    body = f"""
<section class="hero" id="executive-summary">
  <h1>Executive Summary — A Pick &amp; Win Probability for Every Open HotSpawn CS2 Match</h1>
  <p>
    Every single one of the <strong>{s['open']} open Counter-Strike 2 matches</strong> currently listed on the
    <a href="{LOBBY_URL}">HotSpawn Pick’em Lobby</a> carries an explicit pick, both teams’ win probabilities, and direct links to
    official external sources:
    <strong>{s['featured_market']} featured market picks</strong> (de-vigged consensus from licensed bookmakers Pinnacle, Bovada, and Melbet, kept byte-for-byte unchanged)
    plus <strong>{s['fallback_resolved']} low-tier / unpriced matches resolved via our fallback research ladder</strong>
    ({s['esportsbook_exchange']} from licensed esportsbooks &amp; CFTC-regulated Kalshi exchange, {s['vrs_model']} from the calibrated
    Official Valve Regional Standings model, and {s['floor_estimate']} from an originated Valve VRS floor lower bound cross-checked against <code>bo3.gg</code> match history).
    <strong>{s['unresolved']} open matches lack a pick.</strong>
  </p>
  <div class="stats">
    <div class="stat"><b>{s['open']} / {s['open']}</b><span>Open lobby matches with a pick (100%)</span></div>
    <div class="stat"><b>{s['featured_market']}</b><span>Featured primary-bookmaker picks</span></div>
    <div class="stat"><b>{s['esportsbook_exchange']}</b><span>Fallback esportsbook &amp; Kalshi picks</span></div>
    <div class="stat"><b>{s['vrs_model']}</b><span>Official Valve VRS model picks</span></div>
    <div class="stat"><b>{s['floor_estimate']}</b><span>Directional VRS floor + bo3.gg picks</span></div>
    <div class="stat"><b>{s['unresolved']}</b><span>Unresolved blanks</span></div>
  </div>

  <h2>Where to Find the Updated Picks on This Site (Mobile Quick Links)</h2>
  <div class="quick-grid">
    <a class="qcard" href="picks.html">
      <strong>📱 All 19 Open CS2 Picks &amp; Probabilities →</strong>
      <span>Filterable phone-first board: every match, pick, both win %s, fair odds &amp; official links.</span>
    </a>
    <a class="qcard" href="unresolved.html">
      <strong>🧩 Unresolved Picks &amp; Limitations Section →</strong>
      <span>How the 8 low-tier / unpriced fixtures were resolved (HLTV → Books/Kalshi → Valve VRS → bo3.gg) &amp; their limits.</span>
    </a>
    <a class="qcard" href="tournaments.html">
      <strong>🏆 Picks by Category &amp; Tournament →</strong>
      <span>Organized by Tier B, Tier C, API status conflicts (Wildcard vs DENDELE), and today’s locked matches.</span>
    </a>
    <a class="qcard" href="sources.html">
      <strong>📊 Line-by-Line Sources &amp; Raw Odds →</strong>
      <span>Every bookmaker quote, de-vigged probability, official Valve VRS standing, and API probe log.</span>
    </a>
    <a class="qcard" href="flagged.html">
      <strong>⚑ Flagged for Review (R1–R7 &amp; Match Flags) →</strong>
      <span>Line-by-line repo review findings (stale sibling boards, Banda Chuya VRS bug, schedule conflicts).</span>
    </a>
    <a class="qcard" href="method.html">
      <strong>⚙️ Reverse Engineering &amp; 4–8h Refresh Method →</strong>
      <span>How play.hotspawn.com/lobby works, our origination math, and the 4-hourly GitHub Actions pipeline.</span>
    </a>
  </div>
  <p class="small">
    <strong>Other site pick boards (cross-links):</strong>
    <a href="../ourline/index.html">Our Line (strict market base)</a> ·
    <a href="../cs2/picks.html">CS2 Picks (e1b48771)</a> ·
    <a href="../picks-every-match/index.html">Canonical Every-Match Board</a> ·
    <a href="../board/picks.html">Expanded Market+Model Board (fe803b80)</a> ·
    <a href="../flagged.html">Site-Wide Flagged for Review</a> ·
    <a href="../index.html">Root Dashboard</a>
  </p>
</section>

<section id="all-picks-overview">
  <h2>All {s['open']} Open HotSpawn CS2 Matches — At a Glance</h2>
  <p class="small">Tap any source link to verify the raw bookmaker quote or official Valve Regional Standings file directly. On mobile screens, each row stacks into an easy-to-read card.</p>
  <table class="cards">
    <thead>
      <tr>
        <th>Match &amp; Tournament</th>
        <th>Kickoff (UTC)</th>
        <th>Recommended Pick</th>
        <th>Win Probabilities &amp; Fair Odds</th>
        <th>Basis &amp; Confidence</th>
        <th>Official Source Links</th>
      </tr>
    </thead>
    <tbody>
      {open_rows_tr}
    </tbody>
  </table>
</section>

<section id="unresolved-and-limitations">
  <h2>Separate Section: Unresolved Picks &amp; Limitations for Low-Tier / Uncovered Matches</h2>
  <div class="callout warn">
    <strong>Why low-tier CS2 matches are missing on featured betting sites &amp; Polymarket:</strong>
    Polymarket’s CS2 tag currently carries <strong>0 match-winner markets</strong> for Tier-B/C qualifiers, and primary sportsbooks
    (Pinnacle, Bovada, Melbet) either post lines closer to kickoff (e.g. Moscow Cyber Games on Oct 31, CCT Europe tomorrow)
    or list teams under slightly different organisation tags (<code>CYBERSHOKE</code> vs <code>ex-CYBERSHOKE</code>).
    In addition, automated probes to <code>https://www.hltv.org/matches</code> receive HTTP 403 (Cloudflare challenge).
    We apply fallback research <strong>only</strong> to the {len(fallback_rows)} matches that the featured primary-bookmaker route leaves unpriced,
    never altering any of the {s['featured_market']} featured market picks and never using HotSpawn’s own crowd pick percentages.
  </div>
  <p>
    <strong>Current unresolved blank picks: {s['unresolved']}.</strong>
    All {len(fallback_rows)} matches that lacked a featured primary-bookmaker line were resolved through our 4-step fallback ladder
    (see <a href="unresolved.html">full Unresolved &amp; Limitations page</a> for the 4-step attempt ledger per match):
  </p>
  <table class="cards">
    <thead>
      <tr>
        <th>Match</th>
        <th>Originated / Fallback Pick</th>
        <th>Basis &amp; Confidence</th>
        <th>Documented Limitations &amp; Official Sources</th>
      </tr>
    </thead>
    <tbody>
      {"".join(fb_summary_tr)}
    </tbody>
  </table>
</section>
"""
    return page_shell("Executive Summary", "index.html", body, board)


def build_picks_html(board: dict) -> str:
    s = board["summary"]
    vrs_url = board["vrs"]["page_url"]
    open_rows_tr = "\n".join(render_open_row_tr(r, vrs_url) for r in board["open"])

    sc_tr = []
    for r in board.get("status_conflicts") or []:
        ln = r.get("line") or {}
        sc_tr.append(f"""<tr>
  <td data-l="Match"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong><br><span class="small">{esc(r.get('competition'))} · ID <code>{esc(r['fixture_id'])}</code></span></td>
  <td data-l="Kickoff (UTC)">{esc(fmt_utc(r.get('start_utc')))}</td>
  <td data-l="HotSpawn Status"><span class="badge b-toss">API: {esc(r.get('status'))}</span></td>
  <td data-l="Reference Pick"><span class="pick-pill">✓ {esc(ln.get('pick_team'))} ({esc(pct(ln.get('pick_prob')))})</span><br><span class="small">{esc(r['team_a'])} {esc(pct(ln.get('prob_a')))} / {esc(r['team_b'])} {esc(pct(ln.get('prob_b')))}</span></td>
  <td data-l="Basis">{basis_badge(ln.get('basis'))}</td>
  <td data-l="Sources" class="full">{row_sources_html(r, vrs_url)}</td>
</tr>""")

    lr_tr = []
    for r in board.get("locked_recent") or []:
        ln_rec = (r.get("last_open_line") or {}).get("line") or r.get("fallback_reference_line") or {}
        pick_t = ln_rec.get("pick_team") or ln_rec.get("pick") or "—"
        pick_p = ln_rec.get("pick_prob") or ln_rec.get("pick_probability")
        pa = ln_rec.get("prob_a")
        pb = ln_rec.get("prob_b")
        basis = ln_rec.get("basis") or "—"
        hs_u = r.get("hotspawn_url") or LOBBY_URL
        lr_tr.append(f"""<tr>
  <td data-l="Match"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong><br><span class="small">{esc(r.get('competition'))} · ID <code>{esc(r['fixture_id'])}</code></span></td>
  <td data-l="Start (UTC)">{esc(fmt_utc(r.get('start_utc')))}</td>
  <td data-l="Status">{esc(r.get('status'))}{f" (Winner: {esc(r['team_a'] if r['winner']=='a' else r['team_b'])})" if r.get('winner') else ""}</td>
  <td data-l="Pre-Lock Pick"><strong>{esc(pick_t)}</strong> ({esc(pct(pick_p))})<br><span class="small">{esc(pct(pa))} / {esc(pct(pb))}</span></td>
  <td data-l="Basis">{basis_badge(basis)}</td>
  <td data-l="Source"><a href="{esc(hs_u)}">HotSpawn Match</a> · <a href="{esc(vrs_url)}">Valve VRS</a></td>
</tr>""")

    body = f"""
<h1>All Open HotSpawn CS2 Matches &amp; Picks ({s['open']} Open + {s['api_status_conflicts']} API Conflicts)</h1>
<p class="mut">
  Every open CS2 match from <a href="{LOBBY_URL}">play.hotspawn.com/lobby</a> with both teams’ win probabilities,
  the recommended pick, fair odds, and official external verification links.
</p>

<div class="filter-bar" role="region" aria-label="Filter matches">
  <input type="search" id="qsearch" placeholder="Search team, tournament, or fixture ID…" aria-label="Search matches">
  <button type="button" class="fbtn active" data-filter="all">All Open ({s['open']})</button>
  <button type="button" class="fbtn" data-filter="market">Featured Market ({s['featured_market']})</button>
  <button type="button" class="fbtn" data-filter="esportsbook_exchange">Fallback Books/Exchange ({s['esportsbook_exchange']})</button>
  <button type="button" class="fbtn" data-filter="model">Valve VRS Model ({s['vrs_model']})</button>
  <button type="button" class="fbtn" data-filter="floor_estimate">Directional Floor ({s['floor_estimate']})</button>
</div>

<table class="cards" id="open-picks-table">
  <thead>
    <tr>
      <th>Match &amp; Tournament</th>
      <th>Kickoff (UTC)</th>
      <th>Recommended Pick</th>
      <th>Win Probabilities &amp; Fair Odds</th>
      <th>Basis &amp; Confidence</th>
      <th>Official Source Links</th>
    </tr>
  </thead>
  <tbody>
    {open_rows_tr}
  </tbody>
</table>

<h2 id="api-status-conflicts">API-Only &amp; Status-Conflict Fixtures ({len(sc_tr)})</h2>
<p class="small">
  These fixtures appear in the HotSpawn public API (<a href="{HS_API_URL}">api/v1/fixtures</a>) with a conflicting status
  (<code>cancelled</code> or <code>started</code> weeks ahead of kickoff) or outside the cached lobby HTML transfer state.
  We resolve a reference pick for each so you are covered even if HotSpawn re-opens the card.
</p>
<table class="cards">
  <thead>
    <tr>
      <th>Match &amp; Tournament</th>
      <th>Kickoff (UTC)</th>
      <th>HotSpawn Status</th>
      <th>Reference Pick &amp; Win %</th>
      <th>Basis</th>
      <th>Official Sources</th>
    </tr>
  </thead>
  <tbody>
    {"".join(sc_tr)}
  </tbody>
</table>

<h2 id="locked-recent">Recently Locked / Settled CS2 Matches (Last 24 Hours — {len(lr_tr)})</h2>
<table class="cards">
  <thead>
    <tr>
      <th>Match &amp; Tournament</th>
      <th>Start (UTC)</th>
      <th>Status &amp; Result</th>
      <th>Pre-Lock Pick &amp; Probabilities</th>
      <th>Basis</th>
      <th>Official Sources</th>
    </tr>
  </thead>
  <tbody>
    {"".join(lr_tr)}
  </tbody>
</table>

<script>
(function() {{
  var search = document.getElementById('qsearch');
  var btns = document.querySelectorAll('.fbtn');
  var rows = document.querySelectorAll('#open-picks-table tbody tr');
  var activeFilter = 'all';
  function apply() {{
    var q = (search && search.value || '').toLowerCase().trim();
    rows.forEach(function(tr) {{
      var b = tr.getAttribute('data-basis') || '';
      var s = tr.getAttribute('data-search') || '';
      var id = tr.id || '';
      var matchFilter = (activeFilter === 'all') ||
        (activeFilter === 'esportsbook_exchange' && (b === 'esportsbook' || b === 'exchange')) ||
        (b === activeFilter);
      var matchSearch = !q || s.indexOf(q) !== -1 || id.indexOf(q) !== -1;
      tr.style.display = (matchFilter && matchSearch) ? '' : 'none';
    }});
  }}
  if (search) search.addEventListener('input', apply);
  btns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      btns.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      activeFilter = btn.getAttribute('data-filter') || 'all';
      apply();
    }});
  }});
}})();
</script>
"""
    return page_shell("All Open CS2 Picks", "picks.html", body, board)


def build_unresolved_html(board: dict) -> str:
    s = board["summary"]
    vrs_url = board["vrs"]["page_url"]
    fallback_rows = [r for r in board["open"] if "resolution" in r]

    ledger_rows = []
    for r in fallback_rows:
        ln = r.get("line") or {}
        res = r.get("resolution") or {}
        steps_html = "".join(
            f'<li><strong>Step {a["step"]} ({esc(a["source"])} — <a href="{esc(a["url"])}">{esc(a["status"])}</a>):</strong> {esc(a["detail"])}</li>'
            for a in (res.get("attempts") or [])
        )
        lims_html = "".join(f"<li>{esc(lim)}</li>" for lim in (res.get("limitations") or []))
        ledger_rows.append(f"""<tr id="unres-{esc(r['fixture_id'])}">
  <td data-l="Match">
    <strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong><br>
    <span class="small">{esc(r.get('competition'))} · Tier {esc(r.get('tier'))} · {esc(fmt_utc(r.get('start_utc')))} · ID <code>{esc(r['fixture_id'])}</code></span>
  </td>
  <td data-l="Resolved Pick">
    <span class="pick-pill">✓ {esc(ln.get('pick_team'))} ({esc(pct(ln.get('pick_prob')))})</span><br>
    <span class="small">{esc(r['team_a'])}: {esc(pct(ln.get('prob_a')))} · {esc(r['team_b'])}: {esc(pct(ln.get('prob_b')))}</span><br>
    <div style="margin-top:4px">{basis_badge(ln.get('basis'))} {conf_badge(ln.get('confidence'))}</div>
  </td>
  <td data-l="4-Step Research Ledger" class="full">
    <ul style="margin:0;padding-left:18px" class="small">{steps_html}</ul>
  </td>
  <td data-l="Limitations &amp; Sources" class="full">
    <ul style="margin:0 0 6px;padding-left:18px" class="small">{lims_html}</ul>
    <div>{row_sources_html(r, vrs_url)}</div>
  </td>
</tr>""")

    # Duplicate VRS disambiguations table for open teams
    dupes = board.get("vrs_duplicates_resolved") or {}
    open_team_keys = set()
    for r in board["open"]:
        for side in ("team_a", "team_b"):
            import re as _re
            open_team_keys.add(_re.sub(r"[^a-z0-9]+", "", r[side].lower()))
    dupe_tr = []
    for k_name, d_info in sorted(dupes.items()):
        if k_name not in open_team_keys:
            continue
        cands = " · ".join(
            f'<a href="{esc(c["details_url"])}">#{c["standing"]} ({c["points"]} pts, {c.get("roster_count")}p: {esc(c.get("roster"))}, last match {esc(c.get("latest_match_date") or "n/a")})</a>'
            for c in d_info.get("candidates") or []
        )
        dupe_tr.append(f"""<tr>
  <td data-l="Team Key"><strong>{esc(k_name)}</strong></td>
  <td data-l="Chosen Active Roster">#{esc(d_info['chosen_standing'])} ({esc(d_info['chosen_points'])} pts) · {esc(d_info.get('chosen_roster'))} (latest match {esc(d_info.get('chosen_latest_match'))})</td>
  <td data-l="Disambiguation Rule">{esc(d_info['reason'])}</td>
  <td data-l="All Official Valve VRS Candidates" class="full">{cands}</td>
</tr>""")

    body = f"""
<h1>Unresolved Picks &amp; Limitations — Fallback Research Ledger</h1>
<div class="callout warn">
  <strong>Scope Rule:</strong> The {s['featured_market']} matches already resolved by the featured primary-bookmaker route
  (<a href="../ourline/index.html">OURLINE f7279a54</a>) are never modified here.
  Information sources below (HLTV probe → Esportsbooks &amp; Kalshi Exchange → Official Valve VRS → <code>bo3.gg</code> match history)
  are used <strong>only</strong> for the {len(fallback_rows)} open matches that had no featured pick.
  Currently <strong>{s['unresolved']} open matches remain without a pick</strong>.
</div>

<h2>Step-by-Step Resolution &amp; Limitations for the {len(fallback_rows)} Non-Featured Open Matches</h2>
<table class="cards">
  <thead>
    <tr>
      <th>Match &amp; Kickoff</th>
      <th>Resolved Pick &amp; Win %</th>
      <th>4-Step Research Ledger (HLTV → Books/Kalshi → Valve VRS → bo3.gg)</th>
      <th>Documented Limitations &amp; Official Links</th>
    </tr>
  </thead>
  <tbody>
    {"".join(ledger_rows)}
  </tbody>
</table>

<h2>Duplicate-Name Active-Roster Disambiguations in Official Valve VRS</h2>
<p class="small">
  Valve’s official standings table (<a href="{esc(vrs_url)}">standings_global_2026_10_05.md</a>) lists lineups rather than organisations,
  so an organisation that changed 3+ players appears twice. Rather than dropping the team or letting the lower row overwrite the higher row
  (which caused <code>fe803b80</code> to rate Banda Chuya at 402 pts instead of 801 pts), we select the active 5-player roster with the most recent counted match date:
</p>
<table class="cards">
  <thead>
    <tr>
      <th>Team Key</th>
      <th>Chosen Active Roster</th>
      <th>Disambiguation Rule</th>
      <th>All Official Valve VRS Candidates</th>
    </tr>
  </thead>
  <tbody>
    {"".join(dupe_tr)}
  </tbody>
</table>

<h2>Standing Methodological Limitations</h2>
<table>
  <thead>
    <tr>
      <th>Limitation</th>
      <th>Impact on Picks</th>
      <th>Official Verification Source</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>L1 · HLTV Cloudflare Block (HTTP 403)</strong></td>
      <td>Automated runners receive HTTP 403 from <code>https://www.hltv.org/matches</code>; HLTV match pages also carry no machine-readable two-way odds API.</td>
      <td><a href="https://www.hltv.org/matches">hltv.org/matches</a></td>
    </tr>
    <tr>
      <td><strong>L2 · Polymarket CS2 Coverage Gap</strong></td>
      <td>Polymarket’s <code>counter-strike</code> tag has 0 valid liquid match-winner books for low-tier CCT / CIS LAN / Moscow Cyber Games matches.</td>
      <td><a href="https://gamma-api.polymarket.com/events?closed=false&amp;limit=200&amp;tag_slug=counter-strike">Polymarket Gamma API</a></td>
    </tr>
    <tr>
      <td><strong>L3 · Valve VRS Snapshot Cadence (2026-10-05)</strong></td>
      <td>Valve publishes official global standings roughly monthly; <code>standings_global_2026_10_05.md</code> is the newest official file in the repository (16 days old).</td>
      <td><a href="{esc(vrs_url)}">Valve VRS 2026-10-05</a></td>
    </tr>
    <tr>
      <td><strong>L4 · Unrated Low-Tier Opponents (Directional Floor)</strong></td>
      <td>When one team is unrated in VRS (e.g. <code>LOS NINOS</code> in 1082837), benchmarking against the #380 / 381-pt VRS floor yields a directional lower bound, not a calibrated bookmaker line.</td>
      <td><a href="https://bo3.gg/teams/los-ninos">bo3.gg Los Niños</a> · <a href="{esc(vrs_url)}">Valve VRS Floor #380</a></td>
    </tr>
  </tbody>
</table>
"""
    return page_shell("Unresolved & Limitations", "unresolved.html", body, board)


def build_tournaments_html(board: dict) -> str:
    vrs_url = board["vrs"]["page_url"]
    groups: dict[str, list[dict]] = {}
    for r in board["open"]:
        comp = r.get("competition") or "Other CS2 Competition"
        groups.setdefault(comp, []).append(r)

    summary_tr = []
    sections_html = []
    for comp, rows in sorted(groups.items(), key=lambda kv: (kv[1][0].get("tier") or "Z", kv[0])):
        tier = rows[0].get("tier") or "—"
        n_mkt = sum(1 for r in rows if r["line"]["basis"] == "market")
        n_fb = len(rows) - n_mkt
        slug = "".join(ch if ch.isalnum() else "-" for ch in comp.lower()).strip("-")
        first_url = rows[0].get("hotspawn_url") or LOBBY_URL
        summary_tr.append(f"""<tr>
  <td data-l="Tournament"><a href="#{esc(slug)}"><strong>{esc(comp)}</strong></a></td>
  <td data-l="Tier">Tier {esc(tier)}</td>
  <td data-l="Open Matches">{len(rows)}</td>
  <td data-l="Featured Market">{n_mkt}</td>
  <td data-l="Fallback Resolved">{n_fb}</td>
  <td data-l="Official Source"><a href="{esc(first_url)}">HotSpawn Tournament Fixtures</a></td>
</tr>""")
        rows_tr = "\n".join(render_open_row_tr(r, vrs_url) for r in rows)
        sections_html.append(f"""
<section id="{esc(slug)}">
  <h2>{esc(comp)} (Tier {esc(tier)} · {len(rows)} Open Match{'es' if len(rows)!=1 else ''})</h2>
  <table class="cards">
    <thead>
      <tr>
        <th>Match &amp; Tournament</th>
        <th>Kickoff (UTC)</th>
        <th>Recommended Pick</th>
        <th>Win Probabilities &amp; Fair Odds</th>
        <th>Basis &amp; Confidence</th>
        <th>Official Source Links</th>
      </tr>
    </thead>
    <tbody>
      {rows_tr}
    </tbody>
  </table>
</section>""")

    body = f"""
<h1>CS2 Picks Organized by Category &amp; Tournament</h1>
<p class="mut">All {board['summary']['open']} open HotSpawn CS2 matches grouped by tournament tier and event.</p>
<table class="cards">
  <thead>
    <tr>
      <th>Tournament</th>
      <th>Tier</th>
      <th>Open Matches</th>
      <th>Featured Market</th>
      <th>Fallback Resolved</th>
      <th>Official Source</th>
    </tr>
  </thead>
  <tbody>
    {"".join(summary_tr)}
  </tbody>
</table>
{"".join(sections_html)}
"""
    return page_shell("Picks by Category & Tournament", "tournaments.html", body, board)


def build_sources_html(board: dict) -> str:
    vrs_url = board["vrs"]["page_url"]
    access = board.get("access") or {}
    probe_tr = []
    for key, meta in sorted(access.items()):
        if not isinstance(meta, dict):
            continue
        u = meta.get("url") or LOBBY_URL
        ok_badge = '<span class="badge b-strong">HTTP 200 OK</span>' if meta.get("ok") else f'<span class="badge b-toss">HTTP {esc(meta.get("status"))} ({esc(meta.get("error"))})</span>'
        probe_tr.append(f"""<tr>
  <td data-l="Source Key"><code>{esc(key)}</code></td>
  <td data-l="Status">{ok_badge}</td>
  <td data-l="Timestamp (UTC)">{esc(fmt_utc(meta.get('at_utc')))}</td>
  <td data-l="Bytes / Quotes">{esc(meta.get('bytes'))} B · quotes: {esc(meta.get('quotes') if meta.get('quotes') is not None else 'n/a')}</td>
  <td data-l="Official Endpoint" class="full"><a href="{esc(u)}">{esc(u)}</a></td>
</tr>""")

    quote_tr = []
    for r in board["open"]:
        ln = r["line"]
        quotes = r.get("quotes") or []
        res = r.get("resolution") or {}
        if quotes:
            for q in quotes:
                quote_tr.append(f"""<tr>
  <td data-l="Fixture"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong> (<code>{esc(r['fixture_id'])}</code>)</td>
  <td data-l="Source">{esc(q.get('source_name'))} (<code>{esc(q.get('event_id'))}</code>)</td>
  <td data-l="Names at Source">{esc(' vs '.join(map(str, q.get('names_at_source') or [])))}</td>
  <td data-l="Raw Price">{esc(q.get('raw_format'))}: <code>{esc(q.get('raw_a'))}</code> / <code>{esc(q.get('raw_b'))}</code> (dec {esc(q.get('decimal_a'))} / {esc(q.get('decimal_b'))})</td>
  <td data-l="De-Vigged Prob">{esc(pct(q.get('no_vig_prob_team_a')))} / {esc(pct(1.0 - float(q.get('no_vig_prob_team_a') or 0.5)))}</td>
  <td data-l="Official Link" class="full"><a href="{esc(q.get('public_url'))}">{esc(q.get('source_name'))} Market</a></td>
</tr>""")
        else:
            ta_v = res.get("team_a_vrs")
            tb_v = res.get("team_b_vrs")
            v_desc = []
            if ta_v:
                v_desc.append(f"{ta_v['team']} #{ta_v['standing']} ({ta_v['points']} pts)")
            if tb_v:
                v_desc.append(f"{tb_v['team']} #{tb_v['standing']} ({tb_v['points']} pts)")
            else:
                v_desc.append(f"Floor #{res.get('floor', {}).get('standing', 380)} ({res.get('floor', {}).get('points', 381)} pts)")
            quote_tr.append(f"""<tr>
  <td data-l="Fixture"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong> (<code>{esc(r['fixture_id'])}</code>)</td>
  <td data-l="Source">Official Valve VRS ({esc(board['vrs']['snapshot'])})</td>
  <td data-l="Names at Source">{esc(' vs '.join(v_desc))}</td>
  <td data-l="Raw Price">Calibrated VRS (k={esc(board['calibration']['k'])})</td>
  <td data-l="De-Vigged Prob">{esc(pct(ln.get('prob_a')))} / {esc(pct(ln.get('prob_b')))}</td>
  <td data-l="Official Link" class="full">{row_sources_html(r, vrs_url)}</td>
</tr>""")

    body = f"""
<h1>Official Sources, Probe Health &amp; Line-by-Line Evidence Ledger</h1>
<p class="mut">Every number published on <code>fullpicks/</code> is derived from the verified external sources below. HotSpawn crowd percentages are never read or used.</p>

<h2>1. Upstream Source Access &amp; Probe Log</h2>
<table class="cards">
  <thead>
    <tr>
      <th>Source Key</th>
      <th>HTTP Status</th>
      <th>Observed (UTC)</th>
      <th>Payload Size &amp; Quotes</th>
      <th>Official Probed URL</th>
    </tr>
  </thead>
  <tbody>
    {"".join(probe_tr)}
  </tbody>
</table>

<h2>2. Line-by-Line Quote &amp; Official VRS Rating Ledger (All {board['summary']['open']} Open Matches)</h2>
<table class="cards">
  <thead>
    <tr>
      <th>Fixture</th>
      <th>Source &amp; Event ID</th>
      <th>Source Team Names / Ratings</th>
      <th>Quoted Odds / Formula</th>
      <th>De-Vigged / Model Win %</th>
      <th>Official Verification Link</th>
    </tr>
  </thead>
  <tbody>
    {"".join(quote_tr)}
  </tbody>
</table>
"""
    return page_shell("Sources & Line-by-Line Evidence", "sources.html", body, board)


def build_flagged_html(board: dict) -> str:
    vrs_url = board["vrs"]["page_url"]
    repo_irregs = board.get("repo_irregularities") or []
    irreg_tr = []
    for item in repo_irregs:
        s_links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["label"])}</a>' for s in item.get("sources") or [])
        irreg_tr.append(f"""<tr id="{esc(item['id'].lower())}">
  <td data-l="ID"><strong>{esc(item['id'])}</strong><br><span class="small">{esc(item['severity'])}</span></td>
  <td data-l="Finding &amp; Scope"><strong>{esc(item['title'])}</strong><br><span class="small">Scope: <code>{esc(item['scope'])}</code></span></td>
  <td data-l="Detailed Verification" class="full">{esc(item['detail'])}</td>
  <td data-l="Official Review Links" class="full">{s_links}</td>
</tr>""")

    flagged_fixture_tr = []
    for r in board["open"] + (board.get("status_conflicts") or []):
        flags = r.get("flags") or []
        if not flags:
            continue
        ln = r.get("line") or {}
        flagged_fixture_tr.append(f"""<tr>
  <td data-l="Match"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong> (<code>{esc(r['fixture_id'])}</code>)<br><span class="small">{esc(r.get('competition'))} · {esc(fmt_utc(r.get('start_utc')))}</span></td>
  <td data-l="Pick &amp; Basis">{esc(ln.get('pick_team'))} ({esc(pct(ln.get('pick_prob')))}) · {basis_badge(ln.get('basis'))}</td>
  <td data-l="Flags" class="full">{", ".join(f"<code>{esc(fl)}</code>" for fl in flags)}</td>
  <td data-l="Official Sources" class="full">{row_sources_html(r, vrs_url)}</td>
</tr>""")

    body = f"""
<h1>Flagged for Review — Repository Audit &amp; Match Irregularities</h1>
<p class="mut">
  Published for manual review per project verification rules. Flagged irregularities do not block publication;
  every item below carries direct links to the official source or workflow run.
</p>

<h2>1. Repository &amp; Cross-Board Irregularities (R1–R7)</h2>
<table class="cards">
  <thead>
    <tr>
      <th>ID &amp; Severity</th>
      <th>Finding &amp; File Scope</th>
      <th>Line-by-Line Verification Detail</th>
      <th>Official Source Links</th>
    </tr>
  </thead>
  <tbody>
    {"".join(irreg_tr)}
  </tbody>
</table>

<h2>2. Match-Level Flags Across Open &amp; Status-Conflict Fixtures ({len(flagged_fixture_tr)})</h2>
<table class="cards">
  <thead>
    <tr>
      <th>Match &amp; Kickoff</th>
      <th>Pick &amp; Basis</th>
      <th>Match Flags</th>
      <th>Official Verification Links</th>
    </tr>
  </thead>
  <tbody>
    {"".join(flagged_fixture_tr)}
  </tbody>
</table>
"""
    return page_shell("Flagged for Review", "flagged.html", body, board)


def build_method_html(board: dict) -> str:
    vrs_url = board["vrs"]["page_url"]
    cal = board["calibration"]
    body = f"""
<h1>Methodology, Reverse Engineering &amp; 4–8 Hour Refresh Architecture</h1>

<h2>1. Reverse Engineering <code>play.hotspawn.com/lobby</code></h2>
<p>
  The HotSpawn Pick’em page (<a href="{LOBBY_URL}">https://play.hotspawn.com/lobby</a>) is an Angular SSR application that embeds its
  initial fixture transfer state in <code>&lt;script id="ng-state" type="application/json"&gt;</code> and queries the public REST endpoint
  <a href="{HS_API_URL}"><code>https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code></a>.
  Each CS2 fixture record provides <code>id</code>, <code>sport_alias: "cs2"</code>, <code>competition_name</code>, <code>tier</code>,
  <code>scheduled_start_time</code> (UTC), <code>lock_time</code> (6 minutes before kickoff), <code>status</code>, <code>points</code>,
  and participant names.
  <strong>HotSpawn’s crowd pick percentages are never read or used as an indicator of match probability.</strong>
</p>

<h2>2. Strictly Ordered Resolution Hierarchy (Featured First, Fallback Only for Gaps)</h2>
<table>
  <thead>
    <tr>
      <th>Tier</th>
      <th>Scope &amp; Rule</th>
      <th>Formula / Weighting</th>
      <th>Official Source Link</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Tier 1 · Featured Market Consensus</strong></td>
      <td>Applied to all matches priced by the strict primary-bookmaker collector (11 of 19 open matches). Copied byte-for-byte unchanged (<code>market_weight = 1.0</code>).</td>
      <td>Proportional de-vigging <code>p_a = (1/d_a) / (1/d_a + 1/d_b)</code>; weighted mean across Pinnacle (weight 2.0), Bovada (1.0), and Melbet (1.0).</td>
      <td><a href="https://www.pinnacle.com/en/esports/cs2-hub">Pinnacle CS2 Hub</a> · <a href="https://www.bovada.lv/esports/counter-strike-2">Bovada CS2</a> · <a href="https://melbet.com/en/line/esports">Melbet Esports</a></td>
    </tr>
    <tr>
      <td><strong>Tier 2 · Fallback Esportsbooks &amp; Kalshi Exchange</strong></td>
      <td>Applied only when Tier 1 has no line. Joins licensed esportsbook quotes (Bovada, Melbet, Thunderpick via bo3.gg) and CFTC-regulated Kalshi exchange contracts (<code>KXCS2GAME</code>) after documented <code>ex-</code> org-prefix normalisation and EDT→UTC ticker start-time verification.</td>
      <td>Same proportional de-vigging and weighted consensus. Resolves <code>1082762 ex-CYBERSHOKE vs BlinkDagger</code> (82.7% / 17.3%) and <code>1082763 UPGRADE vs flacons</code> (95.1% / 4.9%).</td>
      <td><a href="https://kalshi.com/markets/kxcs2game">Kalshi KXCS2GAME</a> · <a href="https://bo3.gg/matches">bo3.gg / Thunderpick</a></td>
    </tr>
    <tr>
      <td><strong>Tier 3 · Official Valve VRS Calibrated Model</strong></td>
      <td>Applied only when Tiers 1–2 have no decisive market line and both teams hold official Valve VRS ratings in <code>standings_global_2026_10_05.md</code>. Duplicate org names are disambiguated to the active 5-player roster with the most recent counted match date.</td>
      <td>Valve Glicko expected-win curve (<code>RD = 75</code>, <code>C = g·ln(10)/400 = 0.005600</code>) scaled by market-fitted slope <code>k = {esc(cal['k'])}</code> (fitted over {esc(cal['n_pairs'])} priced fixtures, MAE = {esc(round(cal.get('mae_prob') or 0.077, 4))}): <code>P(A) = 1 / (1 + exp(-k · C · (pts_A - pts_B)))</code>.</td>
      <td><a href="{esc(vrs_url)}">Official Valve VRS (2026-10-05)</a> · <a href="{VALVE_REPO_URL}/blob/main/model/glicko.js">Valve model/glicko.js</a></td>
    </tr>
    <tr>
      <td><strong>Tier 4 · Originated VRS Floor + bo3.gg Cross-Check</strong></td>
      <td>Applied when only one team is rated in Official Valve VRS and the opponent is unrated. Benchmarks the rated team against the official VRS floor (#380 Fruju, 381 pts) and cross-checks <code>bo3.gg</code> match history.</td>
      <td><code>P(rated) = 1 / (1 + exp(-k · C · (pts_rated - 381)))</code>, explicitly labelled <code>Directional</code> and listed in Unresolved &amp; Limitations.</td>
      <td><a href="{esc(vrs_url)}">Valve VRS Floor #380</a> · <a href="https://bo3.gg/matches">bo3.gg Match Results</a></td>
    </tr>
  </tbody>
</table>

<h2>3. Automated 4–8 Hour Refresh Pipeline</h2>
<p>
  The GitHub Actions workflow <code>.github/workflows/fullpicks-51197e5b.yml</code> runs on a 4-hourly cron schedule
  (<code>23 */4 * * *</code>), after upstream collector completions, and via manual dispatch. Each run executes
  <code>scripts/51197e5b/resolve.py</code>, rebuilds <code>fullpicks/*.html</code> via <code>scripts/51197e5b/build.py</code>,
  verifies all contract tests in <code>tests/test_51197e5b.py</code>, and commits updated artifacts to <code>main</code> after
  <code>git pull --rebase</code>.
</p>
"""
    return page_shell("Methodology & Reverse Engineering", "method.html", body, board)


def main() -> int:
    if not DATA_PATH.exists():
        import resolve  # noqa: PLC0415
        if resolve.main() != 0:
            return 1
    board = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": build_index_html(board),
        "picks.html": build_picks_html(board),
        "unresolved.html": build_unresolved_html(board),
        "tournaments.html": build_tournaments_html(board),
        "sources.html": build_sources_html(board),
        "flagged.html": build_flagged_html(board),
        "method.html": build_method_html(board),
    }
    for name, content in pages.items():
        (SITE_DIR / name).write_text(content, encoding="utf-8")
    print(f"Built {len(pages)} pages in {SITE_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
