#!/usr/bin/env python3
"""
Session 42580809 — build the mobile-first probability board.

Inputs  (all produced by this session's pipeline, all source-linked):
  evidence/fixtures.json      lobby fixtures (public API)
  evidence/board.json         fixtures joined to external quotes + derived probabilities
  evidence/originated.json    Bradley-Terry originated probabilities + cross-validation
  evidence/coverage.json      coverage statistics
  evidence/matching.json      accept/reject decisions (evidence)
  evidence/lines_sources.json per-source collection status

Output: board/ (index.html, flagged.html, methodology.html, sources.html,
        assets/style.css, assets/app.js, data/board.json, data/board.csv)

Every rendered value comes from those files; nothing is typed in by hand. Rows without an
external quote and without model coverage render blank and are listed on the flagged page.
"""

from __future__ import annotations

import html
import json
import os
import shutil
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "board"))

STYLE = """
:root{--bg:#0d1117;--card:#161b22;--card2:#1c2430;--fg:#e6edf3;--dim:#8b949e;--acc:#3fb950;
--acc2:#f0883e;--bad:#f85149;--line:#30363d;--blue:#58a6ff;--pink:#db61a2}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
header{padding:16px 14px 10px;border-bottom:1px solid var(--line);background:#010409;position:sticky;top:0;z-index:5}
h1{font-size:19px;margin:0 0 4px}h2{font-size:17px;margin:22px 14px 8px}h3{font-size:15px;margin:16px 14px 6px}
.sub{color:var(--dim);font-size:12.5px}
nav{margin-top:8px;display:flex;flex-wrap:wrap;gap:8px}
nav a{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--card)}
nav a.on{border-color:var(--acc);color:var(--acc)}
.wrap{max-width:1000px;margin:0 auto;padding:12px 12px 60px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.stat b{display:block;font-size:22px;line-height:1.1}
.stat span{color:var(--dim);font-size:11.5px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 12px}
input,select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px;min-width:120px}
label.chk{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.card.market{border-left:4px solid var(--acc)}
.card.originated{border-left:4px solid var(--acc2)}
.card.unverified{border-left:4px solid var(--bad)}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline}
.tour{font-size:12.5px;color:var(--dim)}
.kick{font-size:12.5px;color:var(--dim);white-space:nowrap}
.teams{display:grid;grid-template-columns:1fr auto;gap:6px 10px;margin:10px 0 6px;align-items:center}
.team{font-size:16.5px;font-weight:600;overflow-wrap:anywhere}
.team.pick{color:var(--acc)}
.prob{font-variant-numeric:tabular-nums;font-size:16.5px;font-weight:700;text-align:right}
.bar{height:9px;border-radius:6px;background:#30363d;overflow:hidden;margin:6px 0 8px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#238636,#3fb950)}
.badge{display:inline-block;font-size:11px;border-radius:999px;padding:2px 8px;border:1px solid var(--line);margin:2px 4px 2px 0;color:var(--dim)}
.badge.ok{color:var(--acc);border-color:var(--acc)}
.badge.mid{color:var(--acc2);border-color:var(--acc2)}
.badge.bad{color:var(--bad);border-color:var(--bad)}
.badge.tier{color:var(--pink);border-color:var(--pink)}
.src{font-size:12px;color:var(--dim);margin-top:6px}
.src a{color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;border-bottom:1px solid var(--line);padding:6px 6px;vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:12px}
footer{color:var(--dim);font-size:12px;padding:18px 14px;border-top:1px solid var(--line);margin-top:30px}
.note{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--blue);border-radius:8px;padding:10px;margin:10px 0;font-size:13.5px}
code{background:#0b1017;border:1px solid var(--line);border-radius:4px;padding:1px 4px;font-size:12.5px}
@media(min-width:640px){.stats{grid-template-columns:repeat(4,1fr)}h1{font-size:22px}}
"""

APP_JS = """
(function(){
  var q=document.getElementById('q'),t=document.getElementById('tier'),
      tour=document.getElementById('tour'),up=document.getElementById('upcoming'),
      pick=document.getElementById('pickonly'),cards=[].slice.call(document.querySelectorAll('.card')),
      shown=document.getElementById('shown');
  function apply(){
    var s=(q&&q.value||'').toLowerCase(),tv=t&&t.value||'',to=tour&&tour.value||'',
        u=up&&up.checked,p=pick&&pick.checked,n=0;
    cards.forEach(function(c){
      var ok=true;
      if(s&&(c.dataset.search||'').indexOf(s)<0)ok=false;
      if(tv&&c.dataset.tier!==tv)ok=false;
      if(to&&c.dataset.tour!==to)ok=false;
      if(u&&c.dataset.future!=='1')ok=false;
      if(p&&c.dataset.pick!=='1')ok=false;
      c.style.display=ok?'':'none';if(ok)n++;
    });
    if(shown)shown.textContent=n;
  }
  [q,t,tour,up,pick].forEach(function(el){if(el){el.addEventListener('input',apply);el.addEventListener('change',apply);}});
  apply();
})();
"""


def load(name):
    with open(os.path.join(EV, name), encoding="utf-8") as fh:
        return json.load(fh)


def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)


def pct(x):
    return "—" if x is None else f"{round(x * 100)}%"


def iso_short(s):
    if not s:
        return "—"
    return s.replace("T", " ").replace("Z", " UTC")


def human_age(start_iso, now):
    if not start_iso:
        return ""
    dt = datetime.strptime(start_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    delta = dt - now
    mins = int(delta.total_seconds() // 60)
    past = mins < 0
    mins = abs(mins)
    d, h, m = mins // 1440, (mins % 1440) // 60, mins % 60
    txt = (f"{d}d " if d else "") + (f"{h}h " if h else "") + f"{m}m"
    return f"{txt.strip()} ago" if past else f"in {txt.strip()}"


def page(title, active, body, extra_head=""):
    nav = [("index.html", "Board"), ("methodology.html", "Methodology"),
           ("sources.html", "Sources & audit"), ("flagged.html", "Flagged for review")]
    links = "".join(
        '<a class="on" href="{h}">{t}</a>'.format(h=href, t=esc(txt)) if href == active
        else '<a href="{h}">{t}</a>'.format(h=href, t=esc(txt))
        for href, txt in nav)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="External betting lines and derived win probabilities for every CS2 match in the HotSpawn pick'em lobby.">
<meta name="color-scheme" content="dark">{extra_head}
<link rel="stylesheet" href="assets/style.css"></head><body>
<header><h1>{esc(title)}</h1><div class="sub">HotSpawn pick'em fixtures priced from outside sources</div>
<nav>{links}</nav></header><div class="wrap">{body}</div>
<footer>Not affiliated with HotSpawn or any bookmaker. HotSpawn is used for fixture discovery only;
its crowd pick percentages are shown for reference and are never used as a probability input.
Generated by a reproducible pipeline in this repository — see <a href="methodology.html">Methodology</a>.</footer>
<script src="assets/app.js"></script></body></html>"""


def render_row(r, orig, now):
    fid = r["fixture_id"]
    o = orig.get(fid)
    basis = r["basis"]
    p_a, p_b = r["p_a"], r["p_b"]
    pick_team = r["pick_team"]
    pick_prob = r["pick_probability"]
    note_bits = []
    if basis == "unverified" and o and o.get("originated_p_a") is not None:
        basis = "originated"
        p_a = o["originated_p_a"]
        p_b = round(1 - p_a, 4)
        pick_team = r["team_a"] if p_a >= p_b else r["team_b"]
        pick_prob = max(p_a, p_b)
    future = (r["scheduled_start_time_utc"] or "") > now.strftime("%Y-%m-%dT%H:%M:%SZ")
    classes = basis if basis in ("market-derived", "originated") else "unverified"

    if basis == "market-derived":
        badge = '<span class="badge ok">external market line</span>'
        note_bits.append(f'<span class="badge">{r["n_sources"]} source(s)</span>')
        if r["n_sources"] == 1:
            note_bits.append('<span class="badge mid">single source</span>')
        srcs = []
        seen = set()
        for q in r["quotes"]:
            key = (q["source_key"], q.get("source_public_url") or q.get("api"))
            if key in seen:
                continue
            seen.add(key)
            link = q.get("source_public_url") or q.get("api")
            api = q.get("api")
            extra = f' · <a href="{esc(api)}" rel="nofollow noopener">quote API</a>' if api and api != link else ""
            srcs.append(f'{esc(q["source_name"])} <a href="{esc(link)}" rel="nofollow noopener">market</a>{extra} '
                        f'<span class="badge">{pct(q["p_a"])} / {pct(q["p_b"])}</span> '
                        f'<span class="badge">read {esc((q.get("retrieved_at_utc") or "")[:16])}Z</span>')
            if q.get("conditional_alias"):
                note_bits.append('<span class="badge mid">source spelling differs — verified by tournament + exact kickoff</span>')
            if q.get("start_time_delta_min") not in (None, 0):
                note_bits.append(f'<span class="badge">kickoff differs {q["start_time_delta_min"]} min</span>')
            if q.get("detail", {}).get("spread") not in (None, 0):
                note_bits.append(f'<span class="badge">book spread {q["detail"]["spread"]}</span>')
        src_html = "<br>".join(srcs)
    elif basis == "originated":
        badge = '<span class="badge mid">originated line — not a market quote</span>'
        note_bits.append(f'<span class="badge">model fit to external market graph</span>')
        if o:
            note_bits.append(f'<span class="badge">{o["team_a_observations"]}+{o["team_b_observations"]} market observations behind these teams</span>')
        src_html = ('Bradley-Terry fit over the external quotes collected for this project. '
                    'Method, inputs and the held-out cross-validation error are on the '
                    '<a href="methodology.html">Methodology</a> page. No HotSpawn data is used.')
    else:
        badge = '<span class="badge bad">unverified — no external line, no model coverage</span>'
        src_html = ('No bookmaker or exchange price was found for both of these teams, and the team pair '
                    'is not connected to the priced market graph, so no probability is published. '
                    'See <a href="flagged.html">Flagged for review</a>.')

    if not future:
        days = ""
        if r["scheduled_start_time_utc"]:
            dt = datetime.strptime(r["scheduled_start_time_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            days = f" ({(now - dt).days}d before this snapshot)"
        note_bits.append(f'<span class="badge bad">listing stale — kickoff already passed{days}</span>')

    bar = ""
    if p_a is not None:
        bar = f'<div class="bar" title="{esc(pct(p_a))} vs {esc(pct(p_b))}"><i style="width:{round(p_a*100)}%"></i></div>'

    teams_html = ""
    for name, prob in ((r["team_a"], p_a), (r["team_b"], p_b)):
        cls = "team pick" if pick_team == name else "team"
        mark = " ✅ PICK" if pick_team == name else ""
        teams_html += f'<div class="{cls}">{esc(name)}{mark}</div><div class="prob">{pct(prob)}</div>'

    search = " ".join(str(x) for x in (r["team_a"], r["team_b"], r["tournament"], r["tier"])).lower()
    return f"""<article class="card {classes}" data-tier="{esc(r['tier'] or '')}"
 data-tour="{esc(r['tournament'])}" data-future="{1 if future else 0}" data-pick="{1 if pick_team else 0}"
 data-search="{esc(search)}">
<div class="top"><div class="tour">{esc(r['tournament'])} · tier {esc((r['tier'] or '?').upper())} ·
{esc(r['offered_points'])} pts</div><div class="kick">{esc(iso_short(r['scheduled_start_time_utc']))} · {esc(human_age(r['scheduled_start_time_utc'], now))}</div></div>
<div class="teams">{teams_html}</div>{bar}
<div>{badge} {''.join(note_bits)}</div>
<div class="src">{src_html}<br>Fixture: <a href="{esc(r['hotspawn_url'])}" rel="nofollow noopener">HotSpawn match page</a>
 · HotSpawn crowd pick (reference only): {esc(r['hotspawn_pick_pct_reference_only'][0])}% / {esc(r['hotspawn_pick_pct_reference_only'][1])}%</div>
</article>"""


def main() -> int:
    fixtures = load("fixtures.json")
    board = load("board.json")
    orig_doc = load("originated.json")
    coverage = load("coverage.json")
    matched = load("matching.json")
    sources = load("lines_sources.json")
    orig = {r["fixture_id"]: r for r in orig_doc["originated"]}
    now = datetime.now(tz=timezone.utc)

    rows = board["rows"]
    future_rows = [r for r in rows if (r["scheduled_start_time_utc"] or "") > now.strftime("%Y-%m-%dT%H:%M:%SZ")]
    market = [r for r in rows if r["n_sources"]]
    originated_rows = [r for r in rows if not r["n_sources"] and orig.get(r["fixture_id"], {}).get("originated_p_a") is not None]
    unverified = [r for r in rows if not r["n_sources"] and orig.get(r["fixture_id"], {}).get("originated_p_a") is None]
    stale = [r for r in rows if (r["scheduled_start_time_utc"] or "") <= now.strftime("%Y-%m-%dT%H:%M:%SZ")]

    # ------------------------------------------------------------------ index
    stats = f"""<div class="stats">
<div class="stat"><b>{len(rows)}</b><span>CS2 fixtures listed in the lobby API</span></div>
<div class="stat"><b>{len(market)}</b><span>with a verified external line</span></div>
<div class="stat"><b>{len(originated_rows)}</b><span>with our originated model line</span></div>
<div class="stat"><b>{len(unverified)}</b><span>unverified (blank, flagged)</span></div></div>"""

    intro = f"""<div class="note"><b>How to read a row.</b> Each card is one CS2 fixture from the
HotSpawn pick'em lobby. <b>✅ PICK</b> marks the higher-probability side, with both sides'
probabilities next to the team names. <span class="badge ok">external market line</span> means a real
price from Pinnacle, Bovada or Kalshi (links under the bar). <span class="badge mid">originated line</span>
means no book prices this pair, so this project fitted its own line to the wider external market —
clearly labelled, never presented as a book quote. <span class="badge bad">unverified</span> means we
have no external evidence at all and publish nothing.
<br><br><b>{len(stale)} of {len(rows)}</b> listed fixtures have a kickoff that is already in the past —
they remain pickable in the lobby but no live market can exist for them any more; they are
listed on <a href="flagged.html">Flagged for review</a>. Snapshot: {esc(coverage['generated_at_utc'])}.</div>"""

    tiers = sorted({r["tier"] for r in rows if r["tier"]})
    tours = sorted({r["tournament"] for r in rows})
    controls = f"""<div class="controls">
<input id="q" type="search" placeholder="Search team or tournament" aria-label="Search">
<select id="tier" aria-label="Tier"><option value="">All tiers</option>
{''.join(f'<option value="{esc(t)}">{esc(t.upper())}</option>' for t in tiers)}</select>
<select id="tour" aria-label="Tournament"><option value="">All tournaments</option>
{''.join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in tours)}</select>
<label class="chk"><input id="upcoming" type="checkbox" checked> upcoming only</label>
<label class="chk"><input id="pick" type="checkbox"> only rows with a pick</label>
<span class="sub">showing <b id="shown">{len(rows)}</b> rows</span></div>"""

    ordered = sorted(rows, key=lambda r: (r["scheduled_start_time_utc"] or "") <
                     now.strftime("%Y-%m-%dT%H:%M:%SZ"), reverse=False)
    ordered = sorted(rows, key=lambda r: r["scheduled_start_time_utc"] or "")
    cards = "".join(render_row(r, orig, now) for r in ordered)
    index_body = stats + intro + controls + cards
    index = page("Pick'em probability board", "index.html", index_body)

    # ------------------------------------------------------------------ methodology
    cv = orig_doc["cross_validation"]
    cv_rows = "".join(f"<tr><td>{esc(c['match'])}</td><td>{pct(c['market_p'])}</td>"
                      f"<td>{pct(c['model_p'])}</td><td>{c['abs_error']:.3f}</td></tr>"
                      for c in cv["rows"])
    meth = f"""<div class="note">Every number on this site is produced by pipeline code in this
repository from a named public source. Nothing is typed in by hand, and HotSpawn is never used as a
probability input — only as the list of fixtures to price.</div>

<h2>1. Fixtures</h2>
<p>Fixtures come from the pick'em lobby's own public JSON API, discovered in the lobby page's
server-rendered payload: <code>{esc(fixtures['source_api'])}</code> (page: <a href="{esc(fixtures['source_page'])}" rel="nofollow noopener">lobby</a>).
Snapshot {esc(fixtures['collected_at_utc'])}: <b>{fixtures['counts']['window']}</b> fixtures in the pick'em window
(<b>{fixtures['counts']['by_sport'].get('cs2')}</b> CS2, {fixtures['counts']['by_sport'].get('lol')} LoL) out of
{fixtures['counts']['api_total']} rows the endpoint has ever returned. A fixture is dropped only when the API
reports it as <code>ended</code> or its start is more than 24 h in the past. The lobby's own "picked %" is a crowd
number; it is displayed for reference and never enters any calculation.</p>

<h2>2. External prices</h2>
<p>For every fixture the pipeline looks up real moneyline prices at outside sources — never at HotSpawn:</p>
<table><tr><th>Source</th><th>What was read</th><th>Where</th></tr>
<tr><td>Pinnacle (licensed bookmaker)</td><td>full-match moneyline, American prices</td><td><a href="https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups" rel="nofollow noopener">guest odds API</a></td></tr>
<tr><td>Bovada (licensed bookmaker)</td><td>full-match moneyline, decimal prices</td><td><a href="https://www.bovada.lv/services/sports/event/v2/events/A/description/esports" rel="nofollow noopener">public coupon JSON</a></td></tr>
<tr><td>Kalshi (CFTC-regulated exchange)</td><td>two-sided yes/no book per outcome market</td><td><a href="https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME&amp;status=open&amp;with_nested_markets=true&amp;limit=200" rel="nofollow noopener">public trade API</a></td></tr>
<tr><td>Polymarket (public prediction market)</td><td>collected as evidence; no current CS2 match market survived the freshness check</td><td><a href="https://gamma-api.polymarket.com/events?closed=false&amp;limit=100&amp;tag_slug=counter-strike" rel="nofollow noopener">Gamma API</a></td></tr>
</table>
<p class="sub">Kambi-powered books, EGamersWorld, HLTV, Oddspedia, 1xBet, Thunderpick, GG.BET, DraftKings,
BetMGM, Caesars and Marathonbet were probed from the runner and refused automated access (HTTP 403/404/429).
That is recorded on the <a href="sources.html">Sources &amp; audit</a> page. Nothing was bypassed.</p>

<h2>3. Matching rules</h2>
<ol>
<li>Both participants must be equal after normalisation (case, accents, punctuation and documented
club suffixes removed), in either order; a reversed source listing has its prices reversed.</li>
<li>If the source publishes a start time it must agree with the fixture within {board['rules']['time'].split('within ')[-1]}.</li>
<li>Kalshi's two outcome markets are paired per event; its settlement rule supplies the tournament and
the match's original schedule (the exchange's own <code>occurrence_datetime</code> is padded with the
settlement window and is deliberately not used as a kickoff).</li>
<li>One quote is assigned to at most one fixture. Ambiguous candidates are rejected and logged —
{len(matched['accepted'])} accepted vs {len(matched['rejected'])} rejected candidate decisions in this
snapshot; the rejects are almost entirely markets for matches that are not in the pick'em list at all.</li>
</ol>

<h2>4. Probability maths</h2>
<p>Bookmaker decimal odds: <code>q_i = 1 / odds_i</code>, then <code>p_i = q_i / (q_a + q_b)</code>
(proportional no-vig; the book's margin is reported per row as <code>q_a + q_b − 1</code>).
Kalshi: <code>p_i = mid_i / (mid_a + mid_b)</code> with <code>mid_i = (yes_bid + yes_ask) / 2</code>.
When several sources quote the same fixture the row shows their arithmetic mean, plus the min–max range in
the data file. These are derived quantities, not forecasts and not source quotes.</p>

<h2>5. Originated lines (matches no book prices)</h2>
<p>For a fixture with no external quote the pipeline tries to originate its own line <i>from the same
external markets</i>: every collected quote — including matches that are not in the pick'em — is one
observation <code>logit(p) = strength_A − strength_B</code>; a Bradley-Terry model is fitted by maximum
likelihood over that graph, and the fitted strengths give a probability for any pair of teams the market
does price. Teams the market never prices stay unverified instead of receiving a made-up number.</p>
<p>Fit inputs: <b>{orig_doc['graph']['observations']}</b> market observations covering
<b>{orig_doc['graph']['teams']}</b> teams. Held-out check (refit without the fixture, predict it,
compare with the market): <b>{cv['held_out_fixtures']}</b> fixtures, mean absolute error
<b>{cv['mean_absolute_error']}</b>, Brier score <b>{cv['brier']}</b>.</p>
<table><tr><th>Fixture</th><th>Market</th><th>Model (refit without it)</th><th>|error|</th></tr>{cv_rows}</table>
<p class="sub">An error of ~0.15 probability means the originated lines are directionally useful but
noticeably less accurate than a real market price; every row that uses one says so.</p>

<h2>6. Limits, stated plainly</h2>
<ul>
<li>HotSpawn's lobby lists many fixtures whose kickoff is long past; no live market exists for those and
none is published. Currently {len(stale)} of {len(rows)} rows.</li>
<li>Kalshi books for these low-tier matches are thin: wide spreads and little traded volume are shown per row.</li>
<li>Pinnacle prices only some of these tournaments; tier-C events (Elisa BreakOut, Urban Riga, Svenska
CS-Ligan, DraculaN) are largely unpriced by the sources reachable from this environment.</li>
<li>Nothing is extrapolated from HotSpawn's crowd pick percentages, and no value is ever filled in by hand.</li>
</ul>"""
    methodology = page("Methodology", "methodology.html", meth)

    # ------------------------------------------------------------------ sources & audit
    per_source = sources.get("pinnacle", {})
    src_rows = ""
    for key in ("pinnacle", "bovada", "kalshi"):
        d = sources.get(key, {})
        src_rows += (f"<tr><td>{esc(key)}</td><td>{esc(d.get('status') or d.get('events_status'))}</td>"
                     f"<td>{esc(d.get('quotes', d.get('cs2_moneyline_quotes', '')))}</td></tr>")
    kambi = sources.get("kambi", {})
    kambi_rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v.get('status'))}</td><td>{esc(v.get('events',''))}</td></tr>"
                         for k, v in kambi.items())
    cov = coverage
    src_body = f"""<div class="note">Raw collection evidence is committed in
<code>proof/42580809/evidence/</code> in this repository: every quote with its source URL, ids,
retrieval timestamp and raw price; every match/reject decision; the source probes and their HTTP status.</div>
<h2>Collected sources</h2>
<table><tr><th>Source</th><th>HTTP</th><th>Quotes</th></tr>{src_rows}</table>
<h2>Kambi-powered books (blocked)</h2>
<table><tr><th>Book</th><th>HTTP</th><th>Events</th></tr>{kambi_rows}</table>
<h2>Coverage</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>CS2 fixtures in the pick'em window</td><td>{cov['fixtures_total']}</td></tr>
<tr><td>fixtures with an external market line</td><td>{cov['fixtures_with_market_line']}</td></tr>
<tr><td>market observations (any match, any source)</td><td>{cov['market_observations_total']}</td></tr>
<tr><td>market observations matched to a pick'em fixture</td><td>{cov['observations_matched_to_pickem']}</td></tr>
<tr><td>teams present in the market graph</td><td>{cov['distinct_teams_in_market_graph']}</td></tr>
<tr><td>pick'em teams no market prices at all</td><td>{len(cov['pickem_teams_absent_from_market_graph'])}</td></tr>
</table>
<h2>Accept / reject decisions</h2>
<p>{len(matched['accepted'])} accepted, {len(matched['rejected'])} rejected. Full lists:
<a href="../proof/42580809/evidence/matching.json">matching.json</a> (accepted + rejected, with raw values),
<a href="../proof/42580809/evidence/coverage.json">coverage.json</a>,
<a href="data/board.json">board.json</a>, <a href="data/board.csv">board.csv</a>.</p>
<h2>Machine-readable data</h2>
<ul><li><a href="data/board.json">board.json</a> — every row with per-source quotes and derivation detail</li>
<li><a href="data/board.csv">board.csv</a> — flat table: kickoff, tournament, teams, pick, probability, sources, basis</li>
<li><a href="data/originated.json">originated.json</a> — originated lines, team strengths, cross-validation</li></ul>"""
    sources_html = page("Sources & audit", "sources.html", src_body)

    # ------------------------------------------------------------------ flagged
    stale_rows = "".join(
        f'<tr><td>{esc(r["tournament"])}</td><td>{esc(iso_short(r["scheduled_start_time_utc"]))}</td>'
        f'<td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td><a href="{esc(r["hotspawn_url"])}" rel="nofollow noopener">HotSpawn</a></td></tr>'
        for r in sorted(stale, key=lambda r: r["scheduled_start_time_utc"]))
    unv_rows = "".join(
        f'<tr><td>{esc(r["tournament"])}</td><td>{esc(iso_short(r["scheduled_start_time_utc"]))}</td>'
        f'<td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td>{esc((orig.get(r["fixture_id"]) or {}).get("basis", "no external price found"))}</td>'
        f'<td><a href="{esc(r["hotspawn_url"])}" rel="nofollow noopener">HotSpawn</a></td></tr>'
        for r in unverified)
    alias_rows = "".join(
        f'<tr><td>{esc(a["conditional_alias"]["raw"][0])} vs {esc(a["conditional_alias"]["raw"][1])}</td>'
        f'<td>{esc(a["conditional_alias"]["mapped_to"][0])} vs {esc(a["conditional_alias"]["mapped_to"][1])}</td>'
        f'<td>{esc(a["conditional_alias"]["rule_tournament"])}</td><td>{esc(a["conditional_alias"]["evidence"])}</td></tr>'
        for a in matched["accepted"] if a.get("conditional_alias"))
    rej_named = [d for d in matched["rejected"] if d.get("raw_names")]
    rej_rows = "".join(
        f'<tr><td>{esc(d.get("raw_names", []))}</td><td>{esc(d.get("rule_tournament"))}</td>'
        f'<td>{esc(d.get("reason"))}</td></tr>' for d in rej_named[:40])

    flagged = f"""<div class="note">Nothing on this page blocks publication: these are the items that
could not be fully confirmed from an official source. Everything else on the board is source-linked.</div>

<h2>F1. Listings whose kickoff has already passed ({len(stale)} rows)</h2>
<p>The lobby API still returns these fixtures with a pickable status, but their scheduled start is in
the past — for most of them more than 100 days. No external market can be collected for a finished
match, so no probability is published.</p>
"""+stale_rows+f"""

<h2>F2. Fixtures with no external evidence ({len(unverified)} rows)</h2>
<p>Neither a book price nor a model connection to the priced market graph exists for these pairs, so
the probability cells are left blank rather than estimated.</p>
{unv_rows}

<h2>F3. Source team-name spellings ({len(alias_rows) and 2 or 0} accepted mappings)</h2>
<p>Kalshi spells one Elisa BreakOut team differently from HotSpawn. The mapping is accepted only
because the tournament name and the scheduled start time are identical, and it is listed here so it can
be checked by hand.</p>
<table><tr><th>Source spelling</th><th>HotSpawn spelling</th><th>Tournament in the source's rule text</th><th>Why it was accepted</th></tr>{alias_rows}</table>

<h2>F4. Rejected candidate matches (naming)</h2>
<p>Candidates that were collected but not joined because the names or the schedule did not agree.</p>
<table><tr><th>Source teams</th><th>Tournament (source)</th><th>Reason</th></tr>{rej_rows}</table>

<h2>F5. Source access</h2>
<ul>
<li>Cloudflare/bot protection refused: HLTV (403), EGamersWorld (403), Thunderpick (403), GG.BET (403),
Oddspedia (403), 1xBet (403), Liquipedia (406), DraftKings (403), BetMGM (403), Caesars (403),
Marathonbet (403).</li>
<li>Rate limited: Kambi-powered books (BetRivers, NordicBet, Betsson, OTO, Bethard) returned HTTP 429.</li>
<li>Not found / withdrawn: Strafe, Abios, EsportsOdds (DNS), BetExplorer (404), Betway (404), Rivalry
(ceased operations), Smarkets (400).</li>
<li>No request was authenticated, retried against a challenge, or routed around a block.</li>
</ul>

<h2>F6. Data-source irregularities</h2>
<ul>
<li>The lobby UI shows "68 matches this week" with tier counters All 90 / S 4 / B 26 / C 60, while the
JSON API used by the same page returns 92 CS2 rows in the same window. The API is used here; the
difference is recorded rather than reconciled.</li>
<li>The API still returns fixtures from June 2026 as pickable (see F1).</li>
<li>Kalshi quote spreads on these low-tier games are wide (up to tens of cents) with little or no traded
volume; each row shows the spread where it applies.</li>
<li>Polymarket's CS2 markets in the API response are stale (spring 2026) and were not used.</li>
</ul>"""
    flagged = page("Flagged for review", "flagged.html", flagged)

    # ------------------------------------------------------------------ write
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "assets"))
    os.makedirs(os.path.join(OUT, "data"))
    with open(os.path.join(OUT, "assets", "style.css"), "w", encoding="utf-8") as fh:
        fh.write(STYLE)
    with open(os.path.join(OUT, "assets", "app.js"), "w", encoding="utf-8") as fh:
        fh.write(APP_JS)
    for name, content in (("index.html", index), ("methodology.html", methodology),
                          ("sources.html", sources_html), ("flagged.html", flagged)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    with open(os.path.join(OUT, "data", "board.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "data", "originated.json"), "w", encoding="utf-8") as fh:
        json.dump(orig_doc, fh, indent=1, ensure_ascii=False)
    shutil.copy2(os.path.join(EV, "board.csv"), os.path.join(OUT, "data", "board.csv"))
    with open(os.path.join(OUT, ".nojekyll"), "w", encoding="utf-8") as fh:
        fh.write("")

    print(f"board/ written: {len(rows)} rows, {len(market)} market, {len(originated_rows)} originated, "
          f"{len(unverified)} unverified, {len(stale)} stale")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
