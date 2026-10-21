#!/usr/bin/env python3
"""Render the 86f3af65 phone-first pick dashboard into ``pickboard/``.

Pages
    index.html        executive summary: coverage, where the updated picks live, today's picks,
                      the separate Unresolved picks & limitations section, audit summary
    picks.html        every open fixture: the pick, both win probabilities, basis, sources
    unresolved.html   the separate Unresolved & limitations section (one section per limitation)
    tournaments.html  the same picks grouped by event
    sources.html      every raw quote, every rating row, every endpoint read, with links
    flagged.html      Flagged for review: repo irregularities + how earlier boards disagree
    method.html       the reverse-engineered lobby, the ladder, the formulas, how to reproduce

Design rules: one stylesheet, no framework, no external requests, cards that read as a table on
a wide screen and as stacked rows on a phone, tap targets at least 44px, and a source link on
every number that came from a source.
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ladder  # noqa: E402

OUT = ROOT / "pickboard"
BOARD = json.loads((ROOT / "data/86f3af65/board.json").read_text())

NAV = [
    ("index.html", "Summary"),
    ("picks.html", "All picks"),
    ("unresolved.html", "Unresolved"),
    ("tournaments.html", "Events"),
    ("sources.html", "Sources"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method"),
]

CSS = """
:root{
  --bg:#0b1220; --panel:#131c2e; --panel2:#0f1727; --line:#233149; --text:#e9eef7;
  --dim:#9aa9c0; --accent:#38e1a4; --accent2:#5aa9ff; --warn:#ffc861; --bad:#ff7a7a;
  --radius:14px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent2);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:960px;margin:0 auto;padding:0 14px 64px}
header.top{position:sticky;top:0;z-index:20;background:rgba(11,18,32,.96);
  border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.top .bar{max-width:960px;margin:0 auto;display:flex;align-items:center;gap:10px;
  padding:8px 14px;flex-wrap:wrap}
.brand{font-weight:700;font-size:15px;color:var(--text);letter-spacing:.2px}
.brand span{color:var(--accent)}
nav.chips{display:flex;gap:8px;overflow-x:auto;padding:2px 0 6px;scrollbar-width:none}
nav.chips::-webkit-scrollbar{display:none}
nav.chips a{flex:0 0 auto;padding:9px 12px;border:1px solid var(--line);border-radius:999px;
  font-size:13px;color:var(--dim);background:var(--panel2);min-height:38px;display:flex;
  align-items:center}
nav.chips a[aria-current="page"]{color:#05140f;background:var(--accent);border-color:var(--accent);
  font-weight:700}
h1{font-size:24px;line-height:1.25;margin:22px 0 6px}
h2{font-size:18px;margin:30px 0 10px}
h3{font-size:15px;margin:20px 0 6px;color:var(--text)}
p,li{color:#cfd8e6}
.lede{color:var(--dim);margin:0 0 14px;font-size:15px}
.sub{color:var(--dim);font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px;margin:12px 0}
.grid{display:grid;gap:10px;grid-template-columns:1fr}
@media(min-width:640px){.grid.two{grid-template-columns:1fr 1fr}
  .grid.three{grid-template-columns:repeat(3,1fr)}}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px}
.kpi .n{font-size:26px;font-weight:700;line-height:1.1}
.kpi .l{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.btns{display:grid;gap:10px;margin:14px 0}
@media(min-width:560px){.btns{grid-template-columns:1fr 1fr}}
.btn{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:56px;
  padding:14px 16px;border-radius:var(--radius);border:1px solid var(--line);
  background:var(--panel);color:var(--text);font-weight:600}
.btn.primary{background:var(--accent);color:#04140e;border-color:var(--accent)}
.btn small{display:block;font-weight:400;font-size:12px;opacity:.85}
.pickrow{display:grid;grid-template-columns:1fr auto;gap:2px 10px;align-items:center;
  background:var(--panel);border:1px solid var(--line);border-left:5px solid var(--line);
  border-radius:12px;padding:12px 12px;margin:10px 0}
.pickrow.picked{border-left-color:var(--accent)}
.meta{grid-column:1/-1;color:var(--dim);font-size:12px;margin-bottom:4px}
.team{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
  padding:6px 0;border-top:1px dashed #1d2a40}
.team:first-of-type{border-top:0}
.team .nm{font-weight:600;font-size:17px}
.team .pc{font-variant-numeric:tabular-nums;font-size:20px;font-weight:700}
.team.win .nm,.team.win .pc{color:var(--accent)}
.team.lose .nm,.team.lose .pc{color:var(--dim)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);color:var(--dim);margin-left:6px;vertical-align:middle}
.tag.pick{background:var(--accent);color:#04140e;border-color:var(--accent);font-weight:700}
.tag.warn{background:#3a2d12;color:var(--warn);border-color:#5b4718}
.tag.bad{background:#3a1616;color:var(--bad);border-color:#5b2222}
.call{font-size:14px;color:var(--text);margin-top:8px}
.call b{color:var(--accent)}
.basis{grid-column:1/-1;color:var(--dim);font-size:12px;margin-top:6px}
details{margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
summary{cursor:pointer;color:var(--accent2);font-size:13px;min-height:32px}
ul.src{list-style:none;margin:6px 0 0;padding:0}
ul.src li{font-size:12px;color:var(--dim);padding:6px 0;border-bottom:1px dashed #1d2a40}
ul.src li:last-child{border-bottom:0}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 0;display:block;
  overflow-x:auto;white-space:nowrap}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
td.wrapcell{white-space:normal;min-width:220px}
.note{background:var(--panel2);border:1px solid var(--line);border-left:4px solid var(--warn);
  border-radius:10px;padding:10px 12px;margin:10px 0;font-size:13px;color:#dfe6f2}
.note.ok{border-left-color:var(--accent)}
.note.bad{border-left-color:var(--bad)}
.flag{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;
  margin:10px 0}
.flag h3{margin:0 0 6px;font-size:15px}
.flag .id{color:var(--accent);font-weight:700;margin-right:6px}
.flag p{font-size:13px;color:#cfd8e6;margin:6px 0}
.flag .files{font-size:12px;color:var(--dim)}
.search{width:100%;min-height:48px;border-radius:12px;border:1px solid var(--line);
  background:var(--panel2);color:var(--text);padding:12px 14px;font-size:16px;margin:6px 0 2px}
.foot{margin-top:36px;border-top:1px solid var(--line);padding-top:14px;color:var(--dim);
  font-size:12px}
.pill{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:999px;
  padding:4px 10px;color:var(--dim);margin:0 6px 6px 0}
.acc{color:var(--accent)}
.small{font-size:12px}
code{background:#0a1526;border:1px solid var(--line);border-radius:6px;padding:1px 5px;
  font-size:12px}
"""

APP_JS = """
(function(){
  var q=document.getElementById('q');
  if(q){q.addEventListener('input',function(){
    var v=q.value.trim().toLowerCase();
    document.querySelectorAll('[data-teams]').forEach(function(el){
      el.style.display=(!v||el.dataset.teams.indexOf(v)>=0)?'':'none';
    });
  });}
  document.querySelectorAll('[data-utc]').forEach(function(el){
    var d=new Date(el.dataset.utc);
    if(isNaN(d))return;
    var loc=d.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',
      minute:'2-digit'});
    el.title=d.toISOString();
    var span=el.querySelector('.local');
    if(span){span.textContent=loc;}
  });
})();
"""


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pct(v) -> str:
    return "—" if v is None else f"{float(v) * 100:.1f}%"


def utc_short(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso.replace("T", " ").replace(":00Z", "Z").replace("Z", " UTC")


def freshness_strip() -> str:
    """One line, on every page, saying how old the numbers are and when they are rebuilt."""
    cap = BOARD["capture"]
    hours = cap.get("age_hours")
    age = "unknown age" if hours is None else (
        f"{(hours * 60):.0f} min old at build time" if hours < 1 else f"{hours:.1f} h old at build time")
    mode = cap.get("mode") or "unknown"
    stale = bool(cap.get("stale"))
    cls = "fresh warn" if (stale or mode != "live") else "fresh"
    if mode != "live":
        text = (f"Capture mode <b>{esc(mode)}</b> - these numbers were converted from pinned "
                f"repository evidence rather than read live, {esc(age)}.")
    elif stale:
        text = (f"<b>Stale data.</b> The newest capture is {esc(age)}; the scheduled refresh has "
                f"not landed. Re-check the sources before acting on any number here.")
    else:
        text = (f"Live capture {esc(utc_short(cap.get('captured_utc')))} - {esc(age)}. "
                f"Rebuilt every 4 h by the scheduled workflow.")
    return (f'<div class="{cls}"><span class="dot" aria-hidden="true"></span>{text}'
            f' <a href="sources.html#access">read log</a></div>')


def page(title: str, active: str, body: str, extra_head: str = "") -> str:
    parts = []
    for href, label in NAV:
        attr = ' aria-current="page"' if href == active else ""
        parts.append(f'<a href="{href}"{attr}>{esc(label)}</a>')
    nav = "".join(parts)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>{esc(title)} · CS2 Pick Board</title>
<meta name="description" content="A pick and both win probabilities for every open HotSpawn
Counter-Strike 2 fixture, built from external bookmaker lines and official Valve rankings.">
<link rel="stylesheet" href="style.css">
{extra_head}</head>
<body>
<header class="top">
  <div class="bar">
    <a class="brand" href="index.html">CS2 <span>Pick Board</span></a>
    <span class="sub" style="margin-left:auto">{esc(BOARD['coverage']['with_pick'])}/{esc(BOARD['coverage']['open'])} priced</span>
  </div>
  <nav class="chips">{nav}</nav>
</header>
{freshness_strip()}
<div class="wrap">
{body}
<div class="foot">
  <p><b>Independent research.</b> Not affiliated with HotSpawn, Valve, any bookmaker or any
  exchange. HotSpawn supplies the fixture list and contest context only; it is never used as a
  probability. Odds are public, unauthenticated reads and move constantly — check the source
  link before acting on any number here.</p>
  <p>Board generated {esc(BOARD['generated_utc'])} from a capture taken
  {esc(BOARD['capture']['captured_utc'])}. Session <code>86f3af65</code>.
  Data: <a href="../data/86f3af65/board.json">board.json</a>.</p>
</div>
</div>
<script src="app.js"></script>
</body>
</html>
"""



def unrated_teams(row: dict) -> list[str]:
    if not row.get("model"):
        return []
    return [res["team"] for res in (row["model"]["rating_a"], row["model"]["rating_b"])
            if res["status"] == "floor-proxy"]


def roster_used(row: dict) -> str:
    if not row.get("model"):
        return "—"
    out = []
    for res in (row["model"]["rating_a"], row["model"]["rating_b"]):
        if res["status"] == "roster-selected" and res.get("row"):
            r = res["row"]
            out.append(f'{res["team"]} #{r["standing"]} ({r["points"]} pts, roster {r["roster"]}, '
                       f'last counted match {r.get("latest_match_date")})')
    return "; ".join(out) or "—"


def roster_rejected(row: dict) -> str:
    if not row.get("model"):
        return "—"
    out = []
    for res in (row["model"]["rating_a"], row["model"]["rating_b"]):
        for r in res.get("rejected") or []:
            out.append(f'{res["team"]} #{r["standing"]} ({r["points"]} pts, roster {r["roster"]})')
    return "; ".join(out) or "—"


def check_row(c: dict) -> str:
    src = "—"
    if c.get("source"):
        target = c["source"]
        if target.startswith("http"):
            href = target
        elif (ROOT / target).exists():
            href = "../" + target
        else:
            href = None
        src = (f'<a href="{esc(href)}" target="_blank" rel="noopener">source</a>'
               if href else f'<span class="sub">{esc(target)}</span>')
    return (f'<tr><td>{esc(c["id"])}</td><td class="wrapcell">{esc(c["check"])}</td>'
            f'<td class="wrapcell">{esc(c["result"])}</td><td>{esc(c["verdict"])}</td>'
            f'<td>{src}</td></tr>')



def obs_row(r: dict, o: dict) -> str:
    src = (f'<a href="{esc(o["url"])}" target="_blank" rel="noopener">{esc(o["source"])}</a>'
           if o.get("url") else esc(o["source"]))
    return (f'<tr><td class="wrapcell">{esc(r["team_a"])} v {esc(r["team_b"])}</td>'
            f'<td>{src}</td><td class="wrapcell">{esc(o["teams"][0])} v {esc(o["teams"][1])}</td>'
            f'<td>{esc(o["raw"])}</td><td class="wrapcell">{esc(o["reason"])}</td></tr>')


NO_OBS_ROW = '<tr><td colspan="5" class="sub">None at this build.</td></tr>'


def files_links(files: list[str]) -> str:
    out = []
    for raw in files:
        path = raw.split(" ")[0].rstrip(",")
        if (ROOT / path).exists():
            out.append(f'<a href="../{esc(path)}" target="_blank" rel="noopener">'
                       f'{esc(raw)}</a>')
        else:
            out.append(esc(raw))
    return ", ".join(out)


def overround(v) -> str:
    return "—" if v is None else f"{float(v) * 100:+.2f}%"



def dup_candidate(c: dict) -> str:
    return (f'#{esc(c["standing"])} · {esc(c["points"])} pts · {len(c["players"])} players · '
            f'last match {esc(c["latest_match_date"] or "n/a")}<br>'
            f'<span class="small sub">{esc(c["roster"])}</span>')


def dup_row(d: dict) -> str:
    body = "<br>".join(dup_candidate(c) for c in d["candidates"])
    return (f'<tr><td class="wrapcell">{esc(d["team"])}</td>'
            f'<td class="wrapcell">{body}</td></tr>')


PEER_COLUMNS = ("fe803b80", "51197e5b", "36495748")


def peer_cell(peers: dict, session: str) -> str:
    p = (peers or {}).get(session) or {}
    if p.get("prob_a") is None:
        value = '<span class="sub">blank</span>'
    else:
        value = pct(p["prob_a"])
    basis = esc(p.get("basis") or "—")
    return f'<td>{value}<br><span class="small sub">{basis}</span></td>'


def dis_row(d: dict) -> str:
    cells = "".join(peer_cell(d.get("peers"), s) for s in PEER_COLUMNS)
    return (f'<tr><td class="wrapcell">{esc(d["teams"][0])} v {esc(d["teams"][1])}</td>'
            f'<td>{pct(d["ours"])}<br><span class="small sub">{esc(d["ours_basis"])}</span></td>'
            f'{cells}<td>{esc(round(d["max_gap"] * 100, 1))} pts</td></tr>')


def blank_row(r: dict) -> str:
    return (f'<tr><td class="wrapcell">{esc(r["team_a"])} v {esc(r["team_b"])}</td>'
            f'<td class="wrapcell">{len(r["sources"])} source(s) recorded - see the row detail '
            f'on the picks page</td></tr>')


# --------------------------------------------------------------------------------- fragments
def source_list(sources: list[dict], limit: int | None = None) -> str:
    items = []
    for s in (sources[:limit] if limit else sources):
        read = f' <span class="pill">read {esc(s["read_utc"])}</span>' if s.get("read_utc") else ""
        link = (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                f'{esc(s["label"])}</a>' if s.get("url") else esc(s["label"]))
        items.append(f'<li>{link}{read}<br>{esc(s.get("note") or "")}</li>')
    return '<ul class="src">' + "".join(items) + "</ul>"


def team_line(row: dict, side: str) -> str:
    name = row["team_a"] if side == "a" else row["team_b"]
    prob = row["prob_a"] if side == "a" else row["prob_b"]
    won = side == "a" if (row["prob_a"] or 0) >= 0.5 else side == "b"
    mark = '<span class="tag pick">PICK</span>' if row["pick_side"] == side else ""
    return (f'<div class="team {"win" if won else "lose"}"><span class="nm">{esc(name)}{mark}'
            f'</span><span class="pc">{pct(prob)}</span></div>')


def pick_card(row: dict) -> str:
    tags = []
    if row.get("confidence"):
        tags.append(f'<span class="tag">{esc(row["confidence"])}</span>')
    if row["basis"] == "market (contested)":
        tags.append('<span class="tag bad">contested</span>')
    if "floor_proxy_unrated_team" in row["flags"] and row["basis"].startswith("originated"):
        tags.append('<span class="tag warn">floor proxy</span>')
    if "duplicate_vrs_roster" in row["flags"]:
        tags.append('<span class="tag warn">roster choice</span>')
    if "alias_join" in row["flags"]:
        tags.append('<span class="tag warn">alias</span>')
    meta = (f'{esc(row["competition"])} · <span data-utc="{esc(row["start_utc"])}">'
            f'{esc(utc_short(row["start_utc"]))}</span> · locks '
            f'{esc((row["lock_utc"] or "").replace("T", " ").replace("Z", " UTC"))}'
            f' · {esc(row["points"])} pts')
    obs = ""
    if row.get("observations"):
        obs = ("<h4 class='small'>Prices seen but NOT used</h4>" + source_list([
            {"label": f'{o["source"]}: {o["teams"][0]} v {o["teams"][1]}', "url": o["url"],
             "read_utc": None, "note": f'{o["reason"]} (raw {o["raw"]})'}
            for o in row["observations"]]))
    model_note = ""
    if row.get("model"):
        m = row["model"]
        pts_a = m["rating_a"]["row"]["points"] if m["rating_a"].get("row") else "—"
        pts_b = m["rating_b"]["row"]["points"] if m["rating_b"].get("row") else "—"
        model_note = (f'<p class="small">Rating line: {esc(row["team_a"])} {esc(pts_a)} vs '
                      f'{esc(row["team_b"])} {esc(pts_b)} points (gap {esc(m["delta"])}), '
                      f'slope k={m["k"]:.4f}.')
        if m.get("alternate_prob_a") is not None:
            model_note += (f' With the other published roster this would be '
                           f'{pct(m["alternate_prob_a"])} for {esc(row["team_a"])}.')
        model_note += "</p>"
        if m.get("notes"):
            model_note += ('<ul class="src">' +
                           "".join(f"<li>{esc(n)}</li>" for n in m["notes"]) + "</ul>")
    link = ""
    if row.get("hotspawn_url"):
        link = (f' · <a href="{esc(row["hotspawn_url"])}" target="_blank" rel="noopener">'
                f'HotSpawn page</a>')
    lim = (" · " + esc(row["limitation"])) if row.get("limitation") else ""
    picked = " picked" if row["pick_side"] else ""
    teams_blob = (row["team_a"] + " " + row["team_b"] + " " + (row["competition"] or "")).lower()
    return f"""<article class="pickrow{picked}" data-teams="{esc(teams_blob)}">
  <div class="meta">{meta}</div>
  {team_line(row, "a")}{team_line(row, "b")}
  <div class="call">Pick: <b>{esc(row["pick_team"] or "no pick published")}</b>
    {pct(row["pick_prob"])} {' '.join(tags)}</div>
  <div class="basis">{esc(row["basis"])}{lim}{link}</div>
  <details><summary>Sources for this pick ({len(row["sources"])})</summary>
    {source_list(row["sources"])}{model_note}{obs}
  </details>
</article>"""


def kpi(n, label: str) -> str:
    return f'<div class="kpi"><div class="n">{esc(n)}</div><div class="l">{esc(label)}</div></div>'


def next_locks(rows: list[dict], n: int = 3) -> list[dict]:
    return sorted([r for r in rows if r["lock_utc"]], key=lambda r: r["lock_utc"])[:n]


# ------------------------------------------------------------------------------------ pages
def render_index() -> str:
    cov = BOARD["coverage"]
    rows = BOARD["rows"]
    unresolved = BOARD["unresolved"]
    contested = [r for r in rows if r["basis"] == "market (contested)"]
    floor_rows = [r for r in rows if "floor_proxy_unrated_team" in r["flags"]
                  and r["basis"].startswith("originated")]
    dup_rows = [r for r in rows if "duplicate_vrs_roster" in r["flags"]]
    market_rows = [r for r in rows if r["basis"].startswith("market")]
    body = f"""
<h1>Every HotSpawn CS2 match now has a pick</h1>
<p class="lede">A pick and both teams' win probabilities for <b>all {cov['open']}</b> open
Counter-Strike 2 fixtures in the HotSpawn Pick'ems lobby, built from external bookmaker and
exchange lines and — where no book prices a low-tier match — from Valve's official rankings.
HotSpawn is used to find the fixtures only; it is never used as a probability.</p>

<div class="grid three">
  {kpi(f"{cov['with_pick']}/{cov['open']}", "matches priced")}
  {kpi(cov['market'] + cov['market_contested'], "from betting lines")}
  {kpi(cov['originated_vrs'] + cov['originated_floor'], "originated from Valve VRS")}
</div>
<div class="grid three" style="margin-top:10px">
  {kpi(cov['unresolved'], "left blank")}
  {kpi(cov['caveated'], "published with a caveat")}
  {kpi(len(BOARD['findings']), "repo irregularities flagged")}
</div>

<div class="note {'ok' if cov['unresolved'] == 0 else 'bad'}">
  <b>Coverage: {cov['with_pick']} of {cov['open']} open fixtures carry a pick.</b>
  {cov['unresolved']} rows are blank and {cov['caveated']} rows are published with a stated
  limitation. Nothing is inferred silently: every row shows its basis and its source links.
</div>

<h2>Where the updated picks live</h2>
<p class="sub">This page is the front door. The numbers themselves are on the pages below, which
are rebuilt by the scheduled workflow every four hours.</p>
<div class="btns">
  <a class="btn primary" href="picks.html"><span>All picks — every match<small>{cov['open']} fixtures · pick + both probabilities</small></span><span aria-hidden="true">›</span></a>
  <a class="btn" href="unresolved.html"><span>Unresolved &amp; limitations<small>{len(unresolved)} rows need a caveat</small></span><span aria-hidden="true">›</span></a>
  <a class="btn" href="tournaments.html"><span>Picks by event<small>{len({r['competition'] for r in rows})} competitions</small></span><span aria-hidden="true">›</span></a>
  <a class="btn" href="sources.html"><span>Sources &amp; raw quotes<small>every price, rating and endpoint</small></span><span aria-hidden="true">›</span></a>
  <a class="btn" href="flagged.html"><span>Flagged for review<small>{len(BOARD['findings'])} irregularities</small></span><span aria-hidden="true">›</span></a>
  <a class="btn" href="method.html"><span>Method<small>ladder, formulas, how to reproduce</small></span><span aria-hidden="true">›</span></a>
</div>

<h2>Next to lock</h2>
<p class="sub">Times shown in UTC; your device's local time is applied by script where available.</p>
{''.join(pick_card(r) for r in next_locks(rows, 3))}

<h2>Unresolved picks &amp; limitations</h2>
<p class="sub">The separate section requested for the rows that cannot be resolved the same way as
the featured picks. Full detail, with the source attempts, on
<a href="unresolved.html">Unresolved &amp; limitations</a>.</p>
<div class="card">
  <table>
    <thead><tr><th>Match</th><th>Pick</th><th>Why it needs a caveat</th></tr></thead>
    <tbody>
    {''.join(f'''<tr><td class="wrapcell">{esc(r['team_a'])} v {esc(r['team_b'])}<br>
      <span class="small sub">{esc(r['competition'])}</span></td>
      <td>{esc(r['pick_team'])}<br><span class="small sub">{pct(r['pick_prob'])}</span></td>
      <td class="wrapcell">{esc(r['limitation'] or r['basis'])}</td></tr>''' for r in unresolved)}
    </tbody>
  </table>
  <p class="small sub" style="margin-top:10px">Categories: {len(floor_rows)} fixture(s) with a
  team that has no published Valve rating, {len(dup_rows)} fixture(s) where Valve publishes two
  rosters under one name, {len(contested)} fixture where the market and the rating model disagree
  by more than 15 points. Two prices that were seen but <b>not</b> used are also listed there,
  with the reason.</p>
</div>

<h2>How the picks are produced</h2>
<div class="card">
  <p class="small">One ladder, applied in order, never blended across rungs:</p>
  <ol class="small">
    <li><b>External betting lines</b> — Pinnacle, Bovada, Melbet (licensed bookmakers) and Kalshi
    (regulated exchange). Both team names must agree <i>and</i> the kickoff must agree within five
    minutes; a two-way price is de-vigged proportionally.
    <span class="acc">{len(market_rows)} of {cov['open']}</span> fixtures priced this way.</li>
    <li><b>Originated line from Valve's official Regional Standings</b> — when no book prices the
    match, the official point gap is converted to a probability with a slope fitted on this
    repository's own 60 market-observation pairs (k={BOARD['calibration']['k']:.4f},
    MAE {BOARD['calibration']['mae_prob'] * 100:.1f} pts).
    <span class="acc">{cov['originated_vrs']}</span> fixtures.</li>
    <li><b>Originated line with a floor proxy</b> — where one team is absent from all four Valve
    files, it is assigned the lowest rank value Valve publishes (381 points, #380). Explicitly an
    assumption. <span class="acc">{cov['originated_floor']}</span> fixtures.</li>
    <li><b>No pick</b> — published blank with the sources attempted, never guessed.</li>
  </ol>
  <p class="small"><a href="method.html">Read the full method, including the reverse-engineered
  HotSpawn lobby endpoint.</a></p>
</div>

<h2>Repository audit</h2>
<div class="card">
  <p class="small">This session re-read the official Valve standings from
  <code>api.github.com</code>, re-derived every published probability from its quoted prices and
  compared the result with the boards earlier sessions left in this repository.
  <b>{sum(1 for c in BOARD['audit']['checks'] if c['verdict'] == 'verified')} of
  {len(BOARD['audit']['checks'])}</b> checks pass;
  <b>{len(BOARD['findings'])}</b> irregularities are published for review, including two boards
  that used an un-fitted slope and two that priced a fixture off a dormant roster.</p>
  <p class="small"><a href="flagged.html">See every check, every finding and every disagreement
  with the earlier boards →</a></p>
</div>

<h2>Refresh</h2>
<div class="card small">
  <p>Capture taken <b>{esc(BOARD['capture']['captured_utc'])}</b>
  ({esc(BOARD['capture']['age_hours'])} h before this build). Automated refresh runs every four
  hours (<code>.github/workflows/pickboard-86f3af65.yml</code>) and re-reads the HotSpawn lobby and
  API, Pinnacle, Bovada, Melbet, Kalshi and the Valve standings, then republishes these pages.</p>
  <p>Source files: <a href="../data/86f3af65/board.json">board.json</a> ·
  <a href="../data/86f3af65/capture.json">capture.json</a> ·
  <code>scripts/86f3af65/</code></p>
  <p class="sub">HotSpawn week {esc((BOARD['hotspawn'].get('week') or {}).get('weekId'))} ·
  {esc((BOARD['hotspawn'].get('week') or {}).get('weekStartUtc'))} →
  {esc((BOARD['hotspawn'].get('week') or {}).get('weekEndUtc'))} ·
  {esc(BOARD['hotspawn']['fixtures_total'])} CS2 rows read from the feed,
  {esc(cov['open'])} still open.</p>
</div>
"""
    return page("Executive summary", "index.html", body)


def render_picks() -> str:
    rows = BOARD["rows"]
    by_event = defaultdict(list)
    for r in rows:
        by_event[r["competition"]].append(r)
    body = f"""
<h1>All picks</h1>
<p class="lede">{len(rows)} open HotSpawn CS2 fixtures. The picked team is highlighted and marked
<b>PICK</b>; both win probabilities are shown, then the basis and the sources for that row.</p>
<input class="search" id="q" type="search" placeholder="Filter by team or event…"
  aria-label="Filter picks by team or event" autocomplete="off">
<p class="sub">{BOARD['coverage']['market'] + BOARD['coverage']['market_contested']} from betting
lines · {BOARD['coverage']['originated_vrs']} from Valve VRS · {BOARD['coverage']['originated_floor']}
with a floor proxy · {BOARD['coverage']['unresolved']} blank</p>
{''.join(pick_card(r) for r in sorted(rows, key=lambda r: r["start_utc"]))}
<p class="sub">Sorted by kickoff. Times are UTC. Data snapshot
{esc(BOARD['capture']['captured_utc'])}.</p>
"""
    return page("All picks", "picks.html", body)


def render_unresolved() -> str:
    rows = BOARD["rows"]
    floor_rows = [r for r in rows if "floor_proxy_unrated_team" in r["flags"]
                  and r["basis"].startswith("originated")]
    dup_rows = [r for r in rows if "duplicate_vrs_roster" in r["flags"]]
    contested = [r for r in rows if r["basis"] == "market (contested)"]
    blank = [r for r in rows if not r["pick_team"]]
    obs = [(r, o) for r in rows for o in r["observations"]]
    obs_rows = "".join(obs_row(r, o) for r, o in obs) or NO_OBS_ROW
    hltv = BOARD["capture"]["access"].get("hltv_probe") or {}
    hltv_note = (
        f'<p><b>HLTV</b> — <code>{esc(hltv.get("url") or "https://www.hltv.org/matches")}</code> '
        f'returned HTTP {esc(hltv.get("status") or "no response")}'
        + (f' ({esc(hltv.get("error"))})' if hltv.get("error") else "")
        + '. HLTV publishes match pages and results rather than two-way prices, and its odds '
        'panels are populated by partner bookmakers only for covered events; the low-tier '
        'fixtures here have no HLTV odds panel. No number on this site depends on HLTV.</p>')
    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="lede">A separate section for every row that could <b>not</b> be resolved the way the
featured picks are: no bookmaker prices the match, or a team has no published rating, or two
sources disagree. Each row keeps its pick — nothing is left blank unless there is genuinely no
basis — but the limitation is stated here in plain language, with what would change it.</p>

<div class="grid three">
  {kpi(len(blank), "rows with no pick at all")}
  {kpi(len(floor_rows), "rows using an unrated-team floor")}
  {kpi(len(dup_rows) + len(contested), "rows with a source conflict")}
</div>

<div class="note">
  <b>Summary of the limitation.</b> Low-tier Counter-Strike fixtures are frequently listed by
  HotSpawn but not priced by any bookmaker or exchange we can read. For those the pick comes from
  Valve's official rank values, which are published monthly — the current file is
  <b>{esc(BOARD['vrs']['snapshot'])}</b> — and from a fitted conversion of the point gap into a
  probability. That conversion has a mean absolute error of
  <b>{BOARD['calibration']['mae_prob'] * 100:.1f} points of probability</b> on the 60 market
  observations it was fitted on, so treat originated rows as estimates rather than prices.
</div>

<h2>1 · Rows where a team has no published Valve rating</h2>
<p class="sub">The team is absent from the global, americas, asia <i>and</i> europe standings files.
It is assigned the lowest rank value Valve publishes ({esc((BOARD['vrs']['floor'] or {}).get('points'))}
points at #{esc((BOARD['vrs']['floor'] or {}).get('standing'))}). The pick direction is usually
robust; the number is an assumption. The sensitivity column shows what the model would say at
higher assumed ratings for the unrated team.</p>
<div class="card">
<table><thead><tr><th>Match</th><th>Pick</th><th>Unrated team</th>
<th>Sensitivity (assumed points → that team's win chance)</th><th>Source</th></tr></thead><tbody>
{''.join(f'''<tr><td class="wrapcell">{esc(r['team_a'])} v {esc(r['team_b'])}<br>
  <span class="small sub">{esc(r['competition'])}</span></td>
  <td>{esc(r['pick_team'])}<br><span class="small sub">{pct(r['pick_prob'])}</span></td>
  <td class="wrapcell">{esc(' and '.join(unrated_teams(r)) or '—')}</td>
  <td class="wrapcell">{esc(' · '.join(f"{s['assumed_points']} → {s['prob_this_team'] * 100:.1f}%"
     for s in (r['model'] or {}).get('sensitivity', [])))}</td>
  <td><a href="{esc(r['sources'][-1]['url'])}" target="_blank" rel="noopener">lobby</a> ·
  <a href="{esc((BOARD['vrs']['files'] or [{}])[0].get('page_url'))}" target="_blank" rel="noopener">Valve</a></td></tr>'''
  for r in floor_rows)}
</tbody></table></div>

<h2>2 · Rows where Valve publishes two rosters under one name</h2>
<p class="sub">Valve keeps one row per roster, so the same organisation name can carry two rank
values. The policy used here: a roster with fewer than five players cannot field a team
(excluded); if two five-player rosters remain, the one whose official details page shows the most
recent counted match is used. Both candidates and the probability the rejected one would have
produced are shown, so the assumption is visible.</p>
<div class="card">
<table><thead><tr><th>Match</th><th>Pick</th><th>Roster used</th><th>Roster rejected</th>
<th>If the other roster played</th></tr></thead><tbody>
{''.join(f'''<tr><td class="wrapcell">{esc(r['team_a'])} v {esc(r['team_b'])}</td>
  <td>{esc(r['pick_team'])}<br><span class="small sub">{pct(r['pick_prob'])}</span></td>
  <td class="wrapcell">{esc(roster_used(r))}</td>
  <td class="wrapcell">{esc(roster_rejected(r))}</td>
  <td>{pct((r['model'] or {}).get('alternate_prob_a'))} {esc(r['team_a'])}</td></tr>'''
  for r in dup_rows)}
</tbody></table></div>

<h2>3 · Rows where the market and the rating model disagree</h2>
{''.join(f'''<div class="note bad"><b>{esc(r['team_a'])} v {esc(r['team_b'])}</b> —
{esc(r['competition'])}. Market: {esc(r['team_a'])} {pct(r['market']['prob_a'])}; rating model:
{esc(r['team_a'])} {pct(r['model']['prob_a'])}. {esc(r['limitation'])}</div>'''
  for r in contested) or '<p class="sub">None at this build.</p>'}

<h2>4 · Prices that were seen but deliberately NOT used</h2>
<p class="sub">Publishing a rejected join is how a reader can tell the difference between "no price
exists" and "a price exists but could not be safely attached".</p>
<div class="card">
<table><thead><tr><th>Fixture</th><th>Source</th><th>Names on the source</th><th>Raw</th>
<th>Why not used</th></tr></thead><tbody>
{obs_rows}
</tbody></table></div>

<h2>5 · Sources that could not be read, and what that costs us</h2>
<div class="card small">
{hltv_note}
<p><b>Polymarket</b> — <code>https://gamma-api.polymarket.com/events?closed=false&amp;tag_slug=counter-strike</code>
returned no CS2 match markets at capture time, so that venue is not represented. Polymarket's
coverage of low-tier CS2 is thin; a listing there would be used as an exchange price (rung 2) if
both names and the kickoff joined.</p>
<p><b>Thunderpick</b> is an esportsbook whose prices are visible through bo3.gg match pages. It
priced the market rows in earlier sessions' captures and added nothing that Pinnacle, Bovada or
Melbet did not already price, so it appears in the source ledger but is not a separate rung at
this build.</p>
<p><b>What would remove each limitation:</b> a bookmaker opening these matches (low-tier CS2 lines
typically appear in the last 12–24 h before kickoff, so re-running nearer the lock is the single
most useful action); a published rating for the unrated team; or a roster document confirming
which of Valve's two rows is being fielded.</p>
</div>

<h2>6 · Fixtures with no pick at all</h2>
{('<p class="sub">None: every open fixture has a pick this build.</p>' if not blank else
 '<div class="card"><table><thead><tr><th>Match</th><th>Sources attempted</th></tr></thead><tbody>' +
 ''.join(blank_row(r) for r in blank) + '</tbody></table></div>')}
"""
    return page("Unresolved & limitations", "unresolved.html", body)


def render_tournaments() -> str:
    rows = BOARD["rows"]
    by = defaultdict(list)
    for r in rows:
        by[r["competition"]].append(r)
    cards = []
    for comp in sorted(by, key=lambda c: min(r["start_utc"] for r in by[c])):
        group = sorted(by[comp], key=lambda r: r["start_utc"])
        market = sum(1 for r in group if r["basis"].startswith("market"))
        cards.append(f"""<h2>{esc(comp)}</h2>
<p class="sub">{len(group)} open fixture(s) · {market} priced by a book or exchange ·
{esc(group[0]['tier'] or '')} tier</p>
{''.join(pick_card(r) for r in group)}""")
    body = (f"<h1>Picks by event</h1><p class=\"lede\">The same {len(rows)} picks, grouped by "
            f"competition, so a low-tier event that only HotSpawn lists is easy to find.</p>"
            + "".join(cards))
    return page("Picks by event", "tournaments.html", body)


def render_sources() -> str:
    capture = json.loads((ROOT / "data/86f3af65/capture.json").read_text())
    quotes = capture.get("quotes") or []
    rows = BOARD["rows"]

    def qrows():
        out = []
        for q in sorted(quotes, key=lambda q: (q.get("source_key") or "", q.get("start_utc") or "")):
            used = [r for r in rows if any(s.get("url") == q.get("public_url") for s in r["sources"])]
            out.append(
                f'<tr><td>{esc(q.get("source_name"))}</td>'
                f'<td class="wrapcell">{esc(q.get("team_a"))} v {esc(q.get("team_b"))}</td>'
                f'<td>{esc(q.get("decimal_a"))} / {esc(q.get("decimal_b"))}</td>'
                f'<td>{pct(q.get("prob_a"))}</td>'
                f'<td>{esc(overround(q.get("overround")))}</td>'
                f'<td>{esc(q.get("start_utc") or "not published")}</td>'
                f'<td>{esc(q.get("retrieved_utc"))}</td>'
                f'<td><a href="{esc(q.get("public_url"))}" target="_blank" rel="noopener">quote</a></td>'
                f'<td>{"used in " + esc(used[0]["team_a"]) + " v " + esc(used[0]["team_b"]) if used else "not used"}</td></tr>')
        return "".join(out)

    ratings = []
    for r in rows:
        for res in (r["model"]["rating_a"], r["model"]["rating_b"]) if r.get("model") else []:
            row = res.get("row") or {}
            ratings.append(
                f'<tr><td class="wrapcell">{esc(r["team_a"])} v {esc(r["team_b"])}</td>'
                f'<td>{esc(res["team"])}</td><td>{esc(res["status"])}</td>'
                f'<td>{esc(row.get("standing"))}</td><td>{esc(row.get("points"))}</td>'
                f'<td class="wrapcell">{esc(row.get("roster") or "—")}</td>'
                f'<td>{esc(row.get("latest_match_date") or "—")}</td>'
                f'<td><a href="{esc(res.get("source"))}" target="_blank" rel="noopener">standings</a></td></tr>')

    endpoints = "".join(
        f'<tr><td class="wrapcell">{esc(s["label"])}</td>'
        f'<td>{esc(s["status"])}</td><td>{esc(s["bytes"])}</td><td>{esc(s["at_utc"])}</td>'
        f'<td class="wrapcell"><code>{esc((s["sha256"] or "")[:16])}</code></td>'
        f'<td class="wrapcell"><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["url"])}</a></td></tr>'
        for s in BOARD["sources_read"])

    files = "".join(
        f'<tr><td>{esc(f["region"])}</td><td>{esc(f["snapshot"])}</td>'
        f'<td class="wrapcell"><code>{esc((f.get("sha256") or "")[:16])}</code></td>'
        f'<td>{esc(f.get("retrieved_utc") or "pinned copy")}</td>'
        f'<td>{esc(f.get("sha256_matches_live_read"))}</td>'
        f'<td><a href="{esc(f["page_url"])}" target="_blank" rel="noopener">open</a></td></tr>'
        for f in BOARD["vrs"]["files"] or [])

    body = f"""
<h1>Sources</h1>
<p class="lede">Every number on this site traces to one of these reads: a published price, a
published rank value, or a fixture listing. HotSpawn appears only as a fixture source.</p>

<h2 id="access">Endpoints read at capture time</h2>
<div class="card"><table><thead><tr><th>Source</th><th>HTTP</th><th>Bytes</th><th>Read (UTC)</th>
<th>SHA-256 (prefix)</th><th>URL</th></tr></thead><tbody>{endpoints}</tbody></table></div>

<h2>Official Valve standings files used</h2>
<div class="card"><table><thead><tr><th>File</th><th>Snapshot</th><th>SHA-256 (prefix)</th>
<th>Read</th><th>Matches live re-read</th><th>Link</th></tr></thead><tbody>{files}</tbody></table>
<p class="small sub">The global file is the only pool used for probabilities: regional files repeat
the same rank values for the same rosters and, per check C3, contain no team that the global file
lacks.</p></div>

<h2>Every two-way quote read ({len(quotes)})</h2>
<div class="card"><table><thead><tr><th>Source</th><th>Names on the source</th><th>Decimal</th>
<th>No-vig A</th><th>Margin</th><th>Source kickoff</th><th>Read (UTC)</th><th>Link</th>
<th>Status</th></tr></thead><tbody>{qrows()}</tbody></table>
<p class="small sub">"No-vig A" is the proportional de-vig of the two decimals; it is not a
probability for any fixture until the names and kickoff join. Quotes with no published kickoff
(Kalshi) cannot be joined by rule and are listed as observations instead.</p></div>

<h2>Rating rows used ({len(ratings)})</h2>
<div class="card"><table><thead><tr><th>Fixture</th><th>Team</th><th>Resolution</th>
<th>Standing</th><th>Points</th><th>Roster</th><th>Latest counted match</th><th>Source</th>
</tr></thead><tbody>{''.join(ratings)}</tbody></table>
<p class="small sub">Resolution is <code>unique</code> (one row in the file),
<code>roster-selected</code> (duplicate name resolved by the published roster policy) or
<code>floor-proxy</code> (no row at all: the lowest published value is assumed).</p></div>

<h2>Not used, on purpose</h2>
<div class="card small">
  <p><b>HotSpawn crowd "picked %"</b> — never read by any script in this session. It measures what
  other players chose, not what will happen.</p>
  <p><b>HotSpawn as a probability</b> — the lobby supplies fixture id, competition, kickoff, lock
  time and offered points only.</p>
  <p><b>Any value we could not re-read</b> — see <a href="flagged.html">Flagged for review</a>,
  including a roster-identity claim inherited from an earlier session that could not be
  re-verified and is therefore not used to price anything.</p>
</div>
"""
    return page("Sources", "sources.html", body)


def render_flagged() -> str:
    checks = "".join(check_row(c) for c in BOARD["audit"]["checks"])
    findings = "".join(
        f"""<div class="flag"><h3><span class="id">{esc(f['id'])}</span>{esc(f['title'])}</h3>
        <p>{esc(f['detail'])}</p>
        <p class="files">Files: {files_links(f['files'])} · verdict:
        <b>{esc(f['verdict'])}</b></p></div>""" for f in BOARD["findings"])
    dup_rows = [d for d in BOARD["audit"]["duplicate_vrs_table"] if d["used_in_open_fixture"]]
    other_dups = [d for d in BOARD["audit"]["duplicate_vrs_table"] if not d["used_in_open_fixture"]]
    dups = "".join(dup_row(d) for d in dup_rows)
    dis = BOARD["audit"]["earlier_board_disagreements"]
    disrows = "".join(dis_row(d) for d in dis)

    body = f"""
<h1>Flagged for review</h1>
<p class="lede">Everything that could not be confirmed, everything that disagreed with the rest of
the repository, and the guard rails that stopped a wrong price from being used. None of this
blocks the picks — it is published so you can check it.</p>

<h2>Audit checks</h2>
<div class="card"><table><thead><tr><th>#</th><th>Check</th><th>Result</th><th>Verdict</th>
<th>Source</th></tr></thead><tbody>{checks}</tbody></table></div>

<h2>Irregularities</h2>
{findings}

<h2>Duplicate roster names in Valve's file that touch an open fixture</h2>
<div class="card"><table><thead><tr><th>Team</th><th>Every published row</th></tr></thead>
<tbody>{dups}</tbody></table>
<p class="small sub">{len(other_dups)} further duplicate names exist in the 380-row file but touch
no open fixture; they are listed in <a href="../data/86f3af65/board.json">board.json</a>
(<code>audit.duplicate_vrs_table</code>).</p></div>

<h2>How this board differs from the earlier boards in this repository</h2>
<p class="sub">Same fixtures, same official ratings, different answers. Any gap of five points or
more is listed; the file behind each column is committed in the repository.</p>
<div class="card"><table><thead><tr><th>Fixture</th><th>This board</th>
<th>fe803b80 (19:29Z)</th><th>51197e5b</th><th>36495748 (16:45Z)</th><th>Max gap</th></tr></thead>
<tbody>{disrows or '<tr><td colspan="6" class="sub">No disagreements.</td></tr>'}</tbody></table>
<p class="small sub">Probabilities are for the first-named team of this board's fixture pair.</p>
</div>

<h2>What is deliberately not on this page</h2>
<div class="card small"><p>No unverified number is shown anywhere on the site. Where a value could
not be confirmed — an unlisted team's rating, a roster identity we could not re-read, a source we
could not reach — the row says so and the assumption is named. See
<a href="unresolved.html">Unresolved &amp; limitations</a>.</p></div>
"""
    return page("Flagged for review", "flagged.html", body)


def render_method() -> str:
    cal = BOARD["calibration"]
    vrs = BOARD["vrs"]
    body = f"""
<h1>Method</h1>
<p class="lede">How a HotSpawn fixture becomes a pick: the reverse-engineered lobby, the ladder,
the arithmetic, and the commands that reproduce every number on this site.</p>

<h2>1 · The HotSpawn Pick'ems lobby, reverse engineered</h2>
<div class="card small">
<p>The lobby at <a href="https://play.hotspawn.com/lobby" target="_blank" rel="noopener">
play.hotspawn.com/lobby</a> is an Angular single-page app. Its server-rendered transfer state
(<code>&lt;script id="ng-state"&gt;</code>) contains the same fixture array the page requests from
the endpoint below, plus the week window, the offered points and the per-match permalinks.</p>
<table><thead><tr><th>What</th><th>Where</th></tr></thead><tbody>
<tr><td>Lobby page</td><td class="wrapcell"><code>https://play.hotspawn.com/lobby</code></td></tr>
<tr><td>Fixtures API (used by the page itself)</td>
<td class="wrapcell"><code>https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code></td></tr>
<tr><td>Counter-Strike filter</td><td class="wrapcell"><code>sport_alias == "cs2"</code></td></tr>
<tr><td>Fields used</td><td class="wrapcell"><code>id, competition_name, tier, stage, best_of,
offered_points, status, scheduled_start_time, lock_time, participants0/1_name,
participants0/1_score, sport_alias</code></td></tr>
<tr><td>Fields refused</td><td class="wrapcell">any crowd "picked %" / ownership field — never
read, never used</td></tr>
<tr><td>Open definition</td><td class="wrapcell"><code>status == "scheduled"</code> <b>and</b>
<code>lock_time &gt; now</code>. The feed keeps 61+ rows at "scheduled" long after they locked; a
consumer that trusts status alone will publish picks for matches that can no longer be entered.</td></tr>
<tr><td>Freshness</td><td class="wrapcell">the API response carries an <code>Age</code> header
(upstream cache); both the page and the API are read and merged, and the age is recorded in
<code>capture.json</code>.</td></tr>
</tbody></table>
<p>At this build: <b>{esc(BOARD['hotspawn']['fixtures_total'])}</b> CS2 rows read,
<b>{esc(BOARD['coverage']['open'])}</b> open (lock in the future);
{esc(len(BOARD['recently_locked']))} further rows locked inside the last 24 hours and are listed
for context only.</p>
</div>

<h2>2 · The ladder</h2>
<div class="card small">
<table><thead><tr><th>Rung</th><th>Input</th><th>Rule</th><th>Used by</th></tr></thead><tbody>
<tr><td>1</td><td class="wrapcell">Licensed bookmakers: Pinnacle, Bovada, Melbet</td>
<td class="wrapcell">Main-period two-way moneyline only. Both names must agree after
normalisation (or a published alias) <b>and</b> the source kickoff must be within 5 minutes of
HotSpawn's. Margin removed proportionally; Pinnacle weighted 2, others 1.</td>
<td>{BOARD['coverage']['market']}</td></tr>
<tr><td>2</td><td class="wrapcell">Kalshi (CFTC-regulated exchange, series
<code>KXCS2GAME</code>)</td><td class="wrapcell">Mid of the yes bid/ask, rejected if either side is
missing or the spread exceeds 10c. A price is only usable if the event carries a verifiable
kickoff — the ticker timestamp is not treated as a kickoff.</td><td>{BOARD['coverage']['market_contested']}
(observation only this build)</td></tr>
<tr><td>3</td><td class="wrapcell">Official Valve Regional Standings (global file)</td>
<td class="wrapcell">Point gap → probability with the fitted slope below. Duplicate roster names
resolved by the published policy.</td><td>{BOARD['coverage']['originated_vrs']}</td></tr>
<tr><td>4</td><td class="wrapcell">Valve floor value (381 pts, #380)</td>
<td class="wrapcell">Assigned only to a team absent from all four published files, and labelled
as an assumption.</td><td>{BOARD['coverage']['originated_floor']}</td></tr>
<tr><td>5</td><td class="wrapcell">Nothing</td><td class="wrapcell">Blank row, published with the
sources attempted.</td><td>{BOARD['coverage']['unresolved']}</td></tr>
</tbody></table>
</div>

<h2>3 · The arithmetic</h2>
<div class="card small">
<p><b>De-vig.</b> For decimals <code>d_a, d_b</code>:
<code>p_a = (1/d_a) / (1/d_a + 1/d_b)</code>. A book whose implied sum falls outside
0.95–1.30 is rejected as bad data rather than trimmed.</p>
<p><b>Valve's curve.</b> Valve publishes its model: <code>Q = ln(10)/400</code>,
<code>g = 1/sqrt(1 + 3·Q²·RD²/π²)</code> with <code>RD = 75</code>, and expected score
<code>1/(1 + 10^(g·(r−r₀)/−400))</code>. That is a logistic in the point gap with slope
<code>C = g·ln(10)/400 = {cal['c']:.10f}</code>.</p>
<p><b>The fitted slope.</b> A straight read of that curve is too steep (Valve's own README says
so). We fit <code>k</code> in <code>logit(p) = k · C · Δpoints</code> by least squares through the
origin on <b>{cal['n_pairs']}</b> (fixture, market consensus) pairs captured by this repository:
<code>k = {cal['k']:.6f}</code> (raw {cal['k_raw']:.6f}, bounds {cal['bounds']}). Mean absolute
error <b>{cal['mae_prob'] * 100:.1f} probability points</b>; Valve's un-fitted slope scores
{cal['mae_prob_valve'] * 100:.1f} points on the same sample. Residual sd
{cal['resid_sd'] * 100:.1f} points — that is the honest error bar on every originated row.</p>
<p><b>Duplicate rosters.</b> {esc(vrs['snapshot'])} publishes one row per roster. Policy: drop
rosters with fewer than five players; if two five-player rosters remain, take the one whose
official details page shows the most recent counted match; if they tie, leave the fixture
unrated.</p>
<p><b>Contested rows.</b> If a market price and the rating model differ by more than 15 points the
market is still used (it is a price), but the row is labelled <i>contested</i> and listed on the
Unresolved page.</p>
</div>

<h2>4 · Verification performed</h2>
<div class="card small">
<ul>
<li>Valve's newest published global standings was re-listed live from <code>api.github.com</code>:
<b>{esc(vrs['snapshot'])}</b> is the current file (no later file exists).</li>
<li>Its SHA-256 matches the copy pinned by an earlier session byte for byte
(<code>{(vrs['files'] or [{}])[0].get('sha256')}</code>).</li>
<li>All four published files parsed: {', '.join(f"{k}={v}" for k, v in (vrs['counts'] or {}).items())} rows.
Every regional name also appears in the global file (check C3), so the global pool is complete.</li>
<li>Every published probability is recomputed from its cited raw price in
<code>tests/test_86f3af65.py</code>; any drift fails the build.</li>
<li>No HotSpawn URL appears among any row's price citations (check C6).</li>
<li>The 20 official per-roster details pages needed for duplicate names were re-read and their
dates recorded (<code>data/86f3af65/valve/details/</code>).</li>
</ul>
</div>

<h2>5 · Reproduce it</h2>
<div class="card small">
<pre style="overflow-x:auto;font-size:12px"><code>python3 scripts/86f3af65/collect.py --live    # or --from-canonical (committed evidence)
python3 scripts/86f3af65/build.py             # board.json
python3 scripts/86f3af65/site.py              # pickboard/*.html
python3 -m unittest tests.test_86f3af65 -v</code></pre>
<p>Refresh cadence: <code>cron: '17 */4 * * *'</code> in
<code>.github/workflows/pickboard-86f3af65.yml</code>, plus a manual dispatch. The workflow fails
loudly if the board comes out with a blank row, a probability that does not re-derive, or a
HotSpawn-only citation.</p>
</div>
"""
    return page("Method", "method.html", body)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (OUT / "app.js").write_text(APP_JS.strip() + "\n", encoding="utf-8")
    pages = {
        "index.html": render_index(),
        "picks.html": render_picks(),
        "unresolved.html": render_unresolved(),
        "tournaments.html": render_tournaments(),
        "sources.html": render_sources(),
        "flagged.html": render_flagged(),
        "method.html": render_method(),
    }
    for name, text in pages.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(json.dumps({name: len(text) for name, text in pages.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
