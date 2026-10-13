"""Independent audit policy regressions; upstream review findings do not block merging."""
import importlib.util
import json
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit_eb454aaa',ROOT/'audits/eb454aaa/audit.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MarketSafetyAudit(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,13,22,0,tzinfo=timezone.utc)
        self.row = {'start_time_utc':'2026-10-14T10:00:00Z'}
        self.q = {'market_is_live':False,'market_status':'open','source_api_url':'https://www.pinnacle.com/',
                  'retrieved_at_utc':'2026-10-13T21:00:00Z','start_time_utc':'2026-10-14T10:00:00Z',
                  'decimal_odds_a':2,'decimal_odds_b':2,'implied_prob_a':.5,'implied_prob_b':.5,'side_order':'same'}

    def flags(self):
        return m.quote_flags(self.row,self.q,self.now)

    def test_clean_mechanical_quote(self):
        self.assertEqual(self.flags(),[])

    def test_live_quote_is_flagged(self):
        self.q['market_is_live']=True
        self.assertIn('live_or_unknown_market_state',self.flags())

    def test_missing_live_state_is_not_assumed_prematch(self):
        del self.q['market_is_live']
        self.assertIn('live_or_unknown_market_state',self.flags())

    def test_non_open_quote(self):
        self.q['market_status']='S'
        self.assertIn('market_state_not_confirmed_open',self.flags())

    def test_unknown_state(self):
        self.q['market_status']=None
        self.assertIn('market_state_not_confirmed_open',self.flags())

    def test_stale_and_future_observations(self):
        for time in ('2026-10-13T17:59:59Z','2026-10-13T22:00:01Z',None):
            self.q['retrieved_at_utc']=time
            self.assertIn('missing_stale_or_future_observation',self.flags())

    def test_skew_is_not_certified(self):
        self.q['start_time_utc']='2026-10-14T05:00:00Z'
        self.assertIn('start_time_disagreement_over_90_minutes',self.flags())

    def test_no_timezone_inference(self):
        self.assertIsNone(m.utc('2026-10-14T10:00:00'))
        self.q['start_time_utc']='2026-10-14T10:00:00'
        self.assertIn('missing_explicit_start_time',self.flags())

    def test_alias_is_flagged(self):
        self.q['aliases_applied']=['WhiteBIT']
        self.assertIn('team_alias_requires_primary_identity_review',self.flags())

    def test_fair_math_rejects_invalid_and_nonfinite(self):
        for a in (None,'bad',0,1,-2,float('nan'),float('inf')):
            self.assertIsNone(m.fair(a,2))
        a,b=m.fair(1.5,3)
        self.assertAlmostEqual(a,2/3)
        self.assertAlmostEqual(a+b,1)

    def test_reversed_arithmetic(self):
        self.q.update(decimal_odds_a=1.5,decimal_odds_b=3,implied_prob_a=.3333,implied_prob_b=.6667,side_order='reversed')
        self.assertEqual(self.flags(),[])
        self.q['implied_prob_a']=.6667
        self.assertIn('per_source_probability_arithmetic_mismatch',self.flags())

    def test_audit_never_publishes_unconfirmed_predictions(self):
        report=json.loads((ROOT/'audits/eb454aaa/report.json').read_text())
        for row in report['rows']:
            self.assertIsNone(row['prob_a'])
            self.assertIsNone(row['prob_b'])
            self.assertIsNone(row['pick'])
            self.assertTrue(row['source_link'].startswith('https://'))
        self.assertEqual(len(report['rows']),report['summary']['inventory_rows'])
        for finding in report['findings']:
            self.assertTrue(finding['source_url'].startswith('https://'))

    def test_verified_valve_hashes(self):
        report=json.loads((ROOT/'audits/eb454aaa/valve_verification.json').read_text())
        self.assertEqual(len(report['files']),4)
        for row in report['files']:
            self.assertTrue(row['byte_match'])
            self.assertEqual(row['official_sha256'],row['local_sha256'])

if __name__=='__main__':
    unittest.main()
