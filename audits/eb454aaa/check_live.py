"""Official deployed Pages response check, run on GitHub Actions (not sandbox egress)."""
import json
import time
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

BASE='https://buffedlizard55-lab.github.io/MaltaProj2/'
report=json.loads((Path(__file__).parent/'report.json').read_text())
expected_rows=sum(r['snapshot_future_label'] or bool(r['quotes']) for r in report['rows'])
checks=[('','Pick'),('audits/eb454aaa/index.html','Independent market safety audit'),
        ('audits/eb454aaa/flagged.html','Flagged for Review'),('audits/eb454aaa/rows.html','Row-by-row safety review')]
for path,expected in checks:
    last=None
    for attempt in range(6):
        try:
            url=BASE+path+'?audit='+str(int(time.time()))
            req=urllib.request.Request(url,headers={'User-Agent':'MaltaProj2-Pages-verification/1.0','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=30) as response:
                assert response.status==200
                body=response.read().decode('utf-8')
            soup=BeautifulSoup(body,'html.parser')
            assert soup.find('h1') is not None
            assert expected.casefold() in soup.get_text().casefold(),path
            if path.endswith('rows.html'):
                rows=soup.select('tbody tr')
                assert len(rows)==expected_rows,(len(rows),expected_rows)
                for row in rows:
                    assert row.select_one('a[href^="https://"]') is not None
                    assert row.select_one('td[data-label="Probability / pick"]').get_text(strip=True)==''
            if path.endswith('flagged.html'):
                assert len(soup.select('tbody tr'))==8
            print('PASS HTTP 200 / deployed content:',BASE+path)
            last=None
            break
        except Exception as error:
            last=error
            if attempt<5:
                time.sleep(10)
    if last:
        raise SystemExit(f'Live Pages verification failed: {path}: {last}')
print('PASS: live dashboard and all audit pages served; source-linked rows, blank unconfirmed probabilities and eight review findings present')
