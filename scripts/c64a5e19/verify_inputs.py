"""Offline, line-by-line inventory and rating replay from retained official responses."""
import hashlib
import re


def verify(snapshot, evidence, core):
    failures, rows = [], []
    lobby = evidence.get('lobby') or {}
    valve = evidence.get('valve') or {}
    raw = (lobby.get('transfer_state') or {}).get('fixtures') or []
    expected = {}
    for item in raw:
        fx = core.fixture_from_hotspawn(item)
        if fx:
            if fx['fixture_id'] in expected:
                failures.append('Duplicate official fixture ID: ' + fx['fixture_id'])
            expected[fx['fixture_id']] = fx
        elif str(item.get('sport_alias') or '').lower() == 'cs2':
            failures.append('Unparseable CS2 fixture in official lobby response: ' + str(item.get('id')))
    actual = {r['fixture_id']: r for r in snapshot['hotspawn']['fixtures'] if 'lobby_page' in r.get('seen_in', [])}
    if not expected or set(expected) != set(actual):
        failures.append('Lobby inventory differs from retained official response')
    for fid, fx in expected.items():
        confirmed = all(actual.get(fid, {}).get(k) == v for k, v in fx.items())
        if not confirmed:
            failures.append('Fixture fields differ from official response: ' + fid)
        rows.append({'fixture_id': fid, 'source': lobby.get('url'), 'confirmed': confirmed})
    current_meta = snapshot.get('access_log', {}).get('hotspawn_lobby_page', {})
    if current_meta.get('at_utc') != lobby.get('metadata', {}).get('at_utc'):
        failures.append('Fixture observation time differs from retained evidence')
    text = valve.get('markdown', '')
    points = {(m.group(3).strip(), int(m.group(1)), int(m.group(2)), m.group(4).strip())
              for m in re.finditer(r'^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]', text, re.M)}
    teams = snapshot.get('vrs', {}).get('teams', [])
    actual_points = {(r['team'], r['standing'], r['points'], r['roster']) for r in teams}
    if teams and (not points or actual_points != points):
        failures.append('Valve ratings differ from official standings markdown')
    if teams and snapshot['vrs'].get('api_url') != valve.get('url'):
        failures.append('Valve snapshot path differs from retained official source')
    if teams:
        data = text.encode('utf-8')
        git_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if git_sha != valve.get('git_blob_sha'):
            failures.append('Valve official Git blob hash mismatch')
    return {'failures': failures, 'fixture_rows_checked': len(rows), 'rating_rows_checked': len(teams),
            'fixture_rows': rows, 'valve_source': valve.get('url'), 'valve_git_blob_sha': valve.get('git_blob_sha')}
