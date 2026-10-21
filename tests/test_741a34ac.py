"""Synthetic edge cases plus independent read-only contracts; no frozen live fixture counts."""
import copy
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_741a34ac_tests',ROOT/'scripts/741a34ac/audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
CLOCK=datetime(2026,10,21,20,tzinfo=timezone.utc)


def fixture(fid='1'):
    return dict(fixture_id=fid,team_a='Alpha',team_b='Beta',start_utc='2026-10-22T15:00:00Z',lock_utc='2026-10-22T14:54:00Z',status='scheduled',seen_in=['lobby_page'])


def sample():
    snap=dict(collected_to_utc='2026-10-21T19:59:00Z',hotspawn=dict(fixtures=[fixture()],permalinks={}),access_log=dict(hotspawn_lobby_page=dict(status=200,error=None,at_utc='2026-10-21T19:00:00Z',age_header='60',fixtures_in_transfer_state=1)))
    q=dict(public_url='https://melbet.com/en/line/esports',retrieved_utc='2026-10-21T19:00:00Z',decimal_a=5/3,decimal_b=2.5,prob_a=.6)
    row={**fixture(), 'pick':'Alpha','resolution':dict(basis='market',prob_a=.6,prob_b=.4),'quotes':[q], 'sources':[dict(url='https://melbet.com/en/line/esports')]}
    return snap,dict(rows=[row])


def run_audit(s,b): return a.audit(s,b,'',{},CLOCK,[])
def codes(r): return [f['code'] for f in r['findings']]


class ArithmeticAndCoverage(unittest.TestCase):
    def test_inventory_includes_unresolved(self):
        s,b=sample();b['rows'][0].update(pick=None,resolution=dict(basis='unresolved',prob_a=None,prob_b=None))
        r=run_audit(s,b);self.assertEqual(r['summary']['unresolved'],1);self.assertEqual(len(r['rows']),1)
    def test_missing_rows_never_disappear(self):
        s,b=sample();b['rows']=[];r=run_audit(s,b)
        self.assertIn('missing_or_duplicate_pick_row',codes(r));self.assertEqual(r['summary']['open'],1)
    def test_api_only_is_not_lobby_coverage(self):
        s,b=sample();b['rows'].append({**b['rows'][0],'fixture_id':'2'})
        self.assertEqual(run_audit(s,b)['summary']['api_or_board_only'],1)
    def test_duplicate_published_row_is_flagged(self):
        s,b=sample();b['rows']*=2;self.assertIn('missing_or_duplicate_pick_row',codes(run_audit(s,b)))
    def test_duplicate_capture_refused(self):
        s,b=sample();s['hotspawn']['fixtures']*=2
        with self.assertRaises(ValueError):run_audit(s,b)
    def test_empty_capture_is_not_full_coverage(self):
        s,b=sample();s['hotspawn']['fixtures']=[]
        with self.assertRaises(ValueError):run_audit(s,b)
    def test_parse_count_disagreement_refused(self):
        s,b=sample();s['access_log']['hotspawn_lobby_page']['fixtures_in_transfer_state']=3
        with self.assertRaises(ValueError):run_audit(s,b)
    def test_http_failure_not_live(self):
        s,b=sample();s['access_log']['hotspawn_lobby_page']['status']=403
        with self.assertRaises(ValueError):run_audit(s,b)
    def test_cache_age_subtracted(self):
        s,b=sample();s['access_log']['hotspawn_lobby_page']['age_header']='18000'
        r=run_audit(s,b);self.assertFalse(r['inventory_fresh']);self.assertIn('expired_inventory',codes(r))
    def test_rebuild_does_not_refresh_source_clock(self):
        s,b=sample();s['collected_to_utc']=a.iso(CLOCK)
        s['access_log']['hotspawn_lobby_page']['at_utc']='2026-10-20T00:00:00Z'
        self.assertFalse(run_audit(s,b)['inventory_fresh'])
    def test_missing_age_is_zero_but_malformed_age_unverified(self):
        self.assertIsNone(a.observation(dict(at_utc='2026-10-21T19:00:00Z',age_header='NaN')))
        self.assertIsNone(a.observation(dict(at_utc='2026-10-21T19:00:00Z',age_header='-1')))
    def test_future_quote_flagged(self):
        s,b=sample();b['rows'][0]['quotes'][0]['retrieved_utc']='2026-10-22T00:00:00Z'
        self.assertIn('quote_expired_or_unverified',codes(run_audit(s,b)))
    def test_eight_hour_old_quote_flagged(self):
        s,b=sample();b['rows'][0]['quotes'][0]['retrieved_utc']='2026-10-21T11:00:00Z'
        self.assertIn('quote_expired_or_unverified',codes(run_audit(s,b)))
    def test_floor_is_not_a_probability_bound(self):
        s,b=sample();b['rows'][0]['resolution']['basis']='originated_vrs_bound'
        self.assertIn('unsupported_probability_basis',codes(run_audit(s,b)))
    def test_arithmetic_mismatch_flagged(self):
        s,b=sample();b['rows'][0]['quotes'][0]['prob_a']=.9
        self.assertIn('quote_arithmetic_conflict',codes(run_audit(s,b)))
    def test_valid_market_arithmetic_has_no_flags(self):
        s,b=sample();self.assertEqual(codes(run_audit(s,b)),[])
    def test_aggregate_probability_must_reproduce(self):
        s,b=sample();b['rows'][0]['resolution'].update(prob_a=.7,prob_b=.3)
        self.assertIn('market_consensus_conflict',codes(run_audit(s,b)))
    def test_invalid_odds_flagged(self):
        s,b=sample();b['rows'][0]['quotes'][0]['decimal_a']=float('inf')
        self.assertIn('quote_not_reproducible',codes(run_audit(s,b)))
    def test_wrong_pick_side_flagged(self):
        s,b=sample();b['rows'][0]['pick']='Beta'
        self.assertIn('pick_side_conflict',codes(run_audit(s,b)))
    def test_nan_probability_flagged(self):
        s,b=sample();b['rows'][0]['resolution']['prob_a']=float('nan')
        self.assertIn('invalid_probability_pair',codes(run_audit(s,b)))
    def test_unresolved_probability_not_accepted(self):
        s,b=sample();b['rows'][0]['pick']=None
        self.assertIn('unresolved_with_probability',codes(run_audit(s,b)))
    def test_zero_volume_disclosed(self):
        s,b=sample();b['rows'][0]['quotes'][0]['raw']={'volume_dollars':0}
        self.assertIn('zero_volume_exchange',codes(run_audit(s,b)))
    def test_lock_and_start_both_matter(self):
        s,b=sample();s['hotspawn']['fixtures'][0]['start_utc']='2026-10-21T15:00:00Z'
        self.assertEqual(run_audit(s,b)['summary']['open'],0)
    def test_missing_lock_is_unverified(self):
        s,b=sample();s['hotspawn']['fixtures'][0]['lock_utc']=None
        self.assertIn('schedule_unverified',codes(run_audit(s,b)))
    def test_no_naive_dates(self): self.assertIsNone(a.parse('2026-10-21T20:00:00'))
    def test_unknown_basis_flagged(self):
        s,b=sample();b['rows'][0]['resolution']['basis']='crowd'
        self.assertIn('unsupported_probability_basis',codes(run_audit(s,b)))
    def test_identity_conflict_flagged(self):
        s,b=sample();b['rows'][0]['team_a']='Other Alpha'
        self.assertIn('fixture_identity_conflict',codes(run_audit(s,b)))
    def test_no_side_effect_on_foreign_evidence(self):
        s,b=sample();old=copy.deepcopy((s,b));run_audit(s,b);self.assertEqual((s,b),old)
    def test_url_spoof_rejected(self):
        for u in ['http://melbet.com','https://melbet.com.evil.test','https://evil@melbet.com','javascript:alert(1)']:
            self.assertFalse(a.official_url(u))
    def test_exact_rating_tuple_required(self):
        text='| 1 | 900 | Alpha | one, two, three, four, five | [details](x) |'
        index=a.rating_index(text)
        row=dict(standing=1,points=900,vrs_name='Alpha',roster='five, four, one, three, two')
        self.assertTrue(a.rating_matches(row,index));row['points']=901;self.assertFalse(a.rating_matches(row,index))


class PublishedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.report=json.loads((ROOT/'data/741a34ac/report.json').read_text())
    def test_counts_and_ids(self):
        r=self.report;rows=r['rows'];self.assertEqual(len(rows),r['summary']['listed'])
        self.assertEqual(len(rows),len({x['fixture_id'] for x in rows}))
        self.assertEqual(sum(x['state']=='open' for x in rows),r['summary']['open'])
    def test_every_row_has_official_inventory_source(self):
        for row in self.report['rows']:
            self.assertIn(urlsplit(row['hotspawn_url']).hostname,{'www.hotspawn.com','play.hotspawn.com'})
    def test_complete_rendered_inventory(self):
        page=(ROOT/'audits/741a34ac/index.html').read_text()
        for r in self.report['rows']: self.assertIn('id="m'+r['fixture_id']+'"',page)
    def test_no_unsourced_findings(self):
        for f in self.report['findings']:self.assertTrue(a.official_url(f['source_url']))
    def test_local_links_resolve(self):
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.urls=[]
            def handle_starttag(self,tag,attrs):
                d=dict(attrs)
                for key in ('href','src'):
                    if d.get(key):self.urls.append(d[key])
        for p in (ROOT/'audits/741a34ac').glob('*.html'):
            parser=Links();parser.feed(p.read_text())
            for u in parser.urls:
                parts=urlsplit(u)
                if not parts.scheme and parts.path:self.assertTrue((p.parent/parts.path).exists(),u)
    def test_accessibility_and_escaping(self):
        page=(ROOT/'audits/741a34ac/index.html').read_text()
        self.assertIn('name="viewport"',page);self.assertIn('scope="row"',page)
        self.assertIn('Skip to content',page);self.assertIn('data-expires=',page)
        self.assertEqual(a.esc('<script>'),'&lt;script&gt;')

if __name__=='__main__':unittest.main()
