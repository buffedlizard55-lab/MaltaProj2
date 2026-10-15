"""Explain the fallback ladder from the SAME captured inputs as the pick.

A successful endpoint response is not evidence of odds for a particular fixture.
This module never supplies a price, team alias, rating or probability to the engine.
"""
HLTV = 'https://www.hltv.org/matches'
VALVE = 'https://github.com/ValveSoftware/counter-strike_regional_standings'
PROVIDERS = (
    ('pinnacle', 'Pinnacle', 'https://www.pinnacle.com/en/esports/cs2-hub'),
    ('bovada', 'Bovada', 'https://www.bovada.lv/sports/esports/counter-strike-2'),
    ('melbet', 'Melbet esportsbook', 'https://melbet.com/en/line/esports'),
    ('kalshi', 'Kalshi exchange', 'https://kalshi.com/markets/kxcs2game'),
)


def access_result(meta):
    if not meta or not meta.get('at_utc'):
        return 'Not recorded in this capture; access unverified.'
    if meta.get('error') or meta.get('crash') or meta.get('status') != 200 or meta.get('looks_like_challenge'):
        return 'Unavailable or blocked in this capture; this does not prove the source has no odds.'
    return 'Endpoint responded; this alone does not verify fixture coverage.'


def limitations(row):
    reasons = []
    for flag in row.get('flags', []):
        key, _, value = flag.partition(':')
        if key == 'not_in_vrs':
            reasons.append(f'{value}: no uniquely identified rating under this name. A different roster’s rating is not a substitute.')
        elif key == 'ambiguous_vrs_name':
            reasons.append(f'{value}: multiple official rating rows; the fixture’s current roster is not confirmed.')
        elif key == 'fixture_observation_stale_or_unverified':
            reasons.append('The lobby evidence has expired or its observation time is unverified. Wait for a fresh capture.')
        elif key == 'vrs_snapshot_stale_or_unverified':
            reasons.append('The official ratings are missing, undated or outside the 14-day eligibility window.')
        elif key == 'start_time_mismatch_not_joined':
            reasons.append(f'{value}: a candidate price has a missing, approximate or mismatched kickoff; it is not joined.')
        elif key == 'stale_or_unverified_quote':
            reasons.append(f'{value}: price or fixture freshness could not be established.')
    if not row.get('market'):
        reasons.insert(0, 'No eligible two-sided external market price joined to both teams and the published kickoff.')
    if row.get('line') and row['line'].get('basis') == 'model':
        reasons.append('Both unique Valve ratings are available: a labelled model estimate is shown, not verified bookmaker odds. No out-of-sample accuracy is claimed.')
    if not row.get('line'):
        reasons.append('Pick and win probabilities remain blank. New source captures automatically retry this fixture.')
    return reasons


def fallback_review(row, snapshot, core):
    if row.get('market'):
        return None  # never supplement or alter a featured/accepted market pick
    log = snapshot.get('access_log', {})
    meta = log.get('hltv_probe', {})
    steps = [{'label': '1 · HLTV research', 'url': meta.get('url') or HLTV,
              'at_utc': meta.get('at_utc'), 'http_status': meta.get('status'),
              'result': access_result(meta) + ' Automated access probe only; no HLTV odds or roster join was verified by this capture.'}]
    for key, name, url in PROVIDERS:
        meta = log.get(key, {})
        # Exact same participant canonicalization as the pricing engine; still not
        # an accepted join. Do not attribute unrelated markets to this fixture.
        pair = sorted(core.canon(row[k])[0] for k in ('team_a', 'team_b'))
        candidates = [q for q in snapshot.get('quotes', [])
                      if q.get('source_key') == key and
                      sorted(core.canon(q[k])[0] for k in ('team_a', 'team_b')) == pair]
        rejected = [q for q in snapshot.get('rejected_quotes', [])
                    if q.get('source_key') == key and q.get('team_a') and q.get('team_b') and
                    sorted(core.canon(q[k])[0] for k in ('team_a', 'team_b')) == pair]
        rejected_note = (' Rejected same-pair contract(s): ' + '; '.join(sorted(set(q.get('reason') or 'unverified' for q in rejected)))) if rejected else ''
        steps.append({'label': '2 · ' + name, 'url': meta.get('url') or url,
                      'at_utc': meta.get('at_utc'), 'http_status': meta.get('status'),
                      'candidate_count': len(candidates), 'rejected_candidate_count': len(rejected),
                      'result': access_result(meta) + (f' {len(candidates)} same-pair candidate(s), but none passed all identity, time, freshness and market gates.' if candidates else
                                 ' No same-pair usable quote retained. This is capture coverage, not proof of market absence.') + rejected_note})
    vrs = snapshot.get('vrs') or {}
    steps.append({'label': '3 · Official Valve rating fallback', 'url': vrs.get('page_url') or VALVE,
                  'at_utc': log.get('valve_vrs_file', {}).get('at_utc'), 'http_status': log.get('valve_vrs_file', {}).get('status'),
                  'result': 'Unique eligible ratings support a model estimate only.' if row.get('line') else
                            'No eligible rating pair can resolve this fixture; missing, duplicate or stale inputs are not inferred.'})
    return {'steps': steps, 'limitations': limitations(row),
            'status': 'model_estimate' if row.get('line') else 'unresolved'}
