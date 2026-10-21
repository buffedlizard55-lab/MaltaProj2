"""Missing rankings never justify strength bounds; market selections are unchanged."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('safety_00231608', ROOT / 'scripts/5f903db4/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class MissingEvidence(unittest.TestCase):
    def test_either_missing_rating_is_unresolved_even_with_a_floor(self):
        rated = {'listed': True, 'points': 1500, 'alternatives': []}
        absent = {'listed': False}
        for a, b in ((rated, absent), (absent, rated), (absent, absent)):
            for floor in (None, {'standing': 380, 'points': 381}):
                with self.subTest(a=a, b=b, floor=floor):
                    row = build.originate(a, b, floor)
                    self.assertEqual(row['basis'], 'unresolved')
                    self.assertIsNone(row['prob_a'])
                    self.assertIsNone(row['prob_b'])
                    self.assertIsNone(row['bound'])
                    self.assertTrue(row['reason'])

    def test_two_rated_teams_still_have_reproducible_model(self):
        a = {'listed': True, 'points': 1500, 'alternatives': []}
        b = {'listed': True, 'points': 1400, 'alternatives': []}
        result = build.originate(a, b, None)
        self.assertEqual(result['basis'], 'originated_vrs')
        self.assertAlmostEqual(result['prob_a'], build.core.vrs_prob(1500, 1400))
        self.assertAlmostEqual(result['prob_a'] + result['prob_b'], 1)

    def test_all_unresolved_fixtures_are_published_with_sources(self):
        board = json.loads((ROOT / 'data/5f903db4/board.json').read_text())
        page = (ROOT / 'everypick/unresolved.html').read_text()
        self.assertEqual(board['summary']['originated_bound'], 0)
        for row in board['rows']:
            if row['resolution']['basis'] == 'unresolved':
                self.assertIsNone(row['pick'])
                self.assertIn(f'unresolved-{row["fixture_id"]}', page)
                self.assertTrue(row['sources'])
        self.assertIn('R7', (ROOT / 'everypick/flagged.html').read_text())

    def test_market_consensus_unchanged_from_raw_quotes(self):
        board = build.build()
        for row in board['rows']:
            if row['resolution']['basis'] == 'market':
                mean = sum(q['prob_a'] for q in row['quotes']) / len(row['quotes'])
                self.assertAlmostEqual(row['resolution']['prob_a'], mean)


class LiveFallbackQuotes(unittest.TestCase):
    def test_own_collector_kalshi_and_melbet_are_not_filtered_as_secondary(self):
        baseline = build.build()
        fixture = next(r for r in baseline['rows'] if r['resolution']['basis'] == 'unresolved')
        fid = fixture['fixture_id']
        real_load = build.core.load
        for source in ('kalshi', 'melbet'):
            quote = {'fixture_id': fid, 'source_key': source, 'source_name': source,
                     'team_a': fixture['team_a'], 'team_b': fixture['team_b'],
                     'decimal_a': 2.0, 'decimal_b': 2.0, 'event_id': 'synthetic-live-test',
                     'start_utc': fixture['start_utc'], 'declared_order': 'ab',
                     'retrieved_utc': build.now_utc(),
                     'api_url': 'https://example.invalid/synthetic-test-only'}
            def load(path, default=None):
                if path == build.LIVE:
                    return {'quotes': [quote]}
                return real_load(path, default)
            with self.subTest(source=source), patch.object(build.core, 'load', side_effect=load):
                row = next(r for r in build.build()['rows'] if r['fixture_id'] == fid)
                self.assertEqual(row['resolution']['basis'], 'market')
                self.assertEqual(row['resolution']['prob_a'], 0.5)
                self.assertIn('synthetic-live-test', [q['event_id'] for q in row['quotes']])


class QuoteExpiry(unittest.TestCase):
    def test_eight_hour_boundary_and_invalid_dates(self):
        from datetime import datetime, timezone
        ref = datetime(2026, 10, 21, 20, tzinfo=timezone.utc)
        for seen, expected in [('2026-10-21T12:00:00Z', True),
                               ('2026-10-21T11:59:59Z', False),
                               ('2026-10-21T20:00:01Z', False),
                               ('2026-10-21T19:00:00', False),
                               ('bad', False), (None, False)]:
            with self.subTest(seen=seen):
                self.assertEqual(build.quote_is_fresh({'retrieved_utc': seen}, ref), expected)

    def test_primary_source_timestamp_schema_is_preserved(self):
        fixture = {'team_a': 'A', 'team_b': 'B', 'start_utc': '2026-10-22T05:00:00Z'}
        quote = {'decimal_a': 2.0, 'decimal_b': 2.0,
                 'retrieved_utc': build.now_utc(),
                 'start_utc_at_source': '2026-10-22T05:00:00Z'}
        record = build.quote_record(fixture, quote, 'synthetic primary-schema test')
        self.assertIsNotNone(record)
        self.assertEqual(record['start_diff_minutes'], 0.0)
        quote['start_utc_at_source'] = '2026-10-23T05:00:00Z'
        self.assertIsNone(build.quote_record(fixture, quote, 'synthetic mismatch test'))
