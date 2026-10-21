#!/usr/bin/env python3
"""Read-only canonical-board audit. Source replay + independent probability arithmetic.

No collector, alias, quote, probability or other session's output is changed.
The report is a dated audit, not an additional current picks board.
"""
from __future__ import annotations
import hashlib
import html
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/c64a5e19'
OUT = ROOT / 'data/6ffacd40'
SITE = ROOT / 'audits/6ffacd40'
WEIGHTS = {'pinnacle': 2, 'bovada': 1, 'melbet': 1, 'kalshi': 1}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return json.loads(Path(path).read_text())


def raw_decimals(q):
    a, b = float(q['raw_a']), float(q['raw_b'])
    if q['raw_format'] == 'american':
        return tuple(1 + (100 / abs(x) if x < 0 else x / 100) for x in (a, b))
    if q['raw_format'] == 'decimal':
        return a, b
    if q['raw_format'] == 'yes mid ($)':
        return 1 / a, 1 / b
    raise ValueError('Unsupported price format: ' + str(q['raw_format']))


def quote_probability(q):
    a, b = raw_decimals(q)
    p = (1 / a) / (1 / a + 1 / b)
    return 1 - p if q.get('swapped') else p


def verify_board(board):
    failures, rows = [], []

    def check(condition, text):
        if not condition:
            failures.append(text)

    # Independently re-fit the declared through-origin logit slope, not the stored k.
    q = math.log(10) / 400
    c = q / math.sqrt(1 + 3 * q * q * 75 * 75 / math.pi ** 2)
    pairs = []
    if board.get('vrs', {}).get('fresh', True) and board.get('calibration', {}).get('fitted', True):
        for r in board['open']:
            va, vb = (r.get('vrs') or {}).get('team_a'), (r.get('vrs') or {}).get('team_b')
            m = r.get('market')
            if va and vb and m:
                # Calibration uses unrounded source consensus, not rounded table output.
                quotes = r['quotes']
                p = sum(WEIGHTS.get(t['source_key'], 1) * quote_probability(t) for t in quotes) / sum(WEIGHTS.get(t['source_key'], 1) for t in quotes)
                pairs.append((c * (va['points'] - vb['points']), math.log(p / (1 - p))))
    sxx = sum(x * x for x, _ in pairs)
    k = (
        min(1.5, max(.25, sum(x * y for x, y in pairs) / sxx))
        if board['calibration'].get('fitted', True) and len(pairs) >= 6 and sxx
        else 1.
    )
    check(abs(k - board['calibration']['k']) < 1e-9, 'Calibration slope differs from independent fit')
    for r in board['open']:
        fid, line = r['fixture_id'], r.get('line')
        before = len(failures)
        quotes = r.get('quotes') or []
        for t in quotes:
            da, db = raw_decimals(t)
            check(abs(da - t['decimal_a']) < 1e-3 and abs(db - t['decimal_b']) < 1e-3, fid + ': decimal conversion')
            check(abs(quote_probability(t) - t['no_vig_prob_team_a']) <= .000051, fid + ': no-vig arithmetic')
            check(t['api_url'].startswith('https://'), fid + ': missing quote source')
        check(r['hotspawn_url'].startswith('https://'), fid + ': missing official fixture source')
        if not line:
            check(bool(r['flags']) and bool(r.get('research')), fid + ': undocumented blank')
        else:
            if line['basis'] == 'market':
                check(bool(quotes), fid + ': market line without quotes')
                if quotes:
                    p = sum(WEIGHTS.get(t['source_key'], 1) * quote_probability(t) for t in quotes) / sum(WEIGHTS.get(t['source_key'], 1) for t in quotes)
                    check(abs(line['prob_a'] - p) <= .000051, fid + ': consensus probability')
            elif line['basis'] == 'model':
                va, vb = r['vrs']['team_a'], r['vrs']['team_b']
                p = 1 / (1 + math.exp(-k * c * (va['points'] - vb['points'])))
                check(abs(line['prob_a'] - p) <= .000051, fid + ': model probability')
                check(not quotes, fid + ': model changed a featured market')
            else:
                check(False, fid + ': unsupported basis')
            pa, pb = line['prob_a'], line['prob_b']
            check(0 < pa < 1 and 0 < pb < 1 and abs(pa + pb - 1) < 1e-9, fid + ': normalization')
            expected = r['team_a'] if pa > pb else r['team_b'] if pb > pa else None
            check(line['pick_team'] == expected, fid + ': recommendation not argmax / tie is forced')
        rows.append({'fixture_id': fid, 'match': r['team_a'] + ' vs ' + r['team_b'],
                     'basis': line['basis'] if line else None,
                     'state': 'directional pick' if line and line['pick_team'] else 'priced tie / no edge' if line else 'unverified / blank',
                     'quotes_checked': len(quotes), 'failures': failures[before:],
                     'sources': [r['hotspawn_url']] + [t['api_url'] for t in quotes] + ([board['vrs']['page_url']] if line and line['basis'] == 'model' else [])})
    counts = {name: sum(r['state'] == name for r in rows) for name in ('directional pick', 'priced tie / no edge', 'unverified / blank')}
    check(sum(counts.values()) == len(board['open']), 'Coverage partition omits rows')
    check(len({r['fixture_id'] for r in rows}) == len(rows), 'Duplicate open fixture ids')
    return {'failures': failures, 'rows': rows, 'counts': counts, 'refitted_k': k}


def audit():
    board = read(DATA / 'board.json')
    report = verify_board(board)
    sys.path.insert(0, str(ROOT / 'scripts/c64a5e19'))
    try:
        b = module('audit_6ff_canonical', 'scripts/c64a5e19/build.py')
        verifier = module('audit_6ff_inputs', 'scripts/c64a5e19/verify_inputs.py')
        inputs = verifier.verify(read(DATA / 'snapshot.json'), read(DATA / 'official_inputs.json'), b.core)
        payloads = module('audit_6ff_payloads', 'scripts/ae75c5c3/verify_source_payloads.py')
        replay = payloads.verify(DATA, quote_normalizer=b.RULES.enrich_quotes)
    finally:
        sys.path.remove(str(ROOT / 'scripts/c64a5e19'))
    report.update(canonical_evaluated_utc=board['generated_utc'], source_observed_utc=board['collected_to_utc'],
                  inventory_replay=inputs, provider_replay=replay,
                  input_sha256={name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in ('board.json', 'snapshot.json', 'official_inputs.json', 'source_payloads.json')})
    report['failures'] += inputs['failures'] + replay['failures']
    return report


def esc(v):
    return html.escape(str(v), quote=True)


def links(urls):
    return ' · '.join(f'<a href="{esc(u)}">Source {i + 1}</a>' for i, u in enumerate(dict.fromkeys(urls)))


def table(headers, rows):
    return '<div class="tablewrap"><table><thead><tr>' + ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td data-label="{esc(h)}">{v}</td>' for h, v in zip(headers, row)) + '</tr>' for row in rows) + '</tbody></table></div>'


def render(report, research):
    count = report['counts']
    evidence_table = table(['Match', 'Coverage at capture', 'Verification', 'Sources'], [[esc(r['match']), esc(r['state']), esc(f"{r['quotes_checked']} quotes; " + ('PASS' if not r['failures'] else '; '.join(r['failures']))), links(r['sources'])] for r in report['rows']])
    results_table = table(['Day', 'Match', 'Result', 'Finding / interpretation', 'Official publisher'], [[esc(r['day']), esc(r['match']), esc(r['result']), esc(r['finding']), links([r['url']])] for r in research['official_results']])
    roster_table = table(['Verified announcement', 'Original text', 'Team source'], [[esc(r['claim']), esc(r['excerpt']), links([r['url']])] for r in research['roster']])
    gap_table = table(['Uncovered match at review', 'Probability / pick', 'Research and remaining limitation', 'Sources'], [[esc(r['match']), '— · unverified', esc(r['finding']), links([r['url']] + ([r['context_url']] if r.get('context_url') else []) + ['https://play.hotspawn.com/lobby'])] for r in research['gap_reviews']])
    flags = table(['Flag', 'Status', 'Limitation', 'Source'], [[esc(r['id']), esc(r['status']), esc(r['finding']), links([r['url']])] for r in research['source_limitations']])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>16 October coverage &amp; source audit · CS2 picks</title><link rel="stylesheet" href="../../assets/style.css"></head>
<body><a class="skip-link" href="#main-content">Skip to content</a><header class="topbar"><div class="wrap"><div class="brand">CS2 · Coverage verification</div><nav><a href="../../index.html">Home</a><a href="../../picks-every-match/index.html">All CS2 picks</a><a href="../../picks-every-match/unresolved.html">Unresolved</a><a href="../../twc-2026/index.html">TWC day 3</a><a href="#limitations">Flagged for Review</a></nav></div></header>
<main class="wrap" id="main-content" tabindex="-1"><h1>Every match accounted for. No forced guesses.</h1>
<p>Research reviewed {esc(research['reviewed_date_utc'])}. This is a dated audit, <strong>not another live pick list</strong>.
<a class="btn btn-primary" href="../../picks-every-match/index.html">Open current CS2 picks →</a></p>
<p>Canonical source capture: <strong>{esc(report['source_observed_utc'])}</strong>; evaluated {esc(report['canonical_evaluated_utc'])}.
{len(report['rows'])} open rows: <strong>{count['directional pick']} directional picks</strong>, {count['priced tie / no edge']} priced ties and {count['unverified / blank']} unsupported blanks.
A tie has an evidenced probability but no preferred side; a blank has neither. Do not count either as a directional recommendation.</p>
<p><strong>Arithmetic / retained-source replay: {'PASS' if not report['failures'] else 'FAIL'}</strong> · {report['inventory_replay']['fixture_rows_checked']} official lobby rows, {report['inventory_replay']['rating_rows_checked']} Valve rating rows and {report['provider_replay']['consumed_quotes_checked']} consumed quotes replayed. This confirms agreement with retained responses, not renewed source availability, prediction accuracy or every legacy repo claim.</p>
<h2>Day 1 → Day 2 → Day 3</h2><p>9z's opening sweep is genuine upset evidence. Aurora's elimination-match rebound is counter-evidence. 9z then taking a map from Falcons keeps the upset plausible, not automatically profitable. BetBoom's reverse sweep creates an alternative swing candidate. All are qualitative context, not invented percentage adjustments.</p>
{results_table}
<p><a href="../../twc-2026/index.html">Open the updated day-three decision sheet</a>: favor the externally priced higher-probability side for expected points. Its declared optional swing needs an underdog at least 35%, ownership at most 20%, leverage at least 2× and two books. At most one deliberate swing. This is a heuristic, not a calibrated probability of finishing first. Contest crowd ownership never prices a match.</p>
<h2>Aurora: verify the change, do not invent the penalty</h2>{roster_table}
<p>The primary posts establish July signings, not a verified October emergency change. Rest hours, travel fatigue and a quantitative onboarding penalty remain <strong>— · unverified</strong>. Do not treat the original premise as a causal finding.</p>
<h2 id="unresolved">Unresolved picks &amp; limitations</h2>
<p>Fallback research was restricted to uncovered matches: HLTV match pages first, public esportsbook pages next, retained bookmaker/exchange APIs and uniquely identified Valve inputs. All five HLTV betting areas rendered social-casino promotions rather than usable two-sided prices in this read. HLTV votes are not betting odds. The original provider API snapshot records attempts and rejections for each row; a 200 response is not match coverage.</p>
{gap_table}<p>New captures automatically retry these matches. <a href="../../picks-every-match/unresolved.html">Current unresolved list and per-match source attempts</a>. The following research leads do not overwrite the canonical engine.</p>
<h2 id="limitations">Flagged for Review</h2>{flags}
<h2>Line-by-line coverage check</h2>
<p>Market conversion and no-vig consensus are re-derived independently from raw prices, with declared Pinnacle weight 2 and other sources 1. The Valve logistic slope is independently fitted on the same priced/rated pairs and used only for model fallbacks. A provider replay re-parses retained official JSON to check price and event provenance. Input hashes bind this dated report to its exact capture; later refreshes are not silently claimed as reviewed.</p>
{evidence_table}
<p><a href="../../data/6ffacd40/report.json">Machine-readable checks and input hashes</a> · <a href="../../data/6ffacd40/research.json">Manual research ledger</a> · <a href="../../picks-every-match/method.html">Current pricing and freshness policy</a> · <a href="../../flagged.html">Site-wide Flagged for Review</a>.</p>
<p class="note">HotSpawn is the primary authority for its lobby and its own reports, not an independent bookmaker probability source. HLTV is specialist reporting, not the tournament organizer. Secondary aggregator prices are not promoted to officially verified quotes. Estimates are not guarantees. 18+; gamble responsibly.</p></main></body></html>'''


def main():
    report = audit()
    OUT.mkdir(parents=True, exist_ok=True)
    SITE.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    (SITE / 'index.html').write_text(render(report, read(OUT / 'research.json')))
    print(f"Audit: {len(report['rows'])} open rows, {report['provider_replay']['consumed_quotes_checked']} quotes, {len(report['failures'])} failures")
    for failure in report['failures']:
        print(failure)
    return bool(report['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
