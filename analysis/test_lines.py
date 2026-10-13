"""Validation tests for originated lines (analysis/lines.json / lines.csv). Session 6196c585 T-A.

Run: python -m unittest discover -s analysis -p 'test_*.py' -v

These tests enforce the verification policy:
  - every priced line traces to >=1 external source with a public URL and observation id;
  - probabilities are internally consistent (sum to 1, fair decimal = 1/p);
  - Hotspawn is never a probability source;
  - conflict-flagged / one-sided / placeholder observations never enter consensus;
  - fixtures without admissible two-sided lines are left blank and flagged (never inferred).
"""
import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OCTOBER_FIXTURE_IDS = {
    '1079620', '1081076', '1079546', '1079621', '1080176', '1079438', '1079439', '1079622',
    '1080177', '1080178', '1079623', '1080179', '1079624', '1080279', '1079440', '1079442',
    '1080280', '1080281', '1080282', '1080283', '1080284', '1080285', '1080286', '1080287',
    '1080288', '1080289', '1080290',
}
KNOWN_NO_LINE = {'1079620', '1079624', '1080285'}  # Black Phoenix-6666, FORZE Reload-LFO 10, Voca-Phantom (one-sided only)
MUST_NEVER_BE_USED = {'OBS-007', 'OBS-015', 'OBS-040', 'OBS-044', 'OBS-055', 'OBS-061', 'OBS-062'}


def load():
    return json.loads((ROOT / 'analysis/lines.json').read_text())


def load_observations():
    return {o['obs_id']: o for o in json.loads((ROOT / 'analysis/odds_observations.json').read_text())['observations']}


class LinesTests(unittest.TestCase):
    def test_lines_file_shape(self):
        d = load()
        self.assertEqual(d['fixtures_total'], 86)
        self.assertEqual(len(d['lines']), 86)
        self.assertEqual(d['priced'], len(OCTOBER_FIXTURE_IDS) - len(KNOWN_NO_LINE))

    def test_priced_records_consistent(self):
        d = load()
        observations = load_observations()
        used = set()
        for r in d['lines']:
            if r['probability_a'] is None:
                continue
            pa, pb = r['probability_a'], r['probability_b']
            self.assertTrue(0 < pa < 1 and 0 < pb < 1, r['fixture_id'])
            self.assertAlmostEqual(pa + pb, 1.0, places=9)
            self.assertAlmostEqual(r['fair_decimal_a'], 1.0 / pa, places=6)
            self.assertAlmostEqual(r['fair_decimal_b'], 1.0 / pb, places=6)
            self.assertTrue(r['sources'], 'priced fixture must have >=1 source')
            expected = 'multi-source' if len(r['sources']) >= 2 else 'single-source'
            self.assertEqual(r['confidence'], expected)
            for s in r['sources']:
                self.assertTrue(s['source'].startswith('http'), 'every line needs a public source URL')
                self.assertIn(s['obs_id'], observations)
                self.assertNotIn('hotspawn', s['source'].lower(), 'Hotspawn must never be a probability source')
                self.assertNotIn(s['obs_id'], MUST_NEVER_BE_USED)
                used.add(s['obs_id'])
        self.assertEqual(used & MUST_NEVER_BE_USED, set())

    def test_october_coverage_and_blanks(self):
        d = load()
        for r in d['lines']:
            is_oct = r['fixture_id'] in OCTOBER_FIXTURE_IDS
            if is_oct and r['fixture_id'] in KNOWN_NO_LINE:
                self.assertIsNone(r['probability_a'])
                self.assertTrue(r['flags'], 'no-line fixture must be blank AND flagged')
                self.assertEqual(r['confidence'], 'no-two-sided-line')
            elif is_oct:
                self.assertIsNotNone(r['probability_a'], f"October fixture {r['fixture_id']} must be priced or in KNOWN_NO_LINE")
            else:
                self.assertIsNone(r['probability_a'])
                self.assertEqual(r['confidence'], 'stale-fixture')
                self.assertEqual(r['status'], 'unverified')
                self.assertTrue(r['flags'])

    def test_voca_phantom_one_side_never_inferred(self):
        d = load()
        r = next(x for x in d['lines'] if x['fixture_id'] == '1080285')
        self.assertIsNone(r['probability_a'])
        self.assertIsNone(r['probability_b'])
        self.assertTrue(any(e['obs_id'] == 'OBS-055' for e in r['excluded_observations']))

    def test_csv_matches_json(self):
        d = load()
        with (ROOT / 'analysis/lines.csv').open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(d['lines']))
        for row, rec in zip(rows, d['lines']):
            self.assertEqual(row['fixture_id'], rec['fixture_id'])
            if rec['probability_a'] is None:
                self.assertEqual(row['probability_a'], '')
            else:
                self.assertAlmostEqual(float(row['probability_a']), rec['probability_a'], places=4)

    def test_crowd_file_is_context_only(self):
        c = json.loads((ROOT / 'analysis/hotspawn_picked_pct.json').read_text())
        self.assertIn('NEVER', c['purpose'])
        self.assertEqual(len(c['records']), 27)
        for rec in c['records']:
            self.assertIn(rec['picked_pct_a'] + rec['picked_pct_b'], (99, 100, 101), 'Hotspawn rounding; see rounding_note')
            self.assertIn(rec['fixture_id'], OCTOBER_FIXTURE_IDS)


if __name__ == '__main__':
    unittest.main()
