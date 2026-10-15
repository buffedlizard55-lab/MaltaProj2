"""69e4c06a: source clocks, explicit exchange rules, and market-gap-only admission."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


RULES = module('test_rule_kickoffs_69', 'scripts/69e4c06a/kalshi.py')
REFRESH = module('test_lobby_refresh_69', 'scripts/69e4c06a/refresh.py')


def synthetic_event():
    """Test-only synthetic contracts; never exported as factual source evidence."""
    ticker = 'KXCS2GAME-26OCT160600ALPBET'
    pair = 'Alpha vs. Beta'
    schedule = 'CS2 match originally scheduled for Oct 16, 2026 at 6:00 AM EDT'
    markets = []
    for name, bid, ask in [('Alpha', '0.55', '0.59'), ('Beta', '0.40', '0.44')]:
        markets.append({'status': 'active', 'market_type': 'binary', 'event_ticker': ticker,
                        'yes_sub_title': name, 'title': name + ' wins',
                        'rules_primary': f'If {name} wins the Test Cup: {pair} {schedule}, then the market resolves to Yes.',
                        'rules_secondary': f'The following market refers to the full match in the Test Cup: {pair} {schedule}',
                        'yes_bid_dollars': bid, 'yes_ask_dollars': ask,
                        'occurrence_datetime': '2026-10-16T14:00:00Z',
                        'volume_fp': '0.00', 'volume_24h_fp': '0.00'})
    return {'series_ticker': 'KXCS2GAME', 'event_ticker': ticker, 'mutually_exclusive': True,
            'product_metadata': {'competition': 'CS2', 'competition_scope': 'Game'},
            'title': pair, 'markets': markets}


def synthetic_capture():
    event = synthetic_event()
    observed = '2026-10-15T22:26:47Z'
    quote = {'source_key': 'kalshi', 'source_name': 'Kalshi (exchange)', 'api_url': RULES.KALSHI,
             'event_id': event['event_ticker'], 'team_a': 'Alpha', 'team_b': 'Beta',
             'raw_format': 'yes mid ($)', 'raw_a': 0.57, 'raw_b': 0.42,
             'start_utc': None, 'start_is_approx': True, 'live': False,
             'retrieved_utc': '2026-10-15T22:26:48Z'}
    payloads = {'sources': {RULES.KALSHI: {'http_status': 200, 'retrieved_utc': observed,
                                         'payload': {'events': [event]}}}}
    return quote, payloads


class PublicLobbyRevalidation(unittest.TestCase):
    def test_revalidation_retains_returned_clock_cache_hash_and_logical_source(self):
        calls = []
        original = {'at_utc': '2026-10-15T22:00:00Z', 'age_header': '8326', 'sha256': 'digest', 'status': 200}
        headers = {'Accept': 'text/html'}
        def fetch(*args):
            calls.append(args)
            return b'body', original
        body, meta = REFRESH.fetch_recent_lobby(fetch, REFRESH.LOBBY, headers, 60,
            now=datetime(2026, 10, 15, 22, 26, 36, tzinfo=timezone.utc))
        self.assertEqual(body, b'body')
        self.assertEqual(calls[0][0], REFRESH.LOBBY + '?cs2_refresh=20261015T222636Z')
        self.assertEqual(calls[0][1]['Cache-Control'], 'no-cache')
        self.assertEqual(calls[0][2], 60)
        for key in ('at_utc', 'age_header', 'sha256', 'status'):
            self.assertEqual(meta[key], original[key])
        self.assertEqual(meta['url'], REFRESH.LOBBY)
        self.assertEqual(meta['request_url'], calls[0][0])
        self.assertEqual(headers, {'Accept': 'text/html'})
        self.assertNotIn('request_url', original)

    def test_non_lobby_url_is_unchanged(self):
        calls = []
        def fetch(*args):
            calls.append(args)
            return b'other', {'status': 403}
        REFRESH.fetch_recent_lobby(fetch, 'https://example.test/api', {'Accept': 'application/json'}, 45)
        self.assertEqual(calls, [('https://example.test/api', {'Accept': 'application/json'}, 45)])


class ExplicitContractRules(unittest.TestCase):
    def test_explicit_edt_converts_to_utc_not_occurrence_or_ticker(self):
        event = synthetic_event()
        event['event_ticker'] = 'KXCS2GAME-UNKNOWN-TICKER'
        for market in event['markets']:
            market['event_ticker'] = event['event_ticker']
        evidence = RULES.rule_evidence(event)
        self.assertEqual(evidence['start_utc'], '2026-10-16T10:00:00Z')
        self.assertEqual(evidence['occurrence_datetime_not_used'], ['2026-10-16T14:00:00Z'] * 2)
        self.assertIn('not executable', evidence['limitation'])
        self.assertEqual(evidence['outcomes'][0]['volume_contracts_reported'], '0.00')

    def test_missing_rule_is_not_replaced_with_any_settlement_time(self):
        event = synthetic_event()
        event['markets'][1].pop('rules_primary')
        event['markets'][1]['close_time'] = '2026-10-16T10:00:00Z'
        self.assertIsNone(RULES.rule_evidence(event))

    def test_disagreeing_contract_schedules_fail_closed(self):
        event = synthetic_event()
        for key in ('rules_primary', 'rules_secondary'):
            event['markets'][1][key] = event['markets'][1][key].replace('6:00 AM', '7:00 AM')
        self.assertIsNone(RULES.rule_evidence(event))

    def test_timezone_must_be_explicit_and_dst_consistent(self):
        for bad in ('EST', 'CET', '', 'ET'):
            event = synthetic_event()
            for market in event['markets']:
                for key in ('rules_primary', 'rules_secondary'):
                    market[key] = market[key].replace('EDT', bad)
            with self.subTest(timezone=bad):
                self.assertIsNone(RULES.rule_evidence(event))

    def test_unknown_time_and_invalid_calendar_date_are_rejected(self):
        for bad in ('Feb 30, 2026', 'Oct 16, 26', 'Oct 16, 2026 at 99:00 AM EDT'):
            event = synthetic_event()
            for market in event['markets']:
                for key in ('rules_primary', 'rules_secondary'):
                    market[key] = market[key].replace('Oct 16, 2026', bad)
            self.assertIsNone(RULES.rule_evidence(event))

    def test_wrong_game_scope_pair_or_outcome_status_is_rejected(self):
        changes = [lambda e: e['product_metadata'].update(competition='LoL'),
                   lambda e: e['product_metadata'].update(competition_scope='Map'),
                   lambda e: e.update(mutually_exclusive=False),
                   lambda e: e.update(title='Alpha vs. Gamma'),
                   lambda e: e['markets'][0].update(status='settled'),
                   lambda e: e['markets'][0].update(market_type='scalar'),
                   lambda e: e['markets'][0].update(yes_sub_title='Gamma'),
                   lambda e: e['markets'].append(copy.deepcopy(e['markets'][0]))]
        for change in changes:
            event = synthetic_event()
            change(event)
            self.assertIsNone(RULES.rule_evidence(event))

    def test_missing_one_sided_crossed_nonfinite_and_wide_books_rejected(self):
        for bid, ask in [(None, '.59'), ('0', '.59'), ('.70', '.59'), ('.40', '.59'),
                         ('nan', '.59'), ('.55', 'inf'), ('.55', '1')]:
            event = synthetic_event()
            event['markets'][0].update(yes_bid_dollars=bid, yes_ask_dollars=ask)
            self.assertIsNone(RULES.rule_evidence(event))

    def test_enrichment_is_source_backed_idempotent_and_never_refreshes_clock(self):
        quote, payloads = synthetic_capture()
        first = RULES.enrich_quotes([quote], payloads)
        self.assertTrue(first[0]['fallback_only'])
        self.assertFalse(first[0]['start_is_approx'])
        self.assertEqual(first[0]['retrieved_utc'], payloads['sources'][RULES.KALSHI]['retrieved_utc'])
        self.assertEqual(RULES.enrich_quotes(first, payloads), first)
        self.assertIsNone(quote['start_utc'])
        self.assertNotIn('kickoff_evidence', quote)

    def test_changed_or_missing_payload_removes_previously_attached_extension(self):
        quote, payloads = synthetic_capture()
        enriched = RULES.enrich_quotes([quote], payloads)
        for bad in ({}, {'sources': {RULES.KALSHI: {'http_status': 403}}}):
            result = RULES.enrich_quotes(enriched, bad)[0]
            self.assertIsNone(result['start_utc'])
            self.assertTrue(result['start_is_approx'])
            self.assertNotIn('kickoff_evidence', result)
            self.assertNotIn('fallback_only', result)

    def test_raw_price_identity_and_duplicate_event_tampering_not_blessed(self):
        for field, value in [('raw_a', .99), ('team_a', 'Other'), ('live', True), ('api_url', 'https://example.test')]:
            quote, payloads = synthetic_capture()
            quote[field] = value
            self.assertNotIn('kickoff_evidence', RULES.enrich_quotes([quote], payloads)[0])
        quote, payloads = synthetic_capture()
        events = payloads['sources'][RULES.KALSHI]['payload']['events']
        events.append(copy.deepcopy(events[0]))
        self.assertNotIn('kickoff_evidence', RULES.enrich_quotes([quote], payloads)[0])


class CanonicalGapAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_c64a5e19 import B
        cls.B = B
        cls.snapshot = json.loads((ROOT / 'data/c64a5e19/snapshot.json').read_text())
        payloads = json.loads((ROOT / 'data/c64a5e19/source_payloads.json').read_text())
        cls.snapshot['quotes'] = RULES.enrich_quotes(cls.snapshot['quotes'], payloads)
        cls.board = B.build_board(cls.snapshot, 'test')

    def test_existing_accepted_market_estimates_remain_identical(self):
        inputs = copy.deepcopy(self.snapshot)
        inputs['quotes'] = [q for q in inputs['quotes'] if not q.get('fallback_only')]
        primary = self.B.ENGINE.build_board(inputs, {}, {}, {})
        changed = {r['fixture_id']: r for r in self.board['open']}
        for old in primary['open']:
            if old['market']:
                current = changed[old['fixture_id']]
                for key in ('prob_a', 'prob_b', 'pick_team', 'pick_prob'):
                    self.assertEqual(current['line'][key], old['line'][key])
                self.assertNotIn('market_gap_resolution', current)

    def test_rule_backed_fallback_requires_retained_proof_and_gap_history(self):
        for row in self.board['open']:
            if row.get('market_gap_resolution'):
                self.assertIsNone(row['research'])
                self.assertTrue(row['gap_research']['steps'])
                self.assertEqual(row['gap_research']['steps'][0]['label'], '1 · HLTV research')
                self.assertIn('exchange_midpoints_not_executable_bookmaker_odds', row['flags'])
                for quote in row['quotes']:
                    self.assertEqual(quote['kickoff_evidence']['start_utc'], quote['start_utc_at_source'])
                    self.assertLessEqual(quote['start_diff_h'], 5 / 60)

    def test_expired_capture_cannot_be_revived_by_the_rule_extension(self):
        later = self.B.core.parse_iso(self.snapshot['collected_to_utc']) + timedelta(hours=5)
        board = self.B.build_board(self.snapshot, 'test', later)
        self.assertTrue(all(r['line'] is None for r in board['open']))
        self.assertEqual(board['collected_to_utc'], self.snapshot['collected_to_utc'])

    def test_no_roster_alias_or_duplicate_rating_is_inferred(self):
        for row in self.board['open']:
            if not row.get('market') and (row['team_a'] == 'ex-RUSTEC' or 'WROTBERRY' in (row['team_a'], row['team_b'])):
                self.assertIsNone(row['line'])
            if 'RoundsGG' in (row['team_a'], row['team_b']):
                side = 'team_a' if row['team_a'] == 'RoundsGG' else 'team_b'
                self.assertIsNone(row['vrs'][side])

    def test_extended_offline_replay_reconstructs_rules_and_detects_tampering(self):
        verifier = module('test_extended_replay_69', 'scripts/ae75c5c3/verify_source_payloads.py')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'source_payloads.json').write_text((ROOT / 'data/c64a5e19/source_payloads.json').read_text())
            (directory / 'board.json').write_text(json.dumps(self.board))
            result = verifier.verify(directory, quote_normalizer=RULES.enrich_quotes)
            self.assertFalse(result['failures'], result['failures'])
            tampered = copy.deepcopy(self.board)
            proof_quotes = [q for r in tampered['open'] for q in r['quotes'] if q.get('kickoff_evidence')]
            if not proof_quotes:
                self.skipTest('No rule-backed open fixtures in this independently timed capture')
            proof_quotes[0]['kickoff_evidence']['start_utc'] = '2099-01-01T00:00:00Z'
            (directory / 'board.json').write_text(json.dumps(tampered))
            result = verifier.verify(directory, quote_normalizer=RULES.enrich_quotes)
            self.assertTrue(any('rule evidence differs' in f for f in result['failures']))


if __name__ == '__main__':
    unittest.main()
