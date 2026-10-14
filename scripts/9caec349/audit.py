"""Dated independent arithmetic/input audit of the canonical pick board."""
import base64
import hashlib
import html
import json
import math
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'audits/9caec349'

def main():
    board = json.loads((ROOT / 'data/f7279a54/board.json').read_text())
    blob = json.loads((OUT / 'valve-official.json').read_text())
    replay = json.loads((OUT / 'provider-replay.json').read_text())
    md = base64.b64decode(blob['content']).decode()
    ratings = {(m.group(3).strip(), m.group(4).strip(), int(m.group(2))) for m in re.finditer(r'^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|', md, re.M)}
    checked = []
    for row in board['open']:
        errors = []
        ln = row.get('line')
        for rating in [row['vrs'].get('team_a'), row['vrs'].get('team_b')]:
            if rating and (rating['team'], rating['roster'], rating['points']) not in ratings:
                errors.append('rating absent from official standings')
        for q in row['quotes']:
            if q['raw_format'] == 'american':
                decimal = lambda x: 1 + float(x)/100 if float(x) > 0 else 1 + 100/abs(float(x))
                a, b = decimal(q['raw_a']), decimal(q['raw_b'])
            elif q['raw_format'] == 'decimal':
                a, b = float(q['raw_a']), float(q['raw_b'])
            else:
                a, b = 1/float(q['raw_a']), 1/float(q['raw_b'])
            p = (1/a) / (1/a + 1/b)
            if q['swapped']: p = 1-p
            if abs(p-q['no_vig_prob_team_a']) > 0.0001: errors.append('quote arithmetic')
        if ln:
            if abs(ln['prob_a']+ln['prob_b']-1) > 0.0001: errors.append('non-complementary probabilities')
            if ln['basis'] == 'market' and ln['prob_a'] != row['market']['prob_a']: errors.append('market changed by fallback')
            if ln['basis'] == 'model':
                if row['market']: errors.append('fallback overrides market')
                ra, rb = row['vrs']['team_a'], row['vrs']['team_b']
                if not ra or not rb: errors.append('missing rating')
                else:
                    Q = math.log(10)/400
                    g = 1/math.sqrt(1+3*Q**2*75**2/math.pi**2)
                    p = 1/(1+math.exp(-board['calibration']['k']*g*Q*(ra['points']-rb['points'])))
                    if abs(p-ln['prob_a']) > 0.0001: errors.append('model arithmetic')
        checked.append({'id': row['fixture_id'], 'teams': [row['team_a'], row['team_b']], 'basis': ln['basis'] if ln else 'unverified', 'line': ln, 'flags': row['flags'], 'failures': errors, 'sources': [row['hotspawn_url']] + [q['api_url'] for q in row['quotes']] + ([row['vrs']['page_url']] if row['model'] else [])})
    report = {'source_observation_utc': board['generated_utc'], 'input_commit': '3068d2873bfe31aa617ad30d79fa24b0e1563a79', 'valve_blob_sha': blob['sha'], 'valve_rows': len(ratings), 'board_sha256': hashlib.sha256((ROOT/'data/f7279a54/board.json').read_bytes()).hexdigest(), 'rows_checked': len(checked), 'provider_quotes_replayed': replay['consumed_quotes_checked'], 'failures': replay['failures'] + [e for r in checked for e in r['failures']], 'rows': checked}
    (OUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    e = lambda x: html.escape(str(x), quote=True)
    rows = []
    for r in checked:
        ln = r['line']
        probs = f"{ln['prob_a']*100:.1f}% / {ln['prob_b']*100:.1f}%" if ln else ''
        links = ' · '.join(f'<a href="{e(s)}">Official source {i+1}</a>' for i,s in enumerate(r['sources']))
        rows.append(f'<tr><td data-label="Match">{e(" vs ".join(r["teams"]))}</td><td data-label="Basis">{e(r["basis"])}</td><td data-label="Probabilities">{probs}</td><td data-label="Flags">{e("; ".join(r["flags"]))}</td><td data-label="Sources">{links}</td></tr>')
    (OUT/'index.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Integration audit · Flagged for Review</title><link rel="stylesheet" href="../../assets/style.css"></head><body><main class="wrap"><a href="../../index.html">← Canonical picks dashboard</a><h1>Integration audit / Flagged for Review</h1>
<p>This is a dated evidence review, not another current pick board. Current picks: <a href="../../ourline/index.html">all CS2 picks</a>.</p>'''+f'''<p>Source observation: {e(board['generated_utc'])}. Checked {len(checked)} open rows, replayed {replay['consumed_quotes_checked']} consumed quotes from 12 retained official provider responses, and independently re-read {len(ratings)} rows from Valve’s official GitHub standings. Arithmetic/input failures: {len(report['failures'])}. Source-input verification is not forecast validation.</p>
<p><a href="report.json">Per-row machine-readable audit</a> · <a href="provider-replay.json">Official provider replay</a> · <a href="valve-official.json">Independently retrieved Valve response</a> · <a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/{report['input_commit']}/data/f7279a54/source_payloads.json">Pinned provider payloads</a></p>'''+'''
<h2>Findings &amp; limitations</h2><ul>
<li><strong>Fixed:</strong> the landing page claimed 28/28 coverage and used hard-coded counts inconsistent with the strict source board. It now derives every row/count from that board, preserves market picks unchanged and labels model-only estimates.</li>
<li><strong>Fixed:</strong> conflicting start-here links are replaced by one canonical table and detailed board. Alternate experiments remain in the research archive.</li>
<li><strong>Fixed:</strong> the canonical landing table hides probabilities after source expiry or match lock, including when a phone returns from sleep. Counts explicitly describe the captured snapshot.</li>
<li><strong>Needs review — eight unverified rows at this observation:</strong> LFO 10 has no unique official rating; WROTBERRY identity is contested; RoundsGG’s alias/roster is not accepted by the strict pipeline; Banda chuya/6666 have duplicate rating names. Probabilities remain blank. <a href="../../summary/gaps.html">Identity evidence and counter-evidence</a> · <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md">Official standings</a>.</li>
<li><strong>Needs review — alternate numeric completeness:</strong> sibling LFO roster ratings, slot-based identity substitutions and thin exchange books on the <a href="../../picks-every-match/flagged.html">alternate board</a> are assumptions, not verified inputs for these teams. They are not adopted here.</li>
<li><strong>Needs review — freshness and access:</strong> the captured HotSpawn response had an Age header of 3818 seconds; HLTV returned HTTP 403 to the runner. No HLTV value was fabricated. Refreshes target ~30 minutes but GitHub schedules, caches and provider blocks can delay coverage. <a href="https://play.hotspawn.com/lobby">Official lobby</a> · <a href="https://www.hltv.org/matches">HLTV</a> · <a href="../../ourline/sources.html">Current source health</a>.</li>
<li><strong>Verification boundary:</strong> this restricted sandbox cannot independently access bookmaker sites or the public Pages host. Price checks replay official responses captured by the hosted runner. CI checks the deployed site. This report does not certify every historical file/claim in the repository or promise complete numeric coverage.</li>
</ul><h2>Line-by-line open-match review</h2><p>Blanks mean unverified, not an inferred probability. Values below are dated model or market estimates, never verified outcomes.</p><div class="tablewrap"><table><thead><tr><th>Match</th><th>Basis</th><th>Team A / B</th><th>Flags</th><th>Sources</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div></main></body></html>''')
    print(f"Audited {len(checked)} rows; {len(report['failures'])} failures")
    return bool(report['failures'])
if __name__ == '__main__': raise SystemExit(main())
