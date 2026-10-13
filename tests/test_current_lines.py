"""Behavior tests, not assertions that a stored 'verified' label is true."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_lines import build_document, iso, MAX_AGE_SECONDS, parse_iso
from collect_odds import ms_iso, aligned_bovada_outcomes, collect_bovada
from build_site import fixture_row, table
from unittest.mock import patch

NOW = datetime(2026, 10, 13, 21, 0, tzinfo=timezone.utc)


def fixture(fid='1', **changes):
    f = {'fixture_id': fid, 'sport': 'cs2', 'team_a': 'Alpha', 'team_b': 'Beta',
         'status': 'scheduled', 'scheduled_start_time': iso(NOW + timedelta(hours=12)),
         'lock_time': iso(NOW + timedelta(hours=11)), 'tier': 's',
         'competition_name': 'Example CS2', 'source': {'hotspawn_match_url': 'https://play.hotspawn.com/lobby'}}
    f.update(changes)
    return f


def quote(**changes):
    q = {'source_key': 'bovada', 'source_name': 'Bovada', 'source_kind': 'bookmaker', 'sport': 'cs2',
         'source_api_url': 'https://www.bovada.lv/services/sports/event/v2/events/A/description/esports',
         'source_event_id': 'test-only', 'team_a_name': 'Alpha', 'team_b_name': 'Beta',
         'start_time_utc': iso(NOW + timedelta(hours=12)), 'retrieved_at_utc': iso(NOW),
         'market_type': 'match winner (moneyline, full match)', 'market_status': 'O',
         'market_is_live': False, 'outcome_alignment_verified': True,
         'decimal_odds_a': 2.0, 'decimal_odds_b': 3.0}
    q.update(changes)
    return q


class CurrentLinesTests(unittest.TestCase):
    def build(self, fixtures=None, quotes=None, fixture_time=None):
        return build_document({'generated_at_utc': fixture_time or iso(NOW), 'matches': fixtures or [fixture()]},
                              {'generated_at_utc': iso(NOW), 'lines': quotes if quotes is not None else [quote()]}, NOW)

    def test_math_and_reversed_pair(self):
        d, _ = self.build()
        c = d['fixtures'][0]['derived']['consensus']
        self.assertAlmostEqual(c['derived_probability_a_mean'], .6)
        self.assertAlmostEqual(c['derived_probability_b_mean'], .4)
        d, _ = self.build(quotes=[quote(team_a_name='Beta', team_b_name='Alpha')])
        self.assertAlmostEqual(d['fixtures'][0]['derived']['consensus']['derived_probability_a_mean'], .4)
        self.assertEqual(d['fixtures'][0]['bookmaker_lines'][0]['decimal_odds_a'], 3)

    def test_eligibility_rejects_missing_or_unsafe_fields(self):
        for changes in [
            {'retrieved_at_utc': iso(NOW - timedelta(seconds=MAX_AGE_SECONDS + 1))},
            {'retrieved_at_utc': iso(NOW + timedelta(seconds=1))},
            {'retrieved_at_utc': None}, {'retrieved_at_utc': '2026-10-13T21:00:00'},
            {'sport': 'lol'}, {'sport': None}, {'market_is_live': True}, {'market_is_live': None},
            {'market_status': 'S'}, {'market_status': None}, {'market_type': 'map 1 winner'},
            {'outcome_alignment_verified': False}, {'start_time_utc': None},
            {'start_time_utc': iso(NOW + timedelta(hours=12, minutes=1))},
            {'source_api_url': 'https://www.bovada.lv.evil.example/quote'},
            {'source_api_url': 'http://www.bovada.lv/quote'}, {'source_key': 'hotspawn'},
        ]:
            with self.subTest(changes=changes):
                d, e = self.build(quotes=[quote(**changes)])
                self.assertIsNone(d['fixtures'][0]['derived']['consensus'])
                self.assertTrue(e['rejected_candidates'])

    def test_nonfinite_or_invalid_prices_fail_closed(self):
        for price in [None, True, False, 0, 1, -100, '2.0', float('nan'), float('inf')]:
            with self.subTest(price=price):
                d, _ = self.build(quotes=[quote(decimal_odds_a=price)])
                self.assertIsNone(d['fixtures'][0]['derived']['consensus'])
                json.dumps(d, allow_nan=False)

    def test_old_snapshot_locked_started_and_missing_lock(self):
        d, _ = self.build(fixture_time=iso(NOW - timedelta(hours=5)))
        self.assertIsNone(d['fixtures'][0]['derived']['consensus'])
        for changes in [{'lock_time': iso(NOW)}, {'lock_time': None}, {'status': 'started'},
                        {'scheduled_start_time': iso(NOW)}]:
            d, _ = self.build(fixtures=[fixture(**changes)])
            self.assertIsNone(d['fixtures'][0]['derived']['consensus'])

    def test_ambiguous_fixture_join_is_order_independent(self):
        for fixtures in [[fixture('1'), fixture('2')], [fixture('2'), fixture('1')]]:
            d, e = self.build(fixtures=fixtures)
            self.assertEqual(d['summary']['fixtures_with_external_line'], 0)
            self.assertTrue(all('ambiguous_fixture_join' in f['review_flags'] for f in d['fixtures']))
            self.assertEqual(len(e['rejected_candidates']), 2)

    def test_ambiguous_source_quotes_not_first_quote_wins(self):
        d, _ = self.build(quotes=[quote(), quote(decimal_odds_a=4)])
        self.assertEqual(d['summary']['fixtures_with_external_line'], 0)
        self.assertIn('ambiguous_source_quotes', d['fixtures'][0]['review_flags'])

    def test_crowd_percentages_do_not_influence_model(self):
        a, _ = self.build(fixtures=[fixture(team_a_pick_pct=99, team_b_pick_pct=1)])
        b, _ = self.build(fixtures=[fixture(team_a_pick_pct=1, team_b_pick_pct=99)])
        self.assertEqual(a, b)
        self.assertNotIn('pick_pct', json.dumps(a))

    def test_no_quotes_and_cancelled_or_ended_fixtures(self):
        d, _ = self.build(fixtures=[fixture('1'), fixture('2', status='cancelled'), fixture('3', status='ended')], quotes=[])
        self.assertEqual(len(d['fixtures']), 1)
        self.assertIsNone(d['fixtures'][0]['derived']['consensus'])

    def test_timestamp_formats(self):
        self.assertEqual(ms_iso('2026-10-14T09:30:00+02:00'), '2026-10-14T07:30:00Z')
        self.assertEqual(ms_iso(int(NOW.timestamp() * 1000)), iso(NOW))
        self.assertIsNone(ms_iso('2026-10-13T21:00:00'))
        self.assertIsNone(parse_iso('2026-10-13T21:00:00'))
        self.assertIsNone(ms_iso(None))

    def test_bovada_actual_sample_aligns_by_competitor_id(self):
        # Verbatim preserved source sample, not a guess at provider field names.
        sample = json.loads((ROOT / 'evidence/raw_samples/raw_samples.json').read_text())['bovada_event_sample']
        comps = sample['competitors']
        market = sample['displayGroups'][0]['markets'][0]
        expected = [str(c['id']) for c in comps]
        result = aligned_bovada_outcomes(comps, list(reversed(market['outcomes'])))
        self.assertEqual([str(o['competitorId']) for o in result], expected)
        self.assertIsNone(aligned_bovada_outcomes(comps, [market['outcomes'][0]] * 2))
        self.assertIsNone(aligned_bovada_outcomes(comps, [{}, {}]))
        ev = copy.deepcopy(sample)
        ev['link'] = '/sports/esports/counter-strike/test'
        ev['displayGroups'][0]['markets'] = [copy.deepcopy(market)]
        ev['displayGroups'][0]['markets'][0]['outcomes'].reverse()
        with patch('collect_odds.get_json', return_value=(200, [{'events': [ev]}])):
            lines, evidence = [], {}
            collect_bovada(lines, evidence)
        self.assertEqual(lines[0]['decimal_odds_a'], float(market['outcomes'][0]['price']['decimal']))
        self.assertTrue(lines[0]['outcome_alignment_verified'])
        self.assertTrue(evidence['quote_payloads'])

    def test_mobile_pick_and_source_links(self):
        d, _ = self.build()
        row = fixture_row(d['fixtures'][0])
        html = table(['Time', 'Tier', 'Event', 'Match', 'Odds', 'Probability', 'Status', 'Fixture', 'Flags'], [row], classes='sortable')
        self.assertIn('Pick: Alpha', html)
        self.assertIn('data-label="Probability"', html)
        self.assertIn('https://www.bovada.lv/', html)
        self.assertIn('https://play.hotspawn.com/lobby', html)

    def test_current_published_rows_have_official_source_and_no_third_party_probability(self):
        # Validate the actual current data batch whenever a collector refresh has rendered it.
        path = ROOT / 'data/current_probabilities.json'
        if not path.exists():
            return
        d = json.loads(path.read_text())
        for row in d['rows']:
            self.assertIn(urlsplit(row['official_source_url']).hostname, {'www.hotspawn.com', 'play.hotspawn.com', 'phpstack-1372681-6459848.cloudwaysapps.com'})
            if row['probability_a'] is not None:
                self.assertTrue(row['sources'])
                self.assertAlmostEqual(row['probability_a'] + row['probability_b'], 1)
                self.assertTrue(all(s['source'] in {'Pinnacle', 'Bovada'} for s in row['sources']))
            else:
                self.assertIsNone(row['probability_b'])

    def test_primary_quote_payloads_reproduce_current_numeric_lines(self):
        evidence = json.loads((ROOT / 'evidence/odds_collection.json').read_text())
        payloads = evidence.get('quote_payloads', [])
        doc = json.loads((ROOT / 'data/lines.json').read_text())
        for fixture in doc['fixtures']:
            for line in fixture['bookmaker_lines']:
                candidates = [p for p in payloads if p['source'] == line['source_key'] and
                              p['retrieved_at_utc'] == line['retrieved_at_utc'] and
                              p['url'] == line['source_api_url'] and
                              str((p.get('matchup') or {}).get('id') if p['source'] == 'pinnacle' else p.get('event_id')) == line['source_event_id']]
                self.assertEqual(len(candidates), 1, (fixture['fixture_id'], line['source_key']))
                payload = candidates[0]
                if line['source_key'] == 'pinnacle':
                    matchup, market = payload['matchup'], payload['market']
                    self.assertEqual(str(matchup['id']), line['source_event_id'])
                    self.assertEqual(market['type'], 'moneyline')
                    self.assertEqual(market['period'], 0)
                    self.assertFalse(market['isAlternate'])
                    self.assertEqual(parse_iso(matchup['startTime']), parse_iso(fixture['start_time_utc']))
                    prices = {p['designation']: p['price'] for p in market['prices']}
                    raw = [prices[p['alignment']] for p in matchup['participants']]
                    decimals = [round(1 + 100 / abs(x) if x < 0 else 1 + x / 100, 4) for x in raw]
                else:
                    self.assertEqual(str(payload['event_id']), line['source_event_id'])
                    outcomes = aligned_bovada_outcomes(payload['competitors'], payload['market']['outcomes'])
                    self.assertIsNotNone(outcomes)
                    decimals = [float(o['price']['decimal']) for o in outcomes]
                    self.assertEqual(ms_iso(payload['startTime']), fixture['start_time_utc'])
                if line['order_as_quoted'] == 'reversed':
                    decimals.reverse()
                self.assertEqual(decimals, [line['decimal_odds_a'], line['decimal_odds_b']])
                shares = [1 / d for d in decimals]
                self.assertEqual(round(shares[0] / sum(shares), 4), line['derived_probability_a'])

    def test_every_current_generator_table_row_has_a_source_link(self):
        from bs4 import BeautifulSoup
        for path in ROOT.glob('*.html'):
            # These preserved independent models are explicitly flagged, outside this generator's scope.
            if path.name in {'lines.html', 'teams.html', 'hotspawn.html'}:
                continue
            soup = BeautifulSoup(path.read_text(), 'html.parser')
            for row in soup.select('tbody tr'):
                self.assertTrue(row.select('a[href^="https://"]'), (path.name, row.get_text()[:100]))


if __name__ == '__main__':
    unittest.main()
