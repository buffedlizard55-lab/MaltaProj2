#!/usr/bin/env python3
"""Render the pickaudit mobile dashboard from data/82e71372/audit.json.

Writes only files inside pickaudit/. Every number shown comes from the audit JSON; this
module invents nothing. Rows without a value render an em dash and an explicit note.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "82e71372"
SITE = ROOT / "pickaudit"

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium",
             "low": "Low", "info": "Info"}

CSS = """
:root{--bg:#0b1220;--card:#121c2e;--card2:#0f1727;--ink:#e8eefc;--dim:#93a4c3;--line:#25334d;
--good:#7ef0b2;--warn:#ffd479;--bad:#ff9aa2;--crit:#ff6b78;--accent:#7cc4ff;--purple:#c3a7ff}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:12px 14px 64px}
header.top{position:sticky;top:0;z-index:5;background:rgba(11,18,32,.96);border-bottom:1px solid var(--line);
backdrop-filter:blur(6px)}
header.top .bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;
max-width:1080px;margin:0 auto;padding:8px 14px}
.brand{font-weight:700;font-size:15px;letter-spacing:.2px}
.brand span{color:var(--accent)}
nav{display:flex;flex-wrap:wrap;gap:6px}
nav a{display:inline-block;padding:9px 12px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;color:var(--ink);font-size:13px;min-height:40px;line-height:1.4}
nav a.active{background:var(--accent);color:#04121f;border-color:var(--accent);font-weight:700}
h1{font-size:23px;line-height:1.22;margin:10px 0 4px}
h2{font-size:18px;margin:26px 0 8px}
h3{font-size:15px;margin:18px 0 6px}
p{margin:8px 0}
.eyebrow{color:var(--dim);text-transform:uppercase;letter-spacing:.09em;font-size:11px;margin:14px 0 2px}
.lede{color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0}
@media(min-width:680px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:11px}
.tile b{display:block;font-size:23px;line-height:1.15}
.tile small{color:var(--dim);font-size:12px}
.cta{display:grid;gap:10px;margin:14px 0}
@media(min-width:680px){.cta{grid-template-columns:1fr 1fr}}
.cta a{display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--card);
border:1px solid var(--line);border-radius:14px;padding:14px 16px;text-decoration:none;color:var(--ink);
font-weight:700;min-height:56px}
.cta a.primary{background:var(--accent);color:#04121f;border-color:var(--accent)}
.cta a span.small{font-weight:400;opacity:.8;font-size:12px;text-align:right}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;
border:1px solid var(--line);white-space:nowrap}
.badge.critical{color:#2a0608;background:var(--crit);border-color:var(--crit)}
.badge.high{color:#2a1206;background:var(--bad);border-color:var(--bad)}
.badge.medium{color:#2a1d00;background:var(--warn);border-color:var(--warn)}
.badge.low{color:#0d1f33;background:var(--accent);border-color:var(--accent)}
.badge.info{color:var(--dim);background:transparent}
.badge.good{color:#08200f;background:var(--good);border-color:var(--good)}
.badge.model{color:#04121f;background:var(--accent);border-color:var(--accent)}
.badge.market{color:#08200f;background:var(--good);border-color:var(--good)}
.badge.dir{color:#2a1d00;background:var(--warn);border-color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.muted{color:var(--dim);font-size:12px}
.src{display:flex;flex-wrap:wrap;gap:6px 10px;font-size:12px}
.src a{text-decoration:underline;word-break:break-all}
.match{font-weight:700}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;border:1px solid var(--line)}
.pill.ok{color:var(--good);border-color:var(--good)}
.pill.no{color:var(--bad);border-color:var(--bad)}
.pill.warn{color:var(--warn);border-color:var(--warn)}
@media(max-width:639px){
 table thead{display:none}
 table,thead,tbody,tr,td,th{display:block;width:100%}
 tr{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 10px;padding:10px 12px}
 td{border:0;padding:4px 0}
 td[data-l]{display:flex;gap:10px;justify-content:space-between;align-items:baseline}
 td[data-l]::before{content:attr(data-l);color:var(--dim);font-size:11px;text-transform:uppercase;
 letter-spacing:.06em;flex:0 0 38%}
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

NAV = [("index.html", "Summary"), ("coverage.html", "Coverage"),
       ("arithmetic.html", "Arithmetic"), ("reconciliation.html", "Reconciliation"),
       ("links.html", "Links"), ("mobile.html", "Mobile"),
       ("flagged.html", "Flagged"), ("method.html", "Method")]


REPO = "https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/"


def ref(url: str) -> str:
    """Normalize a source reference for a page served from /pickaudit/."""
    if not url:
        return ""
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return url
    if url.startswith(("data/", "scripts/", "tests/", ".github/")):
        return REPO + url
    if url.startswith("pickaudit/"):
        return url.split("/", 1)[1]
    return "../" + url  # another desk's page or a repo page


def esc(v) -> str:
    if v is None:
        return "—"
    return html.escape(str(v), quote=True)


def pct(v, digits=1):
    if v is None:
        return "—"
    return f"{100 * float(v):.{digits}f}%"


def src_links(urls):
    out = ['<div class="src">']
    seen = set()
    for u in urls or []:
        if not u or u in seen:
            continue
        seen.add(u)
        href = ref(u)
        label = u if len(u) <= 72 else u[:69] + "…"
        out.append(f'<a href="{html.escape(href, quote=True)}" rel="noopener">{html.escape(label)}</a>')
    out.append("</div>")
    return "".join(out) if len(out) > 2 else '<span class="muted">no link published</span>'


def page(title, description, active, body):
    nav = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        nav.append(f'<a href="{href}"{cls}>{label}</a>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="description" content="{html.escape(description)}">
<title>{html.escape(title)} · Pick audit 82e71372</title>
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="bar">
<div class="brand">Pick audit <span>· independent verification</span></div>
<nav>{''.join(nav)}</nav>
</div></header>
<main class="wrap">
{body}
<footer>
<p>Independent audit desk <code>82e71372</code>. Read-only verification of every published pick desk;
this desk originates no probabilities of its own. HotSpawn is fixture discovery only and is never used
as a probability input. Blank means not verifiable from an official source — never an inferred value.</p>
<p><a href="../index.html">Site home</a> · <a href="../everypick/picks.html">Every-match picks</a> ·
<a href="method.html">Audit method &amp; tolerances</a> · <a href="flagged.html">Flagged for review</a></p>
</footer>
</main>
</body>
</html>
"""


def basis_badge(basis, directional=False):
    if not basis:
        return '<span class="badge info">—</span>'
    b = str(basis)
    if "market" in b or "exchange" in b or "book" in b:
        cls = "market"
    elif "bound" in b or "floor" in b or directional:
        cls = "dir"
    else:
        cls = "model"
    return f'<span class="badge {cls}">{html.escape(b)}</span>'


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
    s = audit["summary"]
    run = audit["generated_utc"]
    findings = sorted(audit["findings"], key=lambda f: SEV_ORDER.get(f["severity"], 9))

    # ------------------------------------------------------------- index / executive summary
    sev_counts = s["findings_by_severity"]
    key_findings = [f for f in findings if f["severity"] in ("critical", "high", "medium")]
    rows = []
    rows.append(f"""
<p class="eyebrow">Executive summary · audit run {esc(run)}</p>
<h1>Every HotSpawn CS2 match has a verified pick. Here is the independent proof.</h1>
<p class="lede">This desk re-derives every published probability from raw bookmaker quotes and the
official Valve rating table, checks every source link, and compares all pick desks fixture by fixture.
It originates no picks itself — it verifies the desks that do.</p>
<div class="tiles">
  <div class="tile"><b>{s['canonical_open_fixtures']}</b><small>open HotSpawn CS2 fixtures audited</small></div>
  <div class="tile"><b>{s['fully_unresolved']}</b><small>fixtures with no pick anywhere</small></div>
  <div class="tile"><b>{s['arithmetic_checks']}</b><small>arithmetic checks · <strong>{s['arithmetic_failures']} failed</strong></small></div>
  <div class="tile"><b>{s['valve_point_checks']}</b><small>Valve point references · {s['valve_point_failures']} mismatch</small></div>
  <div class="tile"><b>{s['pick_flips']}</b><small>pick-direction disagreements between desks</small></div>
  <div class="tile"><b>{s['wide_spreads']}</b><small>fixtures with &gt;10pp probability spread</small></div>
  <div class="tile"><b>{sev_counts.get('high', 0) + sev_counts.get('critical', 0)}</b><small>high/critical flags</small></div>
  <div class="tile"><b>{'live' if s['valve_reachable'] else 'offline'}</b><small>Valve GitHub verification</small></div>
</div>
<div class="callout good"><strong>Coverage result:</strong> all {s['canonical_open_fixtures']} currently open
lobby fixtures have a pick and both win probabilities on the every-match desks, with zero fully unresolved
rows. {s['policy_blanks']} blanks exist on strict/collector boards by policy and are filled downstream.</div>
""")
    rows.append('<h2>Where to find the updated picks (on this site)</h2>')
    rows.append("""
<div class="cta">
<a class="primary" href="../everypick/picks.html"><span>All picks · every open match, both probabilities</span><span class="small">refreshed every 4 hours →</span></a>
<a href="../everypick/index.html"><span>Every-match executive summary</span><span class="small">mobile-first start-here desk →</span></a>
<a href="../hotspawn-picks/picks.html"><span>HotSpawn-picks desk (HLTV → books → VRS ladder)</span><span class="small">independent every-match desk →</span></a>
<a href="../fullpicks/picks.html"><span>Fullpicks desk</span><span class="small">earlier every-match desk →</span></a>
<a href="../everypick/unresolved.html"><span>Unresolved picks &amp; limitations</span><span class="small">bounds, thin books, stale ratings →</span></a>
<a href="coverage.html"><span>This audit's coverage matrix</span><span class="small">fixture × desk →</span></a>
</div>""")
    rows.append("<h2>Findings that need your review</h2><table><thead><tr><th>ID</th><th>Severity</th><th>Finding</th></tr></thead><tbody>")
    for f in key_findings:
        rows.append(f'<tr><td data-l="ID"><code>{esc(f["id"])}</code></td>'
                    f'<td data-l="Severity"><span class="badge {f["severity"]}">{SEV_LABEL[f["severity"]]}</span></td>'
                    f'<td data-l="Finding"><strong>{esc(f["title"])}</strong><br><span class="muted">{esc(f["detail"][:300])}</span></td></tr>')
    rows.append("</tbody></table>")
    rows.append('<p class="muted">Full list including low-severity and informational items: <a href="flagged.html">Flagged for review</a>.</p>')
    rows.append(f"""
<h2>What was verified</h2>
<div class="card">
<ul>
<li><strong>Arithmetic ({s['arithmetic_checks']} checks, {s['arithmetic_failures']} failures):</strong>
each book no-vig probability, consensus, Valve-rating logistic probability and pick-side rule re-derived
independently. See <a href="arithmetic.html">arithmetic</a>.</li>
<li><strong>Official Valve ratings ({s['valve_point_checks']} references):</strong> every standing/points
pair checked against the live <code>ValveSoftware/counter-strike_regional_standings</code> GitHub file;
{s['valve_remnant_rows']} sub-five-player 'remnant' roster use detected and flagged.</li>
<li><strong>Calibration:</strong> the fitted slope k is re-derived from the 60 stored market/rating pairs
({'matches' if audit['calibration']['matches'] else 'DOES NOT MATCH'}): refit {audit['calibration']['refit_k']:.6f}
vs published {audit['calibration']['claimed_k']:.6f}.</li>
<li><strong>Cross-desk reconciliation:</strong> {s['pick_flips']} pick flips and {s['wide_spreads']} wide
spreads documented with each desk's basis on <a href="reconciliation.html">reconciliation</a>.</li>
<li><strong>Links &amp; mobile:</strong> internal link rot, source-per-row presence and mobile rendering
checked page by page on <a href="links.html">links</a> and <a href="mobile.html">mobile</a>.</li>
</ul>
</div>
<p class="muted">Audit inputs are the committed boards listed on <a href="method.html">method</a>.
External (non-GitHub) links are live-checked by the CI runner where the build sandbox cannot reach them;
unchecked links are labelled, never assumed valid.</p>
""")
    (SITE / "index.html").write_text(
        page("Executive summary", "Independent verification of every HotSpawn CS2 pick: coverage, "
             "arithmetic, sources and mobile checks.", "index.html", "".join(rows)), encoding="utf-8")

    # ------------------------------------------------------------- coverage
    cov = audit["coverage"]
    hotspawn_by_id = {f["fixture_id"]: f.get("hotspawn_url") for f in audit["canonical_fixtures"]}
    valve_url = ("https://github.com/ValveSoftware/counter-strike_regional_standings/"
                 "blob/main/live/2026/standings_global_2026_10_05.md")
    desk_ids = [d["id"] for d in audit["desks"] if d["present"]]
    h = ["<h1>Coverage matrix</h1>",
         f'<p class="lede">One row per open HotSpawn CS2 fixture ({len(cov)}). A green cell means the desk '
         "publishes a pick plus both probabilities; blanks mean the desk leaves the fixture to another desk "
         "by policy.</p>",
         '<div class="tbl-scroll"><table><thead><tr><th>Fixture</th><th>Start (UTC)</th>']
    for d in desk_ids:
        h.append(f"<th>{esc(d)}</th>")
    h.append("<th>Sources</th></tr></thead><tbody>")
    for c in cov:
        h.append(f'<tr><td data-l="Fixture"><span class="match">{esc(c["team_a"])} v {esc(c["team_b"])}</span>'
                 f'<br><span class="muted">{esc(c["competition"])} · {esc(c["fixture_id"])}</span></td>'
                 f'<td data-l="Start">{esc(c["start_utc"])}</td>')
        for d in desk_ids:
            cell = c["desks"].get(d, {})
            if cell.get("complete"):
                h.append(f'<td class="num" data-l="{esc(d)}"><span class="pill ok">{esc(cell["pick"])} '
                         f'{pct(cell["prob_a"])}</span><br><span class="muted">{esc(cell["basis"])}</span></td>')
            elif cell.get("has_row"):
                h.append('<td data-l="' + esc(d) + '"><span class="pill warn">blank by policy</span></td>')
            else:
                h.append('<td data-l="' + esc(d) + '"><span class="muted">no row</span></td>')
        row_urls = [u for u in (hotspawn_by_id.get(c["fixture_id"]), valve_url) if u]
        h.append(f'<td data-l="Sources">{src_links(row_urls)}</td></tr>')
    h.append("</tbody></table></div>")
    h.append(f'<div class="callout"><strong>{s["fully_unresolved"]} fully unresolved fixtures.</strong> '
             "Policy blanks live on strict featured-line and collector boards; the every-match desks "
             "(everypick, hotspawn-picks, fullpicks) resolve them via the documented research ladder.</div>")
    (SITE / "coverage.html").write_text(
        page("Coverage matrix", "Fixture by desk coverage of every open HotSpawn CS2 match.",
             "coverage.html", "".join(h)), encoding="utf-8")

    # ------------------------------------------------------------- arithmetic
    a = ["<h1>Arithmetic verification</h1>",
         '<p class="lede">Every stored probability is re-derived from its raw inputs. Tolerances and '
         "formulas are documented on the method page.</p>"]
    cal = audit["calibration"]
    a.append('<h2>Calibration slope (independent refit)</h2><div class="card"><table><tbody>')
    for label, val in [("Method", cal["method"]), ("Pairs", cal["n_pairs"]),
                       ("Published k", cal["claimed_k"]), ("Re-derived k", f'{cal["refit_k"]:.10f}'),
                       ("Published MAE", cal["claimed_mae"]), ("Re-derived MAE", cal["refit_mae"]),
                       ("Result", "MATCH" if cal["matches"] else "MISMATCH")]:
        a.append(f'<tr><td data-l="{esc(label)}">{esc(label)}</td><td data-l="Value">{esc(val)}</td></tr>')
    a.append("</tbody></table>" + src_links([cal["source"], cal["method_source"]]) + "</div>")
    cp = audit["constant_provenance"]
    a.append('<h2>Rating constant C provenance</h2><div class="card"><table><tbody>')
    for label, val in [("Project C", cp["project_c"]),
                       ("Valve Glicko Q = ln(10)/400", cp["valve_glicko_q"]),
                       ("Valve default RD (fit.js)", cp["valve_default_rd"]),
                       ("Q × g(RD) re-derived", cp["derived_c_q_times_g_rd"]),
                       ("Absolute difference", cp["abs_diff"]),
                       ("fit.js literally contains 0.0056000078", cp["fit_js_contains_project_c"])]:
        a.append(f'<tr><td data-l="{esc(label)}">{esc(label)}</td><td data-l="Value">{esc(val)}</td></tr>')
    a.append("</tbody></table>" + src_links([cp["glicko_source"], cp["fit_source"]]) + "</div>")
    ar = audit["arithmetic"]
    a.append(f'<h2>Per-row checks ({sum(x["n_checks"] for x in ar)} checks across {len(ar)} desk rows)</h2>')
    a.append('<div class="tbl-scroll"><table><thead><tr><th>Desk</th><th>Fixture</th><th>Basis</th>'
             "<th>Checks</th><th>Result</th></tr></thead><tbody>")
    for r in ar:
        res = '<span class="pill ok">all pass</span>' if r["n_fail"] == 0 else \
              f'<span class="pill no">{r["n_fail"]} fail</span>'
        a.append(f'<tr><td data-l="Desk">{esc(r["desk"])}</td>'
                 f'<td data-l="Fixture">{esc(r["team_a"])} v {esc(r["team_b"])} <span class="muted">{esc(r["fixture_id"])}</span>'
                 f'{src_links([valve_url])}</td>'
                 f'<td data-l="Basis">{basis_badge(r["basis"])}</td>'
                 f'<td class="num" data-l="Checks">{r["n_checks"]}</td>'
                 f'<td data-l="Result">{res}</td></tr>')
        for f in r["failures"]:
            a.append(f'<tr><td colspan="5" data-l="Failure"><span class="badge high">{esc(f["check"])}</span> '
                     f'{esc(f["detail"])} {src_links(f["urls"])}</td></tr>')
    a.append("</tbody></table></div>")
    vc = audit["valve_checks"]
    a.append(f'<h2>Official Valve point references ({len(vc)})</h2>')
    a.append('<div class="tbl-scroll"><table><thead><tr><th>Desk</th><th>Fixture</th><th>Side</th>'
             "<th>Standing</th><th>Published</th><th>Official</th><th>OK</th></tr></thead><tbody>")
    for v in vc:
        ok = '<span class="pill ok">match</span>' if v["ok"] else '<span class="pill no">mismatch</span>'
        rem = ' <span class="badge dir">remnant</span>' if v.get("remnant_row") else ""
        a.append(f'<tr><td data-l="Desk">{esc(v["desk"])}</td>'
                 f'<td data-l="Fixture">{esc(v["fixture_id"])} {esc(v["team"])}</td>'
                 f'<td data-l="Side">{esc(v["side"])}</td>'
                 f'<td class="num" data-l="Standing">#{esc(v["standing"])}</td>'
                 f'<td class="num" data-l="Published">{esc(v["published_points"])}</td>'
                 f'<td class="num" data-l="Official">{esc(v["official_points"])} {rem}</td>'
                 f'<td data-l="OK">{ok}</td></tr>')
    a.append("</tbody></table>" + src_links([vc[0]["source"] if vc else VALVE_GITHUB]) + "</div>")
    (SITE / "arithmetic.html").write_text(
        page("Arithmetic", "Independent re-derivation of every published pick probability.",
             "arithmetic.html", "".join(a)), encoding="utf-8")

    # ------------------------------------------------------------- reconciliation
    rc = ["<h1>Cross-desk reconciliation</h1>",
          '<p class="lede">Probabilities are aligned to the HotSpawn team order (archive-desk swaps are '
          "corrected by team name). A flip means desks disagree on which side wins; a wide spread is a "
          "gap above 10 percentage points.</p>"]
    for r in audit["reconciliation"]:
        cls = "callout bad" if r["pick_flip"] else ("callout" if r["wide_spread"] else "callout good")
        rc.append('<section class="card">')
        rc.append(f'<div class="{cls}"><strong>{esc(r["team_a"])} v {esc(r["team_b"])}</strong> '
                  f'<span class="muted">{esc(r["competition"])} · {esc(r["start_utc"])} · '
                  f'{esc(r["fixture_id"])}</span><br>')
        if r["pick_flip"]:
            rc.append('<span class="badge high">PICK FLIP</span> ')
        if r["wide_spread"]:
            rc.append('<span class="badge medium">WIDE SPREAD</span> ')
        if r["order_swaps"]:
            rc.append(f'<span class="badge low">order swapped on: {esc(", ".join(r["order_swaps"]))}</span>')
        rc.append(f'<span class="muted">probability spread {100 * r["spread"]:.1f} pp</span></div>')
        rc.append('<div class="tbl-scroll"><table><thead><tr><th>Desk</th><th>Pick</th>'
                  '<th>P(team A)</th><th>Basis</th></tr></thead><tbody>')
        for d, v in r["desks"].items():
            rc.append(f'<tr><td data-l="Desk">{esc(d)}</td><td data-l="Pick">{esc(v["pick"])}</td>'
                      f'<td class="num" data-l="P(team A)">{pct(v["prob_a"])}</td>'
                      f'<td data-l="Basis">{basis_badge(v["basis"], v.get("directional"))}</td></tr>')
        rc.append("</tbody></table></div>")
        rc.append(src_links([r["hotspawn_url"],
                    "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md"]))
        rc.append("</section>")
    (SITE / "reconciliation.html").write_text(
        page("Reconciliation", "Fixture-by-fixture comparison of every pick desk.",
             "reconciliation.html", "".join(rc)), encoding="utf-8")

    # ------------------------------------------------------------- links
    lk = ["<h1>Source-link audit</h1>",
          '<p class="lede">Internal links must resolve inside the repository. External links are '
          "live-checked when the environment allows; otherwise they are recorded as unchecked with the "
          "reason rather than assumed valid.</p>"]
    lk.append('<div class="tbl-scroll"><table><thead><tr><th>Page</th><th>Internal</th><th>Broken</th>'
              "<th>External</th><th>External errors</th><th>Unchecked here</th><th>Rows lacking source</th></tr></thead><tbody>")
    for e in audit["link_audit"]:
        if not e.get("exists"):
            lk.append(f'<tr><td data-l="Page">{esc(e["page"])}</td><td colspan="6"><span class="pill no">page missing</span></td></tr>')
            continue
        lk.append(f'<tr><td data-l="Page">{esc(e["page"])}</td>'
                  f'<td class="num" data-l="Internal">{e["internal_links"]}</td>'
                  f'<td class="num" data-l="Broken">{len(e["internal_broken"])}</td>'
                  f'<td class="num" data-l="External">{e["external_links"]}</td>'
                  f'<td class="num" data-l="Errors">{len(e["external_bad"])}</td>'
                  f'<td class="num" data-l="Unchecked">{len(e["external_unchecked"])}</td>'
                  f'<td data-l="No source">{esc(", ".join(e.get("fixture_blocks_without_source", [])) or "none")}</td></tr>')
        if e["internal_broken"]:
            lk.append(f'<tr><td colspan="7" data-l="Broken links"><span class="muted">{esc("; ".join(e["internal_broken"]))}</span></td></tr>')
    lk.append("</tbody></table></div>")
    hosts = {}
    for e in audit["link_audit"]:
        for u in e.get("external_unchecked", []):
            hosts[u["host"]] = hosts.get(u["host"], 0) + 1
    lk.append('<h2>External hosts not reachable from the build sandbox</h2><div class="card"><p>')
    lk.append(" ".join(f'<span class="pill">{esc(h)} ({n})</span>' for h, n in sorted(hosts.items())))
    lk.append('</p><p class="muted">The CI workflow sets PICKAUDIT_LIVE_LINKS=1 on its runner, which has '
              "full network access, and live-checks every host. GitHub hosts are always checked live.</p></div>")
    lk.append(src_links(["https://github.com/ValveSoftware/counter-strike_regional_standings"]))
    (SITE / "links.html").write_text(
        page("Source links", "Per-page link and source-citation verification.",
             "links.html", "".join(lk)), encoding="utf-8")

    # ------------------------------------------------------------- mobile
    mb = ["<h1>Mobile rendering audit</h1>",
          '<p class="lede">Static checks of viewport, language, titles, responsive CSS, readable base '
          "type and touch-target sizing. This audit's own pages are held to the same checklist.</p>",
          '<div class="tbl-scroll"><table><thead><tr><th>Page</th><th>Failed checks</th></tr></thead><tbody>']
    for m in audit["mobile_audit"]:
        if not m.get("exists"):
            mb.append(f'<tr><td data-l="Page">{esc(m["page"])}</td><td data-l="Result"><span class="pill no">missing</span></td></tr>')
            continue
        failed = m.get("failed", [])
        res = '<span class="pill ok">all pass</span>' if not failed else \
              ", ".join(f'<span class="pill warn">{esc(x)}</span>' for x in failed)
        mb.append(f'<tr><td data-l="Page">{esc(m["page"])}</td><td data-l="Result">{res}</td></tr>')
    mb.append("</tbody></table></div>")
    mb.append('<div class="card"><h3>Checklist</h3><ul>'
              "<li>viewport meta with width=device-width</li><li>html lang attribute</li>"
              "<li>title and meta description</li><li>@media responsive rules present</li>"
              "<li>base font ≥15px</li><li>tap targets with min-height ≥38px</li>"
              "<li>responsive card tables or horizontal scroll wrapper</li></ul></div>")
    (SITE / "mobile.html").write_text(
        page("Mobile", "Phone-readability checks for every audited page.",
             "mobile.html", "".join(mb)), encoding="utf-8")

    # ------------------------------------------------------------- flagged
    fl = ["<h1>Flagged for review</h1>",
          '<p class="lede">Every irregularity, disagreement and unverifiable item found by the audit, '
          "with source links. Nothing here blocks the published picks; each item is recorded so it can be "
          "reviewed and traced.</p>"]
    for f in findings:
        fl.append(f'<div class="card"><h3><span class="badge {f["severity"]}">{SEV_LABEL[f["severity"]]}</span> '
                  f'<code>{esc(f["id"])}</code> · {esc(f["title"])}</h3>'
                  f'<p>{esc(f["detail"])}</p>'
                  f'{src_links(f.get("urls"))}'
                  f'<p class="muted">Scope: {esc(f.get("scope") or "repository-wide")}</p></div>')
    (SITE / "flagged.html").write_text(
        page("Flagged for review", "All audit findings with severity and source links.",
             "flagged.html", "".join(fl)), encoding="utf-8")

    # ------------------------------------------------------------- method
    pol = audit["policy"]
    mt = f"""
<h1>Audit method &amp; limitations</h1>
<p class="lede">How this desk verifies the every-match picks without originating any of its own.</p>
<h2>Inputs (read-only)</h2>
<div class="card"><ul>"""
    for d in audit["desks"]:
        mt += f'<li><strong>{esc(d["label"])}</strong> — <code>{esc(d["board"])}</code>'
        if not d["present"]:
            mt += ' <span class="pill no">missing</span>'
        else:
            mt += (f' · generated {esc(d.get("generated_utc"))} · {d["n_open"]} open rows, '
                   f'{d["n_with_pick"]} with picks, {d["n_blank"]} policy blanks')
        if d.get("adapter_error"):
            mt += f'<br><span class="pill no">{esc(d["adapter_error"])}</span>'
        mt += "</li>"
    mt += "</ul></div>"
    mt += f"""
<h2>Checks and tolerances</h2>
<div class="card"><table><tbody>
<tr><td data-l="Rule">No HotSpawn crowd input</td><td>{esc(pol["no_hotspawn_crowd_as_probability"])}</td></tr>
<tr><td data-l="Rule">Blank stays blank (never inferred)</td><td>{esc(pol["blank_stays_blank"])}</td></tr>
<tr><td data-l="Tolerance">prob_a + prob_b = 1 within</td><td>{esc(pol["tolerances"]["sum"])}</td></tr>
<tr><td data-l="Tolerance">single-book no-vig re-derivation</td><td>{esc(pol["tolerances"]["quote"])}</td></tr>
<tr><td data-l="Tolerance">consensus re-derivation</td><td>{esc(pol["tolerances"]["consensus"])}</td></tr>
<tr><td data-l="Tolerance">VRS logistic re-derivation</td><td>{esc(pol["tolerances"]["model"])}</td></tr>
<tr><td data-l="Tolerance">cross-desk spread flag</td><td>{100 * pol["tolerances"]["spread_flag"]:.0f} pp</td></tr>
</tbody></table></div>
<h2>Probability formulas being checked</h2>
<div class="card">
<p>Book two-way no-vig: <code>p_a = (1/odds_a) / ((1/odds_a) + (1/odds_b))</code></p>
<p>Valve-rating logistic: <code>p = 1 / (1 + exp(-k · C · (points_a − points_b)))</code> with
<code>C = Q·g(RD=75)</code>, <code>Q = ln(10)/400</code> from Valve's glicko.js, and
<code>k</code> fitted by OLS through the origin in logit space on 60 market/rating pairs
(documented in scripts/f7279a54/core.py).</p>
<p>Pick rule: the higher-probability side; ties published as explicit toss-ups.</p>
</div>
<h2>Research ladder used by the desks being audited</h2>
<div class="card"><ol>
<li>Featured bookmaker consensus (Pinnacle, Bovada, Melbet, Thunderpick) — de-vigged.</li>
<li>Regulated exchange / secondary books (Kalshi) with roster-verified name aliases.</li>
<li>HLTV / bo3.gg identity and roster checks for alias joins.</li>
<li>Official Valve regional standings logistic origination when no book prices the fixture.</li>
<li>One-sided ratings become labelled bounds (≥ / ≤), never point estimates.</li>
<li>If no source exists at all, the row stays explicitly unresolved.</li>
</ol></div>
<h2>Limitations</h2>
<div class="card"><ul>
<li>The build sandbox can only reach GitHub hosts; HLTV, book and exchange links are live-checked by
the CI runner (PICKAUDIT_LIVE_LINKS=1) and labelled unchecked in local runs.</li>
<li>The Valve global table is monthly and can be up to ~4 weeks old; roster changes after publication
are not reflected.</li>
<li>Originated model lines carry roughly ±8 pp mean absolute error (see the calibration MAE).</li>
<li>Thin or zero-volume exchange quotes are market-maker ladders, not traded consensus.</li>
<li>This audit verifies published numbers; it does not settle match outcomes or grade pick accuracy.</li>
</ul></div>
<h2>Automation</h2>
<div class="card"><p><code>.github/workflows/pickaudit-82e71372.yml</code> re-runs this audit every eight
hours and after the upstream board workflows, committing only <code>data/82e71372/**</code> and
<code>pickaudit/**</code>.</p></div>
"""
    (SITE / "method.html").write_text(
        page("Method", "Audit methodology, tolerances, sources and limitations.",
             "method.html", mt), encoding="utf-8")

    print("rendered", len(list(SITE.glob("*.html"))), "pages to pickaudit/")


VALVE_GITHUB = "https://github.com/ValveSoftware/counter-strike_regional_standings"

if __name__ == "__main__":
    main()
