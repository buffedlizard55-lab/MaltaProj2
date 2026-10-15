"""Guard the primary handoff against competing snapshots and false coverage."""
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]

class CanonicalIntegration(unittest.TestCase):
    def setUp(self):
        self.soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')

    def test_primary_cta_and_nav_use_same_strict_board(self):
        summary = self.soup.select_one('#executive-summary')
        self.assertEqual(summary.select_one('a.btn-primary')['href'], 'picks-every-match/index.html')
        self.assertIsNotNone(self.soup.select_one('nav a[href="picks-every-match/index.html"]'))
        self.assertIsNone(self.soup.select_one('nav a[href="board/picks.html"]'))
        self.assertIsNotNone(summary.select_one('#canonical-unresolved'))
        self.assertIsNone(summary.select_one('a[href="picks-every-match/unresolved.html"]').find_parent('details'))

    def test_counts_reproduce_one_board_not_competing_totals(self):
        board = json.loads((ROOT / 'data/c64a5e19/board.json').read_text())
        expected = [str(board['summary'][key]) for key in ('open', 'tier_a_market', 'tier_b_model', 'tier_d_none')]
        self.assertEqual([e.get_text() for e in self.soup.select('#executive-summary .card-num')], expected)
        self.assertIn(board['collected_to_utc'], self.soup.get_text())
        self.assertIn(board['generated_utc'], self.soup.get_text())
        self.assertNotIn('gets a pick and win probability here', self.soup.get_text())

    def test_day_one_rows_have_direct_specialist_sources_and_blank_limits(self):
        soup = BeautifulSoup((ROOT / 'day-one.html').read_text(), 'html.parser')
        rows = soup.select('tbody tr')
        self.assertEqual(len(rows), 7)
        for row in rows:
            self.assertIsNotNone(row.select_one('a[href^="https://"]'))
        for row in rows[-3:]:
            self.assertEqual(row.select('td')[1].get_text(), '—')
            self.assertIn('Unverified', row.get_text())
        self.assertIn('not the event organizer', soup.get_text())
        self.assertIn('not immediately before', soup.get_text())

    def test_day_one_review_does_not_feed_the_pricing_engine(self):
        engine = (ROOT / 'scripts/c64a5e19/build.py').read_text()
        self.assertNotIn('day_one_review', engine)
        self.assertNotIn('45082', engine)

    def test_no_duplicate_ids_and_mobile_metadata(self):
        for name in ('index', 'day-one', 'flagged'):
            soup = BeautifulSoup((ROOT / (name + '.html')).read_text(), 'html.parser')
            ids = [e['id'] for e in soup.select('[id]')]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
