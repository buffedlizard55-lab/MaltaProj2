#!/usr/bin/env python3
"""Session 34af18bf renderer — the phone-first pick desk.

Pages written (all static, no JavaScript required for content):

  pickdesk/index.html        executive summary: where the picks are, coverage KPIs,
                             today's TWC day-4 decisions, the unresolved section link
  pickdesk/picks.html        every open HotSpawn CS2 fixture: pick, win probability,
                             basis, source link, crowd ownership, differential
  pickdesk/twc.html          TWC 2026 day 1-4 review, roster/onboarding/rest audit,
                             day-4 safe pick + contrarian climb pick with gates
  pickdesk/unresolved.html   the separate unresolved-picks & limitations section
  pickdesk/flagged.html      irregularities with links
  pickdesk/method.html       sources, weights, formulas, cadence, verification
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import research  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "34af18bf"
OUT = ROOT / "pickdesk"

NAV = [("index.html", "Home"), ("picks.html", "All picks"), ("twc.html", "TWC day 4"),
       ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"), ("method.html", "Method")]

CSS = """
:root{--bg:#0b1120;--card:#131e33;--card2:#0f1830;--txt:#e9eefb;--mut:#94a6c6;--line:#26344f;
--acc:#3d7dff;--good:#16a34a;--warn:#c9861b;--bad:#b91c1c;--climb:#7c3aed}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:14px}
header.site{position:sticky;top:0;z-index:30;background:rgba(11,17,32,.97);border-bottom:1px solid var(--line)}
header.site .wrap{padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
header.site a{color:var(--mut);text-decoration:none;font-size:13px;padding:8px 10px;border-radius:9px;min-height:40px;display:inline-flex;align-items:center}
header.site a.on{background:var(--card);color:var(--txt)}
.brand{font-weight:800;color:#cfe0ff;font-size:14px;margin-right:4px}
h1{font-size:22px;line-height:1.25;margin:14px 0 6px}
h2{font-size:19px;margin:26px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:16.5px;margin:18px 0 6px}
p{margin:9px 0}
.mut{color:var(--mut);font-size:13.5px}
.eyebrow{color:#7fa7ff;font-weight:800;letter-spacing:.09em;text-transform:uppercase;font-size:11px;margin:14px 0 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.kpi b{display:block;font-size:21px}
.kpi span{color:var(--mut);font-size:12.5px}
.cta{display:grid;gap:9px;margin:14px 0}
.cta a{display:block;background:var(--acc);color:#fff;text-decoration:none;font-weight:700;border-radius:13px;padding:15px 16px;min-height:48px}
.cta a small{display:block;font-weight:400;opacity:.9;font-size:12.5px;margin-top:3px}
.cta a.alt{background:var(--card);border:1.5px solid var(--acc);color:#bcd2ff}
.cta a.warn{background:#8a5a10}
.cta a.climb{background:var(--climb)}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:12px;margin:10px 0}
.tag{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700;white-space:nowrap}
.tag.mkt{background:#1d4ed8;color:#fff}.tag.ori{background:var(--warn);color:#1b1300}
.tag.blank{background:#3b2430;color:#ffb4ae}.tag.safe{background:#0f766e;color:#fff}
.tag.climb{background:var(--climb);color:#fff}.tag.res{background:#0e7490;color:#fff}
.tag.s{background:#14532d;color:#bbf7d0}
.bar{height:9px;border-radius:999px;background:#22304c;overflow:hidden;margin:7px 0 4px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#3d7dff,#22c55e)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 7px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#b9c8e4;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
a{color:#93b8ff}
details{background:var(--card2);border:1px solid var(--line);border-radius:12px;margin:9px 0}
details>summary{cursor:pointer;padding:12px;font-weight:700;min-height:44px}
details .inner{padding:0 13px 13px}
.flag{background:#2a1a12;border-color:#7c3f10}
.rowcard{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:12px;margin:9px 0}
.rowcard .teams{font-weight:700;font-size:16px}
.rowcard .meta{color:var(--mut);font-size:12.5px;margin:2px 0 8px}
.pickline{display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.pickline b{font-size:17px}
footer{margin:34px 0 20px;color:var(--mut);font-size:12.5px}
ul{margin:8px 0 8px 18px;padding:0}li{margin:5px 0}
@media (max-width:640px){h1{font-size:20px}.wrap{padding:12px}table{font-size:13px}th,td{padding:7px 6px}}
"""


def shell(title: str, active: str, body: str, generated: str) -> str:
    nav = "".join(
        f'<a href="{core.esc(h)}" class="{"on" if h == active else ""}">{core.esc(label)}</a>'
        for h, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{core.esc(title)}</title>
<meta name="description" content="Phone-first pick desk: every open HotSpawn CS2 match with a pick, a win probability from external betting lines only, and the TWC 2026 day-4 decisions.">
<style>{CSS}</style></head><body>
<header class="site"><div class="wrap"><span class="brand">Pick desk</span>{nav}<a href="../index.html">Site index</a></div></header>
<main class="wrap">
{body}
<footer>Built by session <code>34af18bf</code> · board generated {core.esc(generated)} · fixture capture
{core.esc(generated)} · no manual input. HotSpawn supplies fixtures and the pick'em scoreboard only;
every probability on this site comes from an external bookmaker, exchange or dated research reading.
Not betting advice.</footer>
</main></body></html>
"""


def bar(p: float | None) -> str:
    if p is None:
        return ""
    width = max(2, round(float(p) * 100))
    return f'<div class="bar"><i style="width:{width}%"></i></div>'


def pick_card(row: dict) -> str:
    prob = row.get("probability")
    own = row.get("pick_own")
    diff = row.get("differential")
    basis = row.get("basis")
    tag = {"market": '<span class="tag mkt">MARKET</span>',
           "originated": '<span class="tag ori">ORIGINATED</span>',
           "blank": '<span class="tag blank">UNRESOLVED</span>'}.get(basis, "")
    links = " · ".join(f'<a href="{core.esc(l["url"])}" target="_blank" rel="noopener">{core.esc(l["label"])}</a>'
                       for l in row.get("source_links") or [])
    climb = ""
    if row.get("climb"):
        climb = (f'<p class="mut">Climb pick (contrarian, gates passed): <b>{core.esc(row["climb"])}</b> at '
                 f'{core.pct(row.get("climb_probability"))} vs {core.pct(row.get("climb_ownership"))} ownership '
                 f'· differential {core.pct(row.get("climb_differential"), 1)}</p>')
    elif row.get("climb_candidate"):
        climb = (f'<p class="mut">Contrarian candidate <b>{core.esc(row["climb_candidate"])}</b> '
                 f'{core.pct(row.get("climb_probability"))} vs {core.pct(row.get("climb_ownership"))} ownership — '
                 f'not activated: gates C1/C3 not both met.</p>')
    blank = ""
    if row["basis"] == "blank":
        blank = '<p class="mut">No external price was reachable and no unambiguous rating pair exists — this row is published blank, never filled with a guess.</p>'
    where = ('<span class="tag s">LOBBY CARD</span>' if row.get("lobby_card")
             else '<span class="tag res">FIXTURES FEED</span>')
    return f"""<div class="rowcard">
<div class="teams">{core.esc(row["team_a"])} vs {core.esc(row["team_b"])} {tag} {where} <span class="mut" style="font-weight:400">#{core.esc(row["fixture_id"])}</span></div>
<div class="meta">{core.esc(row.get("competition") or "")} · {core.human_utc(row.get("start_utc"))} · pick'em points {core.esc(row.get("offered_points") or "—")}</div>
<div class="pickline"><span>Pick: <b>{core.esc(row.get("pick") or "—")}</b></span><span>{core.pct(prob, 1)}</span></div>
{bar(prob)}
<div class="meta">HotSpawn crowd ownership on that side: {core.pct(own)} · market-vs-crowd differential {core.pct(diff, 1)} · basis: {core.esc(basis)} ({core.esc(row.get("confidence") or "")})</div>
{climb}{blank}
<div class="meta">{links if links else "No accepted external price source for this fixture."}<br>
<a href="{core.esc(row.get("hotspawn_url") or "")}" target="_blank" rel="noopener">HotSpawn fixture</a></div>
</div>"""


# --------------------------------------------------------------------------- pages
def page_index(board: dict) -> str:
    s = board["summary"]
    twc_rows = board["twc"]
    now = core.parse_iso(board["generated_utc"])
    upcoming = [r for r in board["fixtures"] if core.parse_iso(r["start_utc"]) and
                core.parse_iso(r["start_utc"]) > now][:4]
    twc_cards = "".join(pick_card(r) for r in twc_rows)
    nxt = "".join(f'<li>{core.esc(r["team_a"])} vs {core.esc(r["team_b"])} — '
                  f'{core.human_utc(r["start_utc"])} · pick <b>{core.esc(r.get("pick") or "—")}</b> '
                  f'{core.pct(r.get("probability"), 0)}</li>' for r in upcoming)
    blanks = board["unresolved"]
    blank_list = "".join(f'<li>{core.esc(b["team_a"])} vs {core.esc(b["team_b"])} — {core.esc(b["competition"])}</li>'
                         for b in blanks[:8]) or "<li>None — every open fixture carries a pick.</li>"
    body = f"""
<p class="eyebrow">Executive summary · updated every 4 hours</p>
<h1>Every HotSpawn CS2 pick, on one phone screen</h1>
<p>This desk covers <b>all {s['open_fixtures_total']} open Counter-Strike 2 matches</b> HotSpawn is
listing right now: the <b>{s.get('lobby_cards', 0)} cards</b> the rendered lobby page shows, the
<b>{s['twc_playoff_rows']} Thunderpick World Championship semi-finals</b> it shows under competition 35859,
and <b>{s.get('fixtures_feed_only', 0)} further fixtures</b> HotSpawn's own fixtures endpoint lists without
rendering a lobby card. Every row carries a pick, a win probability built from external betting lines, the
basis it uses, and a source link. Rows are tagged <b>LOBBY CARD</b> or <b>FIXTURES FEED</b> so the two are
never confused. HotSpawn is used for the fixture list and the crowd scoreboard only — never as a
probability.</p>

<div class="kpis">
<div class="kpi"><b>{s['open_fixtures_total']}</b><span>open CS2 fixtures covered</span></div>
<div class="kpi"><b>{s['market_rows']}</b><span>priced by real bookmaker/exchange lines</span></div>
<div class="kpi"><b>{s['originated_rows']}</b><span>originated (labelled) lines</span></div>
<div class="kpi"><b>{s['blank_rows']}</b><span>unresolved, published blank</span></div>
<div class="kpi"><b>{s['climb_picks_activated']}</b><span>contrarian climb picks activated</span></div>
<div class="kpi"><b>{s.get('lobby_cards', 0)}</b><span>cards on the rendered lobby page</span></div>
</div>

<div class="cta">
<a href="picks.html">All {s['open_fixtures_total']} picks — every open match<small>Pick, win probability, basis and source link for each fixture, in one mobile list.</small></a>
<a class="climb" href="twc.html">TWC 2026 day-4 decisions<small>Day 1–3 review, roster/rest audit, and today's safe + contrarian picks for both semi-finals.</small></a>
<a class="alt" href="unresolved.html">Unresolved picks &amp; limitations<small>The separate section for anything that could not be resolved, with the reason and the sources that were tried.</small></a>
<a class="alt" href="flagged.html">Flagged for review<small>Irregularities, refused prices, blocked sources and coverage fixes.</small></a>
</div>

<h2>Today's Thunderpick World Championship semi-finals</h2>
<p class="mut">HotSpawn lists both as 7-point tier-S pick'em cards. Crowd ownership and market probability are
different things: the crowd is where the leaderboard field sits, the market is what the books price.</p>
{twc_cards}

<h2>Next fixtures from the lobby</h2>
<ul>{nxt}</ul>
<p class="mut">Full table on <a href="picks.html">All picks</a>.</p>

<h2>Unresolved picks and limitations</h2>
<p>{len(blanks)} of {s['open_fixtures_total']} rows could not be resolved from an external two-sided price or an
unambiguous official rating pair. They stay blank and are listed — with every source that was tried — on
<a href="unresolved.html">Unresolved picks &amp; limitations</a>.</p>
<ul>{blank_list}</ul>

<h2>Where everything lives on this site</h2>
<div class="tablewrap"><table>
<tr><th>Page</th><th>What it gives you</th></tr>
<tr><td><a href="picks.html">All picks — every open match</a></td><td>Pick + win probability per fixture, with basis and source.</td></tr>
<tr><td><a href="twc.html">TWC day 1–4</a></td><td>Verified results, Aurora roster audit, day-4 safe + climb picks.</td></tr>
<tr><td><a href="unresolved.html">Unresolved &amp; limitations</a></td><td>Blank rows, refused prices, blocked sources, method limits.</td></tr>
<tr><td><a href="flagged.html">Flagged for review</a></td><td>Irregularities and the fixes this desk made.</td></tr>
<tr><td><a href="method.html">Method</a></td><td>Ladder, weights, formulas, cadence, verification checks.</td></tr>
<tr><td><a href="../picks-every-match/">Every-match board (canonical)</a></td><td>The project's long-running every-match board, refreshed every 4 hours.</td></tr>
<tr><td><a href="../index.html">Site index</a></td><td>Every other section, including dated research.</td></tr>
</table></div>
"""
    return shell("Pick desk — executive summary", "index.html", body, board["generated_utc"])


def page_picks(board: dict) -> str:
    rows = board["fixtures"]
    twc = board["twc"]
    cards = "".join(pick_card(r) for r in twc + rows)
    def source_cell(row: dict) -> str:
        links = (row.get("source_links") or [])[:2]
        if not links:
            return "—"
        return " ".join('<a href="%s" target="_blank" rel="noopener">source</a>' % core.esc(l["url"])
                        for l in links)

    def board_row(r: dict) -> str:
        return ("<tr>"
                f'<td>{core.esc(r["team_a"])} vs {core.esc(r["team_b"])}</td>'
                f'<td>{core.human_utc(r.get("start_utc"))}</td>'
                f'<td>{core.esc(r.get("pick") or "—")}</td>'
                f'<td>{core.pct(r.get("probability"), 0)}</td>'
                f'<td>{core.esc(r.get("basis"))}</td>'
                f'<td>{source_cell(r)}</td></tr>')

    table = "".join(board_row(r) for r in twc + rows)
    body = f"""
<p class="eyebrow">Complete coverage</p>
<h1>All picks: every open HotSpawn CS2 match</h1>
<p>{len(twc) + len(rows)} fixtures — {len(twc)} Thunderpick World Championship play-off cards (competition 35859)
plus {len(rows)} lobby fixtures. Probabilities are no-vig splits of external bookmaker/exchange lines
(Pinnacle, Bovada, Melbet, Kalshi, Thunderpick-via-bo3.gg, Polymarket). Where no market prices a fixture the
row is either labelled <span class="tag ori">ORIGINATED</span> from Valve's official standings or published
<span class="tag blank">UNRESOLVED</span> — never a made-up 50/50.</p>
<div class="tablewrap"><table>
<tr><th>Fixture</th><th>Kick-off (UTC)</th><th>Pick</th><th>Win prob.</th><th>Basis</th><th>Source</th></tr>
{table}
</table></div>
<h2>Every fixture, in detail</h2>
{cards}
"""
    return shell("All picks — every open HotSpawn CS2 match", "picks.html", body, board["generated_utc"])


def page_twc(board: dict) -> str:
    res = research
    def maps_cell(r: dict) -> str:
        if not r["maps"]:
            return '<span class="mut">maps not read from a primary source — blank</span>'
        return " · ".join(f"{m[0]} {m[1]}-{m[2]}" for m in r["maps"])

    def result_row(r: dict) -> str:
        source_url = core.esc(res.SOURCES[r["source"]][1])
        return ("<tr>"
                f'<td>{core.esc(r["day"])}<br><span class="mut">{core.esc(r["stage"])}</span></td>'
                f'<td><b>{core.esc(r["winner"])}</b> {core.esc(r["score"])} {core.esc(r["loser"])}</td>'
                f'<td>{maps_cell(r)}</td>'
                f'<td><a href="{source_url}" target="_blank" rel="noopener">official page</a></td>'
                f'<td class="mut">{core.esc(r["note"])}</td></tr>')

    rows = "".join(result_row(r) for r in res.TWC_RESULTS)
    h2h = "".join(f'<li><b>{core.esc(h["pair"][0])} vs {core.esc(h["pair"][1])}</b> — {core.esc(h["result"])} '
                  f'({core.esc(h["when"])}). {core.esc(h["note"])} '
                  f'<a href="{core.esc(res.SOURCES[h["source"]][1])}" target="_blank" rel="noopener">source</a></li>'
                  for h in res.H2H)
    maps = "".join(f'<li><b>{core.esc(m["team"])}</b> — {core.esc(m["map"])}: {core.esc(m["fact"])} '
                   f'<a href="{core.esc(res.SOURCES[m["source"]][1])}" target="_blank" rel="noopener">source</a></li>'
                   for m in res.MAP_POOL_NOTES)
    roster_blocks = []
    for team, entry in res.ROSTER_AUDIT.items():
        change = entry.get("last_active_lineup_change")
        change_html = ("No active-line-up change could be confirmed from the sources read."
                       if not change else
                       f'{change["date"]} — {core.esc(change["what"])} '
                       + " ".join(f'<a href="{core.esc(res.SOURCES[s][1])}" target="_blank" rel="noopener">source</a>'
                                  for s in change["sources"]))
        move = entry.get("recent_non_playing_move")
        move_html = ""
        if move:
            move_html = (f'<p class="mut"><b>Non-playing move:</b> {move["date"]} — {core.esc(move["what"])} '
                         + " ".join(f'<a href="{core.esc(res.SOURCES[s][1])}" target="_blank" rel="noopener">source</a>'
                                    for s in move["sources"]) + f'<br><b>Flagged:</b> {core.esc(move["flag"])}</p>')
        roster_blocks.append(f"""<details><summary>{core.esc(team)} — {core.esc(", ".join(entry["active_five"]))}</summary>
<div class="inner"><p class="mut">Coach: {core.esc(entry.get("coach") or "—")}</p>
<p>Last confirmed active-line-up change: {change_html}</p>
{move_html}
<p class="mut">Rest before the semi-final: {core.esc(entry.get("rest_before_semi") or "—")}</p>
<p class="mut">Form: {core.esc(entry.get("form") or "—")}</p></div></details>""")
    twc_cards = "".join(pick_card(r) for r in board["twc"])
    rules = "".join(f'<tr><td>{core.esc(r["id"])}</td><td>{core.esc(r["rule"])}</td></tr>'
                    for r in res.CONTRARIAN_RULES)
    remaining = "".join(f'<tr><td>{core.human_utc(r["when_utc"])}</td><td>{core.esc(r["label"])}</td>'
                        f'<td>{core.esc(r.get("teams") or "not fixed at read time")}</td>'
                        f'<td><a href="{core.esc(res.SOURCES[r["source"]][1])}" target="_blank" rel="noopener">source</a></td></tr>'
                        for r in res.TWC_REMAINING)
    body = f"""
<p class="eyebrow">Thunderpick World Championship 2026 · Malta · day 4</p>
<h1>Day 1 upset, day 3 avenge — and the day-4 contrarian case</h1>
<p>All ten group-stage series are listed below with the map scores this session could read on official pages.
The day-1 result the brief asks about — <b>9z 2-0 Aurora</b> — was a genuine upset: on Valve's 5 October
standings 9z sat at #17 and Aurora at #9, and 9z took Aurora's own map pick (Nuke) 13-1 (HLTV's 16 October
Valve-ranking page lists Aurora at #5 with 1,815 points, a later reading of a different date). Aurora
answered by eliminating 9z 2-0 in the day-3 decider. Both semi-finals are <b>HotSpawn pick'em cards worth 7 points</b>.</p>

<h2>The two day-4 decisions</h2>
{twc_cards}

<h2>Why these picks — contrarian but not stupid</h2>
<p>The leaderboard is scored on pick'em points, so the value of a pick is not "who wins" but
<b>points × (true probability − crowd ownership)</b>. A pick everybody owns is worth nothing when it lands and
costs you the week when it does not. The gates below are published so you can check every activation.</p>
<div class="tablewrap"><table><tr><th>Rule</th><th>Gate</th></tr>{rules}</table></div>
<p class="mut"><b>Semi-final 1 — Aurora.</b> The market itself is a coin flip (Thunderpick 1.85/1.85,
Kalshi 1.94/2.11), so Aurora at ~50% is not a long shot: it is the crowd's blind side. 75% of pick'em players
are on FURIA, 25% on Aurora, so the differential is about +25 points of probability on a 7-point card.
Two verified context flags back it: Aurora beat FURIA 2-1 at ESL Pro League Season 24 on 6 October
(HLTV head-to-head), and Aurora have three consecutive top-four finishes with kyxsan as the rebuilt IGL.
Against it: FURIA rested ~44 hours against Aurora's ~24, and the sources do not all agree on the favourite —
HLTV's own analytics page states “Aurora is the bookmaker favorite with the best odds”, while the accepted
price set on this row (Pinnacle, Melbet, Thunderpick-via-bo3.gg, Kalshi) blends to a narrow FURIA edge. Both
readings are published; neither is smoothed away.</p>
<p class="mut"><b>Semi-final 2 — BETBOOM.</b> Here the crowd is <i>unanimous</i> — 100% Falcons, 0% BETBOOM —
while the books price BETBOOM at roughly one win in five. That is the only way this card can move you up the
board. Two verified flags: BETBOOM beat Falcons 2-0 at the last meeting (IEM Cologne Major), and BETBOOM won
Nuke 16-13 from 4-10 down in the decider while Falcons lost Mirage to 9z and lost both maps to BETBOOM in
Cologne. Against it: BETBOOM played a three-map decider under 24 hours earlier, and Falcons are the heavier
favourite on every source read. The safe pick stays Falcons.</p>

<div class="cta">
<a href="picks.html">All {board['summary']['open_fixtures_total']} picks — every open match<small>Including both semi-final cards once the lobby refreshes.</small></a>
<a class="alt" href="unresolved.html">Unresolved picks &amp; limitations</a>
</div>

<h2>Complete day 1–3 review (all ten series)</h2>
<div class="tablewrap"><table>
<tr><th>Day / stage</th><th>Result</th><th>Maps</th><th>Source</th><th>Note</th></tr>
{rows}
</table></div>

<h2>Head-to-head record behind the picks</h2>
<ul>{h2h}</ul>

<h2>Map-pool and veto evidence</h2>
<ul>{maps}</ul>

<h2>Roster, onboarding and rest audit</h2>
<p>Read from HLTV's team page and transfer announcements, Liquipedia's roster and transfer pages, and HotSpawn's
own tournament page. Dates are the announcement dates the sources publish.</p>
{''.join(roster_blocks)}

<h2>Remaining schedule</h2>
<div class="tablewrap"><table><tr><th>Kick-off</th><th>Stage</th><th>Teams</th><th>Source</th></tr>{remaining}</table></div>
"""
    return shell("TWC 2026 day-4 decisions", "twc.html", body, board["generated_utc"])


def page_unresolved(board: dict) -> str:
    rows = board["unresolved"]
    cards = "".join(f"""<div class="card">
<div class="teams"><b>{core.esc(r["team_a"])} vs {core.esc(r["team_b"])}</b> <span class="tag blank">UNRESOLVED</span> <span class="mut">#{core.esc(r["fixture_id"])}</span></div>
<p class="mut">{core.esc(r["competition"])} · {core.human_utc(r["start_utc"])}</p>
<p><b>Why it stays blank:</b> {core.esc(r["reason"])}</p>
<p class="mut"><b>Prices that were refused for this fixture:</b><br>
{(" ".join(f"- {core.esc(x.get('source'))}: {core.esc(x.get('reason'))}" for x in r["refused"]) if r["refused"] else "none — no source prices it yet")}</p>
<p class="mut"><a href="{core.esc(r["hotspawn_url"])}" target="_blank" rel="noopener">HotSpawn fixture</a></p>
</div>""" for r in rows)
    limits = "".join(f"<li>{core.esc(t)}</li>" for t in research.LIMITATIONS)
    blocked = board["flag"]["sources_blocked_for_the_runner"]
    body = f"""
<p class="eyebrow">Independent section, linked from the executive summary</p>
<h1>Unresolved picks and limitations</h1>
<p>The goal is a pick for every match, and this desk resolves <b>{board['summary']['market_rows']} fixtures from
market lines</b> and <b>{board['summary']['originated_rows']} from Valve's official standings</b>. What is left is
listed here with the exact reason, the sources that were tried, and the price that was refused — blank, never
guessed.</p>
<div class="kpis">
<div class="kpi"><b>{len(rows)}</b><span>rows still unresolved</span></div>
<div class="kpi"><b>{sum(1 for r in rows if r["refused"])}</b><span>rows where a price existed but failed a gate</span></div>
<div class="kpi"><b>{len(blocked)}</b><span>sources that refused the collector</span></div>
</div>
{cards if cards else "<p>Every open fixture currently carries a pick or a labelled originated line.</p>"}
<h2>Standing limitations of this desk</h2>
<ul>{limits}</ul>
<h2>Sources that refused the automated collector</h2>
<p class="mut">These are read by the agent with the URL and UTC read time recorded per fact, and re-checked by
hand; the four-hourly refresh relies on the sources that do answer the runner.</p>
<ul>{''.join(f"<li><code>{core.esc(b)}</code></li>" for b in blocked)}</ul>
"""
    return shell("Unresolved picks and limitations", "unresolved.html", body, board["generated_utc"])


def page_flagged(board: dict) -> str:
    def refused_row(r: dict) -> str:
        reasons = "; ".join("%s: %s" % (x.get("source"), x.get("reason")) for x in r["refused"])
        return ("<tr>"
                f'<td>{core.esc(r["team_a"])} vs {core.esc(r["team_b"])} '
                f'<span class="mut">#{core.esc(r["fixture_id"])}</span></td>'
                f'<td>{core.esc(reasons)}</td></tr>')

    refused = "".join(refused_row(r) for r in board["flag"]["refused_prices"])
    comps = "".join(f'<li><code>{core.esc(cid)}</code> — {core.esc(name)}</li>'
                    for cid, name in sorted(board["flag"]["hotspawn_competition_scan"].items(),
                                            key=lambda kv: int(kv[0])))
    def blocked_item(key: str) -> str:
        err = str((board["access"].get(key) or {}).get("error"))
        return '<li>%s <span class="mut">%s</span></li>' % (core.esc(key), core.esc(err))

    blocked = "".join(blocked_item(b) for b in board["flag"]["sources_blocked_for_the_runner"])
    items = [
        ("Coverage fix: the two TWC semi-finals were missing from every earlier board",
         "Earlier collectors swept a hard-coded list of HotSpawn competition ids that omitted "
         "<code>35859</code> — the Thunderpick World Championship 2026 pick'em competition HotSpawn links from "
         "its own semi-final preview. This desk sweeps every competition id seen in the lobby transfer state "
         "<b>plus</b> the id HotSpawn publishes, so fixtures <code>1080207</code> and <code>1080208</code> are "
         "now covered. Cross-check: <a href=\"https://play.hotspawn.com/lobby?competitionId=35859\" "
         "target=\"_blank\" rel=\"noopener\">the lobby URL</a> and "
         "<a href=\"https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-semi-preview\" "
         "target=\"_blank\" rel=\"noopener\">HotSpawn's preview</a>."),
        ("Day-1 map score conflict in the repository (13-4 vs 13-1 on Nuke)",
         "This session re-read the primary page: <a href=\"https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026\" "
         "target=\"_blank\" rel=\"noopener\">HLTV match 2399384</a> shows Nuke <b>13-1</b> for 9z (halves 11:1; 2:0). "
         "The 13-4 figure that appeared in some earlier tables is therefore wrong; this desk publishes 13-1."),
        ("Aurora roster-change premise: active line-up unchanged since 8 July 2026",
         "HLTV's team page lists the same active five (XANTARES, woxic, Wicadia, Jimpphat, kyxsan) and shows no "
         "substitution after 8 July. The only later movement found is <b>deko</b> on the <i>inactive</i> list, and "
         "the two tracked sources disagree on its date (Liquipedia 2026-09-17; HLTV renders it in October). "
         "Published as unresolved, not as a line-up change."),
        ("HotSpawn's own card for both semi-finals still names a placeholder opponent on the tournament page",
         "The tournament page's day-4 rows read “Waiting for information” for the opponents, while the pick'em "
         "lobby and the fixtures API name FURIA–Aurora and Falcons–BETBOOM. The desk takes the named pair from the "
         "pick'em row and the official match page, and keeps the discrepancy here."),
        ("Thin exchange books on low-tier fixtures",
         "Kalshi lists many of the tier-C fixtures with untraded books; those quotes are refused (the refusal is "
         "printed per fixture on the unresolved page) instead of being published as a price."),
    ]
    cards = "".join(f'<div class="card flag"><h3>{core.esc(t)}</h3><p>{body}</p></div>' for t, body in items)
    body = f"""
<p class="eyebrow">Irregularities · nothing blocking the pick</p>
<h1>Flagged for review</h1>
<p>Everything this desk could not confirm, or had to correct, is listed here with its source so it can be
checked by hand.</p>
{cards}
<h2>HotSpawn competitions swept on this capture</h2>
<ul>{comps}</ul>
<h2>Sources that refused the automated collector</h2>
<p class="mut">A refusal is published as a refusal — never as “no price exists”.</p>
<ul>{blocked or "<li>none this run</li>"}</ul>
<h2>Prices that were found but refused</h2>
<div class="tablewrap"><table><tr><th>Fixture</th><th>Reason</th></tr>{refused or "<tr><td colspan='2'>none this run</td></tr>"}</table></div>
"""
    return shell("Flagged for review", "flagged.html", body, board["generated_utc"])


def page_method(board: dict) -> str:
    w = board["declared_weights"]
    weights = "".join(f"<tr><td>{core.esc(research.SOURCES.get(k, (k, ''))[0] if k in research.SOURCES else core.esc(k))}</td>"
                      f"<td>{v}</td></tr>" for k, v in sorted(w.items()))
    sources = "".join(f'<tr><td>{core.esc(label)}</td><td><a href="{core.esc(url)}" target="_blank" rel="noopener">{core.esc(url)}</a></td></tr>'
                      for label, url in sorted((v for v in research.SOURCES.values()), key=lambda x: x[0]))
    g = board["gates"]
    body = f"""
<p class="eyebrow">Method · verification · cadence</p>
<h1>How every number on this desk is produced</h1>
<h2>1. Fixture discovery (never probability)</h2>
<p>Fixtures come from the public HotSpawn lobby page and HotSpawn's own fixtures endpoint, swept per competition id
seen in the lobby transfer state plus the ids HotSpawn publishes in its own links (competition <code>35859</code>
carries the TWC semi-finals). A fixture is <i>open</i> while its lock time has not passed. Crowd pick percentages
are stored as <code>crowd_*</code> ownership and are read by nothing except the differential formula below.</p>
<h2>2. Prices (external only)</h2>
<p>Pinnacle guest odds, Bovada coupons, the Melbet/22bet/Betwinner LineFeed, the Kalshi exchange, Thunderpick
coefficients published per fixture by bo3.gg, and Polymarket with a traded book. Sources that refuse the runner
(HLTV, EGamersWorld, GG.bet, Stake, Betano, VBet, Thunderpick's own site — HTTP 403) are recorded as refusals and
read by hand with a dated citation.</p>
<h2>3. Arithmetic</h2>
<ul>
<li>Decimal → implied probability: <code>p = 1 / decimal</code>.</li>
<li>No-vig two-way split: <code>p_a = (1/d_a) / (1/d_a + 1/d_b)</code>; the overround is published per quote.</li>
<li>Consensus: weighted mean of the accepted sources' no-vig splits; weights below.</li>
<li>Originated line, rung 1 (only when no market prices the fixture and Valve ranks both teams):
<code>p = 1 / (1 + 10^(-Δpoints/{g['vrs_elo_scale']:.0f}))</code> applied to Valve's official regional standings,
always labelled ORIGINATED.</li>
<li>Originated line, rung 2 (no market and no Valve pair): <code>p = 0.5 + 0.5·tanh(Δrank/{g.get('rank_scale', 40):.0f})</code>
on the bo3.gg world rank of both teams, clamped to [0.08, 0.92] — a coarse input, so the clamp and the label are
part of the published number.</li>
<li>Expected leaderboard differential: <code>points × (probability − crowd ownership)</code>.</li>
</ul>
<div class="tablewrap"><table><tr><th>Source weight in the consensus</th><th>Weight</th></tr>{weights}</table></div>
<h2>4. Gates</h2>
<ul>
<li>Kalshi books with a spread above <b>{core.esc(g['kalshi_spread'])}</b> are refused as thin.</li>
<li>Polymarket books below <b>$25</b> traded volume are refused as untraded.</li>
<li>Climb (contrarian) pick: at least <b>{core.esc(g['C1_min_probability'])}</b> market probability,
a positive market-vs-crowd differential, at least two verified context flags, and at most
<b>{core.esc(g['C4_max_climb_per_day'])}</b> activations per day.</li>
</ul>
<h2>5. Cadence and automation</h2>
<p><code>.github/workflows/pickdesk-34af18bf.yml</code> re-collects, re-derives and re-renders this section every
four hours and on demand; collection and rendering run in a GitHub-hosted runner with general internet access.
No step needs manual input, and a failing verification step blocks the commit so the previous good build stays
published.</p>
<h2>6. Verification performed</h2>
<ul>
<li>Every published probability is re-derived from the retained raw quotes in <code>data/34af18bf/snapshot.json</code>
by <code>scripts/34af18bf/verify.py</code>; a mismatch fails the build.</li>
<li>Every row must carry at least one official/external source link; rows without one fail the build.</li>
<li>No HotSpawn crowd field may appear in any arithmetic input (asserted in code).</li>
<li>Internal links are checked before publish; the same check runs again in <code>scripts/stage_site.py</code>.</li>
</ul>
<h2>Sources read for the dated research in this section</h2>
<div class="tablewrap"><table><tr><th>Source</th><th>URL</th></tr>{sources}</table></div>
<p class="mut">Read times: the dated research in the TWC section was read in this session at
{core.esc(research.READ_UTC)}; the live market numbers are re-read every four hours and each quote keeps its own
<code>retrieved_utc</code>.</p>
"""
    return shell("Method — sources, formulas, gates", "method.html", body, board["generated_utc"])


def main() -> int:
    board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": page_index(board),
        "picks.html": page_picks(board),
        "twc.html": page_twc(board),
        "unresolved.html": page_unresolved(board),
        "flagged.html": page_flagged(board),
        "method.html": page_method(board),
    }
    for name, content in pages.items():
        (OUT / name).write_text(content, encoding="utf-8")
    print(json.dumps({name: len(text) for name, text in pages.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
