"""Canonical handoff, fallback-only research and blank-safe source reporting."""
import copy
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from tests.test_c64a5e19 import B, snapshot

ROOT = Path(__file__).resolve().parents[1]


class FallbackResearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = snapshot()
        cls.board = B.build_board(cls.snap, 'test')

    def test_research_never_overrides_or_supplements_accepted_market(self):
        for row in self.board['open']:
            if row['market']:
                self.assertIsNone(row['research'])
                self.assertEqual(row['line']['prob_a'], row['market']['prob_a'])
            else:
                self.assertIsNotNone(row['research'])
                self.assertTrue(row['research']['limitations'])

    def test_every_fallback_attempt_is_source_linked_and_dated_or_unverified(self):
        for row in self.board['open']:
            for step in (row['research'] or {}).get('steps', []):
                self.assertTrue(step['url'].startswith('https://'))
                self.assertIn('at_utc', step)
                self.assertIn('http_status', step)
        text = B.render_unresolved(self.board)
        self.assertIn('Automated access probe only', text)
        self.assertIn('same captured snapshot', text)

    def test_research_attempt_order_and_all_external_providers(self):
        for row in self.board['open']:
            if not row['research']:
                continue
            labels = [s['label'] for s in row['research']['steps']]
            self.assertEqual(labels[0], '1 · HLTV research')
            for name in ('Pinnacle', 'Bovada', 'Melbet esportsbook', 'Kalshi exchange'):
                self.assertIn('2 · ' + name, labels)
            self.assertEqual(labels[-1], '3 · Official Valve rating fallback')

    def test_unresolved_rows_exactly_match_missing_lines(self):
        soup = BeautifulSoup(B.render_unresolved(self.board), 'html.parser')
        actual = {r['id'].removeprefix('u-') for r in soup.select('tr[id^="u-"]')}
        expected = {r['fixture_id'] for r in self.board['open'] if not r.get('market')}
        self.assertEqual(actual, expected)
        for r in self.board['open']:
            if not r['line']:
                cell = soup.select_one('#u-' + r['fixture_id']).find_all('td')[1]
                self.assertIn('—', cell.get_text())
                self.assertNotIn('%', cell.get_text())

    def test_every_unresolved_table_row_links_official_source(self):
        soup = BeautifulSoup(B.render_unresolved(self.board), 'html.parser')
        for row in soup.select('tbody tr'):
            self.assertIsNotNone(row.select_one('a[href^="https://"]'))

    def test_missing_metadata_not_reported_as_no_odds_or_success(self):
        snap = copy.deepcopy(self.snap)
        snap['access_log'] = {}
        b = B.build_board(snap, 'test')
        self.assertTrue(all(not r['line'] for r in b['open']))
        for row in b['open']:
            step = row['research']['steps'][0]
            self.assertIsNone(step['http_status'])
            self.assertIsNone(step['at_utc'])
            self.assertIn('Not recorded', step['result'])

    def test_blocked_probe_does_not_claim_no_markets(self):
        snap = copy.deepcopy(self.snap)
        snap['access_log']['hltv_probe'] = {'status': 403, 'error': 'HTTPError 403', 'at_utc': snap['collected_to_utc']}
        b = B.build_board(snap, 'test')
        for row in b['open']:
            if row['research']:
                self.assertIn('does not prove', row['research']['steps'][0]['result'])

    def test_stale_board_is_blank_but_keeps_inventory_and_research(self):
        from datetime import timedelta
        b = B.build_board(self.snap, 'test', B.core.parse_iso(self.snap['collected_to_utc']) + timedelta(hours=5))
        self.assertTrue(b['inventory'])
        for row in b['open']:
            self.assertIsNone(row['line'])
            self.assertIsNotNone(row['research'])

    def test_mobile_navigation_has_direct_unresolved_page(self):
        soup = BeautifulSoup(B.render_unresolved(self.board), 'html.parser')
        self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
        self.assertIsNotNone(soup.select_one('nav a[href="unresolved.html"]'))
        self.assertIn('unresolved.html', B.render_index(self.board))

    def test_research_does_not_change_pricing(self):
        plain = B.ENGINE.build_board(copy.deepcopy(self.snap), {}, {}, {})
        expected = {r['fixture_id']: r['line'] for r in plain['open']}
        for row in self.board['open']:
            old = expected[row['fixture_id']]
            self.assertEqual((old or {}).get('prob_a'), (row['line'] or {}).get('prob_a'))
            self.assertEqual((old or {}).get('prob_b'), (row['line'] or {}).get('prob_b'))


class CanonicalLanding(unittest.TestCase):
    def test_landing_has_unique_ids_one_primary_summary_and_no_frozen_other_totals(self):
        soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        ids = [t['id'] for t in soup.select('[id]')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNotNone(soup.select_one('#executive-summary a[href="picks-every-match/index.html"]'))
        self.assertIsNotNone(soup.select_one('#executive-summary a[href="picks-every-match/unresolved.html"]'))
        self.assertNotIn('Second, independent executive summary', soup.get_text())
        self.assertNotIn('resolved 28 of 28', soup.get_text())

    def test_source_research_has_official_links_on_every_row(self):
        soup = BeautifulSoup((ROOT / 'audits/dc741cc1/index.html').read_text(), 'html.parser')
        for row in soup.select('tbody tr'):
            self.assertIsNotNone(row.select_one('a[href^="https://"]'))

    def test_workflow_keeps_four_hour_schedule(self):
        s = (ROOT / '.github/workflows/every-match-c64a5e19.yml').read_text()
        self.assertIn("cron: '12 */4 * * *'", s)
        self.assertIn('scripts/c64a5e19/collect.py', s)
        self.assertIn('scripts/c64a5e19/build.py', s)
