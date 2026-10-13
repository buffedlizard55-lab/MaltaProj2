import json
import math
import unittest
from fractions import Fraction
from pathlib import Path

from compile_audit import OBSERVED, build, calculate, implied


class AuditTests(unittest.TestCase):
    def test_all_visible_cards_have_official_links_and_blank_unverified_values(self):
        audit = build()
        self.assertEqual(len(audit['matches']), 26)
        self.assertEqual(len({m['id'] for m in audit['matches']}), 26)
        for m in audit['matches']:
            self.assertEqual(m['source'], 'https://play.hotspawn.com/lobby')
            self.assertTrue(m['match_source'].startswith('https://www.hotspawn.com/matches/'))
            self.assertIsNone(m['scheduled_at_utc'])
            self.assertIsNone(m['timezone'])
            self.assertIsNone(m['year'])
            self.assertIsNone(m['odds'])
            self.assertIsNone(m['probabilities'])
            self.assertEqual(len(m['teams']), 2)
            self.assertTrue(m['flags'])

    def test_all_input_rows_are_preserved(self):
        for row, observed in zip(build()['matches'], OBSERVED):
            self.assertEqual(row['scheduled_label'], observed[0])
            self.assertEqual(row['teams'], list(observed[1:3]))
            self.assertEqual(row['tournament'], observed[3])
            self.assertTrue(row['match_source'].endswith(observed[4]))

    def test_american_conversion(self):
        self.assertEqual(implied(100), Fraction(1, 2))
        self.assertEqual(implied(-100), Fraction(1, 2))
        self.assertEqual(implied(280), Fraction(5, 19))
        self.assertEqual(implied(-455), Fraction(91, 111))
        for invalid in [0, 1, -99, 99, 1.5, True, '280']:
            with self.assertRaises(ValueError):
                implied(invalid)

    def test_independent_fraction_checks(self):
        self.assertEqual(calculate([280, -455])['exact_probability_fractions'], ['555/2284', '1729/2284'])
        self.assertEqual(calculate([-1250, 530])['exact_probability_fractions'], ['35/41', '6/41'])
        for q in build()['independent_official_price_observations']:
            self.assertFalse(q['publish_as_current_lobby_probability'])
            self.assertIsNone(q['market_phase'])
            a = q['analysis']
            self.assertAlmostEqual(sum(a['probability']), 1)
            self.assertAlmostEqual(sum(a['raw_implied_probability']) - 1, a['overround'])
            for p, d in zip(a['probability'], a['fair_decimal_odds']):
                self.assertTrue(math.isfinite(p))
                self.assertAlmostEqual(p * d, 1)

    def test_committed_snapshot_matches_compiler(self):
        self.assertEqual(json.loads(Path(__file__).with_name('observations.json').read_text()), build())

    def test_no_crowd_pick_fields(self):
        text = json.dumps(build()).lower()
        self.assertNotIn('picked', text)
        self.assertNotIn('crowd_probability', text)


if __name__ == '__main__':
    unittest.main()
