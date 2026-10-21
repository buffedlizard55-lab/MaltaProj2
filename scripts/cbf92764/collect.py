#!/usr/bin/env python3
"""Additional source research ONLY for fixtures without featured market lines.

Uses the existing maintained collector in a subprocess with isolated outputs. No other
session's evidence is edited. Run on a GitHub-hosted runner for unrestricted public reads.
Raw bounded HTTP payloads, failures and per-fixture attempts are retained for audit.
"""
import base64
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import timedelta
from common import ROOT, DATA, CORE, now, read, write, strict_join, RULES

UA = 'Mozilla/5.0 CS2EvidenceDashboard/1.0'
VRS = 'ValveSoftware/counter-strike_regional_standings'


def fetch(url, parse_json=True):
    meta = {'url': url, 'at_utc': CORE.to_iso(now()), 'status': None, 'error': None}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=45) as res:
            body = res.read(3_000_001)
            meta['status'] = res.status
            if len(body) > 3_000_000:
                raise ValueError('response exceeds 3 MB evidence limit')
        meta['sha256'] = hashlib.sha256(body).hexdigest()
        meta['bytes'] = len(body)
        return (json.loads(body) if parse_json else body.decode('utf-8', 'replace')), meta
    except Exception as exc:
        meta['status'] = getattr(exc, 'code', meta['status'])
        meta['error'] = f'{type(exc).__name__}: {exc}'[:300]
        return None, meta


def main():
    # Redirecting OUT is an explicit supported Python-module override, in an isolated
    # process so legacy `import core` cannot collide with this session's imports.
    upstream = DATA / 'upstream'
    upstream.mkdir(parents=True, exist_ok=True)
    if not (upstream / 'snapshot.json').exists():
        for name in ('snapshot.json', 'source_payloads.json', 'vrs_details_cache.json'):
            src = ROOT / 'data/f7279a54' / name
            if src.exists():
                (upstream / name).write_bytes(src.read_bytes())
    code = ("import sys, pathlib; sys.path.insert(0, 'scripts/f7279a54'); import collect; "
            "collect.OUT=pathlib.Path('data/cbf92764/upstream'); raise SystemExit(collect.main())")
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True)
    code = ("import sys, pathlib; sys.path.insert(0, 'scripts/f7279a54'); import build; "
            "build.DATA=pathlib.Path('data/cbf92764/upstream'); "
            "build.SITE=pathlib.Path('data/cbf92764/upstream/rendered'); raise SystemExit(build.main())")
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True)
    board = read(upstream / 'board.json')
    gaps = [r for r in board['open'] if not r.get('line')]
    evidence = {'checked_utc': CORE.to_iso(now()), 'base_generated_utc': board['generated_utc'],
                'gap_ids': [r['fixture_id'] for r in gaps], 'reads': [], 'matches': [], 'quotes': []}
    # First HLTV. No bypass of HTTP challenges; a failure cannot supply a rating/line.
    if gaps:
        body, meta = fetch('https://www.hltv.org/matches', False)
        evidence['reads'].append({**meta, 'kind': 'hltv', 'payload': body})
    # Re-read full-match contract rules from the official retained exchange payload.
    # Ticker/settlement time is never used as a kickoff. Scope strictly to gaps.
    payloads = read(upstream / 'source_payloads.json', {})
    enriched = RULES.enrich_quotes(read(upstream / 'snapshot.json')['quotes'], payloads)
    accepted = [q for q in enriched if q.get('kickoff_evidence')
                and any(strict_join(r, q) for r in gaps)]
    # Store exact official event JSON for independent rule/price replay in the builder.
    source = dict((payloads.get('sources') or {}).get(RULES.KALSHI) or {})
    wanted = {q['event_id'] for q in accepted}
    source['payload'] = {'events': [e for e in (source.get('payload') or {}).get('events', [])
                                    if e.get('event_ticker') in wanted]}
    evidence['exchange_payload'] = {'sources': {RULES.KALSHI: source}}
    evidence['exchange_quotes'] = accepted
    # Then esportsbook prices published by bo3.gg. Do not label a mirror as a direct
    # bookmaker read. Use only the explicitly returned coefficient fields/provider.
    team_cache = {}
    for page in range(6 if gaps else 0):
        url = ('https://api.bo3.gg/api/v1/matches/?filter%5Bmatches.discipline_id%5D%5Beq%5D=1'
               '&filter%5Bmatches.status%5D%5Bin%5D=upcoming'
               f'&page%5Boffset%5D={page*100}&page%5Blimit%5D=100')
        body, meta = fetch(url)
        evidence['reads'].append({**meta, 'kind': 'bo3gg', 'payload': body})
        results = (body or {}).get('results', []) if isinstance(body, dict) else []
        for m in results:
            if m.get('status') != 'upcoming':
                continue
            bu = m.get('bet_updates') or {}
            a, b = bu.get('team_1') or {}, bu.get('team_2') or {}
            ta = a.get('name') or (m.get('team1') or {}).get('name')
            tb = b.get('name') or (m.get('team2') or {}).get('name')
            if not ta or not tb:
                start = CORE.parse_any(m.get('start_date'))
                near_gap = start and any(abs((start-CORE.parse_any(r['start_utc'])).total_seconds()) <= 3600 for r in gaps)
                if not near_gap:
                    continue
                names = []
                for tid in (m.get('team1_id'), m.get('team2_id')):
                    if not tid or len(team_cache) >= 60 and tid not in team_cache:
                        names.append(None)
                        continue
                    if tid not in team_cache:
                        turl = f'https://api.bo3.gg/api/v1/teams/?filter%5Bteams.id%5D%5Beq%5D={tid}&limit=1'
                        data, tmeta = fetch(turl)
                        evidence['reads'].append({**tmeta, 'kind': 'bo3gg_team', 'payload': data})
                        rows = (data or {}).get('results') or []
                        team_cache[tid] = rows[0].get('name') if len(rows)==1 and rows[0].get('id')==tid else None
                    names.append(team_cache[tid])
                ta, tb = names
            if not ta or not tb:
                continue
            q = {'team_a': ta, 'team_b': tb, 'start_utc': m.get('start_date')}
            if not any(strict_join(r, q) for r in gaps):
                continue
            item = {**q, 'event_id': str(m.get('id')), 'public_url': 'https://bo3.gg/matches/' + m.get('slug', ''),
                    'api_url': url, 'retrieved_utc': meta['at_utc'], 'source_key': 'bo3gg',
                    'source_name': 'bo3.gg published coefficients (secondary)', 'provider': bu.get('provider'),
                    'raw_format': 'decimal', 'raw_a': a.get('coeff'), 'raw_b': b.get('coeff'), 'live': False}
            evidence['matches'].append(item)
            if CORE.no_vig(a.get('coeff'), b.get('coeff')):
                evidence['quotes'].append(item)
        if len(results) < 100:
            break
    # Verify the latest officially published file and retain exact bytes + Git blob id.
    directory, meta = fetch(f'https://api.github.com/repos/{VRS}/contents/live/{now().year}')
    evidence['reads'].append({**meta, 'kind': 'valve_directory', 'payload': directory})
    files = sorted([r for r in directory or [] if isinstance(r, dict)
                    and re.fullmatch(r'standings_global_\d{4}_\d{2}_\d{2}\.md', r.get('name', ''))],
                   key=lambda r: r['name']) if isinstance(directory, list) else []
    if files:
        blob, meta = fetch(files[-1]['url'])
        evidence['reads'].append({**meta, 'kind': 'valve_file', 'payload': blob})
        if blob and blob.get('content'):
            md = base64.b64decode(blob['content'])
            git_sha = hashlib.sha1(f'blob {len(md)}\0'.encode() + md).hexdigest()
            if git_sha != blob['sha']:
                raise ValueError('Valve content does not match official Git blob SHA')
            evidence['valve'] = {'latest_file': files[-1]['name'], 'path': blob['path'], 'sha': blob['sha'],
                                 'source_url': f"https://github.com/{VRS}/blob/{blob['sha']}/{blob['name']}",
                                 'checked_utc': meta['at_utc']}
            # GitHub blob URL uses /blob/<SHA> (not a branch/path).
            evidence['valve']['source_url'] = blob['html_url']
            (DATA / 'valve-standings.md').write_bytes(md)
    write(DATA / 'research.json', evidence)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
