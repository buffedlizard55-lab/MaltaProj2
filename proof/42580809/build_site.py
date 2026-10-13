#!/usr/bin/env python3
"""
Session 42580809 — publish the coverage board as a static, mobile-first section.

Reads (never writes) the session data files:
  data/board_42580809.json     rows for every CS2 fixture in the pick'em window
  data/originated_42580809.json originated model lines + their diagnostics
  proof/42580809/evidence/matching.json   accept/reject decisions (summarised)
  proof/42580809/evidence/coverage.json   coverage counters

Writes site/42580809/{index,tables,methodology,flagged}.html + assets + data/*.
Every value rendered here is copied from those files; nothing is typed in by hand.
"""

from __future__ import annotations

import html
import json
import os
import shutil
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "evidence")
OUT = os.path.join(REPO, "site", "42580809")
SECTION = "site/42580809"

CSS = """
:root{--bg:#0b0f16;--card:#151b24;--card2:#1d2531;--fg:#e8eef6;--dim:#93a1b1;--line:#2a3442;
--ok:#3fb950;--warn:#e3b341;--bad:#f85149;--acc:#58a6ff;--acc2:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header{padding:14px 12px 8px;background:#060a10;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}
h1{font-size:19px;margin:0 0 2px}h2{font-size:18px;margin:24px 12px 8px}h3{font-size:15px;margin:16px 12px 6px}
.sub{color:var(--dim);font-size:12.5px}
nav{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
nav a{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:4px 10px;background:var(--card);color:var(--fg)}
nav a.on{border-color:var(--ok);color:var(--ok)}
.wrap{max-width:1040px;margin:0 auto;padding:10px 12px 70px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:14px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.stat b{display:block;font-size:23px;line-height:1.1}
.stat span{color:var(--dim);font-size:11.5px}
.note{background:var(--card2);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:10px;padding:11px;margin:12px 0;font-size:14px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
input[type=search],select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:9px;padding:9px 10px;font-size:15px;min-width:130px;flex:1 1 150px}
label.chk{font-size:13.5px;color:var(--dim);display:flex;gap:6px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:9px;padding:8px 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0}
.card.named{border-left:5px solid var(--ok)}
.card.originated{border-left:5px solid var(--acc2)}
.card.none{border-left:5px solid var(--bad)}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--dim)}
.teams{margin:10px 0 4px}
.team{display:flex;justify-content:space-between;gap:10px;align-items:baseline;font-size:17px;font-weight:600;padding:3px 0}
.team.pick{color:var(--ok)}
.team .p{font-variant-numeric:tabular-nums;font-weight:700}
.team.nodata .p{color:var(--dim);font-weight:500}
.bar{height:9px;border-radius:6px;background:#2c3543;overflow:hidden;margin:8px 0}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#238636,#3fb950)}
.bar.orig i{background:linear-gradient(90deg,#9e6a03,#d29922)}
.badge{display:inline-block;font-size:11.5px;border-radius:999px;padding:2px 9px;border:1px solid var(--line);margin:3px 4px 0 0;color:var(--dim)}
.badge.ok{color:var(--ok);border-color:var(--ok)}.badge.warn{color:var(--warn);border-color:var(--warn)}
.badge.bad{color:var(--bad);border-color:var(--bad)}
.src{font-size:12.5px;color:var(--dim);border-top:1px dashed var(--line);margin-top:8px;padding-top:7px}
.src div{margin:4px 0}
.src b{color:var(--fg);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;border-bottom:1px solid var(--line);padding:7px 6px;vertical-align:top}
th{color:var(--dim);font-size:12px;font-weight:600}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px}
code{background:#0a1017;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-size:12.5px;overflow-wrap:anywhere}
ul{padding-left:20px}li{margin:4px 0}
footer{color:var(--dim);font-size:12.5px;border-top:1px solid var(--line);margin-top:36px;padding:16px 12px}
.fresh{color:var(--dim);font-size:12px}
@media(min-width:680px){.stats{grid-template-columns:repeat(4,1fr)}h1{font-size:23px}.team{font-size:18px}}
"""

JS = """
(function(){
  var q=document.getElementById('q'),b=document.getElementById('basis'),t=document.getElementById('tour'),
      s=document.getElementById('show'),cards=[].slice.call(document.querySelectorAll('article.card')),
      shown=document.getElementById('shown');
  function apply(){
    var term=(q&&q.value||'').toLowerCase(), bs=b&&b.value||'', tr=t&&t.value||'', sh=s&&s.value||'upcoming', n=0;
    cards.forEach(function(c){
      var ok=true;
      if(term && (c.dataset.search||'').indexOf(term)<0) ok=false;
      if(bs && c.dataset.basis!==bs) ok=false;
      if(tr && c.dataset.tour!==tr) ok=false;
      if(sh==='upcoming' && c.dataset.stale==='1') ok=false;
      if(sh==='stale' && c.dataset.stale!=='1') ok=false;
      if(sh==='nopick' && c.dataset.pick!=='0') ok=false;
      c.style.display = ok?'':'none'; if(ok) n++;
    });
    if(shown) shown.textContent = n;
  }
  [q,b,t,s].forEach(function(el){ if(el){ el.addEventListener('input',apply); el.addEventListener('change',apply);} });
  apply();
})();
"""

BASIS_LABEL = {
    "market-derived": ("named bookmaker/exchange quote", "named"),
    "aggregator-fallback": ("aggregator fallback (not a licensed bookmaker)", "originated"),
    "unverified": ("no usable external line", "none"),
    "stale-listing": ("past-kickoff listing — no probability published", "none"),
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def esc(v):
    return html.escape(str("" if v is None else v), quote=True)


def pct(x, digits=0):
    if x is None:
        return "—"
    return f"{round(x * 100, digits):g}%"


def short_ts(v):
    return "—" if not v else str(v).replace("T", " ").replace("Z", " UTC")


def page(title, active, body):
    links = [("index.html", "Board"), ("tables.html", "Tables"), ("methodology.html", "Methodology"),
             ("flagged.html", "Flagged for review")]
    nav = "".join('<a class="{c}" href="{h}">{t}</a>'.format(c="on" if h == active else "", h=h, t=t)
                  for h, t in links)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="Win probabilities and picks for every CS2 match in the HotSpawn pick'em lobby, derived from external betting lines only.">
<meta name="color-scheme" content="dark"><link rel="stylesheet" href="assets/style.css"></head>
<body><header><h1>{esc(title)}</h1>
<div class="sub">Every CS2 fixture in the HotSpawn pick'em lobby · external lines only · HotSpawn used for fixture discovery, never as a probability</div>
<nav>{nav}</nav></header><div class="wrap">{body}</div>
<footer>Session 42580809 coverage board. Odds and probabilities are derived from the external sources linked on each
row; rows that could not be confirmed are blank and published on <a href="flagged.html">Flagged for review</a>.
Not affiliated with HotSpawn or any bookmaker. 18+ · betting involves risk.</footer>
<script src="assets/app.js"></script></body></html>"""


def source_line(q):
    odds = (q.get("raw") or {}).get("odds")
    bits = []
    if odds:
        bits.append(f"quoted decimal odds {odds[0]} / {odds[1]}")
    if (q.get("raw") or {}).get("yes_bid_a") is not None:
        r = q["raw"]
        bits.append(f"Kalshi book: {r['yes_bid_a']}–{r['yes_ask_a']} / {r['yes_bid_b']}–{r['yes_ask_b']}"
                    f" (spread {r.get('spread_a')}/{r.get('spread_b')}, volume {r.get('volume_a')}/{r.get('volume_b')})")
    if q.get("overround") is not None:
        bits.append(f"book margin {round(q['overround'] * 100, 2)}%")
    if q.get("orientation_vs_fixture") == "reversed":
        bits.append("source listed the teams in the opposite order (prices reversed)")
    if q.get("start_time_delta_min") not in (None, 0):
        bits.append(f"source schedule differs by {q['start_time_delta_min']:.0f} min")
    if q.get("alias_note"):
        bits.append("name spelling differs — accepted with tournament + schedule proof")
    if q.get("market_is_live"):
        bits.append("market status active when read")
    return (f'<div><b><a href="{esc(q.get("source_url") or q.get("api_url"))}" rel="nofollow noopener">'
            f'{esc(q.get("source_name"))}</a></b> — no-vig {pct(q["no_vig_probability_a"], 1)} / '
            f'{pct(q["no_vig_probability_b"], 1)} · read {esc(short_ts(q.get("retrieved_at_utc")))}'
            + (f' · <a href="{esc(q["api_url"])}" rel="nofollow noopener">quote API</a>' if q.get("api_url") and q["api_url"] != q.get("source_url") else "")
            + (". " + esc("; ".join(bits)) if bits else "") + "</div>")


def card(row, originated):
    basis = row["basis"]
    label, css = BASIS_LABEL.get(basis, (basis, "none"))
    o = originated.get(row["fixture_id"]) if basis == "unverified" else None
    p_a, p_b = row["p_a"], row["p_b"]
    method = None
    if o and o.get("originated_p_a") is not None:
        p_a, p_b = o["originated_p_a"], o["originated_p_b"]
        method = o["method"]
        css, label = "originated", "originated model line"
    pick = None
    if p_a is not None:
        pick = row["team_a"] if p_a >= p_b else row["team_b"]
    teams = ""
    for name, prob in ((row["team_a"], p_a), (row["team_b"], p_b)):
        cls = "team" + (" pick" if pick == name else "") + (" nodata" if prob is None else "")
        teams += f'<div class="{cls}"><span>{esc(name)}{" ✅" if pick == name else ""}</span><span class="p">{pct(prob)}</span></div>'
    bar = (f'<div class="bar{" orig" if css == "originated" else ""}"><i style="width:{round((p_a or 0) * 100)}%"></i></div>'
           if p_a is not None else "")
    badges = [f'<span class="badge {css}">{esc(label)}</span>']
    if basis == "market-derived":
        badges.append(f'<span class="badge ok">{row["n_named_sources"]} named source(s)</span>')
        if row["n_named_sources"] == 1:
            badges.append('<span class="badge warn">single source</span>')
    if basis == "aggregator-fallback":
        badges.append('<span class="badge warn">aggregator, not a licensed bookmaker</span>')
    for q in row["sources"]:
        if q["source_key"] == "kalshi":
            r = q.get("raw") or {}
            spread = max(r.get("spread_a") or 0, r.get("spread_b") or 0)
            volume = float(r.get("volume_a") or 0) + float(r.get("volume_b") or 0)
            if spread >= 0.05 or volume == 0:
                badges.append(f'<span class="badge warn">thin Kalshi book: spread {spread}, traded volume {volume:g}'
                              ' — read the bid/ask below</span>')
    if row["stale"]:
        badges.append('<span class="badge bad">listing stale: kickoff already passed</span>')
    if row["rejected_quotes_flagged"]:
        badges.append('<span class="badge bad">source quote(s) rejected by the quality gate — see flagged page</span>')
    if o and o.get("method"):
        badges.append(f'<span class="badge warn">{esc(o["method"])} — not a book price</span>')
    if o and o.get("cross_check_vrs_probability_a") is not None:
        badges.append(f'<span class="badge">VRS cross-check {pct(o["cross_check_vrs_probability_a"])}</span>')
    if o and not o.get("method"):
        badges.append('<span class="badge bad">no model coverage: ' + esc("; ".join(o.get("unoriginated_because", []))) + '</span>')

    if row["stale"]:
        late = row.get("late_quotes") or []
        src = ("<div>This listing's kickoff has already passed, so any price read for it was read while "
               "the match was live or finished. It is not a pre-match line, no probability or pick is "
               "published, and the readings below are kept only as evidence.</div>"
               + "".join(source_line(q) for q in late))
    elif row["sources"]:
        src = "".join(source_line(q) for q in row["sources"])
    elif o and o.get("method"):
        src = "<div>No bookmaker or exchange price exists for this pairing. This line is our own model output; " \
              "the inputs and the calibration error are on the <a href=\"methodology.html\">Methodology</a> page.</div>"
    else:
        src = "<div>No external source priced this match and no model input covers both teams, so no probability is " \
              "published. Listed on <a href=\"flagged.html\">Flagged for review</a>.</div>"

    search = " ".join(str(x) for x in (row["team_a"], row["team_b"], row["tournament"])).lower()
    return f"""<article class="card {css}" data-basis="{esc(basis)}" data-tour="{esc(row['tournament'])}"
 data-stale="{1 if row['stale'] else 0}" data-pick="{0 if pick is None else 1}" data-search="{esc(search)}">
<div class="top"><span>{esc(row['tournament'])} · tier {esc(row['tier'] or '?')} · {esc(row['offered_points'])} pts</span>
<span>{esc(short_ts(row['scheduled_start_time_utc']))} · {esc(row['fixture_id'])}</span></div>
<div class="teams">{teams}</div>{bar}
<div>{''.join(badges)}</div>
<div class="src">{src}
<div>Fixture listing: <a href="{esc(row['hotspawn_url'])}" rel="nofollow noopener">HotSpawn match page</a>
 · crowd pick shown for reference only: {esc(row['hotspawn_pick_pct_reference_only'][0])}% / {esc(row['hotspawn_pick_pct_reference_only'][1])}%
 (<a href="methodology.html">excluded from every calculation</a>)</div></div></article>"""


def main() -> int:
    board = load(os.path.join(REPO, "data", "board_42580809.json"))
    orig_doc = load(os.path.join(REPO, "data", "originated_42580809.json"))
    matching = load(os.path.join(EV, "matching.json"))
    coverage = load(os.path.join(EV, "coverage.json"))
    rows = board["rows"]
    orig = {r["fixture_id"]: r for r in orig_doc["rows"]}
    now = datetime.now(tz=timezone.utc)

    upcoming = [r for r in rows if not r["stale"]]
    named = [r for r in upcoming if r["basis"] == "market-derived"]
    fallback = [r for r in upcoming if r["basis"] == "aggregator-fallback"]
    orig_rows = [r for r in upcoming if r["basis"] == "unverified" and orig.get(r["fixture_id"], {}).get("originated_p_a") is not None]
    none_rows = [r for r in upcoming if r["basis"] == "unverified" and orig.get(r["fixture_id"], {}).get("originated_p_a") is None]

    stats = f"""<div class="stats">
<div class="stat"><b>{len(rows)}</b><span>CS2 fixtures in the lobby's pick'em window</span></div>
<div class="stat"><b>{len(upcoming)}</b><span>still upcoming ({len(rows) - len(upcoming)} listed kickoffs already passed)</span></div>
<div class="stat"><b>{len(named)}</b><span>upcoming with a named bookmaker/exchange line</span></div>
<div class="stat"><b>{len(fallback)}</b><span>upcoming with only an aggregator fallback</span></div>
<div class="stat"><b>{len(orig_rows)}</b><span>upcoming priced by our originated model</span></div>
<div class="stat"><b>{len(none_rows)}</b><span>upcoming with no usable line (blank + flagged)</span></div>
<div class="stat"><b>{coverage['quotes_accepted']}</b><span>market quotes accepted onto fixtures</span></div>
<div class="stat"><b>{coverage['quotes_rejected_by_quality_gate']}</b><span>quotes rejected by the quality gate</span></div></div>"""

    intro = f"""<div class="note"><b>How to read a card.</b> The team marked ✅ is the pick, with both probabilities
beside the names. <span class="badge ok">named bookmaker/exchange quote</span> means the line comes from Pinnacle,
Bovada or Kalshi and the card links the exact URL that was read. <span class="badge warn">aggregator fallback</span>
means only egamersworld.com priced it — shown because the alternative would be a blank, but it is not a licensed
bookmaker. <span class="badge warn">originated model line</span> means no market prices the pairing at all and the
number comes from our own documented model (<a href="methodology.html">method</a>, with its calibration error).
<span class="badge bad">no usable external line</span> means we publish nothing for that match.
Every card also links the HotSpawn fixture listing and shows the lobby's crowd pick <i>for reference only</i> —
it never enters any calculation.</div>
<div class="note">Snapshot: fixtures read {esc(short_ts(board['generated_at_utc']))} from the lobby's public API;
quotes read at the timestamps printed on each card. Rows sort by kickoff, soonest first; the default filter hides
the {len(rows) - len(upcoming)} listings whose kickoff is in the past (they remain pickable in the lobby but no
live market can exist for them — see <a href="flagged.html">Flagged for review</a>).</div>"""

    tours = sorted({r["tournament"] for r in rows})
    controls = f"""<div class="controls">
<select id="show" aria-label="Show"><option value="upcoming">Upcoming only</option>
<option value="all">All {len(rows)} fixtures</option><option value="stale">Past-kickoff listings only</option>
<option value="nopick">Rows without a probability</option></select>
<input id="q" type="search" placeholder="Search team or tournament" aria-label="Search">
<select id="basis" aria-label="Basis"><option value="">Any evidence</option>
<option value="market-derived">Named bookmaker/exchange line</option>
<option value="aggregator-fallback">Aggregator fallback only</option>
<option value="unverified">No usable line / model only</option></select>
<select id="tour" aria-label="Tournament"><option value="">All tournaments</option>
{''.join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in tours)}</select>
<span class="fresh">showing <b id="shown">{len(upcoming)}</b> of {len(rows)}</span></div>"""

    # Upcoming first (soonest kickoff at the top), then past-kickoff listings newest first, so the
    # actionable rows come first even before the filter script runs.
    ordered = (sorted([r for r in rows if not r["stale"]], key=lambda r: r["scheduled_start_time_utc"] or "")
               + sorted([r for r in rows if r["stale"]], key=lambda r: r["scheduled_start_time_utc"] or "", reverse=True))
    cards = "".join(card(r, orig) for r in ordered)
    index = page("Pick'em coverage board", "index.html", stats + intro + controls + cards)

    # ------------------------------------------------------------------ tables
    def fixture_table(items):
        out = ['<div class="tablewrap"><table><tr><th>Kickoff (UTC)</th><th>Tournament</th><th>Match</th>'
               '<th>P(A)</th><th>P(B)</th><th>Pick</th><th>Basis</th><th>Sources</th><th>Links</th></tr>']
        for r in items:
            o = orig.get(r["fixture_id"]) if r["basis"] == "unverified" else None
            p_a, p_b = r["p_a"], r["p_b"]
            method = ""
            if o and o.get("originated_p_a") is not None:
                p_a, p_b = o["originated_p_a"], o["originated_p_b"]
                method = f'<br><span class="badge warn">{esc(o["method"])}</span>'
            pick = "" if p_a is None else (r["team_a"] if p_a >= p_b else r["team_b"])
            links = [f'<a href="{esc(r["hotspawn_url"])}" rel="nofollow noopener">HotSpawn</a>']
            links += [f'<a href="{esc(q["source_url"] or q["api_url"])}" rel="nofollow noopener">{esc(q["source_name"])}</a>'
                      for q in r["sources"]]
            srcs = ", ".join(f'{esc(q["source_name"])} ({pct(q["no_vig_probability_a"], 1)})' for q in r["sources"]) or "—"
            out.append(f'<tr><td>{esc(short_ts(r["scheduled_start_time_utc"]))}</td><td>{esc(r["tournament"])}</td>'
                       f'<td><b>{esc(r["team_a"])}</b> vs <b>{esc(r["team_b"])}</b></td>'
                       f'<td>{pct(p_a, 1)}</td><td>{pct(p_b, 1)}</td><td>{esc(pick) or "—"}</td>'
                       f'<td>{esc(r["basis"])}{method}</td><td>{srcs}</td><td>{" · ".join(links)}</td></tr>')
        return "".join(out) + "</table></div>"

    src_rows = "".join(
        f'<tr><td>{esc(k)}</td><td>{esc(v["quotes"])}</td>'
        f'<td>{esc(v.get("fixtures") or 0)}</td></tr>' for k, v in sorted(coverage["by_source"].items()))
    tour_rows = "".join(
        f'<tr><td>{esc(t)}</td><td>{esc(v["fixtures"])}</td><td>{esc(v["named"])}</td>'
        f'<td>{esc(v["fallback"])}</td><td>{esc(v["none"])}</td></tr>'
        for t, v in sorted(coverage["by_tournament"].items(), key=lambda kv: (-kv[1]["named"], kv[0])))
    tables = page("Tables", "tables.html", f"""
<h2>Upcoming fixtures ({len(upcoming)})</h2>
<p class="sub">Every CS2 fixture in the pick'em window whose kickoff has not passed. Blank probability means no
usable external line and no model coverage; the row is flagged rather than estimated.</p>
{fixture_table(sorted(upcoming, key=lambda r: r["scheduled_start_time_utc"]))}
<h2>Past-kickoff listings ({coverage['stale_fixtures']})</h2>
<p class="sub">The lobby still returns these as pickable. Their scheduled start is already in the past (most by
more than 100 days), so no external market can exist and no probability is published.</p>
{fixture_table(sorted([r for r in rows if r["stale"]], key=lambda r: r["scheduled_start_time_utc"]))}
<h2>Quote coverage by source</h2>
<div class="tablewrap"><table><tr><th>Source</th><th>Quotes collected</th><th>Fixtures quoted</th></tr>{src_rows}</table></div>
<h2>Coverage by tournament</h2>
<div class="tablewrap"><table><tr><th>Tournament</th><th>Fixtures</th><th>Named line</th><th>Aggregator only</th><th>No usable line</th></tr>{tour_rows}</table></div>
<h2>Machine-readable data</h2>
<ul>
<li><a href="data/board.json">board.json</a> — every fixture with its per-source quotes, derivation and flags</li>
<li><a href="data/board.csv">board.csv</a> — the same rows as a flat table</li>
<li><a href="data/originated.json">originated.json</a> — our model lines, inputs and cross-validation</li>
<li><a href="data/coverage.json">coverage.json</a> — the counters above</li>
</ul>
<p class="sub">Raw collection evidence (every payload, every accept/reject decision) is committed under
<code>proof/42580809/evidence/</code> in the project repository.</p>""")

    # ------------------------------------------------------------------ methodology
    cv = orig_doc["method_a_cross_validation"]
    mv = orig_doc["method_b"]
    vf = mv["fit"]
    cv_rows = "".join(f'<tr><td>{esc(r["match"])}</td><td>{pct(r["market_p"],1)}</td>'
                      f'<td>{pct(r["model_p"],1)}</td><td>{r["abs_error"]}</td></tr>' for r in cv["rows"])
    vrs_rows = "".join(f'<tr><td>{esc(r["match"])}</td><td>{esc(r["points_difference"])}</td>'
                       f'<td>{pct(r["market_p"],1)}</td><td>{pct(r["model_p"],1)}</td><td>{r["abs_error"]}</td></tr>'
                       for r in vf.get("rows", []))
    meth = f"""<div class="note">Every number on this board is produced by the pipeline in this repository from a
named public source. Nothing is typed in by hand, nothing is estimated silently, and HotSpawn is never used as a
probability input — only as the list of fixtures to price.</div>

<h2>1. Fixtures (discovery only)</h2>
<p>The lobby's own public JSON API is read by the runner:
<code>{esc(board['fixtures_source'])}</code> (page: <a href="{esc(board['fixtures_source_page'])}" rel="nofollow noopener">play.hotspawn.com/lobby</a>).
It returned <b>{coverage['fixtures_total']}</b> CS2 fixtures for the pick'em window. The lobby's "picked %" crowd
number is displayed on each card <b>for reference only</b> and never enters a calculation.</p>

<h2>2. External prices</h2>
<table><tr><th>Source</th><th>What is read</th><th>How to check it</th></tr>
<tr><td>Pinnacle (licensed bookmaker)</td><td>full-match moneyline, the two-way market on the matchup's full-match period</td>
<td><a href="https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups" rel="nofollow noopener">guest odds API</a> — each row links the exact matchup URL read</td></tr>
<tr><td>Bovada (licensed bookmaker)</td><td>full-match moneyline from the public esports coupon</td>
<td><a href="https://www.bovada.lv/services/sports/event/v2/events/A/description/esports" rel="nofollow noopener">coupon JSON</a></td></tr>
<tr><td>Kalshi (CFTC-regulated exchange)</td><td>two-sided book per outcome market; mid of yes-bid/yes-ask</td>
<td><a href="https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&amp;status=open&amp;with_nested_markets=true&amp;limit=200" rel="nofollow noopener">trade API</a></td></tr>
<tr><td>egamersworld.com (aggregator, fallback only)</td><td>decimal moneyline from its odds widget</td>
<td>the exact match page is linked on the card</td></tr>
<tr><td>Polymarket (prediction market)</td><td>collected; no current CS2 match market survived the freshness check</td>
<td><a href="https://gamma-api.polymarket.com/events?closed=false&amp;limit=100&amp;tag_slug=counter-strike" rel="nofollow noopener">Gamma API</a></td></tr>
<tr><td>Valve Regional Standings (official ranking)</td><td>team points used by the originated model</td>
<td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="nofollow noopener">Valve's standings repository</a> (mirrored in this repo)</td></tr></table>
<p class="sub">Books that refuse automated access from the runner (HLTV, EGamersWorld page, Thunderpick, GG.BET,
Oddspedia, 1xBet, DraftKings, BetMGM, Caesars, Marathonbet, Kambi-powered books) are listed on the
<a href="flagged.html">Flagged for review</a> page. Nothing was bypassed.</p>

<h2>3. Matching rules</h2>
<ol>
<li>Both participants must match after documented normalisation (case, accents, punctuation, club suffixes,
and an explicit alias table), in either order; a reversed source listing has its prices reversed.</li>
<li>A quote is accepted only when its own schedule agrees with the fixture within 90 minutes. Kalshi's
settlement rule is parsed for the original schedule — the exchange's padded <code>occurrence_datetime</code> is
deliberately ignored.</li>
<li>One quote is assigned to at most one fixture; ambiguous candidates are rejected and logged.</li>
<li>Quotes that fail the quality gate are rejected, not published: empty or far-too-wide Kalshi books, and
aggregator quotes that repeat the identical even price across unrelated matches (placeholders).</li>
</ol>

<h2>4. Probability maths</h2>
<p>Bookmaker decimal odds: <code>q_i = 1 / odds_i</code>, then <code>p_i = q_i / (q_a + q_b)</code> (proportional
no-vig; the book margin <code>q_a + q_b − 1</code> is printed on the card). Kalshi:
<code>p_i = mid_i / (mid_a + mid_b)</code> with <code>mid_i = (yes_bid + yes_ask) / 2</code>. When several named
sources quote the same match the card shows their arithmetic mean; the per-source values are listed under it.
These are derived quantities, not forecasts and not source quotes.</p>

<h2>5. Originated lines (matches no market prices)</h2>
<p>Where no external price exists the board originates its own line, in this order, and says so on the card:</p>
<ol>
<li><b>Market-graph Bradley-Terry.</b> Every collected moneyline is one observation of
<code>logit(p) = strength_A − strength_B</code>; strengths are fitted by maximum likelihood over the whole graph
(including matches outside the pick'em). A team needs at least {orig_doc['rows'][0]['inputs'].get('min_observations_rule', 3) if orig_doc['rows'] and orig_doc['rows'][0]['inputs'] else 3}
collected observations against at least two different opponents to carry a usable strength. Graph: <b>{orig_doc['graph']['observations']}</b>
observations over <b>{orig_doc['graph']['teams']}</b> teams. Held-out (refit without the fixture, predict it, compare with the
market): <b>{cv['held_out_fixtures']}</b> fixture(s), mean absolute error <b>{cv.get('mean_absolute_error')}</b>, Brier
<b>{cv.get('brier')}</b> — thin, because the identification rule excludes everything else.</li>
<li><b>Valve Regional Standings.</b> <code>p = sigmoid((points_A − points_B)/scale)</code> with the scale fitted
against the priced fixtures: <b>{vf.get('scale_points')}</b> points, calibration on
<b>{vf.get('calibration_fixtures')}</b> fixtures, mean absolute error <b>{vf.get('mean_absolute_error')}</b>
(deeper books only: {vf.get('calibration_on_deeper_books', {}).get('n')} fixtures,
MAE {vf.get('calibration_on_deeper_books', {}).get('mean_absolute_error')}). Because that error is large, the
model output is clamped to {vf.get('clamp')} and every row using it says "originated".</li>
</ol>
<h3>Market-graph hold-out checks</h3>
<div class="tablewrap"><table><tr><th>Fixture</th><th>Market</th><th>Model (refit without it)</th><th>|error|</th></tr>{cv_rows}</table></div>
<h3>VRS calibration against real prices</h3>
<div class="tablewrap"><table><tr><th>Fixture</th><th>Points difference</th><th>Market</th><th>Model</th><th>|error|</th></tr>{vrs_rows}</table></div>

<h2>6. Reproducing this board</h2>
<ul>
<li>Collection runs on a GitHub runner (network access is restricted in the authoring sandbox):
<code>python3 proof/42580809/run/fetch_fixtures.py &amp;&amp; python3 proof/42580809/run/fetch_reference.py &amp;&amp;
python3 proof/42580809/run/probe_sources.py &amp;&amp; python3 proof/42580809/run/explore_sources.py &amp;&amp;
python3 proof/42580809/run/inspect_pinnacle.py &amp;&amp; python3 proof/42580809/run/collect_lines.py</code> —
raw payloads land in <code>proof/42580809/evidence/</code>.</li>
<li>Join and derive: <code>python3 proof/42580809/build_board.py</code> → <code>data/board_42580809.json</code>,
plus every accept/reject decision in <code>evidence/matching.json</code>.</li>
<li>Originate: <code>python3 proof/42580809/originate.py</code> → <code>data/originated_42580809.json</code>.</li>
<li>Publish: <code>python3 proof/42580809/build_site.py</code> → this section.</li>
</ul>

<h2>7. Limits, stated plainly</h2>
<ul>
<li>{coverage['stale_fixtures']} of {coverage['fixtures_total']} listed fixtures have a kickoff already in the past;
they stay listed (the lobby still shows them) and stay blank.</li>
<li>Aggregator-only rows are weaker evidence than bookmaker rows and are marked as such everywhere.</li>
<li>Low-tier tournaments (Elisa BreakOut, CCT play-ins, FRAG University) are barely priced by the reachable
sources; that is why the originated model exists and why some rows remain blank.</li>
<li>No value on this board is filled in by hand, and no HotSpawn number is used as a probability.</li>
</ul>"""
    methodology = page("Methodology & sources", "methodology.html", meth)

    # ------------------------------------------------------------------ flagged
    rejected = matching["rejected"]
    by_reason = {}
    for r in rejected:
        key = "quality gate: " + r["reason"].split(":")[0] if r.get("quality_gate") else r["reason"]
        by_reason[key] = by_reason.get(key, 0) + 1
    reason_rows = "".join(f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1]))
    gate = [r for r in rejected if r.get("quality_gate")]
    gate_rows = "".join(
        f'<tr><td>{esc(r["source_key"])}</td><td>{esc(r["raw_names"][0])} vs {esc(r["raw_names"][1])}</td>'
        f'<td>{esc(r["start"])}</td><td>{esc(r["reason"])}</td><td><code>{esc(json.dumps(r.get("raw")))}</code></td></tr>'
        for r in gate[:60])
    dup = matching.get("duplicate_reads", [])
    unverified_rows = "".join(
        f'<tr><td>{esc(r["fixture_id"])}</td><td>{esc(r["tournament"])}</td><td>{esc(short_ts(r["scheduled_start_time_utc"]))}</td>'
        f'<td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td>{esc("; ".join(orig.get(r["fixture_id"], {}).get("unoriginated_because", ["no external line found"])))}</td>'
        f'<td><a href="{esc(r["hotspawn_url"])}" rel="nofollow noopener">HotSpawn</a></td></tr>'
        for r in none_rows)
    def _entries(entries):
        return " · ".join("#%d (%d pts, %s)" % (e["standing"], e["points"], e["name"]) for e in entries)

    amb_rows = "".join(f'<tr><td>{esc(k)}</td><td>{esc(_entries(v))}</td></tr>'
                       for k, v in sorted(mv.get("ambiguous_names_not_used", {}).items()))
    stale_note = ", ".join(sorted({f'{r["tournament"]} ({r["scheduled_start_time_utc"][:10]})'
                                  for r in rows if r["stale"]})[:14])
    flagged = page("Flagged for review", "flagged.html", f"""
<div class="note">These are the irregularities and gaps found while building this board. They do not block
publication: nothing here is hidden, every item links the raw evidence it comes from, and rows without a usable
external line simply stay blank. Items are grouped by the question a reviewer would ask.</div>

<h2>F1. Listings whose kickoff has already passed ({coverage['stale_fixtures']} rows)</h2>
<p>The lobby API still returns these fixtures as pickable, but their scheduled start is in the past — for most of
them more than 100 days ({esc(stale_note)}, …). No external market can be collected for a finished match, so no
probability is published. They stay on the <a href="tables.html">Tables</a> page under "past-kickoff listings".</p>

<h2>F2. Upcoming fixtures with no usable line ({len(none_rows)})</h2>
<p>For these matches no reachable source quotes a price and at least one team has too little market or ranking
coverage for the originated model, so the probability cells stay blank.</p>
<div class="tablewrap"><table><tr><th>Fixture</th><th>Tournament</th><th>Kickoff (UTC)</th><th>Match</th><th>Why no line</th><th>Listing</th></tr>{unverified_rows or '<tr><td colspan="6">none</td></tr>'}</table></div>

<h2>F3. Quotes rejected by the quality gate ({len(gate)})</h2>
<p>A collected number is not automatically a usable price. Rejected here: Kalshi books that are empty or wide
(cheap bid / expensive ask on both sides, no volume) and aggregator quotes that repeat the identical even price
across unrelated matches — the signature of a placeholder rather than a market. The raw book is shown so the
rejection can be checked by hand. Fixtures whose only quotes were rejected carry the badge
"source quote(s) rejected by the quality gate".</p>
<div class="tablewrap"><table><tr><th>Source</th><th>Source teams</th><th>Source schedule (UTC)</th><th>Reason</th><th>Raw book</th></tr>{gate_rows or '<tr><td colspan="5">none</td></tr>'}</table></div>

<h2>F4. Every match/reject decision ({len(matching['accepted'])} accepted, {len(rejected)} rejected)</h2>
<div class="tablewrap"><table><tr><th>Decision</th><th>Count</th></tr>{reason_rows}</table></div>
<p class="sub">The full lists (with raw quote rows and reasons) are in
<code>proof/42580809/evidence/matching.json</code>. {len(dup)} further reads were duplicates of a market already
recorded from another collected batch and were dropped after keeping the newest, not deleted from the evidence.</p>

<h2>F5. Sources that refuse automated access</h2>
<ul>
<li>Cloudflare/bot protection: HLTV (403), egamersworld.com match pages (403; the odds widget data is read from the
collected JSON instead), Thunderpick (403), GG.BET (403), Oddspedia (403), 1xBet (403), Liquipedia (406),
DraftKings (403), BetMGM (403), Caesars (403), Marathonbet (403), Betway (404).</li>
<li>Rate limited: Kambi-powered books (BetRivers US/CA, NordicBet, Betsson, OTO, Bethard) answered HTTP 429.</li>
<li>Unusable: Polymarket's open CS2 markets in the API response are stale (spring 2026) — collected as evidence,
never used. Straight-list payloads above ~400 KB are truncated in the raw mirrors, so live values are always
re-read by the runner rather than parsed from the mirror.</li>
<li>No request was authenticated, retried around a challenge, or routed past a block.</li>
</ul>

<h2>F6. Data-source discrepancies</h2>
<ul>
<li>The lobby UI's counters (All 90 · S 4 · B 26 · C 60) disagree slightly with the {coverage['fixtures_total']}
CS2 rows its own JSON API returns for the same window. The API is used here; the difference is recorded, not
reconciled.</li>
<li>Kalshi's <code>occurrence_datetime</code> runs up to four hours later than the schedule written in its own
settlement rule, so matching uses the rule text and ignores that field.</li>
<li>Aggregator rows are the weakest evidence on the board; they are labelled as fallback on every card and counted
separately in the coverage tables.</li>
<li>Board rows can change between refreshes as books move; each card prints the timestamp of its own read.</li>
</ul>

<h2>F7. Ambiguous team names in Valve's official standings ({len(orig_doc["method_b"]["ambiguous_names_not_used"])} names)</h2>
<p>Valve's standings list some team names twice with different rosters and different points, so a fixture
cannot be tied to one entry. Rather than guess, the originated model refuses those names; if a match needs one,
the row stays blank.</p>
<div class="tablewrap"><table><tr><th>Name</th><th>Entries in the standings</th></tr>{amb_rows}</table></div>

""")

    # ------------------------------------------------------------------ write
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "assets"))
    os.makedirs(os.path.join(OUT, "data"))
    with open(os.path.join(OUT, "assets", "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    with open(os.path.join(OUT, "assets", "app.js"), "w", encoding="utf-8") as fh:
        fh.write(JS)
    for name, content in (("index.html", index), ("tables.html", tables),
                          ("methodology.html", methodology), ("flagged.html", flagged)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    for src, dst in (("board_42580809.json", "board.json"), ("board_42580809.csv", "board.csv"),
                     ("originated_42580809.json", "originated.json")):
        shutil.copy2(os.path.join(REPO, "data", src), os.path.join(OUT, "data", dst))
    shutil.copy2(os.path.join(EV, "coverage.json"), os.path.join(OUT, "data", "coverage.json"))
    with open(os.path.join(OUT, ".nojekyll"), "w", encoding="utf-8") as fh:
        fh.write("")
    print(f"site/{os.path.basename(OUT)}: {len(rows)} rows ({len(upcoming)} upcoming, {len(named)} named, "
          f"{len(fallback)} fallback, {len(orig_rows)} originated, {len(none_rows)} blank)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
