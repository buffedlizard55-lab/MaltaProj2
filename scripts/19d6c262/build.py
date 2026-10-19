#!/usr/bin/env python3
"""Session 19d6c262 — render everymatch/*.html from data/19d6c262/board.json.

Pure offline step. Every published number is re-derived from the board, which itself is
re-derived from the OURLINE snapshot's raw quotes + the official Valve VRS files. Every
fixture row carries a link to an official source (bookmaker/exchange for featured market
picks; the official Valve standings file + per-team details file for VRS-model, floor and
alias resolutions). HotSpawn crowd percentages are never shown as a probability input.
"""
from __future__ import annotations
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "19d6c262"
SITE = ROOT / "everymatch"
LOBBY = "https://play.hotspawn.com/lobby"
HS_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"

CSS = """:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;
--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b;--pur:#b48cff}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--acc2)}header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.brand{font-weight:700;margin-right:auto}.bar nav{display:flex;gap:6px;flex-wrap:wrap}
.bar nav a{padding:7px 11px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px;min-height:40px;display:inline-flex;align-items:center}
.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:1100px;margin:0 auto;padding:14px}
h1{font-size:22px;margin:8px 0 4px}h2{font-size:18px;margin:26px 0 8px}.mut{color:var(--mut)}
.note{background:#12161f;border:1px solid var(--line);border-left:3px solid var(--acc2);border-radius:10px;padding:12px 14px;margin:12px 0}
.note.warn{border-left-color:var(--warn)}.note.bad{border-left-color:var(--bad)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.stat b{display:block;font-size:24px}
.stat span{color:var(--mut);font-size:13px}
.quick{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin:10px 0}
.quick a{display:block;padding:13px 14px;background:#202938;border:1px solid var(--line);border-radius:10px;text-decoration:none;min-height:52px;font-weight:600}
.quick a span{display:block;font-weight:400;color:var(--mut);font-size:13px;margin-top:2px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:14px}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);background:#131720}
.small{font-size:13px;color:var(--mut)}.nm,.small{overflow-wrap:anywhere}
.team{display:flex;align-items:center;gap:8px;margin:2px 0}.team .nm{flex:1;min-width:0}
.team.pk .nm{font-weight:700;color:var(--acc)}
.pct{font-variant-numeric:tabular-nums;min-width:52px;text-align:right}
.meter{height:6px;background:#2a303c;border-radius:4px;overflow:hidden;margin:2px 0 6px}.meter i{display:block;height:100%;background:var(--acc)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700}
.b-market{background:#123; color:#9ad0ff}.b-model{background:#1d2b1f;color:#8fe6b0}.b-floor{background:#3a2f16;color:#ffd591}
.b-dir{background:#3a2f16;color:#ffd591}.b-strong{background:#0e3d2a;color:#57e39b}.b-solid{background:#133247;color:#8fc7ff}
.b-lean{background:#33290f;color:#ffd166}.b-toss{background:#3a1f1f;color:#ff9b9b}
code{background:#11151c;padding:1px 5px;border-radius:5px;font-size:13px}
@media(max-width:720px){table.cards thead{display:none}table.cards tr{display:block;border:1px solid var(--line);border-radius:10px;margin:10px 0;padding:6px 10px;background:#12161f}
table.cards td{display:flex;gap:10px;border:0;padding:5px 0}table.cards td:before{content:attr(data-l);color:var(--mut);font-size:12px;text-transform:uppercase;min-width:96px;flex:0 0 96px;padding-top:2px}
table.cards td[data-l=""]:before{display:none}}"""


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def pct(p):
    return "—" if p is None else f"{p*100:.1f}%"


def page(title, active, body, board):
    nav = [("index.html", "Summary"), ("picks.html", "All picks"),
           ("unresolved.html", "Unresolved & limits"), ("sources.html", "Sources"),
           ("flagged.html", "Flagged"), ("method.html", "Method")]
    links = "".join(f'<a href="{h}"{" class=on" if h==active else ""}>{esc(t)}</a>' for h, t in nav)
    links += '<a href="../index.html">Main dashboard</a>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Pick for every CS2 match</title>
<style>{CSS}</style></head>
<body><header><div class="bar"><div class="brand">✅ Every match · CS2 picks</div>
<nav>{links}</nav></div></header>
<main data-observed="{esc(board.get('base_generated_utc'))}">
{body}
<p class="small" style="margin-top:26px">Board observed {esc(board.get('base_generated_utc'))} UTC from the
<a href="{HS_API}">HotSpawn fixtures API</a> via the OURLINE collector; Valve VRS snapshot
{esc(board['vrs']['snapshot'])}. Percentages are our own estimates from external lines / Valve's official
standings — never a HotSpawn crowd pick. Refresh is automated.</p>
</main></body></html>"""


def basis_badge(basis):
    m = {"market": ("b-market", "Market"), "market+model": ("b-market", "Market"),
         "model": ("b-model", "VRS model"), "floor_estimate": ("b-floor", "VRS floor est.")}
    cls, lab = m.get(basis, ("b-toss", basis))
    return f'<span class="badge {cls}">{esc(lab)}</span>'


def conf_badge(conf):
    cls = {"Strong": "b-strong", "Solid": "b-solid", "Lean": "b-lean",
           "Toss-up": "b-toss", "Directional": "b-dir"}.get(conf, "b-toss")
    return f'<span class="badge {cls}">{esc(conf)}</span>'


def source_links(row):
    """Official source link(s) for a row: bookmaker/exchange URLs for featured market picks,
    official Valve standings + team details for VRS resolutions."""
    out = []
    if row.get("quotes"):
        seen = set()
        for q in row["quotes"]:
            u = q.get("public_url")
            if u and u not in seen:
                seen.add(u)
                out.append(f'<a href="{esc(u)}">{esc(q.get("source_name") or q.get("source_key"))}</a>')
    res = row.get("resolution")
    if res:
        if res.get("vrs_page_url"):
            out.append(f'<a href="{esc(res["vrs_page_url"])}">Valve VRS</a>')
        for side in ("team_a", "team_b"):
            t = res.get(side)
            if t and t.get("details_url"):
                out.append(f'<a href="{esc(t["details_url"])}">{esc(t["team"])} #{t["standing"]}</a>')
    if not out:
        out.append(f'<a href="{LOBBY}">HotSpawn lobby</a>')
    return " · ".join(out)


def team_rows(row):
    ln = row["line"]
    a = f'<div class="team{" pk" if ln and ln["pick_side"]=="a" else ""}"><span class="nm">{esc(row["team_a"])}</span><span class="pct">{pct(ln["prob_a"]) if ln else "—"}</span></div>'
    b = f'<div class="team{" pk" if ln and ln["pick_side"]=="b" else ""}"><span class="nm">{esc(row["team_b"])}</span><span class="pct">{pct(ln["prob_b"]) if ln else "—"}</span></div>'
    meter = ""
    if ln:
        meter = f'<div class="meter"><i style="width:{ln["prob_a"]*100:.0f}%"></i></div>'
    return a + b + meter


def render_picks(board):
    rows = []
    for r in board["open"]:
        ln = r.get("line")
        pick = f'<b style="color:var(--acc)">{esc(ln["pick_team"])}</b>' if ln else '<span class="small">unresolved</span>'
        basis = basis_badge(ln["basis"]) if ln else '<span class="badge b-toss">none</span>'
        conf = conf_badge(ln["confidence"]) if ln else ""
        fair = (f'{ln["fair_decimal_a"]:.2f} / {ln["fair_decimal_b"]:.2f}' if ln else "—")
        comp = f'{esc(r.get("competition"))}<div class="small">Tier {esc(r.get("tier"))} · Bo{r.get("best_of") or "?"}</div>'
        rows.append(
            f'<tr data-row><td data-l="Locks / starts"><span>{esc(r.get("lock_utc") or r.get("start_utc"))}</span>'
            f'<div class="small">{esc(r.get("start_utc"))}</div></td>'
            f'<td data-l="Match &amp; probability">{team_rows(r)}</td>'
            f'<td data-l="Pick">{pick}<div class="small">{conf}</div></td>'
            f'<td data-l="Basis">{basis}</td>'
            f'<td data-l="Fair odds">{fair}</td>'
            f'<td data-l="Event">{comp}</td>'
            f'<td data-l="Sources">{source_links(r)}</td></tr>')
    s = board["summary"]
    return f"""
<h1>A pick for every open CS2 match</h1>
<p class="mut">All {s['open']} CS2 fixtures currently open for picks in the
<a href="{LOBBY}">HotSpawn Pick'ems lobby</a>. {s['with_pick']} of {s['open']} carry a pick:
{s['featured_market']} featured (external book/exchange prices, margin removed),
{s['vrs_model']} from the calibrated Valve VRS model (both teams rated),
{s['floor_estimate']} directional estimates (one team rated, opponent at the VRS floor).
The <b>PICK</b> is the team our line makes more likely to win.</p>
<table class="cards"><thead><tr><th>Locks / starts</th><th>Match &amp; win probability</th><th>Pick</th>
<th>Basis</th><th>Fair odds</th><th>Event</th><th>Sources</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""


def render_index(board):
    s = board["summary"]
    vrs = board["vrs"]
    nxt = board["open"][:4]
    nxt_html = "".join(
        f'<li><a href="picks.html">{esc(r["team_a"])} v {esc(r["team_b"])}</a> — '
        f'picks <b style="color:var(--acc)">{esc(r["line"]["pick_team"]) if r.get("line") else "?"}</b> '
        f'({pct(r["line"]["pick_prob"]) if r.get("line") else "—"}), locks {esc(r.get("lock_utc"))}</li>'
        for r in nxt)
    resolved = [r for r in board["open"] if "resolution" in r]
    return f"""
<h1>Pick for every open CS2 match</h1>
<section class="note" aria-label="Executive summary"><h2 style="margin-top:0">Executive summary</h2>
<p><b>Every one of the {s['open']} open HotSpawn CS2 matches has a pick.</b>
{s['featured_market']} are featured market picks (de-vigged external book/exchange prices).
The other {s['resolved_this_session']} had no bookmaker price — this board resolves them from
official data only: {s['vrs_model']} via the calibrated Valve VRS model (both teams officially
rated) and {s['floor_estimate']} as clearly-labelled directional estimates (one team rated, the
unrated opponent assumed at the VRS floor). {s['unresolved']} are left without a number.</p>
<div class="quick">
<a href="picks.html">All {s['open']} picks<span>every match, both win probabilities, obvious pick</span></a>
<a href="unresolved.html">Unresolved &amp; limitations<span>directional picks, name ambiguities, what we could not verify</span></a>
<a href="sources.html">Sources<span>every official link behind a row</span></a>
<a href="method.html">Method<span>how a pick is originated, no HotSpawn crowd %</span></a>
<a href="flagged.html">Flagged for review<span>irregularities &amp; unverified leads</span></a>
<a href="../ourline/index.html">OURLINE board<span>the strict market-only companion (blanks kept blank)</span></a>
</div>
<p class="small">This board intentionally does <b>not</b> stop at the {s['featured_market']} bookmaker-priced
matches: it resolves the {s['resolved_this_session']} low-tier / uncovered fixtures the strict board leaves
blank, so you always get a pick. Directional (floor) picks are weaker — read the limitations before relying
on them. Observed {esc(board.get('base_generated_utc'))} UTC.</p></section>
<div class="stats">
<div class="stat"><b>{s['open']}</b><span>open matches</span></div>
<div class="stat"><b>{s['with_pick']}</b><span>with a pick</span></div>
<div class="stat"><b>{s['featured_market']}</b><span>market (featured)</span></div>
<div class="stat"><b>{s['vrs_model']}</b><span>VRS model</span></div>
<div class="stat"><b>{s['floor_estimate']}</b><span>directional</span></div>
<div class="stat"><b>{s['unresolved']}</b><span>unresolved</span></div>
<div class="stat"><b>{esc(vrs['snapshot'])}</b><span><a href="{esc(vrs['page_url'])}">Valve VRS snapshot</a></span></div>
</div>
<h2>Locking soonest</h2>
<ul class="small">{nxt_html}</ul>
<h2>What this board adds</h2>
<p class="small">The strict OURLINE board prices {s['featured_market']} of {s['open']} and keeps the rest blank
because its Valve snapshot aged past its own 14-day window. Valve's newest published standings is
{esc(vrs['snapshot'])} (Valve publishes about monthly). This board re-derives a pick for those
{s['resolved_this_session']} fixtures from that same official standings file, so coverage is complete.
Every resolution cites the official source; nothing is inferred from a HotSpawn crowd percentage and no
bookmaker price is fabricated or mis-joined.</p>"""


def render_unresolved(board):
    s = board["summary"]
    floor_rows = [r for r in board["open"] if r.get("line") and r["line"]["basis"] == "floor_estimate"]
    dup_rows = [r for r in board["open"] if "vrs_duplicate_name_resolved" in r.get("flags", [])]
    alias_rows = [r for r in board["open"] if "vrs_alias_join" in r.get("flags", [])]
    hard_unresolved = [r for r in board["open"] if not r.get("line")]

    def li_floor(r):
        res = r["resolution"]
        cands = res.get("possible_alias_candidates")
        extra = (f' <b class="small">May be rated under an alias:</b> {esc(", ".join(cands))} — '
                 f'if so the pick could change.' if cands else "")
        return (f'<li><a href="picks.html"><b>{esc(r["team_a"])} v {esc(r["team_b"])}</b></a> — '
                f'pick <b style="color:var(--acc)">{esc(r["line"]["pick_team"])}</b> '
                f'{pct(r["line"]["pick_prob"])} (directional). Rated side VRS '
                f'{esc(res["team_a"]["standing"] if res["rated_side"]=="a" else res["team_b"]["standing"])} / '
                f'{res["rated_points"]} pts vs an unrated opponent assumed at the floor '
                f'(#{res["floor"]["standing"]} / {res["floor_points"]} pts).{extra}</li>')

    def li_dup(r):
        key = "lilmix" if "lilmix" in (r["team_a"] + r["team_b"]).lower() else "chinggis warriors"
        dup = board["vrs_duplicates_resolved"].get(key, {})
        cands = "; ".join(f"#{c['standing']} ({c['points']} pts, last match {c.get('latest_match_date')})"
                          for c in dup.get("candidates", []))
        return (f'<li><b>{esc(r["team_a"])} v {esc(r["team_b"])}</b> — Valve lists more than one '
                f'"{esc(key.title())}" roster. Resolved to #{dup.get("chosen_standing")} (most recent counted '
                f'match, then higher standing). Candidates: {esc(cands)}. Flagged because a wrong roster would '
                f'move the line.</li>')

    def li_alias(r):
        res = r["resolution"]
        return (f'<li><b>{esc(r["team_a"])} v {esc(r["team_b"])}</b> — '
                f'{esc("; ".join(res.get("notes", [])))}</li>')

    return f"""
<h1>Unresolved &amp; limitations</h1>
<section class="note"><h2 style="margin-top:0">Where a pick is weaker than a bookmaker price</h2>
<p>This board gives every open match a pick, but not every pick is equally strong. Featured market picks
({s['featured_market']}) come from real external prices. The rest are originated from Valve's official
standings only, and carry the limitations below. {s['unresolved']} matches are left with no number at all.</p></section>

<h2>1. Directional picks — unrated opponent ({len(floor_rows)})</h2>
<p class="small">These matches have exactly one officially-rated team. We originate the pick as the rated team
and estimate its win probability against an opponent <i>assumed</i> at the VRS floor (#380 / 381 pts). The
opponent's true strength is unknown — it may be stronger — so the percentage is a directional estimate, not a
calibrated probability, and it is labelled <span class="badge b-dir">Directional</span> on the picks table.</p>
<ul>{''.join(li_floor(r) for r in floor_rows) or "<li class=small>None in this capture.</li>"}</ul>

<h2>2. Duplicate-name rosters resolved ({len(dup_rows)})</h2>
<p class="small">Valve keeps an older roster of the same organisation as a separate standings row. We resolve to
the roster with the most recent counted match (tie-broken by higher standing), read from the official details
file, and flag it.</p>
<ul>{''.join(li_dup(r) for r in dup_rows) or "<li class=small>None.</li>"}</ul>

<h2>3. Alias joins ({len(alias_rows)})</h2>
<p class="small">A HotSpawn name joined to an official VRS name by a documented rule.</p>
<ul>{''.join(li_alias(r) for r in alias_rows) or "<li class=small>None.</li>"}</ul>

<h2>4. Genuinely unresolved ({len(hard_unresolved)})</h2>
<ul>{''.join(f'<li><b>{esc(r["team_a"])} v {esc(r["team_b"])}</b> — neither team has an official rating and no '
              f'external price was found; no number invented. Flags: {esc(", ".join(r.get("flags", [])))}</li>'
              for r in hard_unresolved) or "<li class=small>None in this capture — every open match carries at least one rated team.</li>"}</ul>

<h2>5. Standing limitations of this board</h2>
<ul class="small">
<li><b>Valve snapshot age.</b> Valve's newest published global standings is {esc(board['vrs']['snapshot'])}
(published about monthly). Every VRS-model / floor number is relative to that snapshot, which is
~14 days old at capture; roster moves since then are not reflected.</li>
<li><b>Model, not market.</b> VRS-model and floor picks are our own logistic on Valve's points with a slope
(k = {board['calibration']['k']}) fitted to bookmaker lines — an estimate, weaker than a live price.</li>
<li><b>HLTV not machine-readable here.</b> The automated runner cannot parse HLTV betting pages, so HLTV is
not a numeric input; Valve's official standings are used instead.</li>
<li><b>Low-tier coverage.</b> Obscure teams are often absent from both bookmakers and Valve's top-380; those
rows can only be directional or unresolved.</li>
<li><b>Not betting advice.</b> Estimates only; verify against a live book before acting.</li>
</ul>"""


def render_sources(board):
    vrs = board["vrs"]
    books = {}
    for r in board["open"]:
        for q in r.get("quotes", []):
            books.setdefault(q.get("source_name") or q.get("source_key"), q.get("public_url"))
    book_rows = "".join(f'<tr><td data-l="Source">{esc(n)}</td><td data-l="Link"><a href="{esc(u)}">{esc(u)}</a></td></tr>'
                        for n, u in sorted(books.items()) if u)
    detail = {}
    for r in board["open"]:
        res = r.get("resolution") or {}
        for side in ("team_a", "team_b"):
            t = res.get(side)
            if t and t.get("details_url"):
                detail[t["team"]] = (t["details_url"], t["standing"], t["points"], t.get("latest_match_date"))
    detail_rows = "".join(
        f'<tr><td data-l="Team">{esc(n)}</td><td data-l="VRS">#{st} · {p} pts</td>'
        f'<td data-l="Last counted match">{esc(lm or "—")}</td>'
        f'<td data-l="Official details"><a href="{esc(u)}">Valve details</a></td></tr>'
        for n, (u, st, p, lm) in sorted(detail.items(), key=lambda kv: kv[1][1]))
    return f"""
<h1>Sources</h1>
<section class="note"><p>Featured market picks use de-vigged external book/exchange prices collected by the
OURLINE runner (HotSpawn is used only to know which matches exist — never its crowd pick %). VRS-model, floor
and alias resolutions use the official
<a href="{esc(vrs['page_url'])}">Valve Regional Standings, snapshot {esc(vrs['snapshot'])}</a> and each team's
official details file. Every picks-table row links to one of these.</p></section>
<h2>Bookmakers &amp; exchange (featured market picks)</h2>
<table class="cards"><thead><tr><th>Source</th><th>Link</th></tr></thead><tbody>{book_rows}</tbody></table>
<h2>Official Valve VRS team details used this board</h2>
<table class="cards"><thead><tr><th>Team</th><th>VRS</th><th>Last counted match</th><th>Official details</th></tr></thead>
<tbody>{detail_rows}</tbody></table>
<p class="small">Fixture list: <a href="{HS_API}">HotSpawn fixtures API</a> (enumeration only).</p>"""


def render_method(board):
    cal = board["calibration"]
    vrs = board["vrs"]
    return f"""
<h1>Method</h1>
<div class="note"><p>Short version: featured market picks use external prices with the margin removed. Matches
with no eligible price are resolved from Valve's official standings: a calibrated rating model when both teams
are rated, and a labelled directional estimate when only one is. HotSpawn is never a probability input and no
price is ever invented or mis-joined.</p></div>
<h2>1. Which matches</h2>
<p class="small">Every CS2 fixture open for picks in the <a href="{LOBBY}">HotSpawn lobby</a>, read from its
public fixtures API by the OURLINE collector. HotSpawn tells us <i>which</i> matches exist and when they lock;
its crowd pick percentages are not read.</p>
<h2>2. Featured market picks (unchanged from OURLINE)</h2>
<p class="small">Eligible external prices (Pinnacle, Bovada, Melbet, Kalshi) are de-vigged
(<code>p = (1/d) / (1/d_A + 1/d_B)</code>) and combined as a source-weighted consensus. A price is joined to a
fixture only when both team names match after normalisation (or a published alias) and the source start time is
within ±5 minutes; in-play prices are excluded. These {board['summary']['featured_market']} rows are copied
through unchanged.</p>
<h2>3. Valve VRS model (both teams rated)</h2>
<p class="small">Win probability from Valve's official points via
<code>p_A = 1/(1+10^(−k·g·Δ/400))</code>, where Δ is the points difference and
<code>g = 1/sqrt(1+3·Q²·RD²/π²)</code> with RD = 75 (Valve's own <code>model/glicko.js</code> /
<code>model/fit.js</code>). Valve's readme notes its curve is too steep, so the slope <b>k = {cal['k']}</b> is
least-squares fitted to {cal['n_pairs']} eligible priced fixtures (source: {esc(cal['source'])}). This is the
same model and the same fitted k the OURLINE board uses, so a model pick here equals the pick OURLINE would
publish if its Valve snapshot were inside its 14-day window.</p>
<h2>4. Directional floor estimate (one team rated)</h2>
<p class="small">When only one team is officially rated, the pick is that team and its probability is estimated
against an opponent assumed at the VRS floor (#{vrs['floor']['standing']} / {vrs['floor']['points']} pts — the
weakest ranked team). Because the unrated opponent's true strength is unknown, this is labelled
<span class="badge b-dir">Directional</span> and listed under Unresolved &amp; limitations. If the unrated name
shares a token with an official team (e.g. a renamed org), that is flagged as a possible alias that could change
the pick.</p>
<h2>5. Duplicate names &amp; aliases</h2>
<p class="small">Valve can list two rosters of one organisation. We resolve to the roster with the most recent
counted match (tie-broken by higher standing), read from the official details file, and flag it. Acronym
aliases (e.g. "Aurora YB" → "Aurora Young Blud") are applied only when the target is unambiguous in the
official standings, and are flagged.</p>
<h2>6. Automation</h2>
<p class="small"><code>.github/workflows/everymatch-19d6c262.yml</code> re-reads the newest OURLINE board and
the official Valve standings, re-derives every pick, re-renders these pages and commits. No manual input.</p>"""


def render_flagged(board):
    vrs = board["vrs"]
    alias_flag = [r for r in board["open"] if "unrated_team_may_be_rated_alias" in r.get("flags", [])]
    items = [
        ("F1 · Mis-joined book price elsewhere (irregularity)",
         "Another board (expanded) shows a book price for fixture 1081529 <b>Nexus v WROTBERRY</b>, but that "
         "price is for <b>Whitebit Team v Nexus</b> (DraculaN) — a loose name/competition match joined the wrong "
         "match. This board does <b>not</b> use it; 1081529 is resolved as a directional pick for Nexus (VRS "
         "#111) vs an unrated WROTBERRY. Source to check: "
         "<a href='https://www.bovada.lv/esports/counter-strike-2/draculan/whitebit-team-nexus-202610190500'>Bovada Whitebit–Nexus</a>."),
        ("F2 · Valve snapshot age",
         f"Valve's newest published global standings is <code>{esc(vrs['snapshot'])}</code> "
         f"(<a href='{esc(vrs['page_url'])}'>official file</a>), about 14 days old at capture. The OURLINE board "
         f"treats a &gt;14-day snapshot as unusable and drops its model; this board still uses it for the "
         f"unpriced fixtures because it is the newest official data, and labels every such row. Next Valve "
         f"publish is expected around 2026-11-02."),
        ("F3 · Unrated teams that may be a rated roster under another name",
         "The directional picks below share a name token with an official VRS team; if they are that roster the "
         "pick could change. Listed as leads, not used to move a number: " +
         "; ".join(f"<b>{esc(r['team_a'])} v {esc(r['team_b'])}</b> → {esc(', '.join(r['resolution'].get('possible_alias_candidates', [])))}"
                   for r in alias_flag) + "."),
        ("F4 · Duplicate-name rosters",
         "Valve lists two rosters each for Lilmix, Chinggis Warriors and Betclic. Resolved by most-recent "
         "counted match; the rejected candidate is recorded on the Unresolved page. A wrong roster would move "
         "the line."),
        ("F5 · HLTV not machine-readable",
         "The automated runner cannot parse HLTV betting pages, so HLTV is not used as a numeric input; Valve's "
         "official standings originate the non-market lines instead."),
    ]
    lis = "".join(f'<section class="note warn"><h2 style="margin-top:0">{esc(t)}</h2><p class=small>{b}</p></section>'
                  for t, b in items)
    return f"<h1>Flagged for review</h1>{lis}"


def main() -> int:
    board = json.loads((DATA / "board.json").read_text())
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(render_index(board))
    (SITE / "picks.html").write_text(page("All picks", "picks.html", render_picks(board), board))
    (SITE / "unresolved.html").write_text(page("Unresolved & limits", "unresolved.html", render_unresolved(board), board))
    (SITE / "sources.html").write_text(page("Sources", "sources.html", render_sources(board), board))
    (SITE / "flagged.html").write_text(page("Flagged", "flagged.html", render_flagged(board), board))
    (SITE / "method.html").write_text(page("Method", "method.html", render_method(board), board))
    (SITE / "index.html").write_text(page("Summary", "index.html", render_index(board), board))
    print("built", board["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
