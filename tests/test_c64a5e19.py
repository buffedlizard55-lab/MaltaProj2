"""Every-match integration invariants; no frozen match counts or forced picks."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scripts/c64a5e19'
previous_path = sys.path[:]
try:
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location('verified_every_match_build', HERE / 'build.py')
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
finally:
    sys.path[:] = previous_path


def snapshot():
    return json.loads((ROOT / 'data/f7279a54/snapshot.json').read_text())


class TestEveryMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = snapshot()
        cls.b = B.build_board(cls.snap, 'test')

    def test_every_open_fixture_is_present_once(self):
        now = B.core.parse_iso(self.snap['collected_to_utc'])
        expected = {f['fixture_id'] for f in self.snap['hotspawn']['fixtures']
                    if 'lobby_page' in f.get('seen_in', []) and f['status'] == 'scheduled'
                    and B.core.parse_iso(f['lock_utc'] or f['start_utc']) > now}
        actual = [r['fixture_id'] for r in self.b['open']]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))
        s = self.b['summary']
        self.assertEqual(s['open'], s['tier_a_market'] + s['tier_b_model'] + s['tier_d_none'])
        self.assertEqual(s['tier_c_fallback'], 0)

    def test_inventory_includes_locked_and_past_but_not_api_only(self):
        expected = {f['fixture_id'] for f in self.snap['hotspawn']['fixtures'] if 'lobby_page' in f.get('seen_in', [])}
        self.assertEqual({r['fixture_id'] for r in self.b['inventory']}, expected)

    def test_probabilities_and_pick_orientation(self):
        for r in self.b['open']:
            ln = r['line']
            if not ln:
                self.assertIn('no_line_unverified', r['flags'])
                continue
            self.assertAlmostEqual(ln['prob_a'] + ln['prob_b'], 1.0, places=3)
            self.assertEqual(ln['pick_prob'], max(ln['prob_a'], ln['prob_b']))
            if ln['pick_team']:
                self.assertEqual(ln['pick_team'], r['team_a'] if ln['prob_a'] > ln['prob_b'] else r['team_b'])

    def test_market_first_fallback_only_for_gaps(self):
        for r in self.b['open']:
            if r['market']:
                self.assertEqual(r['line']['tier'], 'A')
                self.assertEqual(r['line']['prob_a'], r['market']['prob_a'])
                self.assertEqual(r['line']['market_weight'], 1)
            elif r['line']:
                self.assertEqual(r['line']['tier'], 'B')
                self.assertTrue(r['vrs']['team_a'])
                self.assertTrue(r['vrs']['team_b'])

    def test_no_sibling_floor_or_ambiguous_slot_inference(self):
        for r in self.b['open']:
            if 'LFO 10' in (r['team_a'], r['team_b']) or 'WROTBERRY' in (r['team_a'], r['team_b']):
                self.assertIsNone(r['line'], r['fixture_id'])
            self.assertIsNone(r['fallback'])

    def test_all_rows_have_official_source_and_flags_page_anchor(self):
        flagged = B.render_flagged(self.b)
        for r in self.b['open']:
            self.assertTrue(r['sources'])
            self.assertTrue(r['sources'][0]['url'].startswith(('https://www.hotspawn.com/', B.LOBBY)))
            self.assertIn(f'id="f-{r["fixture_id"]}"', flagged)

    def test_no_crowd_input(self):
        noisy = copy.deepcopy(self.snap)
        for f in noisy['hotspawn']['fixtures']:
            f['picked_percent'] = 99.9
        changed = B.build_board(noisy, 'test')
        self.assertEqual([r['line'] for r in changed['open']], [r['line'] for r in self.b['open']])

    def test_rendered_pages_and_mobile_navigation(self):
        for render in (B.render_index, B.render_picks, B.render_inventory, B.render_method, B.render_flagged):
            text = render(self.b)
            self.assertIn('name="viewport"', text)
            self.assertIn('Skip to content', text)
            self.assertIn('Every-match picks', text)
            self.assertIn('href="../index.html"', text)
        self.assertIn('Executive summary', B.render_index(self.b))
        self.assertIn('Missing prices or uncertain team identities', B.render_index(self.b))


if __name__ == '__main__':
    unittest.main()
