"""Source/eligibility regressions; no network and no guessed fixture data."""
import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scripts/f7279a54'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

core = module('ae_core', HERE / 'core.py')
old_core = sys.modules.get('core')
sys.modules['core'] = core
try:
    build = module('ae_build', HERE / 'build.py')
finally:
    if old_core is not None:
        sys.modules['core'] = old_core
    else:
        sys.modules.pop('core', None)

class Eligibility(unittest.TestCase):
    def setUp(self):
        self.snap = json.loads((ROOT / 'data/f7279a54/snapshot.json').read_text())

    def board(self, snap=None):
        return build.build_board(snap or self.snap, {}, {}, {})

    def test_market_is_not_changed_by_fallback_model(self):
        for r in self.board()['open']:
            if r['market']:
                self.assertEqual(r['line']['basis'], 'market')
                self.assertEqual(r['market']['prob_a'], r['line']['prob_a'])

    def test_stale_fixture_observation_never_gets_line(self):
        snap = copy.deepcopy(self.snap)
        snap['access_log']['hotspawn_lobby_page']['age_header'] = '14401'
        b = self.board(snap)
        self.assertTrue(b['open'])
        for r in b['open']:
            self.assertIsNone(r['line'])
            self.assertIn('fixture_observation_stale_or_unverified', r['flags'])

    def test_stale_quotes_not_used(self):
        snap = copy.deepcopy(self.snap)
        for q in snap['quotes']:
            q['retrieved_utc'] = '2020-01-01T00:00:00Z'
        self.assertFalse(any(r['market'] for r in self.board(snap)['open']))

    def test_future_dated_quotes_not_used(self):
        snap = copy.deepcopy(self.snap)
        for q in snap['quotes']:
            q['retrieved_utc'] = '2099-01-01T00:00:00Z'
        self.assertFalse(any(r['market'] for r in self.board(snap)['open']))

    def test_stale_ratings_not_used(self):
        snap = copy.deepcopy(self.snap)
        snap['vrs']['snapshot'] = '2020_01_01'
        self.assertFalse(any(r['model'] for r in self.board(snap)['open']))

    def test_corrupt_derived_probabilities_do_not_change_board(self):
        snap = copy.deepcopy(self.snap)
        for q in snap['quotes']:
            q['prob_a'] = 0.999
        a = self.board()
        b = self.board(snap)
        self.assertEqual([r['line'] for r in a['open']], [r['line'] for r in b['open']])

    def test_api_only_rows_not_presented_as_lobby_matches(self):
        snap = copy.deepcopy(self.snap)
        original = next(f for f in snap['hotspawn']['fixtures'] if 'lobby_page' in f['seen_in'])
        extra = {**original, 'fixture_id': 'mock-api-only', 'seen_in': ['api']}
        snap['hotspawn']['fixtures'].append(extra)
        self.assertNotIn('mock-api-only', [r['fixture_id'] for r in self.board(snap)['open']])

    def test_duplicates_do_not_establish_roster_by_match_recency(self):
        idx, dup = build.rating_index({'teams': [
            {'team': 'Example', 'points': 1500, 'latest_match_date': '2026-10-10'},
            {'team': 'Example', 'points': 1100, 'latest_match_date': '2026-09-10'}]})
        self.assertNotIn('example', idx)
        self.assertIn('example', dup)

    def test_missing_start_and_approximate_start_rejected(self):
        f = {'team_a': 'A', 'team_b': 'B', 'start_utc': '2026-10-16T12:00:00Z'}
        q = {**f, 'start_utc': None}
        self.assertTrue(core.match_quote(f, q)['rejected'])
        q = {**f, 'start_is_approx': True}
        self.assertTrue(core.match_quote(f, q)['rejected'])

    def test_invalid_numbers_never_form_probabilities(self):
        for n in (float('nan'), float('inf'), -1, 0, 1):
            self.assertIsNone(core.no_vig(n, 2))

    def test_expiration_deadline_and_executive_summary_rendered(self):
        b = self.board()
        page = build.render_index(b)
        self.assertIn('Executive summary', page)
        self.assertIn('data-valid-until=', page)
        self.assertIn('Expired — awaiting source refresh', page)
        self.assertIn('setInterval(expire,60000)', page)
        self.assertIn('Strict market-only picks', page)
        for r in b['open']:
            self.assertIsNotNone(core.parse_iso(r['valid_until_utc']))

class OfficialPayloadReplay(unittest.TestCase):
    @unittest.skipUnless((ROOT / 'data/f7279a54/source_payloads.json').exists(), 'no retained responses yet')
    def test_every_consumed_quote_replays_from_official_response(self):
        verifier = module('ae_payload_verifier', ROOT / 'scripts/ae75c5c3/verify_source_payloads.py')
        result = verifier.verify()
        self.assertFalse(result['failures'], result['failures'])
        self.assertGreater(result['provider_responses'], 0)

class CollectorPermalinks(unittest.TestCase):
    def test_real_collector_cannot_reintroduce_numeric_routes(self):
        path = str(ROOT / 'scripts/live')
        sys.path.insert(0, path)
        try:
            collect = module('ae_live_collect', ROOT / 'scripts/live/collect_live.py')
        finally:
            sys.path.remove(path)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        ms = str(int(now.timestamp() * 1000))
        rows = [{'id': '12345', 'sport_alias': 'cs2', 'scheduled_start_time': ms},
                {'id': '67890', 'sport_alias': 'cs2', 'scheduled_start_time': ms}]
        official = 'https://www.hotspawn.com/matches/example-vs-other-event-12345'
        with patch.object(collect, 'fetch_json', return_value=(rows, {'status': 200})):
            result = collect.collect_fixtures({}, {'12345', '67890'}, {'12345': official})
        self.assertEqual(result[0]['source']['hotspawn_match_url'], official)
        self.assertEqual(result[1]['source']['hotspawn_match_url'], collect.LOBBY_PAGE)
        self.assertEqual(result[1]['source']['hotspawn_match_url_kind'], 'official_lobby_fallback')

if __name__ == '__main__':
    unittest.main()
