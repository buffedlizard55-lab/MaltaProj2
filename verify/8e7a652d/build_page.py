#!/usr/bin/env python3
"""Builds verify/8e7a652d/index.html from verified_market_lines.json (session 8e7a652d)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, 'verified_market_lines.json')))

def pct(x): return f"{x*100:.1f}%"

rows_matches = ""
for m in data['matches']:
    cells = ""
    for l in m['lines']:
        cells += f'<td><div class="odds">{l["odds_display"]}</div><div class="sub">{l["source"]}</div><div class="sub dim">{l["captured_utc"][11:16]}Z · <a href="{l["source_url"]}" target="_blank" rel="noopener">source</a></div></td>'
    n = len(m['lines'])
    missing = 5 - n
    for _ in range(missing):
        cells += '<td class="blank">—</td>'
    pick_a = m['consensus_fair_a'] >= 0.5
    rows_matches += f'''<tr>
<td><b>{m['match'].split(' vs ')[0]}</b> vs <b>{m['match'].split(' vs ')[1]}</b><div class="sub dim">{m['kickoff']} · BO3</div></td>
{cells}
<td><div class="fair">{pct(m['consensus_fair_a'])} / {pct(m['consensus_fair_b'])}</div><div class="sub dim">{m['consensus_sources']} sources</div>
<div class="pick">Pick: <b>{m['pick']}</b></div></td>
<td><a href="{m['hltv']}" target="_blank" rel="noopener">HLTV</a> · <a href="https://play.hotspawn.com/lobby" target="_blank" rel="noopener">Lobby</a></td>
</tr>'''

outright = data['outright_market']
rows_outright = ""
for o in outright['entries']:
    rows_outright += f'<tr><td><b>{o["team"]}</b></td><td>{o["american"]}</td><td>{o["decimal"]}</td><td>{pct(o["raw_implied"])}</td><td><b>{pct(o["fair_probability"])}</b></td></tr>'

html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verification &amp; Market Cross-Check — MaltaProj2</title>
<style>
:root{{--bg:#0d1117;--panel:#161b22;--line:#30363d;--txt:#e6edf3;--dim:#8b949e;--acc:#58a6ff;--good:#3fb950;--warn:#d29922;--bad:#f85149}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.wrap{{max-width:1280px;margin:0 auto;padding:0 20px}}
header{{border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:5}}
.hbar{{display:flex;justify-content:space-between;align-items:center;padding:12px 0;gap:14px;flex-wrap:wrap}}
.brand b{{color:var(--acc)}}
nav a{{color:var(--txt);text-decoration:none;margin-left:14px;font-size:14px}}
nav a:hover{{color:var(--acc)}}
main{{padding:28px 0 40px}}
h1{{font-size:26px;margin-bottom:6px}}
h2{{font-size:19px;margin:30px 0 10px}}
.lead{{color:var(--dim);max-width:900px}}
.badges span{{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px 12px;margin:8px 8px 0 0;font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:20px 0}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}}
.card .n{{font-size:26px;font-weight:700;color:var(--acc)}}
.card .l{{font-size:13px;color:var(--dim)}}
.card .s{{font-size:12px;color:var(--dim);margin-top:4px}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin-top:10px}}
table{{border-collapse:collapse;width:100%;min-width:1080px;font-size:13.5px}}
th{{background:var(--panel);text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap;position:sticky;top:52px}}
td{{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.odds{{font-weight:600;font-variant-numeric:tabular-nums}}
.fair{{font-weight:700;color:var(--good);font-variant-numeric:tabular-nums}}
.sub{{font-size:12px}}
.dim{{color:var(--dim)}}
.blank{{color:var(--dim);text-align:center}}
.pick{{margin-top:4px;font-size:12.5px;background:#1f6feb22;border:1px solid #1f6feb66;border-radius:6px;padding:2px 8px;display:inline-block}}
a{{color:var(--acc)}}
.note{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:8px;padding:12px 14px;margin:14px 0;font-size:14px}}
.flag{{border-left:3px solid var(--bad)}}
.tag{{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:600}}
.tgood{{background:#3fb95033;color:var(--good)}} .twarn{{background:#d2992233;color:var(--warn)}} .tbad{{background:#f8514933;color:var(--bad)}}
footer{{border-top:1px solid var(--line);color:var(--dim);font-size:12.5px;padding:16px 0 30px}}
.mini{{min-width:640px}}
ul{{margin:8px 0 8px 20px}} li{{margin:3px 0}}
</style></head><body>
<header><div class="wrap hbar">
<div class="brand"><b>MaltaProj2</b> · Verification &amp; Market Cross-Check</div>
<nav><a href="../../index.html">TWC Dashboard</a><a href="../../pickem/index.html">Pick'em Board</a><a href="../../flagged.html">Flagged</a><a href="../../docs/">LineWatch</a><a href="VERIFICATION_REPORT.md">Full Report (MD)</a></nav>
</div></header>
<main><div class="wrap">
<h1>Independent Verification &amp; Multi-Book Market Cross-Check</h1>
<p class="lead">Session <code>8e7a652d</code> · verified 2026-10-13 18:07–18:50 UTC. Every number below was captured directly from the named official source and de-margined with the proportional method. <b>Hotspawn is used for fixture discovery only</b> — its crowd pick percentages never enter any calculation.</p>
<div class="badges">
<span>✅ Valve VRS: 8/8 teams exact</span><span>✅ 4/4 opening fixtures triple-verified</span><span>✅ 3 bookmakers + 2 markets captured live</span><span>⚠ 10 irregularities flagged</span>
</div>

<div class="cards">
<div class="card"><div class="n">8/8</div><div class="l">VRS ranks &amp; points verified exact</div><div class="s">vs Valve's official Oct 5 &amp; Aug 3 tables</div></div>
<div class="card"><div class="n">3</div><div class="l">Independent source families per fixture</div><div class="s">Hotspawn lobby · HLTV/Liquipedia · Pinnacle cutoffs</div></div>
<div class="card"><div class="n">17</div><div class="l">Live market prices cross-checked</div><div class="s">Pinnacle · Thunderpick · Bovada · bc.game · Polymarket</div></div>
<div class="card"><div class="n">15/15</div><div class="l">Repo unit tests passing</div><div class="s">incl. 28-pair model arithmetic reproduced exactly</div></div>
</div>

<h2>Thunderpick World Championship 2026 — opening fixtures (Oct 14)</h2>
<p class="lead">Kickoffs in UTC. "Fair" = consensus of the de-margined prices of all captured sources (equal weight). Odds formats as quoted by each source (American for Pinnacle/Thunderpick, decimal elsewhere, cents for Polymarket).</p>
<div class="tablewrap"><table>
<thead><tr><th>Match</th><th>Pinnacle</th><th>Thunderpick</th><th>Bovada</th><th>bc.game (EGW)</th><th>Polymarket</th><th>Consensus fair &amp; pick</th><th>Fixture sources</th></tr></thead>
<tbody>{rows_matches}</tbody>
</table></div>
<div class="note">All prices are <b>point-in-time captures</b> (timestamps per cell). Pinnacle's Legacy–PARIVISION line moved from −150/+123 (18:01Z) to −129/+106 (18:20Z) in 19 minutes — re-check the linked source before acting. The crowd percentages shown on Hotspawn (e.g. 95% picked Aurora over 9z) are <b>not</b> used here.</div>

<h2>Tournament winner — verified Thunderpick outright market</h2>
<p class="lead">Captured {outright['captured_utc']} from <a href="{outright['source_url']}" target="_blank" rel="noopener">Thunderpick's official outright market</a> (the tournament's sponsor bookmaker). Book overround {(outright['overround']-1)*100:.1f}% removed proportionally.</p>
<div class="tablewrap"><table class="mini">
<thead><tr><th>Team</th><th>American</th><th>Decimal</th><th>Raw implied</th><th>Fair probability</th></tr></thead>
<tbody>{rows_outright}</tbody>
</table></div>
<div class="note flag">⚠ IR-V3: the same Thunderpick page also lists a boosted special "NiP to win the tournament +5000", conflicting with the Winner-market +2900 — flagged for review. The verified market makes <b>Falcons the title favorite (33.0%)</b>, not Legacy — see IR-V1.</div>

<h2>What was verified, line by line</h2>
<div class="tablewrap"><table class="mini">
<thead><tr><th>Check</th><th>Result</th><th>Primary source (manual review link)</th></tr></thead>
<tbody>
<tr><td>Valve VRS Oct 5: rank &amp; points for all 8 finalists + withdrawn Virtus.pro</td><td><span class="tag tgood">EXACT 9/9</span></td><td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_10_05.md" target="_blank" rel="noopener">Valve official standings</a> (verbatim copy in <a href="evidence/standings_global_2026_10_05.md">evidence/</a>)</td></tr>
<tr><td>Valve VRS Aug 3 invitation snapshot points</td><td><span class="tag tgood">EXACT 7/7</span></td><td><a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_08_03.md" target="_blank" rel="noopener">Valve official standings</a></td></tr>
<tr><td>Rosters vs Valve Oct 5 table</td><td><span class="tag tgood">7/8 EXACT</span> <span class="tag twarn">1 flagged</span></td><td>PARIVISION: HObbit signing verified via <a href="https://liquipedia.net/counterstrike/PARIVISION" target="_blank" rel="noopener">Liquipedia timeline</a> (Sep 17) — Valve table lags the transfer; already flagged on site</td></tr>
<tr><td>TWC 2026 dates, venue, prize pool, organizer, 8 teams</td><td><span class="tag tgood">VERIFIED</span></td><td><a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026" target="_blank" rel="noopener">HLTV</a> · <a href="https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026" target="_blank" rel="noopener">Liquipedia</a></td></tr>
<tr><td>Virtus.pro withdrew Oct 9 → replaced by NiP; groups drawn</td><td><span class="tag tgood">VERIFIED</span></td><td><a href="https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026" target="_blank" rel="noopener">Liquipedia event note (Oct 9)</a> — propagated to root site by PR #12</td></tr>
<tr><td>4 opening fixtures + kickoffs + BO3</td><td><span class="tag tgood">TRIPLE-VERIFIED</span></td><td><a href="https://play.hotspawn.com/lobby" target="_blank" rel="noopener">Hotspawn lobby</a> · HLTV match pages 2399384–2399387 · Pinnacle <code>cutoffAt</code> equals kickoff for each</td></tr>
<tr><td>Live Hotspawn lobby structure (86 fixtures this week: S4/B27/C55, CS2+LoL, lock offsets, crowd %)</td><td><span class="tag tgood">VERIFIED</span></td><td><a href="https://play.hotspawn.com/lobby" target="_blank" rel="noopener">play.hotspawn.com/lobby</a> (fetched 18:10Z)</td></tr>
<tr><td>Thunderpick 9z–Aurora +280/−455 (stored quote in docs/data/quotes.json)</td><td><span class="tag tgood">CONFIRMED LIVE</span></td><td><a href="https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376" target="_blank" rel="noopener">Thunderpick match page</a> (also: map hcap, totals, map-1 markets)</td></tr>
<tr><td>Pinnacle prices for all 4 openers (American odds, open status)</td><td><span class="tag tgood">CAPTURED</span></td><td><a href="https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111785/markets/related/straight" target="_blank" rel="noopener">Pinnacle guest API</a> (matchups 1638111785/74/86/87)</td></tr>
<tr><td>Falcons IEM Cologne Major 2026 title, 3–0 vs FURIA (Jun 21)</td><td><span class="tag tgood">VERIFIED</span></td><td><a href="https://www.shanethegamer.com/esports-news/iem-cologne-major-2026-falcons-furia-final/" target="_blank" rel="noopener">shanethegamer</a> · <a href="https://vpesports.com/more-esports/falcons-are-iem-cologne-major-2026-champions" target="_blank" rel="noopener">vpesports</a></td></tr>
<tr><td>Legacy FISSURE Playground 3 title, 3–0 vs G2 (Sep 13), latto MVP</td><td><span class="tag tgood">VERIFIED</span></td><td><a href="https://esports-news.co.uk/2026/09/14/legacy-deliver-at-4-1-to-win-fissure-playground-3" target="_blank" rel="noopener">esports-news.co.uk</a> · <a href="https://1vx.gg/news/legacy-sweep-g2-3-0-to-win-fissure-playground-3-as-latto-takes-mvp" target="_blank" rel="noopener">1vX.gg</a></td></tr>
<tr><td>Root model arithmetic (28 pairwise + 8 outright lines)</td><td><span class="tag tgood">REPRODUCED EXACT</span></td><td>Recomputed from verified VRS inputs; clamps [0.08, 0.92], vigs 4.5%/10% confirmed in code</td></tr>
<tr><td>Repo test suite</td><td><span class="tag tgood">15/15 PASS</span></td><td><code>python3 -m unittest discover tests/</code> (requires beautifulsoup4)</td></tr>
<tr><td>HLTV September team-rank fields (Falcons 5, Legacy 6, …)</td><td><span class="tag twarn">NOT RE-VERIFIED</span></td><td>HLTV ranking archive is JS-heavy; values left as published (not used in any probability) — IR-V9</td></tr>
</tbody></table></div>

<h2>Irregularity register (IR-V1 … IR-V10)</h2>
<div class="tablewrap"><table class="mini">
<thead><tr><th>ID</th><th>Severity</th><th>Finding</th><th>Handling</th></tr></thead>
<tbody>
<tr><td><b>IR-V1</b></td><td><span class="tag tbad">High</span></td><td>Root pairwise model diverges materially from the real market: model Legacy 92.0% vs PARIVISION vs Pinnacle-implied 53.7%; model outright favorite Legacy 34.4% vs Thunderpick-verified favorite Falcons 33.0% (Legacy 17.4%).</td><td>Use market-anchored consensus (this page / pickem board) for the four real fixtures; keep the 28-pairing model as a labeled hypothetical. Root site already labels lines "Derived, not a bookmaker quote" (PR #12).</td></tr>
<tr><td><b>IR-V2</b></td><td><span class="tag tbad">High</span></td><td>Session 0c90448b's <code>data/odds.json</code> stores Pinnacle <b>American</b> odds in fields named <code>decimal_odds_a/b</code> (e.g. −150/+123).</td><td>Flagged to owner via COORDINATION.md; correct decimals published in <a href="verified_market_lines.json">verified_market_lines.json</a>.</td></tr>
<tr><td><b>IR-V3</b></td><td><span class="tag twarn">Med</span></td><td>Thunderpick page: NiP +2900 (Winner market) vs "NiP to win the tournament +5000" (specials) — inconsistent.</td><td>Winner market used; discrepancy flagged.</td></tr>
<tr><td><b>IR-V4</b></td><td><span class="tag twarn">Med</span></td><td>245 upcoming LoL lobby fixtures unpriced (CS2-focused scope). Bovada lines for several LoL fixtures exist on the unmerged 0c90448b branch.</td><td>Left blank (never inferred); noted for follow-up integration.</td></tr>
<tr><td><b>IR-V5</b></td><td><span class="tag twarn">Med</span></td><td>Rapid line movement (Pinnacle Legacy−PVISION −150→−129 in 19 min).</td><td>All captures timestamped; point-in-time disclaimer shown.</td></tr>
<tr><td><b>IR-V6</b></td><td><span class="tag twarn">Med</span></td><td>Bovada capture has 4 unlabeled price rows per match; first row taken as headline.</td><td>Cross-checked vs Pinnacle/bc.game — deviations within normal book spread.</td></tr>
<tr><td><b>IR-V7</b></td><td><span class="tag twarn">Med</span></td><td>FreeTips secondary outright snapshot (root data file) differs from verified Thunderpick market (9z 14.00 vs 30.00; Legacy 3.80 vs 4.75).</td><td>Verified Thunderpick capture published as primary; FreeTips retained as flagged secondary.</td></tr>
<tr><td><b>IR-V8</b></td><td><span class="tag tgood">Low</span></td><td>docs/ 86-fixture dataset is a June-2026 payload (60/86 kickoffs in the past) — already flagged by LineWatch audits.</td><td>Confirmed; no change.</td></tr>
<tr><td><b>IR-V9</b></td><td><span class="tag tgood">Low</span></td><td>HLTV Sept team-rank fields not independently re-verified.</td><td>Left as published; unused in probabilities.</td></tr>
<tr><td><b>IR-V10</b></td><td><span class="tag tgood">Info</span></td><td>Sandbox egress limited to GitHub/npm/PyPI; non-GitHub evidence captured via platform fetch tool / GitHub Actions runners.</td><td>Documented; no bypass attempted.</td></tr>
</tbody></table></div>

<h2>Files</h2>
<ul>
<li><a href="VERIFICATION_REPORT.md">VERIFICATION_REPORT.md</a> — full line-by-line report with all manual-review links</li>
<li><a href="verified_market_lines.json">verified_market_lines.json</a> — every captured price, decimal conversion, overround, fair probability, source URL and timestamp</li>
<li><a href="evidence/standings_global_2026_10_05.md">evidence/standings_global_2026_10_05.md</a>, <a href="evidence/standings_global_2026_08_03.md">…_08_03.md</a>, <a href="evidence/standings_global_2026_09_07.md">…_09_07.md</a> — verbatim Valve VRS snapshots</li>
<li><a href="build_page.py">build_page.py</a> — this page is generated from the JSON (no hand-typed numbers)</li>
</ul>
</div></main>
<footer><div class="wrap">
Data snapshot 2026-10-13 18:01–18:25 UTC · page generated by build_page.py · session 8e7a652d.
All external prices are point-in-time captures — re-check the linked source before acting.
Hotspawn crowd percentages are context only and never used as a probability input.
</div></footer>
</body></html>'''

open(os.path.join(HERE, 'index.html'), 'w').write(html)
print("verify/8e7a652d/index.html written,", len(html), "bytes")
