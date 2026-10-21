"""Verify the actual published strict dashboard, not merely a successful build."""
import json
import os
import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen

NAMES = ('index', 'picks', 'unresolved', 'sources', 'flagged', 'inventory')


class Rows(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.rows = {}
        self.current = None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.current = attrs.get('id')
            if self.current:
                assert self.current not in self.rows, 'Duplicate fixture row'
                self.rows[self.current] = []
        if tag == 'a' and self.current:
            self.rows[self.current].append(attrs.get('href', ''))

    def handle_endtag(self, tag):
        if tag == 'tr':
            self.current = None


def verify(report, pages, root):
    assert 'dashboard/picks.html' in root and 'dashboard/unresolved.html' in root
    assert report['provider_replay']['failures'] == [], 'Published provider replay failed'
    rows = report['rows']
    assert len({r['fixture_id'] for r in rows}) == len(rows)
    opened = [r for r in rows if r['state'] == 'open']
    unresolved = [r for r in opened if not r['pick']]
    c = report['summary']
    assert c['listed'] == len(rows) and c['open'] == len(opened)
    assert c['unresolved'] == len(unresolved) and c['with_pick'] == len(opened) - len(unresolved)
    assert c['locked_or_conflicting'] == len(rows) - len(opened)
    for row in rows:
        pa, pb = row['prob_a'], row['prob_b']
        if pa is None or pb is None:
            assert pa is None and pb is None and row['pick'] is None
        else:
            assert 0 <= pa <= 1 and 0 <= pb <= 1 and abs(pa + pb - 1) < .00011
            expected = row['team_a'] if pa > pb else row['team_b'] if pb > pa else None
            assert row['pick'] == expected
    for name in NAMES:
        body = pages[name]
        assert 'CS2 / MATCH DESK' in body and 'name="viewport"' in body, name
        assert f'data-capture-expiry="{report["valid_until_utc"]}"' in body, name
        expected = rows if name == 'inventory' else unresolved if name in ('unresolved', 'flagged') else opened if name in ('picks', 'sources') else []
        published = Rows(body).rows
        assert set(published) == {'m' + r['fixture_id'] for r in expected}, name
        for row in expected:
            links = published['m' + row['fixture_id']]
            assert links and all(s['url'] in links for s in row['sources']), (name, row['fixture_id'])
            assert any(link.startswith('https://') for link in links)
    assert 'Unresolved picks &amp; limitations' in pages['index']
    assert f"{c['unresolved']} open matches have no supported directional pick" in pages['index']


def main():
    base = 'https://buffedlizard55-lab.github.io/MaltaProj2/'
    version = os.environ.get('GITHUB_SHA', 'strict-dashboard-verification')

    def get(path):
        request = Request(base + path + '?verification=' + version,
                          headers={'Cache-Control': 'no-cache'})
        with urlopen(request, timeout=30) as response:
            assert response.status == 200, path
            return response.read().decode('utf-8')

    for attempt in range(12):
        try:
            report = json.loads(get('data/cbf92764/report.json'))
            pages = {name: get('dashboard/' + name + '.html') for name in NAMES}
            verify(report, pages, get('index.html'))
            for name in ('style.css', 'app.js'):
                assert get('dashboard/' + name).strip(), name
            break
        except Exception as exc:
            if attempt == 11:
                raise RuntimeError('Live strict dashboard failed semantic/source verification') from exc
            time.sleep(10)
    print('PASS: live strict dashboard, six pages, assets, complete inventory, source links, provider replay and unresolved summary')
    print('Live strict dashboard:', report['capture_utc'], json.dumps(report['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
