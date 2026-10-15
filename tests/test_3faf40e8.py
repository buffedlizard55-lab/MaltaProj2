"""Current canonical evidence contracts, independent of archive refresh clocks."""
import json
import math
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from tests.test_c64a5e19 import B

ROOT = Path(__file__).resolve().parents[1]


class CurrentEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = json.loads((ROOT / 'data/c64a5e19/snapshot.json').read_text())
        cls.board = B.build_board(cls.snap, 'data/c64a5e19/snapshot.json')

    def test_all_lobby_rows_retained_from_the_same_snapshot(self):
        expected = {f['fixture_id'] for f in self.snap['hotspawn']['fixtures'] if 'lobby_page' in f.get('seen_in', [])}
        ids = [r['fixture_id'] for r in self.board['inventory']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), expected)
        self.assertEqual(self.board['summary']['listed'], len(ids))

    def test_primary_response_replay_covers_inventory_ratings_and_prices(self):
        verification = json.loads((ROOT / 'data/c64a5e19/verification.json').read_text())
        saved = json.loads((ROOT / 'data/c64a5e19/board.json').read_text())
        self.assertEqual(verification['failures'], [])
        inputs = verification['official_inputs']
        self.assertEqual(inputs['fixture_rows_checked'], len(saved['inventory']))
        self.assertEqual(inputs['rating_rows_checked'], len(self.snap['vrs']['teams']))
        self.assertTrue(all(r['confirmed'] for r in inputs['fixture_rows']))
        self.assertEqual(verification['consumed_quotes_checked'], sum(len(r['quotes']) for r in saved['open']))

    def test_research_is_explanatory_only_and_does_not_change_market_picks(self):
        for row in self.board['open']:
            if row['market']:
                self.assertIsNone(row['research'])
                self.assertEqual(row['line']['prob_a'], row['market']['prob_a'])
            else:
                self.assertIn(row['research']['status'], ('unresolved', 'model_estimate'))
                self.assertTrue(row['research']['limitations'])
                self.assertTrue(row['research']['steps'])

    def test_supported_numbers_finite_normalized_or_blank_with_reason(self):
        for row in self.board['open']:
            line = row['line']
            if not line:
                self.assertIsNotNone(row['research'])
                self.assertIn('no_line_unverified', row['flags'])
                continue
            self.assertTrue(math.isfinite(line['prob_a']))
            self.assertTrue(math.isfinite(line['prob_b']))
            self.assertAlmostEqual(line['prob_a'] + line['prob_b'], 1, places=5)
            self.assertEqual(line['pick_prob'], max(line['prob_a'], line['prob_b']))

    def test_every_canonical_table_row_has_primary_source_link(self):
        for render in (B.render_index, B.render_picks, B.render_inventory, B.render_unresolved, B.render_flagged):
            soup = BeautifulSoup(render(self.board), 'html.parser')
            for row in soup.select('tbody tr'):
                self.assertTrue(row.select('a[href^="https://"]'), row.get_text())

    def test_expiry_cannot_be_reset_by_page_regeneration(self):
        from datetime import timedelta
        expired = B.build_board(self.snap, 'test', B.core.parse_iso(self.snap['collected_to_utc']) + timedelta(hours=5))
        self.assertEqual(expired['collected_to_utc'], self.snap['collected_to_utc'])
        self.assertTrue(all(r['line'] is None for r in expired['open']))
        self.assertEqual(len(expired['inventory']), len(self.board['inventory']))

    def test_audit_has_official_sources_and_no_inferred_observation_time(self):
        doc = json.loads((ROOT / 'audits/3faf40e8/sources.json').read_text())
        self.assertIsNone(doc['source_observation_utc'])
        self.assertEqual(len(doc['valve_git_blob_sha']), 40)
        for finding in doc['findings']:
            self.assertTrue(finding['sources'])
            self.assertTrue(all(u.startswith('https://') for u in finding['sources']))
        soup = BeautifulSoup((ROOT / 'audits/3faf40e8/index.html').read_text(), 'html.parser')
        self.assertEqual(len(soup.select('tbody tr')), len(doc['findings']))
        for row in soup.select('tbody tr'):
            self.assertTrue(row.select('a[href^="https://"]'))

    def test_unresolved_and_review_are_reachable_without_archive_navigation(self):
        soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        for path in ('picks-every-match/index.html', 'picks-every-match/unresolved.html'):
            link = soup.select_one('#executive-summary a[href="' + path + '"]')
            self.assertIsNotNone(link)
            self.assertIsNone(link.find_parent('details'))
        self.assertIsNotNone(soup.select_one('a[href="audits/3faf40e8/index.html"]'))
        self.assertIn('../audits/3faf40e8/index.html', B.render_flagged(self.board))


if __name__ == '__main__':
    unittest.main()
