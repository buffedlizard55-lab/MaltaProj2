"""Rule-backed Kalshi kickoff evidence, scoped to canonical market gaps.

Never interpret a ticker, occurrence_datetime, close or settlement time as kickoff.
Both binary full-match contracts must explicitly agree on the originally scheduled
CS2 match time and timezone. The shared collector and other dashboards are unchanged.
"""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KALSHI = ('https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCS2GAME'
          '&status=open&with_nested_markets=true&limit=200')
RULE_TIME = re.compile(
    r'CS2 match originally scheduled for '
    r'([A-Z][a-z]{2} \d{1,2}, \d{4} at \d{1,2}:\d{2} [AP]M) (EDT|EST|UTC|GMT)'
    r', then the market resolves to Yes\.$')


def _price(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 < number < 1 else None


def rule_evidence(event):
    """Return explicit, internally consistent contract evidence, or fail closed."""
    if (event.get('series_ticker') != 'KXCS2GAME'
            or event.get('mutually_exclusive') is not True
            or event.get('product_metadata', {}).get('competition') != 'CS2'
            or event.get('product_metadata', {}).get('competition_scope') != 'Game'):
        return None
    markets = event.get('markets') or []
    if len(markets) != 2 or any(m.get('status') not in ('active', 'open') for m in markets):
        return None
    names = [m.get('yes_sub_title') for m in markets]
    if any(not isinstance(n, str) or not n.strip() for n in names) or names[0] == names[1]:
        return None
    title = event.get('title')
    if title not in (names[0] + ' vs. ' + names[1], names[1] + ' vs. ' + names[0]):
        return None
    times, outcomes, rules = [], [], []
    for market, name in zip(markets, names):
        rule = market.get('rules_primary') or ''
        secondary = market.get('rules_secondary') or ''
        prefix = 'If ' + name + ' wins the '
        match = RULE_TIME.search(rule)
        if (market.get('market_type') != 'binary'
                or market.get('event_ticker') != event.get('event_ticker')
                or market.get('title') != name + ' wins'
                or not rule.startswith(prefix) or not match
                or ': ' + title + ' ' not in rule[:match.start()]
                or 'refers to the full match' not in secondary
                or match.group(0).split(', then ')[0] not in secondary):
            return None
        try:
            local = datetime.strptime(match.group(1), '%b %d, %Y at %I:%M %p')
        except ValueError:
            return None
        zone = match.group(2)
        if zone in ('EDT', 'EST'):
            local = local.replace(tzinfo=ZoneInfo('America/New_York'))
            # An explicit abbreviation that contradicts DST is not silently corrected.
            if local.tzname() != zone:
                return None
        else:
            local = local.replace(tzinfo=timezone.utc)
        times.append(local.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        bid, ask = _price(market.get('yes_bid_dollars')), _price(market.get('yes_ask_dollars'))
        if bid is None or ask is None or ask < bid or ask - bid > 0.100000001:
            return None
        outcomes.append({'team': name, 'bid_dollars': bid, 'ask_dollars': ask,
                         'mid_dollars': round((bid + ask) / 2, 4),
                         'volume_contracts_reported': market.get('volume_fp'),
                         'volume_24h_contracts_reported': market.get('volume_24h_fp')})
        rules.append(rule)
    if times[0] != times[1]:
        return None
    return {'kind': 'explicit_full_match_contract_rules', 'start_utc': times[0],
            'rules_primary': rules, 'outcomes': outcomes,
            'occurrence_datetime_not_used': [m.get('occurrence_datetime') for m in markets],
            'limitation': 'Normalized two-outcome yes midpoints, not executable bookmaker odds. '
                          'Reported volume can be low or zero; no liquidity or calibration guarantee.'}


def enrich_quotes(quotes, payloads):
    """Derive evidence from official JSON, also used during independent offline replay.

    No caller-supplied normalized timestamp/evidence is trusted. Previously attached
    extensions are removed before revalidation, so a changed/missing payload fails closed.
    """
    source = (payloads.get('sources') or {}).get(KALSHI) or {}
    events = (source.get('payload') or {}).get('events') or []
    # Duplicate event IDs are ambiguous, not last-row-wins.
    indexed, duplicate = {}, set()
    for event in events:
        ticker = event.get('event_ticker')
        if ticker in indexed:
            duplicate.add(ticker)
        indexed[ticker] = event
    result = copy.deepcopy(quotes)
    for quote in result:
        if quote.get('source_key') != 'kalshi':
            continue
        quote.pop('kickoff_evidence', None)
        quote.pop('fallback_only', None)
        quote['start_utc'], quote['start_is_approx'] = None, True
        # The accepted shared parser already enforces two outcomes and bid/ask gates.
        # Check arithmetic/identity against the payload again instead of blessing fields.
        event = indexed.get(quote.get('event_id'))
        if (source.get('http_status') != 200 or quote.get('api_url') != KALSHI
                or quote.get('event_id') in duplicate or not event or quote.get('live')
                or not source.get('retrieved_utc')
                or quote.get('raw_format') != 'yes mid ($)'):
            continue
        evidence = rule_evidence(event)
        if not evidence:
            continue
        outcomes = evidence['outcomes']
        if [quote.get('team_a'), quote.get('team_b')] != [x['team'] for x in outcomes]:
            continue
        try:
            valid = all(abs(float(quote.get('raw_' + side)) - outcomes[i]['mid_dollars']) < 1e-8
                        for i, side in enumerate(('a', 'b')))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            continue
        quote.update(start_utc=evidence['start_utc'], start_is_approx=False,
                     retrieved_utc=source['retrieved_utc'],
                     fallback_only=True, kickoff_evidence=evidence)
    return result


def select_for_gaps(inputs, primary_board, core):
    """Do not reprice an already accepted bookmaker/featured match with research."""
    gaps = [row for row in primary_board['open'] if not row.get('market')]
    kept, excluded = [], []
    for quote in inputs.get('quotes', []):
        if not quote.get('fallback_only'):
            kept.append(quote)
            continue
        joins = [core.match_quote(row, quote) for row in gaps]
        if any(join and not join.get('rejected') for join in joins):
            kept.append(quote)
        else:
            excluded.append({'source_key': quote['source_key'], 'event_id': quote['event_id'],
                             'reason': 'Rule-backed exchange research is used only for an open market gap.'})
    return kept, excluded


def normalize_saved_capture(data_dir):
    """Reparse a retained capture without any network request or refreshed clock."""
    import json
    from pathlib import Path
    directory = Path(data_dir)
    snapshot_path = directory / 'snapshot.json'
    snapshot = json.loads(snapshot_path.read_text())
    payloads = json.loads((directory / 'source_payloads.json').read_text())
    snapshot['quotes'] = enrich_quotes(snapshot['quotes'], payloads)
    snapshot['exchange_rule_policy'] = 'explicit-full-match-rules; market-gaps-only'
    snapshot_path.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False, allow_nan=False) + '\n')
    return snapshot


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Reparse retained official rules; never reset observation clocks.')
    parser.add_argument('--normalize-capture', required=True)
    args = parser.parse_args()
    normalize_saved_capture(args.normalize_capture)
