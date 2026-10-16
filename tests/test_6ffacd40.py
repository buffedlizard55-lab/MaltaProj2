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
        # Integration session 1fac4be2 moved the two CURRENT lists above the fold
        # (every-match picks and the day-4 desk) and made the unresolved action an
        # in-page anchor to this page's own unresolved section. Archived boards stay
        # collapsed; the anchor must resolve on the landing page itself.
        self.assertEqual([a['href'] for a in soup.select('.primary-actions a')], [
            'picks-every-match/index.html', 'day4/index.html', '#canonical-unresolved'])
        landing = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        self.assertIsNotNone(landing.select_one('.primary-actions a[href="#canonical-unresolved"]'))
        self.assertIsNotNone(landing.select_one('#canonical-unresolved'))
        # twc-2026/ and day-one.html remain reachable as current-era cards in the
        # picks grid; the preserved parallel boards stay collapsed in the archive.
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


class PagesPublisher(unittest.TestCase):
    def setUp(self):
        self.gate = mod('test_pages_gate_6ff', 'scripts/6ffacd40/pages_gate.py')

    def test_only_configured_publisher_is_selected(self):
        self.assertEqual(self.gate.configured_publisher({'build_type': 'workflow'}), 'actions')
        self.assertEqual(self.gate.configured_publisher({'build_type': 'legacy', 'source': {'branch': 'main', 'path': '/'}}), 'legacy')
        for pages in ({}, {'build_type': 'legacy'}, {'build_type': 'legacy', 'source': {'branch': 'other', 'path': '/'}}):
            with self.assertRaises(ValueError):
                self.gate.configured_publisher(pages)

    def test_orphan_building_does_not_block_successful_descendant(self):
        builds = [{'status': 'building', 'commit': 'old-orphan'}, {'status': 'errored', 'commit': 'target'}, {'status': 'built', 'commit': 'descendant'}]
        b = self.gate.published_build(builds, 'target', lambda a, b: b == 'descendant')
        self.assertEqual(b['commit'], 'descendant')

    def test_exact_built_sha_does_not_need_compare(self):
        b = self.gate.published_build([{'status': 'built', 'commit': 'target'}], 'target', lambda a, b: self.fail('not needed'))
        self.assertEqual(b['commit'], 'target')

    def test_pending_target_and_unrelated_success_never_count(self):
        builds = [{'status': 'building', 'commit': 'target'}, {'status': 'errored', 'commit': 'target'}, {'status': 'built', 'commit': 'unrelated'}]
        self.assertIsNone(self.gate.published_build(builds, 'target', lambda a, b: False))

    def test_missing_publication_times_out_without_deploying(self):
        with self.assertRaises(RuntimeError):
            self.gate.wait_for_legacy('owner/repo', 'target', attempts=2, api=lambda path: [], sleep=lambda _: None)

    def test_ancestry_comparisons_are_cached(self):
        calls = []
        def api(path):
            calls.append(path)
            if '/compare/' in path:
                return {'status': 'behind'}
            return [{'status': 'built', 'commit': 'older'}]
        with self.assertRaises(RuntimeError):
            self.gate.wait_for_legacy('owner/repo', 'target', attempts=3, api=api, sleep=lambda _: None)
        self.assertEqual(sum('/compare/' in p for p in calls), 1)

    def test_workflow_does_not_use_two_publishers(self):
        text = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertIn("if: steps.publisher.outputs.publisher == 'actions'", text)
        self.assertIn('python scripts/6ffacd40/pages_gate.py', text)
        self.assertIn('python scripts/check_deployment.py', text)
        self.assertNotIn('not active', text)


if __name__ == '__main__':
    unittest.main()
