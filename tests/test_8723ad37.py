"""Evidence-contract regressions. Synthetic inputs are tests, never published fixtures."""
import copy
import json
import re
import unittest
from datetime import timedelta
from tests.test_c64a5e19 import B, core, ROOT

class EvidenceGate(unittest.TestCase):
    def setUp(self):
        self.s = json.loads((ROOT/'data/c64a5e19/snapshot.json').read_text())
        self.now = core.parse_iso(self.s['collected_to_utc'])
        self.board = B.build_board(self.s, 'test')
    def test_stale_fixture_disables_all_picks(self):
        s=copy.deepcopy(self.s)
        s['hotspawn_fallback_from']=core.to_iso(self.now-timedelta(hours=5))
        self.assertTrue(all(not r['line'] for r in B.build_board(s,'test')['open']))
    def test_missing_fixture_observation_fails_closed(self):
        self.s.pop('hotspawn_fallback_from',None)
        self.s['access_log']['hotspawn_lobby_page'].pop('at_utc',None)
        self.assertTrue(all(not r['line'] for r in B.build_board(self.s,'test')['open']))
    def test_stale_quotes_do_not_become_market_picks(self):
        for q in self.s['quotes']: q['retrieved_utc']=core.to_iso(self.now-timedelta(hours=5))
        self.assertTrue(all(not r['market'] for r in B.build_board(self.s,'test')['open']))
    def test_stale_rating_and_missing_market_stay_blank(self):
        self.s['quotes']=[]; self.s['vrs']['snapshot']='2000_01_01'
        self.assertTrue(all(not r['line'] for r in B.build_board(self.s,'test')['open']))
    def test_derived_percentages_are_not_trusted(self):
        for q in self.s['quotes']: q['prob_a']=0.999
        rebuilt=B.build_board(self.s,'test')
        self.assertEqual([r['line'] for r in rebuilt['open']], [r['line'] for r in self.board['open']])
    def test_no_model_changes_to_market(self):
        self.s['vrs']={}
        rows={r['fixture_id']:r for r in B.build_board(self.s,'test')['open']}
        for r in self.board['open']:
            if r['market']: self.assertEqual(rows[r['fixture_id']]['line'],r['line'])
    def test_duplicate_ratings_never_choose_recent_roster(self):
        idx,dup=B.rating_index({'teams':[{'team':'Example','points':100,'latest_match_date':'2026-10-10'},
                                        {'team':'Example','points':900,'latest_match_date':'2026-09-01'}]})
        self.assertFalse(idx); self.assertIn('example',dup)
    def test_missing_approximate_or_late_kickoff_rejected(self):
        fx={'team_a':'Alpha','team_b':'Bravo','start_utc':'2026-10-15T08:00:00Z'}
        for start,approx in [(None,False),('2026-10-15T08:00:00Z',True),('2026-10-15T09:00:00Z',False)]:
            q={**fx,'start_utc':start,'start_is_approx':approx}
            self.assertTrue(core.match_quote(fx,q)['rejected'])
    def test_api_only_cannot_inflate_lobby_coverage(self):
        fx=copy.deepcopy(next(f for f in self.s['hotspawn']['fixtures'] if f['fixture_id'] in {r['fixture_id'] for r in self.board['open']}))
        fx['fixture_id']='test-api-only';fx['seen_in']=['api'];self.s['hotspawn']['fixtures'].append(fx)
        self.assertEqual(B.build_board(self.s,'test')['summary'],self.board['summary'])
    def test_all_consumed_rating_values_match_official_file(self):
        if self.s['vrs'].get('snapshot') != '2026_10_05':
            self.skipTest('Current rating date differs from this preserved source audit')
        text=(ROOT/'audits/8723ad37/valve-2026-10-05.md').read_text()
        source={(m[2].strip(),int(m[1]),m[3].strip()) for m in re.findall(r'^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|',text,re.M)}
        for r in self.board['open']:
            if r['model']:
                for side in ('team_a','team_b'):
                    v=r['vrs'][side]
                    self.assertIn((v['team'],v['points'],v['roster']),source)
    def test_each_market_quote_arithmetic_and_deadline(self):
        for r in self.board['open']:
            if r['line']:
                self.assertGreater(core.parse_iso(r['valid_until_utc']),self.now)
            for q in r['quotes']:
                nv=core.no_vig(q['decimal_a'],q['decimal_b'])
                expected=1-nv['prob_a'] if q['swapped'] else nv['prob_a']
                self.assertAlmostEqual(expected,q['no_vig_prob_team_a'],places=3)
    def test_all_flagged_rows_have_working_anchor(self):
        text=B.render_flagged(self.board)
        for r in self.board['open']:
            if r['flags']: self.assertIn('id="f-'+r['fixture_id']+'"',text)
    def test_expiry_and_escaped_source_names(self):
        b=copy.deepcopy(self.board);b['open'][0]['team_a']='<img src=x onerror=alert(1)>'
        text=B.render_index(b)
        self.assertNotIn('<img src=x',text)
        self.assertIn('data-until=',text); self.assertIn('setInterval(expire,30000)',text)
    def test_rebuild_at_future_time_does_not_keep_locked_picks(self):
        future=self.now+timedelta(days=30)
        self.assertEqual(B.build_board(self.s,'test',now=future)['summary']['open'],0)

if __name__=='__main__': unittest.main()
