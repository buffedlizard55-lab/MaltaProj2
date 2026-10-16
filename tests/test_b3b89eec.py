"""b3b89eec: independent re-derivation of the retained CS2 capture + static site audit.

These tests re-verify the LATEST committed capture rather than hard-coding its numbers, so
they keep holding as the board refreshes: every quote must re-derive from its retained raw
odds, every market consensus must match the declared (published) weighting, and every public
page must keep its viewport, single h1, resolving links and per-row official source links.
"""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BOARD_VERIFY = module('test_b3b89eec_board', 'scripts/b3b89eec/verify_board.py')
PAGES_VERIFY = module('test_b3b89eec_pages', 'scripts/b3b89eec/verify_pages.py')
TWC_REVIEW = ROOT / 'data/b3b89eec/twc_review.json'


class BoardReDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        art = ROOT / 'data/b3b89eec/board_verification.json'
        cls._saved_art = art.read_bytes() if art.exists() else None
        cls.result = BOARD_VERIFY.run()
        cls._fresh_art = art.read_bytes() if art.exists() else None
        if cls._saved_art is not None:
            art.write_bytes(cls._saved_art)

    def test_no_findings(self):
        self.assertEqual(self.result['findings'], [],
                         'stored values no longer re-derive from the retained raw quotes')

    def test_summary_arithmetic(self):
        counts = self.result['counts']
        self.assertEqual(counts['open'], counts['market'] + counts['model'] + counts['none'])
        self.assertGreaterEqual(counts['quotes'], 1)
        self.assertGreaterEqual(counts['market'], 1)

    def test_twc_deciders_crosschecked_when_open(self):
        board = json.loads(BOARD_VERIFY.BOARD.read_text())
        open_ids = {f['fixture_id'] for f in board['open']}
        deciders = {'1080205', '1081775'} & open_ids
        checked = {o['fixture_id'] for o in self.result['checks_passed'] if o['check'] == 'hltv_crosscheck'}
        self.assertEqual(checked, deciders)

    def test_artifact_written(self):
        art = ROOT / 'data/b3b89eec/board_verification.json'
        self.assertTrue(art.exists())
        data = json.loads((self._fresh_art or art.read_bytes()).decode('utf-8'))
        self.assertEqual(data['counts'], self.result['counts'])
        self.assertEqual(data['findings'], [])


class TwcReviewFacts(unittest.TestCase):
    """The session's verified TWC fact ledger: kickoffs, scores, rosters, sources."""

    @classmethod
    def setUpClass(cls):
        cls.review = json.loads(TWC_REVIEW.read_text())

    def test_day3_kickoffs_resolved(self):
        by_fixture = {m['fixture_id']: m for m in self.review['day3']['matches']}
        self.assertEqual(by_fixture['1080205']['start_utc'], '2026-10-16T14:00:00Z')
        self.assertEqual(by_fixture['1081775']['start_utc'], '2026-10-16T17:00:00Z')
        for m in self.review['day3']['matches']:
            self.assertTrue(m['hltv_url'].startswith('https://www.hltv.org/matches/'))
            self.assertTrue(m['hotspawn_url'].startswith('https://'))
            for line in m['lines_capture_2026_10_16T04_09Z']:
                self.assertTrue(line['url'].startswith('https://'))
            self.assertGreaterEqual(len(m['kickoff_evidence']), 2)

    def test_day1_day2_rows_verified_with_links(self):
        for day in (self.review['day1'], self.review['day2']):
            self.assertEqual(len(day['rows']), 4)
            for row in day['rows']:
                self.assertTrue(row['verified'])
                self.assertTrue(row['hltv_url'].startswith('https://www.hltv.org/matches/'))

    def test_roster_finding_is_dated_not_causal(self):
        rv = self.review['roster_verification']
        self.assertIn('July 2026', rv['finding'])
        self.assertIn('No October roster change was found', rv['finding'])
        for s in rv['sources']:
            self.assertTrue(s['url'].startswith('https://www.hltv.org/'))
        self.assertTrue(rv['limitations'], 'unverified seconds must stay flagged')

    def test_ownership_is_context_only(self):
        ctx = self.review['day3']['matches'][0]['hotspawn_ownership_context_only']
        # ownership is stored as a labeled context block, never fed into the board math
        self.assertLess(ctx['9z'], ctx['Aurora'])
        self.assertGreater(ctx['Aurora'], 0.5)
        self.assertTrue(ctx['source'].startswith('https://'))
        self.assertGreaterEqual(ctx['reported_picks'], 1)


class PagesAudit(unittest.TestCase):
    def test_all_pages_pass(self):
        result = PAGES_VERIFY.audit()
        self.assertEqual(result['findings'], [])
        self.assertGreaterEqual(result['pages_checked'], 51)

    def test_session_pages_are_audited(self):
        for page in ('verify/b3b89eec/index.html', 'verify/b3b89eec/flagged.html'):
            self.assertIn(page, PAGES_VERIFY.PAGES)
            self.assertIn(page, PAGES_VERIFY.ROW_SOURCE_PAGES)


if __name__ == '__main__':
    unittest.main()
