"""Independent arithmetic, exhaustive membership and fail-closed regression tests."""
import copy
import importlib.util
import json
import math
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/cbf92764'))
spec=importlib.util.spec_from_file_location('cbf_build',ROOT/'scripts/cbf92764/build.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)

class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.rows=[];self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='tr':self.current=[]
        if tag=='a' and a.get('href'):
            self.links.append(a['href'])
            if self.current is not None:self.current.append(a['href'])
    def handle_endtag(self,tag):
        if tag=='tr':self.rows.append(self.current);self.current=None

def setUpModule():
    # Upstream collectors refresh more often than this section's four-hour schedule.
    # Re-render at verification time instead of comparing unrelated capture versions.
    B.build()


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder,cls.board,cls.snap=B.select_input()
        cls.report=B.read(B.DATA/'report.json')
        cls.research=B.read(B.DATA/'research.json')
        cls.md=(B.DATA/'valve-standings.md').read_text()
        cls.clock=B.parse(cls.report['generated_utc'])

    def resolved(self,board=None,snap=None,research=None,clock=None):
        return B.resolve(board or self.board,snap or self.snap,research or self.research,self.md,clock or self.clock)

    def test_report_replays_exactly(self):
        reproduced=self.resolved();actual=copy.deepcopy(self.report);actual.pop('input');actual.pop('provider_replay')
        self.assertEqual(reproduced,actual)

    def test_official_provider_json_replays_every_consumed_price(self):
        result=B.PAYLOAD_VERIFIER.verify(self.folder)
        self.assertEqual(result['failures'],[])
        self.assertEqual(result,self.report['provider_replay'])
        self.assertEqual(result['consumed_quotes_checked'],sum(len(r.get('quotes',[])) for r in self.board['open']))

    def test_every_listed_fixture_exactly_once(self):
        want={r['fixture_id'] for r in self.snap['hotspawn']['fixtures'] if 'lobby_page' in r.get('seen_in',[])}
        got=[r['fixture_id'] for r in self.report['rows']]
        self.assertEqual(want,set(got));self.assertEqual(len(got),len(set(got)))

    def test_counts_partition_all_rows(self):
        c=self.report['summary'];rows=self.report['rows']
        self.assertEqual(c['listed'],len(rows))
        self.assertEqual(c['open']+c['locked_or_conflicting'],len(rows))
        self.assertEqual(c['with_pick']+c['unresolved'],c['open'])
        self.assertEqual(c['featured']+c['secondary']+c['exchange']+c['model'],sum(r['prob_a'] is not None for r in rows))

    def test_all_rows_have_official_inventory_source(self):
        for r in self.report['rows']:
            self.assertIn({'label':'HotSpawn fixture inventory','url':'https://play.hotspawn.com/lobby'},r['sources'])

    def test_featured_picks_unchanged(self):
        upstream={r['fixture_id']:r for r in self.board['open']}
        for r in self.report['rows']:
            if r['basis']=='featured market':
                self.assertEqual(r['prob_a'],upstream[r['fixture_id']]['line']['prob_a'])
                self.assertEqual(r['prob_b'],upstream[r['fixture_id']]['line']['prob_b'])

    def test_every_raw_price_independently_reproduces_market(self):
        for r in self.report['rows']:
            if r['basis']!='featured market':continue
            probs=[]
            for q in r['quotes']:
                a,b=float(q['raw_a']),float(q['raw_b'])
                if q['raw_format']=='american':a,b=[1+(100/abs(x) if x<0 else x/100) for x in (a,b)]
                elif q['raw_format']=='yes mid ($)':a,b=1/a,1/b
                p=(1/a)/(1/a+1/b)
                if q['swapped']:p=1-p
                weight=2 if q['source_key']=='pinnacle' else 1
                probs.append((p,weight))
            self.assertAlmostEqual(round(sum(p*w for p,w in probs)/sum(w for _,w in probs),4),r['prob_a'])

    def test_all_probabilities_normalize_and_pick_is_argmax(self):
        for r in self.report['rows']:
            if r['prob_a'] is None:self.assertIsNone(r['prob_b']);self.assertIsNone(r['pick']);continue
            self.assertTrue(0<r['prob_a']<1);self.assertAlmostEqual(r['prob_a']+r['prob_b'],1)
            self.assertEqual(r['pick'],r['team_a'] if r['prob_a']>r['prob_b'] else r['team_b'] if r['prob_b']>r['prob_a'] else None)

    def test_model_reproduces_independent_formula(self):
        k=self.report['calibration']['k'];q=math.log(10)/400;g=1/math.sqrt(1+3*q*q*75*75/math.pi**2)
        for r in self.report['rows']:
            if r['basis']!='originated rating model':continue
            self.assertEqual(len(r['ratings']),2)
            p=1/(1+math.exp(-k*g*q*(r['ratings'][0]['points']-r['ratings'][1]['points'])))
            self.assertEqual(round(p,4),r['prob_a']);self.assertIn('Experimental',' '.join(r['flags']))

    def test_expired_sources_suppress_all_probabilities(self):
        report=self.resolved(clock=self.clock+timedelta(hours=9))
        self.assertFalse(any(r['prob_a'] is not None for r in report['rows']))

    def test_stale_valve_check_cannot_originate(self):
        research=copy.deepcopy(self.research);research['valve']['checked_utc']=B.CORE.to_iso(self.clock-timedelta(days=2))
        self.assertFalse(any(r['basis']=='originated rating model' for r in self.resolved(research=research)['rows']))

    def test_unverified_valve_blob_cannot_originate(self):
        research=copy.deepcopy(self.research);research['valve']['sha']='wrong'
        self.assertFalse(any(r['basis']=='originated rating model' for r in self.resolved(research=research)['rows']))

    def test_ambiguous_or_missing_ratings_refused(self):
        index=B.ratings(self.md)
        for r in self.report['rows']:
            if r['basis']=='originated rating model':self.assertIsNotNone(B.model_pair(r,index))
        self.assertIsNone(B.model_pair({'team_a':'nonexistent_unranked','team_b':'also_unranked'},index))
        duplicate=next((rs[0]['team'] for rs in index.values() if len(rs)>1),None)
        if duplicate:self.assertIsNone(B.model_pair({'team_a':duplicate,'team_b':duplicate},index))

    def test_crowd_cannot_change_report(self):
        snap=copy.deepcopy(self.snap)
        for r in snap['hotspawn']['fixtures']:r['participants0_picked_percent']=99;r['pick_score']=999
        self.assertEqual(self.resolved(snap=snap),self.resolved())

    def test_unresolved_have_explicit_limitation_and_attempts(self):
        for r in self.report['rows']:
            if r['state']=='open' and not r['pick']:
                self.assertTrue(r['flags']);self.assertTrue(r['attempts'])

    def test_changed_raw_odds_fail_verification(self):
        board=copy.deepcopy(self.board)
        row=next((r for r in board['open'] if r.get('quotes')),None)
        if not row:self.skipTest('no market prices in this source capture')
        row['quotes'][0]['raw_a']=3.14
        with self.assertRaises(ValueError):self.resolved(board=board)

    def test_exchange_price_replays_from_official_rules_and_midpoints(self):
        for r in self.report['rows']:
            if r['basis']!='rule-backed exchange':continue
            for q in r['quotes']:
                evidence=q['kickoff_evidence'];outcomes=evidence['outcomes']
                self.assertEqual(evidence['start_utc'],q['start_utc'])
                raw=[(o['bid_dollars']+o['ask_dollars'])/2 for o in outcomes]
                p=raw[0]/sum(raw)
                if q['swapped']:p=1-p
                self.assertAlmostEqual(r['prob_a'],round(p,4))
                self.assertTrue(all(float(o['volume_contracts_reported'])>=20 for o in outcomes))

    def test_mutated_exchange_rules_fail_closed(self):
        research=copy.deepcopy(self.research)
        for src in research.get('exchange_payload',{}).get('sources',{}).values():
            for event in (src.get('payload') or {}).get('events',[]):
                event['markets'][0]['rules_primary']='No verified kickoff'
        result=self.resolved(research=research)
        self.assertFalse(any(r['basis']=='rule-backed exchange' for r in result['rows']))

    def test_zero_volume_exchange_quotes_do_not_make_picks(self):
        research=copy.deepcopy(self.research)
        for src in research.get('exchange_payload',{}).get('sources',{}).values():
            for event in (src.get('payload') or {}).get('events',[]):
                for market in event['markets']:market['volume_fp']='0.00'
        self.assertFalse(any(r['basis']=='rule-backed exchange' for r in self.resolved(research=research)['rows']))

    def test_secondary_wrong_opponent_or_time_cannot_join(self):
        fx={'team_a':'A','team_b':'B','start_utc':'2026-10-21T10:00:00Z'}
        for q in ({'team_a':'A','team_b':'C','start_utc':fx['start_utc']},
                  {'team_a':'A','team_b':'B','start_utc':None},
                  {'team_a':'A','team_b':'B','start_utc':'2026-10-22T10:00:00Z'}):self.assertIsNone(B.strict_join(fx,q))

class Pages(unittest.TestCase):
    def test_internal_links_files_and_fragments(self):
        for path in B.SITE.glob('*.html'):
            p=Links();p.feed(path.read_text())
            for link in p.links:
                u=urlsplit(link)
                if u.scheme:self.assertEqual(u.scheme,'https');continue
                target=(path.parent/unquote(u.path)).resolve() if u.path else path
                self.assertTrue(target.is_file(),(path,link))
                if u.fragment:self.assertIn(f'id="{u.fragment}"',target.read_text())

    def test_each_data_row_has_source_link(self):
        for path in B.SITE.glob('*.html'):
            p=Links();p.feed(path.read_text())
            for links in p.rows:
                if links:self.assertTrue(any(s.startswith('https://') for s in links),(path,links))

    def test_mobile_and_accessibility_contract(self):
        for path in B.SITE.glob('*.html'):
            t=path.read_text();self.assertIn('width=device-width, initial-scale=1',t)
            self.assertEqual(t.count('<h1>'),1);self.assertIn('href="#main"',t)
        self.assertIn('data-label', (B.SITE/'picks.html').read_text())
        self.assertIn('@media(max-width:720px)',(B.SITE/'style.css').read_text())
        self.assertIn('Expired / locked',(B.SITE/'app.js').read_text())

    def test_executive_summary_links_every_category(self):
        t=(B.SITE/'index.html').read_text()
        for name in ('picks.html','unresolved.html','flagged.html','sources.html','inventory.html'):self.assertIn(f'href="{name}"',t)
        self.assertIn('Unresolved picks &amp; limitations',t)


class PublishedStrictDashboard(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('cbf_deployment_check', ROOT / 'scripts/cbf92764/check_deployment.py')
        self.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.check)
        self.report = json.loads((ROOT / 'data/cbf92764/report.json').read_text())
        self.pages = {name: (ROOT / 'dashboard' / (name + '.html')).read_text() for name in self.check.NAMES}
        self.root = (ROOT / 'index.html').read_text()

    def test_live_contract_against_checked_in_pages(self):
        self.check.verify(self.report, self.pages, self.root)
        workflow = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertIn('python scripts/cbf92764/check_deployment.py', workflow)

    def test_live_contract_rejects_missing_rows_and_false_replay(self):
        broken = copy.deepcopy(self.report)
        broken['provider_replay']['failures'] = ['deliberate corrupted source']
        with self.assertRaises(AssertionError):
            self.check.verify(broken, self.pages, self.root)
        self.pages['inventory'] = self.pages['inventory'].replace('id="m', 'id="lost-m')
        with self.assertRaises(AssertionError):
            self.check.verify(self.report, self.pages, self.root)

if __name__=='__main__':unittest.main()
