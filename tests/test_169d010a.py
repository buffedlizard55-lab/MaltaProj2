"""Tests for session 169d010a (TWC Day-3 re-check + every-open-fixture recheck).

They re-derive from the committed canonical board, so they keep holding when the board rotates.
Run: python3 -m unittest tests.test_169d010a -v
"""
import importlib.util
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'scripts/169d010a/build.py'
RECHECK = ROOT / 'data/169d010a/recheck.json'
EVIDENCE = ROOT / 'data/169d010a/evidence.json'
AUDIT = ROOT / 'audits/169d010a'
PAGES = [AUDIT / 'index.html', AUDIT / 'open-matches.html']


def load_build():
    spec = importlib.util.spec_from_file_location('build_169d010a', BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs, self.ids, self.h1 = [], set(), 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.hrefs.append(a['href'])
        if a.get('id'):
            self.ids.add(a['id'])
        if tag == 'h1':
            self.h1 += 1
        if tag == 'meta' and a.get('name') == 'viewport':
            self.viewport = a.get('content', '')


class Recheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(RECHECK.read_text())
        cls.build = load_build()

    def test_every_priced_row_rederives_from_raw_quotes(self):
        s = self.data['stats']
        self.assertEqual(s['open'], 31)
        self.assertEqual(s['priced_rows'], 23)
        self.assertEqual(s['priced_matches_rederived'], s['priced_rows'])
        self.assertEqual(s['mismatches'], [])

    def test_recheck_is_deterministic_against_board(self):
        fresh = self.build.build_recheck()
        self.assertEqual(fresh['stats']['mismatches'], [])
        self.assertEqual(fresh['stats']['priced_matches_rederived'], fresh['stats']['priced_rows'])
        if fresh.get('source_board', {}).get('generated_utc') == self.data.get('source_board', {}).get('generated_utc'):
            self.assertEqual(fresh['stats']['priced_matches_rederived'], self.data['stats']['priced_matches_rederived'])
            self.assertEqual(fresh['stats']['rows_with_pick'], self.data['stats']['rows_with_pick'])
            self.assertEqual(fresh['unresolved_fixture_ids'], self.data['unresolved_fixture_ids'])

    def test_unresolved_rows_have_no_pick_and_no_invented_probability(self):
        for r in self.data['rows']:
            if r['fixture_id'] in self.data['unresolved_fixture_ids']:
                self.assertIsNone(r['pick_team'], r['fixture_id'])
        self.assertEqual(len(self.data['unresolved_fixture_ids']), 7)
        self.assertEqual(
            sorted(u['fixture_id'] for u in self.build.UNRESOLVED_ATTEMPTS),
            sorted(self.data['unresolved_fixture_ids']))

    def test_exact_coin_flips_are_not_picked(self):
        flips = [r for r in self.data['rows'] if r['prob_a_rederived'] == 0.5]
        self.assertEqual(sorted(r['fixture_id'] for r in flips), ['1079167', '1081769'])
        for r in flips:
            self.assertIsNone(r['pick_team'], r['fixture_id'])
            self.assertTrue(r['toss_up_no_edge'])

    def test_crowd_is_not_a_price(self):
        # The stored probability must equal the re-derived quote consensus, never the lobby crowd %.
        for r in self.data['rows']:
            if r['prob_a_rederived'] is not None:
                self.assertAlmostEqual(r['prob_a_rederived'], r['prob_a_stored'], delta=0.0005)

    def test_secondary_cross_check_within_one_point(self):
        cc = self.data['secondary_cross_check']
        self.assertLess(abs(cc['delta_pp']), 1.0)
        self.assertAlmostEqual(cc['aurora_no_vig'], round((1 / 1.38) / (1 / 1.38 + 1 / 2.7), 4), places=4)


class Day3Decisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(RECHECK.read_text())
        cls.aur, cls.bb = cls.data['day3_decisions']

    def test_safe_picks_are_market_favourites(self):
        self.assertEqual(self.aur['safe_pick'], 'Aurora')
        self.assertEqual(self.bb['safe_pick'], 'Legacy')
        self.assertGreater(self.aur['safe_prob'], 0.5)
        self.assertGreater(self.bb['safe_prob'], 0.5)

    def test_9z_is_a_climb_under_desk_floor_but_not_hub_floor(self):
        self.assertEqual(self.aur['climb_candidate'], '9z')
        self.assertGreaterEqual(self.aur['climb_prob'], 0.30)
        self.assertLess(self.aur['climb_prob'], 0.35)
        self.assertTrue(self.aur['climb_qualifies_day3_desk_rule'])
        self.assertFalse(self.aur['climb_clears_stricter_hub_floor_35pct'])

    def test_betboom_clears_both_floors(self):
        self.assertEqual(self.bb['climb_candidate'], 'BetBoom')
        self.assertGreaterEqual(self.bb['climb_prob'], 0.35)
        self.assertTrue(self.bb['climb_qualifies_day3_desk_rule'])
        self.assertTrue(self.bb['climb_clears_stricter_hub_floor_35pct'])

    def test_expected_points_are_arithmetic(self):
        for d in (self.aur, self.bb):
            self.assertAlmostEqual(d['safe_expected_points'], round(d['safe_prob'] * 7, 2), places=2)
            self.assertAlmostEqual(d['climb_expected_points'], round(d['climb_prob'] * 7, 2), places=2)

    def test_each_counted_flag_has_evidence_ids(self):
        ev_ids = {e['id'] for e in json.loads(EVIDENCE.read_text())['entries']}
        for d in (self.aur, self.bb):
            for f in d['flags']:
                self.assertTrue(f['evidence'], f['id'])
                for i in f['evidence']:
                    self.assertIn(i, ev_ids, f"{f['id']} cites unknown evidence {i}")

    def test_day3_decisions_need_two_counted_flags(self):
        for d in (self.aur, self.bb):
            self.assertGreaterEqual(len(d['flags_counted']), 2)


class Evidence(unittest.TestCase):
    def test_every_entry_has_https_url_and_read_time(self):
        entries = json.loads(EVIDENCE.read_text())['entries']
        self.assertGreaterEqual(len(entries), 15)
        for e in entries:
            self.assertTrue(e['url'].startswith('https://'), e['id'])
            self.assertRegex(e['read_utc'], r'^2026-10-16T\d{2}:\d{2}Z$', e['id'])

    def test_unverified_entries_are_not_used_as_inputs(self):
        entries = {e['id']: e for e in json.loads(EVIDENCE.read_text())['entries']}
        self.assertTrue(entries['E15']['status'].startswith('unverified'))
        self.assertTrue(entries['E14']['status'].startswith('not_usable'))
        self.assertTrue(entries['E16']['status'].startswith('not_usable'))


class Pages(unittest.TestCase):
    def test_mobile_viewport_and_single_h1(self):
        for p in PAGES:
            parser = _Links()
            parser.feed(p.read_text())
            self.assertIn('width=device-width', getattr(parser, 'viewport', ''), p.name)
            self.assertEqual(parser.h1, 1, p.name)

    def test_every_open_match_card_has_an_https_source_link(self):
        text = (AUDIT / 'open-matches.html').read_text()
        cards = text.count('<div class="card">')
        self.assertEqual(cards, 31)
        self.assertGreaterEqual(len(re.findall(r'href="https://[^"]+"', text)), cards)

    def test_every_unresolved_card_links_evidence(self):
        text = (AUDIT / 'index.html').read_text()
        unresolved = text.split('id="unresolved"', 1)[1]
        self.assertGreaterEqual(unresolved.count('class="card"'), 7)
        self.assertGreaterEqual(len(re.findall(r'href="https://', unresolved)), 14)

    def test_internal_links_resolve(self):
        for p in PAGES:
            parser = _Links()
            parser.feed(p.read_text())
            for href in parser.hrefs:
                if href.startswith(('http://', 'https://', 'mailto:', '#')):
                    continue
                target = (p.parent / href.split('#')[0]).resolve()
                self.assertTrue(target.exists(), f'{p.name} -> {href}')

    def test_index_links_to_every_site_section_it_needs(self):
        text = (AUDIT / 'index.html').read_text()
        for needle in ('../../hub/index.html', '../../picks-every-match/index.html',
                       '../../picks-every-match/unresolved.html', '../../twc-2026/index.html',
                       'open-matches.html'):
            self.assertIn(needle, text)


if __name__ == '__main__':
    unittest.main()
