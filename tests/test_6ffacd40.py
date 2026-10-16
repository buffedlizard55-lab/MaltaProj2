"""Coverage accounting, independent raw-price audit and mobile handoff regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def mod(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = mod('test_audit_6ff', 'scripts/6ffacd40/audit.py')
HOME = mod('test_home_6ff', 'scripts/build_site.py')


def board():
    return json.loads((ROOT / 'data/c64a5e19/board.json').read_text())


class CoverageAudit(unittest.TestCase):
    def test_current_board_independently_rederives(self):
        result = A.verify_board(board())
        self.assertEqual(result['failures'], [])
        self.assertEqual(sum(result['counts'].values()), len(board()['open']))

    def test_retained_official_inventory_ratings_and_quotes_replay(self):
        result = A.audit()
        self.assertEqual(result['failures'], [])
        self.assertGreater(result['inventory_replay']['fixture_rows_checked'], 0)
        self.assertGreater(result['inventory_replay']['rating_rows_checked'], 0)
        self.assertEqual(result['provider_replay']['consumed_quotes_checked'], sum(len(r['quotes']) for r in board()['open']))

    def test_raw_american_conversion_and_orientation(self):
        q = {'raw_a': -200, 'raw_b': 150, 'raw_format': 'american', 'swapped': False}
        self.assertEqual(A.raw_decimals(q), (1.5, 2.5))
        self.assertAlmostEqual(A.quote_probability(q), .625)
        q['swapped'] = True
        self.assertAlmostEqual(A.quote_probability(q), .375)

    def test_decimal_conversion_does_not_use_votes(self):
        q = {'raw_a': 2., 'raw_b': 2., 'raw_format': 'decimal', 'crowd_a': .99}
        self.assertEqual(A.quote_probability(q), .5)

    def test_changed_quote_is_detected(self):
        b = board()
        row = next(r for r in b['open'] if r['quotes'])
        row['quotes'][0]['raw_a'] = 400
        self.assertTrue(A.verify_board(b)['failures'])

    def test_wrong_recommendation_is_detected(self):
        b = board()
        row = next(r for r in b['open'] if (r.get('line') or {}).get('pick_team'))
        row['line']['pick_team'] = 'unsupported choice'
        self.assertTrue(A.verify_board(b)['failures'])

    def test_no_input_mutation(self):
        b = board()
        original = copy.deepcopy(b)
        A.verify_board(b)
        self.assertEqual(b, original)


class MobileHandoff(unittest.TestCase):
    def test_summary_counts_directional_ties_and_blanks_separately(self):
        b = board()
        text = BeautifulSoup(HOME.canonical_home(b), 'html.parser').get_text(' ', strip=True)
        directional = sum(bool((r.get('line') or {}).get('pick_team')) for r in b['open'])
        ties = sum(bool(r.get('line')) and r['line']['prob_a'] == r['line']['prob_b'] for r in b['open'])
        self.assertIn(f'{directional} directional picks', text)
        self.assertIn(f'{ties} priced ties', text)
        self.assertIn('Market-priced matches', text)
        self.assertNotIn('Market-derived picks', text)

    def test_missing_inventory_does_not_claim_zero_picks(self):
        text = BeautifulSoup(HOME.canonical_home({}), 'html.parser').get_text(' ', strip=True)
        self.assertIn('— directional picks', text)
        self.assertIn('— priced ties', text)

    def test_only_canonical_actions_come_before_archives(self):
        soup = BeautifulSoup(HOME.canonical_home(board()), 'html.parser')
        self.assertEqual([a['href'] for a in soup.select('.primary-actions a')], [
            'picks-every-match/index.html', 'picks-every-match/unresolved.html', 'twc-2026/index.html'])
        for href in ('strategy/index.html', 'day3/index.html', 'hub/index.html'):
            a = soup.select_one(f'a[href="{href}"]')
            self.assertIsNotNone(a.find_parent('details'), href)
        self.assertIsNone(soup.select_one('#canonical-unresolved').find_parent('details'))

    def test_skip_link_targets_main(self):
        soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        self.assertEqual(soup.select_one('a.skip-link')['href'], '#main-content')
        self.assertEqual(soup.select_one('#main-content').name, 'main')

    def test_audit_every_value_row_has_source_and_mobile_labels(self):
        soup = BeautifulSoup((ROOT / 'audits/6ffacd40/index.html').read_text(), 'html.parser')
        self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
        self.assertEqual(len(soup.select('h1')), 1)
        for row in soup.select('tbody tr'):
            self.assertIsNotNone(row.select_one('a[href^="https://"]'))
            self.assertTrue(all(td.get('data-label') for td in row.select('td')))

    def test_primary_roster_posts_not_hypothetical_october_move(self):
        data = json.loads((ROOT / 'data/6ffacd40/research.json').read_text())
        self.assertEqual(len(data['official_results']), 8)
        self.assertEqual(len(data['roster']), 3)
        self.assertTrue(all(r['url'].startswith('https://x.com/AuroraCS2_GG/status/') for r in data['roster']))
        self.assertTrue(all('July' in r['claim'] for r in data['roster']))
        self.assertEqual(len(data['gap_reviews']), 5)
        self.assertTrue(all(r['url'].startswith('https://www.hltv.org/matches/') for r in data['gap_reviews']))

    def test_audit_rebuild_is_deterministic_on_same_inputs(self):
        r = A.audit()
        research = json.loads((ROOT / 'data/6ffacd40/research.json').read_text())
        self.assertEqual(A.render(r, research), A.render(r, research))


if __name__ == '__main__':
    unittest.main()
