#!/usr/bin/env python3
"""T4: generate the GitHub Pages site in docs/ from data/*.csv.

Pages: index.html (dashboard), cs2.html, lol.html, flagged.html + style.css.
Every table row links its official sources (Hotspawn match card always; external
odds source when a line exists). Rows without an external line show a blank
probability and an "unverified" badge — never inferred or filled.

Also runs T5-style checks after writing: every data row must contain a source
link, and every unpriced row must carry the unverified badge.

Usage: python3 tools/build_site.py   (from repo root)
"""

import csv
import os
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
REPO = "https://github.com/buffedlizard55-lab/MaltaProj2"
GENERATED = "2026-10-13"

CSS = """
:root { --ink:#1c2333; --muted:#5c6675; --line:#d9dee6; --bg:#f6f7f9; --card:#ffffff;
        --accent:#1653c4; --good:#0a7d43; --warn:#b45309; --bad:#b91c1c; }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       color:var(--ink); background:var(--bg); }
header { background:#142242; color:#fff; padding:22px 24px 16px; }
header h1 { margin:0 0 4px; font-size:23px; }
header p { margin:2px 0; color:#c7d2e6; font-size:14px; }
nav { background:#fff; border-bottom:1px solid var(--line); padding:10px 24px; }
nav a { margin-right:18px; color:var(--accent); text-decoration:none; font-weight:600; }
nav a.on { text-decoration:underline; }
main { padding:20px 24px 40px; max-width:1220px; margin:0 auto; }
h2 { font-size:19px; margin:26px 0 10px; }
h3 { font-size:16px; margin:20px 0 8px; }
.cards { display:flex; flex-wrap:wrap; gap:12px; margin:14px 0 6px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:12px 16px; min-width:150px; }
.card b { display:block; font-size:24px; }
.card span { color:var(--muted); font-size:12.5px; }
table { border-collapse:collapse; width:100%; background:var(--card); font-size:13.5px; }
th, td { border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
th { background:#eef1f6; position:sticky; top:0; }
tr:nth-child(even) td { background:#fafbfc; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.badge { display:inline-block; padding:1px 8px; border-radius:9px; font-size:11.5px; font-weight:600; }
.b-ok { background:#e2f5ea; color:var(--good); }
.b-unv { background:#fde8e8; color:var(--bad); }
.b-ctx { background:#eef1f6; color:var(--muted); }
.note { background:#fff8e8; border:1px solid #e7d39a; border-radius:8px;
        padding:10px 14px; margin:12px 0; font-size:13.5px; }
.ok-box { background:#e9f6ee; border:1px solid #b5dcc4; border-radius:8px;
          padding:10px 14px; margin:12px 0; font-size:13.5px; }
footer { color:var(--muted); font-size:12.5px; padding:18px 24px 30px; }
a { color:var(--accent); }
.src a { white-space:nowrap; }
.tsrc { color:var(--muted); font-size:12px; }
"""

NAV = [("analysis.html", "Dashboard"), ("cs2.html", "CS2 Matches"),
       ("lol.html", "LoL Matches"), ("flagged.html", "Flagged for Review")]


def page(name, title, body):
    nav = "".join(
        f'<a href="{href}" class="{"on" if href == name else ""}">{label}</a>'
        for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="analysis-style.css">
</head>
<body>
<header>
<h1>Hotspawn Pick'em — Match Inventory &amp; Market Win Probabilities</h1>
<p>Reverse-engineered lobby of <a style="color:#9db8ee" href="https://play.hotspawn.com/lobby">play.hotspawn.com</a> ·
probabilities derived exclusively from external bookmaker lines · generated {GENERATED}</p>
</header>
<nav>{nav}</nav>
<main>
{body}
</main>
<footer>Generated {GENERATED} by session <code>arena-1da4b0ef-maltaproj2</code> ·
data: <a href="{REPO}/blob/main/data/matches.csv">matches.csv</a> ·
<a href="{REPO}/blob/main/data/odds.csv">odds.csv</a> ·
<a href="{REPO}/blob/main/data/probabilities.csv">probabilities.csv</a> ·
<a href="{REPO}/blob/main/data/analysis.md">analysis.md</a> ·
<a href="{REPO}/blob/main/data/irregularities.md">irregularities.md</a></footer>
</body>
</html>
"""


def load():
    matches = {r["match_id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "matches.csv"), encoding="utf-8"))}
    probs = {r["match_id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "probabilities.csv"), encoding="utf-8"))}
    odds = {r["match_id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "odds.csv"), encoding="utf-8"))}
    return matches, probs, odds


def row_html(m, p, o):
    mid = m["match_id"]
    match_cell = (f'<b>{escape(m["team1"])}</b> vs <b>{escape(m["team2"])}</b><br>'
                  f'<span class="tsrc">id {mid}</span>')
    start = f'{escape(m["start_display_et"])} ET<br><span class="tsrc">{escape(m["start_utc"])} UTC</span>'
    comm = f'{escape(m["team1_pct"])}% / {escape(m["team2_pct"])}%'
    if o["odds_team1"]:
        odds_cell = (f'{escape(o["odds_team1"])} / {escape(o["odds_team2"])}<br>'
                     f'<span class="tsrc">{escape(o["bookmaker"])}</span>')
        prob_cell = (f'<b>{escape(p["team1_prob_pct"])}%</b> / <b>{escape(p["team2_prob_pct"])}%</b><br>'
                     f'<span class="tsrc">de-vig of {escape(o["odds_team1"])} / {escape(o["odds_team2"])}</span>')
        status = '<span class="badge b-ok">verified line</span>'
        srcs = [f'<a href="{escape(o["source_url"])}">{escape(o["source_name"])} (odds)</a>']
        if o["secondary_source_url"]:
            sec = f'{escape(o["secondary_source_name"])}'
            if o["secondary_odds_team1"]:
                sec += f' ({escape(o["secondary_odds_team1"])}/{escape(o["secondary_odds_team2"])})'
            srcs.append(f'<a href="{escape(o["secondary_source_url"])}">{sec}</a>')
    else:
        odds_cell = '<span class="b-ctx badge">no market published</span>'
        prob_cell = '— <span class="badge b-unv">unverified</span>'
        status = '<span class="badge b-unv">unverified</span>'
        srcs = []
    srcs.append(f'<a href="{escape(m["hotspawn_url"])}">Hotspawn match card</a>')
    src_cell = '<div class="src">' + '<br>'.join(srcs) + '</div>'
    return (f'<tr><td>{match_cell}</td><td>{escape(m["tournament"])}<br>'
            f'<span class="tsrc">{escape(m["stage"])} · tier {escape(m["tier"])} · '
            f'{escape(m["points"])} pts</span></td>'
            f'<td>{start}</td><td class="num">{comm}</td><td>{odds_cell}</td>'
            f'<td>{prob_cell}</td><td>{status}</td><td>{src_cell}</td></tr>')


TABLE_HEAD = ("<tr><th>Match</th><th>Tournament</th><th>Start</th>"
              '<th>Community picks<br><span class="tsrc">context only</span></th>'
              "<th>Market odds (external)</th><th>Our win probability</th>"
              "<th>Status</th><th>Sources</th></tr>")


def table(rows_html):
    return f'<table>{TABLE_HEAD}{"".join(rows_html)}</table>'


def build():
    os.makedirs(DOCS, exist_ok=True)
    matches, probs, odds = load()
    ordered = sorted(matches.values(), key=lambda m: (m["game"], m["start_utc"], m["match_id"]))

    cs2 = [m for m in ordered if m["game"] == "CS2"]
    lol = [m for m in ordered if m["game"] == "LoL"]
    priced = [m for m in ordered if odds[m["match_id"]]["odds_team1"]]

    # ---- cs2.html ----
    body = ['<h2>Counter-Strike 2 — all 26 pick\'em matches</h2>',
            '<div class="note">Win probabilities are derived only from external bookmaker lines '
            '(proportional de-vig). Community pick % is shown for context and was <b>never</b> used '
            'to derive probabilities. Rows without a published market are blank and flagged '
            '<span class="badge b-unv">unverified</span>.</div>',
            table(row_html(m, probs[m["match_id"]], odds[m["match_id"]]) for m in cs2)]
    open(os.path.join(DOCS, "cs2.html"), "w", encoding="utf-8").write(
        page("cs2.html", "CS2 matches — Hotspawn pick'em analysis", "\n".join(body)))

    # ---- lol.html ----
    body = ['<h2>League of Legends — all 231 pick\'em matches</h2>',
            '<div class="note">Only 4 LoL matches have published bookmaker markets on any checked '
            'source (Worlds Play-In ×2, Demacia Cup semifinal, EMEA Masters Summer semifinal). '
            'The remaining 227 rows are left blank + <span class="badge b-unv">unverified</span> — '
            'values are never inferred. See the <a href="flagged.html">Flagged for Review</a> page.</div>']
    current = None
    rows = []
    for m in lol:
        if m["tournament"] != current:
            if rows:
                body.append(table(rows))
                rows = []
            current = m["tournament"]
            body.append(f'<h3>{escape(current)}</h3>')
        rows.append(row_html(m, probs[m["match_id"]], odds[m["match_id"]]))
    if rows:
        body.append(table(rows))
    open(os.path.join(DOCS, "lol.html"), "w", encoding="utf-8").write(
        page("lol.html", "LoL matches — Hotspawn pick'em analysis", "\n".join(body)))

    # ---- index.html ----
    n_unv = len(matches) - len(priced)
    lobby_link = '<a href="https://play.hotspawn.com/lobby">Hotspawn lobby</a>'
    findings = [
        ("ex-Keyd Stars vs Galorys", "Galorys 62.5% (2.43/1.46)", "ex-Keyd Stars 86%",
         "Market favorite is Galorys; community heavily on ex-Keyd Stars",
         odds["1081076"]["source_url"], m_url(matches, "1081076")),
        ("WROTBERRY vs ENCE", "WROTBERRY 57.9% (1.6/2.2)", "ENCE 71%",
         "Market favorite is WROTBERRY; community on ENCE",
         odds["1080281"]["source_url"], m_url(matches, "1080281")),
        ("Zomblers vs Overtake Sector", "Overtake Sector 62.4% (2.46/1.48)", "Overtake Sector 89%",
         "Same side, community far more extreme than the market",
         odds["1079546"]["source_url"], m_url(matches, "1079546")),
        ("HOTU vs Fnatic", "Fnatic 52.0% (1.97/1.82)", "Fnatic 91%",
         "Market sees a near coin-flip",
         odds["1079439"]["source_url"], m_url(matches, "1079439")),
        ("Cloud9 vs Karmine Corp", "Karmine Corp 65.8% (2.71/1.41)", "no picks yet",
         "GG.bet (2.41/1.54) and N1 Bet both make KC favorite",
         odds["1075808"]["source_url"], m_url(matches, "1075808")),
        ("KT Rolster vs BNK FearX", "KT 71.4% (1.31/3.27)", "no picks yet",
         "EGW widget and Polymarket (KT 65–66% devig) agree",
         odds["1076650"]["source_url"], m_url(matches, "1076650")),
        ("Falcons vs Ninjas in Pyjamas", "Falcons 76.3% (1.23/3.95)", "Falcons 89%",
         "One-sided Bo3, both sides agree",
         odds["1080177"]["source_url"], m_url(matches, "1080177")),
        ("9z vs Aurora", "Aurora 73.9% (3.6/1.27)", "Aurora 95%",
         "One-sided Bo3, both sides agree",
         odds["1080176"]["source_url"], m_url(matches, "1080176")),
    ]
    frows = "".join(
        f'<tr><td><b>{escape(a)}</b></td><td>{escape(b)}</td><td>{escape(c)}</td><td>{escape(d)}</td>'
        f'<td class="src"><a href="{escape(e)}">odds source</a><br>'
        f'<a href="{escape(f)}">Hotspawn card</a></td></tr>'
        for a, b, c, d, e, f in findings)
    body = f"""
<h2>Dashboard</h2>
<div class="cards">
<div class="card"><b>257</b><span>pick'em matches captured<br>(26 CS2 · 231 LoL)</span></div>
<div class="card"><b>28</b><span>with external bookmaker line<br>(24 CS2 · 4 LoL)</span></div>
<div class="card"><b>28</b><span>win probabilities derived<br>(de-vigged, our own)</span></div>
<div class="card"><b>{n_unv}</b><span>blank + flagged<br>"unverified"</span></div>
<div class="card"><b>11</b><span>irregularities flagged<br>for review</span></div>
</div>

<div class="ok-box"><b>Method.</b> Each probability is the proportional de-vig of a two-way
external bookmaker market: <code>p = (1/o) / (1/o1 + 1/o2)</code>, with decimal odds captured on
2026-10-13 from GG.BET, BC.GAME or N1 Bet bookmaker panels (via EGamersWorld event/match pages),
plus GG.bet (tips.gg/win.gg) and Polymarket cross-checks. Hotspawn community pick percentages
are displayed for context only and are <b>never</b> used as probability indicators. Matches with
no published market stay blank and are flagged unverified — nothing is inferred or filled.</div>

<h2>Key findings — market vs community</h2>
<p>Community % is the Hotspawn lobby pick split (context only). Every row links its odds source
and the official Hotspawn match card.</p>
<table>
<tr><th>Match</th><th>Market favorite (our line)</th><th>Community favorite</th><th>Read</th><th>Sources</th></tr>
{frows}
</table>

<h2>Coverage</h2>
<table>
<tr><th>Segment</th><th>Matches</th><th>With line</th><th>Unverified</th><th>Inventory source</th></tr>
<tr><td>CS2 — Thunderpick World Championship (S)</td><td>4</td><td>4</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>CS2 — Stake Pulse Beat III (B)</td><td>4</td><td>4</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>CS2 — CCT Europe Series #11 (B)</td><td>4</td><td>2</td><td>2</td><td>{lobby_link}</td></tr>
<tr><td>CS2 — ESL Challenger League cups (B)</td><td>2</td><td>2</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>CS2 — Elisa BreakOut Series #2 (C)</td><td>12</td><td>12</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>LoL — Worlds 2026 Play-In</td><td>2</td><td>2</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>LoL — Demacia Cup / EMEA Masters Summer</td><td>2</td><td>2</td><td>0</td><td>{lobby_link}</td></tr>
<tr><td>LoL — LGC Rising Playoffs</td><td>2</td><td>0</td><td>2</td><td>{lobby_link}</td></tr>
<tr><td>LoL — minor leagues (PRM 2nd/3rd, Tunisian, RIVALS, Arabian 2nd, Komplettligaen, LigaGG CELOL A, Superstrike, MängudeÖÖ, Benelux)</td><td>225</td><td>0</td><td>225</td><td>{lobby_link}</td></tr>
<tr><td><b>Total</b></td><td><b>257</b></td><td><b>28</b></td><td><b>229</b></td><td>{lobby_link}</td></tr>
</table>

<h2>Browse</h2>
<ul>
<li><a href="cs2.html">CS2 matches (26)</a> — full table with odds, probabilities and per-row sources</li>
<li><a href="lol.html">LoL matches (231)</a> — full table, grouped by tournament</li>
<li><a href="flagged.html">Flagged for Review</a> — irregularities and unverified items</li>
</ul>
"""
    open(os.path.join(DOCS, "analysis.html"), "w", encoding="utf-8").write(
        page("analysis.html", "Hotspawn pick'em — analysis dashboard", body))

    # ---- flagged.html ----
    irr = open(os.path.join(ROOT, "data", "irregularities.md"), encoding="utf-8").read()
    body = f"""
<h2>Flagged for Review</h2>
<p>Items below are flagged, published with source links, and do not block merge. Unverified
values were left blank — never inferred or filled.</p>
<div class="note"><b>229 matches carry no external bookmaker line</b> (4 individual matches +
225 minor-league LoL). Their probability cells are blank and badge-marked
<span class="badge b-unv">unverified</span> on the category pages. No market exists on any
checked source (EGamersWorld/GG.BET/BC.GAME/N1 Bet, GG.bet, Polymarket, HLTV, odds aggregators).</div>
<h3>Irregularities log (<a href="{REPO}/blob/main/data/irregularities.md">data/irregularities.md</a>)</h3>
<pre style="white-space:pre-wrap;background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:12.5px">{escape(irr)}</pre>
"""
    open(os.path.join(DOCS, "flagged.html"), "w", encoding="utf-8").write(
        page("flagged.html", "Flagged for Review — Hotspawn pick'em analysis", body))

    with open(os.path.join(DOCS, "analysis-style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)

    verify(matches, probs, odds, ordered)
    print(f"site written to docs/ ({len(ordered)} matches, {len(priced)} priced)")


def m_url(matches, mid):
    return matches[mid]["hotspawn_url"]


def verify(matches, probs, odds, ordered):
    """T5 checks: every table row links a source; unpriced rows are flagged unverified."""
    for page_name in ("analysis.html", "cs2.html", "lol.html", "flagged.html"):
        path = os.path.join(DOCS, page_name)
        assert os.path.getsize(path) > 500, f"{page_name} suspiciously small"
    for m in ordered:
        mid = m["match_id"]
        assert m["hotspawn_url"].startswith("https://"), f"row {mid} missing official link"
        o, p = odds[mid], probs[mid]
        if o["odds_team1"]:
            assert o["source_url"].startswith("https://"), f"row {mid} priced but no odds source"
            assert p["team1_prob_pct"] and p["team2_prob_pct"], f"row {mid} priced but no probs"
        else:
            assert not p["team1_prob_pct"], f"row {mid} unpriced but has probs (forbidden fill!)"
            assert p["status"] == "unverified", f"row {mid} unpriced but not flagged"
    for name in ("cs2.html", "lol.html"):
        html = open(os.path.join(DOCS, name), encoding="utf-8").read()
        assert html.count("unverified") >= 1 or name == "cs2.html"
        assert 'href="https://www.hotspawn.com/matches/' in html, f"{name} lacks per-row source links"
    print("verification checks passed (T5 pre-check)")


if __name__ == "__main__":
    build()
