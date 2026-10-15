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


TWC = module('test_twc_category_69', 'scripts/69e4c06a/build.py')


class ThinBookReporting(unittest.TestCase):
    def test_same_pair_rejection_is_explicit_in_the_fallback_ladder(self):
        from tests.test_c64a5e19 import B
        row = {'team_a': 'Alpha', 'team_b': 'Beta', 'market': None, 'line': None, 'flags': ['no_line_unverified']}
        snap = {'access_log': {}, 'quotes': [], 'vrs': {}, 'rejected_quotes': [
            {'source_key': 'kalshi', 'team_a': 'Alpha', 'team_b': 'Beta', 'reason': 'thin or one-sided order book'}]}
        review = B.fallback_review(row, snap, B.core)
        kalshi = [step for step in review['steps'] if step['label'] == '2 · Kalshi exchange'][0]
        self.assertEqual(kalshi['rejected_candidate_count'], 1)
        self.assertIn('thin or one-sided order book', kalshi['result'])


class DatedResearchAndDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads((ROOT / 'data/c64a5e19/board.json').read_text())
        cls.evaluated = TWC.core.parse_iso(cls.canonical['generated_utc'])
        cls.data = TWC.derive(ROOT, cls.evaluated)

    def test_all_eight_results_maps_and_primary_publisher_links_are_consistent(self):
        from urllib.parse import urlsplit
        results = self.data['facts']['results']
        self.assertEqual([sum(r['day'] == day for r in results) for day in (1, 2)], [4, 4])
        for result in results:
            self.assertEqual(urlsplit(result['official_publisher_url']).hostname, 'www.hotspawn.com')
            self.assertEqual(urlsplit(result['specialist_url']).hostname, 'www.hltv.org')
            self.assertEqual(sum(m['score_a'] > m['score_b'] for m in result['maps']), result['series_a'])
            self.assertEqual(sum(m['score_b'] > m['score_a'] for m in result['maps']), result['series_b'])
            self.assertTrue(all(m['score_a'] != m['score_b'] for m in result['maps']))
        aurora = [r for r in results if r['day'] == 2 and r['team_a'] == 'Aurora'][0]
        self.assertEqual([(m['name'], m['score_a'], m['score_b']) for m in aurora['maps']], [('Cache', 13, 9), ('Dust2', 13, 7)])
        nine_z = [r for r in results if r['day'] == 2 and r['team_a'] == '9z'][0]
        self.assertEqual((nine_z['series_a'], nine_z['series_b']), (1, 2))
        self.assertEqual([(m['name'], m['score_a'], m['score_b']) for m in nine_z['maps']], [('Nuke', 9, 13), ('Mirage', 13, 8), ('Dust2', 9, 13)])

    def test_primary_july_announcements_do_not_become_causal_rest_values(self):
        announcements = self.data['roster_announcements']
        self.assertEqual(len(announcements), 3)
        self.assertEqual(sorted(a['calendar_days_before_day_one'] for a in announcements), [98, 103, 103])
        self.assertTrue(all(a['primary_url'].startswith('https://x.com/AuroraCS2_GG/status/') for a in announcements))
        self.assertTrue(all(a['announcement_utc'].startswith('2026-07-') for a in announcements))
        self.assertTrue(all(u['value'] is None and u['reason'] for u in self.data['facts']['unknowns']))
        self.assertIsNone(self.data['facts']['source_observation_utc'])

    def test_listed_probabilities_are_copied_exactly_in_canonical_order(self):
        indexed = {r['fixture_id']: r for r in self.canonical['open']}
        for row in self.data['day_three']:
            if not row['listed_on_hotspawn']:
                continue
            source = indexed[row['fixture_id']]
            self.assertEqual([row['team_a'], row['team_b']], [source['team_a'], source['team_b']])
            if row['line']:
                for key in ('prob_a', 'prob_b', 'pick_team'):
                    self.assertEqual(row['line'][key], source['line'][key])
            self.assertEqual(row['offered_points'], source['points'])
            self.assertEqual(row['valid_until_utc'], source['valid_until_utc'])

    def test_unlisted_preview_cannot_invent_a_hotspawn_fixture_ownership_or_points(self):
        for row in self.data['day_three']:
            if row['listed_on_hotspawn']:
                continue
            for key in ('fixture_id', 'ownership', 'offered_points', 'lock_utc'):
                self.assertIsNone(row[key])
            self.assertFalse(row['decision']['qualified'])
            self.assertIsNone(row['decision']['pick_team'])
            if row['line']:
                self.assertAlmostEqual(row['line']['prob_a'] + row['line']['prob_b'], 1, places=5)
                self.assertTrue(all(q['source_key'] in ('pinnacle', 'bovada', 'melbet') for q in row['quotes']))

    def test_raw_quote_labels_preserve_provider_outcome_order(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(TWC.render_index(self.data), 'html.parser')
        for row in self.data['day_three']:
            text = soup.select_one('#' + row['key']).get_text()
            for quote in row['quotes']:
                names = quote.get('names_at_source') or [quote['team_a'], quote['team_b']]
                self.assertIn(f"{names[0]}: {quote['raw_a']} / {names[1]}: {quote['raw_b']}", text)

    def test_source_expiry_cannot_be_reset_by_rerendering(self):
        expired = TWC.derive(ROOT, self.evaluated + timedelta(hours=5))
        self.assertEqual(expired['source_collected_utc'], self.data['source_collected_utc'])
        self.assertTrue(all(row['line'] is None for row in expired['day_three']))
        self.assertTrue(all(not row['decision']['qualified'] for row in expired['day_three']))
        self.assertTrue(all(row['start_utc'] is None for row in expired['day_three'] if not row['listed_on_hotspawn']))
        self.assertEqual(expired['canonical_unresolved'], self.data['canonical_unresolved'])

    def test_crowd_changes_cannot_change_any_probability(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for relative in ('data/69e4c06a/research.json', 'data/c64a5e19/board.json',
                             'data/c64a5e19/official_inputs.json', 'data/c64a5e19/source_payloads.json'):
                destination = directory / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            evidence = json.loads((directory / 'data/c64a5e19/official_inputs.json').read_text())
            for fixture in evidence['lobby']['transfer_state']['fixtures']:
                fixture['participants0_picked_percent'], fixture['participants1_picked_percent'] = 1, 99
            (directory / 'data/c64a5e19/official_inputs.json').write_text(json.dumps(evidence))
            changed = TWC.derive(directory, self.evaluated)
            self.assertEqual([r['line'] for r in changed['day_three']], [r['line'] for r in self.data['day_three']])
            self.assertEqual([r['quotes'] for r in changed['day_three']], [r['quotes'] for r in self.data['day_three']])

    def test_every_category_table_row_has_https_source_and_mobile_chrome(self):
        from bs4 import BeautifulSoup
        for renderer in (TWC.render_index, TWC.render_results, TWC.render_roster, TWC.render_flagged, TWC.render_method):
            soup = BeautifulSoup(renderer(self.data), 'html.parser')
            self.assertEqual(len(soup.select('h1')), 1)
            self.assertTrue(soup.select_one('meta[name="viewport"]'))
            self.assertTrue(soup.select_one('nav a[href="../picks-every-match/index.html"]'))
            self.assertIn('Skip to content', soup.get_text())
            for row in soup.select('tbody tr'):
                self.assertTrue(row.select('a[href^="https://"]'), row.get_text())

    def test_future_group_b_listing_is_not_still_flagged_as_unlisted(self):
        data = copy.deepcopy(self.data)
        row = next(r for r in data['day_three'] if r['key'] == 'legacy-betboom')
        row.update(listed_on_hotspawn=True, fixture_id='synthetic-listed-fixture')
        rendered = TWC.render_flagged(data)
        self.assertIn('Listed in this canonical capture as #synthetic-listed-fixture', rendered)
        self.assertNotIn('Unlisted Group B decider', rendered)

    def test_missing_ownership_is_not_mislabelled_as_a_missing_fixture(self):
        data = copy.deepcopy(self.data)
        row = next(r for r in data['day_three'] if r['key'] == 'aurora-9z')
        row.update(listed_on_hotspawn=True, ownership=None)
        self.assertIn('Ownership unverified for this listed fixture.', TWC.render_index(data))

    def test_a_model_fallback_cannot_be_displayed_as_a_bookmaker_estimate(self):
        data = copy.deepcopy(self.data)
        row = data['day_three'][0]
        row['line'] = {'prob_a': .6, 'prob_b': .4, 'basis': 'model', 'pick_team': row['team_a']}
        self.assertIn('Originated model estimate', TWC.render_index(data))

    def test_results_have_no_unverified_finish_or_rest_timestamps(self):
        for result in self.data['facts']['results']:
            self.assertNotIn('finish_utc', result)
            self.assertNotIn('rest_hours', result)
        self.assertIn('not a new IGL this week', TWC.render_roster(self.data))
        self.assertIn('class="expiry"', TWC.render_index(self.data))

    def test_root_executive_links_category_without_replacing_canonical_primary(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        summary = soup.select_one('#executive-summary')
        self.assertEqual(summary.select_one('a.btn-primary')['href'], 'picks-every-match/index.html')
        link = summary.select_one('a[href="twc-2026/index.html"]')
        self.assertIsNotNone(link)
        self.assertIsNone(link.find_parent('details'))
        self.assertLessEqual(len(soup.select('header nav a')), 10)

    def test_category_is_in_scheduled_build_publication_and_staged_link_gate(self):
        refresh = (ROOT / '.github/workflows/every-match-c64a5e19.yml').read_text()
        pages = (ROOT / '.github/workflows/pages.yml').read_text()
        stage = (ROOT / 'scripts/stage_site.py').read_text()
        self.assertIn("cron: '12 */4 * * *'", refresh)
        self.assertIn('python3 scripts/69e4c06a/build.py', refresh)
        self.assertIn('data/69e4c06a/day3.json twc-2026', refresh)
        self.assertIn('python scripts/69e4c06a/build.py', pages)
        self.assertIn('scripts/69e4c06a/browser_smoke.py', pages)
        self.assertIn("'twc-2026'", stage)
        self.assertIn('_twc.build(OUT)', stage)


class DeclaredLeaderboardRisk(unittest.TestCase):
    def row(self):
        return {'listed_on_hotspawn': True, 'team_a': 'Alpha', 'team_b': 'Beta',
                'line': {'basis': 'market', 'prob_a': .65, 'prob_b': .35},
                'ownership': {'team_a': .83, 'team_b': .17}, 'offered_points': 7,
                'quotes': [{'source_key': 'pinnacle'}, {'source_key': 'melbet'}]}

    def test_qualifying_swing_exposes_cost_without_changing_the_line(self):
        row = self.row()
        original = copy.deepcopy(row)
        pick = TWC.decision(row)
        self.assertTrue(pick['qualified'])
        self.assertEqual(pick['pick_team'], 'Beta')
        self.assertAlmostEqual(pick['expected_points_sacrificed'], 2.1)
        self.assertAlmostEqual(pick['favorite_expected_points'], 4.55)
        self.assertAlmostEqual(pick['underdog_expected_points'], 2.45)
        self.assertEqual(row, original)

    def test_below_floor_never_tunes_threshold_to_force_an_underdog(self):
        row = self.row()
        row['line'].update(prob_a=.6522, prob_b=.3478)
        choice = TWC.decision(row)
        self.assertFalse(choice['qualified'])
        self.assertIsNone(choice['pick_team'])
        self.assertEqual(TWC.POLICY['minimum_underdog_probability'], .35)

    def test_missing_zero_or_overowned_ownership_is_not_an_infinite_edge(self):
        for ownership in (None, {'team_a': 1, 'team_b': 0}, {'team_a': .7, 'team_b': .3}):
            row = self.row()
            row['ownership'] = ownership
            self.assertFalse(TWC.decision(row)['qualified'])
            if ownership and ownership['team_b'] == 0:
                self.assertIsNone(TWC.decision(row)['probability_to_ownership_ratio'])

    def test_model_one_book_or_exchange_only_is_not_a_two_book_swing(self):
        row = self.row()
        row['line']['basis'] = 'model'
        self.assertFalse(TWC.decision(row)['qualified'])
        for quotes in ([{'source_key': 'melbet'}], [{'source_key': 'kalshi'}],
                       [{'source_key': 'pinnacle'}, {'source_key': 'kalshi'}]):
            row = self.row()
            row['quotes'] = quotes
            self.assertFalse(TWC.decision(row)['qualified'])

    def test_mismatched_ownership_order_is_blank_not_reversed_by_guess(self):
        row = {'fixture_id': 'test', 'team_a': 'Alpha', 'team_b': 'Beta'}
        evidence = {'lobby': {'transfer_state': {'fixtures': [
            {'id': 'test', 'participants0_name': 'Beta', 'participants1_name': 'Alpha',
             'participants0_picked_percent': 20, 'participants1_picked_percent': 80}]}}}
        self.assertIsNone(TWC.canonical_ownership(row, evidence))


if __name__ == '__main__':
    unittest.main()
