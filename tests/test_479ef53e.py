"""Regression checks for freshness, fallback eligibility, and complete source replay."""
import copy
import importlib.util
import json
import unittest
from datetime import timedelta
from tests.test_c64a5e19 import B, ROOT, snapshot


class TestStrictIntegration(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot()

    def test_stale_evidence_keeps_fixture_rows_but_blanks_picks(self):
        now = B.core.parse_iso(self.snap['collected_to_utc'])
        for meta in self.snap['access_log'].values():
            if isinstance(meta, dict) and 'at_utc' in meta:
                meta['at_utc'] = B.core.to_iso(now - timedelta(hours=5))
        board = B.build_board(self.snap, 'test')
        self.assertTrue(board['open'])
        self.assertTrue(all(r['line'] is None for r in board['open']))

    def test_future_quote_times_do_not_create_markets(self):
        now = B.core.parse_iso(self.snap['collected_to_utc'])
        for q in self.snap['quotes']:
            q['retrieved_utc'] = B.core.to_iso(now + timedelta(minutes=5))
        board = B.build_board(self.snap, 'test')
        self.assertTrue(all(r['market'] is None for r in board['open']))

    def test_new_unrated_low_tier_fixture_is_not_dropped_or_assigned_floor(self):
        now = B.core.parse_iso(self.snap['collected_to_utc'])
        fx = copy.deepcopy(next(f for f in self.snap['hotspawn']['fixtures'] if f['status'] == 'scheduled'))
        fx.update(fixture_id='test-new-fixture', team_a='Unrated Test A', team_b='Unrated Test B',
                  lock_utc=B.core.to_iso(now + timedelta(hours=2)),
                  start_utc=B.core.to_iso(now + timedelta(hours=3)), seen_in=['lobby_page'])
        self.snap['hotspawn']['fixtures'].append(fx)
        b = B.build_board(self.snap, 'test')
        row = next(r for r in b['open'] if r['fixture_id'] == fx['fixture_id'])
        self.assertIsNone(row['line'])
        self.assertIn('no_line_unverified', row['flags'])
        self.assertEqual(row['hotspawn_url'], B.LOBBY)

    def test_locked_fixture_moves_to_inventory(self):
        b = B.build_board(self.snap, 'test')
        if not b['open']: self.skipTest('No current open fixtures')
        fid = b['open'][0]['fixture_id']
        next(f for f in self.snap['hotspawn']['fixtures'] if f['fixture_id'] == fid)['lock_utc'] = self.snap['collected_to_utc']
        rebuilt = B.build_board(self.snap, 'test')
        self.assertNotIn(fid, {r['fixture_id'] for r in rebuilt['open']})
        self.assertIn(fid, {r['fixture_id'] for r in rebuilt['inventory']})

    def test_duplicate_roster_cannot_get_a_model_probability(self):
        self.snap['quotes'] = []
        self.snap['vrs']['teams'] += copy.deepcopy(self.snap['vrs']['teams'])
        b = B.build_board(self.snap, 'test')
        self.assertTrue(all(r['line'] is None for r in b['open']))

    def test_exact_evaluation_is_reproducible_and_does_not_mutate_snapshot(self):
        original = copy.deepcopy(self.snap)
        a = B.build_board(self.snap, 'test')
        b = B.build_board(self.snap, 'test', B.core.parse_iso(a['generated_utc']))
        self.assertEqual(a, b)
        self.assertEqual(original, self.snap)

    def test_current_output_replays_official_fixture_and_rating_rows(self):
        data = ROOT / 'data/c64a5e19'
        spec = importlib.util.spec_from_file_location('test_replay_inputs', ROOT / 'scripts/c64a5e19/verify_inputs.py')
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        snap = json.loads((data / 'snapshot.json').read_text())
        evidence = json.loads((data / 'official_inputs.json').read_text())
        result = verify.verify(snap, evidence, B.core)
        self.assertEqual(result['failures'], [])
        self.assertGreater(result['fixture_rows_checked'], 0)
        changed = copy.deepcopy(snap)
        f = next(f for f in changed['hotspawn']['fixtures'] if 'lobby_page' in f.get('seen_in', []))
        f['team_a'] = 'CORRUPTED'
        self.assertTrue(verify.verify(changed, evidence, B.core)['failures'])
        if changed['vrs'].get('teams'):
            changed = copy.deepcopy(snap)
            changed['vrs']['teams'][0]['points'] += 1
            self.assertTrue(verify.verify(changed, evidence, B.core)['failures'])

    def test_root_summary_has_no_frozen_match_counts_or_obsolete_blend_claim(self):
        text = (ROOT / 'scripts/build_site.py').read_text()
        self.assertNotIn('28 open: 22', text)
        self.assertNotIn('All 89 CS2', text)
        self.assertNotIn('The 10 open matches', text)
        self.assertIn('pick_summary.get(key', text)
        self.assertIn('picks-every-match/index.html', text)


if __name__ == '__main__':
    unittest.main()
