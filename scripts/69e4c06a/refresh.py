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
