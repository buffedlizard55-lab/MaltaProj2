"""Session 5468b0ba unit tests: TWC Day 1-3 review, every-match CS2 verification, and CI gate invariants."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import unittest
from datetime import timedelta
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUDIT = load_module('audit_5468b0ba', 'scripts/5468b0ba/build_audit.py')
TWC = load_module('twc_69e4c06a', 'scripts/69e4c06a/build.py')


class Session5468b0baVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = AUDIT.build_audit_data()
        cls.html = AUDIT.render_html(cls.doc)
        cls.soup = BeautifulSoup(cls.html, 'html.parser')

    def test_audit_json_and_html_match_canonical_board(self):
        saved_json = json.loads((ROOT / 'data/5468b0ba/audit.json').read_text(encoding='utf-8'))
        saved_html = (ROOT / 'audits/5468b0ba/index.html').read_text(encoding='utf-8')
        self.assertEqual(saved_json['canonical_generated_utc'], self.doc['canonical_generated_utc'])
        self.assertEqual(len(saved_json['open_fixtures']), len(self.doc['open_fixtures']))
        self.assertEqual(saved_html, self.html)

    def test_every_audit_table_row_has_official_https_link(self):
        rows = self.soup.select('tbody tr')
        self.assertGreaterEqual(len(rows), 45)
        for tr in rows:
            links = tr.select('a[href^="https://"]')
            self.assertTrue(links, f"Missing https:// source link in row: {tr.get_text(' ', strip=True)}")

    def test_executive_summary_links_all_required_destinations_and_is_mobile_ready(self):
        self.assertIsNotNone(self.soup.select_one('meta[name="viewport"]'))
        summary = self.soup.select_one('#executive-summary')
        self.assertIsNotNone(summary)
        for href in (
            '../../picks-every-match/index.html',
            '../../picks-every-match/unresolved.html',
            '../../twc-2026/index.html',
            '../../flagged.html',
        ):
            link = summary.select_one(f'a[href="{href}"]')
            self.assertIsNotNone(link, f"Missing executive-summary link: {href}")
            target = (ROOT / 'audits/5468b0ba' / href).resolve()
            self.assertTrue(target.exists(), f"Broken relative target: {target}")

    def test_all_open_fixtures_math_and_blank_rules_verified(self):
        self.assertTrue(self.doc['verification_summary']['all_quotes_math_verified'])
        self.assertEqual(self.doc['verification_summary']['failures'], [])
        for r in self.doc['open_fixtures']:
            if r['evidence_tier'] == 'D':
                self.assertIsNone(r['prob_a'])
                self.assertIsNone(r['prob_b'])
                self.assertIsNone(r['pick_team'])
                self.assertIn('no_line_unverified', r['flags'])
            else:
                self.assertTrue(math.isfinite(r['prob_a']) and math.isfinite(r['prob_b']))
                self.assertAlmostEqual(r['prob_a'] + r['prob_b'], 1.0, places=4)
                if r['prob_a'] == r['prob_b']:
                    self.assertIsNone(r['pick_team'])
                    self.assertIn('equal_probability_no_edge', r['flags'])
                else:
                    expected = r['team_a'] if r['prob_a'] > r['prob_b'] else r['team_b']
                    self.assertEqual(r['pick_team'], expected)

    def test_twc_day3_both_deciders_priced_and_contrarian_rules_enforced(self):
        by_key = {r['key']: r for r in self.doc['twc_day3']}
        self.assertEqual(set(by_key.keys()), {'aurora-9z', 'legacy-betboom'})
        for key, r in by_key.items():
            self.assertIsNotNone(r['line'])
            self.assertEqual(r['line']['basis'], 'market')
            self.assertAlmostEqual(r['line']['prob_a'] + r['line']['prob_b'], 1.0, places=4)
            # HotSpawn ownership never equals or drives the market probability
            if r.get('ownership'):
                self.assertNotAlmostEqual(r['line']['prob_a'], r['ownership']['team_a'], places=2)

    def test_expired_unlisted_preview_row_preserves_not_a_hotspawn_pick_disclosure(self):
        data = json.loads((ROOT / 'data/69e4c06a/day3.json').read_text(encoding='utf-8'))
        row = next(r for r in data['day_three'] if r['key'] == 'legacy-betboom')
        row.update(listed_on_hotspawn=False, fixture_id='unlisted-legacy-betboom', line=None, quotes=[])
        rendered = TWC.render_index(data)
        soup = BeautifulSoup(rendered, 'html.parser')
        tr = soup.select_one('tr#legacy-betboom')
        self.assertIsNotNone(tr)
        # Ensure 'not a HotSpawn pick' appears outside <div data-live> so it remains visible when .expired hides [data-live]
        for live_div in tr.select('[data-live]'):
            live_div.decompose()
        self.assertIn('not a HotSpawn pick', tr.get_text(' ', strip=True))


if __name__ == '__main__':
    unittest.main()
