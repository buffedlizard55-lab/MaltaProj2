#!/usr/bin/env python3
"""Session c0e223d3 — build the `summary/` executive hub for the MaltaProj2 dashboard.

Reads only data that other sessions already published (it never re-collects and never writes to
another session's directory):

  * `data/f7279a54/board.json`  - the OURLINE pick board (market lines + rating model)
  * `data/expanded/vrs/*.md`    - Valve's official regional standings capture
  * `scripts/c0e223d3/aliases.py` - team-name resolutions verified against official sources

Writes `summary/**` and `data/c0e223d3/board.json`.

Rules honoured here:
  * A row without a confirmed external price AND without an official rating for BOTH teams stays
    blank and is published on the gaps page. Nothing is inferred.
  * Every row carries at least one link to an official source.
  * Pick probabilities taken from the OURLINE board are reproduced, not recomputed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "c0e223d3"))

import core  # noqa: E402
import aliases  # noqa: E402

OUT = ROOT / "summary"
DATA = ROOT / "data" / "c0e223d3"

OUR_BOARD = ROOT / "data" / "f7279a54" / "board.json"
LIVE_BOARD = ROOT / "data" / "live" / "board.json"

VALVE_PAGE_URL = aliases.VALVE_FILE_PAGE
VALVE_API_URL = aliases.VALVE_FILE_API
HLTV_ELISA = aliases.HLTV_ELISA_EVENT

# ---------------------------------------------------------------------------------- site map
# The hub's job is to answer "where do I find the picks?" on a phone. Each card is checked for
# existence at build time and only rendered when the page really ships.
SITE_SECTIONS = [
    {
        "href": "index.html",
        "title": "Every open pick",
        "blurb": "One row per CS2 match that is still open on HotSpawn, with the pick, the "
                 "probability and the official source link.",
        "badge": "Start here",
    },
    {
        "href": "../ourline/index.html",
        "title": "Our line",
        "blurb": "The model board: a probability and a pick for every open fixture, including "
                 "the ones with no bookmaker price. Graded track record included.",
        "badge": "Model",
    },
    {
        "href": "../probabilities.html",
        "title": "Probabilities (strict)",
        "blurb": "Only rows with an eligible primary-bookmaker price. Everything else is left "
                 "blank on purpose.",
        "badge": "Strict",
    },
    {
        "href": "../cs2.html",
        "title": "CS2 inventory",
        "blurb": "The exact CS2 fixture list embedded in the HotSpawn lobby, split into open "
                 "picks and listed-but-closed rows.",
        "badge": "Inventory",
    },
    {
        "href": "../live/index.html",
        "title": "Live coverage board",
        "blurb": "Session 3cd9787c's lobby-listed board with per-row source links.",
        "badge": "Board",
    },
    {
        "href": "../coverage/index.html",
        "title": "Coverage board",
        "blurb": "Session 6ddde224's board: closes the remaining uncovered pickable fixtures "
                 "with extra line sources and a fitted rating model.",
        "badge": "Board",
    },
    {
        "href": "../market/index.html",
        "title": "Expanded market board",
        "blurb": "Session a0586093's wider market sweep across every listed event.",
        "badge": "Board",
    },
    {
        "href": "../fresh/index.html",
        "title": "Fresh board",
        "blurb": "Session dd2b7fee's mobile board, priced from Bovada / Pinnacle / Kalshi only.",
        "badge": "Board",
    },
    {
        "href": "gaps.html",
        "title": "Uncovered matches",
        "blurb": "Every match with no bookmaker price, what we could and could not confirm, and "
                 "the official links to check it yourself.",
        "badge": "Flagged",
    },
    {
        "href": "../flagged.html",
        "title": "Flagged for review",
        "blurb": "All open gaps, stale quotes, rejected joins and access failures across the "
                 "whole site.",
        "badge": "Flagged",
    },
    {
        "href": "sources.html",
        "title": "Sources",
        "blurb": "Every source used anywhere on this site, with the exact URL and the UTC time "
                 "it was read.",
        "badge": "Evidence",
    },
    {
        "href": "method.html",
        "title": "Method",
        "blurb": "Where the numbers come from, the formula, and the limits of the model.",
        "badge": "Method",
    },
    {
        "href": "repo-review.html",
        "title": "Repository review",
        "blurb": "Line-by-line review of the repo with irregularities flagged for manual review.",
        "badge": "Review",
    },
]


# ---------------------------------------------------------------------------------- row build
def resolve_vrs(team_name: str, valve_by_name: dict):
    """Return (row, resolution_entry_or_None, notes, resolved_name_or_None)."""
    direct = valve_by_name.get((team_name or "").strip().casefold())
    if direct:
        return direct, None, [], None
    entry = aliases.by_hotspawn_name(team_name)
    if entry and entry.get("valve_name"):
        resolved = valve_by_name.get(entry["valve_name"].casefold())
        if resolved:
            return (
                resolved,
                entry,
                [f'name resolved: HotSpawn "{entry["hotspawn_name"]}" = Valve "{entry["valve_name"]}"'],
                entry["valve_name"],
            )
    return None, entry, [], None


def build_rows(our_board: dict, valve_by_name: dict, k: float):
    rows = []
    for fx in our_board.get("open", []):
        line = fx.get("line") or {}
        basis = line.get("basis")
        prob_a = line.get("prob_a")
        prob_b = line.get("prob_b")
        pick_team = line.get("pick_team")
        source_links = []
        notes: list[str] = []
        flags = list(fx.get("flags") or [])
        resolved_entries = []

        # Name resolution runs for every row, because a stale "not_in_vrs:<team>" flag inherited
        # from the upstream board must be corrected even on rows that already have a market price.
        va, ea, na, ra = resolve_vrs(fx.get("team_a"), valve_by_name)
        vb, eb, nb, rb = resolve_vrs(fx.get("team_b"), valve_by_name)
        for team, resolved_name in ((fx.get("team_a"), ra), (fx.get("team_b"), rb)):
            if resolved_name:
                flags = [f for f in flags if f != f"not_in_vrs:{team}"]
                flags.append(f"name_resolved:{team}={resolved_name}")

        # 1. Reproduce what the OURLINE board already publishes.
        if basis and prob_a is not None:
            for q in fx.get("quotes", []):
                if q.get("public_url"):
                    source_links.append({"label": q.get("source_name", "source"), "url": q["public_url"]})
            notes.append(f"published by the Our line board, basis: {basis}")
        else:
            # 2. Otherwise try to originate one from Valve's official ratings.
            notes += na + nb
            for e in (ea, eb):
                if e:
                    resolved_entries.append(e)
            if va and vb:
                prob_a = core.vrs_prob(va["points"], vb["points"], k)
                prob_b = 1.0 - prob_a
                pick_team = fx["team_a"] if prob_a >= prob_b else fx["team_b"]
                basis = "vrs-resolved"
                source_links.append({"label": "Valve regional standings (official)", "url": VALVE_PAGE_URL})
                for e in resolved_entries:
                    for ev in e.get("evidence", []):
                        if ev.get("url"):
                            source_links.append({"label": ev["source"], "url": ev["url"]})
                flags = [f for f in flags if f != "no_line_unverified"]
                flags.append("originated_estimate_not_a_market_price")
            else:
                prob_a = prob_b = None
                pick_team = None
                basis = "none"
                source_links.append({"label": "Valve regional standings (official)", "url": VALVE_PAGE_URL})
                for e in resolved_entries:
                    for ev in e.get("evidence", []):
                        if ev.get("url"):
                            source_links.append({"label": ev["source"], "url": ev["url"]})
                missing = [
                    t
                    for t, v in ((fx.get("team_a"), va), (fx.get("team_b"), vb))
                    if v is None
                ]
                for team in missing:
                    flags.append(f"no_official_rating:{team}")
                flags = [f for f in flags if f != "no_line_unverified"]

        # Always carry the HotSpawn official page for the fixture itself.
        hs = fx.get("hotspawn_url") or "https://play.hotspawn.com/lobby"
        source_links.insert(0, {"label": "HotSpawn (fixture listing)", "url": hs})

        rows.append(
            {
                "fixture_id": fx.get("fixture_id"),
                "competition": fx.get("competition"),
                "tier": fx.get("tier"),
                "start_utc": fx.get("start_utc"),
                "lock_utc": fx.get("lock_utc"),
                "team_a": fx.get("team_a"),
                "team_b": fx.get("team_b"),
                "best_of": fx.get("best_of"),
                "basis": basis,
                "prob_a": prob_a,
                "prob_b": prob_b,
                "pick_team": pick_team,
                "pick_prob": max(prob_a, prob_b) if prob_a is not None else None,
                "confidence": core.confidence_label(max(prob_a, prob_b)) if prob_a is not None else None,
                "source_links": source_links,
                "hotspawn_url": hs,
                "hotspawn_url_kind": fx.get("hotspawn_url_kind"),
                "notes": notes,
                "flags": sorted(set(flags)),
                "resolved": [
                    {"hotspawn_name": e["hotspawn_name"], "valve_name": e["valve_name"],
                     "status": e["status"], "evidence": e["evidence"]}
                    for e in resolved_entries
                ],
            }
        )
    rows.sort(key=lambda r: (r["start_utc"] or "", r["fixture_id"] or ""))
    return rows


# --------------------------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0e1116;--card:#161b22;--card2:#1c232d;--line:#2a333f;--fg:#e6edf3;--mut:#9aa7b4;
--acc:#4ade80;--acc2:#60a5fa;--warn:#fbbf24;--bad:#f87171;--radius:14px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc2)}
.wrap{max-width:1080px;margin:0 auto;padding:16px 14px 56px}
header.top{background:linear-gradient(180deg,#131a24,#0e1116);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:5}
header.top .wrap{padding-top:12px;padding-bottom:12px;display:flex;gap:10px;align-items:center;
justify-content:space-between;flex-wrap:wrap}
.brand{font-weight:700;font-size:17px;letter-spacing:.2px}
.brand span{color:var(--acc)}
nav.topnav{display:flex;gap:6px;flex-wrap:wrap;font-size:14px}
nav.topnav a{display:inline-block;padding:7px 11px;border-radius:999px;background:var(--card2);
color:var(--fg);text-decoration:none;border:1px solid var(--line)}
nav.topnav a.on{background:var(--acc);color:#06210f;border-color:var(--acc);font-weight:600}
h1{font-size:26px;line-height:1.2;margin:6px 0 8px}
h2{font-size:19px;margin:26px 0 10px;padding-top:6px}
h3{font-size:16px;margin:18px 0 8px}
p.sub{color:var(--mut);margin:0 0 14px}
.note{background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--acc2);
border-radius:10px;padding:11px 13px;margin:12px 0;font-size:14px}
.warn{background:#241d0e;border:1px solid #4a3a12;border-left:3px solid var(--warn);
border-radius:10px;padding:11px 13px;margin:12px 0;font-size:14px}
.bad{background:#261415;border:1px solid #4a2022;border-left:3px solid var(--bad);
border-radius:10px;padding:11px 13px;margin:12px 0;font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:14px 0 6px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:12px}
.kpi b{display:block;font-size:26px;line-height:1.1}
.kpi span{color:var(--mut);font-size:12.5px;text-transform:uppercase;letter-spacing:.4px}
.cards{display:grid;grid-template-columns:1fr;gap:10px}
.card{display:block;background:var(--card);border:1px solid var(--line);
border-radius:var(--radius);padding:13px 14px;text-decoration:none;color:var(--fg)}
.card:active,.card:hover{border-color:var(--acc)}
.card b{display:block;font-size:15.5px;margin-bottom:3px}
.card span{color:var(--mut);font-size:13.5px;display:block}
.card em{font-style:normal;display:inline-block;margin-top:8px;font-size:11.5px;
text-transform:uppercase;letter-spacing:.5px;color:var(--acc);border:1px solid var(--acc);
border-radius:999px;padding:2px 8px}
table{width:100%;border-collapse:collapse;font-size:14px}
.tbl-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--card)}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--card2);font-size:12px;text-transform:uppercase;letter-spacing:.4px;
color:var(--mut);white-space:nowrap}
tr:last-child td{border-bottom:none}
.pick{color:var(--acc);font-weight:700}
.bar{height:7px;border-radius:4px;background:#2b3440;overflow:hidden;min-width:74px;margin-top:5px}
.bar i{display:block;height:100%;background:var(--acc)}
.small{font-size:12.5px;color:var(--mut)}
.srclist{margin:4px 0 0;padding:0;list-style:none}
.srclist li{margin:2px 0;font-size:12.5px;word-break:break-word}
code{background:#0b0f14;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:13px}
footer{border-top:1px solid var(--line);margin-top:34px;padding-top:14px;color:var(--mut);font-size:13px}
ul.tight{margin:6px 0;padding-left:20px}
ul.tight li{margin:4px 0}
@media(min-width:700px){
 .kpis{grid-template-columns:repeat(4,1fr)}
 .cards{grid-template-columns:repeat(2,1fr)}
 h1{font-size:32px}
}
@media(max-width:699px){
 /* Phone: turn the wide table into stacked, readable cards. */
 .tbl-wrap,table,thead,tbody,tr,td{display:block;width:100%}
 thead{display:none}
 tr{border-bottom:1px solid var(--line);padding:11px 12px}
 td{border:none;padding:2px 0}
 td::before{content:attr(data-l);color:var(--mut);font-size:11.5px;text-transform:uppercase;
 letter-spacing:.4px;display:block;margin-top:8px}
 td:first-child{padding-top:0}
 td:first-child::before{margin-top:0}
 td.hd{font-size:16.5px;font-weight:600;padding-bottom:4px}
 td.hd::before{display:none}
}
"""

NAV = [
    ("index.html", "Start here"),
    ("gaps.html", "Uncovered"),
    ("sources.html", "Sources"),
    ("method.html", "Method"),
    ("repo-review.html", "Repo review"),
]


def page(title: str, active: str, body: str, sub: str = "") -> str:
    nav = "".join(
        f'<a href="{h}" class="{"on" if h == active else ""}">{core.esc(t)}</a>'
        for h, t in NAV
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{core.esc(title)}</title>
<meta name="description" content="HotSpawn Pick'ems CS2 pick hub with probabilities derived from external betting lines and official Valve / HLTV sources.">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="top"><div class="wrap">
  <div class="brand"><span>&#9679;</span> CS2 pick hub</div>
  <nav class="topnav">{nav}
    <a href="../index.html">Main dashboard</a>
  </nav>
</div></header>
<main class="wrap">
  <h1>{core.esc(title)}</h1>
  {"<p class='sub'>" + sub + "</p>" if sub else ""}
  {body}
  <footer>
    Built by session <code>c0e223d3</code>. Fixture discovery: the public
    <a href="https://play.hotspawn.com/lobby">HotSpawn Pick'ems lobby</a>. HotSpawn's own crowd
    &ldquo;picked %&rdquo; is never used as a probability. Probabilities are model estimates, not
    guarantees, and are not betting advice. 18+.
  </footer>
</main>
</body>
</html>
"""


def link_list(links: list[dict]) -> str:
    seen, out = set(), []
    for l in links:
        key = (l["url"], l["label"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f'<li><a href="{core.esc(l["url"])}" rel="nofollow noopener" target="_blank">'
                   f'{core.esc(l["label"])}</a></li>')
    return f'<ul class="srclist">{"".join(out)}</ul>'


def render_picks_table(rows: list[dict]) -> str:
    body = []
    for r in rows:
        if r["prob_a"] is None:
            prob = '<span class="small">No pick &mdash; see <a href="gaps.html">Uncovered</a></span>'
            bar = ""
        else:
            pa = f"{r['prob_a'] * 100:.1f}%"
            pb = f"{r['prob_b'] * 100:.1f}%"
            pick = r["pick_team"]
            prob = (
                f'<span class="pick">{core.esc(pick)}</span> to win '
                f'<b>{r["pick_prob"] * 100:.1f}%</b><br>'
                f'<span class="small">{core.esc(r["team_a"])} {pa} &middot; '
                f'{core.esc(r["team_b"])} {pb} &middot; {core.esc(r["confidence"])}</span>'
            )
            w = int(round(max(r["prob_a"], r["prob_b"]) * 100))
            bar = f'<div class="bar"><i style="width:{w}%"></i></div>'
        when = (r["start_utc"] or "").replace("T", " ").replace("Z", "Z")
        body.append(
            "<tr>"
            f'<td class="hd" data-l="Match">{core.esc(r["team_a"])}<br>'
            f'<span class="small">vs</span><br>{core.esc(r["team_b"])}'
            f'<br><span class="small">{core.esc(r["competition"])}</span></td>'
            f'<td data-l="Pick">{prob}{bar}</td>'
            f'<td data-l="How it was derived">{core.esc(core.basis_label(r["basis"]))}'
            + (f'<br><span class="small">{core.esc("; ".join(r["notes"]))}</span>' if r["notes"] else "")
            + "</td>"
            f'<td data-l="Start (UTC)">{core.esc(when)}</td>'
            f'<td data-l="Sources">{link_list(r["source_links"])}</td>'
            "</tr>"
        )
    return (
        '<div class="tbl-wrap"><table><thead><tr>'
        "<th>Match</th><th>Pick &amp; probability</th><th>Derived from</th>"
        "<th>Start (UTC)</th><th>Official sources</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


# -------------------------------------------------------------------------------------- pages
def build(rows, our_board, valve_meta, k, calibration, sections):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    (OUT / "assets" / "style.css").write_text(CSS, encoding="utf-8")

    generated = core.now_utc()
    total = len(rows)
    with_pick = sum(1 for r in rows if r["prob_a"] is not None)
    market = sum(1 for r in rows if r["basis"] in {"market", "market+model"})
    vrs_only = sum(1 for r in rows if r["basis"] in {"model", "vrs-resolved"})
    blank = total - with_pick

    board = {
        "session": "c0e223d3",
        "generated_utc": generated,
        "source_board": "data/f7279a54/board.json",
        "source_board_generated_utc": our_board.get("generated_utc"),
        "valve_snapshot": valve_meta,
        "calibration_used": calibration,
        "summary": {
            "open": total,
            "with_pick": with_pick,
            "market_priced": market,
            "rating_model": vrs_only,
            "no_pick_flagged": blank,
        },
        "rows": rows,
        "resolutions": aliases.RESOLUTIONS,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, sort_keys=False), encoding="utf-8")

    # ---------------------------------------------------------------- index
    cards = "".join(
        f'<a class="card" href="{core.esc(s["href"])}"><b>{core.esc(s["title"])}</b>'
        f'<span>{core.esc(s["blurb"])}</span><em>{core.esc(s["badge"])}</em></a>'
        for s in sections
    )
    kpis = (
        f'<div class="kpis">'
        f'<div class="kpi"><b>{total}</b><span>Open CS2 matches</span></div>'
        f'<div class="kpi"><b>{with_pick}</b><span>With a pick</span></div>'
        f'<div class="kpi"><b>{market}</b><span>Priced by a bookmaker</span></div>'
        f'<div class="kpi"><b>{blank}</b><span>Blank / flagged</span></div>'
        f"</div>"
    )
    src_age = core.hours_since(our_board.get("generated_utc"))
    age_txt = f"{src_age:.1f} h old" if src_age is not None else "unknown age"
    index_body = f"""
<p class="sub">Every CS2 match currently open for picks in the
<a href="https://play.hotspawn.com/lobby" rel="nofollow noopener" target="_blank">HotSpawn
Pick'ems lobby</a>, with the pick, the win probability and the official source behind it.
Built {core.esc(generated)} from the Our line board published
{core.esc(our_board.get("generated_utc") or "unknown")} ({core.esc(age_txt)}).</p>
{kpis}
<div class="note"><b>What changed in this section.</b> Six open matches had no pick at all because
the team names HotSpawn shows are not the names Valve and HLTV publish. Those names are now
resolved from official sources and shown with the evidence on the
<a href="gaps.html">Uncovered matches</a> page, so five of the six now carry a rating-model pick.
One match (<b>FORZE Reload vs LFO 10</b>) still has no official rating for LFO 10 anywhere we could
verify, so it stays blank and flagged &mdash; it is not guessed.</div>
<h2>Where to find the picks</h2>
<div class="cards">{cards}</div>
<h2>Every open pick</h2>
<p class="small">Sorted by start time. On a phone each row stacks into a card.</p>
{render_picks_table(rows)}
"""
    (OUT / "index.html").write_text(
        page("CS2 pick hub &mdash; start here", "index.html",
             index_body,
             "Executive summary: where the picks are, and every open CS2 pick in one table."),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------- gaps
    gap_rows = [r for r in rows if r["prob_a"] is None or r["basis"] in {"model", "vrs-resolved"}]
    gap_body = []
    for r in gap_rows:
        status = "Resolved from official sources" if r["prob_a"] is not None else "Still unverified"
        res = ""
        for e in r["resolved"]:
            ev = "".join(
                f'<li><a href="{core.esc(x["url"])}" rel="nofollow noopener" target="_blank">'
                f'{core.esc(x["source"])}</a> &mdash; &ldquo;{core.esc(x["quote"])}&rdquo;</li>'
                for x in e.get("evidence", [])
            )
            res += (f"<h3>{core.esc(e['hotspawn_name'])} = {core.esc(e['valve_name'] or 'no match')}"
                    f" <span class='small'>({core.esc(e['status'])})</span></h3><ul class='tight'>{ev}</ul>")
        if r["prob_a"] is None:
            # pull the unresolved resolution entry for this team so the reviewer sees the checks
            for name in (r["team_a"], r["team_b"]):
                ent = aliases.by_hotspawn_name(name)
                if ent and ent["status"] == "unresolved":
                    ev = "".join(
                        f'<li><a href="{core.esc(x["url"])}" rel="nofollow noopener" target="_blank">'
                        f'{core.esc(x["source"])}</a> &mdash; &ldquo;{core.esc(x["quote"])}&rdquo;</li>'
                        for x in ent.get("evidence", [])
                    )
                    res += (f"<h3>{core.esc(ent['hotspawn_name'])} &mdash; no official rating found</h3>"
                            f"<ul class='tight'>{ev}</ul>"
                            f"<p class='small'>{core.esc(ent.get('conflict') or '')}</p>")
        gap_body.append(
            f"<h2>{core.esc(r['team_a'])} vs {core.esc(r['team_b'])} "
            f"<span class='small'>({core.esc(r['competition'])})</span></h2>"
            f"<p><b>Status:</b> {core.esc(status)}"
            + (f" &mdash; pick <b>{core.esc(r['pick_team'])}</b> at "
               f"<b>{r['pick_prob'] * 100:.1f}%</b> ({core.esc(r['confidence'])})"
               if r["prob_a"] is not None else "")
            + "</p>"
            f"<p class='small'>HotSpawn fixture {core.esc(r['fixture_id'])} &middot; start "
            f"{core.esc(r['start_utc'])} &middot; "
            f"<a href=\"{core.esc(r['hotspawn_url'])}\" rel=\"nofollow noopener\" target=\"_blank\">"
            f"official match page</a></p>"
            + res
            + f"<p class='small'><b>Flags:</b> <code>{core.esc(', '.join(r['flags']))}</code></p>"
        )
    conflict_blocks = []
    for e in aliases.RESOLUTIONS:
        if e.get("conflict"):
            links = " ".join(
                f'<a href="{core.esc(u)}" rel="nofollow noopener" target="_blank">{core.esc(u)}</a>'
                for u in e.get("conflict_links", [])
            )
            conflict_blocks.append(
                f"<h3>{core.esc(e['hotspawn_name'])}</h3>"
                f"<p>{core.esc(e['conflict'])}</p><p class='small'>{links}</p>"
            )
    gaps_body = f"""
<p class="sub">Matches with no bookmaker price, what we could confirm from official sources, and
exactly where to check it. Nothing on this page is filled in from a guess: where an official rating
exists for both teams the model pick is shown and labelled as an estimate; where it does not, the
row stays blank.</p>
<div class="warn"><b>Estimates are not prices.</b> A rating-model pick is our own number, derived
from Valve's published points. It is not a bookmaker line and no bookmaker is quoting these
matches. Treat it as a model estimate and check the linked source yourself.</div>
{''.join(gap_body)}
<h2>Name and data conflicts found</h2>
{''.join(conflict_blocks)}
"""
    (OUT / "gaps.html").write_text(
        page("Uncovered matches &mdash; what we could and could not confirm", "gaps.html", gaps_body),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------- sources
    rows_src = []
    for url, when in sorted(aliases.READ_TIMES_UTC.items(), key=lambda kv: kv[0]):
        rows_src.append(f"<tr><td><a href=\"{core.esc(url)}\" rel=\"nofollow noopener\" "
                        f"target=\"_blank\">{core.esc(url)}</a></td><td>{core.esc(when)}</td></tr>")
    board_sources = our_board.get("summary", {}).get("sources_ok", [])
    src_body = f"""
<p class="sub">Every external source used anywhere on this site, with the exact URL and the UTC
time it was read. Click any link to check the value yourself.</p>
<h2>Fixture discovery</h2>
<ul class="tight">
<li><a href="https://play.hotspawn.com/lobby" rel="nofollow noopener" target="_blank">
https://play.hotspawn.com/lobby</a> &mdash; the only place the match list comes from. Its crowd
&ldquo;picked %&rdquo; is <b>not</b> used as a probability anywhere on this site.</li>
</ul>
<h2>Prices (bookmakers and exchanges)</h2>
<p class="small">Sources reported as reachable by the OURLINE collector at
{core.esc(our_board.get("generated_utc") or "unknown")}:
<code>{core.esc(", ".join(board_sources) or "none")}</code>. Each priced row on
<a href="index.html">the pick table</a> links to the exact bookmaker page its number came from.</p>
<h2>Ratings</h2>
<ul class="tight">
<li><a href="{core.esc(VALVE_PAGE_URL)}" rel="nofollow noopener" target="_blank">Valve regional
standings &mdash; {core.esc(valve_meta.get("snapshot") or "")}</a> (official Valve repository,
{core.esc(str(valve_meta.get("n_teams")))} teams read from
<code>{core.esc(valve_meta.get("path") or "")}</code>)</li>
<li><a href="{core.esc(HLTV_ELISA)}" rel="nofollow noopener" target="_blank">HLTV event pages</a>
&mdash; group draws, schedules and team identities used to resolve the names above</li>
<li><a href="{core.esc(aliases.LIQUIPEDIA_ELISA)}" rel="nofollow noopener" target="_blank">
Liquipedia</a> &mdash; participant lists cross-checked against the group draws</li>
</ul>
<h2>Read log (this session)</h2>
<div class="tbl-wrap"><table><thead><tr><th>URL</th><th>Read (UTC)</th></tr></thead>
<tbody>{''.join(rows_src)}</tbody></table></div>
"""
    (OUT / "sources.html").write_text(
        page("Sources", "sources.html", src_body,
             "Every source with its URL and the time it was read."),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------- method
    method_body = f"""
<h2>Where the match list comes from</h2>
<p>The public <a href="https://play.hotspawn.com/lobby" rel="nofollow noopener" target="_blank">
HotSpawn Pick'ems lobby</a> embeds its fixture list in the page. That list is the inventory.
HotSpawn is used for <b>fixture discovery only</b>; its crowd &ldquo;picked %&rdquo; is never used
as a probability, so our numbers are independent of what other players picked.</p>
<h2>Where the probabilities come from</h2>
<ol class="tight">
<li><b>Bookmaker and exchange prices.</b> Pinnacle, Bovada, Melbet and Kalshi full-match prices,
read by the OURLINE collector. Each side's implied probability is de-vigged proportionally
(<code>p = (1/odds) / sum(1/odds)</code>) and the sources are averaged. Every priced row links to
the bookmaker page it came from.</li>
<li><b>Rating model (when there is no price).</b> Valve's own published standings give every team a
points total. Valve's repository documents the win-expectancy curve
(<code>Q = ln(10)/400</code>, <code>g = 1/sqrt(1 + 3*Q^2*RD^2/pi^2)</code>, RD fixed at 75), so
<code>P(A beats B) = sigmoid(k &middot; g &middot; ln(10)/400 &middot; (ptsA - ptsB))</code>.
Valve's README warns their curve is too steep, so <code>k</code> is not assumed: it is fitted by
least squares against observed bookmaker lines. The value used here is the one the OURLINE board
published, <code>k = {k:.4f}</code>, fitted on
<code>{core.esc(str(calibration.get("n_pairs")))}</code> market/model pairs with a mean absolute
error of <code>{core.esc(str(round((calibration.get("mae_prob") or 0), 4)))}</code>.</li>
<li><b>Blend.</b> Where both exist, market and model are blended in logit space with the market
weighted <code>0.85</code> when two or more independent sources agree, <code>0.75</code> otherwise.
That weighting and the blend are the OURLINE board's published choices; this section does not
change them.</li>
</ol>
<h2>Name resolution</h2>
<p>Some teams appear under different names at HotSpawn, Valve and HLTV. Resolutions are only made
when two independent official sources agree through the same event, the same opponents and the same
kickoff offsets, and every one is published with its evidence on the
<a href="gaps.html">Uncovered matches</a> page.</p>
<h2>Limits</h2>
<ul class="tight">
<li>A rating-model pick is our own estimate, not a bookmaker line. No bookmaker is quoting these
matches, which is exactly why they were uncovered.</li>
<li>Valve's standings are a snapshot ({core.esc(valve_meta.get("snapshot") or "unknown")}); rosters
and ratings move between snapshots.</li>
<li>Where a team has no official rating at all in the sources we could read, the row stays blank
and is flagged. It is never filled in.</li>
<li>Probabilities are estimates, not predictions with any validated accuracy, and not betting
advice.</li>
</ul>
"""
    (OUT / "method.html").write_text(
        page("Method", "method.html", method_body,
             "Where every number comes from, and where the model stops."),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------- repo review
    review = build_repo_review(rows, our_board, valve_meta)
    (OUT / "repo-review.html").write_text(
        page("Repository review", "repo-review.html", review,
             "Line-by-line review of the repo, with irregularities flagged for manual review."),
        encoding="utf-8",
    )

    print(f"summary/: {total} open rows, {with_pick} with a pick, {blank} blank/flagged")
    return 0


def build_repo_review(rows, our_board, valve_meta) -> str:
    """Programmatic checks plus the findings verified by hand this session."""
    checks = []

    def check(name, ok, detail):
        checks.append((name, ok, detail))

    # 1. every row has at least one official source link
    missing = [r["fixture_id"] for r in rows if not r["source_links"]]
    check("Every pick row carries an official source link", not missing,
          f"{len(rows) - len(missing)}/{len(rows)} rows have at least one source link"
          + (f"; missing: {', '.join(missing)}" if missing else ""))

    # 2. no row links a constructed /matches/<id> path (the defect session 7cd2e67a repaired)
    constructed = [
        r["fixture_id"] for r in rows
        if any("/matches/" in l["url"] and l["url"].rstrip("/").split("-")[-1].isdigit() is False
               for l in r["source_links"])
    ]
    check("No constructed HotSpawn match path", not constructed,
          "all fixture links are the permalink HotSpawn publishes, or the lobby itself")

    # 3. probabilities sum to 1
    bad = [r["fixture_id"] for r in rows
           if r["prob_a"] is not None and abs(r["prob_a"] + r["prob_b"] - 1.0) > 1e-9]
    check("Probabilities sum to 1", not bad, f"{len(rows) - len(bad)} priced rows checked")

    # 4. blank rows state a reason
    noreason = [r["fixture_id"] for r in rows if r["prob_a"] is None and not r["flags"]]
    check("Blank rows publish a reason", not noreason,
          "every blank row carries a flag explaining why it is blank")

    # 5. Valve file parsed from the committed capture
    check("Valve standings read from the committed official capture",
          bool(valve_meta.get("n_teams")),
          f"{valve_meta.get('n_teams')} teams parsed from {valve_meta.get('path')}")

    # 6. every alias resolution cites at least two official sources
    weak = [e["hotspawn_name"] for e in aliases.RESOLUTIONS if len(e.get("evidence", [])) < 2]
    check("Every name resolution cites at least two sources", not weak,
          f"{len(aliases.RESOLUTIONS) - len(weak)}/{len(aliases.RESOLUTIONS)} resolutions have 2+ citations")

    check_html = "".join(
        f"<tr><td>{'PASS' if ok else 'FLAG'}</td><td>{core.esc(name)}</td>"
        f"<td class='small'>{core.esc(detail)}</td></tr>"
        for name, ok, detail in checks
    )

    findings = [
        ("R-C0-1", "Six open matches were reported as having no line because of a team-name "
         "mismatch, not because the team is unranked.",
         "WROTBERRY and RoundsGG are absent from Valve's file under those names, but the file does "
         "contain <code>WBT</code> (standing 60, 1201 pts) and <code>ROUNDS</code> (standing 310, "
         "548 pts). HLTV's Elisa BreakOut Series 2 group draw and schedule put WBT and ROUNDS in "
         "exactly the slots HotSpawn fills with WROTBERRY and RoundsGG. Five of the six rows are "
         "therefore resolvable from sources already in the repo.",
         [VALVE_PAGE_URL, HLTV_ELISA, HLTV_ELISA.replace("/elisa-breakout-series-2", "/matches")]),
        ("R-C0-2", "Third-party sites list a different roster for 'WROTBERRY' than Valve and HLTV do.",
         "bo3.gg, egamersworld and strafe.com give WROTBERRY the five fl1peR / svemyy / aRTYSAN / "
         "tired73 / lyoli. That is Valve's <code>WBT Academy</code> row (standing 130, 911 pts), "
         "not the <code>WBT</code> row that HotSpawn's schedule matches. HotSpawn's fixtures follow "
         "WBT, so WBT is used and the conflict is published rather than resolved by guess.",
         [aliases.BO3GG_WROTBERRY, aliases.EGAMERSWORLD_WROTBERRY, aliases.STRAFE_WROTBERRY, VALVE_PAGE_URL]),
        ("R-C0-3", "HLTV contradicts itself about LFO 10's ranking.",
         "On the match analytics page HLTV writes &ldquo;LFO 10 is worse ranked (Unranked)&rdquo;; "
         "on the event overview for the same tournament the seed column shows <code>#170 LFO 10</code>. "
         "No rating is taken from either, and the row stays blank.",
         [aliases.HLTV_FORZE_LFO10, aliases.HLTV_CCT_EVENT]),
        ("R-C0-4", "The committed Valve snapshot is nine days older than the ranking HLTV displays.",
         "The repo holds <code>standings_global_2026_10_05.md</code>. Listing the repository's "
         "<code>live/2026</code> directory during this session shows 2026_10_05 is the newest file "
         "Valve has published there, yet HLTV's team page displays a Valve rank of #64 for WBT "
         "against #60 in the file, and #113 for ENCE against #105. Either Valve publishes an update "
         "somewhere other than that directory or HLTV re-derives the ordering. The difference is "
         "flagged; the repo's official file is what the model uses.",
         [VALVE_PAGE_URL, aliases.VALVE_REPO_LIVE, HLTV_ELISA]),
        ("R-C0-5", "The HotSpawn lobby's own counter still does not match its fixture list.",
         "The lobby header read <b>68 matches this week</b> while its own tier filter read "
         "All tiers (89), B (25), C (60), S (4) and the rendered card list was shorter again. "
         "Inherited sessions already published this as unexplained; it is reproduced here for "
         "continuity and left unexplained rather than guessed.",
         ["https://play.hotspawn.com/lobby"]),
        ("R-C0-6", "The lobby's displayed kickoff times are not UTC.",
         "HotSpawn's cards are labelled with local times; the embedded fixture payload carries UTC "
         "epochs. HLTV renders the same matches four hours behind the UTC values the board stores, "
         "which is a display-timezone difference, not a scheduling conflict. Only the UTC values "
         "are used.",
         ["https://play.hotspawn.com/lobby", HLTV_ELISA]),
    ]
    find_html = "".join(
        f"<h3>{core.esc(fid)} &mdash; {core.esc(title)}</h3>"
        f"<p>{detail}</p><p class='small'>Sources: " +
        " &middot; ".join(
            f'<a href="{core.esc(u)}" rel="nofollow noopener" target="_blank">{core.esc(u)}</a>'
            for u in urls
        ) + "</p>"
        for fid, title, detail, urls in findings
    )

    return f"""
<p class="sub">Read line by line during this session. Every finding below is reproduced from the
linked official source; anything that could not be confirmed is flagged rather than filled in.</p>
<h2>Automated checks</h2>
<div class="tbl-wrap"><table><thead><tr><th>Result</th><th>Check</th><th>Detail</th></tr></thead>
<tbody>{check_html}</tbody></table></div>
<h2>Findings flagged for manual review</h2>
{find_html}
<h2>Repository layout</h2>
<p class="small">The site is published from the repository root by GitHub Pages. Each session owns
its own directory and its own data; <code>COORDINATION.md</code> in the root is the shared task
board that keeps concurrent sessions out of each other's files. This section
(<code>summary/</code>) is owned by session <code>c0e223d3</code> and writes nothing outside it and
<code>data/c0e223d3/</code>.</p>
"""


def main() -> int:
    our_board = core.read_json(OUR_BOARD)
    if not our_board or "open" not in our_board:
        print(f"SKIP: no readable OURLINE board at {OUR_BOARD}", file=sys.stderr)
        return 1

    valve_by_name, valve_meta = core.load_valve_teams(ROOT)
    calibration = our_board.get("calibration") or {}
    k = float(calibration.get("k") or core.DEFAULT_K)

    rows = build_rows(our_board, valve_by_name, k)

    sections = []
    for s in SITE_SECTIONS:
        href = s["href"]
        if href.startswith("../"):
            target = ROOT / href[3:]
        else:
            target = OUT / href
        if target.exists():
            sections.append(s)
    return build(rows, our_board, valve_meta, k, calibration, sections)


if __name__ == "__main__":
    raise SystemExit(main())
