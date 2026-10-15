"""Verify actual hosted Pages content (not a deployment API's success alone)."""
import json
import os
import time
import re
from urllib.request import Request, urlopen

base='https://buffedlizard55-lab.github.io/MaltaProj2/docs/'
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

# Verify the actual user-facing root and every-match board, not only the archived
# LineWatch subsite. Retry boundedly for Pages/CDN propagation.
public_base = base.removesuffix('docs/')
def public_get(path):
    with urlopen(Request(public_base + path + '?verification=' + version,
                         headers={'Cache-Control': 'no-cache'}), timeout=30) as response:
        assert response.status == 200, path
        return response.read().decode('utf-8')

for attempt in range(12):
    try:
        root = public_get('index.html')
        assert 'Open all CS2 picks' in root and 'picks-every-match/index.html' in root
        assert 'picks-every-match/unresolved.html' in root and 'canonical-unresolved' in root
        live = json.loads(public_get('data/c64a5e19/board.json'))
        assert live['policy'] == 'verified-every-match-v3'
        for name in ('index', 'picks', 'inventory', 'unresolved', 'flagged', 'method'):
            body = public_get('picks-every-match/' + name + '.html')
            assert 'data-policy="verified-every-match-v3"' in body, name
            assert 'name="viewport"' in body, name
            if name == 'picks':
                assert body.count('data-match data-search=') == len(live['open'])
                for row in live['open']:
                    assert 'id="m-' + row['fixture_id'] + '"' in body
        unresolved = public_get('picks-every-match/unresolved.html')
        assert 'Source attempts &amp; next steps' in unresolved or not live['summary']['tier_d_none']
        audit = json.loads(public_get('audits/3faf40e8/sources.json'))
        assert audit['session'] == '3faf40e8' and audit['findings']
        verification = json.loads(public_get('data/c64a5e19/verification.json'))
        assert not verification['failures'], verification['failures']
        assert verification['official_inputs']['fixture_rows_checked'] == len(live['inventory'])
        break
    except Exception as exc:
        if attempt == 11:
            raise RuntimeError('Public every-match dashboard did not pass semantic checks') from exc
        time.sleep(10)
print('PASS: live root executive summary and all six every-match pages; policy, source replay, inventory and picks agree')
print('Live every-match summary:', json.dumps(live['summary'], sort_keys=True))

# Session 69e4c06a: the focused TWC category must ship with the same canonical
# data batch. A green deployment API result alone does not prove these pages exist.
for attempt in range(12):
    try:
        root = public_get('index.html')
        assert 'twc-2026/index.html' in root and 'twc-2026/results.html' in root
        current = json.loads(public_get('data/c64a5e19/board.json'))
        twc = json.loads(public_get('data/69e4c06a/day3.json'))
        assert twc['session'] == '69e4c06a' and twc['schema_version'] == 1
        assert twc['canonical_generated_utc'] == current['generated_utc']
        assert twc['source_collected_utc'] == current['collected_to_utc']
        assert twc['canonical_summary'] == current['summary']
        assert len(twc['facts']['results']) == 8 and len(twc['roster_announcements']) == 3
        assert all(item['value'] is None for item in twc['facts']['unknowns'])
        indexed = {row['fixture_id']: row for row in current['open']}
        for row in twc['day_three']:
            if row['listed_on_hotspawn']:
                original = indexed[row['fixture_id']]
                assert [row['team_a'], row['team_b']] == [original['team_a'], original['team_b']]
                if row['line']:
                    assert row['line']['prob_a'] == original['line']['prob_a']
                    assert row['line']['prob_b'] == original['line']['prob_b']
            else:
                assert all(row[key] is None for key in ('fixture_id', 'ownership', 'offered_points'))
                assert not row['decision']['qualified']
        for name in ('index', 'results', 'roster', 'flagged', 'method'):
            body = public_get('twc-2026/' + name + '.html')
            assert 'TWC 2026 evidence' in body and 'name="viewport"' in body, name
            assert 'assets.css' in body and 'app.js' in body, name
            if name == 'index':
                for row in twc['day_three']:
                    assert 'id="' + row['key'] + '"' in body
        for asset in ('assets.css', 'app.js'):
            assert public_get('twc-2026/' + asset).strip(), asset
        break
    except Exception as exc:
        if attempt == 11:
            raise RuntimeError('Public TWC category did not pass source/canonical consistency checks') from exc
        time.sleep(10)
print('PASS: live TWC results, original roster timeline, source-linked decisions, assets and canonical consistency')
print('TWC source collection:', twc['source_collected_utc'])
