"""Session 5a40690b unit tests: TWC 2026 Day 1-3 review -> Day 4 Semifinals picks,
contrarian leaderboard strategy, and every-match CS2 coverage + unresolved verification."""
from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location('build_5a40690b', ROOT / 'scripts/5a40690b/build.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BUILDER = load_builder()


class TestSession5a40690b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = BUILDER.build_data(ROOT)
        cls.saved_json = json.loads((ROOT / 'data/5a40690b/day4_and_coverage.json').read_text(encoding='utf-8'))
        cls.day4_html = (ROOT / 'twc-2026/day-4.html').read_text(encoding='utf-8')
        cls.audit_html = (ROOT / 'audits/5a40690b/index.html').read_text(encoding='utf-8')
        cls.day4_soup = BeautifulSoup(cls.day4_html, 'html.parser')
        cls.audit_soup = BeautifulSoup(cls.audit_html, 'html.parser')

    def test_saved_artifacts_match_canonical_board(self):
        self.assertEqual(self.saved_json['canonical_collected_to_utc'], self.doc['canonical_collected_to_utc'])
        self.assertEqual(len(self.saved_json['open_fixtures']), len(self.doc['open_fixtures']))
        self.assertEqual(self.day4_html, BUILDER.render_page(self.doc, '..', 'day4'))
        self.assertEqual(self.audit_html, BUILDER.render_page(self.doc, '../..', 'audit'))

    def test_zero_math_or_canonical_verification_failures(self):
        v = self.doc['verification']
        self.assertEqual(v['canonical_failures'], [])
        self.assertEqual(v['math_failures'], [])
        for r in self.doc['open_fixtures']:
            if r['evidence_tier'] == 'D':
                self.assertIsNone(r['prob_a'])
                self.assertIsNone(r['prob_b'])
                self.assertIsNone(r['pick_team'])
                self.assertIn('no_line_unverified', r['flags'])
            else:
                self.assertTrue(math.isfinite(r['prob_a']) and math.isfinite(r['prob_b']))
                self.assertAlmostEqual(r['prob_a'] + r['prob_b'], 1.0, places=4)
                for q in r['quotes_verified']:
                    self.assertTrue(q['verified'])

    def test_every_table_row_has_official_https_link(self):
        expected_rows = (
            len(self.doc['twc_day4_semifinals'])
            + len(self.doc['twc_matches_d1_d3'])
            + len(self.doc['aurora_roster'])
            + len(self.doc['open_fixtures'])
            + len(self.doc['unresolved_fixtures'])
            + len(self.doc['flagged_items'])
        )
        for name, soup in [('twc-2026/day-4.html', self.day4_soup), ('audits/5a40690b/index.html', self.audit_soup)]:
            rows = soup.select('tbody tr')
            self.assertEqual(len(rows), expected_rows, name)
            for tr in rows:
                links = tr.select('a[href^="https://"]')
                self.assertTrue(links, f'{name} row missing https:// source link: {tr.get_text(" ", strip=True)}')

    def test_twc_day1_to_day3_and_day4_semifinals_complete(self):
        d13 = self.doc['twc_matches_d1_d3']
        self.assertEqual(len(d13), 10)
        self.assertEqual([sum(m['day'] == d for m in d13) for d in (1, 2, 3)], [4, 4, 2])
        d3_aur = next(m for m in d13 if m['fixture_id'] == '1080205')
        self.assertEqual(d3_aur['score'], 'Aurora 2–0 9z')
        self.assertIn('Cache 13–11', d3_aur['maps'])
        self.assertIn('Inferno 13–4', d3_aur['maps'])

        sf = {s['key']: s for s in self.doc['twc_day4_semifinals']}
        self.assertEqual(set(sf.keys()), {'sf1-furia-aurora', 'sf2-falcons-tbd'})
        sf1 = sf['sf1-furia-aurora']
        self.assertAlmostEqual(sf1['external_bookmaker_line']['prob_a'], 0.5, places=4)
        self.assertAlmostEqual(sf1['external_bookmaker_line']['prob_b'], 0.5, places=4)
        self.assertEqual(sf1['vrs_a']['points'], 1795)
        self.assertEqual(sf1['vrs_b']['points'], 1811)

        sf2 = sf['sf2-falcons-tbd']
        self.assertIsNone(sf2['external_bookmaker_line'])
        self.assertEqual(sf2['vrs_a']['points'], 1859)
        self.assertAlmostEqual(
            sf2['vrs_model_scenarios']['vs_Legacy']['calibrated_prob_falcons']
            + sf2['vrs_model_scenarios']['vs_Legacy']['calibrated_prob_underdog'],
            1.0,
            places=4,
        )
        self.assertAlmostEqual(
            sf2['vrs_model_scenarios']['vs_BetBoom']['calibrated_prob_falcons']
            + sf2['vrs_model_scenarios']['vs_BetBoom']['calibrated_prob_underdog'],
            1.0,
            places=4,
        )

    def test_mobile_chrome_and_relative_links_resolve(self):
        for page_path, soup in [
            (ROOT / 'twc-2026/day-4.html', self.day4_soup),
            (ROOT / 'audits/5a40690b/index.html', self.audit_soup),
        ]:
            self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
            self.assertEqual(len(soup.select('h1')), 1)
            self.assertIsNotNone(soup.select_one('#executive-summary'))
            self.assertIsNotNone(soup.select_one('#unresolved-section'))
            self.assertIsNotNone(soup.select_one('#flagged-for-review'))
            for a in soup.select('a[href]'):
                href = a['href'].split('#')[0]
                if not href or href.startswith(('http://', 'https://', 'mailto:')):
                    continue
                target = (page_path.parent / href).resolve()
                self.assertTrue(target.exists(), f'Broken link in {page_path}: {a["href"]} -> {target}')


if __name__ == '__main__':
    unittest.main()
