"""Ordinary public-lobby revalidation; freshness still comes from returned evidence.

The unversioned Angular lobby can be cached for hours after new fixtures are added.
A distinct public query plus no-cache headers asks for revalidation; it does not prove
that revalidation happened. Returned Age and the original response clock are retained.
"""
from datetime import datetime, timezone

LOBBY = 'https://play.hotspawn.com/lobby'


def fetch_recent_lobby(fetch, url, headers=None, timeout=45, now=None):
    if url != LOBBY:
        return fetch(url, headers, timeout)
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')
    requested = url + '?cs2_refresh=' + stamp
    request_headers = dict(headers or {})
    request_headers.update({'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    body, original_meta = fetch(requested, request_headers, timeout)
    meta = dict(original_meta)
    meta['url'] = url  # logical source; actual HTTP request is retained separately
    meta['request_url'] = requested
    meta['cache_revalidation_requested'] = True
    return body, meta


def scope_fixture_clock(snapshot, core):
    """Conservatively scope a private working copy; never revive a fallback clock.

    A backup timestamp is not a substitute for the retained successful HTTP/cache
    metadata. If two clocks survive, the earlier observation bounds eligibility.
    Source JSON passed by the caller is not edited by the canonical builder.
    """
    log = snapshot.setdefault('access_log', {})
    meta = log.get('hotspawn_lobby_page') or {}
    observed = core.parse_iso(meta.get('at_utc'))
    evaluated = core.parse_iso(snapshot.get('collected_to_utc'))
    retained_value = snapshot.get('hotspawn_fallback_from')
    retained = core.parse_iso(retained_value)
    valid = (meta.get('status') == 200 and observed is not None and evaluated is not None
             and observed <= evaluated and (not retained_value or retained is not None and retained <= evaluated))
    if not valid:
        snapshot['hotspawn_fallback_from'] = None
        log['hotspawn_lobby_page'] = {**meta, 'at_utc': None}
        return {'eligible_clock': False, 'reason': 'Missing, failed, invalid or future retained HTTP observation; backup timestamp alone cannot establish freshness.'}
    if retained:
        snapshot['hotspawn_fallback_from'] = core.to_iso(min(observed, retained))
    return {'eligible_clock': True, 'reason': 'Earliest retained HTTP/fallback clock with unchanged cache Age; normal age and lock gates still apply.'}
