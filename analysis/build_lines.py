"""Build originated lines for Hotspawn Pick'em fixtures from external odds observations.

Session 6196c585 (T-A). Inputs:
  - analysis/odds_observations.json  (external odds observations, each with source URL)
  - docs/data/matches.json           (fixture inventory captured from play.hotspawn.com/lobby)

Method (fully disclosed, reproducible):
  1. Eligible observation = join_status "identity-unverified" (identity corroborated by teams +
     tournament + date/format), two-sided numeric decimal prices (or explicit American odds, or
     explicit Polymarket probability-form), and NOT conflict-flagged. Editorial price *ranges*
     are never point-estimated and are excluded from consensus (kept as supplementary evidence).
  2. Per source: q_i = 1 / decimal_i; de-vig by proportional normalization p_i = q_i / (qA + qB).
     (Identical arithmetic to scripts/model.py fair_line; American odds converted with
     scripts/model.py american_to_decimal.)
  3. Fixture consensus = equal-weight mean of per-source de-vigged probabilities.
     Our originated fair line = 1 / p_consensus.
  4. Hotspawn crowd percentages are NEVER an input (requirements). They are stored separately in
     analysis/hotspawn_picked_pct.json for divergence display only.
  5. Fail-closed: unresolved team names, one-sided lines, stale fixtures => probability null + flag.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from model import american_to_decimal  # noqa: E402

ALIAS = {
    'wrotberry': 'WROTBERRY', 'wbt': 'WROTBERRY',
    'esport academy copenhagen': 'EAC', 'eac': 'EAC',
    'roundsgg': 'RoundsGG', 'rgg': 'RoundsGG', 'rounds': 'RoundsGG',
    'phantom esports': 'Phantom', 'phantom': 'Phantom', 'pha': 'Phantom',
    'voca': 'Voca', 'voc': 'Voca',
    'havu': 'HAVU',
    'overtake': 'Overtake Sector', 'overtake sector': 'Overtake Sector', 'ot2': 'Overtake Sector',
    '9z team': '9z', '9z': '9z',
    'aurora gaming': 'Aurora', 'aurora': 'Aurora',
    'sashi esport': 'Sashi', 'sashi': 'Sashi',
    'fnatic': 'Fnatic', 'fnc': 'Fnatic',
    'nip': 'Ninjas in Pyjamas', 'ninjas in pyjamas': 'Ninjas in Pyjamas',
    'team falcons': 'Falcons', 'falcons': 'Falcons', 'fal2': 'Falcons',
    'betboom team': 'BetBoom', 'betboom': 'BetBoom',
    'bc.game esports': 'BC.Game', 'bc.game': 'BC.Game', 'bc.g': 'BC.Game', 'bcg': 'BC.Game',
    'team envy': 'Envy', 'envy': 'Envy',
    'mibr': 'MIBR', 'heroic': 'Heroic',
    'ex-keyd stars': 'ex-Keyd Stars', 'keydst': 'ex-Keyd Stars',
    'galorys': 'Galorys', 'gls1': 'Galorys',
    'zomblers': 'Zomblers',
    'gothic': 'Gothic', 'lavked': 'Lavked',
    'ex-rustec': 'ex-RUSTEC', 'mellren': 'mellren',
    'g2 ares': 'G2 Ares', 'the last resort': 'The Last Resort', 'tlr': 'The Last Resort',
    'legacy': 'Legacy', 'parivision': 'PARIVISION', 'prv': 'PARIVISION',
    'furia': 'FURIA',
    'astralis': 'Astralis',
    'hotu': 'HOTU',
    'ence': 'ENCE', 'bojong': 'BOJONG',
    'forze reload': 'FORZE Reload', 'lfo 10': 'LFO 10',
    'black phoenix': 'Black Phoenix', '6666': '6666',
}


def norm_team(raw):
    """Normalize a book-side label to the Hotspawn fixture team name, or None."""
    if not isinstance(raw, str):
        return None
    s = raw.lower().strip()
    if '(' in s:  # strip parentheticals like "WROTBERRY (WBT)"
        s = s.split('(')[0].strip()
    return ALIAS.get(s)


def prices_from_obs(o):
    """Return (decimal_a, decimal_b) as floats or (None, None); probability-form -> decimals."""
    da, db = o.get('decimal_a'), o.get('decimal_b')
    if isinstance(da, (int, float)) and isinstance(db, (int, float)):
        return float(da), float(db)
    aa, ab = o.get('american_a'), o.get('american_b')
    if isinstance(aa, (int, float)) and isinstance(ab, (int, float)):
        return american_to_decimal(aa), american_to_decimal(ab)
    pa, pb = o.get('probability_a_pct'), o.get('probability_b_pct')
    if isinstance(pa, (int, float)) and isinstance(pb, (int, float)) and 0 < pa < 100 and 0 < pb < 100:
        return 100.0 / pa, 100.0 / pb  # explicit implied-probability form (e.g. Polymarket %)
    return None, None


def devig(da, db):
    qa, qb = 1.0 / da, 1.0 / db
    total = qa + qb
    return qa / total, qb / total, total - 1.0


def main():
    observations = json.loads((ROOT / 'analysis/odds_observations.json').read_text())['observations']
    inv = json.loads((ROOT / 'docs/data/matches.json').read_text())
    fixtures = {m['id']: m for m in inv['matches']}

    per_fixture = {}
    excluded = []
    excluded_by_fixture = {}

    def excl(obs_id, reason, fx=None):
        excluded.append({'obs_id': obs_id, 'fixture_id': fx, 'reason': reason})
        if fx:
            excluded_by_fixture.setdefault(fx, []).append({'obs_id': obs_id, 'reason': reason})

    for o in observations:
        fx = o.get('fixture_id')
        if not fx:
            continue  # context/outright observations handled separately
        if fx not in fixtures:
            excl(o['obs_id'], 'unknown fixture id', fx)
            continue
        if o.get('join_status') == 'conflict-flagged':
            excl(o['obs_id'], 'conflict-flagged: ' + o.get('join_notes', ''), fx)
            continue
        da, db = prices_from_obs(o)
        if da is None or db is None or da <= 1.0 or db <= 1.0:
            excl(o['obs_id'], 'no two-sided numeric point prices (one-sided / context-only observation)', fx)
            continue
        m = fixtures[fx]
        ta = norm_team(o.get('team_a_book'))
        tb = norm_team(o.get('team_b_book'))
        if ta is None or tb is None:
            excl(o['obs_id'], f'unresolved team labels: {o.get("team_a_book")!r}/{o.get("team_b_book")!r}', fx)
            continue
        # map observation sides onto fixture sides by team identity
        if ta == m['team_a'] and tb == m['team_b']:
            d_fix_a, d_fix_b = da, db
        elif ta == m['team_b'] and tb == m['team_a']:
            d_fix_a, d_fix_b = db, da
        else:
            excl(o['obs_id'], f'team identity mismatch vs fixture ({m["team_a"]}/{m["team_b"]})', fx)
            continue
        pa, pb, over = devig(d_fix_a, d_fix_b)
        per_fixture.setdefault(fx, []).append({
            'obs_id': o['obs_id'], 'source': o['source'], 'book': o.get('book'),
            'source_type': o.get('source_type'),
            'decimal_a': round(d_fix_a, 4), 'decimal_b': round(d_fix_b, 4),
            'p_a': pa, 'p_b': pb, 'overround': over,
            'observed_at': o.get('observed_at'), 'join_notes': o.get('join_notes'),
        })

    lines = []
    for fx_id, m in fixtures.items():
        srcs = per_fixture.get(fx_id, [])
        stale = (m.get('start_utc') or '') < '2026-10-01'
        rec = {
            'fixture_id': fx_id, 'team_a': m['team_a'], 'team_b': m['team_b'],
            'tournament': m['tournament'], 'start_utc': m['start_utc'],
            'visible_card': m['visible_card'], 'hotspawn_source': m['source'],
            'sources': srcs,
            'excluded_observations': excluded_by_fixture.get(fx_id, []),
        }
        if stale:
            rec.update(probability_a=None, probability_b=None, fair_decimal_a=None, fair_decimal_b=None,
                       confidence='stale-fixture', status='unverified',
                       flags=['Historical embedded record (pre-October start, source status still "scheduled"); no current external market exists or is admissible'])
        elif srcs:
            pa = sum(s['p_a'] for s in srcs) / len(srcs)
            pb = sum(s['p_b'] for s in srcs) / len(srcs)
            rec.update(probability_a=pa, probability_b=pb,
                       fair_decimal_a=1.0 / pa, fair_decimal_b=1.0 / pb,
                       overround_min=min(s['overround'] for s in srcs),
                       overround_max=max(s['overround'] for s in srcs),
                       confidence='multi-source' if len(srcs) >= 2 else 'single-source',
                       status='line originated from external odds',
                       flags=([] if len(srcs) >= 2 else ['Single external source only']))
        else:
            rec.update(probability_a=None, probability_b=None, fair_decimal_a=None, fair_decimal_b=None,
                       confidence='no-two-sided-line', status='unverified',
                       flags=['No admissible two-sided external line found; left blank per verification policy'])
        lines.append(rec)

    lines.sort(key=lambda r: (r['start_utc'] or '', r['fixture_id']))
    out = {
        'built_at_utc': inv['observed_at'],
        'method': 'proportional de-vig per source (q=1/decimal, p=q/sum q), equal-weight consensus across eligible sources; fair decimal = 1/p. Hotspawn crowd % never used.',
        'fixtures_total': len(lines),
        'priced': sum(1 for r in lines if r['probability_a'] is not None),
        'excluded_observations': excluded,
        'lines': lines,
    }
    (ROOT / 'analysis/lines.json').write_text(json.dumps(out, indent=2, ensure_ascii=False))

    import csv
    with (ROOT / 'analysis/lines.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['fixture_id', 'team_a', 'team_b', 'tournament', 'start_utc', 'visible_card',
                    'probability_a', 'probability_b', 'fair_decimal_a', 'fair_decimal_b',
                    'confidence', 'n_sources', 'source_obs_ids', 'source_urls', 'flags'])
        for r in lines:
            w.writerow([r['fixture_id'], r['team_a'], r['team_b'], r['tournament'], r['start_utc'],
                        r['visible_card'],
                        '' if r['probability_a'] is None else round(r['probability_a'], 4),
                        '' if r['probability_b'] is None else round(r['probability_b'], 4),
                        '' if r['fair_decimal_a'] is None else round(r['fair_decimal_a'], 4),
                        '' if r['fair_decimal_b'] is None else round(r['fair_decimal_b'], 4),
                        r['confidence'], len(r['sources']),
                        ';'.join(s['obs_id'] for s in r['sources']),
                        ';'.join(s['source'] for s in r['sources']),
                        ' | '.join(r['flags'])])
    print(f"fixtures: {len(lines)}, priced: {out['priced']}, excluded obs: {len(excluded)}")
    for fx_id, m in fixtures.items():
        srcs = per_fixture.get(fx_id, [])
        if srcs and (m.get('start_utc') or '') >= '2026-10-01':
            pa = sum(s['p_a'] for s in srcs) / len(srcs)
            print(f"  {fx_id} {m['team_a']} {pa*100:5.1f}% / {m['team_b']} {(1-pa)*100:5.1f}%  [{len(srcs)} src: {', '.join(s['obs_id'] for s in srcs)}]")
        elif (m.get('start_utc') or '') >= '2026-10-01':
            print(f"  {fx_id} {m['team_a']} vs {m['team_b']}: NO LINE")


if __name__ == '__main__':
    main()
