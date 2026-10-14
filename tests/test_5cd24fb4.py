"""Executive summary must distinguish verified coverage from provisional research."""
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('landing_5cd', ROOT / 'scripts/build_site.py')
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class LandingEvidenceTests(TestCase):
    def render(self, lines, research=None):
        def load(path, default=None):
            return {'data/lines.json': lines, 'data/c64a5e19/board.json': research or {}}.get(path, {})
        with patch.object(site, 'load', side_effect=load):
            return site.executive_summary_html()

    def test_missing_data_is_not_zero_coverage(self):
        self.assertIn('coverage is unverified, not zero', self.render({}))

    def test_unresolved_rows_are_blank_and_source_linked(self):
        row = dict(fixture_id='1', team_a='A<script>', team_b='B', pick_status='open', bookmaker_lines=[])
        result = self.render({'fixtures': [row]})
        self.assertIn('0 of 1', result)
        self.assertIn('A&lt;script&gt;', result)
        self.assertIn('https://play.hotspawn.com/lobby', result)
        self.assertIn('Verified probability', result)
        self.assertNotIn('50.0%', result)

    def test_fallback_does_not_fill_strict_probability(self):
        row = dict(fixture_id='1', team_a='A', team_b='B', pick_status='open')
        research = {'open': [dict(fixture_id='1', flags=['fallback_originated_sibling_vrs_range_unverified_roster'], line={'prob_a': .7637})]}
        result = self.render({'fixtures': [row]}, research)
        self.assertIn('does not verify LFO 10', result)
        self.assertNotIn('76.37', result)
        self.assertNotIn('0.7637', result)

    def test_featured_and_closed_rows_not_listed_as_gaps(self):
        rows = [dict(pick_status='open', bookmaker_lines=[{}], team_a='Priced'),
                dict(pick_status='closed', team_a='Closed')]
        result = self.render({'fixtures': rows})
        self.assertIn('1 of 1', result)
        self.assertNotIn('data-label="Match"', result)

    def test_research_and_quote_age_limitations_visible(self):
        result = self.render({'fixtures': []})
        for phrase in ['Start here: source-linked CS2 picks', 'Unresolved picks &amp; limitations',
                       'Board build times are not quote', 'different evidence standards',
                       'audits/5cd24fb4/index.html']:
            self.assertIn(phrase, result)

    def test_unsafe_fixture_url_falls_back_to_official_lobby(self):
        result = self.render({'fixtures': [dict(pick_status='open', hotspawn_match_url='javascript:alert(1)')]})
        self.assertNotIn('javascript:', result)
