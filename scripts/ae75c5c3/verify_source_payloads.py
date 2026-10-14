"""Replay official provider JSON offline and verify every consumed quote's identity/prices.

Network is mocked; no secondary site or hand-written quote is accepted as source evidence.
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'scripts/f7279a54'

def verify(data_dir=None):
    data_dir = Path(data_dir or ROOT / 'data/f7279a54')
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, HERE / filename)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    core = load('payload_core', 'core.py')
    previous = sys.modules.get('core')
    sys.modules['core'] = core
    try:
        collect = load('payload_collect', 'collect.py')
    finally:
        if previous is not None:
            sys.modules['core'] = previous
        else:
            sys.modules.pop('core', None)
    payloads = json.loads((data_dir / 'source_payloads.json').read_text())
    board = json.loads((data_dir / 'board.json').read_text())
    def response(url, *args, **kwargs):
        source = payloads['sources'].get(url)
        if not source:
            return None, {'status': None, 'error': 'payload not retained'}
        return source['payload'], {'status': source['http_status'], 'at_utc': source['retrieved_utc']}
    parsed, rejected = [], []
    with patch.object(collect, 'fetch_json', side_effect=response), patch.object(collect.time, 'sleep'):
        collect.collect_pinnacle(parsed)
        collect.collect_bovada(parsed)
        collect.collect_melbet(parsed)
        collect.collect_kalshi(parsed, rejected)
    def key(q):
        names = q.get('names_at_source') or [q['team_a'], q['team_b']]
        return (q['source_key'], q['event_id'], tuple(names), q['raw_format'],
                str(q['raw_a']), str(q['raw_b']))
    indexed = {key(q): q for q in parsed}
    checked, rows, failures = 0, [], []
    for row in board['open']:
        for quote in row['quotes']:
            checked += 1
            k = key(quote)
            source = indexed.get(k)
            if source is None:
                failures.append(f"{row['fixture_id']} quote not reproduced from official response: {k}")
            elif source.get('start_utc') != quote.get('start_utc_at_source'):
                failures.append(f"{row['fixture_id']} kickoff differs from official response")
            elif source.get('live'):
                failures.append(f"{row['fixture_id']} live quote entered prematch picks")
            rows.append({'fixture_id': row['fixture_id'], 'source': quote['api_url'],
                         'event_id': quote['event_id'], 'confirmed': source is not None})
    return {'source_observed_utc': payloads['collected_to_utc'], 'provider_responses': len(payloads['sources']),
            'replayed_quotes': len(parsed), 'consumed_quotes_checked': checked,
            'failures': failures, 'rows': rows}

if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, indent=2))
    if result['failures']:
        raise SystemExit(1)
