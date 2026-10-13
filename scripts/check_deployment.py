"""Verify actual hosted Pages content (not a deployment API's success alone)."""
import json
import os
import time
import re
from urllib.request import Request, urlopen

base='https://buffedlizard55-lab.github.io/MaltaProj2/'
version=os.environ.get('GITHUB_SHA','verification')
def get(path):
    with urlopen(Request(base+path+'?verification='+version,
                         headers={'Cache-Control':'no-cache'}),timeout=30) as r:
        assert r.status==200, (path,r.status)
        return r.read().decode('utf-8')
for path in ('index.html','matches.html','odds.html','methodology.html','sources.html','flags.html'):
    for attempt in range(12):
        try:
            body=get(path)
            if 'LINEWATCH' in body and 'style.css' in body and 'app.js' in body:
                break
            title=re.search(r'<title>(.*?)</title>',body,re.S)
            detail=f'{path}: unexpected published title {title.group(1) if title else body[:160]}'
        except Exception as exc:
            detail=f'{path}: {type(exc).__name__}: {exc}'
        if attempt==11:
            print('::error title=Public Pages content check::'+detail,flush=True)
            raise RuntimeError(detail)
        time.sleep(10)
    print('HTTP 200 / LineWatch marker:',path)
for path in ('style.css','app.js'):
    assert get(path).strip(), path
fixtures=json.loads(get('data/matches.json'))
assert fixtures['matches']
assert all(x['probability_a'] is None and x['odds_a'] is None for x in fixtures['matches'])
health=json.loads(get('data/health.json'))
print('PASS: live site, six pages, CSS/JS,',len(fixtures['matches']),'source-linked fixtures and health report')
print('Fixture observation:',fixtures['observed_at'])
print('Collection attempt:',health['attempted_at'])
