import json
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit, unquote
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
sys.modules.pop('collect', None)
sys.path.insert(0,str(ROOT/'scripts'))
from collect import parse_lobby, iso_ms
from model import fair_line, american_to_decimal
from build import build

class AuditTests(unittest.TestCase):
    def test_reference_math(self):
        f=fair_line(-1250,530)
        self.assertAlmostEqual(f['probability_a'],35/41)
        self.assertAlmostEqual(f['probability_a']+f['probability_b'],1)
        self.assertAlmostEqual(american_to_decimal(280),3.8)
        self.assertAlmostEqual(f['fair_a'],1/f['probability_a'])
        self.assertAlmostEqual(fair_line(100,100)['overround'],0)
    def test_invalid_odds(self):
        for x in (0,99,-99,float('nan'),float('inf'),True,'100',None):
            with self.assertRaises(ValueError): american_to_decimal(x)
    def test_exact_fixture_source(self):
        raw=(ROOT/'docs/evidence/probe/lobby.txt').read_text()
        d=parse_lobby(raw,'2026-10-13T17:51:30+00:00')
        self.assertEqual(len(d['matches']),86)
        self.assertEqual(d['visible_count'],27)
        a=next(x for x in d['matches'] if x['id']=='1079438')
        self.assertEqual(a['team_a'],'Astralis')
        self.assertEqual(a['start_utc'],'2026-10-14T10:00:00+00:00')
        self.assertEqual(a['lock_offset_sec'],360)
        self.assertNotIn('picked_percent', json.dumps(d))
        for row in d['matches']:
            self.assertIsNone(row['probability_a'])
            self.assertIsNone(row['odds_a'])
            self.assertTrue(row['source'].startswith('https://'))
    def test_fail_closed(self):
        for raw in ('', '<html>Access denied</html>', '<script id="ng-state">{}</script>'):
            with self.assertRaises(ValueError): parse_lobby(raw,'2026-10-13T00:00:00+00:00')
        with self.assertRaises(ValueError): iso_ms('tomorrow')
    def test_every_row_has_official_source(self):
        build()
        allowed={'play.hotspawn.com','www.hotspawn.com','thunderpick.io','www.hltv.org','gg.bet','www.rivalry.com'}
        for file in (ROOT/'docs').glob('*.html'):
            soup=BeautifulSoup(file.read_text(),'html.parser')
            for row in soup.select('tbody tr'):
                self.assertTrue(any(urlsplit(a['href']).hostname in allowed for a in row.select('a[href]')), (file,str(row)))
    def test_all_local_links(self):
        build()
        for file in (ROOT/'docs').glob('*.html'):
            soup=BeautifulSoup(file.read_text(),'html.parser')
            for node in soup.select('[href], [src]'):
                url=node.get('href') or node.get('src')
                part=urlsplit(url)
                if part.scheme or part.netloc: continue
                target=(file.parent/unquote(part.path)).resolve() if part.path else file
                self.assertTrue(target.exists(),(file,url))
                if part.fragment and target.suffix=='.html':
                    dest=BeautifulSoup(target.read_text(),'html.parser')
                    self.assertIsNotNone(dest.find(id=part.fragment),(file,url))
    def test_no_current_quotes_without_evidence(self):
        data=json.loads((ROOT/'docs/data/matches.json').read_text())
        for row in data['matches']:
            self.assertEqual(row['status'],'unverified')
            for field in ('odds_a','odds_b','probability_a','probability_b'):
                self.assertIsNone(row[field])

if __name__=='__main__': unittest.main()
