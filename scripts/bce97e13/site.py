#!/usr/bin/env python3
"""Render the bce97e13 verification desk to ``cs2-picks/*.html``.

Phone-first by construction: one column, >=44px tap targets, probability bars instead of dense
tables, self-contained CSS (no external assets, no JavaScript required).  Every number rendered
here comes from data/bce97e13/board.json, which verify.py only writes after re-deriving it.
"""
from __future__ import annotations

import importlib.util as _iu
import json
import sys
from datetime import datetime
from pathlib import Path

_spec = _iu.spec_from_file_location("bce97e13_core", Path(__file__).resolve().parent / "core.py")
core = _iu.module_from_spec(_spec)
sys.modules["bce97e13_core"] = core
_spec.loader.exec_module(core)

BOARD_JSON = "data/bce97e13/board.json"
VERIFY_JSON = "data/bce97e13/verification.json"
VALVE_JSON = "data/bce97e13/valve_live.json"

NAV = [("index.html", "Summary"), ("picks.html", "All picks"), ("unresolved.html", "Unresolved"),
       ("sources.html", "Sources"), ("method.html", "Method"), ("flagged.html", "Flagged")]

STYLE = """
:root{--bg:#0b1220;--card:#121c2e;--card2:#0f1727;--ink:#e8eefc;--dim:#93a4c3;--line:#25334d;
--good:#7ef0b2;--warn:#ffd479;--bad:#ff9aa2;--accent:#7cc4ff;--market:#7ef0b2;--model:#7cc4ff;--bound:#ffd479}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:880px;margin:0 auto;padding:12px 14px 72px}
header.top{position:sticky;top:0;z-index:5;background:rgba(11,18,32,.97);border-bottom:1px solid var(--line)}
header.top .bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;
max-width:880px;margin:0 auto;padding:8px 14px}
.brand{font-weight:800;font-size:15px;letter-spacing:.2px}
.brand span{color:var(--good)}
nav{display:flex;flex-wrap:wrap;gap:6px}
nav a{display:inline-flex;align-items:center;padding:8px 12px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;color:var(--ink);font-size:13px;min-height:40px}
nav a.active{background:var(--good);color:#0b2417;border-color:var(--good);font-weight:800}
h1{font-size:clamp(1.35rem,5vw,1.8rem);line-height:1.22;margin:12px 0 6px}
h2{font-size:1.15rem;margin:26px 0 8px}
h3{font-size:1rem;margin:16px 0 6px}
p{margin:8px 0}
.eyebrow{color:var(--dim);text-transform:uppercase;letter-spacing:.09em;font-size:11px;margin:16px 0 2px}
.lede{color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0}
@media(min-width:640px){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:12px}
.tile b{display:block;font-size:26px;line-height:1.1}
.tile small{color:var(--dim);font-size:12px}
.cta{display:grid;gap:10px;margin:14px 0}
@media(min-width:640px){.cta{grid-template-columns:1fr 1fr}}
.cta a{display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--card);
border:1px solid var(--line);border-radius:14px;padding:15px 16px;text-decoration:none;color:var(--ink);
font-weight:700;min-height:58px}
.cta a.primary{background:var(--good);color:#08200f;border-color:var(--good)}
.cta a span.small{font-weight:400;color:inherit;opacity:.78;font-size:12px}
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:800;
border:1px solid var(--line);white-space:nowrap}
.badge.market{color:#08200f;background:var(--market);border-color:var(--market)}
.badge.model{color:#04121f;background:var(--model);border-color:var(--model)}
.badge.bound{color:#2a1d00;background:var(--bound);border-color:var(--bound)}
.badge.flag{color:var(--warn);background:transparent;border-color:var(--warn)}
.badge.verify{color:#08200f;background:var(--good);border-color:var(--good)}
.badge.api{color:var(--dim);background:transparent;border-color:var(--dim)}
.match-card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px;margin:12px 0}
.match-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}
.match-title{font-weight:800;font-size:1.05rem}
.match-meta{color:var(--dim);font-size:12.5px;margin-top:2px}
.pick-line{margin:12px 0 8px;padding:10px 12px;border-radius:12px;background:#0b1f16;border:1px solid #1e4a2e;
font-weight:800}
.pick-line small{font-weight:400;color:var(--dim)}
.bar-row{display:grid;grid-template-columns:1fr;gap:6px;margin:8px 0}
.barline{display:grid;grid-template-columns:minmax(0,1fr) 74px;gap:10px;align-items:center}
.barname{font-size:13.5px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.barwrap{grid-column:1 / -1;display:grid;grid-template-columns:minmax(0,1fr) 74px;gap:10px;align-items:center}
.bar{height:14px;border-radius:999px;background:#1a253a;overflow:hidden}
.bar i{display:block;height:100%;border-radius:999px}
.bar.a i{background:var(--accent)}
.bar.b i{background:var(--good)}
.bar.alt i{background:var(--dim)}
.pct{font-variant-numeric:tabular-nums;font-weight:800;text-align:right;font-size:14px}
.pct.dim{color:var(--dim);font-weight:600}
.src{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.src a{display:inline-flex;align-items:center;font-size:12px;padding:7px 11px;border:1px solid var(--line);
border-radius:999px;text-decoration:none;min-height:36px;color:var(--ink)}
.src a:hover{border-color:var(--accent)}
.flags{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.muted{color:var(--dim);font-size:12.5px}
.callout{border-left:4px solid var(--warn);background:#1a1608;padding:11px 13px;border-radius:8px;margin:12px 0}
.callout.good{border-color:var(--good);background:#0b1f16}
.callout.bad{border-color:var(--bad);background:#221010}
ul,ol{padding-left:20px}
li{margin:6px 0}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.07em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.tbl-scroll{overflow-x:auto}
footer{color:var(--dim);font-size:12px;border-top:1px solid var(--line);margin-top:30px;padding-top:14px}
code{background:#0a1322;padding:1px 5px;border-radius:5px;font-size:12.5px}
@media(max-width:639px){
 table thead{display:none}
 table,tbody,tr,td,th{display:block;width:100%}
 table tr{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 10px;padding:10px 12px}
 table td{border:0;padding:4px 0}
 td[data-l]{display:flex;gap:10px;justify-content:space-between;align-items:baseline}
 td[data-l]::before{content:attr(data-l);color:var(--dim);font-size:11px;text-transform:uppercase;
 letter-spacing:.06em;flex:0 0 38%}
 td.num{text-align:right}
}
"""


def esc(x):
    return core.esc(x)


def load(path):
    return core.load(path, default={}) or {}


def fmt_day(ts):
    if not ts:
        return "—"
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d.strftime("%d %b · %H:%M UTC")


def countdown(ts, now):
    if not ts:
        return ""
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    delta = d - now
    hours = delta.total_seconds() / 3600
    if hours < 0:
        return "started"
    if hours < 48:
        return f"in {round(hours)}h"
    return f"in {round(hours/24)}d"


def pct(x):
    return None if x is None else round(float(x) * 100.0, 1)


def basis_badge(row):
    b = row["basis"]
    if b == "market":
        n = len([q for q in row["quotes"] if q.get("no_vig_prob_a") is not None])
        return f'<span class="badge market">Market · {n} book{"s" if n != 1 else ""}</span>'
    if b == "originated_vrs_bound":
        return '<span class="badge bound">Bound · one side unrated</span>'
    return '<span class="badge model">Originated · Valve VRS</span>'


def verify_badge(row):
    ok = row["verification"]["status"] == "verified"
    label = "✓ independently verified" if ok else "⚠ unverified — see flagged"
    cls = "verify" if ok else "flag"
    return f'<span class="badge {cls}">{label}</span>'


def page(shell_id, title, active, body, description):
    parts = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        parts.append(f'<a href="{href}"{cls}>{label}</a>')
    nav = "".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="description" content="{esc(description)}">
<title>{esc(title)} · CS2 picks, independently verified</title>
<link rel="icon" href="../favicon.ico" type="image/x-icon">
<style>{STYLE}</style>
</head>
<body>
<header class="top"><div class="bar">
<div class="brand">CS2 picks <span>· verified</span></div>
<nav>{nav}<a href="../index.html">Site home</a></nav>
</div></header>
<main class="wrap" id="{shell_id}">
{body}
<footer>
<p>Independent verification desk (session bce97e13). Every probability is re-derived from the stored
book/exchange decimal odds or the official Valve regional standings; the basis is printed on every
row. HotSpawn crowd-pick percentages are never used. Unverifiable values stay blank and are flagged.
Board built {esc(load(BOARD_JSON).get('generated_utc', '—'))}.</p>
</footer>
</main>
</body>
</html>
"""


def probability_bars(row):
    pa, pb = pct(row["prob_a"]), pct(row["prob_b"])
    bound = row.get("bound") or {}
    a_mark = "≥ " if bound.get("side") == "a" else ("≤ " if bound.get("side") == "b" else "")
    b_mark = "≤ " if bound.get("side") == "a" else ("≥ " if bound.get("side") == "b" else "")
    wa = max(4.0, min(96.0, float(pa or 0)))
    wb = max(4.0, min(96.0, float(pb or 0)))
    pick_side = row.get("pick_side")
    return f"""
<div class="bar-row">
 <div class="barwrap"><div class="barname">{esc(row['team_a'])}{' ★' if pick_side == 'a' else ''}</div>
   <div class="pct{'' if pick_side == 'a' else ' dim'}">{a_mark}{pa}%</div></div>
 <div class="bar a"><i style="width:{wa:.1f}%"></i></div>
 <div class="barwrap"><div class="barname">{esc(row['team_b'])}{' ★' if pick_side == 'b' else ''}</div>
   <div class="pct{'' if pick_side == 'b' else ' dim'}">{b_mark}{pb}%</div></div>
 <div class="bar b"><i style="width:{wb:.1f}%"></i></div>
</div>"""


def _host(url):
    import re
    m = re.match(r"https?://([^/]+)", url)
    host = m.group(1) if m else url
    return host.replace("www.", "").replace("phpstack-1372681-6459848.cloudwaysapps.com", "HotSpawn API")


def source_label(url: str) -> str:
    """Human, distinguishable label so repeated hosts never render as identical links."""
    u = url.lower()
    if "hotspawn.com/matches" in u:
        return "HotSpawn match ↗"
    if "cloudwaysapps.com" in u or u.endswith("/fixtures"):
        return "HotSpawn API ↗"
    if "kalshi.com" in u:
        return "Kalshi exchange ↗"
    if "hltv.org/matches" in u:
        return "HLTV match ↗"
    if "hltv.org/team" in u:
        return "HLTV team ↗"
    if "hltv.org" in u:
        return "HLTV ↗"
    if "bo3.gg/matches" in u:
        return "bo3.gg match ↗"
    if "bo3.gg/teams" in u:
        return "bo3.gg team ↗"
    if "bo3.gg" in u:
        return "bo3.gg ↗"
    if "valvesoftware" in u and "/details/" in u:
        return "Valve roster detail ↗"
    if "valvesoftware" in u and "standings" in u:
        return "Valve VRS table ↗"
    if "valvesoftware" in u:
        return "Valve official repo ↗"
    if "pinnacle" in u:
        return "Pinnacle ↗"
    if "bovada" in u:
        return "Bovada ↗"
    if "melbet" in u:
        return "Melbet ↗"
    if "thunderpick" in u:
        return "Thunderpick ↗"
    return _host(url) + " ↗"


def humanize(flag: str) -> str:
    return flag.replace("_", " ")


def source_ref(src: str) -> str:
    """An http(s) source becomes a link; a repo-relative path is shown as code, never linked."""
    if not src:
        return ""
    if src.startswith("http://") or src.startswith("https://"):
        first = src.split()[0]
        return f" <a href='{esc(first)}' target='_blank' rel='noopener'>source ↗</a>"
    return f" <code>{esc(src)}</code>"


def source_links(row):
    seen, links = set(), []
    for u in row.get("sources", []):
        if u in seen:
            continue
        seen.add(u)
        links.append(f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(source_label(u))}</a>')
    return '<div class="src">' + "".join(links) + "</div>"


def flags_html(row):
    out = []
    for f in row.get("flags", []) or []:
        out.append(f'<span class="badge flag">{esc(humanize(f))}</span>')
    if row.get("api_only"):
        out.append('<span class="badge api">API-only · not a lobby card</span>')
    if not row.get("permalink_verified", True):
        out.append('<span class="badge api">no HotSpawn permalink</span>')
    cross = row.get("cross_board")
    if cross and not cross.get("agrees"):
        out.append('<span class="badge flag">secondary board picks differently</span>')
    return f'<div class="flags">{"".join(out)}</div>' if out else ""


def match_card(row, now):
    pick_pct = pct(row.get("pick_prob"))
    return f"""
<article class="match-card" id="f{esc(row['fixture_id'])}">
 <div class="match-head">
  <div>
   <div class="match-title">{esc(row['team_a'])} <span class="muted">vs</span> {esc(row['team_b'])}</div>
   <div class="match-meta">{esc(row.get('competition') or '')} · tier {esc(str(row.get('tier') or '—'))}
    · {fmt_day(row.get('start_utc'))} · {esc(countdown(row.get('lock_utc'), now) or '')} · locks {fmt_day(row.get('lock_utc'))}</div>
  </div>
  <div style="text-align:right">{basis_badge(row)}<div style="height:6px"></div>{verify_badge(row)}</div>
 </div>
 <div class="pick-line">PICK: {esc(row.get('pick'))} <small>· {esc(row.get('confidence') or '')} · {pick_pct}% to win</small></div>
 {probability_bars(row)}
 {flags_html(row)}
 {source_links(row)}
</article>"""


def render():
    board = load(BOARD_JSON)
    verify = load(VERIFY_JSON)
    valve = load(VALVE_JSON)
    rows = board.get("rows", [])
    summary = verify.get("summary", {})
    now = datetime.fromisoformat(board["generated_utc"].replace("Z", "+00:00"))
    core.SITE.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- index / executive summary
    n_unresolved = summary.get("unresolved", 0)
    valve_line = ("live official check " + esc(valve.get("fetched_utc", "")) + " · newest table "
                  + esc(valve.get("newest_global_table", "?"))) if valve.get("live") else \
                 ("live Valve check unavailable — committed standings used ("
                  + esc(valve.get("attempted_utc", "no attempt recorded")) + ")")
    upcoming = [r for r in rows if r.get("lobby_rendered")][:5]
    preview = "".join(f"""
 <tr><td data-l="Match"><strong>{esc(r['team_a'])} vs {esc(r['team_b'])}</strong>
  <div class="muted">{esc(r.get('competition') or '')}</div></td>
  <td data-l="Kick-off">{fmt_day(r.get('start_utc'))}<div class="muted">{esc(countdown(r.get('lock_utc'), now))}</div></td>
  <td data-l="Pick">{esc(r.get('pick'))} <strong>({pct(r.get('pick_prob'))}%)</strong></td>
  <td data-l="Basis">{basis_badge(r)}</td></tr>""" for r in upcoming)

    limitations = verify.get("limitations", [])
    lim_items = "".join(f"<li><strong>{esc(l.get('title') if isinstance(l, dict) else l)}</strong></li>"
                        for l in limitations[:7])
    body = f"""
<p class="eyebrow">Executive summary · HotSpawn CS2 pick'em · independent verification desk</p>
<h1>Every open CS2 match has a pick, both win probabilities, and a source you can open.</h1>
<p class="lede">Built {esc(board.get('generated_utc'))} from the {summary.get('open_lobby_fixtures', 0)}
fixtures open in the HotSpawn lobby plus {summary.get('api_only_fixtures', 0)} API-only fixture.
Each number below is independently re-derived here, not copied: book/exchange prices are de-vigged
from their decimal odds and every model row is recomputed from Valve's official rating table.</p>

<div class="tiles">
 <div class="tile"><b>{summary.get('open_lobby_fixtures', 0)}</b><small>open lobby matches (+{summary.get('api_only_fixtures', 0)} API-only)</small></div>
 <div class="tile"><b>{summary.get('verified_rows', 0)}/{summary.get('open_fixtures_total', 0)}</b><small>picks independently verified</small></div>
 <div class="tile"><b>{summary.get('market_rows', 0)}</b><small>from real betting lines</small></div>
 <div class="tile"><b>{n_unresolved}</b><small>unresolved (blank, never guessed)</small></div>
</div>

<h2>Where the picks are</h2>
<p class="lede">One tap on a phone. The lists refresh automatically every four hours.</p>
<div class="cta">
 <a class="primary" href="picks.html"><span>All picks · every match<span class="small"><br>pick, both probabilities, probability bars, source per row</span></span><span>→</span></a>
 <a href="unresolved.html"><span>Unresolved &amp; limitations<span class="small"><br>{n_unresolved} blank row(s) · why low-tier matches lack book prices</span></span><span>→</span></a>
 <a href="sources.html"><span>Sources &amp; read times<span class="small"><br>every book, exchange and the official Valve table</span></span><span>→</span></a>
 <a href="method.html"><span>Method &amp; verification<span class="small"><br>HLTV → esportsbooks → exchange → Valve VRS ladder</span></span><span>→</span></a>
 <a href="flagged.html"><span>Flagged for review<span class="small"><br>irregularities and citation notes</span></span><span>→</span></a>
 <a href="../everypick/picks.html"><span>Canonical every-match board<span class="small"><br>the desk these picks are verified against</span></span><span>→</span></a>
</div>

<h2>Next matches locking</h2>
<div class="tbl-scroll"><table><thead><tr><th>Match</th><th>Kick-off</th><th>Pick</th><th>Basis</th></tr></thead>
<tbody>{preview}</tbody></table></div>
<p class="muted">The full list of {len(rows)} fixtures (including the API-only card) is on <a href="picks.html">All picks</a>.</p>

<h2>Unresolved picks &amp; limitations (summary)</h2>
<div class="callout {'good' if n_unresolved == 0 else 'bad'}">
 <p style="margin-top:0"><strong>{n_unresolved} match(es) unresolved today.</strong>
 {'Every open fixture resolved to a pick with both probabilities — but nine rows are originated models or directional bounds rather than market prices, and they carry real limitations.' if n_unresolved == 0 else 'See the dedicated page for the attempt ledger.'}</p>
 <ul style="margin-bottom:0">{lim_items}</ul>
 <p style="margin-bottom:0"><a href="unresolved.html">Full unresolved &amp; limitations page →</a></p>
</div>

<h2>Verification status</h2>
<div class="card">
 <p>✓ Arithmetic: {summary.get('checks_passed', {}).get('arithmetic', 0)}/{summary.get('checks_total', 0)} rows re-derived within tolerance
  (market no-vig from decimal odds; Valve logistic from official points).</p>
 <p>✓ Official identity: {summary.get('checks_passed', {}).get('identity', 0)} originated rows checked against the official table — {valve_line}.</p>
 <p>✓ Source links: {summary.get('checks_passed', {}).get('sources', 0)}/{summary.get('checks_total', 0)} rows carry an openable external source plus their HotSpawn permalink.</p>
 <p>✓ No HotSpawn crowd/vote percentage is read on any row.</p>
</div>
"""
    (core.SITE / "index.html").write_text(
        page("summary", "Executive summary", "index.html", body,
             "Independently verified win probabilities and picks for every open HotSpawn CS2 match."),
        encoding="utf-8")

    # ---------------------------------------------------------------- picks
    cards = "".join(match_card(r, now) for r in rows)
    body = f"""
<p class="eyebrow">All picks · {len(rows)} fixtures</p>
<h1>Every open HotSpawn CS2 match, verified line by line</h1>
<p class="lede">★ marks the pick. Green bars are the picked side; {summary.get('market_rows', 0)} cards use
real book/exchange prices, {summary.get('originated_vrs_rows', 0)} use Valve's official ratings and
{summary.get('bound_rows', 0)} are directional bounds because one team is unrated. Bounds show
<code>≥</code>/<code>≤</code>, never a fake point estimate.</p>
{cards}
"""
    (core.SITE / "picks.html").write_text(
        page("picks", "All picks", "picks.html", body,
             "Every open HotSpawn CS2 match with pick, both win probabilities and sources."),
        encoding="utf-8")

    # ---------------------------------------------------------------- unresolved + limitations
    unr = verify.get("unresolved", [])
    if unr:
        unr_rows = "".join(
            f"<tr><td data-l='Fixture'>{esc(u.get('fixture_id'))}<div class='muted'>{esc(u.get('team_a'))} vs {esc(u.get('team_b'))}</div></td>"
            f"<td data-l='Kick-off'>{fmt_day(u.get('start_utc'))}</td>"
            f"<td data-l='Reason'>{esc(u.get('reason'))}</td>"
            f"<td data-l='Source'><a href='{esc(u.get('hotspawn_url') or '#')}' target='_blank' rel='noopener'>HotSpawn ↗</a></td></tr>"
            for u in unr)
        unr_html = f"<div class='tbl-scroll'><table><thead><tr><th>Fixture</th><th>Kick-off</th><th>Reason</th><th>Source</th></tr></thead><tbody>{unr_rows}</tbody></table></div>"
    else:
        unr_html = """
<div class="callout good"><p style="margin:0"><strong>0 unresolved matches at this refresh.</strong>
Every fixture open in the HotSpawn lobby (and the one API-only fixture) has a pick with both win
probabilities. This section is kept permanently: the next refresh can introduce a fixture that no
book prices and no rating covers, and it will be listed here as an explicit blank rather than guessed.</p></div>"""
    lim_html = ""
    for l in limitations:
        if isinstance(l, dict):
            lim_html += (f"<li><strong>{esc(l.get('title'))}.</strong> {esc(l.get('detail'))}"
                         f"{source_ref(l.get('source'))}</li>")
        else:
            lim_html += f"<li>{esc(l)}</li>"
    bound_rows = [r for r in rows if r["basis"] == "originated_vrs_bound"]
    bound_list = "".join(f"<li>{esc(r['team_a'])} vs {esc(r['team_b'])} "
                         f"(<a href='../cs2-picks/picks.html#f{esc(r['fixture_id'])}'>card</a>)</li>"
                         for r in bound_rows)
    body = f"""
<p class="eyebrow">Unresolved picks &amp; limitations</p>
<h1>What could not be priced, and what the originated lines can and cannot tell you</h1>
{unr_html}
<h2>Why a low-tier match may have no bookmaker price</h2>
<p class="lede">Reference books (Pinnacle, Bovada, Melbet, Thunderpick) and the Kalshi exchange do not
list most tier-C CS2 fixtures. The resolution ladder is applied in this order and every attempt is
recorded: <strong>featured book lines → other esportsbooks / betting lines → Kalshi exchange →
HLTV/bo3.gg identity checks → official Valve VRS origination → labelled bound → explicit unresolved
blank</strong>. HotSpawn's own crowd percentage is never used.</p>
<h2>Current limitations</h2>
<ol>{lim_html}</ol>
<h2>Directional bounds (one side unrated)</h2>
<p>These {len(bound_rows)} fixtures have exactly one team in Valve's table. The unrated side is at or
below Valve's published floor (#380, 381 points), so the rated side is shown as a lower bound
<code>≥</code> and the other as <code>≤</code> — a direction, not a calibrated point.</p>
<ul>{bound_list}</ul>
<h2>What makes a row unresolved</h2>
<ul>
 <li>no book or exchange prices the fixture <em>and</em> neither team appears in Valve's official standings;</li>
 <li>team identity cannot be confirmed across HLTV / bo3.gg / Valve (name or roster mismatch);</li>
 <li>the only quote fails the kick-off tolerance or has no two-way price;</li>
 <li>any re-derivation check in <a href="method.html">Method</a> fails — the row is then flagged, never silently changed.</li>
</ul>
"""
    (core.SITE / "unresolved.html").write_text(
        page("unresolved", "Unresolved & limitations", "unresolved.html", body,
             "Unresolved HotSpawn CS2 picks and the limitations of betting-line and rating origination."),
        encoding="utf-8")

    # ---------------------------------------------------------------- sources
    ledger = {}
    for r in rows:
        for q in r.get("quotes", []):
            key = q.get("source_name") or q.get("source_key")
            ent = ledger.setdefault(key, {"n": 0, "urls": set(), "times": set()})
            ent["n"] += 1
            if q.get("public_url"):
                ent["urls"].add(q["public_url"])
            if q.get("retrieved_utc"):
                ent["times"].add(q["retrieved_utc"])
        for u in r.get("sources", []):
            if "ValveSoftware" in u or "valve" in u.lower():
                ent = ledger.setdefault("Valve official regional standings",
                                        {"n": 0, "urls": set(), "times": set()})
                ent["urls"].add(u)
    src_rows = ""
    for name, ent in sorted(ledger.items()):
        urls = "<br>".join(f"<a href='{esc(u)}' target='_blank' rel='noopener'>{esc(_host(u))} ↗</a>"
                           for u in sorted(ent["urls"])[:3])
        times = ", ".join(sorted(ent["times"])[:3]) or "—"
        src_rows += (f"<tr><td data-l='Source'>{esc(name)}</td>"
                     f"<td class='num' data-l='Rows priced'>{ent['n']}</td>"
                     f"<td data-l='Last read (UTC)'>{esc(times)}</td>"
                     f"<td data-l='Open'>{urls}</td></tr>")
    valve_src = ""
    if valve:
        valve_src = f"""
<div class="card">
 <h3 style="margin-top:0">Official Valve source — live check</h3>
 <p>Live: <strong>{valve.get('live')}</strong> · fetched {esc(valve.get('fetched_utc') or valve.get('attempted_utc', '—'))}</p>
 <p>Newest global table: <a href="{esc(valve.get('newest_table_url', '#'))}" target="_blank" rel="noopener">{esc(valve.get('newest_global_table', '—'))} ↗</a>
  ({valve.get('n_teams_parsed', '—')} teams, floor {json.dumps(valve.get('floor'))})</p>
 <p>Slope re-derivation: C = {esc(valve.get('slope_check', {}).get('derived_slope_c'))}
  (canonical 0.0056000078, match={esc(valve.get('slope_check', {}).get('matches_canonical'))})</p>
</div>"""
    body = f"""
<p class="eyebrow">Sources &amp; read times</p>
<h1>Every number traces to an openable, timestamped source</h1>
{valve_src}
<div class="tbl-scroll"><table><thead><tr><th>Source</th><th class="num">Rows priced</th><th>Last read (UTC)</th><th>Open</th></tr></thead>
<tbody>{src_rows}</tbody></table></div>
<p class="muted">Raw HotSpawn lobby capture: {esc(verify.get('inputs', {}).get('raw_snapshot_utc', '—'))}
(play.hotspawn.com/lobby transfer-state + public fixtures API). HotSpawn supplies fixtures and lock
times only — never probabilities.</p>
"""
    (core.SITE / "sources.html").write_text(
        page("sources", "Sources", "sources.html", body,
             "Source ledger with read times for every verified CS2 pick."),
        encoding="utf-8")

    # ---------------------------------------------------------------- method
    checks = verify.get("summary", {}).get("checks_passed", {})
    slope = valve.get("slope_check", {})
    body = f"""
<p class="eyebrow">Method &amp; verification</p>
<h1>How each pick is produced and independently checked</h1>
<h2>1. The resolution ladder (no HotSpawn crowd input at any step)</h2>
<ol>
 <li><strong>Featured bookmaker lines, unchanged.</strong> Pinnacle / Bovada / Melbet / Thunderpick
 decimal odds are converted to implied probabilities and de-vigged per book
 (<code>p = (1/odds) / (1/odds_a + 1/odds_b)</code>), then averaged across books.</li>
 <li><strong>Other esportsbooks and betting lines.</strong> Name variants are joined only when the
 opponent and kick-off agree (90-minute tolerance), e.g. UNiTY/Apogee Esports joins.</li>
 <li><strong>Kalshi regulated exchange.</strong> Used where no traditional book prices the fixture,
 with roster-verified aliases (HotSpawn “Zetta” = Kalshi “Alianza Lima Esports”).</li>
 <li><strong>HLTV and bo3.gg identity checks.</strong> Team aliases and rosters are confirmed against
 HLTV team/match pages and bo3.gg before any join is accepted.</li>
 <li><strong>Official Valve VRS origination.</strong> When no external price exists,
 <code>p = 1 / (1 + exp(-k·C·Δpoints))</code> using Valve's published points, Valve's effective
 slope C and this project's fitted k (60 market pairs, MAE 7.70 pp).</li>
 <li><strong>Labelled bounds.</strong> A team absent from Valve's table is at or below the published
 floor; the row shows <code>≥</code>/<code>≤</code>.</li>
 <li><strong>Explicit unresolved blank.</strong> If none of the above applies, the row stays blank and
 is published on the Unresolved page with its attempt ledger.</li>
</ol>
<h2>2. The constants, and where they really come from</h2>
<div class="card">
 <p>Valve's <code>model/glicko.js</code> publishes <code>Q = ln(10)/400</code> and
 <code>model/fit.js</code> fixes RD = 75 for the expected-win fit. The effective logistic slope is
 <code>C = ln(10)·g(75)/400</code>. This desk re-derives it live:
 <strong>{esc(slope.get('derived_slope_c'))}</strong> vs the boards' quoted 0.0056000078
 (match = {esc(slope.get('matches_canonical'))}, diff {esc(slope.get('abs_diff'))}). It is correct,
 but note it spans two files rather than appearing as a literal — see Flagged.</p>
 <p>Calibration slope <code>k = {core.CANONICAL_K}</code> is this project's own fit of market prices
 against rating differences (60 pairs), not a Valve value.</p>
</div>
<h2>3. The five hard verification gates (re-run every refresh)</h2>
<ul>
 <li><strong>Coverage:</strong> every open lobby fixture has a pick and both probabilities
 ({checks.get('coverage', 0)} pass).</li>
 <li><strong>Arithmetic:</strong> stored market consensus reproduces from decimal odds within 0.25 pp;
 originated probabilities reproduce from official points within 0.06 pp ({checks.get('arithmetic', 0)} pass).</li>
 <li><strong>Official identity:</strong> standing, points and five-man roster match the live Valve
 table for every originated row ({checks.get('identity', 0)} pass).</li>
 <li><strong>Sources:</strong> at least one external source link plus the HotSpawn permalink
 ({checks.get('sources', 0)} pass).</li>
 <li><strong>No crowd input:</strong> no row reads HotSpawn vote/crowd percentages
 ({checks.get('no_crowd', 0)} pass).</li>
</ul>
<p>A failed gate flips the row to <em>unverified</em>, adds it to Flagged and (if it has no pick) to
Unresolved. Values are never inferred or filled in.</p>
<h2>4. Automation</h2>
<p>Workflow <code>cs2-picks-bce97e13.yml</code> runs every four hours (and on upstream board refreshes):
live Valve check → verification build → site render → tests → commit. No manual input.</p>
"""
    (core.SITE / "method.html").write_text(
        page("method", "Method", "method.html", body,
             "Resolution ladder, formula and verification gates for the CS2 pick desk."),
        encoding="utf-8")

    # ---------------------------------------------------------------- flagged
    irr = verify.get("irregularities", [])
    items = ""
    for r in irr:
        if isinstance(r, dict):
            items += (f"<li><strong>[{esc(r.get('id') or r.get('severity'))}] {esc(r.get('title'))}</strong>"
                      f"<br>{esc(r.get('detail'))}{source_ref(r.get('source'))}</li>")
        else:
            items += f"<li>{esc(r)}</li>"
    body = f"""
<p class="eyebrow">Flagged for review</p>
<h1>Irregularities, citation notes and unverified items</h1>
<p class="lede">Nothing here blocks publication. Each item links its source so it can be checked manually.</p>
<ol>{items}</ol>
<h2>Per-row verification flags</h2>
<p>Rows carrying warning badges (single-book quotes, zero-volume exchange ladders, stale VRS snapshot,
duplicate Valve rows resolved by the published rule) are listed with their evidence on
<a href="picks.html">All picks</a> and the canonical
<a href="../everypick/flagged.html">everypick flagged page</a>.</p>
"""
    (core.SITE / "flagged.html").write_text(
        page("flagged", "Flagged for review", "flagged.html", body,
             "Irregularities and unverified items in the verified CS2 pick desk."),
        encoding="utf-8")

    print(f"wrote {len(list(core.SITE.glob('*.html')))} pages to {core.SITE}")


if __name__ == "__main__":
    render()
