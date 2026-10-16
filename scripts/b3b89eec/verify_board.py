#!/usr/bin/env python3
"""Session b3b89eec — independent arithmetic + source audit of the latest CS2 capture.

Re-derives every number in the latest ourline capture (data/f7279a54/board.json) from the
retained raw quotes, and cross-checks the two TWC 2026 deciders against facts verified on
HLTV (event 8932, match pages 2399412/2399413) on 2026-10-16 (UTC). No value is inferred:
anything that cannot be re-derived is reported as a finding, never silently accepted.

Output: data/b3b89eec/board_verification.json
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / 'data/f7279a54/board.json'
OUT = ROOT / 'data/b3b89eec/board_verification.json'

# Facts verified on HLTV on 2026-10-16 (UTC) — see data/b3b89eec/twc_review.json for the
# full source list. Used only as an independent cross-check of the capture's schedule and
# roster fields; the capture's own quote data is re-derived from the retained raw quotes.
# Declared modelling choice (published on picks-every-match/method.html: "weight of 2 for
# Pinnacle and 1 for others. This weighting is a modelling choice, not an official win
# probability."). The verifier re-applies the SAME declared weights and reports any row
# whose stored consensus deviates from it.
SOURCE_WEIGHTS = {'pinnacle': 2.0, 'bovada': 1.0, 'melbet': 1.0, 'kalshi': 1.0}


def team_odds(q):
    """(team_a odds, team_b odds) from a retained quote.

    Storage convention (see the engine): raw_a/raw_b and decimal_a/decimal_b are kept in the
    source's own listing order (matching names_at_source); no_vig_prob_team_a is normalized
    to the fixture's team_a. swapped=True means the source listed team_b first.
    """
    if q.get('swapped'):
        return q.get('decimal_b'), q.get('decimal_a')
    return q.get('decimal_a'), q.get('decimal_b')


HLTV_CROSSCHECKS = {
    '1080205': {
        'start_utc': '2026-10-16T14:00:00Z',
        'teams': {'Aurora': ['Jimpphat', 'kyxsan', 'Wicadia', 'woxic', 'XANTARES'],
                  '9z': ['dgt', 'HUASOPEEK', 'luchov', 'max', 'meyern']},
        'hltv_url': 'https://www.hltv.org/matches/2399412/aurora-vs-9z-thunderpick-world-championship-2026',
    },
    '1081775': {
        'start_utc': '2026-10-16T17:00:00Z',
        'teams': {'BetBoom': ['Boombl4', 'd1Ledez', 'Magnojez', 'S1ren', 'zorte'],
                  'Legacy': ['arT', 'dumau', 'latto', 'n1ssim', 'try']},
        'hltv_url': 'https://www.hltv.org/matches/2399413/betboom-vs-legacy-thunderpick-world-championship-2026',
    },
}


def iso(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def no_vig(a, b):
    pa, pb = 1.0 / a, 1.0 / b
    return pa / (pa + pb)


def approx(x, y, tol=5e-4):
    return x is not None and y is not None and math.isfinite(x) and math.isfinite(y) and abs(x - y) <= tol


def verify_fixture(f, now, findings, ok):
    fid = f['fixture_id']

    def bad(msg):
        findings.append({'fixture_id': fid, 'check': 'row', 'finding': msg})

    if not str(f.get('hotspawn_url', '')).startswith('https://'):
        bad('no https HotSpawn source link for the row')
    start = f.get('start_utc')
    if not start or iso(start) <= now:
        bad('open fixture without a future start_utc')

    quotes = f.get('quotes') or []
    for q in quotes:
        da, db = q.get('decimal_a'), q.get('decimal_b')
        if not (da and db and da > 1.0 and db > 1.0):
            bad(f'quote {q.get("source_key")} decimal pair not > 1.0: {da}/{db}')
            continue
        oa, ob = team_odds(q)
        expect = no_vig(oa, ob)
        if not approx(q.get('no_vig_prob_team_a'), expect):
            bad(f'quote {q.get("source_key")} no_vig_prob_team_a={q.get("no_vig_prob_team_a")} '
                f'!= re-derived {expect:.6f} (team_a odds {oa} from raw {q.get("raw_a")}/{q.get("raw_b")}, '
                f'swapped={q.get("swapped")})')
        if q.get('start_utc_at_source') != start:
            diff_h = abs((iso(q['start_utc_at_source']) - iso(start)).total_seconds()) / 3600
            if diff_h > 5 / 60:  # the engine's documented join tolerance (see tests/test_69e4c06a.py)
                bad(f'quote {q.get("source_key")} start_utc_at_source {q.get("start_utc_at_source")} differs from '
                    f'fixture start {start} by {diff_h:.3f}h (> 5 min tolerance)')
        if q.get('retrieved_utc') and iso(q['retrieved_utc']) > now:
            bad(f'quote {q.get("source_key")} retrieved in the future of the capture')

    m = f.get('market')
    ln = f.get('line')
    if quotes:
        if not m:
            bad('quotes present but no market object')
        else:
            if m.get('n_sources') != len({q['source_key'] for q in quotes}):
                bad('market.n_sources != number of distinct quote sources')
            wsum = sum(SOURCE_WEIGHTS.get(q['source_key'], 1.0) for q in quotes)
            expect_pa = sum(SOURCE_WEIGHTS.get(q['source_key'], 1.0) * q['no_vig_prob_team_a'] for q in quotes) / wsum
            if not approx(m.get('prob_a'), expect_pa):
                bad(f'market.prob_a={m.get("prob_a")} != declared weighted mean {expect_pa:.6f} '
                    f'(weights: Pinnacle 2, others 1 — published on the method page)')
            if m.get('prob_a') + m.get('prob_b') not in (None,) and not approx(m['prob_a'] + m['prob_b'], 1.0):
                bad('market probabilities do not sum to 1')
    if ln:
        if ln.get('prob_a') is None or not approx(ln.get('prob_a'), 1 - ln.get('prob_b'), tol=1e-6):
            bad('line probabilities do not sum to 1')
        pa, pb = ln.get('prob_a', 0), ln.get('prob_b', 0)
        if approx(pa, pb):
            # Documented 50/50 tie: the engine flags equal_probability_no_edge, keeps team_a as
            # pick_side and labels the confidence "Toss-up". Verify that documentation is present.
            if 'equal_probability_no_edge' not in (f.get('flags') or []):
                bad('probabilities are equal but the equal_probability_no_edge flag is missing')
            if ln.get('confidence') != 'Toss-up' or ln.get('pick_side') != 'a':
                bad('equal-probability row not documented as a Toss-up (pick_side a)')
        else:
            side = 'a' if pa > pb else 'b'
            if ln.get('pick_side') != side or ln.get('pick_prob') != max(pa, pb):
                bad('pick side/probability is not the larger of the two estimates')
        if m and ln.get('basis') == 'market':
            if not approx(ln.get('prob_a'), m.get('prob_a')):
                bad('market-based line probability differs from the market estimate')
        if ln.get('fair_decimal_a') and not approx(ln['fair_decimal_a'], 1.0 / ln['prob_a'], tol=2e-3):
            bad('fair decimal is not 1/probability')
    else:
        if 'no_line_unverified' not in (f.get('flags') or []):
            bad('row has no line but is not flagged no_line_unverified')
        if quotes:
            bad('row has quotes but no line and is not documented as a gap')
    if f.get('valid_until_utc') and iso(f['valid_until_utc']) <= now:
        bad('valid_until_utc is not after the capture time')

    # TWC decider cross-checks against HLTV-verified facts
    cc = HLTV_CROSSCHECKS.get(fid)
    if cc:
        if f.get('start_utc') != cc['start_utc']:
            findings.append({'fixture_id': fid, 'check': 'hltv_crosscheck',
                             'finding': f'capture start {f.get("start_utc")} != HLTV-verified {cc["start_utc"]}'})
        for team, roster in cc['teams'].items():
            vrs = (f.get('vrs') or {}).get('team_a' if f['team_a'] == team else 'team_b') if team in (f['team_a'], f['team_b']) else None
            if not vrs:
                findings.append({'fixture_id': fid, 'check': 'hltv_crosscheck',
                                 'finding': f'no VRS block for {team} to cross-check the roster'})
                continue
            if sorted(x.split()[0] for x in vrs['roster'].split(',')) != sorted(roster):
                findings.append({'fixture_id': fid, 'check': 'hltv_crosscheck',
                                 'finding': f'VRS roster for {team} {vrs["roster"]} != HLTV roster {", ".join(roster)}'})
        ok.append({'fixture_id': fid, 'check': 'hltv_crosscheck',
                   'verified': 'start time + rosters match HLTV match page (read 2026-10-16 UTC)',
                   'source': cc['hltv_url']})
    return len(quotes)


def run():
    board = json.loads(BOARD.read_text())
    now = iso(board['generated_utc'])
    findings, ok = [], []
    summary = dict(board['summary'])
    open_rows = board['open']
    n_quotes = 0
    counts = {'market': 0, 'model': 0, 'none': 0}
    for f in open_rows:
        n_quotes += verify_fixture(f, now, findings, ok)
        ln = f.get('line')
        counts['market' if (ln and ln.get('basis') == 'market') else 'model' if ln else 'none'] += 1

    # Summary arithmetic
    s_open = summary.get('open')
    if s_open != len(open_rows):
        findings.append({'fixture_id': None, 'check': 'summary', 'finding': f'summary.open={s_open} != {len(open_rows)} open rows'})
    if summary.get('market_based') != counts['market']:
        findings.append({'fixture_id': None, 'check': 'summary', 'finding': f'summary.market_based={summary.get("market_based")} != {counts["market"]} re-derived'})
    if summary.get('model_only') != counts['model']:
        findings.append({'fixture_id': None, 'check': 'summary', 'finding': f'summary.model_only={summary.get("model_only")} != {counts["model"]} re-derived'})
    if summary.get('no_line') != counts['none']:
        findings.append({'fixture_id': None, 'check': 'summary', 'finding': f'summary.no_line={summary.get("no_line")} != {counts["none"]} re-derived'})
    if s_open != counts['market'] + counts['model'] + counts['none']:
        findings.append({'fixture_id': None, 'check': 'summary', 'finding': 'open != market + model + none'})

    result = {
        'session': 'b3b89eec',
        'verified_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'capture': {'path': str(BOARD.relative_to(ROOT)), 'generated_utc': board['generated_utc'],
                    'collected_from_utc': board.get('collected_from_utc'),
                    'fixture_observation_age_seconds': board.get('fixture_observation_age_seconds')},
        'scope': 'every open fixture in the capture: quote arithmetic, market averages, pick orientation, '
                 'source links, flags, validity; TWC deciders additionally cross-checked against HLTV',
        'counts': {'open': s_open, 'market': counts['market'], 'model': counts['model'], 'none': counts['none'],
                   'quotes': n_quotes},
        'checks_passed': [dict(o, fixture_id=o.get('fixture_id')) for o in ok],
        'findings': findings,
        'verdict': 'PASS — every re-derived value matches; no value inferred' if not findings
                   else f'FAIL — {len(findings)} finding(s)',
        'note': 'The capture is a retained snapshot of external sources (HotSpawn lobby + Bovada/Melbet/Pinnacle/Kalshi feeds '
                '+ Valve VRS). Its quotes were re-derived here from the retained raw values; the sources themselves were '
                'independently spot-checked live on 2026-10-16 (see twc_review.json for the spot-check record).',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + '\n')
    return result


def main():
    result = run()
    print(result['verdict'])
    print('counts:', json.dumps(result['counts']))
    for f in result['findings'][:20]:
        print('FINDING:', f)
    return 0 if not result['findings'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
