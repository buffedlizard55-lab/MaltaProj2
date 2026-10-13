"""Read public Angular transfer-state. No login, private API, or crowd-probability use."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/data'
LOBBY = 'https://play.hotspawn.com/lobby'

def utc():
    return datetime.now(timezone.utc).isoformat()

def iso_ms(value):
    if value is None:
        return None
    if not re.fullmatch(r'\d{13}', str(value)):
        raise ValueError('Invalid millisecond timestamp')
    return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat()

def parse_lobby(html, retrieved_at):
    soup = BeautifulSoup(html, 'html.parser')
    state = soup.select_one('script#ng-state')
    if state is None:
        raise ValueError('Public Angular transfer-state missing; refusing empty replacement')
    entries = json.loads(state.string)
    fixtures, links = None, {}
    for value in entries.values():
        if not isinstance(value, dict):
            continue
        url, body = value.get('u', ''), value.get('b')
        if url.endswith('/api/v1/fixtures') and isinstance(body, list):
            fixtures = body
        if isinstance(body, dict) and isinstance(body.get('permalinks'), dict):
            links = body['permalinks']
    if not fixtures:
        raise ValueError('No fixture list; retaining prior snapshot')
    visible = {}
    for card in soup.select('.vs-card'):
        a, date = card.select_one('a[href*="/matches/"]'), card.select_one('.vs-card-date')
        if a and date:
            visible[a['href']] = date.get_text(strip=True)
    matches, seen = [], set()
    for f in fixtures:
        id_ = str(f['id'])
        if id_ in seen:
            raise ValueError('Duplicate fixture ID')
        seen.add(id_)
        for key in ('participants0_name', 'participants1_name', 'competition_name', 'sport_alias'):
            if not isinstance(f.get(key), str) or not f[key].strip():
                raise ValueError('Missing required fixture field: ' + key)
        source = links.get(id_, LOBBY)
        if not source.startswith(('https://www.hotspawn.com/matches/', LOBBY)):
            raise ValueError('Unexpected permalink origin')
        start = iso_ms(f.get('scheduled_start_time'))
        flags = ['No verified current external market mapping']
        if start and datetime.fromisoformat(start) < datetime.fromisoformat(retrieved_at) and f.get('status') == 'scheduled':
            flags.append('Past start but source status still scheduled')
        if f.get('lock_offset_sec') != 300:
            flags.append('Source lock offset differs from 5-minute help-page rule')
        matches.append(dict(id=id_, team_a=f['participants0_name'], team_b=f['participants1_name'],
            team_a_id=f.get('participants0_id'), team_b_id=f.get('participants1_id'),
            tournament=f['competition_name'], game=f['sport_alias'], start_utc=start,
            display_time=visible.get(source), source=source, lobby_source=LOBBY,
            source_status=f.get('status'), visible_card=source in visible,
            lock_utc=iso_ms(f.get('lock_time')), lock_offset_sec=f.get('lock_offset_sec'),
            odds_a=None, odds_b=None, probability_a=None, probability_b=None,
            status='unverified', flags=flags))
    return dict(observed_at=retrieved_at, source=LOBBY,
        collection='Public server-rendered HTML / script#ng-state / api/v1/fixtures response body',
        completeness='All embedded fixtures captured; not proof of all games or live completeness',
        sha256=hashlib.sha256(html.encode()).hexdigest(),
        visible_count=len(visible), matches=matches)

def fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'MaltaProj2-SourceAudit/1.0'}), timeout=40) as res:
        body = res.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError('Response size limit exceeded')
        return body.decode('utf-8'), {k: res.headers.get(k) for k in ('Date','Age','ETag','Last-Modified')}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixture')
    args = ap.parse_args()
    health = {'attempted_at':utc(), 'sources':[]}
    try:
        if args.fixture:
            html = Path(args.fixture).read_text()
            timestamp = '2026-10-13T17:51:30+00:00'
            headers = {'Date':'Tue, 13 Oct 2026 17:51:30 GMT', 'Age':'3839'}
        else:
            html, headers = fetch(LOBBY)
            timestamp = utc()
        result = parse_lobby(html, timestamp)
        result['http_metadata'] = headers
        (DATA/'matches.json').write_text(json.dumps(result, indent=2)+'\n')
        # Public response only. Never persist cookies or authorization headers.
        (ROOT/'docs/evidence/latest-lobby.txt').write_text(html)
        health['sources'].append({'url':LOBBY,'status':'collected (cache age must be reviewed)', 'headers':headers})
    except Exception as exc:
        health['sources'].append({'url':LOBBY,'status':'failed; previous snapshot retained', 'error':str(exc)})
    if not args.fixture:
        for url in ('https://thunderpick.io/esports/cs2-betting', 'https://www.hltv.org/betting/analytics'):
            try:
                html, headers = fetch(url)
                health['sources'].append({'url':url,'status':'HTTP accessible; no validated current odds adapter', 'headers':headers})
            except Exception as exc:
                health['sources'].append({'url':url,'status':'unavailable; no odds imported','error':str(exc)})
    else:
        health['sources'].append({'url':'https://thunderpick.io/esports/cs2-betting','status':'HTTP 403 / Cloudflare challenge in hosted-runner probe; no bypass attempted'})
    (DATA/'health.json').write_text(json.dumps(health,indent=2)+'\n')

if __name__ == '__main__':
    main()
