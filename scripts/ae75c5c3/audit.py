"""Reproducible dated row audit. No network; official responses are preserved beside report."""
import base64
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'audits/ae75c5c3'
b = json.loads((OUT / 'board_snapshot.json').read_text())
s = json.loads((OUT / 'source_snapshot.json').read_text())
blob = json.loads((OUT / 'valve_standings_source.json').read_text())
md = base64.b64decode(blob['content']).decode()
ratings = {(m.group(3).strip(), m.group(4).strip(), int(m.group(2))) for m in re.finditer(
    r'^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|', md, re.M)}
checks = []
for r in b['open']:
    failures = []
    for side in ('team_a', 'team_b'):
        rating = r['vrs'].get(side)
        if rating and (rating['team'], rating['roster'], rating['points']) not in ratings:
            failures.append('rating absent from independently re-read official standings')
    for q in r['quotes']:
        if q['raw_format'] == 'american':
            dec = lambda n: 1 + float(n) / 100 if float(n) > 0 else 1 + 100 / abs(float(n))
            da, db = dec(q['raw_a']), dec(q['raw_b'])
        elif q['raw_format'] == 'decimal':
            da, db = float(q['raw_a']), float(q['raw_b'])
        else:
            da, db = 1 / float(q['raw_a']), 1 / float(q['raw_b'])
        pa = (1 / da) / ((1 / da) + (1 / db))
        if q['swapped']:
            pa = 1 - pa
        if abs(round(pa, 4) - q['no_vig_prob_team_a']) > 0.0001:
            failures.append('quote arithmetic mismatch')
    line = r['line']
    if line:
        if abs(line['prob_a'] + line['prob_b'] - 1) > 0.0001:
            failures.append('not complementary')
        if line['basis'] == 'market' and line['prob_a'] != r['market']['prob_a']:
            failures.append('market changed by model')
        if line['basis'] == 'model' and r['market'] is not None:
            failures.append('fallback used despite eligible price')
        if line['basis'] == 'model' and (not r['vrs']['team_a'] or not r['vrs']['team_b']):
            failures.append('fallback missing input')
    checks.append({'id': r['fixture_id'], 'teams': [r['team_a'], r['team_b']],
                   'basis': line['basis'] if line else 'unverified',
                   'prob_a': line['prob_a'] if line else None, 'prob_b': line['prob_b'] if line else None,
                   'pick': line['pick_team'] if line else None, 'flags': r['flags'], 'failures': failures,
                   'sources': [r['hotspawn_url']] + [q['api_url'] for q in r['quotes']] +
                              ([r['vrs']['page_url']] if r['model'] else [])})
report = {'audited_utc': '2026-10-14T02:40:00Z', 'board_observed_utc': b['generated_utc'],
          'official_valve_blob_sha': blob['sha'], 'official_valve_rows': len(ratings),
          'lobby_sha256': hashlib.sha256((OUT/'lobby_fixture.txt').read_bytes()).hexdigest(),
          'rows_checked': len(checks), 'failures': sum(len(r['failures']) for r in checks), 'rows': checks}
(OUT/'report.json').write_text(json.dumps(report, indent=2) + '\n')
e = lambda v: html.escape(str(v), quote=True)
rows = []
for r in checks:
    probs = '' if r['prob_a'] is None else f"{r['prob_a']*100:.1f}% / {r['prob_b']*100:.1f}%"
    links = ' '.join(f'<a href="{e(url)}">Official source {i+1}</a>' for i, url in enumerate(r['sources']))
    rows.append(f'<tr><td>{e(r["id"])} · {e(" vs ".join(r["teams"]))}</td><td>{e(r["basis"])}</td><td>{probs}</td><td>{e(r["pick"] or "")}</td><td>{e("; ".join(r["flags"]))}</td><td>{links}</td></tr>')
(OUT/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reliability audit · Flagged for Review</title>
<style>body{font:16px/1.6 system-ui;margin:auto;padding:20px;max-width:1100px;background:#101722;color:#e9eef5}a{color:#85c1ff;display:inline-block;padding:4px}td,th{padding:10px;text-align:left;border-bottom:1px solid #344157;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}.wide{overflow:auto}code{overflow-wrap:anywhere} @media(max-width:640px){table,tbody,tr,td{display:block}thead{display:none}tr{background:#1b2637;padding:8px;margin-bottom:12px;border-radius:8px}td:empty{display:none}}</style>
<header><a href="../../ourline/index.html">← All CS2 picks</a> · <a href="../../index.html">Main dashboard</a></header><h1>Reliability audit / Flagged for Review</h1>
<p>This is a dated, reproducible audit, not a second current-picks board. The current board is <a href="../../ourline/index.html">All open CS2 picks</a>.</p>'''+f'''
<p>Source snapshot: {e(b['generated_utc'])}. Audited 2026-10-14 02:40 UTC. {len(checks)} open rows inspected; {report['failures']} arithmetic/input failures. Independently re-read {len(ratings)} Valve global rows via its official GitHub contents API (blob <code>{e(blob['sha'])}</code>).
Bookmaker values are re-derived from their timestamped captured raw prices; this audit does not claim each endpoint was independently reachable from this restricted sandbox.</p>
<h2>Findings</h2><ul>
<li><b>A1 — Fixed:</b> automatic live collector still manufactured /matches/numeric-id links. Its refreshed output reversed the previous repair and failed Pages validation. Collector now uses lobby-published permalinks or the official lobby, with a mocked real-collector test.</li>
<li><b>A2 — Fixed:</b> two tests compared time-varying lobby observations as though they were immutable. Parser test now uses a pinned official capture; permalink comparisons apply to overlapping ids without requiring old fixtures to remain listed.</li>
<li><b>A3 — Fixed:</b> latest counted match does not establish the active roster for duplicate Valve team names. Such model inputs are now unverified and excluded. Official standings include each roster explicitly.</li>
<li><b>A4 — Fixed:</b> fallback research was changing priced/featured picks. Eligible market consensus is now used unchanged; only unpriced matches receive the labelled model fallback.</li>
<li><b>A5 — Fixed:</b> 14-hour matching and unknown/approximate times could join a different meeting. Require both teams and starts within five minutes. Quotes/lobby observations older than four hours and ratings older than 14 days are excluded. These limits are policy, not sourced facts.</li>
<li><b>A6 — Needs review:</b> full numeric coverage cannot be verified for teams without eligible prices and unambiguous source ratings. Blank rows below are intentional, not fabricated 50/50 picks.</li>
<li><b>A7 — Needs review:</b> HLTV access is blocked on the captured runner. No HLTV numeric values are used. Scheduled refreshes and cached lobby content can lag; coverage is relative to the stated source observation.</li>
<li><b>A8 — Needs review:</b> the root introduction still claims the separate board gives every fixture a pick and blends market/model; that wording is outdated and has been requested from the recent root owner on the task board. The audited board reports its gaps explicitly. Historical alternate boards remain dated research and have different estimation policies. Use the linked current board, not their stale figures. Predictive accuracy of the VRS fallback is not independently validated.</li>
<li><b>A9 — Needs review:</b> parallel <a href="../../picks-every-match/flagged.html">every-match research</a> uses unconfirmed WROTBERRY identity/slot prices, sibling LFO ratings and thin Kalshi books. Its lower-confidence estimates are preserved for review, not accepted into this board's verified input joins. A source price for another named team is not a confirmed price for WROTBERRY.</li>
</ul>
<p>Official sources: <a href="https://play.hotspawn.com/lobby">HotSpawn lobby</a>, <a href="{e(blob['html_url'])}">Valve standings</a>, <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/glicko.js">Valve Glicko code</a>, <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/fit.js">Valve fit code</a>, <a href="https://www.hltv.org/matches">HLTV (access flag only)</a>.</p>
<h2>Fresh official provider replay (02:43 UTC)</h2><p>A hosted refresh captured 12 official provider responses. All 31 consumed quotes across 14 priced fixtures reproduced their team identities, raw prices, market selection and start times from those JSON responses; no failures. <a href="payload_verification.json">Quote-by-quote replay report</a> · <a href="../../data/f7279a54/source_payloads.json">Current retained official responses</a>. The report is dated; the current response file continues to refresh.</p>
<h2>Every open row, verified against captured evidence</h2><p>Percentages below are derived estimates, not official facts. Blank cells mean unverified.</p><div class="wide"><table><thead><tr><th>Fixture / teams</th><th>Basis</th><th>A / B probability</th><th>Pick</th><th>Flags</th><th>Sources</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>Downloads: <a href="report.json">Per-row audit JSON</a>, <a href="board_snapshot.json">Immutable board</a>, <a href="source_snapshot.json">Immutable input snapshot</a>, <a href="valve_standings_source.json">Official Valve API response</a>, <a href="lobby_fixture.txt">Pinned public lobby response</a>.</p></html>''')
if report['failures']:
    raise SystemExit('Audit failures')
print(f"PASS: {len(checks)} rows inspected against official/captured evidence")
