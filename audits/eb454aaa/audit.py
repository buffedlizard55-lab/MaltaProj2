#!/usr/bin/env python3
"""Read-only safety audit. No network collection, no forecast, no writes outside own scope.

Reproduce: python audits/eb454aaa/audit.py
The report is a dated evidence review, not a replacement live picks board.
"""
from __future__ import annotations
import hashlib
import html
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
LOBBY = 'https://play.hotspawn.com/lobby'
REPO = 'https://github.com/buffedlizard55-lab/MaltaProj2/blob/'


def utc(value):
    """Do not assume a timezone for an unqualified timestamp."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            n = float(value)
            return datetime.fromtimestamp(n / (1000 if n > 1e11 else 1), timezone.utc)
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def fair(a, b):
    """Independent arithmetic only; this function does not establish source identity."""
    try:
        a, b = float(a), float(b)
        if not all(math.isfinite(n) and n > 1 for n in (a, b)):
            return None
        total = 1/a + 1/b
        return (1/a/total, 1/b/total)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def quote_flags(row, q, observed):
    flags = []
    if q.get('market_is_live') is not False:
        flags.append('live_or_unknown_market_state')
    if str(q.get('market_status', '')).casefold() not in ('open', 'o'):
        flags.append('market_state_not_confirmed_open')
    if not (q.get('source_api_url') or q.get('source_public_url')):
        flags.append('missing_source_link')
    retrieved = utc(q.get('retrieved_at_utc'))
    if not retrieved or not observed or not 0 <= (observed-retrieved).total_seconds() <= 4*3600:
        flags.append('missing_stale_or_future_observation')
    start, source_start = utc(row.get('start_time_utc')), utc(q.get('start_time_utc'))
    if not start or not source_start:
        flags.append('missing_explicit_start_time')
    elif abs((start-source_start).total_seconds()) > 90*60:
        flags.append('start_time_disagreement_over_90_minutes')
    if source_start and observed and source_start <= observed:
        flags.append('source_kickoff_has_passed')
    if q.get('aliases_applied'):
        flags.append('team_alias_requires_primary_identity_review')
    probs = fair(q.get('decimal_odds_a'), q.get('decimal_odds_b'))
    if probs is None:
        flags.append('invalid_decimal_odds')
    else:
        if q.get('side_order') == 'reversed':
            probs = probs[::-1]
        for actual, expected in zip((q.get('implied_prob_a'), q.get('implied_prob_b')), probs):
            if not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual-expected) > 0.000051:
                flags.append('per_source_probability_arithmetic_mismatch')
                break
    return sorted(set(flags))


def audit(doc, inventory):
    observed = utc(doc.get('generated_at_utc'))
    raw_by_id = {str(f['fixture_id']): f for f in inventory['fixtures']}
    uses = defaultdict(set)
    for r in doc['fixtures']:
        for q in r.get('quotes', []):
            uses[(q.get('source_key'), q.get('source_event_id'), q.get('source_market_id'))].add(r['fixture_id'])
    rows, counts = [], Counter()
    for r in doc['fixtures']:
        flags, quotes = [], []
        start = utc(r.get('start_time_utc'))
        raw = raw_by_id.get(str(r['fixture_id']))
        if not raw:
            flags.append('fixture_missing_from_captured_inventory')
        else:
            for key in ('game', 'team_a', 'team_b', 'status'):
                if raw.get(key) != r.get(key):
                    flags.append('fixture_field_mismatch_'+key)
        if not r.get('quotes'):
            flags.append('no_external_line')
        if not start or not observed or start <= observed:
            flags.append('fixture_not_strictly_future_at_snapshot')
        if str(r.get('status', '')).casefold() != 'scheduled':
            flags.append('fixture_state_not_scheduled')
        lock = utc(raw.get('lock_time')) if raw else None
        if not lock:
            flags.append('pick_lock_unconfirmed')
        elif observed and lock <= observed:
            flags.append('pick_lock_has_passed')
        for q in r.get('quotes', []):
            qflags = quote_flags(r, q, observed)
            key = (q.get('source_key'), q.get('source_event_id'), q.get('source_market_id'))
            if len(uses[key]) > 1:
                qflags.append('quote_joined_to_multiple_fixtures')
            flags.extend(qflags)
            quotes.append({'source': q.get('source_key'), 'event_id': q.get('source_event_id'),
                           'source_url': q.get('source_api_url') or q.get('source_public_url'),
                           'raw_decimal_a': q.get('decimal_odds_a'), 'raw_decimal_b': q.get('decimal_odds_b'),
                           'market_state': q.get('market_status'), 'is_live': q.get('market_is_live'),
                           'retrieved_at_utc': q.get('retrieved_at_utc'), 'source_start_time_utc': q.get('start_time_utc'),
                           'flags': sorted(set(qflags))})
        c = r.get('consensus')
        if c and r.get('quotes'):
            qa = [q.get('implied_prob_a') for q in r['quotes']]
            qb = [q.get('implied_prob_b') for q in r['quotes']]
            if all(isinstance(n, (float, int)) and math.isfinite(n) for n in qa+qb):
                if any(abs(c.get(k, -1)-sum(ns)/len(ns)) > 0.000051 for k, ns in (('prob_a',qa),('prob_b',qb))):
                    flags.append('consensus_arithmetic_mismatch')
            else:
                flags.append('invalid_consensus_inputs')
        if not r.get('quotes') and (c is not None or r.get('pick') is not None):
            flags.append('probability_without_external_line')
        flags = sorted(set(flags))
        counts.update(flags)
        rows.append({'fixture_id':r['fixture_id'], 'game':r['game'], 'team_a':r['team_a'], 'team_b':r['team_b'],
                     'start_time_utc':r.get('start_time_utc'), 'source_status':r.get('status'),
                     'source_link':r.get('hotspawn_match_url') or LOBBY, 'snapshot_future_label':bool(r.get('is_future')),
                     'pick_lock_utc':lock.isoformat() if lock else None, 'quotes':quotes, 'flags':flags,
                     'prob_a':None, 'prob_b':None, 'pick':None,
                     'assessment':'needs review' if flags else 'mechanical checks passed; primary identity not independently certified'})
    return {'snapshot_utc':doc.get('generated_at_utc'), 'rows':rows, 'flag_counts':dict(sorted(counts.items())),
            'summary':{'inventory_rows':len(rows), 'labeled_future_rows':sum(r['snapshot_future_label'] for r in rows),
                       'quoted_rows':sum(bool(r['quotes']) for r in rows),
                       'future_quoted_rows':sum(r['snapshot_future_label'] and bool(r['quotes']) for r in rows),
                       'future_quoted_rows_with_safety_flags':sum(r['snapshot_future_label'] and bool(r['quotes']) and bool(r['flags']) for r in rows)},
            'policy':'All audit probability/pick fields deliberately blank. Passing arithmetic is not verified predictive accuracy, fixture identity, or a certified current market.'}


def page(title, body):
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'''+html.escape(title)+'''</title><style>
[hidden]{display:none!important}:root{font-family:system-ui,sans-serif;color:#e9eef9;background:#101725;color-scheme:dark}body{margin:0}main,nav{max-width:1150px;margin:auto;padding:24px}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#8adbd3;overflow-wrap:anywhere}h1{font-size:clamp(1.7rem,5vw,2.6rem)}p{line-height:1.65;max-width:85ch}.notice{background:#263124;border-left:4px solid #e7bd6f;padding:18px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px;border-bottom:1px solid #364155;vertical-align:top}th{color:#91abae}small{display:block;color:#b4bfce}.tag{color:#eac782}code{overflow-wrap:anywhere}details{padding:12px}input{padding:12px;width:min(90%,420px);margin:16px 0} @media(max-width:650px){main,nav{padding:16px}table.cards thead{display:none}table.cards,table.cards tbody,table.cards tr,table.cards td{display:block}table.cards tr{border:1px solid #364155;margin:14px 0;border-radius:12px}table.cards td{border:0;padding:10px 14px}table.cards td:before{content:attr(data-label);display:block;color:#91abae;font-size:.8rem}td,th{overflow-wrap:anywhere}}
</style></head><body><nav><a href="../../index.html">Main dashboard</a><a href="../../market/index.html">Expanded board</a><a href="index.html">Audit overview</a><a href="flagged.html">Flagged for Review</a><a href="rows.html">Row-by-row audit</a></nav><main><h1>'''+html.escape(title)+'''</h1>'''+body+'''<p>This dated audit does not certify live odds. Recheck the linked original source before acting. No guarantees of winning or model calibration.</p></main></body></html>'''


def render(report):
    e = lambda v: html.escape(str(v))
    snap = e(report['snapshot_utc'])
    s = report['summary']
    intro = f'<p class="notice">Dated review of the expanded board at {snap}. This is not a new live source read. Probabilities and picks are intentionally blank in this audit: source links and correct arithmetic alone do not verify event identity or predictive accuracy.</p>'
    overview = intro+f'<p>Reviewed {s["inventory_rows"]} API-inventory rows, including {s["labeled_future_rows"]} labeled future. {s["future_quoted_rows"]} future rows contain quotes; {s["future_quoted_rows_with_safety_flags"]} of those have safety review flags. Inventory inclusion does not prove a match is visible or currently pickable in the lobby.</p><p><a href="report.json">Machine-readable row audit</a> · <a href="valve_verification.json">Official Valve byte comparison</a> · <a href="REPORT.md">Scope and reproduction</a></p>'
    v = json.loads((OUT/'valve_verification.json').read_text())
    overview += '<h2>Official Valve source verification</h2><div class="table-wrap"><table><thead><tr><th>Standings file</th><th>Result</th><th>Official source</th></tr></thead><tbody>'
    for f in v['files']:
        overview += f'<tr><td>{e(Path(f["file"]).name)}</td><td>{"Byte-for-byte match" if f.get("byte_match") else "Unverified"}</td><td><a href="{e(f["official_url"])}">Valve repository</a></td></tr>'
    overview += '</tbody></table></div><p>Rating-source verification does not validate the Elo-style scale-400 probability conversion; that is a modeling assumption.</p>'
    (OUT/'index.html').write_text(page('Independent market safety audit',overview))
    findings = [
        ('F1','Non-open market state','Two captured Bovada quotes have state S and are used in future-row consensus. Their state is not confirmed open; this audit does not infer the provider’s undocumented state semantics. Require explicitly open markets.', 'https://www.bovada.lv/services/sports/event/v2/events/A/description/esports'),
        ('F2','Five-hour start disagreement','Four joins for two LoL fixtures have a 300-minute start discrepancy. One shared competition token allows a join up to 720 minutes, while the published method describes 90 minutes. Do not certify the join without an official schedule/identity reconciliation.', LOBBY),
        ('F3','In-play consensus','The captured ex-Keyd Stars–Galorys row includes an in-play Bovada quote. It is a past fixture and is flagged as past by the board, but the consensus calculation still uses the live value. Separate prematch and in-play inputs.', 'https://www.bovada.lv/services/sports/event/v2/events/A/description/esports'),
        ('F4','No freshness/lock gate in expanded consensus','The expanded build joins and averages quotes without checking quote age, market open state, or fixture pick-lock time. A scheduled refresh is not a validity gate. Apply the root current-board safety rules before showing a current pick.', REPO+'2f8c99290224da556b05cc74a6ec340ab7de0e31/scripts/expanded/collect_lines.py'),
        ('F5','Outcome ordering assumption','The expanded Bovada parser assigns outcome prices by array position rather than competitorId. Captured samples inspected here align; no actual reversed-price incident is asserted. Reordering outcomes would silently invert prices. Join prices by competitorId and require a bijection.', 'https://www.bovada.lv/services/sports/event/v2/events/A/description/esports'),
        ('F6','Publication can continue after errors','expanded-lines.yml converts collector, origination, verifier, renderer and local-link errors to successful echo commands; its commit step runs always. A failed refresh can publish mixed/stale files without failing the workflow. Preserve evidence separately; make validation and atomic publication fail closed.', REPO+'2f8c99290224da556b05cc74a6ec340ab7de0e31/.github/workflows/expanded-lines.yml'),
        ('F7','API inventory is not lobby eligibility','The expanded inventory contains 821 forfeited records, mostly historical. Its future subset also includes a started fixture. Enumerating the full API is useful, but it is not evidence that every API row is currently offered in the pick’em lobby.', LOBBY),
        ('F8','Model probabilities are estimates','Official Valve ratings match, but the scale-400 conversion is not an official Valve win probability and no calibration is demonstrated here. The board labels originated estimates, but its footer also says nothing is estimated. Correct that conflicting statement.', 'https://github.com/ValveSoftware/counter-strike_regional_standings'),
    ]
    report['findings'] = [dict(zip(('id','title','detail','source_url'),f)) for f in findings]
    body = intro+'<p>These findings do not prove every quote is wrong. They limit what may be called verified. Owners retain their scopes; requested fixes are recorded in COORDINATION.md.</p><div class="table-wrap"><table class="cards"><thead><tr><th>Finding</th><th>Evidence / requested action</th><th>Source</th></tr></thead><tbody>'
    for ident,title,detail,url in findings:
        body += f'<tr><td data-label="Finding"><strong>{ident}: {e(title)}</strong><small>Needs review</small></td><td data-label="Evidence / action">{e(detail)}</td><td data-label="Source"><a href="{e(url)}">Original source</a></td></tr>'
    body += '</tbody></table></div><p><a href="rows.html">Inspect per-fixture flags and linked quotes</a>. Exact input SHA-256 fingerprints are recorded in <a href="report.json">report.json</a>.</p>'
    (OUT/'flagged.html').write_text(page('Flagged for Review — market safety',body))
    body = intro+'<p>All labeled-future rows, plus any historical quoted rows. Blank probability cells are deliberate. “Mechanical checks passed” is not an independent primary-source certification.</p><label for="filter">Filter by team, fixture, game or flag</label><br><input id="filter" placeholder="Search audit rows…"><div class="table-wrap"><table class="cards"><thead><tr><th>Fixture / source</th><th>Probability / pick</th><th>Quote evidence</th><th>Assessment</th></tr></thead><tbody>'
    for r in report['rows']:
        if not r['snapshot_future_label'] and not r['quotes']:
            continue
        qs = ''.join(f'<details><summary>{e(q["source"])}, state {e(q["market_state"])}</summary><a href="{e(q["source_url"])}">Official provider endpoint</a><small>Read {e(q["retrieved_at_utc"])} · source start {e(q["source_start_time_utc"])} · live {e(q["is_live"])}</small><small>Raw decimal {e(q["raw_decimal_a"])} / {e(q["raw_decimal_b"])}</small></details>' for q in r['quotes']) or 'No external quote'
        body += f'<tr><td data-label="Fixture / source"><strong>{e(r["team_a"])} vs {e(r["team_b"])}</strong><small>{e(r["game"])} · {e(r["fixture_id"])} · {e(r["start_time_utc"])} · {e(r["source_status"])}</small><a href="{e(r["source_link"])}">HotSpawn fixture source</a></td><td data-label="Probability / pick"></td><td data-label="Quote evidence">{qs}</td><td data-label="Assessment"><span class="tag">{e(r["assessment"])}</span><small>{e("; ".join(r["flags"]))}</small></td></tr>'
    body += '</tbody></table></div><script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>'
    (OUT/'rows.html').write_text(page('Row-by-row safety review',body))


def main():
    inputs = ['data/expanded/lines.json','data/expanded/fixtures.json','scripts/expanded/lines_core.py','scripts/expanded/collect_lines.py','.github/workflows/expanded-lines.yml']
    report = audit(json.loads((ROOT/inputs[0]).read_text()),json.loads((ROOT/inputs[1]).read_text()))
    report['input_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
    report['audited_at_utc'] = datetime.now(timezone.utc).isoformat()
    render(report)
    (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report['summary'],indent=2))
    print(json.dumps(report['flag_counts'],indent=2))

if __name__ == '__main__':
    main()
