"""Canonical dashboard: data-driven coverage, blank unverified inputs and safe links."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard_9caec349', ROOT/'scripts/9caec349/dashboard.py')
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((ROOT/'data/f7279a54/board.json').read_text())
        cls.soup = BeautifulSoup(D.render(cls.board), 'html.parser')

    def test_exact_inventory_not_hardcoded(self):
        rows = self.soup.select('[data-pick-row]')
        self.assertEqual({r['id'] for r in rows}, {'pick-'+r['fixture_id'] for r in self.board['open']})
        smaller = copy.deepcopy(self.board)
        smaller['open'] = smaller['open'][:2]
        self.assertEqual(len(BeautifulSoup(D.render(smaller),'html.parser').select('[data-pick-row]')), 2)

    def test_probabilities_and_picks_copied_without_changing_market(self):
        for r in self.board['open']:
            rendered = self.soup.select_one('#pick-'+r['fixture_id'])
            p = [e.text for e in rendered.select('[data-prob]')]
            if r['line']:
                self.assertEqual(p, [f"{r['line']['prob_a']*100:.1f}%", f"{r['line']['prob_b']*100:.1f}%"])
                self.assertEqual(rendered['data-basis'], r['line']['basis'])
            else:
                self.assertEqual(p, ['—','—'])
                self.assertIn('Unverified', rendered.select_one('[data-pick]').text)

    def test_each_row_has_sources_expiry_and_matching_analysis_anchor(self):
        for r in self.soup.select('[data-pick-row]'):
            self.assertTrue(r.select('a[href^="https://"]'))
            self.assertTrue(r['data-expiry'])
            self.assertTrue(r['data-lock'])
            self.assertTrue(r.select('a[href="ourline/index.html#m-'+r['id'].removeprefix('pick-')+'"]'))

    def test_missing_board_fails_closed(self):
        self.assertNotIn('data-pick-row', D.render({}))
        self.assertIn('unavailable', D.render({}))

    def test_untrusted_strings_escaped(self):
        b = copy.deepcopy(self.board)
        b['open'][0]['team_a'] = '<script>alert(1)</script>'
        self.assertNotIn('<script>', D.render(b))
        self.assertEqual(D.link('javascript:alert(1)', 'source'), '')

    def test_snapshot_stats_and_accessible_controls(self):
        values = [int(e.text) for e in self.soup.select('.card-num')]
        self.assertEqual(values[0], len(self.board['open']))
        self.assertEqual(sum(values[1:]), values[0])
        self.assertIsNotNone(self.soup.select_one('label[for="dashboard-search"]'))
        self.assertIsNotNone(self.soup.select_one('label[for="dashboard-basis"]'))
        self.assertIn('at this observation', self.soup.text)

    def test_dated_independent_audit_passed(self):
        audit = json.loads((ROOT/'audits/9caec349/report.json').read_text())
        self.assertEqual(audit['failures'], [])
        self.assertEqual(audit['rows_checked'], len(audit['rows']))
        self.assertTrue(all(row['sources'] for row in audit['rows']))
